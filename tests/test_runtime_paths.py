import ast
import json
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import Mock, patch

import runtime_paths


_IMPORTAR_AISLADO = """
import importlib.util
import json
import sys
from pathlib import Path
from unittest.mock import patch

raiz = Path(sys.argv[1])
empaquetada = sys.argv[2] == "ejecutable"
preparar = sys.argv[3] == "preparar"
sys.frozen = empaquetada
sys.executable = str(raiz / "aplicacion" / "FM_Master_Gestion.exe")
sys._MEIPASS = str(raiz / "bundle")
spec = importlib.util.spec_from_file_location(
    "_runtime_paths_aislado", raiz / "codigo" / "runtime_paths.py"
)
modulo = importlib.util.module_from_spec(spec)
if preparar:
    # Aisla la funcion explicita de cualquier efecto que pudiera tener la importacion.
    with patch("pathlib.Path.mkdir"), patch("shutil.copy2"):
        spec.loader.exec_module(modulo)
    modulo.preparar_directorios()
    modulo.preparar_directorios()
else:
    spec.loader.exec_module(modulo)
print(json.dumps({
    "app_dir": str(modulo.APP_DIR),
    "bundle_dir": str(modulo.BUNDLE_DIR),
    "database_path": str(modulo.DATABASE_PATH),
}))
"""

_DIRECTORIOS_ESPERADOS = {
    "database", "backup", "pdf", "pdf/resumenes", "manuales", "exports", "cierres",
}


class RuntimePathsAisladoTest(unittest.TestCase):
    def setUp(self):
        temporal = tempfile.TemporaryDirectory()
        self.addCleanup(temporal.cleanup)
        self.raiz = Path(temporal.name)
        self.codigo = self.raiz / "codigo"
        self.aplicacion = self.raiz / "aplicacion"
        self.bundle = self.raiz / "bundle"
        self.trabajo = self.raiz / "trabajo"
        for carpeta in (self.codigo, self.aplicacion, self.bundle, self.trabajo):
            carpeta.mkdir()
        origen = Path(__file__).resolve().parents[1] / "runtime_paths.py"
        shutil.copyfile(origen, self.codigo / "runtime_paths.py")

    def _crear_archivo_ficticio(self, ruta, contenido):
        ruta.parent.mkdir(parents=True, exist_ok=True)
        ruta.write_bytes(contenido)

    def _instantanea(self):
        return {
            ruta.relative_to(self.raiz).as_posix(): (
                ruta.read_bytes() if ruta.is_file() else None
            )
            for ruta in self.raiz.rglob("*")
        }

    def _ejecutar(self, *, empaquetada=False, preparar=False):
        proceso = subprocess.run(
            [
                sys.executable, "-I", "-B", "-c", _IMPORTAR_AISLADO,
                str(self.raiz),
                "ejecutable" if empaquetada else "desarrollo",
                "preparar" if preparar else "importar",
            ],
            cwd=self.trabajo,
            capture_output=True,
            text=True,
            timeout=20,
            check=True,
        )
        self.assertEqual(proceso.stderr, "")
        return json.loads(proceso.stdout)

    def _comprobar_importacion_inocua(self, *, empaquetada=False):
        antes = self._instantanea()

        self._ejecutar(empaquetada=empaquetada)

        self.assertEqual(
            self._instantanea(), antes,
            "Importar runtime_paths no debe crear directorios ni crear/copiar bases.",
        )

    def test_importar_en_desarrollo_no_modifica_archivos_ni_directorios(self):
        self._comprobar_importacion_inocua()

    def test_importar_ejecutable_sin_base_empaquetada_no_modifica_el_disco(self):
        self._comprobar_importacion_inocua(empaquetada=True)

    def test_importar_no_copia_base_empaquetada_sin_autorizacion(self):
        self._crear_archivo_ficticio(
            self.bundle / "database" / "fm_master.db", b"BASE EMPAQUETADA FICTICIA"
        )

        self._comprobar_importacion_inocua(empaquetada=True)

    def test_base_ausente_con_rastros_no_se_reemplaza_al_importar(self):
        self._crear_archivo_ficticio(
            self.aplicacion / "backup" / "backup_20261001_120000.db",
            b"BACKUP FICTICIO, NO ES SQLITE",
        )
        self._crear_archivo_ficticio(
            self.aplicacion / "database" / "fm_master.db-wal", b"WAL FICTICIO"
        )
        self._crear_archivo_ficticio(
            self.bundle / "database" / "fm_master.db", b"BASE EMPAQUETADA FICTICIA"
        )

        self._comprobar_importacion_inocua(empaquetada=True)

    def test_importar_con_base_existente_preserva_archivos_y_contenido(self):
        for carpeta in _DIRECTORIOS_ESPERADOS:
            (self.aplicacion / Path(carpeta)).mkdir(parents=True, exist_ok=True)
        self._crear_archivo_ficticio(
            self.aplicacion / "database" / "fm_master.db", b"BASE ORIGINAL FICTICIA"
        )
        self._crear_archivo_ficticio(
            self.bundle / "database" / "fm_master.db", b"OTRA BASE FICTICIA"
        )

        self._comprobar_importacion_inocua(empaquetada=True)

    def test_preparacion_explicita_crea_solo_directorios_y_es_idempotente(self):
        for empaquetada in (False, True):
            with self.subTest(empaquetada=empaquetada):
                destino = self.aplicacion if empaquetada else self.codigo
                antes = self._instantanea()
                nuevas_rutas = {
                    (destino / Path(carpeta)).relative_to(self.raiz).as_posix(): None
                    for carpeta in _DIRECTORIOS_ESPERADOS
                }

                self._ejecutar(empaquetada=empaquetada, preparar=True)

                self.assertEqual(self._instantanea(), {**antes, **nuevas_rutas})

    def test_preparacion_explicita_nunca_copia_la_base_empaquetada(self):
        self._crear_archivo_ficticio(
            self.bundle / "database" / "fm_master.db", b"BASE EMPAQUETADA FICTICIA"
        )
        antes = self._instantanea()
        nuevas_rutas = {
            (self.aplicacion / Path(carpeta)).relative_to(self.raiz).as_posix(): None
            for carpeta in _DIRECTORIOS_ESPERADOS
        }

        self._ejecutar(empaquetada=True, preparar=True)

        self.assertEqual(
            self._instantanea(), {**antes, **nuevas_rutas},
            "La preparacion explicita debe limitarse a crear directorios.",
        )

    def test_rutas_de_desarrollo_y_ejecutable_no_dependen_del_cwd(self):
        for empaquetada in (False, True):
            with self.subTest(empaquetada=empaquetada):
                esperado = self.aplicacion if empaquetada else self.codigo

                rutas = self._ejecutar(empaquetada=empaquetada)

                self.assertEqual(Path(rutas["app_dir"]), esperado)
                self.assertEqual(
                    Path(rutas["bundle_dir"]),
                    self.bundle if empaquetada else self.codigo,
                )
                self.assertEqual(
                    Path(rutas["database_path"]), esperado / "database" / "fm_master.db"
                )


