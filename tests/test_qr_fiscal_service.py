"""
Tests para QR Fiscal Service

Casos A-U según especificación Phase 4:
- Payloads A/B, receptor válido/omitible/inválido
- CAE valid/invalid
- Fechas normalizadas
- Columnas _num
- JSON determinista
- Base64 reversible
- URL final
- ReportLab compatible
- PDF sin QR si falla
- Histórico con receptor NULL
- Regeneración sin usar cliente actual
"""

import unittest
import json
import base64
from decimal import Decimal
from datetime import datetime
from services.arca.qr_fiscal_service import QrFiscalService, QRFiscalError


class QrFiscalPayloadTest(unittest.TestCase):
    """Tests de construcción y validación de payload QR"""

    def setUp(self):
        self.service = QrFiscalService()

    # A: Payload Factura A (Responsable Inscripto - receptor con CUIT)
    def test_payload_factura_a_con_cuit_receptor(self):
        """Factura A: receptor CUIT válido (tipoDocRec=80)"""
        payload = self.service.construir_payload(
            ver=1,
            fecha="20260801",
            cuit_emisor=20111111117,
            punto_venta_num=5,
            tipo_comprobante_num=1,  # Factura A
            numero_comprobante_num=100,
            importe=1000.50,
            cae="12345678901234",
            tipo_documento_receptor=80,  # CUIT
            numero_documento_receptor=20222222221,  # CUIT 11 dígitos
        )
        self.assertEqual(payload["ver"], 1)
        self.assertEqual(payload["tipoCmp"], 1)
        self.assertEqual(payload["tipoDocRec"], 80)
        self.assertEqual(payload["nroDocRec"], 20222222221)
        self.assertIn("tipoDocRec", payload)
        self.assertIn("nroDocRec", payload)

    # B: Payload Factura C (flexible, puede tener o no documento)
    def test_payload_factura_c_sin_documento(self):
        """Factura C: sin documento (tipoDocRec=99, nroDocRec=0)"""
        payload = self.service.construir_payload(
            ver=1,
            fecha="20260801",
            cuit_emisor=20111111117,
            punto_venta_num=5,
            tipo_comprobante_num=11,  # Factura C
            numero_comprobante_num=101,
            importe=500.00,
            cae="12345678901234",
            tipo_documento_receptor=99,  # Sin identificar
            numero_documento_receptor=0,
        )
        self.assertEqual(payload["tipoCmp"], 11)
        self.assertEqual(payload["tipoDocRec"], 99)
        self.assertEqual(payload["nroDocRec"], 0)

    # C: tipoDocRec/nroDocRec presentes y válidos
    def test_payload_receptor_dni_valido(self):
        """Receptor con DNI válido (tipoDocRec=96)"""
        payload = self.service.construir_payload(
            ver=1,
            fecha="20260801",
            cuit_emisor=20111111117,
            punto_venta_num=5,
            tipo_comprobante_num=11,
            numero_comprobante_num=102,
            importe=300.00,
            cae="12345678901234",
            tipo_documento_receptor=96,  # DNI
            numero_documento_receptor=12345678,  # DNI 8 dígitos
        )
        self.assertEqual(payload["tipoDocRec"], 96)
        self.assertEqual(payload["nroDocRec"], 12345678)

    # D: Receptor omitible (None, None -> no incluir en payload)
    def test_payload_receptor_omitible(self):
        """Receptor no incluido en payload si ambos None"""
        payload = self.service.construir_payload(
            ver=1,
            fecha="20260801",
            cuit_emisor=20111111117,
            punto_venta_num=5,
            tipo_comprobante_num=11,
            numero_comprobante_num=103,
            importe=200.00,
            cae="12345678901234",
            tipo_documento_receptor=None,
            numero_documento_receptor=None,
        )
        self.assertNotIn("tipoDocRec", payload)
        self.assertNotIn("nroDocRec", payload)

    # E: Receptor inválido (uno presente, otro no)
    def test_payload_receptor_inconsistente_error(self):
        """Error si tipoDocRec presente pero nroDocRec None"""
        with self.assertRaises(QRFiscalError):
            self.service.construir_payload(
                ver=1,
                fecha="20260801",
                cuit_emisor=20111111117,
                punto_venta_num=5,
                tipo_comprobante_num=11,
                numero_comprobante_num=104,
                importe=150.00,
                cae="12345678901234",
                tipo_documento_receptor=80,  # Presente
                numero_documento_receptor=None,  # Faltante -> ERROR
            )

    # F: CUIT emisor válido
    def test_cuit_emisor_valido(self):
        """CUIT emisor válido (11 dígitos, positivo)"""
        payload = self.service.construir_payload(
            ver=1,
            fecha="20260801",
            cuit_emisor=27369901175,  # CUIT válido
            punto_venta_num=5,
            tipo_comprobante_num=1,
            numero_comprobante_num=105,
            importe=100.00,
            cae="12345678901234",
        )
        self.assertEqual(payload["cuit"], 27369901175)

    # G: Fecha YYYYMMDD -> YYYY-MM-DD
    def test_fecha_normalizacion_yyyymmdd(self):
        """Fecha YYYYMMDD se normaliza a YYYY-MM-DD"""
        payload = self.service.construir_payload(
            ver=1,
            fecha="20260815",  # YYYYMMDD
            cuit_emisor=20111111117,
            punto_venta_num=5,
            tipo_comprobante_num=1,
            numero_comprobante_num=106,
            importe=100.00,
            cae="12345678901234",
        )
        self.assertEqual(payload["fecha"], "2026-08-15")

    # G2: Fecha ya en YYYY-MM-DD se preserva
    def test_fecha_yyyy_mm_dd_preservada(self):
        """Fecha ya en YYYY-MM-DD se preserva"""
        payload = self.service.construir_payload(
            ver=1,
            fecha="2026-08-15",
            cuit_emisor=20111111117,
            punto_venta_num=5,
            tipo_comprobante_num=1,
            numero_comprobante_num=107,
            importe=100.00,
            cae="12345678901234",
        )
        self.assertEqual(payload["fecha"], "2026-08-15")

    # H: Datos desde columnas _num (no parsear numero_factura)
    def test_columnas_num_directas(self):
        """Usar directamente punto_venta_num, tipo_comprobante_num, numero_comprobante_num"""
        payload = self.service.construir_payload(
            ver=1,
            fecha="20260801",
            cuit_emisor=20111111117,
            punto_venta_num=5,
            tipo_comprobante_num=1,
            numero_comprobante_num=200,
            importe=100.00,
            cae="12345678901234",
        )
        self.assertEqual(payload["ptoVta"], 5)
        self.assertEqual(payload["tipoCmp"], 1)
        self.assertEqual(payload["nroCmp"], 200)

    # I: Importe
    def test_importe_redondeo_dos_decimales(self):
        """Importe se redondea a 2 decimales"""
        payload = self.service.construir_payload(
            ver=1,
            fecha="20260801",
            cuit_emisor=20111111117,
            punto_venta_num=5,
            tipo_comprobante_num=1,
            numero_comprobante_num=108,
            importe=1000.556,  # 3 decimales
            cae="12345678901234",
        )
        self.assertEqual(payload["importe"], 1000.56)

    # J: Moneda PES (default)
    def test_moneda_pes_default(self):
        """Moneda default es PES"""
        payload = self.service.construir_payload(
            ver=1,
            fecha="20260801",
            cuit_emisor=20111111117,
            punto_venta_num=5,
            tipo_comprobante_num=1,
            numero_comprobante_num=109,
            importe=100.00,
            cae="12345678901234",
        )
        self.assertEqual(payload["moneda"], "PES")

    # K: Cotización = 1 (default)
    def test_cotizacion_1_default(self):
        """Cotización default es 1"""
        payload = self.service.construir_payload(
            ver=1,
            fecha="20260801",
            cuit_emisor=20111111117,
            punto_venta_num=5,
            tipo_comprobante_num=1,
            numero_comprobante_num=110,
            importe=100.00,
            cae="12345678901234",
        )
        self.assertEqual(payload["ctz"], 1)

    # L: tipoCodAut = "E"
    def test_tipo_cod_aut_e(self):
        """tipoCodAut siempre es 'E' (electrónico)"""
        payload = self.service.construir_payload(
            ver=1,
            fecha="20260801",
            cuit_emisor=20111111117,
            punto_venta_num=5,
            tipo_comprobante_num=1,
            numero_comprobante_num=111,
            importe=100.00,
            cae="12345678901234",
        )
        self.assertEqual(payload["tipoCodAut"], "E")

    # M: CAE válido (14 dígitos numéricos)
    def test_cae_valido_14_digitos(self):
        """CAE válido: 14 dígitos numéricos"""
        cae = "12345678901234"
        payload = self.service.construir_payload(
            ver=1,
            fecha="20260801",
            cuit_emisor=20111111117,
            punto_venta_num=5,
            tipo_comprobante_num=1,
            numero_comprobante_num=112,
            importe=100.00,
            cae=cae,
        )
        self.assertEqual(payload["codAut"], int(cae))

    # N: CAE inválido (no numérico o longitud incorrecta)
    def test_cae_invalido_no_numerico(self):
        """CAE inválido: contiene caracteres no numéricos"""
        with self.assertRaises(QRFiscalError):
            self.service.construir_payload(
                ver=1,
                fecha="20260801",
                cuit_emisor=20111111117,
                punto_venta_num=5,
                tipo_comprobante_num=1,
                numero_comprobante_num=113,
                importe=100.00,
                cae="ABCD678901234",  # No numérico
            )

    def test_cae_invalido_longitud(self):
        """CAE inválido: longitud != 14"""
        with self.assertRaises(QRFiscalError):
            self.service.construir_payload(
                ver=1,
                fecha="20260801",
                cuit_emisor=20111111117,
                punto_venta_num=5,
                tipo_comprobante_num=1,
                numero_comprobante_num=114,
                importe=100.00,
                cae="123456789012",  # 12 dígitos, no 14
            )


