"""Servicio real, reserva SQLite y escritores externos sobre bases descartables."""

import faulthandler
import sys
import time

_INICIO_MODULO = time.perf_counter()
# El arranque de un proceso Python en Windows tarda 1-3 s; el limite estricto se aplica
# a la operacion SQLite medida dentro del escritor, no al arranque del interprete.
_PLAZO_SQLITE = 1.0
_PLAZO_ESCRITOR = 15
_PLAZO_ESCENARIO = 90
_MODO_HIJO = (
    __name__ == "__main__" and len(sys.argv) >= 3
    and sys.argv[1] in ("--escritor", "--experimento")
)
if _MODO_HIJO:
    faulthandler.dump_traceback_later(
        _PLAZO_ESCRITOR - 3 if sys.argv[1] == "--escritor" else _PLAZO_ESCENARIO - 10,
        exit=True,
    )

import importlib.util
import json
import os
import re
import sqlite3
import subprocess
import tempfile
import unittest
from contextlib import ExitStack, contextmanager
from pathlib import Path
from types import ModuleType
from unittest.mock import patch
from urllib.parse import unquote, urlsplit


_CONNECT = sqlite3.connect
_ARCHIVO = Path(__file__).resolve()
_SERVICIO = _ARCHIVO.parents[1] / "services" / "backup_service.py"
_ESQUEMA = "SELECT type, name, tbl_name, sql FROM sqlite_master ORDER BY type, name"
_PUBLICADO = re.compile(r"pre_migracion_\d{8}_\d{6}_[0-9a-f]{8}\.db")
_DURANTE = {}


class FalloCopia(sqlite3.Connection):
    def backup(self, destino, **kwargs):
        def interrumpir(_estado, _pendientes, _total):
            raise RuntimeError("fallo de copia simulado")

        return super().backup(destino, pages=1, progress=interrumpir, sleep=0.01)


class CopiaInterrumpida(sqlite3.Connection):
    def backup(self, destino, **kwargs):
        def interrumpir(_estado, _pendientes, _total):
            raise KeyboardInterrupt("interrupcion simulada")

        return super().backup(destino, pages=1, progress=interrumpir, sleep=0.01)


class CopiaConEscritorConcurrente(sqlite3.Connection):
    """Copia por paginas y lanza un escritor externo con la copia a medio hacer."""

    def backup(self, destino, **kwargs):
        def progreso(_estado, pendientes, total):
            if pendientes and "externo_durante_copia" not in _DURANTE:
                _DURANTE["externo_durante_copia"] = _escritor_externo(_DURANTE["raiz"], "SQLITE_BUSY")
                _DURANTE["paginas"] = {"pendientes": pendientes, "total": total}

        return super().backup(destino, pages=1, progress=progreso, sleep=0.001)


class IntegridadInvalida(sqlite3.Connection):
    def execute(self, sql, *args, **kwargs):
        if sql == "PRAGMA integrity_check":
            return super().execute("SELECT 'integridad invalida simulada'")
        return super().execute(sql, *args, **kwargs)


@contextmanager
def _aislamiento(raiz, caso):
    conexiones = []
    permitir_version = [True]
    with ExitStack() as recursos:
        def autorizar(accion, uno, dos, _base, _origen):
            if accion == sqlite3.SQLITE_ATTACH:
                return sqlite3.SQLITE_DENY
            if (accion == sqlite3.SQLITE_PRAGMA and uno.lower() == "user_version"
                    and dos is not None and not permitir_version[0]):
                return sqlite3.SQLITE_DENY
            return sqlite3.SQLITE_OK

        def conectar(base, *args, **kwargs):
            if args:
                raise AssertionError("Argumentos posicionales no autorizados.")
            texto = os.fspath(base)
            if kwargs.get("uri"):
                uri = urlsplit(texto)
                if (uri.scheme != "file" or uri.netloc or uri.fragment
                        or uri.query not in ("mode=ro", "mode=rw")):
                    raise AssertionError("URI no autorizada.")
                texto = unquote(uri.path)
                if os.name == "nt" and texto.startswith("/"):
                    texto = texto[1:]
            ruta = Path(texto)
            # Rechazar antes de resolver para no consultar rutas ajenas.
            if not ruta.is_absolute() or not ruta.is_relative_to(raiz):
                raise AssertionError("Ruta SQLite fuera del temporal.")
            ruta = ruta.resolve()
            if not ruta.is_relative_to(raiz):
                raise AssertionError("Ruta SQLite fuera del temporal.")
            origen = raiz / "origen_ficticio.sqlite"
            if ruta != origen and ruta.parent != raiz / "copias":
                raise AssertionError("Ruta SQLite no autorizada.")
            if kwargs.get("uri"):
                if ruta == origen and caso == "error":
                    kwargs["factory"] = FalloCopia
                elif ruta == origen and caso == "interrupcion":
                    kwargs["factory"] = CopiaInterrumpida
                elif ruta == origen and caso == "durante":
                    kwargs["factory"] = CopiaConEscritorConcurrente
                elif ruta != origen and caso == "invalida" and uri.query == "mode=ro":
                    kwargs["factory"] = IntegridadInvalida
            kwargs["timeout"] = 0.05
            conexion = _CONNECT(base, **kwargs)
            recursos.callback(conexion.close)
            conexiones.append((ruta, kwargs.get("uri", False), conexion))
            conexion.set_authorizer(autorizar)
            return conexion

        recursos.enter_context(patch("sqlite3.connect", conectar))
        recursos.enter_context(patch("sqlite3.dbapi2.connect", conectar))
        yield conexiones, permitir_version
    _cerradas(conexiones)


