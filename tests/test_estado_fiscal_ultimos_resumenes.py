import os
import sqlite3
import tempfile
import unittest

import database
from services.resumen_service import ResumenService


class EstadoFiscalUltimosResumenesTest(unittest.TestCase):

    def setUp(self):
        archivo = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        archivo.close()
        self.ruta = archivo.name
        self._db_name_original = database.DB_NAME
        database.DB_NAME = self.ruta
        database.crear_base()

    def tearDown(self):
        database.DB_NAME = self._db_name_original
        if os.path.exists(self.ruta):
            os.remove(self.ruta)

    def _crear_cliente(self, conexion, nombre="Cliente Test"):
        cur = conexion.execute(
            "INSERT INTO clientes(nombre, razon_social) VALUES(?, ?)",
            (nombre, nombre),
        )
        conexion.commit()
        return cur.lastrowid

    def _crear_resumen(self, conexion, cliente_id, numero, estado="Pendiente", estado_facturacion="Pendiente"):
        cur = conexion.execute(
            """
            INSERT INTO resumenes(numero, cliente_id, fecha, fecha_vencimiento, total, saldo, estado, pdf_path, estado_facturacion)
            VALUES(?,?,?,?,?,?,?,?,?)
            """,
            (numero, cliente_id, "2026-08-01", "2026-08-15", 1000.0, 1000.0, estado, "", estado_facturacion),
        )
        conexion.commit()
        return cur.lastrowid

    def test_indices_anteriores_intactos(self):
        conexion = sqlite3.connect(self.ruta)
        cliente_id = self._crear_cliente(conexion)
        self._crear_resumen(conexion, cliente_id, numero=1, estado="Pendiente")
        conexion.close()

        filas = ResumenService.listar(cliente_id)
        self.assertEqual(len(filas), 1)
        fila = filas[0]
        # id, numero, fecha, fecha_vencimiento, cliente, total, saldo, estado, pdf_path
        self.assertEqual(fila[1], 1)
        self.assertEqual(fila[2], "2026-08-01")
        self.assertEqual(fila[3], "2026-08-15")
        self.assertEqual(fila[4], "Cliente Test")
        self.assertEqual(fila[5], 1000.0)
        self.assertEqual(fila[6], 1000.0)
        self.assertEqual(fila[7], "Pendiente")
        self.assertEqual(fila[8], "")

    def test_estado_facturacion_al_final(self):
        conexion = sqlite3.connect(self.ruta)
        cliente_id = self._crear_cliente(conexion)
        self._crear_resumen(conexion, cliente_id, numero=1, estado_facturacion="Facturado")
        conexion.close()

        fila = ResumenService.listar(cliente_id)[0]
        self.assertEqual(len(fila), 10)
        self.assertEqual(fila[9], "Facturado")

    def test_estado_facturacion_null_devuelve_pendiente(self):
        # La tabla real exige NOT NULL; se usa un esquema minimo con la columna
        # nullable para simular datos legacy previos a la migracion y validar el COALESCE.
        archivo_legacy = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        archivo_legacy.close()
        ruta_legacy = archivo_legacy.name
        try:
            conexion = sqlite3.connect(ruta_legacy)
            conexion.executescript(
                """
                CREATE TABLE clientes(id INTEGER PRIMARY KEY, nombre TEXT, razon_social TEXT);
                CREATE TABLE resumenes(
                    id INTEGER PRIMARY KEY,
                    numero INTEGER,
                    cliente_id INTEGER,
                    fecha TEXT,
                    fecha_vencimiento TEXT,
                    total REAL,
                    saldo REAL,
                    estado TEXT,
                    pdf_path TEXT,
                    estado_facturacion TEXT
                );
                """
            )
            cliente_id = self._crear_cliente(conexion)
            self._crear_resumen(conexion, cliente_id, numero=1, estado_facturacion=None)
            conexion.commit()
            conexion.close()

            database.DB_NAME = ruta_legacy
            fila = ResumenService.listar(cliente_id)[0]
            self.assertEqual(fila[9], "Pendiente")
        finally:
            database.DB_NAME = self.ruta
            if os.path.exists(ruta_legacy):
                os.remove(ruta_legacy)

    def test_distingue_pendiente_comercial_facturado_fiscal(self):
        conexion = sqlite3.connect(self.ruta)
        cliente_id = self._crear_cliente(conexion)
        self._crear_resumen(conexion, cliente_id, numero=1, estado="Pendiente", estado_facturacion="Facturado")
        conexion.close()

        fila = ResumenService.listar(cliente_id)[0]
        self.assertEqual(fila[7], "Pendiente")
        self.assertEqual(fila[9], "Facturado")

    def test_distingue_cobrado_comercial_pendiente_fiscal(self):
        conexion = sqlite3.connect(self.ruta)
        cliente_id = self._crear_cliente(conexion)
        self._crear_resumen(conexion, cliente_id, numero=1, estado="Cobrado", estado_facturacion="Pendiente")
        conexion.close()

        fila = ResumenService.listar(cliente_id)[0]
        self.assertEqual(fila[7], "Cobrado")
        self.assertEqual(fila[9], "Pendiente")


if __name__ == "__main__":
    unittest.main()