class QrFiscalJsonYBase64Test(unittest.TestCase):
    """Tests de serialización JSON y codificación Base64"""

    def setUp(self):
        self.service = QrFiscalService()
        self.payload_base = {
            "ver": 1,
            "fecha": "2026-08-01",
            "cuit": 20111111117,
            "ptoVta": 5,
            "tipoCmp": 1,
            "nroCmp": 100,
            "importe": 1000.50,
            "moneda": "PES",
            "ctz": 1,
            "tipoCodAut": "E",
            "codAut": 12345678901234,
        }

    # O: JSON determinista
    def test_json_determinista_multiple_llamadas(self):
        """JSON es determinista (mismas llamadas, mismo resultado)"""
        payload = self.service.construir_payload(
            ver=1,
            fecha="20260801",
            cuit_emisor=20111111117,
            punto_venta_num=5,
            tipo_comprobante_num=1,
            numero_comprobante_num=115,
            importe=100.00,
            cae="12345678901234",
        )

        json1 = self.service.serializar_json(payload)
        json2 = self.service.serializar_json(payload)
        json3 = self.service.serializar_json(payload)

        self.assertEqual(json1, json2)
        self.assertEqual(json2, json3)

    def test_json_compacto_sin_espacios(self):
        """JSON es compacto (sin espacios innecesarios)"""
        json_str = self.service.serializar_json(self.payload_base)
        # No debe contener ", " (coma-espacio)
        self.assertNotIn(", ", json_str)
        # No debe contener ": " (dos puntos-espacio)
        self.assertNotIn(": ", json_str)

    def test_json_sorted_keys(self):
        """JSON tiene keys ordenadas alfabéticamente"""
        json_str = self.service.serializar_json(self.payload_base)
        parsed = json.loads(json_str)
        keys_orden = list(json.loads(json_str).keys())

        # Verificar que 'citz' no aparece después de 'nroCmp' (order)
        # Es decir, verificar que está ordenado
        expected_order = sorted(self.payload_base.keys())
        self.assertEqual(keys_orden, expected_order)

    # P: Base64 reversible
    def test_base64_reversible(self):
        """Base64 es reversible (encode -> decode devuelve original)"""
        json_str = self.service.serializar_json(self.payload_base)
        base64_encoded = self.service.codificar_base64(json_str)

        # Decodificar manualmente
        decoded_bytes = base64.b64decode(base64_encoded)
        decoded_str = decoded_bytes.decode("utf-8")

        self.assertEqual(json_str, decoded_str)

    def test_base64_utf8_correcto(self):
        """Base64 codifica UTF-8 correctamente"""
        payload_con_unicode = {
            "ver": 1,
            "fecha": "2026-08-01",
            "cuit": 20111111117,
            "ptoVta": 5,
            "tipoCmp": 1,
            "nroCmp": 100,
            "importe": 1000.50,
            "moneda": "PES",
            "ctz": 1,
            "tipoCodAut": "E",
            "codAut": 12345678901234,
            "razonSocial": "Empresa Ejemplo",  # Potencial UTF-8
        }
        json_str = self.service.serializar_json(payload_con_unicode)
        base64_str = self.service.codificar_base64(json_str)

        # Decodificar
        decoded_bytes = base64.b64decode(base64_str)
        decoded_str = decoded_bytes.decode("utf-8")
        decoded_payload = json.loads(decoded_str)

        self.assertEqual(payload_con_unicode["razonSocial"], decoded_payload["razonSocial"])


