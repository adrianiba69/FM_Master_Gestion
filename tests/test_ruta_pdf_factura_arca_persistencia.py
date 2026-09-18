"""Tests de POST-E2E 3B.3A: persistencia estructural de ruta PDF fiscal.

Solo schema/modelo/service. CERO integracion con generacion de PDF real.
CERO ARCA. Usa DB temporal (nunca la real).
"""

import os
import sqlite3
import tempfile
import unittest
from decimal import Decimal

from database import crear_base, migrar_factura_arca_ruta_pdf, migrar_factura_arca_snapshot_fiscal
from models.factura_arca import FacturaArca
from services.arca.snapshot_fiscal_service import (
    SNAPSHOT_VERSION,
    calcular_hash_snapshot,
    construir_snapshot_fiscal_v1,
    serializar_snapshot_fiscal,
)
from services.factura_arca_service import FacturaArcaService


class RutaPdfFacturaArcaPersistenciaTest(unittest.TestCase):
    def setUp(self):
        archivo = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.ruta = archivo.name
        archivo.close()
        self._crear_schema_base()

    def tearDown(self):
        try:
            os.remove(self.ruta)
        except OSError:
            pass

    def _crear_schema_base(self, con_snapshot=True, con_ruta_pdf=True):
        conexion = sqlite3.connect(self.ruta)
        columnas_snapshot = """
            snapshot_fiscal_json TEXT,
            snapshot_version INTEGER,
            snapshot_hash TEXT,
        """ if con_snapshot else ""
        columnas_ruta_pdf = """
            ruta_pdf_relativa TEXT,
            ruta_pdf_absoluta TEXT,
        """ if con_ruta_pdf else ""
        conexion.executescript(
            f"""
            CREATE TABLE IF NOT EXISTS factura_arca(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
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
                fecha_creacion TEXT,
                punto_venta_num INTEGER,
                tipo_comprobante_num INTEGER,
                numero_comprobante_num INTEGER,
                tipo_documento_receptor INTEGER,
                documento_receptor INTEGER,
                {columnas_snapshot}
                {columnas_ruta_pdf}
                marcador TEXT DEFAULT 'intacto'
            );
            """
        )
        conexion.commit()
        conexion.close()

    def _insertar_factura_historica(self, cae="86300674746947"):
        conexion = sqlite3.connect(self.ruta)
        cursor = conexion.execute(
            """
            INSERT INTO factura_arca(
                cliente_id, emisor_id, resumen_id, fecha, punto_venta, tipo_comprobante,
                importe_total, estado, numero_factura, cae, vencimiento_cae, observaciones,
                fecha_creacion, punto_venta_num, tipo_comprobante_num, numero_comprobante_num,
                tipo_documento_receptor, documento_receptor
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                10, 20, 30, "2026-08-23", "5", "Factura A", 1210.0,
                "Facturada manualmente", "00005-00000123", cae,
                "20260902", "obs", "2026-08-23T12:00:00", 5, 1, 123, 80, 20222222221,
            ),
        )
        factura_id = cursor.lastrowid
        conexion.commit()
        conexion.close()
        return factura_id

    def _fila_completa(self, factura_id):
        conexion = sqlite3.connect(self.ruta)
        fila = conexion.execute(
            "SELECT cae, snapshot_fiscal_json, snapshot_hash, estado, punto_venta_num, "
            "tipo_comprobante_num, numero_comprobante_num, ruta_pdf_relativa, ruta_pdf_absoluta "
            "FROM factura_arca WHERE id=?",
            (factura_id,),
        ).fetchone()
        conexion.close()
        return fila

    def _rutas_db(self, factura_id):
        conexion = sqlite3.connect(self.ruta)
        fila = conexion.execute(
            "SELECT ruta_pdf_relativa, ruta_pdf_absoluta FROM factura_arca WHERE id=?",
            (factura_id,),
        ).fetchone()
        conexion.close()
        return fila

    def _con_servicio_temporal(self, funcion):
        import services.factura_arca_service as modulo

        original = modulo.conectar
        try:
            modulo.conectar = lambda: sqlite3.connect(self.ruta)
            return funcion()
        finally:
            modulo.conectar = original

    def _snapshot(self):
        snapshot = construir_snapshot_fiscal_v1(
            fuente="cierre_normal",
            creado_en="2026-08-23T12:34:56",
            ambiente="HOMOLOGACION",
            emisor={
                "emisor_id": 20,
                "emisor_fiscal_id": 2,
                "razon_social": "FM Master SRL",
                "nombre_fantasia": "FM Master",
                "cuit": "20111111117",
                "condicion_iva": "Responsable Inscripto",
                "domicilio": "Domicilio fiscal",
                "ingresos_brutos": "123456",
                "fecha_inicio_actividades": "2020-01-01",
                "punto_venta_num": 5,
            },
            receptor={
                "cliente_id": 10,
                "razon_social": "Cliente SA",
                "documento_visible": "20222222221",
                "condicion_iva": "Responsable Inscripto",
                "domicilio": "Cliente 123",
                "tipo_documento_receptor": 80,
                "documento_receptor": 20222222221,
            },
            comprobante={
                "fecha": "2026-08-23",
                "fecha_arca": "20260823",
                "concepto": 1,
                "concepto_descripcion": "1 - Productos",
                "punto_venta_num": 5,
                "tipo_comprobante_num": 1,
                "tipo_comprobante_texto": "Factura A",
                "numero_comprobante_num": 123,
                "numero_textual": "00005-00000123",
                "periodo_servicio_desde": None,
                "periodo_servicio_hasta": None,
                "vencimiento_pago": None,
                "moneda": "PES",
                "cotizacion": Decimal("1"),
            },
            importes={
                "total": Decimal("1210"),
                "neto": Decimal("1000"),
                "iva": Decimal("210"),
                "exento": Decimal("0"),
                "no_gravado": Decimal("0"),
                "tributos": Decimal("0"),
            },
            iva=[{"id": 5, "base_imponible": Decimal("1000"), "importe": Decimal("210"), "porcentaje": Decimal("21")}],
            items=[{"concepto": "Servicio", "descripcion": "Servicio", "cantidad": Decimal("1"), "precio_unitario": Decimal("1000"), "subtotal": Decimal("1000")}],
            autorizacion={
                "cae": "86300674746947",
                "vencimiento_cae": "2026-09-02",
                "vencimiento_cae_arca": "20260902",
                "tipo_cod_aut": "E",
                "resultado": "AUTORIZADO",
                "cerrado_en": "2026-08-23T12:34:56",
            },
        )
        serializado = serializar_snapshot_fiscal(snapshot)
        return serializado, SNAPSHOT_VERSION, calcular_hash_snapshot(serializado)

    # A) DB nueva crea ambas columnas.
    def test_crear_base_sobre_esquema_nuevo_agrega_columnas_ruta_pdf(self):
        import database

        original = database.DB_NAME
        try:
            database.DB_NAME = self.ruta
            crear_base()
            columnas = {
                fila[1]
                for fila in sqlite3.connect(self.ruta).execute("PRAGMA table_info(factura_arca)")
            }
        finally:
            database.DB_NAME = original
        self.assertIn("ruta_pdf_relativa", columnas)
        self.assertIn("ruta_pdf_absoluta", columnas)

    # B) DB existente sin columnas migra correctamente.
    def test_migracion_agrega_columnas_a_tabla_antigua(self):
        os.remove(self.ruta)
        open(self.ruta, "w").close()
        self._crear_schema_base(con_ruta_pdf=False)
        conexion = sqlite3.connect(self.ruta)
        migrar_factura_arca_ruta_pdf(conexion.cursor())
        columnas = {fila[1] for fila in conexion.execute("PRAGMA table_info(factura_arca)")}
        conexion.close()
        self.assertIn("ruta_pdf_relativa", columnas)
        self.assertIn("ruta_pdf_absoluta", columnas)

    # C) migración repetida es idempotente.
    def test_migracion_idempotente(self):
        conexion = sqlite3.connect(self.ruta)
        cur = conexion.cursor()
        migrar_factura_arca_ruta_pdf(cur)
        migrar_factura_arca_ruta_pdf(cur)
        columnas = [fila[1] for fila in conexion.execute("PRAGMA table_info(factura_arca)")]
        conexion.close()
        self.assertEqual(columnas.count("ruta_pdf_relativa"), 1)
        self.assertEqual(columnas.count("ruta_pdf_absoluta"), 1)

    # D) filas históricas quedan NULL en ambas columnas.
    def test_filas_historicas_quedan_con_rutas_null(self):
        factura_id = self._insertar_factura_historica()
        self.assertEqual(self._rutas_db(factura_id), (None, None))

    def test_migracion_no_cambia_otros_datos_de_filas_historicas(self):
        factura_id = self._insertar_factura_historica()
        conexion = sqlite3.connect(self.ruta)
        antes = conexion.execute(
            "SELECT cae, numero_factura, importe_total, estado, marcador FROM factura_arca WHERE id=?",
            (factura_id,),
        ).fetchone()
        migrar_factura_arca_ruta_pdf(conexion.cursor())
        despues = conexion.execute(
            "SELECT cae, numero_factura, importe_total, estado, marcador FROM factura_arca WHERE id=?",
            (factura_id,),
        ).fetchone()
        conexion.close()
        self.assertEqual(antes, despues)

    # E) guardar factura sin rutas sigue funcionando.
    def test_guardar_sin_rutas_sigue_funcionando(self):
        factura_id = self._con_servicio_temporal(
            lambda: FacturaArcaService.guardar(
                FacturaArca(
                    cliente_id=10, emisor_id=20, resumen_id=30, fecha="2026-08-23",
                    punto_venta="5", tipo_comprobante="Factura A", importe_total=1210,
                    estado="Facturada manualmente", numero_factura="00005-00000123",
                )
            )
        )
        self.assertIsNotNone(factura_id)
        self.assertEqual(self._rutas_db(factura_id), (None, None))

    # F) guardar factura con ambas rutas las persiste correctamente.
    def test_guardar_con_ambas_rutas_las_persiste(self):
        relativa = r"Homologacion\facturas\COQUETTE_PERFUMERIA_Factura_A_00002-00000010.pdf"
        absoluta = r"C:\FM_Master_Certificados\Publicidad_y_Servicios_SH\Homologacion\facturas\COQUETTE_PERFUMERIA_Factura_A_00002-00000010.pdf"
        factura_id = self._con_servicio_temporal(
            lambda: FacturaArcaService.guardar(
                FacturaArca(
                    cliente_id=10, emisor_id=20, resumen_id=30, fecha="2026-08-23",
                    punto_venta="5", tipo_comprobante="Factura A", importe_total=1210,
                    estado="Facturada manualmente", numero_factura="00005-00000123",
                    ruta_pdf_relativa=relativa, ruta_pdf_absoluta=absoluta,
                )
            )
        )
        self.assertEqual(self._rutas_db(factura_id), (relativa, absoluta))

    # G) obtener recupera ambas rutas.
    def test_obtener_recupera_ambas_rutas(self):
        relativa = r"Produccion\facturas\x.pdf"
        absoluta = r"C:\FM_Master_Certificados\ClienteX\Produccion\facturas\x.pdf"
        factura_id = self._con_servicio_temporal(
            lambda: FacturaArcaService.guardar(
                FacturaArca(
                    cliente_id=10, emisor_id=20, resumen_id=30, fecha="2026-08-23",
                    punto_venta="5", tipo_comprobante="Factura A", importe_total=1210,
                    estado="Facturada manualmente", numero_factura="00005-00000123",
                    ruta_pdf_relativa=relativa, ruta_pdf_absoluta=absoluta,
                )
            )
        )
        fila = self._con_servicio_temporal(lambda: FacturaArcaService.obtener(factura_id))
        self.assertEqual(fila[-2:], (relativa, absoluta))

    # H) listar recupera ambas rutas.
    def test_listar_recupera_ambas_rutas(self):
        relativa = r"Homologacion\facturas\y.pdf"
        absoluta = r"C:\FM_Master_Certificados\ClienteY\Homologacion\facturas\y.pdf"
        self._con_servicio_temporal(
            lambda: FacturaArcaService.guardar(
                FacturaArca(
                    cliente_id=10, emisor_id=20, resumen_id=30, fecha="2026-08-23",
                    punto_venta="5", tipo_comprobante="Factura A", importe_total=1210,
                    estado="Facturada manualmente", numero_factura="00005-00000123",
                    ruta_pdf_relativa=relativa, ruta_pdf_absoluta=absoluta,
                )
            )
        )
        filas = self._con_servicio_temporal(lambda: FacturaArcaService.listar())
        self.assertEqual(len(filas), 1)
        self.assertEqual(filas[0][-2:], (relativa, absoluta))

    # I) actualizar posteriormente: NULL -> rutas funciona.
    def test_actualizar_ruta_pdf_desde_null_funciona(self):
        factura_id = self._insertar_factura_historica()
        self.assertEqual(self._rutas_db(factura_id), (None, None))

        relativa = r"Homologacion\facturas\z.pdf"
        absoluta = r"C:\FM_Master_Certificados\ClienteZ\Homologacion\facturas\z.pdf"
        self._con_servicio_temporal(
            lambda: FacturaArcaService.actualizar_ruta_pdf(factura_id, relativa, absoluta)
        )
        self.assertEqual(self._rutas_db(factura_id), (relativa, absoluta))

    # J) actualizar rutas no modifica CAE/snapshot/hash/estado/identidad fiscal.
    def test_actualizar_ruta_pdf_no_toca_otros_campos(self):
        json_text, version, digest = self._snapshot()
        factura_id = self._con_servicio_temporal(
            lambda: FacturaArcaService.guardar(
                FacturaArca(
                    cliente_id=10, emisor_id=20, resumen_id=30, fecha="2026-08-23",
                    punto_venta="5", tipo_comprobante="Factura A", importe_total=1210,
                    estado="Facturada manualmente", numero_factura="00005-00000123",
                    cae="86300674746947",
                    snapshot_fiscal_json=json_text, snapshot_version=version, snapshot_hash=digest,
                )
            )
        )
        antes = self._fila_completa(factura_id)

        self._con_servicio_temporal(
            lambda: FacturaArcaService.actualizar_ruta_pdf(
                factura_id, r"Homologacion\facturas\w.pdf", r"C:\raiz\Homologacion\facturas\w.pdf"
            )
        )
        despues = self._fila_completa(factura_id)

        self.assertEqual(antes[:7], despues[:7])
        self.assertNotEqual(antes[7:], despues[7:])

    # K) ruta relativa/absoluta aceptan strings Windows sin normalizarlos.
    def test_rutas_windows_se_persisten_tal_cual_sin_normalizar(self):
        relativa = r"Homologacion\facturas\ARCHIVO CON ESPACIOS.pdf"
        absoluta = r"C:\FM_Master_Certificados\Publicidad_y_Servicios_SH\Homologacion\facturas\ARCHIVO CON ESPACIOS.pdf"
        factura_id = self._con_servicio_temporal(
            lambda: FacturaArcaService.guardar(
                FacturaArca(
                    cliente_id=10, emisor_id=20, resumen_id=30, fecha="2026-08-23",
                    punto_venta="5", tipo_comprobante="Factura A", importe_total=1210,
                    estado="Facturada manualmente", numero_factura="00005-00000123",
                    ruta_pdf_relativa=relativa, ruta_pdf_absoluta=absoluta,
                )
            )
        )
        rel_db, abs_db = self._rutas_db(factura_id)
        self.assertEqual(rel_db, relativa)
        self.assertEqual(abs_db, absoluta)
        self.assertIsInstance(rel_db, str)
        self.assertIsInstance(abs_db, str)

    # L) constructores/modelo anteriores siguen funcionando.
    def test_modelo_antiguo_sin_rutas_sigue_funcionando(self):
        factura = FacturaArca(cliente_id=1, emisor_id=2, resumen_id=3)
        self.assertIsNone(factura.ruta_pdf_relativa)
        self.assertIsNone(factura.ruta_pdf_absoluta)

    def test_constructor_posicional_id_primero_sigue_funcionando(self):
        factura = FacturaArca(1, 2, 3, 4)
        self.assertEqual((factura.id, factura.cliente_id, factura.emisor_id, factura.resumen_id), (1, 2, 3, 4))
        self.assertIsNone(factura.ruta_pdf_relativa)
        self.assertIsNone(factura.ruta_pdf_absoluta)

    # M) snapshot/contexto permanecen exactamente sin campos de filesystem.
    def test_snapshot_sigue_sin_campos_de_filesystem(self):
        json_text, _, _ = self._snapshot()
        import json as json_module

        snapshot = json_module.loads(json_text)
        claves_planas = set(snapshot.keys()) | set((snapshot.get("emisor") or {}).keys())
        self.assertNotIn("ruta_pdf_relativa", claves_planas)
        self.assertNotIn("ruta_pdf_absoluta", claves_planas)
        self.assertNotIn("carpeta_facturas", claves_planas)

    # N) índice H/P existente permanece sin cambios en este bloque.
    def test_indice_identidad_unica_no_incluye_ambiente(self):
        import database

        original = database.DB_NAME
        try:
            database.DB_NAME = self.ruta
            crear_base()
            sql_indice = sqlite3.connect(self.ruta).execute(
                "SELECT sql FROM sqlite_master WHERE type='index' AND name='idx_factura_arca_identidad_unica'"
            ).fetchone()
        finally:
            database.DB_NAME = original
        self.assertIsNotNone(sql_indice)
        self.assertIn("emisor_id, punto_venta_num, tipo_comprobante_num, numero_comprobante_num", sql_indice[0])
        self.assertNotIn("ambiente", sql_indice[0].lower())


if __name__ == "__main__":
    unittest.main()
