"""Experimentos acotados de reserva de escritura y backup, sin codigo operativo."""

import faulthandler
import json
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch


_CONNECT = sqlite3.connect
_TIMEOUT = 15


def _experimento(raiz, modo, caso):
    comprobar = unittest.TestCase()
    conexiones = []
    abiertas = []
    eventos = []
    resultado = {"modo": modo, "caso": caso, "sqlite": sqlite3.sqlite_version}

    def autorizar(accion, _uno, _dos, _base, _origen):
        return sqlite3.SQLITE_DENY if accion == sqlite3.SQLITE_ATTACH else sqlite3.SQLITE_OK

    def conectar(base, *args, **kwargs):
        if args or kwargs.get("uri"):
            raise AssertionError("URI y argumentos posicionales no autorizados.")
        ruta = Path(base)
        if not ruta.is_absolute() or not ruta.is_relative_to(raiz):
            raise AssertionError("Ruta fuera del temporal.")
        ruta = ruta.resolve()
        if not ruta.is_relative_to(raiz) or "fm_master" in ruta.name.lower():
            raise AssertionError("Base no autorizada.")
        conexion = _CONNECT(ruta, timeout=0.05, **kwargs)
        conexion.set_authorizer(autorizar)
        conexiones.append(conexion)
        abiertas.append(str(ruta))
        return conexion

    def filas(conexion):
        return conexion.execute("SELECT id, valor FROM muestra ORDER BY id").fetchall()

    try:
        with ExitStack() as recursos:
            recursos.enter_context(patch("sqlite3.connect", conectar))
            recursos.enter_context(patch("sqlite3.dbapi2.connect", conectar))

            def abrir(nombre):
                conexion = sqlite3.connect(raiz / nombre)
                recursos.callback(conexion.close)
                return conexion

            a = abrir("origen_ficticio.sqlite")
            comprobar.assertEqual(a.execute(f"PRAGMA journal_mode={modo}").fetchone()[0], modo.lower())
            if modo == "WAL":
                a.execute("PRAGMA wal_autocheckpoint=0")
            a.execute("CREATE TABLE muestra(id INTEGER PRIMARY KEY, valor TEXT NOT NULL)")
            a.executemany("INSERT INTO muestra VALUES(?, ?)", [(i, f"{i}:" + "x" * 2000) for i in range(80)])
            a.commit()
            if modo == "WAL":
                comprobar.assertGreater((raiz / "origen_ficticio.sqlite-wal").stat().st_size, 0)
                resultado["wal_presente"] = True
            inicial = filas(a)
            b = abrir("origen_ficticio.sqlite")
            lector = abrir("origen_ficticio.sqlite")
            lector.execute("PRAGMA query_only=ON")
            lector.execute("BEGIN")
            comprobar.assertEqual(filas(lector), inicial)
            destino = abrir("respaldo_ficticio.sqlite")
            if caso != "negativo":
                a.execute("BEGIN IMMEDIATE")
                comprobar.assertTrue(a.in_transaction)

            if caso == "guardia":
                with comprobar.assertRaises(AssertionError):
                    sqlite3.connect(raiz / "fm_master_ficticia.sqlite")
                with comprobar.assertRaises(AssertionError):
                    sqlite3.dbapi2.connect(raiz.parent / "ajena_ficticia.sqlite")
                with comprobar.assertRaises(AssertionError):
                    sqlite3.connect("file::memory:", uri=True)
                with comprobar.assertRaises(sqlite3.DatabaseError):
                    a.execute("ATTACH ':memory:' AS ajena")

            limite = time.monotonic() + 2
            progreso = []

            def avanzar(estado, pendientes, total):
                progreso.append((estado, pendientes, total))
                if caso == "error":
                    raise RuntimeError("error ficticio de backup")
                if time.monotonic() > limite:
                    raise TimeoutError("Backup excedio su plazo.")

            inicio = time.monotonic()
            if caso == "error":
                with comprobar.assertRaisesRegex(RuntimeError, "error ficticio"):
                    lector.backup(destino, pages=1, progress=avanzar, sleep=0.01)
                comprobar.assertTrue(a.in_transaction)
                a.rollback()
                comprobar.assertFalse(a.in_transaction)
                lector.rollback()
                b.execute("UPDATE muestra SET valor='despues del error' WHERE id=0")
                b.commit()
                comprobar.assertEqual(filas(a)[0][1], "despues del error")
                resultado["rollback_error"] = True
            else:
                lector.backup(destino, pages=1, progress=avanzar, sleep=0.01)
                comprobar.assertEqual(progreso[-1][0], sqlite3.SQLITE_DONE)
                comprobar.assertEqual(destino.execute("PRAGMA integrity_check").fetchall(), [("ok",)])
                comprobar.assertEqual(filas(destino), inicial)
                comprobar.assertFalse(destino.in_transaction)
                eventos.append("backup_verificado")
                comprobar.assertEqual(filas(lector), inicial)
                lector.rollback()
                comprobar.assertEqual(filas(b), inicial)
                if caso == "negativo":
                    b.execute("UPDATE muestra SET valor='externo confirmado' WHERE id=0")
                    b.commit()
                    a.execute("BEGIN IMMEDIATE")
                    comprobar.assertNotEqual(filas(a), filas(destino))
                    comprobar.assertEqual(len(filas(a)), len(filas(destino)))
                    a.rollback()
                    resultado["divergencia_demostrada"] = True
                else:
                    comprobar.assertTrue(a.in_transaction)
                    with comprobar.assertRaises(sqlite3.OperationalError) as bloqueo:
                        b.execute("UPDATE muestra SET valor='no autorizado' WHERE id=0")
                        b.commit()
                    comprobar.assertEqual(bloqueo.exception.sqlite_errorcode, sqlite3.SQLITE_BUSY)
                    b.rollback()
                    comprobar.assertEqual(filas(b), inicial)
                    comprobar.assertEqual(filas(a), filas(destino))
                    eventos.append("escritura_bloqueada_busy")
                    a.execute("UPDATE muestra SET valor='cambio ficticio de A' WHERE id=0")
                    if caso == "commit":
                        a.commit()
                        comprobar.assertEqual(filas(b)[0][1], "cambio ficticio de A")
                    else:
                        a.rollback()
                        comprobar.assertEqual(filas(b), inicial)
                    comprobar.assertFalse(a.in_transaction)
                    comprobar.assertEqual(filas(destino), inicial)
                    b.execute("UPDATE muestra SET valor='B despues de liberar' WHERE id=0")
                    b.commit()
                    comprobar.assertEqual(filas(a)[0][1], "B despues de liberar")
                    resultado["escritura_bloqueada"] = True
                    resultado["escritura_posterior"] = True
            resultado["segundos"] = round(time.monotonic() - inicio, 4)
            comprobar.assertTrue(progreso)
            resultado["paginas"] = progreso[0][2]
            resultado["eventos"] = eventos
    finally:
        # ExitStack cierra primero; comprobar el cierre sin reabrir los archivos.
        for conexion in conexiones:
            with comprobar.assertRaises(sqlite3.ProgrammingError):
                conexion.execute("SELECT 1")
    resultado["conexiones_cerradas"] = len(conexiones)
    comprobar.assertEqual(len(abiertas), 4)
    return resultado


