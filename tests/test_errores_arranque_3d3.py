"""Coordinacion de arranque con imports, interfaz y servicios sustituidos."""

import ast
import importlib.util
import io
import socket
import sqlite3
import sys
import unittest
from contextlib import ExitStack, contextmanager
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock, patch


_RAIZ = Path(__file__).resolve().parents[1]
_FUENTE = _RAIZ / "main.py"
_CONNECT = sqlite3.connect
_CONEXIONES = []
_DENEGACIONES = []


def _autorizar(accion, argumento, valor, _base, _origen):
    if accion == sqlite3.SQLITE_ATTACH or (
        accion == sqlite3.SQLITE_PRAGMA
        and argumento.lower() == "user_version" and valor is not None
    ):
        _DENEGACIONES.append((accion, argumento, valor))
        return sqlite3.SQLITE_DENY
    return sqlite3.SQLITE_OK


def _conectar_memoria(base, *args, **kwargs):
    if base != ":memory:" or kwargs.get("uri") or (len(args) > 6 and args[6]):
        _DENEGACIONES.append(("connect", base))
        raise AssertionError("Solo se permite SQLite :memory: sin URI.")
    conexion = _CONNECT(base, *args, **kwargs)
    conexion.set_authorizer(_autorizar)
    _CONEXIONES.append(base)
    return conexion


@contextmanager
def _guardia():
    perfil_anterior = sys.getprofile()

    def vigilar(frame, evento, argumento):
        if evento == "call":
            ruta = Path(frame.f_code.co_filename)
            if ruta in (_RAIZ / "database.py", _RAIZ / "runtime_paths.py") or (
                ruta.parent in (_RAIZ / "services", _RAIZ / "views")
                or _RAIZ / "services" in ruta.parents
            ):
                raise AssertionError("Modulo operativo real prohibido.")
        if perfil_anterior is not None:
            perfil_anterior(frame, evento, argumento)

    with ExitStack() as pila:
        pila.enter_context(patch("sqlite3.connect", _conectar_memoria))
        pila.enter_context(patch("sqlite3.dbapi2.connect", _conectar_memoria))
        pila.enter_context(patch("socket.socket.connect", side_effect=AssertionError("Red prohibida.")))
        pila.enter_context(patch("socket.create_connection", side_effect=AssertionError("Red prohibida.")))
        sys.setprofile(vigilar)
        try:
            yield
        finally:
            sys.setprofile(perfil_anterior)


def _modulos_sustitutos(arbol):
    modulos = {}
    for nodo in arbol.body:
        if isinstance(nodo, ast.ImportFrom):
            modulo = ModuleType(nodo.module)
            for nombre in nodo.names:
                setattr(modulo, nombre.name, Mock(name=f"{nodo.module}.{nombre.name}"))
            modulos[nodo.module] = modulo
    for nombre in ("services", "views"):
        paquete = ModuleType(nombre)
        paquete.__path__ = []
        modulos[nombre] = paquete
    modulos["tkinter"].Tk = Mock(name="Tk")
    modulos["config"].COLOR_NEGRO = "#000000"
    modulos["config"].COLOR_PRINCIPAL = "#C00000"
    ctk = ModuleType("customtkinter")
    ctk.CTk = type("CTkSustituto", (), {})
    ctk.set_appearance_mode = Mock()
    ctk.set_default_color_theme = Mock()
    modulos["customtkinter"] = ctk
    runtime = modulos["runtime_paths"]
    runtime.ESTADO_BASE_EXISTENTE = "BASE_EXISTENTE"
    runtime.ESTADO_BASE_AUSENTE_CON_RASTROS = "BASE_AUSENTE_CON_RASTROS"
    runtime.inspeccionar_archivo_base.return_value = SimpleNamespace(estado="BASE_EXISTENTE")
    return modulos


