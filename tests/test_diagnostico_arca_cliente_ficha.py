import unittest
from contextlib import ExitStack
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import MagicMock, mock_open, patch

from services.emisor_fiscal_service import (
    ConfiguracionArcaEmisor, ConfiguracionArcaError, EmisorFiscalService,
    ResultadoValidacionArcaPorAmbiente,
)
from services.arca.homologacion_service import HomologacionService
from services.arca.wsaa_service import WSAAService
from services.arca.wsaa_login_service import WSAALoginService
from services.arca.wsfe_service import WSFEService
from views.cliente_ficha import FichaClienteFrame


class DiagnosticoArcaClienteFichaTest(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.prohibidos = []
        for destino in (
            "sqlite3.connect", "socket.socket.connect", "socket.create_connection",
            "urllib.request.urlopen", "http.client.HTTPConnection.connect",
            "services.emisor_fiscal_service.conectar",
            "services.emisor_fiscal_service.EmisorFiscalService.validar_configuracion_arca",
            "views.cliente_ficha.ctk.CTkToplevel",
        ):
            self.prohibidos.append(self.stack.enter_context(patch(
                destino, side_effect=AssertionError("Llamada prohibida en diagnostico local"),
            )))
        for clase in (HomologacionService, WSAAService, WSAALoginService, WSFEService):
            for nombre in vars(clase):
                if not nombre.startswith("_") and callable(getattr(clase, nombre)):
                    self.prohibidos.append(self.stack.enter_context(patch.object(
                        clase, nombre, side_effect=AssertionError("Servicio remoto prohibido"),
                    )))
        self.addCleanup(self._verificar_prohibidos)
        self.resumen = SimpleNamespace(
            id=109, numero=1000075, cliente_id=50, fecha="2026-10-07",
            total=1000, estado_facturacion="Pendiente",
        )
        self.cliente = [50, "C50", "Cliente Test", "", "", "", "", "", "", "",
                        "30111111118", "Responsable Inscripto", "Factura A", "EMISOR:3"]
        self.emisor = [3, "Emisor Test", "Emisor Test", "30712178619",
                       "Responsable Inscripto", "Factura A", "00999", 1, "",
                       "Homologaci\u00f3n", "", "", "", "legacy-cert", "legacy-key",
                       "legacy-carpeta", 0]
        self.h = ConfiguracionArcaEmisor(1, 3, "HOMOLOGACION", "00002", "h-cert", "h-key", "h-dir")
        self.p = ConfiguracionArcaEmisor(2, 3, "PRODUCCION", "00007", "p-cert", "p-key", "p-dir")
        self.hijas = {"HOMOLOGACION": self.h, "PRODUCCION": self.p}
        self.obtener_emisor = self.stack.enter_context(patch.object(
            EmisorFiscalService, "obtener", side_effect=lambda _: self.emisor,
        ))
        self.stack.enter_context(patch("views.cliente_ficha.ResumenService.obtener",
                                      side_effect=lambda _: self.resumen))
        self.stack.enter_context(patch("views.cliente_ficha.ClienteService.obtener",
                                      side_effect=lambda _: self.cliente))
        self.obtener_hija = self.stack.enter_context(patch.object(
            EmisorFiscalService, "obtener_configuracion_arca", side_effect=self._obtener_hija,
        ))
        self.validar = self.stack.enter_context(patch.object(
            EmisorFiscalService, "validar_configuracion_arca_por_ambiente",
            wraps=EmisorFiscalService.validar_configuracion_arca_por_ambiente,
        ))
        self.archivos = self.stack.enter_context(patch(
            "services.emisor_fiscal_service.ArcaCertificadosService.validar_archivo", return_value=True,
        ))
        self.abrir = self.stack.enter_context(patch("builtins.open", mock_open(read_data=b"x")))
        self.isdir = self.stack.enter_context(patch("services.emisor_fiscal_service.os.path.isdir", return_value=True))
        self.stack.enter_context(patch("services.emisor_fiscal_service.os.access", return_value=True))
        self.frame = MagicMock(spec=FichaClienteFrame)
        self.frame._resolver_emisor_id_desde_referencia.return_value = 3
        self.frame._formatear_moneda.side_effect = lambda x: f"${x}"

    def _verificar_prohibidos(self):
        for mock in self.prohibidos:
            mock.assert_not_called()

    def _obtener_hija(self, emisor_id, ambiente):
        self.assertEqual(emisor_id, 3)
        if ambiente not in self.hijas:
            raise ConfiguracionArcaError("CONFIGURACION_ARCA_NO_ENCONTRADA", "No existe")
        return self.hijas[ambiente]

    def diagnostico(self):
        return FichaClienteFrame._construir_diagnostico_facturacion(self.frame, 109)

    def texto(self, diagnostico):
        return " ".join(item["correcto"] if item["ok"] else item["error"]
                        for item in diagnostico["checklist"])

    def test_h_valida_usa_pv_h_y_permite_continuar(self):
        resultado = self.diagnostico()
        self.assertTrue(resultado["preparada"])
        self.assertEqual(resultado["detalle"]["punto_venta"], "00002")
        self.assertEqual(resultado["detalle"]["ambiente_arca"], "HOMOLOGACION")
        self.validar.assert_called_once_with(3, "HOMOLOGACION")
        self.assertTrue(all(c.args == (3, "HOMOLOGACION") for c in self.obtener_hija.call_args_list))

    def test_h_activa_solo_p_bloquea_sin_fallback(self):
        self.hijas.pop("HOMOLOGACION")
        resultado = self.diagnostico()
        self.assertFalse(resultado["preparada"])
        self.assertIn("No hay configuraci\u00f3n ARCA guardada para HOMOLOGACION.", self.texto(resultado))
        self.obtener_hija.assert_called_once_with(3, "HOMOLOGACION")
        self.validar.assert_not_called()
        self.assertEqual(resultado["detalle"]["punto_venta"], "-")

    def test_p_valida_lee_solo_p_y_emision_real_bloqueada(self):
        self.emisor[9] = "Producci\u00f3n"
        resultado = self.diagnostico()
        self.assertFalse(resultado["preparada"])
        self.assertTrue(resultado["estado_confirmacion"]["configuracion_arca_validada"])
        self.assertEqual(resultado["detalle"]["punto_venta"], "00007")
        self.assertEqual(resultado["detalle"]["ambiente_arca"], "PRODUCCION")
        self.assertIn("emisi\u00f3n real contin\u00faa bloqueada", self.texto(resultado))
        self.validar.assert_called_once_with(3, "PRODUCCION")
        self.assertTrue(all(c.args == (3, "PRODUCCION") for c in self.obtener_hija.call_args_list))

    def test_p_activa_solo_h_bloquea_sin_fallback(self):
        self.emisor[9] = "PRODUCCION"
        self.hijas.pop("PRODUCCION")
        resultado = self.diagnostico()
        self.assertFalse(resultado["preparada"])
        self.assertIn("No hay configuraci\u00f3n ARCA guardada para PRODUCCION.", self.texto(resultado))
        self.obtener_hija.assert_called_once_with(3, "PRODUCCION")
        self.validar.assert_not_called()

    def test_rutas_y_estado_legacy_no_son_autoridad(self):
        resultado = self.diagnostico()
        self.assertTrue(resultado["preparada"])
        self.assertEqual([c.args for c in self.archivos.call_args_list], [("h-cert",), ("h-key",)])
        self.assertEqual([c.args for c in self.abrir.call_args_list], [("h-cert", "rb"), ("h-key", "rb")])
        self.isdir.assert_called_once_with("h-dir")
        self.assertNotIn("legacy", self.texto(resultado))

    def test_hija_incompleta_bloquea_con_errores_locales(self):
        self.hijas["HOMOLOGACION"] = replace(self.h, ruta_certificado=None, ruta_clave_privada=None, carpeta_facturas=None)
        resultado = self.diagnostico()
        self.assertFalse(resultado["preparada"])
        self.assertIn("Falta ruta del archivo de certificado.", self.texto(resultado))
        self.assertIn("Falta ruta del archivo de clave privada.", self.texto(resultado))
        self.assertIn("Falta carpeta de facturas.", self.texto(resultado))
        self.abrir.assert_not_called()

    def test_pv_invalido_bloquea(self):
        self.hijas["HOMOLOGACION"] = replace(self.h, punto_venta="0")
        resultado = self.diagnostico()
        self.assertFalse(resultado["preparada"])
        self.assertIn("Punto de venta invalido", self.texto(resultado))

    def test_archivos_inexistentes_bloquean_sin_exponer_rutas(self):
        self.archivos.return_value = False
        resultado = self.diagnostico()
        self.assertFalse(resultado["preparada"])
        self.assertIn("No existe un archivo de certificado utilizable.", self.texto(resultado))
        self.assertNotIn("h-cert", self.texto(resultado))
        self.assertNotIn("h-key", self.texto(resultado))

    def test_carpeta_inexistente_bloquea(self):
        self.isdir.return_value = False
        resultado = self.diagnostico()
        self.assertFalse(resultado["preparada"])
        self.assertIn("La carpeta de facturas no existe.", self.texto(resultado))

    def test_ambiente_invalido_falla_seguro(self):
        for ambiente in (None, "", "token-secreto"):
            with self.subTest(ambiente=ambiente):
                self.emisor[9] = ambiente
                resultado = self.diagnostico()
                self.assertFalse(resultado["preparada"])
                self.assertIn("Ambiente ARCA activo inv\u00e1lido", self.texto(resultado))
                self.assertNotIn("token-secreto", self.texto(resultado))
        self.obtener_hija.assert_not_called()
        self.validar.assert_not_called()

    def test_emisor_inexistente_bloquea(self):
        self.emisor = None
        resultado = self.diagnostico()
        self.assertFalse(resultado["preparada"])
        self.assertIn("emisor fiscal inexistente", self.texto(resultado))
        self.obtener_hija.assert_not_called()

    def test_error_lectura_emisor_controlado(self):
        self.obtener_emisor.side_effect = RuntimeError("clave-privada-secreta")
        resultado = self.diagnostico()
        self.assertFalse(resultado["preparada"])
        self.assertNotIn("clave-privada-secreta", self.texto(resultado))

    def test_errores_configuracion_controlados(self):
        for codigo in ("CONFIGURACION_ARCA_AMBIGUA", "CONFIGURACION_ARCA_INCOHERENTE", "LECTURA_CONFIGURACION_ARCA_FALLIDA", "EMISOR_FISCAL_NO_ENCONTRADO"):
            with self.subTest(codigo=codigo):
                self.obtener_hija.side_effect = ConfiguracionArcaError(codigo, "token-secreto")
                resultado = self.diagnostico()
                self.assertFalse(resultado["preparada"])
                self.assertNotIn("token-secreto", self.texto(resultado))
        self.validar.assert_not_called()

    def test_error_validacion_controlado(self):
        self.validar.side_effect = RuntimeError("token-secreto")
        resultado = self.diagnostico()
        self.assertFalse(resultado["preparada"])
        self.assertIn("No se pudo comprobar", self.texto(resultado))
        self.assertNotIn("token-secreto", self.texto(resultado))

    def test_configuracion_cambia_durante_validacion_bloquea(self):
        self.validar.return_value = ResultadoValidacionArcaPorAmbiente(True, "VALIDACION_OFFLINE_OK", configuracion=self.p)
        resultado = self.diagnostico()
        self.assertFalse(resultado["preparada"])
        self.assertIn("inconsistente", self.texto(resultado))

    def test_validaciones_cliente_existentes_se_conservan(self):
        for indice, valor in ((2, ""), (10, ""), (11, ""), (12, "Factura B")):
            with self.subTest(indice=indice):
                original = self.cliente[indice]
                self.cliente[indice] = valor
                resultado = self.diagnostico()
                self.assertFalse(resultado["preparada"])
                self.assertTrue(resultado["faltantes_cliente"])
                self.cliente[indice] = original

    def test_validaciones_resumen_existentes_se_conservan(self):
        for cambios in ({"total": 0}, {"estado_facturacion": "Facturado"}):
            with self.subTest(cambios=cambios):
                original = vars(self.resumen).copy()
                vars(self.resumen).update(cambios)
                self.assertFalse(self.diagnostico()["preparada"])
                vars(self.resumen).update(original)
        self.resumen = None
        self.assertFalse(self.diagnostico()["preparada"])

    def test_cuit_emisor_faltante_bloquea(self):
        self.emisor[3] = ""
        resultado = self.diagnostico()
        self.assertFalse(resultado["preparada"])
        self.assertTrue(resultado["faltantes_emisor"])


if __name__ == "__main__":
    unittest.main()