def _cerradas(conexiones):
    comprobar = unittest.TestCase()
    for _, _, conexion in conexiones:
        with comprobar.assertRaises(sqlite3.ProgrammingError):
            conexion.execute("SELECT 1")


def _cargar_servicio(raiz):
    rutas = ModuleType("runtime_paths")
    rutas.DATABASE_PATH = raiz / "predeterminada_no_utilizar.sqlite"
    rutas.BACKUP_DIR = raiz / "predeterminados_no_utilizar"
    spec = importlib.util.spec_from_file_location("_backup_real_3d4c3", _SERVICIO)
    modulo = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, {"runtime_paths": rutas}):
        spec.loader.exec_module(modulo)
    return modulo.BackupService


def _contenido(conexion):
    return (
        conexion.execute("PRAGMA user_version").fetchone(),
        conexion.execute(_ESQUEMA).fetchall(),
        conexion.execute("SELECT * FROM muestra ORDER BY id").fetchall(),
        conexion.execute("SELECT * FROM etiquetas ORDER BY id").fetchall(),
    )


def _escribir(raiz):
    comprobar = unittest.TestCase()
    with _aislamiento(raiz, "escritor") as (conexiones, permitir_version):
        permitir_version[0] = False
        inicio_sqlite = time.perf_counter()
        conexion = sqlite3.connect(raiz / "origen_ficticio.sqlite")
        try:
            conexion.execute("UPDATE muestra SET valor='escritor externo' WHERE id=0")
            conexion.commit()
        except sqlite3.OperationalError as error:
            if error.sqlite_errorcode != sqlite3.SQLITE_BUSY:
                raise
            conexion.rollback()
            estado = "SQLITE_BUSY"
        else:
            comprobar.assertEqual(
                conexion.execute("SELECT valor FROM muestra WHERE id=0").fetchone(),
                ("escritor externo",),
            )
            estado = "confirmado"
        comprobar.assertFalse(conexion.in_transaction)
        duracion_sqlite = time.perf_counter() - inicio_sqlite
    return {
        "estado": estado, "pid": os.getpid(), "cerradas": len(conexiones),
        "sqlite_s": round(duracion_sqlite, 4),
        "modulo_s": round(time.perf_counter() - _INICIO_MODULO, 3),
    }


def _escritor_externo(raiz, esperado):
    comprobar = unittest.TestCase()
    inicio = time.perf_counter()
    try:
        proceso = subprocess.run(
            [sys.executable, "-B", str(_ARCHIVO), "--escritor", str(raiz)],
            capture_output=True, text=True, timeout=_PLAZO_ESCRITOR, check=False,
        )
    except subprocess.TimeoutExpired as error:
        raise AssertionError(
            f"Escritor externo sin respuesta en {_PLAZO_ESCRITOR} s: "
            f"{error.stdout!r} {error.stderr!r}"
        ) from error
    comprobar.assertEqual(proceso.returncode, 0, proceso.stdout + proceso.stderr)
    resultado = json.loads(proceso.stdout)
    resultado["proceso_s"] = round(time.perf_counter() - inicio, 3)
    comprobar.assertEqual(resultado["estado"], esperado)
    comprobar.assertNotEqual(resultado["pid"], os.getpid())
    comprobar.assertEqual(resultado["cerradas"], 1)
    # SQLITE_BUSY debe ser inmediato: un bloqueo real superaria este limite estricto.
    comprobar.assertLess(resultado["sqlite_s"], _PLAZO_SQLITE)
    return resultado


