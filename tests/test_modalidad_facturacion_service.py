import unittest
from unittest.mock import patch

from services.facturacion_service import FacturacionService


class ModalidadFacturacionServiceTest(unittest.TestCase):
    def setUp(self):
        parche_resumen = patch(
            "services.facturacion_service.ResumenService.obtener", return_value=None
        )
        self.obtener_resumen = parche_resumen.start()
        self.addCleanup(parche_resumen.stop)
        parche_emision = patch.object(
            FacturacionService, "emitir_en_arca",
            side_effect=AssertionError("Emision ARCA prohibida en esta prueba"),
        )
        self.emitir_en_arca = parche_emision.start()
        self.addCleanup(parche_emision.stop)
        parche_homologacion = patch(
            "services.facturacion_service.HomologacionService.emitir_comprobante_prueba",
            side_effect=AssertionError("Homologacion prohibida en esta prueba"),
        )
        self.emitir_comprobante = parche_homologacion.start()
        self.addCleanup(parche_homologacion.stop)

    def _verificar_rechazo(self, contexto):
        resultado = FacturacionService.emitir_desde_resumen(10, contexto)

        self.assertFalse(resultado["ok"])
        self.assertEqual(resultado["etapa"], "modalidad_comprobante")
        self.assertEqual(resultado["errores"], ["modalidad_no_permite_facturar"])
        self.assertEqual(
            resultado["mensaje"],
            "La modalidad de comprobante no permite emitir una factura.",
        )
        self.assertEqual(resultado["resumen_id"], 10)
        self.assertIsNone(resultado["factura_id"])
        self.obtener_resumen.assert_not_called()
        self.emitir_en_arca.assert_not_called()
        self.emitir_comprobante.assert_not_called()

    def test_solo_resumen_rechazado_con_tipo_a_y_c(self):
        for tipo in ("Factura A", "Factura C"):
            with self.subTest(tipo=tipo):
                self._verificar_rechazo({
                    "modalidad_comprobante": "Solo Resumen",
                    "tipo_factura": tipo,
                    "condicion_iva": "Responsable Inscripto",
                })

    def test_modalidad_desconocida_vacia_o_ausente_rechazada(self):
        for tipo in ("Factura A", "Factura C"):
            datos = {"tipo_factura": tipo, "condicion_iva": "Responsable Inscripto"}
            casos = [
                ("desconocida", {**datos, "modalidad_comprobante": "Otra modalidad"}),
                ("vacia", {**datos, "modalidad_comprobante": ""}),
                ("espacios", {**datos, "modalidad_comprobante": " \t "}),
                ("valor_none", {**datos, "modalidad_comprobante": None}),
                ("ausente", dict(datos)),
                ("contexto_none", None),
            ]
            for nombre, contexto in casos:
                with self.subTest(tipo=tipo, caso=nombre):
                    self._verificar_rechazo(contexto)

    def test_modalidades_validas_superan_validacion_temprana(self):
        for modalidad in (
            "Resumen + Factura", "Resumen+Factura", "Solo Factura",
            "RESUMEN + FACTURA", "RESUMEN+FACTURA", "SOLO FACTURA",
            "  resumen   +   factura  ", "  resumen+factura  ", "  solo \t factura  ",
        ):
            with self.subTest(modalidad=modalidad):
                self.obtener_resumen.reset_mock()
                resultado = FacturacionService.emitir_desde_resumen(10, {
                    "modalidad_comprobante": modalidad,
                    "tipo_factura": "Factura A",
                    "condicion_iva": "Responsable Inscripto",
                })

                self.obtener_resumen.assert_called_once_with(10)
                self.assertFalse(resultado["ok"])
                self.assertEqual(resultado["etapa"], "resumen_no_encontrado")
                self.assertEqual(resultado["errores"], [])
                self.emitir_en_arca.assert_not_called()
                self.emitir_comprobante.assert_not_called()


if __name__ == "__main__":
    unittest.main()