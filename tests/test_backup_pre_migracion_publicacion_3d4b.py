"""3D.4B: copia temporal, verificacion completa y publicacion sin sobrescritura.

Solo bases SQLite ficticias dentro de un directorio temporal propio; runtime_paths
se sustituye antes de importar el servicio y toda conexion fuera de ese
directorio se rechaza.
"""

import importlib.util
import os
import re
import sqlite3
import sys
import tempfile
import unittest
from contextlib import ExitStack, closing
from datetime import datetime
from pathlib import Path
from types import ModuleType
from unittest.mock import Mock, patch
from urllib.parse import unquote, urlparse


_SERVICIO = Path(__file__).resolve().parents[1] / "services" / "backup_service.py"
_CONNECT = sqlite3.connect
_PUBLICADO = re.compile(r"^pre_migracion_\d{8}_\d{6}_[0-9a-f]{8}\.db$")
_TEMPORAL = re.compile(r"^\.pre_migracion_incompleto_.*\.tmp$")
_TABLA_RARA = 'tabla "rara"'


def _cargar_servicio(raiz):
    rutas = ModuleType("runtime_paths")
    rutas.DATABASE_PATH = raiz / "predeterminada_no_utilizar.db"
    rutas.BACKUP_DIR = raiz / "predeterminados_no_utilizar"
    spec = importlib.util.spec_from_file_location("_backup_publicacion_3d4b", _SERVICIO)
    modulo = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, {"runtime_paths": rutas}):
        spec.loader.exec_module(modulo)
    return modulo


def _con_reemplazos(reemplazos):
    """Conexion cuyo execute sustituye consultas exactas o lanza un error inyectado."""

    class Conexion(sqlite3.Connection):
        def execute(self, sql, *args, **kwargs):
            for clave, reemplazo in reemplazos.items():
                if sql.startswith(clave):
                    if isinstance(reemplazo, BaseException):
                        raise reemplazo
                    return super().execute(reemplazo)
            return super().execute(sql, *args, **kwargs)

    return Conexion