def _experimento(raiz, modo, caso):
    comprobar = unittest.TestCase()
    resultado = {"modo": modo, "caso": caso, "sqlite": sqlite3.sqlite_version}
    with _aislamiento(raiz, caso) as (conexiones, permitir_version):
        servicio = _cargar_servicio(raiz)
        origen = raiz / "origen_ficticio.sqlite"
        copias = raiz / "copias"
        a = sqlite3.connect(origen)
        comprobar.assertEqual(a.execute(f"PRAGMA journal_mode={modo}").fetchone(), (modo.lower(),))
        if modo == "WAL":
            a.execute("PRAGMA wal_autocheckpoint=0")
        a.execute("CREATE TABLE muestra(id INTEGER PRIMARY KEY, valor TEXT NOT NULL)")
        a.execute("CREATE UNIQUE INDEX idx_valor ON muestra(valor)")
        a.execute("CREATE TABLE etiquetas(id INTEGER PRIMARY KEY, nombre TEXT)")
        a.executemany("INSERT INTO muestra VALUES(?, ?)", [(i, f"{i}:" + "x" * 2000) for i in range(80)])
        a.executemany("INSERT INTO etiquetas VALUES(?, ?)", [(1, "uno"), (2, "dos")])
        a.execute("PRAGMA user_version=7")
        a.commit()
        permitir_version[0] = False
        if modo == "WAL":
            comprobar.assertGreater(Path(str(origen) + "-wal").stat().st_size, 0)
            resultado["wal_con_datos"] = True
        inicial = _contenido(a)
        a.execute("BEGIN IMMEDIATE")
        comprobar.assertTrue(a.in_transaction)
        resultado["externo_antes"] = _escritor_externo(raiz, "SQLITE_BUSY")
        comprobar.assertEqual(_contenido(a), inicial)
        inicio_servicio = len(conexiones)

        if caso in ("error", "invalida", "interrupcion"):
            tipo = KeyboardInterrupt if caso == "interrupcion" else OSError
            mensaje = {
                "error": "fallo de copia simulado",
                "invalida": "integridad completa",
                "interrupcion": "interrupcion simulada",
            }[caso]
            with comprobar.assertRaisesRegex(tipo, mensaje):
                servicio.crear_backup_pre_migracion(origen, copias)
            _cerradas(conexiones[inicio_servicio:])
            comprobar.assertEqual(list(copias.iterdir()), [])
            comprobar.assertTrue(a.in_transaction)
            comprobar.assertEqual(_contenido(a), inicial)
            resultado["externo_despues_backup"] = _escritor_externo(raiz, "SQLITE_BUSY")
            a.rollback()
            comprobar.assertFalse(a.in_transaction)
            comprobar.assertEqual(_contenido(a), inicial)
            resultado["fallo_sin_publicacion"] = True
            resultado["rollback_correcto"] = True
        else:
            if caso == "durante":
                _DURANTE.clear()
                _DURANTE["raiz"] = raiz
            publicado = Path(servicio.crear_backup_pre_migracion(origen, copias))
            if caso == "durante":
                comprobar.assertIn("externo_durante_copia", _DURANTE)
                comprobar.assertGreater(_DURANTE["paginas"]["pendientes"], 0)
                resultado["externo_durante_copia"] = _DURANTE["externo_durante_copia"]
                resultado["paginas_durante_copia"] = _DURANTE["paginas"]
            comprobar.assertEqual(publicado.parent, copias)
            comprobar.assertRegex(publicado.name, _PUBLICADO)
            comprobar.assertEqual(list(copias.iterdir()), [publicado])
            servicio_conexiones = conexiones[inicio_servicio:]
            comprobar.assertEqual(len(servicio_conexiones), 3)
            comprobar.assertTrue(all(uri for _, uri, _ in servicio_conexiones))
            _cerradas(servicio_conexiones)
            comprobar.assertTrue(a.in_transaction)
            resultado["externo_despues_backup"] = _escritor_externo(raiz, "SQLITE_BUSY")
            comprobar.assertEqual(_contenido(a), inicial)
            respaldo = sqlite3.connect(publicado.as_uri() + "?mode=ro", uri=True)
            comprobar.assertEqual(respaldo.execute("PRAGMA integrity_check").fetchall(), [("ok",)])
            comprobar.assertEqual(respaldo.execute("PRAGMA journal_mode").fetchone(), ("delete",))
            comprobar.assertEqual(_contenido(respaldo), inicial)
            respaldo.close()
            a.execute("UPDATE muestra SET valor='cambio de A' WHERE id=0")
            if caso in ("commit", "durante"):
                a.commit()
                esperado = "cambio de A"
            else:
                a.rollback()
                esperado = inicial[2][0][1]
            comprobar.assertFalse(a.in_transaction)
            lector = sqlite3.connect(origen.as_uri() + "?mode=ro", uri=True)
            comprobar.assertEqual(lector.execute("SELECT valor FROM muestra WHERE id=0").fetchone(), (esperado,))
            lector.close()
            resultado["backup_verificado"] = True
            resultado["liberacion"] = caso

        resultado["externo_liberado"] = _escritor_externo(raiz, "confirmado")
        comprobar.assertEqual(
            a.execute("SELECT valor FROM muestra WHERE id=0").fetchone(), ("escritor externo",)
        )
        if caso in ("commit", "rollback", "durante"):
            respaldo = sqlite3.connect(publicado.as_uri() + "?mode=ro", uri=True)
            comprobar.assertEqual(_contenido(respaldo), inicial)
            respaldo.close()
            comprobar.assertEqual(list(copias.iterdir()), [publicado])
        comprobar.assertFalse(servicio.DATABASE_PATH.exists())
        comprobar.assertFalse(servicio.BACKUP_DIR.exists())
    resultado["conexiones_cerradas"] = len(conexiones)
    resultado["escritores_terminados"] = sum(1 for clave in resultado if clave.startswith("externo_"))
    return resultado


