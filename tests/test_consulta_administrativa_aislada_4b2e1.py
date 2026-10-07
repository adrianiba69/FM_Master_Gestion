import ast
import copy
import socket
import sqlite3
import unittest
import urllib.request
from contextlib import ExitStack
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch


FUENTE = Path(__file__).resolve().parents[1] / "views" / "facturacion_arca.py"
TITULO = "Consulta temporalmente no disponible"
MENSAJE = (
    "Esta herramienta administrativa pertenece al flujo ARCA anterior "
    "y fue deshabilitada preventivamente mientras se adapta a la nueva "
    "configuraci\u00f3n separada por ambiente."
)


class ConsultaAdministrativaAisladaTest(unittest.TestCase):
    def setUp(self):
        self.arbol = ast.parse(FUENTE.read_text(encoding="utf-8"))
        self.clase = next(
            nodo for nodo in self.arbol.body
            if isinstance(nodo, ast.ClassDef) and nodo.name == "FacturacionArcaFrame"
        )
        self.messagebox = Mock()
        self.dependencias = {
            nombre: Mock(side_effect=AssertionError("Dependencia prohibida: " + nombre))
            for nombre in (
                "HomologacionService", "WSAAService", "WSAALoginService", "WSFEService",
                "EmisorFiscalService", "EmisorService", "FacturaArcaService",
                "ClienteService", "ResumenService",
            )
        }
        for dependencia in self.dependencias.values():
            dependencia.obtener.side_effect = AssertionError("Lectura de datos prohibida")
            dependencia.consultar_ultimo_comprobante.side_effect = AssertionError("Consulta ARCA prohibida")
            dependencia.guardar.side_effect = AssertionError("Escritura prohibida")
            dependencia.actualizar.side_effect = AssertionError("Escritura prohibida")
        self.espacio = {
            "ctk": SimpleNamespace(CTkFrame=object),
            "messagebox": self.messagebox,
            **self.dependencias,
        }
        exec(compile(ast.Module(body=[self.clase], type_ignores=[]), str(FUENTE), "exec"), self.espacio)
        self.frame = object.__new__(self.espacio["FacturacionArcaFrame"])

    def invocar_sin_efectos(self, callback):
        with ExitStack() as pila:
            barreras = [
                pila.enter_context(patch(objetivo, side_effect=AssertionError("Efecto prohibido")))
                for objetivo in (
                    "builtins.open", "pathlib.Path.open", "sqlite3.connect",
                    "socket.socket", "socket.create_connection", "urllib.request.urlopen",
                )
            ]
            callback()
            for barrera in barreras:
                barrera.assert_not_called()
        for dependencia in self.dependencias.values():
            self.assertEqual(dependencia.mock_calls, [])
        self.messagebox.showinfo.assert_called_once_with(TITULO, MENSAJE, parent=self.frame)
        self.messagebox.showwarning.assert_not_called()
        self.messagebox.showerror.assert_not_called()

    def test_handler_no_invoca_homologacion_wsaa_wsfe_red_ni_db(self):
        self.invocar_sin_efectos(self.frame.consultar_ultimo_comprobante)

    def test_no_lee_seleccion_ni_credenciales_ni_modifica_datos(self):
        self.frame.emisores = {"Emisor": 1}
        self.frame.datos = {"estado": "Pendiente", "importe": 100, "ambiente": "HOMOLOGACION"}
        self.frame.selector_emisor = Mock()
        self.frame.selector_emisor.get.side_effect = AssertionError("No debe leer la seleccion")
        emisores_antes = copy.deepcopy(self.frame.emisores)
        datos_antes = copy.deepcopy(self.frame.datos)
        atributos_antes = vars(self.frame).copy()
        self.invocar_sin_efectos(self.frame.consultar_ultimo_comprobante)
        self.frame.selector_emisor.get.assert_not_called()
        self.assertEqual(self.frame.emisores, emisores_antes)
        self.assertEqual(self.frame.datos, datos_antes)
        self.assertEqual(vars(self.frame), atributos_antes)

    def test_aviso_incondicional_sin_emisor_y_con_ambos_ambientes(self):
        for ambiente in (None, "HOMOLOGACION", "PRODUCCION"):
            with self.subTest(ambiente=ambiente):
                self.messagebox.reset_mock()
                self.frame.emisores = {} if ambiente is None else {"Emisor": 1}
                self.frame.ambiente = ambiente
                self.invocar_sin_efectos(self.frame.consultar_ultimo_comprobante)
                self.assertEqual(self.frame.ambiente, ambiente)

    def test_boton_conservado_invoca_solo_aviso(self):
        botones = []

        def crear_boton(*args, **opciones):
            botones.append(opciones)
            return Mock()

        self.espacio["ctk"] = SimpleNamespace(
            CTkFrame=Mock(), CTkLabel=Mock(), CTkComboBox=Mock(),
            CTkButton=Mock(side_effect=crear_boton),
        )
        self.espacio["ttk"] = Mock()
        self.frame.grid_rowconfigure = Mock()
        self.frame.grid_columnconfigure = Mock()
        self.frame.crear_interfaz()
        consultas = [boton for boton in botones if boton["text"] == "Consultar \u00faltimo comprobante"]
        self.assertEqual(len(consultas), 1)
        self.assertEqual(consultas[0]["command"], self.frame.consultar_ultimo_comprobante)
        self.invocar_sin_efectos(consultas[0]["command"])

    def test_sin_camino_legacy_ni_callback_secundario_en_la_vista(self):
        handler = next(
            nodo for nodo in self.clase.body
            if isinstance(nodo, ast.FunctionDef) and nodo.name == "consultar_ultimo_comprobante"
        )
        self.assertEqual(len(handler.body), 1)
        llamada = handler.body[0].value
        self.assertIsInstance(llamada, ast.Call)
        self.assertEqual(ast.unparse(llamada.func), "messagebox.showinfo")
        referencias = [
            nodo for nodo in ast.walk(self.arbol)
            if isinstance(nodo, ast.Attribute) and nodo.attr == "consultar_ultimo_comprobante"
        ]
        self.assertEqual(len(referencias), 1)
        self.assertEqual(ast.unparse(referencias[0]), "self.consultar_ultimo_comprobante")
        for nodo in ast.walk(self.arbol):
            if isinstance(nodo, ast.Name):
                self.assertNotEqual(nodo.id, "HomologacionService")
            if isinstance(nodo, ast.ImportFrom):
                self.assertNotEqual(nodo.module, "services.arca.homologacion_service")


if __name__ == "__main__":
    unittest.main()