def _instantanea_de(raiz):
    return {
        ruta.relative_to(raiz).as_posix(): (ruta.read_bytes() if ruta.is_file() else None)
        for ruta in raiz.rglob("*")
    }


class ClasificadorArchivoBaseTest(unittest.TestCase):
    def setUp(self):
        temporal = tempfile.TemporaryDirectory()
        self.addCleanup(temporal.cleanup)
        self.raiz = Path(temporal.name)
        self.database_dir = self.raiz / "database"
        self.backup_dir = self.raiz / "backup"
        self.pdf_dir = self.raiz / "pdf"
        self.base = self.database_dir / "fm_master.db"

    def _inspeccionar(self):
        conexiones = []
        antes = _instantanea_de(self.raiz)
        with patch("sqlite3.connect", side_effect=lambda *a, **k: conexiones.append(a)):
            estado = runtime_paths.inspeccionar_archivo_base(
                database_path=self.base,
                directorios_escritura=(self.database_dir, self.backup_dir, self.pdf_dir),
            )
        self.assertEqual(conexiones, [], "La inspeccion no debe abrir SQLite.")
        self.assertEqual(_instantanea_de(self.raiz), antes, "La inspeccion no debe modificar el disco.")
        return estado

    def _crear(self, ruta, contenido=b"FICTICIO"):
        ruta.parent.mkdir(parents=True, exist_ok=True)
        ruta.write_bytes(contenido)

    def test_clasificador_distingue_base_existente(self):
        self._crear(self.base, b"BASE FICTICIA, NO ES SQLITE")

        estado = self._inspeccionar()

        self.assertEqual(estado.estado, runtime_paths.ESTADO_BASE_EXISTENTE)
        self.assertTrue(estado.existe)
        self.assertEqual(estado.ruta_base, self.base)

    def test_base_ausente_con_backup_o_wal_huerfano_se_reconoce_como_rastro(self):
        casos = {
            "backup": self.backup_dir / "backup_20261001_120000.db",
            "wal": self.database_dir / "fm_master.db-wal",
            "journal": self.database_dir / "fm_master.db-journal",
            "pdf": self.pdf_dir / "resumenes" / "resumen.pdf",
        }
        for nombre, rastro in casos.items():
            with self.subTest(rastro=nombre):
                self._crear(rastro)

                estado = self._inspeccionar()

                self.assertEqual(estado.estado, runtime_paths.ESTADO_BASE_AUSENTE_CON_RASTROS)
                self.assertFalse(estado.existe)
                self.assertTrue(estado.rastros)
                rastro.unlink()

    def test_ruta_de_base_ocupada_por_un_directorio_no_es_base_existente(self):
        self.base.mkdir(parents=True)

        estado = self._inspeccionar()

        self.assertEqual(estado.estado, runtime_paths.ESTADO_BASE_AUSENTE_CON_RASTROS)
        self.assertIn(self.base, estado.rastros)

    def test_base_ausente_sin_rastros_con_o_sin_directorios_vacios(self):
        for crear_directorios in (False, True):
            with self.subTest(crear_directorios=crear_directorios):
                if crear_directorios:
                    for carpeta in (self.database_dir, self.backup_dir, self.pdf_dir):
                        carpeta.mkdir(exist_ok=True)

                estado = self._inspeccionar()

                self.assertEqual(estado.estado, runtime_paths.ESTADO_BASE_AUSENTE_SIN_RASTROS)
                self.assertEqual(estado.rastros, ())


