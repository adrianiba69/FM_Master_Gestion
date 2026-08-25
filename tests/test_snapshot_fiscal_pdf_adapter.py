"""Tests del adaptador puro snapshot fiscal v1 -> PDF/QR (FASE 5D)."""

import json
import unittest
from decimal import Decimal

from services.arca.qr_fiscal_service import QrFiscalService
from services.arca.snapshot_fiscal_pdf_adapter import (
    MODO_CORRUPTO,
    MODO_LEGACY,
    MODO_SNAPSHOT,
    construir_datos_pdf_desde_snapshot,
    datos_comprobante_desde_snapshot,
    datos_emisor_desde_snapshot,
    datos_qr_desde_snapshot,
    datos_receptor_desde_snapshot,
    resolver_modo_regeneracion,
)
from services.arca.snapshot_fiscal_service import (
    SNAPSHOT_VERSION,
    calcular_hash_snapshot,
    construir_snapshot_fiscal_v1,
    serializar_snapshot_fiscal,
)


def _datos_snapshot_factura_a():
    return {
        "fuente": "cierre_normal",
        "creado_en": "2026-08-23T12:34:56",
        "ambiente": "HOMOLOGACION",
        "emisor": {
            "emisor_id": 1,
            "emisor_fiscal_id": 1,
            "razon_social": "FM Master SRL",
            "nombre_fantasia": "FM Master",
            "cuit": "20111111117",
            "condicion_iva": "Responsable Inscripto",
            "domicilio": "Domicilio fiscal 123",
            "ingresos_brutos": "123456",
            "fecha_inicio_actividades": "2020-01-01",
            "punto_venta_num": 5,
        },
        "receptor": {
            "cliente_id": 10,
            "razon_social": "Cliente SA",
            "documento_visible": "20222222221",
            "condicion_iva": "Responsable Inscripto",
            "domicilio": "Cliente 456 - Localidad",
            "tipo_documento_receptor": 80,
            "documento_receptor": 20222222221,
        },
        "comprobante": {
            "fecha": "2026-08-23",
            "fecha_arca": "20260823",
            "concepto": 1,
            "concepto_descripcion": "Productos",
            "punto_venta_num": 5,
            "tipo_comprobante_num": 1,
            "tipo_comprobante_texto": "Factura A",
            "numero_comprobante_num": 123,
            "numero_textual": "00005-00000123",
            "periodo_servicio_desde": "2026-08-01",
            "periodo_servicio_hasta": "2026-08-31",
            "vencimiento_pago": "2026-09-10",
            "moneda": "PES",
            "cotizacion": Decimal("1"),
        },
        "importes": {
            "total": Decimal("1210"),
            "neto": Decimal("1000"),
            "iva": Decimal("210"),
            "exento": Decimal("0"),
            "no_gravado": Decimal("0"),
            "tributos": Decimal("0"),
        },
        "iva": [
            {
                "id": 5,
                "base_imponible": Decimal("1000"),
                "importe": Decimal("210"),
                "porcentaje": Decimal("21"),
            }
        ],
        "items": [
            {
                "concepto": "Servicio mensual",
                "descripcion": "Publicidad agosto",
                "cantidad": Decimal("1"),
                "precio_unitario": Decimal("1000"),
                "subtotal": Decimal("1000"),
            }
        ],
        "autorizacion": {
            "cae": "12345678901234",
            "vencimiento_cae": "2026-09-02",
            "vencimiento_cae_arca": "20260902",
            "tipo_cod_aut": "E",
            "resultado": "AUTORIZADO",
            "cerrado_en": "2026-08-23T12:34:56",
        },
    }


def _snapshot_factura_a():
    return construir_snapshot_fiscal_v1(**_datos_snapshot_factura_a())


def _snapshot_factura_c():
    datos = _datos_snapshot_factura_a()
    datos["emisor"]["condicion_iva"] = "Monotributo"
    datos["receptor"]["razon_social"] = "Consumidor Final"
    datos["receptor"]["condicion_iva"] = "Consumidor Final"
    datos["receptor"]["documento_visible"] = "0"
    datos["receptor"]["tipo_documento_receptor"] = 99
    datos["receptor"]["documento_receptor"] = 0
    datos["comprobante"]["tipo_comprobante_num"] = 11
    datos["comprobante"]["tipo_comprobante_texto"] = "Factura C"
    datos["comprobante"]["numero_comprobante_num"] = 124
    datos["comprobante"]["numero_textual"] = "00005-00000124"
    datos["importes"]["total"] = Decimal("1000")
    datos["importes"]["iva"] = Decimal("0")
    datos["iva"] = []
    datos["autorizacion"]["cae"] = "12345678901235"
    return construir_snapshot_fiscal_v1(**datos)