class BackupRealConcurrenciaTests(unittest.TestCase):
    def experimentar(self, modo, caso):
        with tempfile.TemporaryDirectory(prefix="sqlite_3d4c3_") as temporal:
            proceso = subprocess.run(
                [sys.executable, "-B", str(_ARCHIVO), "--experimento", temporal, modo, caso],
                capture_output=True, text=True, timeout=_PLAZO_ESCENARIO, check=False,
            )
            self.assertEqual(proceso.returncode, 0, proceso.stdout + proceso.stderr)
            resultado = json.loads(proceso.stdout)
            self.assertEqual(resultado["escritores_terminados"], 4 if caso == "durante" else 3)
            print(json.dumps(resultado, sort_keys=True), flush=True)

    def test_delete_escritor_durante_copia(self):
        self.experimentar("DELETE", "durante")

    def test_wal_escritor_durante_copia(self):
        self.experimentar("WAL", "durante")

    def test_delete_commit(self):
        self.experimentar("DELETE", "commit")

    def test_delete_rollback(self):
        self.experimentar("DELETE", "rollback")

    def test_wal_commit(self):
        self.experimentar("WAL", "commit")

    def test_wal_rollback(self):
        self.experimentar("WAL", "rollback")

    def test_delete_error_copia(self):
        self.experimentar("DELETE", "error")

    def test_wal_error_copia(self):
        self.experimentar("WAL", "error")

    def test_delete_integridad_invalida(self):
        self.experimentar("DELETE", "invalida")

    def test_wal_integridad_invalida(self):
        self.experimentar("WAL", "invalida")

    def test_delete_interrupcion(self):
        self.experimentar("DELETE", "interrupcion")

    def test_wal_interrupcion(self):
        self.experimentar("WAL", "interrupcion")

    def test_guardias_antes_de_importar_servicio(self):
        with tempfile.TemporaryDirectory(prefix="sqlite_3d4c3_") as temporal:
            raiz = Path(temporal).resolve()
            with _aislamiento(raiz, "guardia") as (conexiones, permitir_version):
                for conectar in (sqlite3.connect, sqlite3.dbapi2.connect):
                    for base, kwargs in (
                        (raiz.parent / "ajena_ficticia.sqlite", {}),
                        (raiz.parent.as_uri() + "/ajena_ficticia.sqlite?mode=ro", {"uri": True}),
                        (raiz / ".." / "ajena_ficticia.sqlite", {}),
                        (":memory:", {}),
                    ):
                        with self.assertRaises(AssertionError):
                            conectar(base, **kwargs)
                self.assertEqual(conexiones, [])
                conexion = sqlite3.connect(raiz / "origen_ficticio.sqlite")
                permitir_version[0] = False
                with self.assertRaises(sqlite3.DatabaseError):
                    conexion.execute("ATTACH ':memory:' AS ajena")
                with self.assertRaises(sqlite3.DatabaseError):
                    conexion.execute("PRAGMA user_version=99")
                _cargar_servicio(raiz)
                self.assertEqual(len(conexiones), 1)

    def test_supervisor_termina_proceso_bloqueado(self):
        proceso = subprocess.Popen(
            [sys.executable, "-B", "-c", "import time; time.sleep(30)"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        try:
            with self.assertRaises(subprocess.TimeoutExpired):
                proceso.communicate(timeout=0.2)
        finally:
            proceso.kill()
            proceso.communicate(timeout=_PLAZO_ESCRITOR)
        self.assertIsNotNone(proceso.poll())


if __name__ == "__main__":
    if _MODO_HIJO:
        escritor = sys.argv[1] == "--escritor"
        try:
            raiz = Path(sys.argv[2]).resolve(strict=True)
            resultado = _escribir(raiz) if escritor else _experimento(raiz, sys.argv[3], sys.argv[4])
            print(json.dumps(resultado), flush=True)
        finally:
            faulthandler.cancel_dump_traceback_later()
    else:
        unittest.main()
