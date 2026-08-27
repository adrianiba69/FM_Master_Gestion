import unittest
from unittest.mock import MagicMock, patch

from services.emisor_fiscal_service import EmisorFiscalService
from services.facturacion_service import FacturacionService
from views.cliente_ficha import FichaClienteFrame


class EmisionFacturaDesdeClienteFichaTest(unittest.TestCase):

    def setUp(self):
        self.modal_mock = MagicMock()
        self.frame = MagicMock(spec=FichaClienteFrame)

        self.resumen_fake = MagicMock()
        self.resumen_fake.id = 109
        self.resumen_fake.numero = 1000075
        self.resumen_fake.cliente_id = 50
        self.resumen_fake.total = 41322.31
        self.resumen_fake.estado_facturacion = "Pendiente"
        self.resumen_fake.fecha_vencimiento = "2026-09-01"

        # cliente_fila: id(0), codigo(1), razon_social(2), ..., cuit(10), iva(11), tipo_factura(12), emisor(13), modalidad(14)
        self.cliente_factura_a = (
            50, "C050", "IBARRONDO LUIS ANGEL", "", "", "", "", "", "", "", "20263858884", "Responsable Inscripto", "Factura A", "EMISOR:3", "Resumen + Factura"
        )
        self.cliente_factura_c = (
            50, "C050", "IBARRONDO LUIS ANGEL", "", "", "", "", "", "", "", "20263858884", "Monotributo", "Factura C", "EMISOR:1", "Resumen + Factura"
        )
        self.cliente_factura_invalida = (
            50, "C050", "IBARRONDO LUIS ANGEL", "", "", "", "", "", "", "", "20263858884", "Exento", "Factura B", "EMISOR:1", "Resumen + Factura"
        )

        self.emisor_sh = (
            3,
            "Ibarrondo Adrian Oscar e Ibarrondo Luis Angel S.H.",
            "Publicidad & Servicios S.H.",
            "30-71217861-9",
            "Responsable Inscripto",
            "Factura A",
            "00002",
            1,
            "",
            "Homologación",
            "C:/cert.pem",
            "C:/key.pem",
            "C:/facturas",
            1,
        )

        self.diagnostico_base = {
            "detalle": {
                "resumen_id": 109,
                "emisor_id": 3,
            }
        }

    @patch("views.cliente_ficha.messagebox")
    @patch("services.resumen_service.ResumenService.obtener")
    @patch("services.cliente_service.ClienteService.obtener")
    @patch("services.emisor_fiscal_service.EmisorFiscalService.obtener")
    @patch.object(FacturacionService, "emitir_desde_resumen")
    def test_factura_a_permitida_y_delega_en_facturacion_service(
        self, mock_emitir, mock_emisor, mock_cliente, mock_resumen, mock_msg
    ):
        mock_resumen.return_value = self.resumen_fake
        mock_cliente.return_value = self.cliente_factura_a
        mock_emisor.return_value = self.emisor_sh
        mock_emitir.return_value = {
            "ok": True,
            "etapa": "ok",
            "numero_factura": "00002-00000008",
            "cae": "12345678901234",
            "vencimiento_cae": "2026-09-10",
            "ruta_pdf": "",
            "datos_modal": {"codigo_factura": "00002-00000008"},
        }

        FichaClienteFrame._emitir_factura_desde_confirmacion(
            self.frame, self.modal_mock, self.diagnostico_base
        )

        mock_emitir.assert_called_once_with(
            resumen_id=109,
            contexto={
                "tipo_factura": "Factura A",
                "condicion_iva": "Responsable Inscripto",
                "emisor_habitual": "Publicidad & Servicios S.H.",
                "modalidad_comprobante": "Resumen + Factura",
            },
        )
        self.modal_mock.destroy.assert_called_once()
        mock_msg.showinfo.assert_called_once()

    @patch("views.cliente_ficha.messagebox")
    @patch("services.resumen_service.ResumenService.obtener")
    @patch("services.cliente_service.ClienteService.obtener")
    @patch("services.emisor_fiscal_service.EmisorFiscalService.obtener")
    @patch.object(FacturacionService, "emitir_desde_resumen")
    def test_factura_c_permitida_y_delega_en_mismo_servicio(
        self, mock_emitir, mock_emisor, mock_cliente, mock_resumen, mock_msg
    ):
        mock_resumen.return_value = self.resumen_fake
        mock_cliente.return_value = self.cliente_factura_c
        mock_emisor.return_value = self.emisor_sh
        mock_emitir.return_value = {
            "ok": True,
            "etapa": "ok",
            "numero_factura": "00002-00000015",
            "cae": "12345678901234",
            "vencimiento_cae": "2026-09-10",
            "ruta_pdf": "",
            "datos_modal": {"codigo_factura": "00002-00000015"},
        }

        FichaClienteFrame._emitir_factura_desde_confirmacion(
            self.frame, self.modal_mock, self.diagnostico_base
        )

        mock_emitir.assert_called_once_with(
            resumen_id=109,
            contexto={
                "tipo_factura": "Factura C",
                "condicion_iva": "Monotributo",
                "emisor_habitual": "Publicidad & Servicios S.H.",
                "modalidad_comprobante": "Resumen + Factura",
            },
        )
        self.modal_mock.destroy.assert_called_once()

    @patch("views.cliente_ficha.messagebox")
    @patch("services.resumen_service.ResumenService.obtener")
    @patch("services.cliente_service.ClienteService.obtener")
    @patch("services.emisor_fiscal_service.EmisorFiscalService.obtener")
    @patch.object(FacturacionService, "emitir_desde_resumen")
    def test_tipo_distinto_de_a_o_c_bloqueado(
        self, mock_emitir, mock_emisor, mock_cliente, mock_resumen, mock_msg
    ):
        mock_resumen.return_value = self.resumen_fake
        mock_cliente.return_value = self.cliente_factura_invalida
        mock_emisor.return_value = self.emisor_sh

        FichaClienteFrame._emitir_factura_desde_confirmacion(
            self.frame, self.modal_mock, self.diagnostico_base
        )

        mock_emitir.assert_not_called()
        mock_msg.showerror.assert_called_once()
        self.assertIn("solo Factura A / Factura C", mock_msg.showerror.call_args[0][1])

    @patch("views.cliente_ficha.messagebox")
    @patch("services.resumen_service.ResumenService.obtener")
    @patch("services.cliente_service.ClienteService.obtener")
    @patch("services.emisor_fiscal_service.EmisorFiscalService.obtener")
    @patch.object(FacturacionService, "emitir_desde_resumen")
    def test_error_en_facturacion_service_no_reintenta(
        self, mock_emitir, mock_emisor, mock_cliente, mock_resumen, mock_msg
    ):
        mock_resumen.return_value = self.resumen_fake
        mock_cliente.return_value = self.cliente_factura_a
        mock_emisor.return_value = self.emisor_sh
        mock_emitir.return_value = {
            "ok": False,
            "etapa": "arca",
            "mensaje": "Error en ARCA",
            "tipo_mensaje": "error",
            "detalle_arca": {"errores": ["Comprobante duplicado"]},
        }

        FichaClienteFrame._emitir_factura_desde_confirmacion(
            self.frame, self.modal_mock, self.diagnostico_base
        )

        self.assertEqual(mock_emitir.call_count, 1)
        mock_msg.showerror.assert_called_once()

    @patch("views.cliente_ficha.messagebox")
    @patch("services.resumen_service.ResumenService.obtener")
    @patch("services.cliente_service.ClienteService.obtener")
    @patch("services.emisor_fiscal_service.EmisorFiscalService.obtener")
    @patch.object(FacturacionService, "emitir_desde_resumen")
    def test_vista_no_calcula_iva_y_no_fuerza_tipo_11(
        self, mock_emitir, mock_emisor, mock_cliente, mock_resumen, mock_msg
    ):
        mock_resumen.return_value = self.resumen_fake
        mock_cliente.return_value = self.cliente_factura_a
        mock_emisor.return_value = self.emisor_sh
        mock_emitir.return_value = {"ok": True, "etapa": "ok", "numero_factura": "00002-00000008"}

        FichaClienteFrame._emitir_factura_desde_confirmacion(
            self.frame, self.modal_mock, self.diagnostico_base
        )

        call_kwargs = mock_emitir.call_args[1]
        self.assertNotIn("importe_iva", call_kwargs)
        self.assertNotIn("tipo_comprobante", call_kwargs)

    def test_calculo_fiscal_facturacion_service_para_resumen_109(self):
        resumen_mock = MagicMock()
        resumen_mock.id = 109
        concepto_mock = MagicMock()
        concepto_mock.cantidad = 1.0
        concepto_mock.importe = 41322.31
        concepto_mock.total = 41322.31
        resumen_mock.conceptos = [concepto_mock]
        resumen_mock.tipo_factura = "Factura A"

        with patch("services.resumen_service.ResumenService.obtener", return_value=resumen_mock):
            calc = FacturacionService.calcular_importes_fiscales(109, tipo_factura="Factura A")
            self.assertTrue(calc["ok"])
            self.assertEqual(calc["neto_factura"], 41322.31)
            self.assertEqual(calc["importe_iva_factura"], 8677.69)
            self.assertEqual(calc["total_factura_fiscal"], 50000.00)
            self.assertEqual(calc["tipo_comprobante"], 1)