class QrFiscalUrlTest(unittest.TestCase):
    """Tests de construcción de URL QR"""

    def setUp(self):
        self.service = QrFiscalService()

    # Q: URL final
    def test_url_final_formato(self):
        """URL final tiene formato correcto"""
        base64_payload = "eyJjb2RBdXQiOjEyMzQ1Njc4OTAxMjM0fQ=="  # Dummy
        url = self.service.construir_url(base64_payload)

        self.assertTrue(url.startswith("https://www.arca.gob.ar/fe/qr/?p="))
        self.assertIn("?p=", url)
        self.assertEqual(url.split("?p=")[1], base64_payload)

    def test_url_oficial_arca_vigente(self):
        """URL usa dominio oficial ARCA vigente"""
        base64_payload = "test"
        url = self.service.construir_url(base64_payload)

        self.assertIn("https://www.arca.gob.ar/fe/qr/?p=", url)
        self.assertNotIn("https://www.afip.gob.ar/fe/qr", url)
        self.assertNotIn("http://", url)  # Debe ser HTTPS

    def test_url_oficial_arca_decodifica_base64_y_json(self):
        """La URL oficial permite decodificar el Base64 posterior a ?p=."""
        payload = {
            "ver": 1,
            "fecha": "2026-08-01",
            "cuit": 20111111117,
            "ptoVta": 5,
            "tipoCmp": 1,
            "nroCmp": 100,
            "importe": 1000.50,
            "moneda": "PES",
            "ctz": 1,
            "tipoCodAut": "E",
            "codAut": 12345678901234,
        }
        json_str = self.service.serializar_json(payload)
        base64_payload = self.service.codificar_base64(json_str)
        url = self.service.construir_url(base64_payload)

        self.assertTrue(url.startswith("https://www.arca.gob.ar/fe/qr/?p="))
        decoded_json = base64.b64decode(url.split("?p=", 1)[1]).decode("utf-8")
        self.assertEqual(json.loads(decoded_json), payload)


