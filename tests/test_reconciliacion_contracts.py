import unittest
from decimal import Decimal

from services.arca.reconciliacion_contracts import (
    ResultadoReconciliacion,
    SnapshotFiscalEsperado,
    comparar_snapshot_con_comprobante,
)


class ReconciliacionContractsTest(unittest.TestCase):

    def setUp(self):
        self.snapshot = SnapshotFiscalEsperado(
            resumen_id=10,
            cliente_id=20,
            emisor_fiscal_id=30,
            emisor_id=40,
            cuit_emisor="20206871629",
            punto_venta=5,
            tipo_comprobante=11,
            numero_planificado=123,
            fecha_comprobante="20260815",
            concepto=1,
            tipo_documento=80,
            documento_receptor=30712345678,
            condicion_iva_receptor_id=5,
            importe_total=Decimal("12100.00"),
            importe_neto=Decimal("12100.00"),
            importe_iva=Decimal("0.00"),
            importe_exento=Decimal("0.00"),
            importe_no_gravado=Decimal("0.00"),
            importe_tributos=Decimal("0.00"),
            moneda="PES",
            cotizacion=Decimal("1.00"),
        )
        self.comprobante = {
            "resultado": "A",
            "cuit_emisor": "20206871629",
            "punto_venta": 5,
            "tipo_comprobante": 11,
            "numero_comprobante": 123,
            "fecha_comprobante": "2026-08-15",
            "doc_tipo": 80,
            "doc_nro": 30712345678,
            "importe_total": "12100.00",
            "importe_neto": 12100.0,
            "importe_iva": 0,
            "moneda": "PES",
            "cotizacion": "1.000",
            "condicion_iva_receptor_id": 5,
            "cae": "71345678901234",
            "vencimiento_cae": "20260825",
        }

    def test_coincidencia_completa(self):
        comparacion = comparar_snapshot_con_comprobante(self.snapshot, self.comprobante)
        self.assertEqual(comparacion.resultado, ResultadoReconciliacion.AUTORIZADO)
        self.assertEqual(comparacion.diferencias, ())

    def test_importe_diferente(self):
        self.comprobante["importe_total"] = "12000.00"
        comparacion = comparar_snapshot_con_comprobante(self.snapshot, self.comprobante)
        self.assertEqual(comparacion.resultado, ResultadoReconciliacion.CONFLICTO)
        self.assertTrue(any(diferencia.campo == "importe_total" for diferencia in comparacion.diferencias))

    def test_receptor_diferente(self):
        self.comprobante["doc_nro"] = 20123456789
        comparacion = comparar_snapshot_con_comprobante(self.snapshot, self.comprobante)
        self.assertEqual(comparacion.resultado, ResultadoReconciliacion.CONFLICTO)
        self.assertTrue(any(diferencia.campo == "documento_receptor" for diferencia in comparacion.diferencias))

    def test_numero_diferente(self):
        self.comprobante["numero_comprobante"] = 124
        comparacion = comparar_snapshot_con_comprobante(self.snapshot, self.comprobante)
        self.assertEqual(comparacion.resultado, ResultadoReconciliacion.CONFLICTO)
        self.assertTrue(any(diferencia.campo == "numero_comprobante" for diferencia in comparacion.diferencias))

    def test_fecha_diferente(self):
        self.comprobante["fecha_comprobante"] = "20260816"
        comparacion = comparar_snapshot_con_comprobante(self.snapshot, self.comprobante)
        self.assertEqual(comparacion.resultado, ResultadoReconciliacion.CONFLICTO)
        self.assertTrue(any(diferencia.campo == "fecha_comprobante" for diferencia in comparacion.diferencias))

    def test_cae_ausente(self):
        self.comprobante["cae"] = ""
        comparacion = comparar_snapshot_con_comprobante(self.snapshot, self.comprobante)
        self.assertEqual(comparacion.resultado, ResultadoReconciliacion.CONFLICTO)
        self.assertTrue(any(diferencia.campo == "cae" for diferencia in comparacion.diferencias))

    def test_respuesta_incompleta(self):
        del self.comprobante["importe_iva"]
        comparacion = comparar_snapshot_con_comprobante(self.snapshot, self.comprobante)
        self.assertEqual(comparacion.resultado, ResultadoReconciliacion.CONSULTA_INCIERTA)
        self.assertEqual(comparacion.campos_faltantes, ("importe_iva",))


if __name__ == "__main__":
    unittest.main()