class BarreraBaseAntesDeCrearBaseTest(unittest.TestCase):
    def setUp(self):
        import main

        self.main = main
        self.llamadas = []

    def _estado(self, estado, rastros=()):
        return runtime_paths.EstadoArchivoBase(estado, Path("ficticia") / "fm_master.db", rastros)

    def _verificar(self, inspeccionar, preparar=None):
        return self.main.verificar_base_antes_de_arrancar(
            inspeccionar=inspeccionar,
            preparar=preparar or (lambda: self.llamadas.append("preparar")),
            notificar=lambda titulo, mensaje: self.llamadas.append(("notificar", titulo, mensaje)),
        )

    def test_base_existente_prepara_directorios_y_permite_continuar(self):
        resultado = self._verificar(lambda: self._estado(runtime_paths.ESTADO_BASE_EXISTENTE))

        self.assertTrue(resultado)
        self.assertEqual(self.llamadas, ["preparar"])

    def test_base_ausente_detiene_sin_preparar_y_avisa(self):
        casos = (
            (runtime_paths.ESTADO_BASE_AUSENTE_CON_RASTROS, (Path("backup"),), "Restaure"),
            (runtime_paths.ESTADO_BASE_AUSENTE_SIN_RASTROS, (), "confirmación"),
        )
        for estado, rastros, texto in casos:
            with self.subTest(estado=estado):
                self.llamadas.clear()

                resultado = self._verificar(lambda: self._estado(estado, rastros))

                self.assertFalse(resultado)
                self.assertEqual(len(self.llamadas), 1)
                self.assertEqual(self.llamadas[0][0], "notificar")
                self.assertIn(texto, self.llamadas[0][2])
                self.assertIn("sin crear ni modificar", self.llamadas[0][2])

    def test_errores_de_inspeccion_o_preparacion_detienen_el_arranque(self):
        def fallar():
            raise PermissionError("acceso denegado ficticio")

        self.assertFalse(self._verificar(fallar))
        self.assertEqual([llamada[0] for llamada in self.llamadas], ["notificar"])

        self.llamadas.clear()
        self.assertFalse(
            self._verificar(lambda: self._estado(runtime_paths.ESTADO_BASE_EXISTENTE), preparar=fallar)
        )
        self.assertEqual([llamada[0] for llamada in self.llamadas], ["notificar"])


