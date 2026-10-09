import unittest
from contextlib import ExitStack
from types import MethodType, SimpleNamespace
from unittest.mock import Mock, patch

from views.resumenes import ResumenesFrame


class ModalidadVistaPreviaResumenesTest(unittest.TestCase):
    MODALIDADES_FACTURA = ("Resumen + Factura", "Resumen+Factura", "Solo Factura")
    TIPOS_FACTURA = ("Factura A", "Factura C")

    def _verificar_estado(self, modalidad, tipo_factura, estado, fiscal_ok=True, diferencia=0):
        concepto = SimpleNamespace(
            cantidad=1, importe=100, total=100,
            concepto="Servicio ficticio", descripcion="Prueba aislada",
        )
        resumen = SimpleNamespace(
            id=10, numero=10, cliente_id=50, total=100 - diferencia,
            conceptos=[concepto],
        )
        contexto = {
            "modalidad_comprobante": modalidad,
            "tipo_factura": tipo_factura,
            "emisor_habitual": "EMISOR:3",
        }
        frame = SimpleNamespace(
            FACTURA_A_SERVICIOS_IMPORTE_ES_NETO=ResumenesFrame.FACTURA_A_SERVICIOS_IMPORTE_ES_NETO,
            FACTURA_A_ALICUOTA_PORCENTAJE=ResumenesFrame.FACTURA_A_ALICUOTA_PORCENTAJE,
            formatear_moneda=lambda importe: f"{importe:.2f}",
            winfo_toplevel=Mock(),
            wait_window=Mock(),
        )
        for nombre in (
            "_normalizar_modalidad", "_modalidad_requiere_vista_previa_factura",
            "_armar_items_factura_desde_resumen", "_calcular_datos_fiscales_desde_items",
        ):
            setattr(frame, nombre, MethodType(getattr(ResumenesFrame, nombre), frame))

        with ExitStack() as pila:
            obtener = pila.enter_context(patch(
                "views.resumenes.ResumenService.obtener", return_value=resumen
            ))
            if not fiscal_ok:
                pila.enter_context(patch.object(
                    frame, "_calcular_datos_fiscales_desde_items",
                    return_value={"ok": False, "errores": ["Calculo fiscal invalido simulado"]},
                ))
            widgets = {}
            for nombre in (
                "ctk.CTkToplevel", "ctk.CTkFrame", "ctk.CTkLabel",
                "ctk.CTkButton", "ctk.StringVar", "ttk.Treeview", "ttk.Scrollbar",
            ):
                widgets[nombre] = pila.enter_context(patch("views.resumenes." + nombre))
            ventana = widgets["ctk.CTkToplevel"].return_value
            ventana.winfo_screenwidth.return_value = 1366
            ventana.winfo_screenheight.return_value = 768
            widgets["ctk.StringVar"].return_value.get.return_value = "cancelar"

            accion = ResumenesFrame._mostrar_vista_previa_resumen_para_factura(
                frame, resumen, contexto
            )

            botones_emitir = [
                llamada.kwargs
                for llamada in widgets["ctk.CTkButton"].call_args_list
                if llamada.kwargs.get("text") == "Emitir factura"
            ]
            self.assertEqual(len(botones_emitir), 1)
            self.assertEqual(botones_emitir[0]["state"], estado)
            self.assertEqual(accion, "cancelar")
            obtener.assert_called_once_with(resumen.id)
            frame.wait_window.assert_called_once_with(ventana)

    def test_solo_resumen_deshabilita_emision_con_a_y_c_validas(self):
        for tipo in self.TIPOS_FACTURA:
            with self.subTest(tipo=tipo):
                self._verificar_estado("Solo Resumen", tipo, "disabled")

    def test_modalidades_factura_habilitan_emision_valida(self):
        for modalidad in self.MODALIDADES_FACTURA:
            for tipo in self.TIPOS_FACTURA:
                with self.subTest(modalidad=modalidad, tipo=tipo):
                    self._verificar_estado(modalidad, tipo, "normal")

    def test_modalidades_factura_bloquean_calculo_invalido_o_diferencia(self):
        for modalidad in self.MODALIDADES_FACTURA:
            for tipo in self.TIPOS_FACTURA:
                for fiscal_ok, diferencia in ((False, 0), (True, 0.02), (True, -0.02)):
                    with self.subTest(
                        modalidad=modalidad, tipo=tipo,
                        fiscal_ok=fiscal_ok, diferencia=diferencia,
                    ):
                        self._verificar_estado(
                            modalidad, tipo, "disabled", fiscal_ok, diferencia
                        )


if __name__ == "__main__":
    unittest.main()