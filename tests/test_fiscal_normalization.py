import os
import sqlite3
import tempfile
import unittest

from database import migrar_factura_arca_columnas_normalizadas
from services.arca.fiscal_normalization import (
    normalizar_identidad_factura,
    normalizar_punto_venta,
    normalizar_tipo_comprobante,
    separar_numero_factura,
)


class FiscalNormalizationTest(unittest.TestCase):

    def setUp(self):
        archivo = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        archivo.close()
        self.ruta = archivo.name

    def tearDown(self):
        if os.path.exists(self.ruta):
            os.remove(self.ruta)

    def _crear_tabla_antigua(self, filas=()):
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

    def test_normalizadores_basicos(self):
        self.assertEqual(normalizar_punto_venta("00002"), 2)
        self.assertEqual(normalizar_punto_venta("2"), 2)
        self.assertEqual(normalizar_punto_venta("001"), 1)
        self.assertEqual(normalizar_tipo_comprobante("Factura A"), 1)
        self.assertEqual(normalizar_tipo_comprobante("Factura C"), 11)
        self.assertEqual(separar_numero_factura("00002-00000008"), (2, 8))
        self.assertIsNone(separar_numero_factura("8"))
        self.assertIsNone(normalizar_punto_venta(""))
        self.assertIsNone(normalizar_tipo_comprobante("Otro"))

    def test_migracion_tabla_antigua_y_dos_veces(self):
        conexion = self._crear_tabla_antigua()
        migrar_factura_arca_columnas_normalizadas(conexion.cursor())
        conexion.commit()
        migrar_factura_arca_columnas_normalizadas(conexion.cursor())
        conexion.commit()
        columnas = [fila[1] for fila in conexion.execute("PRAGMA table_info(factura_arca)")]
        self.assertEqual(columnas[-3:], ["punto_venta_num", "tipo_comprobante_num", "numero_comprobante_num"])
        conexion.close()

    def test_backfill_factura_a_y_c(self):
        filas = [
            (1, 20, 3, 10, "2026-08-18", "00002", "Factura A", 121, "Facturada", "00002-00000008", "11111111111111", "20260828", "", ""),
            (2, 21, 2, 11, "2026-08-18", "2", "Factura C", 100, "Facturada", "00002-00000009", "22222222222222", "20260828", "", ""),
        ]
        conexion = self._crear_tabla_antigua(filas)
        migrar_factura_arca_columnas_normalizadas(conexion.cursor())
        conexion.commit()
        datos = conexion.execute("SELECT punto_venta_num,tipo_comprobante_num,numero_comprobante_num FROM factura_arca ORDER BY id").fetchall()
        self.assertEqual(datos, [(2, 1, 8), (2, 11, 9)])
        conexion.close()

    def test_numero_vacio_deja_numero_null(self):
        conexion = self._crear_tabla_antigua([(1, 25, 1, 24, "2026-06-30", "001", "Factura A", 1500, "Anulada", "", "", "", "", "")])
        migrar_factura_arca_columnas_normalizadas(conexion.cursor())
        conexion.commit()
        self.assertEqual(conexion.execute("SELECT punto_venta_num,tipo_comprobante_num,numero_comprobante_num FROM factura_arca").fetchone(), (1, 1, None))
        conexion.close()

    def test_prefijo_incompatible_no_actualiza_identidad(self):
        conexion = self._crear_tabla_antigua([(1, 25, 3, 24, "2026-08-01", "001", "Factura A", 1000, "Facturada", "00002-00000001", "", "", "", "")])
        migrar_factura_arca_columnas_normalizadas(conexion.cursor())
        conexion.commit()
        self.assertEqual(conexion.execute("SELECT punto_venta_num,tipo_comprobante_num,numero_comprobante_num FROM factura_arca").fetchone(), (None, None, None))
        conexion.close()

    def test_valores_invalidos_quedan_null(self):
        conexion = self._crear_tabla_antigua([(1, 25, 3, 24, "2026-08-01", "abc", "Otro", 1000, "Pendiente", "", "", "", "", "")])
        migrar_factura_arca_columnas_normalizadas(conexion.cursor())
        conexion.commit()
        self.assertEqual(conexion.execute("SELECT punto_venta_num,tipo_comprobante_num,numero_comprobante_num FROM factura_arca").fetchone(), (None, None, None))
        conexion.close()

    def test_columnas_textuales_no_cambian(self):
        fila = (1, 25, 3, 24, "2026-08-01", "00002", "Factura A", 1000, "Facturada", "00002-00000001", "86310711529020", "20260811", "obs", "fecha")
        conexion = self._crear_tabla_antigua([fila])
        migrar_factura_arca_columnas_normalizadas(conexion.cursor())
        conexion.commit()
        actual = conexion.execute("SELECT punto_venta,tipo_comprobante,numero_factura,cae,estado,importe_total,observaciones,fecha FROM factura_arca").fetchone()
        self.assertEqual(actual, ("00002", "Factura A", "00002-00000001", "86310711529020", "Facturada", 1000.0, "obs", "2026-08-01"))
        conexion.close()


if __name__ == "__main__":
    unittest.main()
