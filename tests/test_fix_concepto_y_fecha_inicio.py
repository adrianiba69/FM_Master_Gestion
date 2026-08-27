import unittest
from unittest.mock import MagicMock, patch

from services.arca.snapshot_fiscal_pdf_adapter import datos_comprobante_desde_snapshot
from services.facturacion_service import FacturacionService


class FixConceptoYFechaInicioTest(unittest.TestCase):

    def test_normalizacion_fecha_inicio_actividades_dd_mm_yyyy(self):
        self.assertEqual(FacturacionService._a_fecha_iso_snapshot("01/01/2012"), "2012-01-01")
        self.assertEqual(FacturacionService._a_fecha_iso_snapshot("04/01/1997"), "1997-01-04")

    def test_normalizacion_fecha_inicio_actividades_formatos_existentes(self):
        self.assertEqual(FacturacionService._a_fecha_iso_snapshot("2012-01-01"), "2012-01-01")
        self.assertEqual(FacturacionService._a_fecha_iso_snapshot("20120101"), "2012-01-01")

    def test_normalizacion_fecha_inicio_actividades_valores_vacios_e_invalidos(self):
        self.assertIsNone(FacturacionService._a_fecha_iso_snapshot(""))
        self.assertIsNone(FacturacionService._a_fecha_iso_snapshot(None))
        self.assertIsNone(FacturacionService._a_fecha_iso_snapshot("invalido"))
        self.assertIsNone(FacturacionService._a_fecha_iso_snapshot("12345"))

    def test_concepto_uno_mas_descripcion_productos_produce_uno_menos_productos(self):
        snapshot = {
            "comprobante": {
                "concepto": 1,
                "concepto_descripcion": "Productos",
            }
        }
        datos = datos_comprobante_desde_snapshot(snapshot)
        self.assertEqual(datos["concepto"], "1 - Productos")

    def test_adaptador_no_duplica_concepto_si_ya_venia_con_prefijo(self):
        snapshot = {
            "comprobante": {
                "concepto": 1,
                "concepto_descripcion": "1 - Productos",
            }
        }
        datos = datos_comprobante_desde_snapshot(snapshot)
        self.assertEqual(datos["concepto"], "1 - Productos")
        self.assertNotEqual(datos["concepto"], "1 - 1 - Productos")

    def test_snapshot_nuevo_congela_fecha_inicio_actividades_y_concepto_correctamente(self):
        emisor_fiscal = (
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
            "EL Indio N° 1048",
            "30-71217861-9",
            "01/01/2012",
        )
        cliente = (50, "C50", "Cliente Test SA", "", "", "", "", "", "", "", "20263858884")

        resultado = FacturacionService._construir_snapshot_fiscal_cierre_normal(
            emisor_fiscal=emisor_fiscal,
            emisor_facturacion_id=3,
            cuit_emisor_normalizado="30712178619",
            punto_venta_num=2,
            cliente=cliente,
            condicion_iva="Responsable Inscripto",
            documento_normalizado="20263858884",
            tipo_documento=80,
            documento_receptor=20263858884,
            tipo_comprobante=1,
            tipo_factura_normalizado="Factura A",
            numero_comprobante=8,
            numero_factura="00002-00000008",
            fecha_comprobante="20260827",
            periodo_desde="2026-08-01",
            periodo_hasta="2026-08-10",
            vencimiento_pago_arca="2026-09-01",
            moneda="PES",
            cotizacion=1,
            neto_factura=41322.31,
            importe_iva_factura=8677.69,
            alicuota_iva=21.0,
            total_factura_fiscal=50000.0,
            importe_exento_factura=0,
            importe_tot_conc=0,
            importe_tributos=0,
            alicuotas_iva=[{"id": 5, "base_imponible": 41322.31, "importe": 8677.69}],
            items_factura=[{"descripcion": "PUBLICIDAD ROTATIVA", "cantidad": 1, "precio_unitario": 41322.31, "importe": 41322.31}],
            cae="86340815420864",
            vencimiento_cae="20260906",
            ambiente_normalizado="Homologación",
        )

        self.assertTrue(resultado["ok"])
        snapshot = resultado["snapshot"]

        self.assertEqual(snapshot["emisor"]["fecha_inicio_actividades"], "2012-01-01")
        self.assertEqual(snapshot["comprobante"]["concepto"], 1)
        self.assertEqual(snapshot["comprobante"]["concepto_descripcion"], "Productos")

        datos_pdf = datos_comprobante_desde_snapshot(snapshot)
        self.assertEqual(datos_pdf["concepto"], "1 - Productos")
        self.assertNotEqual(datos_pdf["concepto"], "1 - 1 - Productos")


if __name__ == "__main__":
    unittest.main()