class PublicacionBackupPreMigracionTests(unittest.TestCase):
    def setUp(self):
        temporal = tempfile.TemporaryDirectory()
        self.addCleanup(temporal.cleanup)
        self.raiz = Path(temporal.name).resolve()
        self.origen = self.raiz / "origen_ficticio.db"
        self.backups = self.raiz / "copias"
        self.conexiones = []
        self.rutas_abiertas = []
        self.fabricas = {}
        pila = ExitStack()
        self.addCleanup(pila.close)
        pila.enter_context(patch("sqlite3.connect", self._conectar_vigilado))
        self.modulo = _cargar_servicio(self.raiz)
        self.servicio = self.modulo.BackupService

        with closing(sqlite3.connect(self.origen)) as conexion:
            conexion.executescript(
                "CREATE TABLE clientes(id INTEGER PRIMARY KEY AUTOINCREMENT, nombre TEXT);"
                "CREATE UNIQUE INDEX idx_clientes_nombre ON clientes(nombre);"
                f'CREATE TABLE "{_TABLA_RARA.replace(chr(34), chr(34) * 2)}"(valor TEXT);'
                "INSERT INTO clientes(nombre) VALUES('Cliente ficticio A'), ('Cliente ficticio B');"
                f'INSERT INTO "{_TABLA_RARA.replace(chr(34), chr(34) * 2)}" VALUES(\'x\');'
                "PRAGMA user_version=7;"
            )
            conexion.commit()
        self.backups.mkdir()
        self.previo = self.backups / "pre_migracion_20260101_000000_deadbeef.db"
        self.previo.write_bytes(b"backup anterior ficticio; no debe tocarse")
        self.conexiones.clear()
        self.rutas_abiertas.clear()

    # -- guardia de aislamiento -------------------------------------------------
    def _conectar_vigilado(self, base, *args, **kwargs):
        texto = str(base)
        if kwargs.get("uri"):
            ruta = Path(unquote(urlparse(texto).path).lstrip("/"))
        else:
            ruta = Path(texto)
        ruta = ruta.resolve()
        if "fm_master" in ruta.name.lower() or self.raiz not in ruta.parents:
            raise AssertionError(f"Conexion fuera del directorio temporal prohibida: {ruta}")
        rol = "fixture"
        if kwargs.get("uri"):
            if texto == self.origen.as_uri() + "?mode=ro":
                rol = "origen"
            elif texto.endswith("?mode=rw"):
                rol = "respaldo"
            elif texto.endswith("?mode=ro"):
                rol = "verificacion"
        if rol in self.fabricas:
            kwargs["factory"] = self.fabricas[rol]
        conexion = _CONNECT(base, *args, **kwargs)
        self.conexiones.append((rol, conexion))
        self.rutas_abiertas.append(ruta)
        return conexion

    # -- utilidades ---------------------------------------------------------------
    def _respaldar(self):
        return Path(self.servicio.crear_backup_pre_migracion(self.origen, self.backups))

    def _contenido(self, ruta):
        with closing(_CONNECT(ruta.as_uri() + "?mode=ro", uri=True)) as conexion:
            return (
                conexion.execute("PRAGMA user_version").fetchone(),
                conexion.execute("SELECT type, name, tbl_name, sql FROM sqlite_master ORDER BY type, name").fetchall(),
                conexion.execute("SELECT * FROM clientes ORDER BY id").fetchall(),
                conexion.execute(f'SELECT * FROM "{_TABLA_RARA.replace(chr(34), chr(34) * 2)}"').fetchall(),
            )

    def _sin_publicacion_nueva(self):
        self.assertEqual(sorted(p.name for p in self.backups.iterdir()), [self.previo.name])
        self.assertEqual(self.previo.read_bytes(), b"backup anterior ficticio; no debe tocarse")

    def _conexiones_cerradas(self):
        for _, conexion in self.conexiones:
            with self.assertRaises(sqlite3.ProgrammingError):
                conexion.execute("SELECT 1")

    # -- exito ----------------------------------------------------------------------
    def test_exito_publica_nombre_definitivo_verificado_sin_temporales(self):
        esperado = self._contenido(self.origen)
        bytes_origen = self.origen.read_bytes()

        copia = self._respaldar()

        self.assertEqual(copia.parent, self.backups)
        self.assertRegex(copia.name, _PUBLICADO)
        self.assertEqual({p.name for p in self.backups.iterdir()}, {self.previo.name, copia.name})
        self.assertEqual(self.previo.read_bytes(), b"backup anterior ficticio; no debe tocarse")
        self.assertEqual(self._contenido(copia), esperado)
        with closing(_CONNECT(copia.as_uri() + "?mode=ro", uri=True)) as conexion:
            self.assertEqual(conexion.execute("PRAGMA integrity_check").fetchall(), [("ok",)])
        self.assertEqual(copia.read_bytes()[18:20], b"\x01\x01")
        self.assertEqual(self.origen.read_bytes(), bytes_origen)
        for sufijo in ("-journal", "-wal", "-shm"):
            self.assertFalse(Path(str(copia) + sufijo).exists())
            self.assertFalse(Path(str(self.origen) + sufijo).exists())
        self.assertEqual([rol for rol, _ in self.conexiones], ["origen", "respaldo", "verificacion"])
        self._conexiones_cerradas()

    def test_copias_consecutivas_conviven_sin_reemplazo(self):
        primera = self._respaldar()
        bytes_primera = primera.read_bytes()

        segunda = self._respaldar()

        self.assertNotEqual(primera, segunda)
        self.assertEqual(primera.read_bytes(), bytes_primera)
        self.assertEqual(
            {p.name for p in self.backups.iterdir()}, {self.previo.name, primera.name, segunda.name}
        )

    def test_wal_publica_registros_confirmados_como_archivo_autonomo(self):
        with closing(_CONNECT(self.origen)) as escritor:
            self.assertEqual(escritor.execute("PRAGMA journal_mode=WAL").fetchone(), ("wal",))
            escritor.execute("PRAGMA wal_autocheckpoint=0")
            escritor.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            escritor.execute("INSERT INTO clientes(nombre) VALUES('Solo en WAL')")
            escritor.commit()
            self.assertGreater(Path(str(self.origen) + "-wal").stat().st_size, 0)

            copia = self._respaldar()

            nombres = [fila[1] for fila in self._contenido(copia)[2]]
            self.assertIn("Solo en WAL", nombres)
            self.assertEqual(copia.read_bytes()[18:20], b"\x01\x01")
            for sufijo in ("-journal", "-wal", "-shm"):
                self.assertFalse(Path(str(copia) + sufijo).exists())

    # -- nombre no publicable durante la copia -------------------------------------
    def test_durante_la_copia_solo_existe_un_nombre_no_publicable(self):
        observados = []
        prueba = self

        class OrigenObservado(sqlite3.Connection):
            def backup(self, destino, **kwargs):
                observados.extend(p.name for p in prueba.backups.iterdir() if p != prueba.previo)
                return super().backup(destino, **kwargs)

        self.fabricas["origen"] = OrigenObservado

        copia = self._respaldar()

        self.assertEqual(len(observados), 1)
        self.assertRegex(observados[0], _TEMPORAL)
        self.assertNotRegex(observados[0], _PUBLICADO)
        self.assertNotEqual(observados[0], copia.name)

    # -- verificacion completa --------------------------------------------------------
    def test_cada_verificacion_fallida_impide_publicar(self):
        casos = {
            "PRAGMA quick_check": ("SELECT 'fallo simulado'", "verificacion del backup"),
            "PRAGMA integrity_check": ("SELECT 'row 1 missing from index'", "integridad completa"),
            "SELECT type, name, tbl_name, sql FROM sqlite_master": ("SELECT 1, 2, 3, 4", "esquema del backup"),
            "PRAGMA user_version": ("SELECT 99", "version del backup"),
            "SELECT COUNT(*) FROM main.\"clientes\"": ("SELECT 999", "cantidad de registros"),
        }
        for consulta, (reemplazo, mensaje) in casos.items():
            with self.subTest(consulta=consulta):
                self.conexiones.clear()
                self.fabricas = {"verificacion": _con_reemplazos({consulta: reemplazo})}

                with self.assertRaisesRegex(OSError, mensaje):
                    self._respaldar()

                self._sin_publicacion_nueva()
                self.assertEqual([rol for rol, _ in self.conexiones], ["origen", "respaldo", "verificacion"])
                self._conexiones_cerradas()

    def test_normalizacion_journal_fallida_impide_publicar(self):
        self.fabricas["respaldo"] = _con_reemplazos({"PRAGMA journal_mode=DELETE": "SELECT 'wal'"})

        with self.assertRaisesRegex(OSError, "modo de journal"):
            self._respaldar()

        self._sin_publicacion_nueva()
        self._conexiones_cerradas()

    # -- interrupciones ---------------------------------------------------------------
    def test_interrupcion_durante_copia_se_relanza_y_limpia(self):
        class OrigenInterrumpido(sqlite3.Connection):
            def backup(self, destino, **kwargs):
                raise KeyboardInterrupt

        self.fabricas["origen"] = OrigenInterrumpido

        with self.assertRaises(KeyboardInterrupt):
            self._respaldar()

        self._sin_publicacion_nueva()
        self._conexiones_cerradas()

    def test_interrupcion_durante_verificacion_se_relanza_y_limpia(self):
        self.fabricas["verificacion"] = _con_reemplazos({"PRAGMA integrity_check": KeyboardInterrupt()})

        with self.assertRaises(KeyboardInterrupt):
            self._respaldar()

        self._sin_publicacion_nueva()
        self._conexiones_cerradas()

    def test_interrupcion_durante_publicacion_no_deja_archivos(self):
        with patch.object(self.modulo.os, "rename", side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                self._respaldar()

        self._sin_publicacion_nueva()

    # -- publicacion sin sobrescritura ----------------------------------------------
    def test_publicacion_fallida_informa_error_y_limpia(self):
        with patch.object(self.modulo.os, "rename", side_effect=PermissionError("acceso denegado simulado")):
            with self.assertRaisesRegex(OSError, "acceso denegado simulado"):
                self._respaldar()

        self._sin_publicacion_nueva()

    def test_colision_de_nombre_no_reemplaza_backup_existente(self):
        reloj = Mock(wraps=datetime)
        reloj.now.return_value = datetime(2026, 1, 1, 0, 0, 0)
        with (
            patch.object(self.modulo, "datetime", reloj),
            patch.object(self.modulo.secrets, "token_hex", side_effect=["deadbeef", "cafebabe"]),
        ):
            copia = self._respaldar()

        self.assertEqual(copia.name, "pre_migracion_20260101_000000_cafebabe.db")
        self.assertEqual(self.previo.read_bytes(), b"backup anterior ficticio; no debe tocarse")
        self.assertEqual({p.name for p in self.backups.iterdir()}, {self.previo.name, copia.name})

    def test_sin_nombre_libre_falla_cerrado_sin_reemplazar(self):
        reloj = Mock(wraps=datetime)
        reloj.now.return_value = datetime(2026, 1, 1, 0, 0, 0)
        with (
            patch.object(self.modulo, "datetime", reloj),
            patch.object(self.modulo.secrets, "token_hex", return_value="deadbeef"),
            patch.object(self.servicio, "INTENTOS_PUBLICACION_PRE_MIGRACION", 3),
        ):
            with self.assertRaisesRegex(OSError, "nombre libre"):
                self._respaldar()

        self._sin_publicacion_nueva()

    # -- limpieza fallida --------------------------------------------------------------
    def test_limpieza_fallida_tras_interrupcion_queda_como_nota_y_sin_nombre_publicable(self):
        class OrigenInterrumpido(sqlite3.Connection):
            def backup(self, destino, **kwargs):
                raise KeyboardInterrupt

        self.fabricas["origen"] = OrigenInterrumpido
        with patch.object(self.modulo.Path, "unlink", side_effect=PermissionError("bloqueado simulado")):
            with self.assertRaises(KeyboardInterrupt) as contexto:
                self._respaldar()

        self.assertTrue(any("bloqueado simulado" in nota for nota in contexto.exception.__notes__))
        restos = [p.name for p in self.backups.iterdir() if p != self.previo]
        self.assertEqual(len(restos), 1)
        self.assertRegex(restos[0], _TEMPORAL)
        os.remove(self.backups / restos[0])
        self._sin_publicacion_nueva()

    def test_limpieza_fallida_tras_error_se_informa_junto_al_original(self):
        self.fabricas["verificacion"] = _con_reemplazos({"PRAGMA integrity_check": "SELECT 'dano simulado'"})
        with patch.object(self.modulo.Path, "unlink", side_effect=PermissionError("bloqueado simulado")):
            with self.assertRaisesRegex(OSError, "integridad completa.*no se pudieron eliminar.*bloqueado simulado"):
                self._respaldar()

        restos = [p.name for p in self.backups.iterdir() if p != self.previo]
        self.assertEqual(len(restos), 1)
        self.assertRegex(restos[0], _TEMPORAL)
        os.remove(self.backups / restos[0])
        self._sin_publicacion_nueva()

    # -- aislamiento ------------------------------------------------------------------
    def test_guardia_rechaza_conexiones_fuera_del_directorio_temporal(self):
        for base, kwargs in (
            (str(self.raiz / "database" / "fm_master.db"), {}),
            (str(self.raiz / "fm_master.db"), {}),
            (str(Path(tempfile.gettempdir()) / "ajena_3d4b.db"), {}),
        ):
            with self.subTest(base=base):
                with self.assertRaises(AssertionError):
                    sqlite3.connect(base, **kwargs)
        self.assertEqual(self.rutas_abiertas, [])

    def test_todas_las_conexiones_quedan_dentro_del_directorio_temporal(self):
        self._respaldar()

        self.assertTrue(self.rutas_abiertas)
        for ruta in self.rutas_abiertas:
            self.assertIn(self.raiz, ruta.parents)
            self.assertNotIn("fm_master", ruta.name.lower())
        self.assertFalse(self.servicio.DATABASE_PATH.exists())
        self.assertFalse(self.servicio.BACKUP_DIR.exists())


if __name__ == "__main__":
    unittest.main()
