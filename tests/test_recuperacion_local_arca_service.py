import os
import sqlite3
import tempfile
import unittest
from decimal import Decimal

from models.intento_emision_arca import IntentoEmisionArca
from services.arca.recuperacion_local_service import RecuperacionLocalArcaService
from services.arca.reconciliacion_contracts import ResultadoReconciliacion, SnapshotFiscalEsperado


class RecuperacionLocalArcaServiceTest(unittest.TestCase):

    def setUp(self):
        archivo = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        archivo.close()
        self.ruta = archivo.name
        conexion = sqlite3.connect(self.ruta)
        try:
            cursor = conexion.cursor()
            cursor.executescript("""
                CREATE TABLE resumenes(id INTEGER PRIMARY KEY, estado_facturacion TEXT, fecha_facturacion TEXT, cae TEXT, vencimiento_cae TEXT, numero_factura TEXT);
                CREATE TABLE factura_arca(id INTEGER PRIMARY KEY AUTOINCREMENT, cliente_id INTEGER NOT NULL, emisor_id INTEGER NOT NULL, resumen_id INTEGER NOT NULL, fecha TEXT NOT NULL, punto_venta TEXT, tipo_comprobante TEXT, importe_total REAL NOT NULL, estado TEXT NOT NULL, numero_factura TEXT, cae TEXT, vencimiento_cae TEXT, observaciones TEXT, fecha_creacion TEXT);
                CREATE TABLE intentos_emision_arca(id INTEGER PRIMARY KEY, estado TEXT, cae TEXT, vencimiento_cae TEXT, factura_arca_id INTEGER, error_codigo TEXT, error_mensaje TEXT, actualizado_en TEXT, reconciliado_en TEXT);
            """)
            cursor.execute("INSERT INTO resumenes VALUES(10, 'Pendiente', '', '', '', '')")
            cursor.execute("INSERT INTO intentos_emision_arca VALUES(1, 'PENDIENTE_RECONCILIAR', '', '', NULL, '', '', '', NULL)")
            conexion.commit()
        finally:
            conexion.close()
        self.service = RecuperacionLocalArcaService(lambda: sqlite3.connect(self.ruta))
        self.snapshot = SnapshotFiscalEsperado(
            resumen_id=10, cliente_id=20, emisor_fiscal_id=30, emisor_id=40, cuit_emisor="20206871629",
            punto_venta=5, tipo_comprobante=11, numero_planificado=123, fecha_comprobante="20260817",
            concepto=1, tipo_documento=80, documento_receptor=30712345678, condicion_iva_receptor_id=5,
            importe_total=Decimal("100.00"), importe_neto=Decimal("100.00"), importe_iva=Decimal("0.00"),
            importe_exento=Decimal("0.00"), importe_no_gravado=Decimal("0.00"), importe_tributos=Decimal("0.00"),
            moneda="PES", cotizacion=Decimal("1.00"),
        )

    def tearDown(self):
        if os.path.exists(self.ruta):
            os.remove(self.ruta)

    def _intento(self, estado="PENDIENTE_RECONCILIAR", factura_arca_id=None):
        return IntentoEmisionArca(1, 10, 20, 30, 40, "20206871629", 5, 11, 123, "20260817", 1, 80, 30712345678, 5, Decimal("100.00"), Decimal("100.00"), Decimal("0.00"), Decimal("0.00"), Decimal("0.00"), Decimal("0.00"), "PES", Decimal("1.00"), (), estado, "", "", "", "", "", factura_arca_id, "", "", None)

    def _consulta(self):
        return {"cuit_emisor": "20206871629", "punto_venta": 5, "tipo_comprobante": 11, "numero_comprobante": 123, "fecha_comprobante": "20260817", "doc_tipo": 80, "doc_nro": 30712345678, "importe_total": "100.00", "importe_neto": "100.00", "importe_iva": "0.00", "moneda": "PES", "cotizacion": "1.00", "condicion_iva_receptor_id": 5, "cae": "86330766550000", "vencimiento_cae": "20260827"}

    def _filas(self, tabla):
        conexion = sqlite3.connect(self.ruta)
        try:
            return conexion.execute(f"SELECT * FROM {tabla}").fetchall()
        finally:
            conexion.close()

    def test_recuperacion_nueva_exitosa_y_persistente(self):
        resultado = self.service.registrar_factura_recuperada(self._intento(), self.snapshot, self._consulta())
        self.assertEqual(resultado.resultado, ResultadoReconciliacion.AUTORIZADO)
        self.assertTrue(resultado.insertada)
        factura = self._filas("factura_arca")[0]
        intento = self._filas("intentos_emision_arca")[0]
        self.assertEqual(factura[9], "00005-00000123")
        self.assertEqual(intento[1], "RECONCILIADO")
        self.assertEqual(intento[4], resultado.factura_arca_id)
        self.assertTrue(intento[8])

    def test_repetir_recuperacion_es_idempotente(self):
        primero = self.service.registrar_factura_recuperada(self._intento(), self.snapshot, self._consulta())
        segundo = self.service.registrar_factura_recuperada(self._intento("RECONCILIADO", primero.factura_arca_id), self.snapshot, self._consulta())
        self.assertEqual(primero.factura_arca_id, segundo.factura_arca_id)
        self.assertEqual(len(self._filas("factura_arca")), 1)

    def test_factura_existe_y_resumen_pendiente(self):
        self.service.registrar_factura_recuperada(self._intento(), self.snapshot, self._consulta())
        conexion = sqlite3.connect(self.ruta)
        conexion.execute("UPDATE resumenes SET estado_facturacion='Pendiente', cae='', numero_factura='' WHERE id=10")
        conexion.execute("UPDATE intentos_emision_arca SET estado='PENDIENTE_RECONCILIAR', factura_arca_id=NULL WHERE id=1")
        conexion.commit(); conexion.close()
        resultado = self.service.registrar_factura_recuperada(self._intento(), self.snapshot, self._consulta())
        self.assertFalse(resultado.insertada)
        self.assertEqual(len(self._filas("factura_arca")), 1)

    def test_resumen_facturado_y_factura_falta(self):
        conexion = sqlite3.connect(self.ruta)
        conexion.execute("UPDATE resumenes SET estado_facturacion='Facturado', cae='86330766550000', numero_factura='00005-00000123' WHERE id=10")
        conexion.commit(); conexion.close()
        resultado = self.service.registrar_factura_recuperada(self._intento(), self.snapshot, self._consulta())
        self.assertEqual(resultado.resultado, ResultadoReconciliacion.AUTORIZADO)
        self.assertEqual(len(self._filas("factura_arca")), 1)

    def test_intento_ya_reconciliado_con_factura_enlazada_es_idempotente(self):
        primero = self.service.registrar_factura_recuperada(self._intento(), self.snapshot, self._consulta())
        resultado = self.service.registrar_factura_recuperada(
            self._intento("RECONCILIADO", primero.factura_arca_id),
            self.snapshot,
            self._consulta(),
        )
        self.assertEqual(resultado.resultado, ResultadoReconciliacion.AUTORIZADO)
        self.assertEqual(resultado.factura_arca_id, primero.factura_arca_id)
        self.assertEqual(len(self._filas("factura_arca")), 1)

    def test_cerrar_y_reabrir_conexion_conserva_recuperacion(self):
        resultado = self.service.registrar_factura_recuperada(self._intento(), self.snapshot, self._consulta())
        conexion = sqlite3.connect(self.ruta)
        try:
            intento = conexion.execute("SELECT estado, factura_arca_id, reconciliado_en FROM intentos_emision_arca WHERE id=1").fetchone()
            resumen = conexion.execute("SELECT estado_facturacion, cae, numero_factura FROM resumenes WHERE id=10").fetchone()
        finally:
            conexion.close()
        self.assertEqual(intento[0], "RECONCILIADO")
        self.assertEqual(intento[1], resultado.factura_arca_id)
        self.assertTrue(intento[2])
        self.assertEqual(resumen[0], "Facturado")

    def test_conflicto_por_identidad_local(self):
        conexion = sqlite3.connect(self.ruta)
        conexion.execute("INSERT INTO factura_arca VALUES(NULL,99,40,10,'20260817','5','Factura C',100,'Facturada manualmente','00005-00000123','86330766550000','20260827','','')")
        conexion.commit(); conexion.close()
        resultado = self.service.registrar_factura_recuperada(self._intento(), self.snapshot, self._consulta())
        self.assertEqual(resultado.resultado, ResultadoReconciliacion.CONFLICTO)
        self.assertEqual(self._filas("intentos_emision_arca")[0][1], "PENDIENTE_RECONCILIAR")

    def test_conflicto_por_cae_local(self):
        conexion = sqlite3.connect(self.ruta)
        conexion.execute("INSERT INTO factura_arca VALUES(NULL,20,40,99,'20260817','5','Factura C',100,'Facturada manualmente','00005-00000123','86330766550000','20260827','','')")
        conexion.commit(); conexion.close()
        resultado = self.service.registrar_factura_recuperada(self._intento(), self.snapshot, self._consulta())
        self.assertEqual(resultado.resultado, ResultadoReconciliacion.CONFLICTO)

    def test_fallo_insertar_hace_rollback(self):
        conexion = sqlite3.connect(self.ruta)
        conexion.execute("CREATE TRIGGER falla_insert BEFORE INSERT ON factura_arca BEGIN SELECT RAISE(ABORT, 'insert'); END")
        conexion.commit(); conexion.close()
        with self.assertRaises(sqlite3.DatabaseError):
            self.service.registrar_factura_recuperada(self._intento(), self.snapshot, self._consulta())
        self.assertEqual(len(self._filas("factura_arca")), 0)
        self.assertEqual(self._filas("intentos_emision_arca")[0][1], "PENDIENTE_RECONCILIAR")

    def test_fallo_marcar_resumen_hace_rollback(self):
        conexion = sqlite3.connect(self.ruta)
        conexion.execute("CREATE TRIGGER falla_resumen BEFORE UPDATE ON resumenes BEGIN SELECT RAISE(ABORT, 'resumen'); END")
        conexion.commit(); conexion.close()
        with self.assertRaises(sqlite3.DatabaseError):
            self.service.registrar_factura_recuperada(self._intento(), self.snapshot, self._consulta())
        self.assertEqual(len(self._filas("factura_arca")), 0)

    def test_fallo_enlazar_intento_hace_rollback(self):
        conexion = sqlite3.connect(self.ruta)
        conexion.execute("CREATE TRIGGER falla_intento BEFORE UPDATE ON intentos_emision_arca BEGIN SELECT RAISE(ABORT, 'intento'); END")
        conexion.commit(); conexion.close()
        with self.assertRaises(sqlite3.DatabaseError):
            self.service.registrar_factura_recuperada(self._intento(), self.snapshot, self._consulta())
        self.assertEqual(len(self._filas("factura_arca")), 0)


if __name__ == "__main__":
    unittest.main()