import os
import sqlite3
import tempfile
import unittest
from decimal import Decimal

from database import crear_tabla_intentos_emision_arca
from services.arca.reconciliacion_contracts import (
    EstadoIntentoEmision,
    ResultadoReconciliacion,
    SnapshotFiscalEsperado,
)
from services.intento_emision_arca_service import IntentoEmisionArcaService


class IntentoEmisionArcaServiceTest(unittest.TestCase):

    def setUp(self):
        archivo_temporal = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        archivo_temporal.close()
        self.ruta_db = archivo_temporal.name
        conexion = sqlite3.connect(self.ruta_db)
        try:
            crear_tabla_intentos_emision_arca(conexion.cursor())
            conexion.commit()
        finally:
            conexion.close()
        self.service = IntentoEmisionArcaService(lambda: sqlite3.connect(self.ruta_db))
        self.snapshot = SnapshotFiscalEsperado(
            resumen_id=10, cliente_id=20, emisor_fiscal_id=30, emisor_id=40, cuit_emisor="20-20687162-9",
            punto_venta=5, tipo_comprobante=11, numero_planificado=123, fecha_comprobante="20260816",
            concepto=1, tipo_documento=80, documento_receptor=30712345678, condicion_iva_receptor_id=5,
            importe_total=Decimal("12100.00"), importe_neto=Decimal("12100.00"), importe_iva=Decimal("0.00"),
            importe_exento=Decimal("0.00"), importe_no_gravado=Decimal("0.00"), importe_tributos=Decimal("0.00"),
            moneda="PES", cotizacion=Decimal("1.00"),
            alicuotas_iva=({"id": 5, "base_imponible": Decimal("100.00"), "importe": Decimal("21.00")},),
        )

    def tearDown(self):
        if os.path.exists(self.ruta_db):
            os.remove(self.ruta_db)

    def test_crear_y_recuperar_snapshot_completo(self):
        intento_id = self.service.crear_intento(self.snapshot)
        intento = self.service.obtener(intento_id)
        self.assertEqual(intento.resumen_id, self.snapshot.resumen_id)
        self.assertEqual(intento.cuit_emisor, "20206871629")
        self.assertEqual(intento.importe_total, Decimal("12100.00"))
        self.assertEqual(intento.estado, EstadoIntentoEmision.PENDIENTE_RECONCILIAR.value)

    def test_alicuotas_se_serializan_y_recuperan(self):
        intento = self.service.obtener(self.service.crear_intento(self.snapshot))
        self.assertEqual(intento.alicuotas_iva, ({"base_imponible": "100.00", "id": 5, "importe": "21.00"},))

    def test_actualizar_estado(self):
        intento_id = self.service.crear_intento(self.snapshot)
        self.service.actualizar_estado(intento_id, EstadoIntentoEmision.ENVIANDO, error_codigo="TEMP", error_mensaje="Diagnóstico")
        intento = self.service.obtener(intento_id)
        self.assertEqual(intento.estado, EstadoIntentoEmision.ENVIANDO.value)
        self.assertEqual(intento.error_codigo, "TEMP")

    def test_guardar_resultado_reconciliacion(self):
        intento_id = self.service.crear_intento(self.snapshot)
        self.service.guardar_resultado_reconciliacion(
            intento_id, ResultadoReconciliacion.AUTORIZADO, cae="71345678901234", vencimiento_cae="20260826", factura_arca_id=99,
        )
        intento = self.service.obtener(intento_id)
        self.assertEqual(intento.estado, EstadoIntentoEmision.RECONCILIADO.value)
        self.assertEqual(intento.cae, "71345678901234")
        self.assertEqual(intento.factura_arca_id, 99)
        self.assertTrue(intento.reconciliado_en)

    def test_listar_pendientes(self):
        pendiente_id = self.service.crear_intento(self.snapshot)
        segundo = SnapshotFiscalEsperado(**{**self.snapshot.__dict__, "numero_planificado": 124})
        reconciliado_id = self.service.crear_intento(segundo)
        self.service.guardar_resultado_reconciliacion(reconciliado_id, ResultadoReconciliacion.NO_AUTORIZADO)
        self.assertEqual([intento.id for intento in self.service.listar_pendientes_reconciliacion()], [pendiente_id])

    def test_buscar_por_clave_fiscal(self):
        intento_id = self.service.crear_intento(self.snapshot)
        encontrados = self.service.obtener_por_clave_fiscal("20-20687162-9", 5, 11, 123)
        self.assertEqual([intento.id for intento in encontrados], [intento_id])

    def test_impide_duplicado_activo_y_conserva_historial_terminal(self):
        primer_id = self.service.crear_intento(self.snapshot)
        with self.assertRaises(sqlite3.IntegrityError):
            self.service.crear_intento(self.snapshot, EstadoIntentoEmision.ENVIANDO)
        self.service.guardar_resultado_reconciliacion(primer_id, ResultadoReconciliacion.NO_AUTORIZADO)
        self.assertNotEqual(primer_id, self.service.crear_intento(self.snapshot))

    def test_persistencia_tras_reabrir_conexion(self):
        intento_id = self.service.crear_intento(self.snapshot)
        servicio_reabierto = IntentoEmisionArcaService(lambda: sqlite3.connect(self.ruta_db))
        self.assertEqual(servicio_reabierto.obtener(intento_id).numero_planificado, 123)

    def test_creacion_de_tabla_no_modifica_registros_existentes(self):
        ruta_existente = f"{self.ruta_db}.existente"
        conexion = sqlite3.connect(ruta_existente)
        try:
            cursor = conexion.cursor()
            cursor.execute("CREATE TABLE registro_existente(id INTEGER PRIMARY KEY, valor TEXT NOT NULL)")
            cursor.execute("INSERT INTO registro_existente(valor) VALUES(?)", ("conservar",))
            crear_tabla_intentos_emision_arca(cursor)
            conexion.commit()
            cursor.execute("SELECT valor FROM registro_existente WHERE id=1")
            self.assertEqual(cursor.fetchone()[0], "conservar")
        finally:
            conexion.close()
            if os.path.exists(ruta_existente):
                os.remove(ruta_existente)


if __name__ == "__main__":
    unittest.main()