class ErroresArranqueTests(unittest.TestCase):
    def setUp(self):
        self.pila = ExitStack()
        self.addCleanup(self.pila.close)
        self.pila.enter_context(_guardia())
        self.arbol = ast.parse(_FUENTE.read_text(encoding="utf-8"))
        self.modulos = _modulos_sustitutos(self.arbol)
        self.pila.enter_context(patch.dict(sys.modules, self.modulos))
        spec = importlib.util.spec_from_file_location("_main_errores_3d3", _FUENTE)
        self.main = importlib.util.module_from_spec(spec)
        self.pila.enter_context(patch.dict(sys.modules, {spec.name: self.main}))
        spec.loader.exec_module(self.main)
        self.crear = self.main.crear_base
        self.inspeccionar = self.main.inspeccionar_archivo_base
        self.preparar = self.main.preparar_directorios
        self.usuarios = self.main.UsuarioService
        self.app = Mock(name="FMMasterApp")
        self.notificar = Mock()
        self.servicios = Mock()
        self.mostrar_original = self.main.mostrar_error_arranque
        self.verificar_original = self.main.verificar_base_antes_de_arrancar
        self.pila.enter_context(patch.object(self.main, "FMMasterApp", self.app))
        self.pila.enter_context(patch.object(self.main, "mostrar_error_arranque", self.notificar))
        self.pila.enter_context(patch.object(self.main, "iniciar_servicios_post_login", self.servicios))
        self.pila.enter_context(patch.object(
            self.main, "verificar_base_antes_de_arrancar",
            wraps=lambda: self.verificar_original(
                inspeccionar=self.inspeccionar,
                preparar=self.preparar,
                notificar=self.notificar,
            ),
        ))

    def _coordinacion(self):
        bloque = self.arbol.body[-1]
        self.assertIsInstance(bloque, ast.If)
        self.assertEqual(ast.unparse(bloque.test), "__name__ == '__main__'")
        codigo = compile(ast.Module(body=bloque.body, type_ignores=[]), str(_FUENTE), "exec")
        exec(codigo, vars(self.main))

    def _sin_continuacion(self):
        self.usuarios.init_admin_if_missing.assert_not_called()
        self.app.assert_not_called()
        self.servicios.assert_not_called()
        self.main.BackupService.crear_backup_automatico.assert_not_called()
        self.main.NotificacionService.generar_automaticas.assert_not_called()

    def _comprobar_fallo(self, error):
        self.crear.side_effect = error
        with self.assertLogs(self.main.__name__, level="ERROR") as diagnostico:
            with self.assertRaises(SystemExit) as salida:
                self._coordinacion()
        self.assertEqual(salida.exception.code, 1)
        self.crear.assert_called_once_with()
        self.notificar.assert_called_once()
        mensaje = self.notificar.call_args.args[1]
        self.assertIn("No debe continuar utilizando el programa", mensaje)
        self.assertIn("sin abrir la interfaz ni iniciar los servicios", mensaje)
        self.assertNotIn(str(error), mensaje)
        self.assertIn(type(error).__name__, diagnostico.output[0])
        self._sin_continuacion()
        return diagnostico

    def test_integrity_error_detiene_arranque(self):
        self._comprobar_fallo(sqlite3.IntegrityError("duplicado fiscal privado"))

    def test_operational_error_detiene_arranque(self):
        self._comprobar_fallo(sqlite3.OperationalError("base bloqueada privada"))

    def test_value_error_detiene_arranque(self):
        self._comprobar_fallo(ValueError("indice fiscal privado"))

    def test_runtime_error_detiene_arranque(self):
        self._comprobar_fallo(RuntimeError("detalle privado"))

    def test_otro_sqlite_error_detiene_arranque(self):
        self._comprobar_fallo(sqlite3.DatabaseError("base incompatible privada"))

    def test_diagnostico_conserva_tipo_y_ubicacion_sin_datos_sensibles(self):
        secreto = "CUIT=20123456789; CAE=12345678901234; clave=secreta"

        def inicializacion_fallida():
            error = ValueError(secreto)
            error.add_note(secreto)
            raise error from RuntimeError(secreto)

        self.crear.side_effect = inicializacion_fallida
        with self.assertLogs(self.main.__name__, level="ERROR") as diagnostico:
            with self.assertRaises(SystemExit):
                self._coordinacion()
        texto = "\n".join(diagnostico.output)
        self.assertIn("ValueError", texto)
        self.assertIn("inicializacion_fallida:", texto)
        self.assertIn("inicializar_base_antes_de_arrancar:", texto)
        self.assertNotIn(secreto, texto)
        self.assertNotIn(secreto, self.notificar.call_args.args[1])
        self._sin_continuacion()

    def test_base_desaparecida_conserva_aviso_especifico(self):
        self.inspeccionar.side_effect = [
            SimpleNamespace(estado="BASE_EXISTENTE"),
            SimpleNamespace(estado="BASE_AUSENTE", ruta_base="base ficticia"),
        ]
        self._comprobar_fallo(sqlite3.OperationalError("archivo desaparecido"))
        self.assertEqual(self.inspeccionar.call_count, 2)
        self.assertEqual(self.notificar.call_args.args[0], "Base de datos no encontrada")
        self.assertIn("No se encontró la base", self.notificar.call_args.args[1])

    def test_reinspeccion_fallida_no_oculta_error_ni_permite_continuar(self):
        self.inspeccionar.side_effect = [
            SimpleNamespace(estado="BASE_EXISTENTE"),
            PermissionError("ruta privada"),
        ]
        diagnostico = self._comprobar_fallo(sqlite3.OperationalError("fallo original privado"))
        self.assertEqual(len(diagnostico.output), 2)
        self.assertIn("PermissionError", diagnostico.output[1])
        self.assertNotIn("ruta privada", diagnostico.output[1])

    def test_exito_conserva_orden_y_configuracion_de_interfaz(self):
        orden = Mock()
        for nombre, funcion in (
            ("inspeccionar", self.inspeccionar),
            ("preparar", self.preparar),
            ("crear", self.crear),
            ("admin", self.usuarios.init_admin_if_missing),
            ("app", self.app),
            ("servicios", self.servicios),
        ):
            orden.attach_mock(funcion, nombre)
        with patch.object(self.main.logging.getLogger(self.main.__name__), "error") as log:
            self._coordinacion()
        self.assertEqual(
            [llamada[0] for llamada in orden.mock_calls if "." not in llamada[0]],
            ["inspeccionar", "preparar", "crear", "admin", "app", "servicios"],
        )
        self.notificar.assert_not_called()
        log.assert_not_called()
        app = self.app.return_value
        self.assertEqual(app.current_user, {"usuario": "admin", "rol": "Administrador"})
        self.servicios.assert_called_once_with(app)
        self.assertEqual(
            [llamada[0] for llamada in app.mock_calls],
            ["aplicar_permisos", "deiconify", "state", "lift", "focus_force",
             "update_idletasks", "mainloop"],
        )
        app.state.assert_called_once_with("zoomed")

    def test_barrera_previa_sigue_deteniendo_antes_de_inicializar(self):
        self.inspeccionar.side_effect = OSError("inspeccion ficticia")
        with self.assertRaises(SystemExit) as salida:
            self._coordinacion()
        self.assertEqual(salida.exception.code, 1)
        self.crear.assert_not_called()
        self.preparar.assert_not_called()
        self._sin_continuacion()

    def test_importacion_no_ejecuta_inicializacion_ni_interfaz(self):
        self.crear.assert_not_called()
        self.inspeccionar.assert_not_called()
        self.preparar.assert_not_called()
        self.main.tk.Tk.assert_not_called()
        self.main.ctk.set_appearance_mode.assert_called_once_with("light")
        self.main.ctk.set_default_color_theme.assert_called_once_with("blue")
        self._sin_continuacion()

    def test_presentacion_usa_tk_temporal_y_lo_destruye(self):
        raiz = self.main.tk.Tk.return_value
        mostrar = self.main.messagebox.showerror
        self.mostrar_original("Error de prueba", "Mensaje de prueba")
        self.main.tk.Tk.assert_called_once_with()
        raiz.withdraw.assert_called_once_with()
        mostrar.assert_called_once_with("Error de prueba", "Mensaje de prueba", parent=raiz)
        raiz.destroy.assert_called_once_with()
        self.app.assert_not_called()

    def test_tk_fallido_usa_stderr_y_detiene_arranque(self):
        self.main.tk.Tk.side_effect = RuntimeError("Tk privado no disponible")
        self.main.mostrar_error_arranque = self.mostrar_original
        self.crear.side_effect = ValueError("detalle fiscal privado")
        stderr = io.StringIO()
        with patch.object(sys, "stderr", stderr), self.assertLogs(self.main.__name__, level="ERROR"):
            with self.assertRaises(SystemExit) as salida:
                self._coordinacion()
        self.assertEqual(salida.exception.code, 1)
        self.assertIn("No debe continuar", stderr.getvalue())
        self.assertNotIn("privado", stderr.getvalue())
        self._sin_continuacion()

    def test_interrupciones_no_se_convierten_en_errores_ordinarios(self):
        for error in (KeyboardInterrupt(), SystemExit(7)):
            with self.subTest(tipo=type(error).__name__):
                self.crear.side_effect = error
                with self.assertRaises(type(error)) as salida:
                    self._coordinacion()
                self.assertIs(salida.exception, error)
                self.notificar.assert_not_called()
                self._sin_continuacion()

    def test_sin_tk_ni_stderr_el_arranque_tambien_se_detiene(self):
        self.main.tk.Tk.side_effect = RuntimeError("Tk no disponible")
        self.main.mostrar_error_arranque = self.mostrar_original
        self.crear.side_effect = RuntimeError("fallo de inicializacion")
        with patch.object(sys, "stderr", None), self.assertLogs(self.main.__name__, level="ERROR"):
            with self.assertRaises(SystemExit) as salida:
                self._coordinacion()
        self.assertEqual(salida.exception.code, 1)
        self._sin_continuacion()

    def test_guardia_bloquea_archivos_uri_attach_y_version(self):
        for conectar in (sqlite3.connect, sqlite3.dbapi2.connect):
            for destino, opciones in (
                ("prohibida.db", {}),
                ("file::memory:", {"uri": True}),
                (":memory:", {"uri": True}),
            ):
                with self.assertRaises(AssertionError):
                    conectar(destino, **opciones)
        conexion = sqlite3.connect(":memory:")
        try:
            with self.assertRaises(sqlite3.DatabaseError):
                conexion.execute("ATTACH ':memory:' AS ajena")
            with self.assertRaises(sqlite3.DatabaseError):
                conexion.execute("PRAGMA user_version=123")
            self.assertEqual(conexion.execute("PRAGMA user_version").fetchone(), (0,))
        finally:
            conexion.close()


if __name__ == "__main__":
    unittest.main()