class QrFiscalCompleteFlowTest(unittest.TestCase):
    """Tests del flujo completo: construir_qr_completo"""

    def setUp(self):
        self.service = QrFiscalService()

    # R: QR completamente construible
    def test_qr_completo_flujo_exitoso(self):
        """QR construido exitosamente de punta a punta"""
        url_qr, error = self.service.construir_qr_completo(
            ver=1,
            fecha="20260801",
            cuit_emisor=20111111117,
            punto_venta_num=5,
            tipo_comprobante_num=1,
            numero_comprobante_num=116,
            importe=1000.50,
            cae="12345678901234",
            tipo_documento_receptor=80,
            numero_documento_receptor=20222222221,
        )
        self.assertIsNotNone(url_qr)
        self.assertIsNone(error)
        self.assertTrue(url_qr.startswith("https://www.arca.gob.ar/fe/qr/?p="))

    # S: PDF continúa si QR falla (fail-safe)
    def test_qr_construir_con_error_retorna_none_no_exception(self):
        """Si QR falla, retorna (None, error_msg) sin levantar excepción"""
        # CAE inválido
        url_qr, error = self.service.construir_qr_completo(
            ver=1,
            fecha="20260801",
            cuit_emisor=20111111117,
            punto_venta_num=5,
            tipo_comprobante_num=1,
            numero_comprobante_num=117,
            importe=100.00,
            cae="INVALIDO",  # No numérico
        )
        self.assertIsNone(url_qr)
        self.assertIsNotNone(error)
        self.assertIn("cae", error.lower())

    # T: Histórico con receptor NULL
    def test_qr_historico_sin_receptor(self):
        """Histórico sin receptor (NULL): QR omite tipoDocRec/nroDocRec"""
        url_qr, error = self.service.construir_qr_completo(
            ver=1,
            fecha="20260801",
            cuit_emisor=20111111117,
            punto_venta_num=5,
            tipo_comprobante_num=11,
            numero_comprobante_num=118,
            importe=500.00,
            cae="12345678901234",
            tipo_documento_receptor=None,
            numero_documento_receptor=None,
        )
        self.assertIsNotNone(url_qr)
        self.assertIsNone(error)

        # Decodificar y verificar que NO tiene tipoDocRec/nroDocRec
        payload, decode_error = self.service.decodificar_url_qr(url_qr)
        self.assertIsNone(decode_error)
        self.assertNotIn("tipoDocRec", payload)
        self.assertNotIn("nroDocRec", payload)

    # U: Regeneración no usa cliente actual
    def test_qr_regeneracion_usa_valores_persistidos(self):
        """Regeneración usa valores persistidos, no recalcula desde cliente"""
        # Simular valores persistidos de una factura antigua
        persistidos = {
            "fecha": "20260701",
            "punto_venta_num": 5,
            "tipo_comprobante_num": 1,
            "numero_comprobante_num": 50,
            "importe": 5000.00,
            "cae": "12345678901234",
            "tipo_documento_receptor": 80,
            "numero_documento_receptor": 20222222221,
        }

        # Generar QR con persistidos
        url_qr, error = self.service.construir_qr_completo(
            ver=1,
            fecha=persistidos["fecha"],
            cuit_emisor=20111111117,
            punto_venta_num=persistidos["punto_venta_num"],
            tipo_comprobante_num=persistidos["tipo_comprobante_num"],
            numero_comprobante_num=persistidos["numero_comprobante_num"],
            importe=persistidos["importe"],
            cae=persistidos["cae"],
            tipo_documento_receptor=persistidos["tipo_documento_receptor"],
            numero_documento_receptor=persistidos["numero_documento_receptor"],
        )

        self.assertIsNotNone(url_qr)
        self.assertIsNone(error)

        # Decodificar y verificar que NO cambió los valores
        payload, decode_error = self.service.decodificar_url_qr(url_qr)
        self.assertIsNone(decode_error)
        self.assertEqual(payload["fecha"], "2026-07-01")  # NORMALIZADO
        self.assertEqual(payload["nroCmp"], 50)
        self.assertEqual(
            payload["nroDocRec"], 20222222221
        )  # Mismo, no recalculado


