import os
import sqlite3
import tempfile
import unittest
from decimal import Decimal

from services.arca.cierre_local_arca_service import CierreLocalArcaService
from services.arca.reconciliacion_contracts import ResultadoReconciliacion


class CommitFallido:
    def __init__(self, conexion):
        self._conexion = conexion

    def cursor(self):
        return self._conexion.cursor()

    def commit(self):
        raise sqlite3.OperationalError("commit simulado")

    def rollback(self):
        self._conexion.rollback()

    def close(self):
        self._conexion.close()


class CierreLocalArcaServiceTest(unittest.TestCase):

    def setUp(self):
        archivo = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        archivo.close()
        self.ruta = archivo.name
        conexion = sqlite3.connect(self.ruta)
        try:
            conexion.executescript(
                """
                CREATE TABLE resumenes(id INTEGER PRIMARY KEY, estado_facturacion TEXT, fecha_facturacion TEXT, cae TEXT, vencimiento_cae TEXT, numero_factura TEXT);
                CREATE TABLE factura_arca(id INTEGER PRIMARY KEY AUTOINCREMENT, cliente_id INTEGER NOT NULL, emisor_id INTEGER NOT NULL, resumen_id INTEGER NOT NULL, fecha TEXT NOT NULL, punto_venta TEXT, tipo_comprobante TEXT, importe_total REAL NOT NULL, estado TEXT NOT NULL, numero_factura TEXT, cae TEXT, vencimiento_cae TEXT, observaciones TEXT, fecha_creacion TEXT, punto_venta_num INTEGER, tipo_comprobante_num INTEGER, numero_comprobante_num INTEGER);
                CREATE TABLE intentos_emision_arca(id INTEGER PRIMARY KEY, estado TEXT, cae TEXT, vencimiento_cae TEXT, factura_arca_id INTEGER, error_codigo TEXT, error_mensaje TEXT, actualizado_en TEXT, reconciliado_en TEXT);
                """
            )
            conexion.execute("INSERT INTO resumenes VALUES(10, 'Pendiente', '', '', '', '')")
            conexion.execute("INSERT INTO intentos_emision_arca VALUES(1, 'ENVIANDO', '', '', NULL, '', '', '', NULL)")
            conexion.commit()
        finally:
            conexion.close()
        self.service = CierreLocalArcaService(lambda: sqlite3.connect(self.ruta))

    def tearDown(self):
        if os.path.exists(self.ruta):
            os.remove(self.ruta)

    def datos(self, tipo="Factura C", numero="00005-00000123", total=100.0):
        return dict(
            intento_id=1,
            resumen_id=10,
            cliente_id=20,
            emisor_id=40,
            fecha="20260818",
            punto_venta="5",
            tipo_comprobante=tipo,
            importe_total=total,
            numero_factura=numero,
            cae="86330766550000",
            vencimiento_cae="20260828",
            observaciones="cierre normal",
        )

    def filas(self, tabla):
        conexion = sqlite3.connect(self.ruta)
        try:
            return conexion.execute(f"SELECT * FROM {tabla}").fetchall()
        finally:
            conexion.close()

    def test_factura_c_exitosa(self):
        resultado = self.service.cerrar_emision_confirmada(**self.datos())
        self.assertTrue(resultado.ok)
        self.assertTrue(resultado.insertada)
        self.assertEqual(self.filas("factura_arca")[0][6], "Factura C")
        self.assertEqual(self.filas("factura_arca")[0][-3:], (5, 11, 123))
        self.assertEqual(self.filas("resumenes")[0][1], "Facturado")
        self.assertEqual(self.filas("intentos_emision_arca")[0][1], "RECONCILIADO")

    def test_factura_a_exitosa(self):
        datos = self.datos("Factura A", total=121.0)
        datos["numero_factura"] = "00005-00000124"
        datos["cae"] = "86330766550001"
        resultado = self.service.cerrar_emision_confirmada(**datos)
        self.assertTrue(resultado.ok)
        self.assertEqual(self.filas("factura_arca")[0][6], "Factura A")
        self.assertEqual(self.filas("factura_arca")[0][-3:], (5, 1, 124))

    def test_repetido_es_idempotente(self):
        primero = self.service.cerrar_emision_confirmada(**self.datos())
        segundo = self.service.cerrar_emision_confirmada(**self.datos(factura_arca_id=primero.factura_arca_id) if False else self.datos())
        self.assertEqual(primero.factura_arca_id, segundo.factura_arca_id)
        self.assertEqual(len(self.filas("factura_arca")), 1)
        self.assertEqual(self.filas("factura_arca")[0][9], "00005-00000123")
        self.assertEqual(self.filas("factura_arca")[0][10], "86330766550000")

    def test_factura_compatible_existente(self):
        datos = self.datos()
        conexion = sqlite3.connect(self.ruta)
        conexion.execute(
            "INSERT INTO factura_arca(cliente_id,emisor_id,resumen_id,fecha,punto_venta,tipo_comprobante,importe_total,estado,numero_factura,cae,vencimiento_cae,observaciones,fecha_creacion) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (20, 40, 10, "20260818", "5", "Factura C", 100, "Facturada manualmente", "00005-00000123", "86330766550000", "20260828", "", ""),
        )
        conexion.commit()
        conexion.close()
        resultado = self.service.cerrar_emision_confirmada(**datos)
        self.assertTrue(resultado.ok)
        self.assertFalse(resultado.insertada)
        self.assertEqual(len(self.filas("factura_arca")), 1)

    def test_factura_incompatible_devuelve_conflicto(self):
        conexion = sqlite3.connect(self.ruta)
        conexion.execute(
            "INSERT INTO factura_arca(cliente_id,emisor_id,resumen_id,fecha,punto_venta,tipo_comprobante,importe_total,estado,numero_factura,cae,vencimiento_cae,observaciones,fecha_creacion) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (99, 40, 10, "20260818", "5", "Factura C", 100, "Facturada manualmente", "00005-00000123", "otro-cae", "20260828", "", ""),
        )
        conexion.commit()
        conexion.close()
        resultado = self.service.cerrar_emision_confirmada(**self.datos())
        self.assertFalse(resultado.ok)
        self.assertEqual(resultado.resultado, ResultadoReconciliacion.CONFLICTO)
        self.assertEqual(self.filas("resumenes")[0][1], "Pendiente")

    def test_rollback_insert(self):
        conexion = sqlite3.connect(self.ruta)
        conexion.execute("CREATE TRIGGER falla BEFORE INSERT ON factura_arca BEGIN SELECT RAISE(ABORT, 'insert'); END")
        conexion.commit(); conexion.close()
        with self.assertRaises(sqlite3.DatabaseError):
            self.service.cerrar_emision_confirmada(**self.datos())
        self.assertEqual(len(self.filas("factura_arca")), 0)
        self.assertEqual(self.filas("resumenes")[0][1], "Pendiente")
        self.assertEqual(self.filas("intentos_emision_arca")[0][1], "ENVIANDO")

    def test_rollback_resumen(self):
        conexion = sqlite3.connect(self.ruta)
        conexion.execute("CREATE TRIGGER falla BEFORE UPDATE ON resumenes BEGIN SELECT RAISE(ABORT, 'resumen'); END")
        conexion.commit(); conexion.close()
        with self.assertRaises(sqlite3.DatabaseError):
            self.service.cerrar_emision_confirmada(**self.datos())
        self.assertEqual(len(self.filas("factura_arca")), 0)
        self.assertEqual(self.filas("resumenes")[0][1], "Pendiente")

    def test_rollback_intento(self):
        conexion = sqlite3.connect(self.ruta)
        conexion.execute("CREATE TRIGGER falla BEFORE UPDATE ON intentos_emision_arca BEGIN SELECT RAISE(ABORT, 'intento'); END")
        conexion.commit(); conexion.close()
        with self.assertRaises(sqlite3.DatabaseError):
            self.service.cerrar_emision_confirmada(**self.datos())
        self.assertEqual(len(self.filas("factura_arca")), 0)
        self.assertEqual(self.filas("resumenes")[0][1], "Pendiente")
        self.assertEqual(self.filas("intentos_emision_arca")[0][1], "ENVIANDO")

    def test_rollback_commit(self):
        conexion = sqlite3.connect(self.ruta)
        conexion.close()
        service = CierreLocalArcaService(lambda: CommitFallido(sqlite3.connect(self.ruta)))
        with self.assertRaises(sqlite3.OperationalError):
            service.cerrar_emision_confirmada(**self.datos())
        self.assertEqual(len(self.filas("factura_arca")), 0)
        self.assertEqual(self.filas("resumenes")[0][1], "Pendiente")
        self.assertEqual(self.filas("intentos_emision_arca")[0][1], "ENVIANDO")


if __name__ == "__main__":
    unittest.main()