_ARRANQUE_SIMULADO = """
import importlib.util
import json
import runpy
import sqlite3
import sys
import tkinter
import tkinter.messagebox
from pathlib import Path

raiz = Path(sys.argv[1])
proyecto = Path(sys.argv[2])
sys.path.insert(0, str(proyecto))
sys.frozen = True
sys.executable = str(raiz / "aplicacion" / "FM_Master_Gestion.exe")
sys._MEIPASS = str(raiz / "bundle")
registro = {"connect": [], "crear_base": 0, "avisos": []}

def connect_prohibido(*args, **kwargs):
    registro["connect"].append([str(a) for a in args])
    raise RuntimeError("sqlite3.connect prohibido en la prueba")

sqlite3.connect = connect_prohibido

class TkFalso:
    def withdraw(self):
        pass
    def destroy(self):
        pass

tkinter.Tk = TkFalso
tkinter.messagebox.showerror = lambda titulo, mensaje, **k: registro["avisos"].append(titulo)

spec = importlib.util.spec_from_file_location("runtime_paths", raiz / "codigo" / "runtime_paths.py")
rutas = importlib.util.module_from_spec(spec)
sys.modules["runtime_paths"] = rutas
spec.loader.exec_module(rutas)

import database

def crear_base_prohibida():
    registro["crear_base"] += 1
    raise SystemExit(99)

database.crear_base = crear_base_prohibida
codigo = 0
try:
    runpy.run_path(str(proyecto / "main.py"), run_name="__main__")
except SystemExit as salida:
    codigo = salida.code
registro["codigo"] = codigo
print("RESULTADO=" + json.dumps(registro))
"""


class ArranqueSimuladoConBaseAusenteTest(unittest.TestCase):
    def setUp(self):
        temporal = tempfile.TemporaryDirectory()
        self.addCleanup(temporal.cleanup)
        self.raiz = Path(temporal.name)
        for carpeta in ("codigo", "aplicacion", "bundle", "trabajo"):
            (self.raiz / carpeta).mkdir()
        self.proyecto = Path(__file__).resolve().parents[1]
        shutil.copyfile(self.proyecto / "runtime_paths.py", self.raiz / "codigo" / "runtime_paths.py")
        base_empaquetada = self.raiz / "bundle" / "database" / "fm_master.db"
        base_empaquetada.parent.mkdir(parents=True)
        base_empaquetada.write_bytes(b"BASE EMPAQUETADA FICTICIA")

    def _arrancar(self):
        proceso = subprocess.run(
            [sys.executable, "-I", "-B", "-c", _ARRANQUE_SIMULADO, str(self.raiz), str(self.proyecto)],
            cwd=self.raiz / "trabajo",
            capture_output=True,
            text=True,
            timeout=120,
        )
        lineas = [l for l in proceso.stdout.splitlines() if l.startswith("RESULTADO=")]
        self.assertTrue(lineas, proceso.stdout + proceso.stderr)
        return json.loads(lineas[-1][len("RESULTADO="):])

    def _comprobar_bloqueo(self):
        antes = _instantanea_de(self.raiz)

        resultado = self._arrancar()

        self.assertEqual(resultado["codigo"], 1)
        self.assertEqual(resultado["crear_base"], 0)
        self.assertEqual(resultado["connect"], [])
        self.assertEqual(resultado["avisos"], ["Base de datos no encontrada"])
        self.assertEqual(
            _instantanea_de(self.raiz), antes,
            "Una base ausente no debe crear directorios, copiar ni crear bases.",
        )

    def test_base_empaquetada_no_autoriza_instalacion_nueva(self):
        self._comprobar_bloqueo()

    def test_base_ausente_con_rastros_detiene_antes_de_crear_base(self):
        rastro = self.raiz / "aplicacion" / "backup" / "backup_20261001_120000.db"
        rastro.parent.mkdir(parents=True)
        rastro.write_bytes(b"BACKUP FICTICIO")

        self._comprobar_bloqueo()