class ConcurrenciaBackupTests(unittest.TestCase):
    def experimentar(self, caso):
        for modo in ("DELETE", "WAL"):
            with self.subTest(modo=modo), tempfile.TemporaryDirectory(prefix="sqlite_3d4c2_") as temporal:
                proceso = subprocess.run(
                    [sys.executable, "-B", str(Path(__file__).resolve()),
                     "--experimento", temporal, modo, caso],
                    capture_output=True, text=True, timeout=_TIMEOUT, check=False,
                )
                self.assertEqual(proceso.returncode, 0, proceso.stdout + proceso.stderr)
                resultado = json.loads(proceso.stdout)
                self.assertEqual(resultado["conexiones_cerradas"], 4)
                print(json.dumps(resultado, sort_keys=True), flush=True)

    def test_reserva_backup_lecturas_y_commit(self):
        self.experimentar("commit")

    def test_reserva_backup_lecturas_y_rollback(self):
        self.experimentar("rollback")

    def test_error_backup_permite_rollback_y_cierra(self):
        self.experimentar("error")

    def test_control_negativo_sin_reserva_diverge(self):
        self.experimentar("negativo")

    def test_guardias_solo_permiten_bases_temporales_ficticias(self):
        self.experimentar("guardia")

    def test_supervisor_termina_proceso_que_no_responde(self):
        with self.assertRaises(subprocess.TimeoutExpired):
            subprocess.run(
                [sys.executable, "-B", "-c", "import time; time.sleep(30)"],
                capture_output=True, timeout=0.2, check=False,
            )


if __name__ == "__main__":
    if len(sys.argv) == 5 and sys.argv[1] == "--experimento":
        faulthandler.dump_traceback_later(5)
        try:
            print(json.dumps(_experimento(Path(sys.argv[2]).resolve(), sys.argv[3], sys.argv[4])))
        finally:
            faulthandler.cancel_dump_traceback_later()
    else:
        unittest.main()