class QrFiscalValidacionTest(unittest.TestCase):
    """Tests de validación de payload"""

    def setUp(self):
        self.service = QrFiscalService()
        self.payload_valido = {
            "ver": 1,
            "fecha": "2026-08-01",
            "cuit": 20111111117,
            "ptoVta": 5,
            "tipoCmp": 1,
            "nroCmp": 100,
            "importe": 1000.50,
            "moneda": "PES",
            "ctz": 1,
            "tipoCodAut": "E",
            "codAut": 12345678901234,
        }

    def test_validacion_payload_valido(self):
        """Payload válido pasa validación"""
        valido, error = self.service.validar_payload(self.payload_valido)
        self.assertTrue(valido)
        self.assertIsNone(error)

    def test_validacion_campo_faltante(self):
        """Payload con campo faltante falla validación"""
        payload_incompleto = self.payload_valido.copy()
        del payload_incompleto["cuit"]

        valido, error = self.service.validar_payload(payload_incompleto)
        self.assertFalse(valido)
        self.assertIn("cuit", error)

    def test_validacion_receptor_inconsistente(self):
        """Payload con receptor inconsistente falla validación"""
        payload = self.payload_valido.copy()
        payload["tipoDocRec"] = 80
        # Falta nroDocRec

        valido, error = self.service.validar_payload(payload)
        self.assertFalse(valido)
        self.assertIn("ambos", error.lower())


class QrFiscalDecodificacionTest(unittest.TestCase):
    """Tests de decodificación/reversibilidad"""

    def setUp(self):
        self.service = QrFiscalService()

    def test_qr_url_decodificable(self):
        """URL QR construida es decodificable"""
        url_qr, error = self.service.construir_qr_completo(
            ver=1,
            fecha="20260801",
            cuit_emisor=20111111117,
            punto_venta_num=5,
            tipo_comprobante_num=1,
            numero_comprobante_num=119,
            importe=1000.00,
            cae="12345678901234",
        )

        self.assertIsNotNone(url_qr)
        payload, decode_error = self.service.decodificar_url_qr(url_qr)
        self.assertIsNone(decode_error)
        self.assertEqual(payload["ver"], 1)
        self.assertEqual(payload["fecha"], "2026-08-01")
        self.assertEqual(payload["cuit"], 20111111117)


if __name__ == "__main__":
    unittest.main()
