import io
import os
import sqlite3
import tempfile
import unittest
from contextlib import redirect_stdout

from database import migrar_factura_arca_columnas_normalizadas, migrar_indices_unicos_factura_arca

INDICE_CAE = "idx_factura_arca_cae_unico"
INDICE_IDENTIDAD = "idx_factura_arca_identidad_unica"


class IndicesUnicosFacturaArcaTest(unittest.TestCase):

    def setUp(self):
        archivo = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        archivo.close()
        self.ruta = archivo.name

    def tearDown(self):
        if os.path.exists(self.ruta):
            os.remove(self.ruta)

    def _crear_tabla(self, filas=()):
        conexion = sqlite3.connect(self.ruta)
        conexion.execute(
            """
            CREATE TABLE factura_arca(
                id INTEGER PRIMARY KEY,
                cliente_id INTEGER NOT NULL,
                emisor_id INTEGER NOT NULL,
                resumen_id INTEGER NOT NULL,
                fecha TEXT NOT NULL,
                punto_venta TEXT,
                tipo_comprobante TEXT,
                importe_total REAL NOT NULL,
                estado TEXT NOT NULL,
                numero_factura TEXT,
                cae TEXT,
                vencimiento_cae TEXT,
                observaciones TEXT,
                fecha_creacion TEXT
            )
            """
        )
        conexion.executemany(
            "INSERT INTO factura_arca(id,cliente_id,emisor_id,resumen_id,fecha,punto_venta,tipo_comprobante,importe_total,estado,numero_factura,cae,vencimiento_cae,observaciones,fecha_creacion) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            filas,
        )
        conexion.commit()
        return conexion

    @staticmethod
    def _indices_existentes(conexion):
        cur = conexion.execute("SELECT name FROM sqlite_master WHERE type='index'")
        return {fila[0] for fila in cur.fetchall()}

    def _migrar_completo(self, conexion):
        cur = conexion.cursor()
        migrar_factura_arca_columnas_normalizadas(cur)
        conexion.commit()
        salida = io.StringIO()
        with redirect_stdout(salida):
            migrar_indices_unicos_factura_arca(cur)
        conexion.commit()
        return salida.getvalue()

    def test_base_limpia_crea_ambos_indices(self):
        filas = [
            (1, 20, 1, 10, "2026-08-01", "00002", "Factura C", 100, "Facturada", "00002-00000001", "11111111111111", "20260811", "", ""),
            (2, 21, 2, 11, "2026-08-01", "00002", "Factura A", 200, "Facturada", "00002-00000001", "22222222222222", "20260811", "", ""),
        ]
        conexion = self._crear_tabla(filas)
        self._migrar_completo(conexion)
        indices = self._indices_existentes(conexion)
        self.assertIn(INDICE_CAE, indices)
        self.assertIn(INDICE_IDENTIDAD, indices)
        conexion.close()

    def test_segunda_ejecucion_es_idempotente(self):
        filas = [(1, 20, 1, 10, "2026-08-01", "00002", "Factura C", 100, "Facturada", "00002-00000001", "11111111111111", "20260811", "", "")]
        conexion = self._crear_tabla(filas)
        self._migrar_completo(conexion)
        # Segunda ejecucion no debe lanzar excepcion ni duplicar indices.
        self._migrar_completo(conexion)
        indices = self._indices_existentes(conexion)
        self.assertIn(INDICE_CAE, indices)
        self.assertIn(INDICE_IDENTIDAD, indices)
        conexion.close()

    def test_cae_duplicado_no_crea_indice_cae(self):
        filas = [
            (1, 20, 1, 10, "2026-08-01", "00002", "Factura C", 100, "Facturada", "00002-00000001", "11111111111111", "20260811", "", ""),
            (2, 21, 2, 11, "2026-08-01", "00003", "Factura C", 200, "Facturada", "00003-00000005", "11111111111111", "20260811", "", ""),
        ]
        conexion = self._crear_tabla(filas)
        salida = self._migrar_completo(conexion)
        indices = self._indices_existentes(conexion)
        self.assertNotIn(INDICE_CAE, indices)
        self.assertIn("1,2", salida)
        conexion.close()

    def test_identidad_duplicada_no_crea_indice_identidad(self):
        filas = [
            (1, 20, 1, 10, "2026-08-01", "00002", "Factura C", 100, "Facturada", "00002-00000001", "11111111111111", "20260811", "", ""),
            (2, 21, 1, 11, "2026-08-01", "00002", "Factura C", 200, "Facturada", "00002-00000001", "22222222222222", "20260811", "", ""),
        ]
        conexion = self._crear_tabla(filas)
        salida = self._migrar_completo(conexion)
        indices = self._indices_existentes(conexion)
        self.assertNotIn(INDICE_IDENTIDAD, indices)
        self.assertIn("1,2", salida)
        conexion.close()

    def test_cae_vacio_multiple_permitido(self):
        filas = [
            (1, 20, 1, 10, "2026-08-01", "00002", "Factura A", 100, "Anulada", "", "", "", "", ""),
            (2, 21, 2, 11, "2026-08-01", "00003", "Factura A", 200, "Anulada", "", "", "", "", ""),
        ]
        conexion = self._crear_tabla(filas)
        self._migrar_completo(conexion)
        indices = self._indices_existentes(conexion)
        self.assertIn(INDICE_CAE, indices)
        conexion.close()

    def test_numero_comprobante_null_multiple_permitido(self):
        filas = [
            (1, 20, 1, 10, "2026-08-01", "001", "Factura A", 100, "Anulada", "", "", "", "", ""),
            (2, 21, 1, 11, "2026-08-01", "001", "Factura A", 200, "Anulada", "", "", "", "", ""),
        ]
        conexion = self._crear_tabla(filas)
        self._migrar_completo(conexion)
        indices = self._indices_existentes(conexion)
        self.assertIn(INDICE_IDENTIDAD, indices)
        conexion.close()

    def test_misma_numeracion_factura_a_y_c_permitido(self):
        filas = [
            (1, 20, 1, 10, "2026-08-01", "00002", "Factura A", 100, "Facturada", "00002-00000001", "11111111111111", "20260811", "", ""),
            (2, 21, 1, 11, "2026-08-01", "00002", "Factura C", 200, "Facturada", "00002-00000001", "22222222222222", "20260811", "", ""),
        ]
        conexion = self._crear_tabla(filas)
        self._migrar_completo(conexion)
        indices = self._indices_existentes(conexion)
        self.assertIn(INDICE_IDENTIDAD, indices)
        conexion.close()

    def test_dos_emisores_mismo_pv_tipo_numero_permitido(self):
        filas = [
            (1, 20, 1, 10, "2026-08-01", "00002", "Factura C", 100, "Facturada", "00002-00000008", "11111111111111", "20260811", "", ""),
            (2, 21, 2, 11, "2026-08-01", "00002", "Factura C", 200, "Facturada", "00002-00000008", "22222222222222", "20260811", "", ""),
        ]
        conexion = self._crear_tabla(filas)
        self._migrar_completo(conexion)
        indices = self._indices_existentes(conexion)
        self.assertIn(INDICE_IDENTIDAD, indices)
        conexion.close()

    def test_mismo_emisor_pv_tipo_numero_repetido_bloqueado(self):
        filas = [
            (1, 20, 1, 10, "2026-08-01", "00002", "Factura C", 100, "Facturada", "00002-00000008", "11111111111111", "20260811", "", ""),
            (2, 21, 1, 11, "2026-08-01", "00002", "Factura C", 200, "Facturada", "00002-00000008", "22222222222222", "20260811", "", ""),
        ]
        conexion = self._crear_tabla(filas)
        salida = self._migrar_completo(conexion)
        indices = self._indices_existentes(conexion)
        self.assertNotIn(INDICE_IDENTIDAD, indices)
        self.assertIn("ADVERTENCIA", salida)
        conexion.close()

    def test_insert_duplicado_por_cae_lanza_integrity_error(self):
        filas = [(1, 20, 1, 10, "2026-08-01", "00002", "Factura C", 100, "Facturada", "00002-00000001", "11111111111111", "20260811", "", "")]
        conexion = self._crear_tabla(filas)
        self._migrar_completo(conexion)
        with self.assertRaises(sqlite3.IntegrityError):
            conexion.execute(
                "INSERT INTO factura_arca(id,cliente_id,emisor_id,resumen_id,fecha,punto_venta,tipo_comprobante,importe_total,estado,numero_factura,cae,vencimiento_cae,observaciones,fecha_creacion) "
                "VALUES(99,20,1,10,'2026-08-02','00002','Factura C',100,'Facturada','00002-00000002','11111111111111','20260811','','')"
            )
        conexion.close()

    def test_insert_duplicado_por_identidad_lanza_integrity_error(self):
        filas = [(1, 20, 1, 10, "2026-08-01", "00002", "Factura C", 100, "Facturada", "00002-00000001", "11111111111111", "20260811", "", "")]
        conexion = self._crear_tabla(filas)
        self._migrar_completo(conexion)
        with self.assertRaises(sqlite3.IntegrityError):
            conexion.execute(
                "INSERT INTO factura_arca(id,cliente_id,emisor_id,resumen_id,fecha,punto_venta,tipo_comprobante,importe_total,estado,numero_factura,cae,vencimiento_cae,observaciones,fecha_creacion,punto_venta_num,tipo_comprobante_num,numero_comprobante_num) "
                "VALUES(99,20,1,10,'2026-08-02','00002','Factura C',100,'Facturada','00002-00000001','33333333333333','20260811','','',2,11,1)"
            )
        conexion.close()

    def test_base_historica_con_duplicados_no_interrumpe_apertura(self):
        filas = [
            (1, 20, 1, 10, "2026-08-01", "00002", "Factura C", 100, "Facturada", "00002-00000001", "11111111111111", "20260811", "", ""),
            (2, 21, 1, 11, "2026-08-01", "00002", "Factura C", 200, "Facturada", "00002-00000001", "11111111111111", "20260811", "", ""),
        ]
        conexion = self._crear_tabla(filas)
        try:
            salida = self._migrar_completo(conexion)
        except Exception as error:  # noqa: BLE001 - la migracion no debe interrumpir el arranque
            self.fail(f"La migracion no debe lanzar excepciones sobre historicos conflictivos: {error}")
        indices = self._indices_existentes(conexion)
        self.assertNotIn(INDICE_CAE, indices)
        self.assertNotIn(INDICE_IDENTIDAD, indices)
        self.assertIn("ADVERTENCIA", salida)
        # La conexion sigue operable pese a los duplicados historicos.
        self.assertEqual(conexion.execute("SELECT COUNT(*) FROM factura_arca").fetchone()[0], 2)
        conexion.close()


if __name__ == "__main__":
    unittest.main()
