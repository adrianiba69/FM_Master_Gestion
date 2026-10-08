import unittest
from types import SimpleNamespace
from unittest.mock import patch

from views.resumenes import ResumenesFrame


class ContextoFacturacionResumenesTest(unittest.TestCase):
    def setUp(self):
        self.cliente_id = 50
        self.frame = SimpleNamespace(contexto_facturacion_cliente={})

    @patch("views.resumenes.ClienteService.obtener")
    def test_contexto_existente_se_devuelve_sin_cambios(self, obtener_cliente):
        contexto = {
            "cliente_id": self.cliente_id,
            "modalidad_comprobante": "Resumen + Factura",
            "tipo_factura": "Factura A",
            "dato_adicional": "conservar",
        }
        self.frame.contexto_facturacion_cliente[self.cliente_id] = contexto
        original = dict(contexto)

        resultado = ResumenesFrame._obtener_contexto_facturacion(
            self.frame, self.cliente_id
        )

        self.assertIs(resultado, contexto)
        self.assertEqual(resultado, original)
        obtener_cliente.assert_not_called()

    @patch("views.resumenes.ClienteService.obtener")
    def test_cliente_existente_reconstruye_y_cachea_contexto(self, obtener_cliente):
        fila = [None] * 23
        fila[0] = self.cliente_id
        fila[11] = "Responsable Inscripto"
        fila[12] = "Factura A"
        fila[14] = 3
        fila[21] = "Resumen + Factura"
        fila[22] = "EMISOR:3"
        obtener_cliente.return_value = tuple(fila)

        resultado = ResumenesFrame._obtener_contexto_facturacion(
            self.frame, self.cliente_id
        )

        self.assertEqual(resultado, {
            "cliente_id": self.cliente_id,
            "modalidad_comprobante": "Resumen + Factura",
            "emisor_habitual": "EMISOR:3",
            "tipo_factura": "Factura A",
            "condicion_iva": "Responsable Inscripto",
            "emisor_id": 3,
        })
        self.assertIs(self.frame.contexto_facturacion_cliente[self.cliente_id], resultado)
        obtener_cliente.assert_called_once_with(self.cliente_id)

    @patch("views.resumenes.ClienteService.obtener", return_value=None)
    def test_cliente_inexistente_devuelve_valores_conservadores(self, obtener_cliente):
        resultado = ResumenesFrame._obtener_contexto_facturacion(
            self.frame, self.cliente_id
        )

        self.assertEqual(resultado, {
            "cliente_id": self.cliente_id,
            "modalidad_comprobante": "Solo Resumen",
            "emisor_habitual": "",
            "tipo_factura": "No factura",
            "condicion_iva": "",
            "emisor_id": None,
        })
        self.assertEqual(self.frame.contexto_facturacion_cliente, {})
        obtener_cliente.assert_called_once_with(self.cliente_id)


if __name__ == "__main__":
    unittest.main()