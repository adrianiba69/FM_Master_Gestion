import importlib.util
import json
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from types import ModuleType
from unittest.mock import patch


def _cargar_servicio_aislado(raiz):
    """Evita importar runtime_paths y preparar directorios o bases habituales."""
    ruta = Path(__file__).resolve().parents[1] / "services" / "backup_service.py"
    spec = importlib.util.spec_from_file_location("_backup_pre_migracion_test", ruta)
    modulo = importlib.util.module_from_spec(spec)
    rutas = ModuleType("runtime_paths")
    rutas.DATABASE_PATH = raiz / "predeterminada_no_utilizar.db"
    rutas.BACKUP_DIR = raiz / "predeterminados_no_utilizar"
    with patch.dict(sys.modules, {"runtime_paths": rutas}):
        spec.loader.exec_module(modulo)
    return modulo


_CODIGO_COPIA_AISLADA = """
import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

sys.dont_write_bytecode = True
archivo_servicio, origen, destino = sys.argv[1:]
rutas = ModuleType('runtime_paths')
rutas.DATABASE_PATH = Path(origen).parent / 'predeterminada_no_utilizar.db'
rutas.BACKUP_DIR = Path(origen).parent / 'predeterminados_no_utilizar'
sys.modules['runtime_paths'] = rutas
spec = importlib.util.spec_from_file_location('_backup_worker', archivo_servicio)
modulo = importlib.util.module_from_spec(spec)
spec.loader.exec_module(modulo)
try:
    ruta = modulo.BackupService.crear_backup_pre_migracion(origen, destino)
except Exception as error:
    print(json.dumps({'error': str(error)}))
else:
    print(json.dumps({'ruta': ruta}))
"""


