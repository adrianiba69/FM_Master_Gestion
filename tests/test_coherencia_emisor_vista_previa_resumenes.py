import io
import unittest
from contextlib import ExitStack, redirect_stdout
from copy import deepcopy
from datetime import date
from types import MethodType, SimpleNamespace
from unittest.mock import Mock, patch

from models.resumen import Resumen
from views.resumenes import ResumenesFrame


class CoherenciaEmisorVistaPreviaResumenesTest(unittest.TestCase):
    IDS_INVALIDOS = (None, "", "abc", 0, -1, True, False, 1.0, 1.9, [], {}, "0", "-1", "1.5")

    def _ejecutar(self, id_habitual, id_persistido, modalidad="Resumen + Factura",
                  tipo_factura="Factura A", accion="cancelar"):
        cliente = [""] * 23
        cliente[0] = 50
        cliente[2] = "Cliente ficticio"
        cliente[10] = "30712345678"
        cliente[11] = "Responsable Inscripto"
        cliente[12] = tipo_factura
        cliente[13] = "EMISOR:2"
        cliente[14] = 999
        cliente[21] = modalidad
        cliente[22] = "Emisor ficticio"
        resumen = Resumen(
            id=10, numero=100, cliente_id=50, emisor_fiscal_id=id_persistido,
            fecha="2026-10-09", total=100, saldo=100,
        )
        cliente_original = deepcopy(cliente)
        resumen_original = deepcopy(vars(resumen))
        frame = SimpleNamespace(
            instancia_id=1, origen_creacion="prueba", cliente_inicial=50,
            selector_cliente=Mock(), clientes_por_nombre={"Cliente ficticio": 50},
            entrada_fecha=Mock(), entrada_vencimiento=Mock(),
            contexto_facturacion_cliente={}, contexto_facturacion_pendiente={},
            ultimo_contexto_facturacion=None, cargar_resumenes=Mock(), on_cambio=Mock(),
            _buscar_emisor_fiscal_por_etiqueta=Mock(return_value=(id_habitual, "Emisor ficticio")),
            _resolver_emisor_facturacion_id=Mock(return_value=(777, "emisor_fiscal_id")),
            _mostrar_vista_previa_resumen_para_factura=Mock(return_value=accion),
            _emitir_factura_arca_desde_resumen=Mock(), mostrar_modal_resumen_generado=Mock(),
        )
        frame.selector_cliente.get.return_value = "Cliente ficticio"
        frame.entrada_fecha.get.return_value = "09/10/2026"
        frame.entrada_vencimiento.get.return_value = "19/10/2026"
        for nombre in (
            "_normalizar_modalidad", "_modalidad_es_solo_resumen",
            "_modalidad_requiere_vista_previa_factura",
        ):
            setattr(frame, nombre, MethodType(getattr(ResumenesFrame, nombre), frame))

        with ExitStack() as pila:
            pila.enter_context(patch("sqlite3.connect", side_effect=AssertionError("Base real prohibida")))
            pila.enter_context(patch("urllib.request.urlopen", side_effect=AssertionError("Red prohibida")))
            pila.enter_context(patch("socket.socket.connect", side_effect=AssertionError("Red prohibida")))
            obtener_cliente = pila.enter_context(patch(
                "views.resumenes.ClienteService.obtener", return_value=cliente,
            ))
            guardar = pila.enter_context(patch(
                "views.resumenes.ResumenService.generar_desde_servicios", return_value=resumen,
            ))
            pdf = pila.enter_context(patch("views.resumenes.ResumenPDF.generar", return_value="resumen_ficticio.pdf"))
            mensajes = pila.enter_context(patch("views.resumenes.messagebox"))
            emitir_servicio = pila.enter_context(patch(
                "views.resumenes.FacturacionService.emitir_desde_resumen",
                side_effect=AssertionError("Facturacion real prohibida"),
            ))
            emitir_arca = pila.enter_context(patch(
                "views.resumenes.FacturacionService.emitir_en_arca",
                side_effect=AssertionError("ARCA real prohibida"),
            ))
            homologacion = pila.enter_context(patch(
                "views.resumenes.HomologacionService.emitir_comprobante_prueba",
                side_effect=AssertionError("Homologacion real prohibida"),
            ))
            diagnostico = io.StringIO()
            with redirect_stdout(diagnostico):
                ResumenesFrame.generar_resumen(frame)

        self.assertEqual(cliente, cliente_original)
        self.assertEqual(vars(resumen), resumen_original)
        emitir_servicio.assert_not_called()
        emitir_arca.assert_not_called()
        homologacion.assert_not_called()
        return SimpleNamespace(
            frame=frame, resumen=resumen, guardar=guardar, pdf=pdf,
            mensajes=mensajes, obtener_cliente=obtener_cliente,
            diagnostico=diagnostico.getvalue(),
        )

    def _verificar_bloqueo(self, id_habitual, id_persistido):
        resultado = self._ejecutar(id_habitual, id_persistido)
        resultado.frame._resolver_emisor_facturacion_id.assert_not_called()
        resultado.frame._mostrar_vista_previa_resumen_para_factura.assert_not_called()
        resultado.frame._emitir_factura_arca_desde_resumen.assert_not_called()
        resultado.pdf.assert_not_called()
        resultado.mensajes.showerror.assert_called_once()
        if id_habitual is None:
            resultado.guardar.assert_not_called()
            self.assertEqual(resultado.mensajes.showerror.call_args.args[0], "Configuración fiscal incompleta")
        else:
            resultado.guardar.assert_called_once_with(
                50, fecha=date(2026, 10, 9), fecha_vencimiento=date(2026, 10, 19),
            )
            self.assertEqual(resultado.mensajes.showerror.call_args.args[0], "Emisor fiscal inconsistente")
            self.assertIn("emisor fiscal incoherente", resultado.diagnostico)

    def _verificar_continuidad(self, resultado):
        resultado.mensajes.showerror.assert_not_called()
        resultado.guardar.assert_called_once()
        resultado.frame._resolver_emisor_facturacion_id.assert_called_once()
        resultado.frame._mostrar_vista_previa_resumen_para_factura.assert_called_once()
        argumentos = resultado.frame._mostrar_vista_previa_resumen_para_factura.call_args.args
        self.assertIs(argumentos[0], resultado.resumen)
        self.assertEqual(argumentos[1]["cliente_id"], 50)
        self.assertEqual(argumentos[1]["emisor_habitual"], "Emisor ficticio")
        self.assertEqual(argumentos[1]["emisor_id"], 999)
        resultado.pdf.assert_not_called()

    def test_ids_fiscales_distintos_bloquean_vista_previa_y_emision(self):
        self._verificar_bloqueo(1, 2)

    def test_ids_coincidentes_continuan_en_modalidades_fiscales(self):
        for modalidad in ("Resumen + Factura", "Resumen+Factura", "Solo Factura"):
            for tipo in ("Factura A", "Factura C"):
                with self.subTest(modalidad=modalidad, tipo=tipo):
                    resultado = self._ejecutar(1, 1, modalidad, tipo)
                    self._verificar_continuidad(resultado)
                    resultado.frame._emitir_factura_arca_desde_resumen.assert_not_called()

    def test_id_habitual_ausente_o_invalido_bloquea(self):
        for valor in self.IDS_INVALIDOS:
            with self.subTest(valor=repr(valor)):
                self._verificar_bloqueo(valor, 1)

    def test_id_persistido_ausente_o_invalido_bloquea(self):
        for valor in self.IDS_INVALIDOS:
            with self.subTest(valor=repr(valor)):
                self._verificar_bloqueo(1, valor)

    def test_ids_enteros_y_cadenas_equivalentes_continuan(self):
        for habitual, persistido in ((1, "1"), ("1", 1), ("001", 1), (1, " 1 "), ("1", "001")):
            with self.subTest(habitual=habitual, persistido=persistido):
                resultado = self._ejecutar(habitual, persistido)
                self._verificar_continuidad(resultado)

    def test_solo_resumen_no_aplica_comparacion_fiscal(self):
        for habitual, persistido in ((1, 2), (None, None), ("abc", "abc")):
            with self.subTest(habitual=habitual, persistido=persistido):
                resultado = self._ejecutar(habitual, persistido, "Solo Resumen")
                resultado.guardar.assert_called_once()
                resultado.mensajes.showerror.assert_not_called()
                resultado.pdf.assert_called_once_with(10)
                resultado.frame.mostrar_modal_resumen_generado.assert_called_once_with("resumen_ficticio.pdf")
                resultado.frame._resolver_emisor_facturacion_id.assert_not_called()
                resultado.frame._mostrar_vista_previa_resumen_para_factura.assert_not_called()
                resultado.frame._emitir_factura_arca_desde_resumen.assert_not_called()

    def test_ids_coincidentes_conservan_delegacion_si_usuario_elige_emitir(self):
        resultado = self._ejecutar(1, 1, accion="emitir")
        self._verificar_continuidad(resultado)
        contexto = resultado.frame._mostrar_vista_previa_resumen_para_factura.call_args.args[1]
        resultado.frame._emitir_factura_arca_desde_resumen.assert_called_once_with(resultado.resumen, contexto)
        self.assertIs(resultado.frame._emitir_factura_arca_desde_resumen.call_args.args[1], contexto)


if __name__ == "__main__":
    unittest.main()