class AdaptadorEmisorTest(unittest.TestCase):
    def test_emisor_sale_del_snapshot(self):
        snapshot = _snapshot_factura_a()
        datos_emisor = datos_emisor_desde_snapshot(snapshot)
        self.assertEqual(datos_emisor["razon_social"], "FM Master SRL")
        self.assertEqual(datos_emisor["nombre_fantasia"], "FM Master")
        self.assertEqual(datos_emisor["cuit"], "20111111117")
        self.assertEqual(datos_emisor["condicion_iva"], "Responsable Inscripto")
        self.assertEqual(datos_emisor["domicilio"], "Domicilio fiscal 123")
        self.assertEqual(datos_emisor["ingresos_brutos"], "123456")
        self.assertEqual(datos_emisor["fecha_inicio_actividades"], "20200101")
        self.assertEqual(datos_emisor["punto_venta"], "5")


class AdaptadorReceptorTest(unittest.TestCase):
    def test_receptor_sale_del_snapshot(self):
        snapshot = _snapshot_factura_a()
        datos_receptor = datos_receptor_desde_snapshot(snapshot)
        self.assertEqual(datos_receptor["razon_social"], "Cliente SA")
        self.assertEqual(datos_receptor["cuit"], "20222222221")
        self.assertEqual(datos_receptor["documento"], "20222222221")
        self.assertEqual(datos_receptor["condicion_iva"], "Responsable Inscripto")
        self.assertEqual(datos_receptor["domicilio"], "Cliente 456 - Localidad")


class AdaptadorComprobanteTest(unittest.TestCase):
    def test_comprobante_sale_del_snapshot(self):
        snapshot = _snapshot_factura_a()
        datos_comprobante = datos_comprobante_desde_snapshot(snapshot)
        self.assertEqual(datos_comprobante["tipo"], "Factura A")
        self.assertEqual(datos_comprobante["numero"], 123)
        self.assertEqual(datos_comprobante["numero_comprobante_num"], 123)
        self.assertEqual(datos_comprobante["punto_venta_num"], 5)
        self.assertEqual(datos_comprobante["tipo_comprobante_num"], 1)
        self.assertEqual(datos_comprobante["fecha"], "20260823")
        self.assertEqual(datos_comprobante["periodo_servicio_desde"], "20260801")
        self.assertEqual(datos_comprobante["periodo_servicio_hasta"], "20260831")
        self.assertEqual(datos_comprobante["vencimiento_pago"], "20260910")
        self.assertEqual(datos_comprobante["moneda"], "PES")
        self.assertEqual(datos_comprobante["cae"], "12345678901234")
        self.assertEqual(datos_comprobante["vencimiento_cae"], "20260902")
        self.assertEqual(datos_comprobante["tipo_documento_receptor"], 80)
        self.assertEqual(datos_comprobante["documento_receptor"], 20222222221)

    def test_importes_salen_del_snapshot(self):
        datos_comprobante = datos_comprobante_desde_snapshot(_snapshot_factura_a())
        self.assertEqual(datos_comprobante["importe_neto"], "1000.00")
        self.assertEqual(datos_comprobante["importe_iva"], "210.00")
        self.assertEqual(datos_comprobante["importe_total"], "1210.00")

    def test_iva_sale_del_snapshot_factura_a(self):
        datos_comprobante = datos_comprobante_desde_snapshot(_snapshot_factura_a())
        self.assertEqual(datos_comprobante["alicuota_iva"], "21.00")

    def test_iva_vacio_en_factura_c(self):
        datos_comprobante = datos_comprobante_desde_snapshot(_snapshot_factura_c())
        self.assertEqual(datos_comprobante["alicuota_iva"], "0")
        self.assertEqual(datos_comprobante["importe_iva"], "0.00")

    def test_items_salen_del_snapshot(self):
        datos_comprobante = datos_comprobante_desde_snapshot(_snapshot_factura_a())
        items = datos_comprobante["items"]
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["cantidad"], "1.000000")
        self.assertEqual(items[0]["precio_unitario"], "1000.00")
        self.assertEqual(items[0]["importe"], "1000.00")
        self.assertIn("Publicidad agosto", items[0]["descripcion"])

    def test_ambiente_sale_del_snapshot(self):
        datos_comprobante = datos_comprobante_desde_snapshot(_snapshot_factura_a())
        self.assertEqual(datos_comprobante["ambiente"], "HOMOLOGACION")

        snapshot_produccion = _snapshot_factura_a()
        snapshot_produccion["ambiente"] = "PRODUCCION"
        datos_comprobante_prod = datos_comprobante_desde_snapshot(snapshot_produccion)
        self.assertEqual(datos_comprobante_prod["ambiente"], "PRODUCCION")