class ConexionExistenteYArranqueTest(unittest.TestCase):
    def setUp(self):
        import database
        import main

        self.database = database
        self.main = main
        temporal = tempfile.TemporaryDirectory()
        self.addCleanup(temporal.cleanup)
        self.raiz = Path(temporal.name)
        self.base = self.raiz / "base con espacios # %.db"
        self.enterContext(patch.object(database, "DB_NAME", str(self.base)))

    def test_conectar_no_crea_archivo_si_la_ruta_no_existe(self):
        antes = _instantanea_de(self.raiz)

        with self.assertRaises(sqlite3.OperationalError):
            self.database.conectar()

        self.assertEqual(_instantanea_de(self.raiz), antes)
        self.assertFalse(self.base.exists())

    def test_conectar_abre_base_existente_con_uri_y_permite_escritura(self):
        # Los caracteres especiales deben codificarse, no alterar la URI SQLite.
        with patch.object(self.database, "DB_NAME", str(self.base)):
            with closing(sqlite3.connect(self.base)):
                pass
            conexion = self.database.conectar()
            try:
                conexion.execute("CREATE TABLE prueba (id INTEGER)")
                conexion.commit()
            finally:
                conexion.close()
            with closing(sqlite3.connect(self.base)) as verificacion:
                self.assertEqual(verificacion.execute("SELECT * FROM prueba").fetchall(), [])

    def _ejecutar_bloque_arranque(self, inspeccionar, preparar, crear_base):
        origen = Path(self.main.__file__).read_text(encoding="utf-8")
        arbol = ast.parse(origen)
        bloque = arbol.body[-1]
        self.assertIsInstance(bloque, ast.If)
        self.assertEqual(ast.unparse(bloque.test), "__name__ == '__main__'")
        self.avisar = Mock()
        self.usuarios = Mock()
        self.interfaz = Mock()
        self.servicios = Mock()
        espacio = {
            **vars(self.main),
            "__name__": "__main__",
            "inspeccionar_archivo_base": inspeccionar,
            "verificar_base_antes_de_arrancar": lambda: self.main.verificar_base_antes_de_arrancar(
                inspeccionar=inspeccionar, preparar=preparar, notificar=self.avisar,
            ),
            "crear_base": crear_base,
            "mostrar_error_arranque": self.avisar,
            "UsuarioService": self.usuarios,
            "FMMasterApp": self.interfaz,
            "iniciar_servicios_post_login": self.servicios,
        }
        # Ejecuta solo la coordinacion real de arranque, con todas sus salidas dobladas.
        exec(compile(ast.Module(body=[bloque], type_ignores=[]), self.main.__file__, "exec"), espacio)

    def _inspeccionar(self):
        return runtime_paths.inspeccionar_archivo_base(
            database_path=self.base, directorios_escritura=(),
        )

    def test_base_desaparecida_no_se_recrea_y_detiene_usuarios_interfaz_y_servicios(self):
        self.base = self.raiz / "fm_master.db"
        with patch.object(self.database, "DB_NAME", str(self.base)):
            with closing(sqlite3.connect(self.base)):
                pass
            crear = Mock(wraps=self.database.crear_base)
            preparar = Mock(side_effect=self.base.unlink)
            inspeccionar = Mock(side_effect=self._inspeccionar)

            with self.assertRaises(SystemExit) as salida:
                self._ejecutar_bloque_arranque(inspeccionar, preparar, crear)

        self.assertEqual(salida.exception.code, 1)
        crear.assert_called_once_with()
        preparar.assert_called_once_with()
        self.assertEqual(inspeccionar.call_count, 2)
        self.assertFalse(self.base.exists())
        self.assertEqual(list(self.raiz.iterdir()), [])
        self.avisar.assert_called_once()
        self.assertIn("No se encontró la base", self.avisar.call_args.args[1])
        self.usuarios.init_admin_if_missing.assert_not_called()
        self.interfaz.assert_not_called()
        self.servicios.assert_not_called()

    def test_otro_error_sqlite_con_base_existente_no_se_oculta_como_ausencia(self):
        self.base.write_bytes(b"BASE FICTICIA")
        error = sqlite3.OperationalError("database is locked")
        with self.assertRaises(sqlite3.OperationalError) as resultado:
            self._ejecutar_bloque_arranque(self._inspeccionar, Mock(), Mock(side_effect=error))

        self.assertIs(resultado.exception, error)
        self.avisar.assert_not_called()
        self.usuarios.init_admin_if_missing.assert_not_called()
        self.interfaz.assert_not_called()
        self.servicios.assert_not_called()


if __name__ == "__main__":
    unittest.main()
