import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from services.emisor_fiscal_service import EmisorFiscalService
from views.cliente_ficha import FichaClienteFrame


class DiagnosticoArcaClienteFichaTest(unittest.TestCase):

    def setUp(self):
        self.dir_temp = tempfile.TemporaryDirectory()
        self.carpeta_facturas = self.dir_temp.name
        
        self.cert_file = tempfile.NamedTemporaryFile(suffix=".pem", delete=False)
        self.cert_file.close()
        self.ruta_cert = self.cert_file.name

        self.key_file = tempfile.NamedTemporaryFile(suffix=".key", delete=False)
        self.key_file.close()
        self.ruta_key = self.key_file.name

        # Tupla devuelta por EmisorFiscalService.obtener:
        # id(0), razon_social(1), nombre_fantasia(2), cuit(3), condicion_iva(4), tipo_factura(5), punto_venta(6), activo(7),
        # observaciones(8), ambiente_arca(9), domicilio(10), ingresos_brutos(11), fecha_inicio_actividades(12),
        # ruta_certificado(13), ruta_clave_privada(14), carpeta_facturas(15), configuracion_arca_completa(16)
        self.emisor_valido_tuple = (
            3,
            "Publicidad & Servicios S.H.",
            "Publicidad & Servicios S.H.",
            "30-71217861-9",
            "Responsable Inscripto",
            "Factura A",
            "00002",
            1,
            "",
            "Homologación",
            "Calle Falsa 123",
            "30-71217861-9",
            "01/01/2012",
            self.ruta_cert,
            self.ruta_key,
            self.carpeta_facturas,
            1,
        )

    def tearDown(self):
        if os.path.exists(self.ruta_cert):
            os.remove(self.ruta_cert)
        if os.path.exists(self.ruta_key):
            os.remove(self.ruta_key)
        self.dir_temp.cleanup()

    @patch.object(EmisorFiscalService, "obtener")
    def test_emisor_configuracion_valida_arca_ok(self, mock_obtener):
        mock_obtener.return_value = self.emisor_valido_tuple
        res = EmisorFiscalService.validar_configuracion_arca(3)
        self.assertTrue(res["completa"])
        self.assertEqual(res["faltantes"], [])
        self.assertEqual(res["errores"], [])

    @patch.object(EmisorFiscalService, "obtener")
    def test_certificado_inexistente_falla(self, mock_obtener):
        emisor_invalido = list(self.emisor_valido_tuple)
        emisor_invalido[13] = "C:/ruta/inexistente/certificado.pem"
        mock_obtener.return_value = emisor_invalido

        res = EmisorFiscalService.validar_configuracion_arca(3)
        self.assertFalse(res["completa"])
        self.assertIn("No existe el archivo del certificado digital.", res["errores"])

    @patch.object(EmisorFiscalService, "obtener")
    def test_clave_inexistente_falla(self, mock_obtener):
        emisor_invalido = list(self.emisor_valido_tuple)
        emisor_invalido[14] = "C:/ruta/inexistente/clave.key"
        mock_obtener.return_value = emisor_invalido

        res = EmisorFiscalService.validar_configuracion_arca(3)
        self.assertFalse(res["completa"])
        self.assertIn("No existe el archivo de la clave privada.", res["errores"])

    @patch.object(EmisorFiscalService, "obtener")
    def test_carpeta_inexistente_falla(self, mock_obtener):
        emisor_invalido = list(self.emisor_valido_tuple)
        emisor_invalido[15] = "C:/ruta/inexistente/carpeta_facturas"
        mock_obtener.return_value = emisor_invalido

        res = EmisorFiscalService.validar_configuracion_arca(3)
        self.assertFalse(res["completa"])
        self.assertIn("No existe la carpeta de facturas.", res["errores"])

    @patch.object(EmisorFiscalService, "validar_configuracion_arca")
    @patch("services.resumen_service.ResumenService.obtener")
    @patch("services.cliente_service.ClienteService.obtener")
    @patch.object(EmisorFiscalService, "obtener")
    def test_cliente_ficha_evaluar_preparacion_independiente_de_indices_manuales(
        self, mock_emisor_obtener, mock_cliente_obtener, mock_resumen_obtener, mock_validar_arca
    ):
        mock_resumen = MagicMock()
        mock_resumen.id = 109
        mock_resumen.numero = 1000075
        mock_resumen.cliente_id = 50
        mock_resumen.total = 1000.0
        mock_resumen.estado_facturacion = "Pendiente"
        mock_resumen_obtener.return_value = mock_resumen

        # cliente_fila: id(0), codigo(1), razon_social(2), ..., cuit(10), iva(11), tipo_factura(12), emisor(13)
        mock_cliente_obtener.return_value = (
            50, "C50", "Cliente Test S.A.", "", "", "", "", "", "", "", "30111111118", "IVA Responsable Inscripto", "Factura A", "EMISOR:3"
        )
        mock_emisor_obtener.return_value = self.emisor_valido_tuple
        mock_validar_arca.return_value = {"completa": True, "faltantes": [], "errores": []}

        frame = MagicMock(spec=FichaClienteFrame)
        frame._resolver_emisor_id_desde_referencia.return_value = 3
        frame._formatear_moneda.side_effect = lambda x: f"${x}"

        evaluacion = FichaClienteFrame._construir_diagnostico_facturacion(frame, resumen_id=109)

        # Verificar que validar_configuracion_arca fue llamado SOLO con emisor_id (o sea, 3) sin rutas ni kwargs
        mock_validar_arca.assert_called_once_with(3)
        self.assertTrue(evaluacion["estado_confirmacion"]["configuracion_arca_validada"])