class AdaptadorQrTest(unittest.TestCase):
    def test_qr_sale_integramente_del_snapshot(self):
        snapshot = _snapshot_factura_a()
        datos_qr = datos_qr_desde_snapshot(snapshot)
        self.assertEqual(datos_qr["fecha"], "2026-08-23")
        self.assertEqual(datos_qr["cuit_emisor"], 20111111117)
        self.assertEqual(datos_qr["punto_venta_num"], 5)
        self.assertEqual(datos_qr["tipo_comprobante_num"], 1)
        self.assertEqual(datos_qr["numero_comprobante_num"], 123)
        self.assertEqual(datos_qr["importe"], 1210.0)
        self.assertEqual(datos_qr["cae"], "12345678901234")
        self.assertEqual(datos_qr["tipo_documento_receptor"], 80)
        self.assertEqual(datos_qr["numero_documento_receptor"], 20222222221)
        self.assertEqual(datos_qr["moneda"], "PES")
        self.assertEqual(datos_qr["cotizacion"], 1.0)

        servicio_qr = QrFiscalService()
        url, error = servicio_qr.construir_qr_completo(
            ver=datos_qr["ver"],
            fecha=datos_qr["fecha"],
            cuit_emisor=datos_qr["cuit_emisor"],
            punto_venta_num=datos_qr["punto_venta_num"],
            tipo_comprobante_num=datos_qr["tipo_comprobante_num"],
            numero_comprobante_num=datos_qr["numero_comprobante_num"],
            importe=datos_qr["importe"],
            cae=datos_qr["cae"],
            tipo_documento_receptor=datos_qr["tipo_documento_receptor"],
            numero_documento_receptor=datos_qr["numero_documento_receptor"],
            moneda=datos_qr["moneda"],
            cotizacion=datos_qr["cotizacion"],
        )
        self.assertIsNone(error)
        self.assertTrue(url.startswith(QrFiscalService.QR_VERIFICATION_URL))

        payload, error_decode = servicio_qr.decodificar_url_qr(url)
        self.assertIsNone(error_decode)
        self.assertEqual(payload["cuit"], 20111111117)
        self.assertEqual(payload["ptoVta"], 5)
        self.assertEqual(payload["nroCmp"], 123)
        self.assertEqual(payload["codAut"], 12345678901234)


class ConstruirDatosPdfDesdeSnapshotTest(unittest.TestCase):
    def test_devuelve_los_tres_bloques(self):
        datos = construir_datos_pdf_desde_snapshot(_snapshot_factura_a())
        self.assertIn("datos_emisor", datos)
        self.assertIn("datos_receptor", datos)
        self.assertIn("datos_comprobante", datos)


class ResolverModoRegeneracionTest(unittest.TestCase):
    def test_snapshot_null_es_legacy(self):
        decision = resolver_modo_regeneracion(None, None, None)
        self.assertEqual(decision.modo, MODO_LEGACY)

    def test_snapshot_vacio_es_legacy(self):
        decision = resolver_modo_regeneracion("", None, None)
        self.assertEqual(decision.modo, MODO_LEGACY)

    def test_snapshot_valido_es_modo_snapshot(self):
        snapshot = _snapshot_factura_a()
        serializado = serializar_snapshot_fiscal(snapshot)
        hash_calculado = calcular_hash_snapshot(serializado)
        decision = resolver_modo_regeneracion(serializado, SNAPSHOT_VERSION, hash_calculado)
        self.assertEqual(decision.modo, MODO_SNAPSHOT)
        self.assertEqual(decision.snapshot, snapshot)

    def test_json_invalido_es_corrupto(self):
        decision = resolver_modo_regeneracion("{no es json", 1, "a" * 64)
        self.assertEqual(decision.modo, MODO_CORRUPTO)

    def test_version_incorrecta_es_corrupto(self):
        snapshot = _snapshot_factura_a()
        serializado = serializar_snapshot_fiscal(snapshot)
        hash_calculado = calcular_hash_snapshot(serializado)
        decision = resolver_modo_regeneracion(serializado, 99, hash_calculado)
        self.assertEqual(decision.modo, MODO_CORRUPTO)

    def test_version_ausente_es_corrupto(self):
        snapshot = _snapshot_factura_a()
        serializado = serializar_snapshot_fiscal(snapshot)
        hash_calculado = calcular_hash_snapshot(serializado)
        decision = resolver_modo_regeneracion(serializado, None, hash_calculado)
        self.assertEqual(decision.modo, MODO_CORRUPTO)

    def test_hash_ausente_es_corrupto(self):
        snapshot = _snapshot_factura_a()
        serializado = serializar_snapshot_fiscal(snapshot)
        decision = resolver_modo_regeneracion(serializado, SNAPSHOT_VERSION, None)
        self.assertEqual(decision.modo, MODO_CORRUPTO)

    def test_hash_incorrecto_es_corrupto(self):
        snapshot = _snapshot_factura_a()
        serializado = serializar_snapshot_fiscal(snapshot)
        decision = resolver_modo_regeneracion(serializado, SNAPSHOT_VERSION, "f" * 64)
        self.assertEqual(decision.modo, MODO_CORRUPTO)

    def test_snapshot_incompleto_es_corrupto(self):
        snapshot = _snapshot_factura_a()
        del snapshot["items"]
        serializado_incompleto = json.dumps(snapshot, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        hash_incompleto = calcular_hash_snapshot(serializado_incompleto)
        decision = resolver_modo_regeneracion(serializado_incompleto, SNAPSHOT_VERSION, hash_incompleto)
        self.assertEqual(decision.modo, MODO_CORRUPTO)


if __name__ == "__main__":
    unittest.main()
