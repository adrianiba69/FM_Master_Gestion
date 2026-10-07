import inspect
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from services.emisor_fiscal_service import ConfiguracionArcaError, ResultadoValidacionArcaPorAmbiente
from tests import test_ui_config_arca_4b2d2 as helpers
from views import emisores_fiscales as vista


class ValidacionLocalUiTest(unittest.TestCase):
    def setUp(self):
        self.ventana = helpers.UiConfiguracionArcaPorAmbienteTest.construir_ventana()
        self.ventana.emisor_id_actual = 42
        self.configuracion = SimpleNamespace(
            punto_venta="00002", ruta_certificado="RUTA_PRIVADA_CERT",
            ruta_clave_privada="RUTA_PRIVADA_CLAVE", carpeta_facturas="RUTA_PRIVADA_CARPETA",
        )
        for ambiente in self.ventana.AMBIENTES_ARCA:
            valores = tuple(getattr(self.configuracion, campo) for campo in self.ventana.CAMPOS_ARCA)
            self.ventana.arca_original[ambiente] = valores
            self.ventana._poner_valores_arca(ambiente, valores)
            self.ventana.arca_validar_botones[ambiente] = helpers.FakeButton()
            self.ventana.arca_validacion_labels[ambiente] = {
                bloque: helpers.FakeLabel() for bloque in
                ("estado", "alcance", "errores", "advertencias", "controles", "produccion")
            }
            self.ventana._refrescar_estado_arca(ambiente)
        self.resultado = ResultadoValidacionArcaPorAmbiente(
            True, "VALIDACION_OFFLINE_OK", advertencias=("No demuestra validez criptografica.",),
            controles_no_realizados=("autorizacion_arca: no verificada",),
            configuracion=self.configuracion,
        )
        self.validador = self.enterContext(patch.object(
            vista.EmisorFiscalService, "validar_configuracion_arca_por_ambiente", return_value=self.resultado
        ))
        self.legacy = self.enterContext(patch.object(
            vista.EmisorFiscalService, "validar_configuracion_arca", side_effect=AssertionError("legacy prohibido")
        ))
        self.enterContext(patch("services.emisor_fiscal_service.conectar", side_effect=AssertionError("DB prohibida")))
        self.enterContext(patch("urllib.request.urlopen", side_effect=AssertionError("red prohibida")))
        self.mensajes = self.enterContext(patch.object(vista, "messagebox"))

    def texto(self, ambiente, bloque=None):
        etiquetas = self.ventana.arca_validacion_labels[ambiente]
        return etiquetas[bloque].texto if bloque else "\n".join(etiqueta.texto for etiqueta in etiquetas.values())

    def modificar(self, ambiente, campo="punto_venta"):
        entrada = self.ventana.arca_entries[ambiente][campo]
        entrada.delete(0, "end")
        entrada.insert(0, "CAMBIO")
        self.ventana._refrescar_estado_arca(ambiente)

    def test_h_explicitamente_aunque_activo_p(self):
        self.ventana.ambiente_activo = "PRODUCCION"
        self.assertTrue(self.ventana.validar_configuracion_local("HOMOLOGACION"))
        self.validador.assert_called_once_with(42, "HOMOLOGACION")

    def test_p_explicitamente_aunque_activo_h(self):
        self.assertTrue(self.ventana.validar_configuracion_local("PRODUCCION"))
        self.validador.assert_called_once_with(42, "PRODUCCION")

    def test_botones_vinculan_su_ambiente(self):
        for ambiente in self.ventana.AMBIENTES_ARCA:
            with self.subTest(ambiente=ambiente), patch.object(vista, "ctk") as ctk, patch.object(
                self.ventana, "_crear_selector_ruta", return_value=Mock()
            ), patch.object(self.ventana, "validar_configuracion_local") as validar:
                self.ventana._crear_pestana_arca(Mock(), ambiente)
                comando = ctk.CTkButton.call_args.kwargs["command"]
                comando()
                validar.assert_called_once_with(ambiente)

    def test_dirty_h_bloquea_solo_h(self):
        self.modificar("HOMOLOGACION")
        self.assertFalse(self.ventana.validar_configuracion_local("HOMOLOGACION"))
        self.assertEqual(self.ventana.arca_validar_botones["HOMOLOGACION"].state, "disabled")
        self.assertEqual(self.ventana.arca_validar_botones["PRODUCCION"].state, "normal")
        self.assertTrue(self.ventana.validar_configuracion_local("PRODUCCION"))
        self.validador.assert_called_once_with(42, "PRODUCCION")

    def test_cambios_observados_sin_evento_de_teclado(self):
        variables = [Mock() for _campo in self.ventana.CAMPOS_ARCA]
        with patch.object(vista, "ctk") as ctk, patch.object(
            self.ventana, "_crear_selector_ruta", return_value=Mock()
        ), patch.object(self.ventana, "_refrescar_estado_arca") as refrescar:
            ctk.StringVar.side_effect = variables
            self.ventana._crear_pestana_arca(Mock(), "PRODUCCION")
            self.assertEqual(ctk.StringVar.call_count, 4)
            for variable in variables:
                variable.trace_add.assert_called_once()
                evento, callback = variable.trace_add.call_args.args
                self.assertEqual(evento, "write")
                callback("variable", "", "write")
                refrescar.assert_called_with("PRODUCCION")

    def test_dirty_p_bloquea_solo_p(self):
        self.modificar("PRODUCCION")
        self.assertFalse(self.ventana.validar_configuracion_local("PRODUCCION"))
        self.assertEqual(self.ventana.arca_validar_botones["PRODUCCION"].state, "disabled")
        self.assertEqual(self.ventana.arca_validar_botones["HOMOLOGACION"].state, "normal")
        self.assertTrue(self.ventana.validar_configuracion_local("HOMOLOGACION"))
        self.validador.assert_called_once_with(42, "HOMOLOGACION")

    def test_sin_configuracion_no_muestra_ok(self):
        self.ventana.arca_original["PRODUCCION"] = None
        self.ventana._poner_valores_arca("PRODUCCION", ("", "", "", ""))
        self.assertFalse(self.ventana.validar_configuracion_local("PRODUCCION"))
        self.assertIn("Sin configurar", self.texto("PRODUCCION"))
        self.assertNotIn("OK", self.texto("PRODUCCION"))
        self.assertEqual(self.ventana.arca_validar_botones["PRODUCCION"].state, "disabled")
        self.validador.assert_not_called()

    def test_nuevo_emisor_no_valida(self):
        self.ventana.emisor_id_actual = None
        self.assertFalse(self.ventana.validar_configuracion_local("HOMOLOGACION"))
        self.validador.assert_not_called()

    def test_ok_y_alcance_local(self):
        self.ventana.validar_configuracion_local("HOMOLOGACION")
        self.assertEqual(self.texto("HOMOLOGACION", "estado"), "Validación local básica OK")
        self.assertIn("no acredita habilitación ni conexión con ARCA", self.texto("HOMOLOGACION"))
        self.assertEqual(self.ventana.arca_validacion_labels["PRODUCCION"]["estado"].texto,
                         "Validación local pendiente.")
        self.mensajes.showinfo.assert_not_called()
        self.mensajes.showwarning.assert_not_called()
        self.mensajes.showerror.assert_not_called()

    def test_produccion_ok_sigue_bloqueada(self):
        self.ventana.validar_configuracion_local("PRODUCCION")
        self.assertIn("Validación local básica OK", self.texto("PRODUCCION"))
        self.assertIn("La emisión real permanece bloqueada.", self.texto("PRODUCCION"))
        self.assertIn("La emisión real permanece bloqueada.", self.ventana.ADVERTENCIA_PRODUCCION)

    def test_errores_y_codigo(self):
        self.validador.return_value = ResultadoValidacionArcaPorAmbiente(
            False, "CONFIGURACION_ARCA_INVALIDA", errores=("Punto de venta invalido.", "Falta clave privada.")
        )
        self.assertFalse(self.ventana.validar_configuracion_local("HOMOLOGACION"))
        self.assertIn("CONFIGURACION_ARCA_INVALIDA", self.texto("HOMOLOGACION", "errores"))
        self.assertIn("Punto de venta invalido.", self.texto("HOMOLOGACION", "errores"))
        self.assertIn("Falta clave privada.", self.texto("HOMOLOGACION", "errores"))

    def test_advertencias_separadas(self):
        self.ventana.validar_configuracion_local("HOMOLOGACION")
        self.assertIn("No demuestra validez criptografica.", self.texto("HOMOLOGACION", "advertencias"))
        self.assertEqual(self.texto("HOMOLOGACION", "errores"), "")

    def test_controles_no_realizados(self):
        self.ventana.validar_configuracion_local("HOMOLOGACION")
        self.assertIn("autorizacion_arca: no verificada", self.texto("HOMOLOGACION", "controles"))

    def test_no_muestra_configuracion_ni_rutas(self):
        self.ventana.validar_configuracion_local("HOMOLOGACION")
        self.assertNotIn("RUTA_PRIVADA", self.texto("HOMOLOGACION"))
        self.assertNotIn("configuracion", repr(self.ventana.arca_validacion_resultados["HOMOLOGACION"]))

    def test_editar_cada_campo_invalida_ok(self):
        for campo in self.ventana.CAMPOS_ARCA:
            with self.subTest(campo=campo):
                self.ventana._poner_valores_arca("HOMOLOGACION", self.ventana.arca_original["HOMOLOGACION"])
                self.ventana.validar_configuracion_local("HOMOLOGACION")
                self.modificar("HOMOLOGACION", campo)
                self.assertNotIn("OK", self.texto("HOMOLOGACION"))
                self.assertIn("Guarde antes de validar", self.texto("HOMOLOGACION"))
                self.assertIsNone(self.ventana.arca_validacion_resultados["HOMOLOGACION"])

    def test_seleccionar_invalida_resultado(self):
        self.ventana.validar_configuracion_local("HOMOLOGACION")
        self.ventana._seleccionar_ruta("HOMOLOGACION", "ruta_certificado", "OTRA_RUTA")
        self.assertNotIn("OK", self.texto("HOMOLOGACION"))

    def test_guardar_habilita_limpia_y_no_valida(self):
        self.ventana.validar_configuracion_local("HOMOLOGACION")
        self.modificar("HOMOLOGACION")
        self.validador.reset_mock()
        with patch.object(vista.EmisorFiscalService, "guardar_configuracion_arca", return_value=SimpleNamespace(
            configuracion=self.configuracion
        )):
            self.assertEqual(self.ventana._guardar_configuraciones_arca_modificadas(42), [])
        self.validador.assert_not_called()
        self.assertEqual(self.ventana.arca_validar_botones["HOMOLOGACION"].state, "normal")
        self.assertEqual(self.texto("HOMOLOGACION", "estado"), "Validación local pendiente.")

    def test_guardar_emisor_conserva_ficha_para_validar(self):
        self.ventana.entry_razon_social.valor = "Emisor"
        self.ventana.entry_cuit.valor = "20111111112"
        with patch.object(vista.EmisorFiscalService, "actualizar_datos_fiscales"), patch.object(
            self.ventana, "cargar_emisores"
        ):
            self.ventana.guardar_emisor()
        self.assertEqual(self.ventana.emisor_id_actual, 42)
        self.validador.assert_not_called()
        self.assertEqual(self.ventana.arca_validar_botones["HOMOLOGACION"].state, "normal")

    def test_cargar_otro_emisor_limpia_resultados(self):
        for ambiente in self.ventana.AMBIENTES_ARCA:
            self.ventana.validar_configuracion_local(ambiente)
        fila = (99, "Otro", "", "20111111112", "Monotributo", "Factura C", "", 1, "",
                "Homologación", "", "", "", "", "", "", 0)
        with patch.object(vista.EmisorFiscalService, "obtener", return_value=fila), patch.object(
            vista.EmisorFiscalService, "obtener_configuracion_arca", return_value=self.configuracion
        ):
            self.ventana._cargar_emisor(99)
        for ambiente in self.ventana.AMBIENTES_ARCA:
            self.assertNotIn("OK", self.texto(ambiente))
            self.assertIsNone(self.ventana.arca_validacion_resultados[ambiente])

    def test_limpiar_nuevo_borra_resultados(self):
        self.ventana.validar_configuracion_local("HOMOLOGACION")
        self.ventana.limpiar_formulario()
        self.assertNotIn("OK", self.texto("HOMOLOGACION"))
        self.assertEqual(self.ventana.arca_validar_botones["HOMOLOGACION"].state, "disabled")

    def test_excepcion_controlada_segura(self):
        self.validador.side_effect = ConfiguracionArcaError("LECTURA_CONFIGURACION_ARCA_FALLIDA", "No se pudo leer.")
        self.assertFalse(self.ventana.validar_configuracion_local("HOMOLOGACION"))
        self.assertIn("LECTURA_CONFIGURACION_ARCA_FALLIDA", self.texto("HOMOLOGACION"))
        self.assertIn("No se pudo leer.", self.texto("HOMOLOGACION"))

    def test_excepcion_inesperada_generica(self):
        self.validador.side_effect = RuntimeError("C:/secreto clave token sign")
        self.assertFalse(self.ventana.validar_configuracion_local("HOMOLOGACION"))
        self.assertIn("No se pudo realizar la validación local", self.texto("HOMOLOGACION"))
        self.assertNotIn("secreto", self.texto("HOMOLOGACION"))

    def test_cero_validador_legacy(self):
        self.ventana.validar_configuracion_local("HOMOLOGACION")
        self.legacy.assert_not_called()
        fuente = inspect.getsource(vista)
        self.assertNotIn("EmisorFiscalService.validar_configuracion_arca(", fuente)
        self.assertNotIn("configuracion_arca_completa", fuente)


if __name__ == "__main__":
    unittest.main()