class BackupPreMigracionTest(unittest.TestCase):
    def setUp(self):
        self.temporal = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporal.cleanup)
        self.raiz = Path(self.temporal.name)
        self.origen = self.raiz / "origen_prueba.db"
        self.backups = self.raiz / "copias"
        self.modulo = _cargar_servicio_aislado(self.raiz)
        self.servicio = self.modulo.BackupService
        with closing(sqlite3.connect(self.origen)) as conexion:
            conexion.executescript(
                "CREATE TABLE clientes_prueba(id INTEGER PRIMARY KEY, nombre TEXT);"
                "CREATE UNIQUE INDEX idx_nombre_prueba ON clientes_prueba(nombre);"
                "CREATE TABLE comprobantes_prueba(id INTEGER PRIMARY KEY, total REAL);"
                "INSERT INTO clientes_prueba VALUES(1, 'Cliente ficticio');"
                "INSERT INTO comprobantes_prueba VALUES(1, 1210);"
                "PRAGMA user_version=7;"
            )
            conexion.commit()

    def _copiar(self, origen=None, destino=None):
        archivo_servicio = Path(__file__).resolve().parents[1] / "services" / "backup_service.py"
        proceso = subprocess.run(
            [sys.executable, "-B", "-c", _CODIGO_COPIA_AISLADA, str(archivo_servicio),
             str(origen if origen is not None else self.origen),
             str(destino if destino is not None else self.backups)],
            capture_output=True, text=True, timeout=20, check=True,
        )
        respuesta = json.loads(proceso.stdout)
        if "error" in respuesta:
            raise OSError(respuesta["error"])
        return Path(respuesta["ruta"])

    def _contenido(self, ruta):
        with closing(sqlite3.connect(ruta.resolve().as_uri() + "?mode=ro", uri=True)) as conexion:
            return (
                conexion.execute("PRAGMA user_version").fetchone(),
                conexion.execute(
                    "SELECT type, name, tbl_name, sql FROM sqlite_master ORDER BY type, name"
                ).fetchall(),
                conexion.execute("SELECT * FROM clientes_prueba ORDER BY id").fetchall(),
                conexion.execute("SELECT * FROM comprobantes_prueba ORDER BY id").fetchall(),
            )

    def _preservar_copia_anterior(self):
        anterior = self._copiar()
        return anterior, anterior.read_bytes()

    def test_base_valida_genera_copia_integra_y_devuelve_ruta(self):
        copia = self._copiar()

        self.assertTrue(copia.is_absolute())
        self.assertEqual(copia.parent, self.backups)
        self.assertTrue(copia.name.startswith("pre_migracion_"))
        self.assertGreater(copia.stat().st_size, 0)
        with closing(sqlite3.connect(copia.as_uri() + "?mode=ro", uri=True)) as conexion:
            self.assertEqual(conexion.execute("PRAGMA quick_check").fetchall(), [("ok",)])
        self.assertFalse(self.servicio.DATABASE_PATH.exists())
        self.assertFalse(self.servicio.BACKUP_DIR.exists())

    def test_copia_conserva_tablas_indices_registros_y_user_version(self):
        esperado = self._contenido(self.origen)

        copia = self._copiar()

        self.assertEqual(self._contenido(copia), esperado)
        self.assertEqual(esperado[0], (7,))
        self.assertIn("idx_nombre_prueba", [fila[1] for fila in esperado[1]])

    def test_dos_copias_consecutivas_no_sobrescriben_la_anterior(self):
        anterior, contenido_anterior = self._preservar_copia_anterior()

        nueva = self._copiar()

        self.assertNotEqual(nueva, anterior)
        self.assertTrue(nueva.is_file())
        self.assertEqual(anterior.read_bytes(), contenido_anterior)
        self.assertEqual(set(self.backups.iterdir()), {anterior, nueva})

    def test_origen_inexistente_falla_sin_crear_base(self):
        inexistente = self.raiz / "inexistente.db"

        with self.assertRaisesRegex(OSError, "backup pre-migracion verificado"):
            self._copiar(origen=inexistente)

        self.assertFalse(inexistente.exists())
        self.assertFalse(self.backups.exists())

    def test_archivo_no_sqlite_o_corrupto_es_rechazado(self):
        for contenido in (b"No es SQLite", b"SQLite format 3\x00" + b"\x00" * 100):
            with self.subTest(contenido=contenido[:16]):
                corrupta = self.raiz / "corrupta.db"
                corrupta.write_bytes(contenido)

                with self.assertRaises(OSError):
                    self._copiar(origen=corrupta)

                self.assertEqual(corrupta.read_bytes(), contenido)
                self.assertFalse(self.backups.exists())

    def test_destino_igual_al_origen_no_sobrescribe_la_base(self):
        contenido_antes = self.origen.read_bytes()

        with self.assertRaisesRegex(OSError, "directorio de backups no puede ser la base"):
            self._copiar(destino=self.origen)

        self.assertEqual(self.origen.read_bytes(), contenido_antes)

    def test_fallo_de_copia_limpia_solo_su_archivo_y_cierra_conexiones(self):
        anterior, contenido_anterior = self._preservar_copia_anterior()
        conectar_real = sqlite3.connect
        conexiones = []

        class ConexionCopiaFallida(sqlite3.Connection):
            def backup(self, respaldo, **kwargs):
                raise sqlite3.OperationalError("fallo de copia simulado")

        def conectar(ruta, **kwargs):
            if ruta == self.origen.as_uri() + "?mode=ro":
                kwargs["factory"] = ConexionCopiaFallida
            conexion = conectar_real(ruta, **kwargs)
            conexiones.append(conexion)
            return conexion

        with patch.object(self.modulo.sqlite3, "connect", side_effect=conectar):
            with self.assertRaisesRegex(OSError, "fallo de copia simulado"):
                self.servicio.crear_backup_pre_migracion(self.origen, self.backups)

        self.assertEqual(set(self.backups.iterdir()), {anterior})
        self.assertEqual(anterior.read_bytes(), contenido_anterior)
        self.assertEqual(len(conexiones), 2)
        for conexion in conexiones:
            with self.assertRaises(sqlite3.ProgrammingError):
                conexion.execute("SELECT 1")

    def test_fallo_de_verificacion_no_elimina_copias_anteriores(self):
        anterior, contenido_anterior = self._preservar_copia_anterior()
        conectar_real = sqlite3.connect
        conexiones = []

        class ConexionVerificacionFallida(sqlite3.Connection):
            def execute(self, consulta, *args, **kwargs):
                if consulta == "PRAGMA quick_check":
                    raise sqlite3.DatabaseError("verificacion simulada fallida")
                return super().execute(consulta, *args, **kwargs)

        def conectar(ruta, **kwargs):
            if ruta.endswith("?mode=ro") and ruta != self.origen.as_uri() + "?mode=ro":
                kwargs["factory"] = ConexionVerificacionFallida
            conexion = conectar_real(ruta, **kwargs)
            conexiones.append(conexion)
            return conexion

        with patch.object(self.modulo.sqlite3, "connect", side_effect=conectar):
            with self.assertRaisesRegex(OSError, "verificacion simulada fallida"):
                self.servicio.crear_backup_pre_migracion(self.origen, self.backups)

        self.assertEqual(set(self.backups.iterdir()), {anterior})
        self.assertEqual(anterior.read_bytes(), contenido_anterior)
        self.assertEqual(len(conexiones), 3)
        for conexion in conexiones:
            with self.assertRaises(sqlite3.ProgrammingError):
                conexion.execute("SELECT 1")

    def test_backup_diario_independiente_conserva_comportamiento(self):
        previo, contenido_previo = self._preservar_copia_anterior()
        with (
            patch.object(self.servicio, "DATABASE_PATH", self.origen),
            patch.object(self.servicio, "BACKUP_DIR", self.backups),
        ):
            self.assertFalse(self.servicio.existe_backup_del_dia())
            diario = Path(self.servicio.crear_backup_automatico())
            self.assertRegex(diario.name, r"^backup_\d{8}_\d{6}\.db$")
            self.assertEqual(self.servicio.listar_backups(), [diario])
            self.assertEqual(self._contenido(diario), self._contenido(self.origen))
            contenido_diario = diario.read_bytes()
            self.assertIsNone(self.servicio.crear_backup_automatico())
            self.assertEqual(diario.read_bytes(), contenido_diario)
        self.assertEqual(previo.read_bytes(), contenido_previo)

    def test_wal_incluye_registros_confirmados_sin_checkpoint(self):
        with closing(sqlite3.connect(self.origen)) as escritor:
            self.assertEqual(escritor.execute("PRAGMA journal_mode=WAL").fetchone(), ("wal",))
            escritor.execute("PRAGMA wal_autocheckpoint=0")
            escritor.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            escritor.execute("INSERT INTO clientes_prueba VALUES(2, 'Registro en WAL')")
            escritor.commit()
            self.assertGreater(Path(str(self.origen) + "-wal").stat().st_size, 0)
            principal_sin_wal = self.raiz / "principal_sin_wal.db"
            principal_sin_wal.write_bytes(self.origen.read_bytes())
            self.assertEqual(len(self._contenido(principal_sin_wal)[2]), 1)

            copia = self._copiar()

            self.assertEqual(
                self._contenido(copia)[2], [(1, "Cliente ficticio"), (2, "Registro en WAL")]
            )

    def test_copia_permite_recuperar_registros_en_base_independiente(self):
        copia = self._copiar()
        restaurada = self.raiz / "restauracion_prueba.db"
        with (
            closing(sqlite3.connect(copia.as_uri() + "?mode=ro", uri=True)) as respaldo,
            closing(sqlite3.connect(restaurada)) as destino,
        ):
            respaldo.backup(destino)

        self.assertEqual(self._contenido(restaurada), self._contenido(self.origen))
        self.assertTrue(copia.is_file())

    def test_copia_no_modifica_datos_esquema_ni_version_del_origen(self):
        contenido_antes = self._contenido(self.origen)
        bytes_antes = self.origen.read_bytes()

        self._copiar()

        self.assertEqual(self._contenido(self.origen), contenido_antes)
        self.assertEqual(self.origen.read_bytes(), bytes_antes)


if __name__ == "__main__":
    unittest.main()