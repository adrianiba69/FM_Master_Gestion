import os
import sqlite3
import tempfile
import unittest
from decimal import Decimal

from database import crear_base, migrar_factura_arca_snapshot_fiscal
from models.factura_arca import FacturaArca
from services.arca.snapshot_fiscal_persistence_service import (
    CODIGO_FACTURA_INEXISTENTE,
    CODIGO_SNAPSHOT_CORRUPTO,
    CODIGO_SNAPSHOT_DIFERENTE,
    CODIGO_SNAPSHOT_GUARDADO,
    CODIGO_SNAPSHOT_IDEMPOTENTE,
    CODIGO_SNAPSHOT_INVALIDO,
    SnapshotFiscalPersistenceService,
)
from services.arca.snapshot_fiscal_service import (
    SNAPSHOT_VERSION,
    calcular_hash_snapshot,
    construir_snapshot_fiscal_v1,
    serializar_snapshot_fiscal,
)
from services.factura_arca_service import FacturaArcaService


class SnapshotFiscalPersistenceTest(unittest.TestCase):
    def setUp(self):
        archivo = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.ruta = archivo.name
        archivo.close()
        self._crear_schema_base()
        self.service = SnapshotFiscalPersistenceService(lambda: sqlite3.connect(self.ruta))

    def tearDown(self):
        try:
            os.remove(self.ruta)
        except OSError:
            pass

    def _crear_schema_base(self, con_snapshot=True):
        conexion = sqlite3.connect(self.ruta)
        columnas_snapshot = """
            snapshot_fiscal_json TEXT,
            snapshot_version INTEGER,
            snapshot_hash TEXT,
        """ if con_snapshot else ""
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
                marcador TEXT DEFAULT 'intacto'
            );
            """
        )
        conexion.commit()
        conexion.close()

    def _insertar_factura(self):
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
                "Facturada manualmente", "00005-00000123", "12345678901234",
                "20260902", "obs", "2026-08-23T12:00:00", 5, 1, 123, 80, 20222222221,
            ),
        )
        factura_id = cursor.lastrowid
        conexion.commit()
        conexion.close()
        return factura_id

    def _snapshot(self, numero=123, cae="12345678901234"):
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
                "numero_comprobante_num": numero,
                "numero_textual": f"00005-{numero:08d}",
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
                "cae": cae,
                "vencimiento_cae": "2026-09-02",
                "vencimiento_cae_arca": "20260902",
                "tipo_cod_aut": "E",
                "resultado": "AUTORIZADO",
                "cerrado_en": "2026-08-23T12:34:56",
            },
        )
        serializado = serializar_snapshot_fiscal(snapshot)
        return serializado, SNAPSHOT_VERSION, calcular_hash_snapshot(serializado)

    def _snapshot_db(self, factura_id):
        conexion = sqlite3.connect(self.ruta)
        fila = conexion.execute(
            "SELECT snapshot_fiscal_json, snapshot_version, snapshot_hash FROM factura_arca WHERE id=?",
            (factura_id,),
        ).fetchone()
        conexion.close()
        return fila

    def test_migracion_agrega_columnas_a_tabla_antigua(self):
        os.remove(self.ruta)
        archivo = open(self.ruta, "w")
        archivo.close()
        self._crear_schema_base(con_snapshot=False)
        conexion = sqlite3.connect(self.ruta)
        migrar_factura_arca_snapshot_fiscal(conexion.cursor())
        columnas = {fila[1] for fila in conexion.execute("PRAGMA table_info(factura_arca)")}
        conexion.close()
        self.assertIn("snapshot_fiscal_json", columnas)
        self.assertIn("snapshot_version", columnas)
        self.assertIn("snapshot_hash", columnas)

    def test_migracion_idempotente(self):
        conexion = sqlite3.connect(self.ruta)
        cur = conexion.cursor()
        migrar_factura_arca_snapshot_fiscal(cur)
        migrar_factura_arca_snapshot_fiscal(cur)
        columnas = [fila[1] for fila in conexion.execute("PRAGMA table_info(factura_arca)")]
        conexion.close()
        self.assertEqual(columnas.count("snapshot_fiscal_json"), 1)

    def test_filas_historicas_conservan_snapshot_null(self):
        factura_id = self._insertar_factura()
        self.assertEqual(self._snapshot_db(factura_id), (None, None, None))

    def test_migracion_no_cambia_otros_datos(self):
        factura_id = self._insertar_factura()
        conexion = sqlite3.connect(self.ruta)
        antes = conexion.execute("SELECT cae, numero_factura, importe_total, estado, marcador FROM factura_arca WHERE id=?", (factura_id,)).fetchone()
        migrar_factura_arca_snapshot_fiscal(conexion.cursor())
        despues = conexion.execute("SELECT cae, numero_factura, importe_total, estado, marcador FROM factura_arca WHERE id=?", (factura_id,)).fetchone()
        conexion.close()
        self.assertEqual(antes, despues)

    def test_crear_base_sobre_esquema_nuevo_funciona(self):
        import database

        original = database.DB_NAME
        try:
            database.DB_NAME = self.ruta
            crear_base()
            crear_base()
            conexion = sqlite3.connect(self.ruta)
            columnas = {fila[1] for fila in conexion.execute("PRAGMA table_info(factura_arca)")}
            conexion.close()
        finally:
            database.DB_NAME = original
        self.assertIn("snapshot_fiscal_json", columnas)

    def test_modelo_acepta_snapshot_opcional(self):
        json_text, version, digest = self._snapshot()
        factura = FacturaArca(snapshot_fiscal_json=json_text, snapshot_version=version, snapshot_hash=digest)
        self.assertEqual(factura.snapshot_hash, digest)

    def test_modelo_antiguo_sigue_funcionando(self):
        factura = FacturaArca(cliente_id=1, emisor_id=2, resumen_id=3)
        self.assertIsNone(factura.snapshot_fiscal_json)

    def test_guardar_sin_snapshot_sigue_funcionando(self):
        factura_id = self._guardar_factura_service(FacturaArca(cliente_id=10, emisor_id=20, resumen_id=30, fecha="2026-08-23", punto_venta="5", tipo_comprobante="Factura A", importe_total=1210, estado="Facturada manualmente", numero_factura="00005-00000123"))
        self.assertEqual(self._snapshot_db(factura_id), (None, None, None))

    def test_guardar_con_snapshot_persiste_campos(self):
        json_text, version, digest = self._snapshot()
        factura_id = self._guardar_factura_service(FacturaArca(cliente_id=10, emisor_id=20, resumen_id=30, fecha="2026-08-23", punto_venta="5", tipo_comprobante="Factura A", importe_total=1210, estado="Facturada manualmente", numero_factura="00005-00000123", snapshot_fiscal_json=json_text, snapshot_version=version, snapshot_hash=digest))
        self.assertEqual(self._snapshot_db(factura_id), (json_text, version, digest))

    def test_select_recupera_campos_snapshot(self):
        json_text, version, digest = self._snapshot()
        factura_id = self._guardar_factura_service(FacturaArca(cliente_id=10, emisor_id=20, resumen_id=30, fecha="2026-08-23", punto_venta="5", tipo_comprobante="Factura A", importe_total=1210, estado="Facturada manualmente", numero_factura="00005-00000123", snapshot_fiscal_json=json_text, snapshot_version=version, snapshot_hash=digest))
        fila = self._con_servicio_temporal(lambda: FacturaArcaService.obtener(factura_id))
        self.assertEqual(fila[-3:], (json_text, version, digest))

    def _guardar_factura_service(self, factura):
        return self._con_servicio_temporal(lambda: FacturaArcaService.guardar(factura))

    def _con_servicio_temporal(self, funcion):
        import services.factura_arca_service as modulo

        original = modulo.conectar
        try:
            modulo.conectar = lambda: sqlite3.connect(self.ruta)
            return funcion()
        finally:
            modulo.conectar = original

    def test_sin_snapshot_escribe(self):
        factura_id = self._insertar_factura()
        json_text, version, digest = self._snapshot()
        resultado = self.service.guardar_snapshot_si_ausente(factura_id, json_text, version, digest)
        self.assertEqual(resultado.codigo, CODIGO_SNAPSHOT_GUARDADO)
        self.assertTrue(resultado.actualizado)
        self.assertEqual(self._snapshot_db(factura_id), (json_text, version, digest))

    def test_repetida_es_noop(self):
        factura_id = self._insertar_factura()
        json_text, version, digest = self._snapshot()
        self.service.guardar_snapshot_si_ausente(factura_id, json_text, version, digest)
        resultado = self.service.guardar_snapshot_si_ausente(factura_id, json_text, version, digest)
        self.assertEqual(resultado.codigo, CODIGO_SNAPSHOT_IDEMPOTENTE)
        self.assertTrue(resultado.idempotente)

    def test_mismo_snapshot_conserva_valores(self):
        factura_id = self._insertar_factura()
        json_text, version, digest = self._snapshot()
        self.service.guardar_snapshot_si_ausente(factura_id, json_text, version, digest)
        antes = self._snapshot_db(factura_id)
        self.service.guardar_snapshot_si_ausente(factura_id, json_text, version, digest)
        self.assertEqual(self._snapshot_db(factura_id), antes)

    def test_snapshot_diferente_error(self):
        factura_id = self._insertar_factura()
        json_text, version, digest = self._snapshot()
        otro_json, otra_version, otro_digest = self._snapshot(numero=124, cae="12345678901235")
        self.service.guardar_snapshot_si_ausente(factura_id, json_text, version, digest)
        resultado = self.service.guardar_snapshot_si_ausente(factura_id, otro_json, otra_version, otro_digest)
        self.assertEqual(resultado.codigo, CODIGO_SNAPSHOT_DIFERENTE)
        self.assertEqual(self._snapshot_db(factura_id), (json_text, version, digest))

    def test_hash_distinto_error(self):
        factura_id = self._insertar_factura()
        json_text, version, _digest = self._snapshot()
        resultado = self.service.guardar_snapshot_si_ausente(factura_id, json_text, version, "0" * 64)
        self.assertEqual(resultado.codigo, CODIGO_SNAPSHOT_INVALIDO)
        self.assertEqual(self._snapshot_db(factura_id), (None, None, None))

    def test_version_distinta_error(self):
        factura_id = self._insertar_factura()
        json_text, _version, digest = self._snapshot()
        resultado = self.service.guardar_snapshot_si_ausente(factura_id, json_text, 2, digest)
        self.assertEqual(resultado.codigo, CODIGO_SNAPSHOT_INVALIDO)

    def test_json_invalido_error(self):
        factura_id = self._insertar_factura()
        resultado = self.service.guardar_snapshot_si_ausente(factura_id, "{mal", SNAPSHOT_VERSION, "0" * 64)
        self.assertEqual(resultado.codigo, CODIGO_SNAPSHOT_INVALIDO)

    def test_estructura_invalida_error(self):
        factura_id = self._insertar_factura()
        json_text, _version, _digest = self._snapshot()
        datos = json_text.replace('"items":', '"items_corruptos":', 1)
        digest = calcular_hash_snapshot(datos)
        resultado = self.service.guardar_snapshot_si_ausente(factura_id, datos, SNAPSHOT_VERSION, digest)
        self.assertEqual(resultado.codigo, CODIGO_SNAPSHOT_INVALIDO)

    def test_factura_inexistente_error(self):
        json_text, version, digest = self._snapshot()
        resultado = self.service.guardar_snapshot_si_ausente(999, json_text, version, digest)
        self.assertEqual(resultado.codigo, CODIGO_FACTURA_INEXISTENTE)

    def test_snapshot_almacenado_corrupto_no_reemplaza(self):
        factura_id = self._insertar_factura()
        conexion = sqlite3.connect(self.ruta)
        conexion.execute("UPDATE factura_arca SET snapshot_fiscal_json=?, snapshot_version=?, snapshot_hash=? WHERE id=?", ("{mal", 1, "0" * 64, factura_id))
        conexion.commit()
        conexion.close()
        json_text, version, digest = self._snapshot()
        resultado = self.service.guardar_snapshot_si_ausente(factura_id, json_text, version, digest)
        self.assertEqual(resultado.codigo, CODIGO_SNAPSHOT_CORRUPTO)
        self.assertEqual(self._snapshot_db(factura_id), ("{mal", 1, "0" * 64))

    def test_rollback_ante_error_con_conexion_propia(self):
        factura_id = self._insertar_factura()
        conexion = sqlite3.connect(self.ruta)
        conexion.execute("CREATE TRIGGER falla_snapshot BEFORE UPDATE OF snapshot_fiscal_json ON factura_arca BEGIN SELECT RAISE(ABORT, 'snapshot'); END")
        conexion.commit()
        conexion.close()
        json_text, version, digest = self._snapshot()
        with self.assertRaises(sqlite3.DatabaseError):
            self.service.guardar_snapshot_si_ausente(factura_id, json_text, version, digest)
        self.assertEqual(self._snapshot_db(factura_id), (None, None, None))

    def test_conexion_externa_no_hace_commit(self):
        factura_id = self._insertar_factura()
        json_text, version, digest = self._snapshot()
        conn = sqlite3.connect(self.ruta)
        conn.execute("BEGIN")
        try:
            resultado = self.service.guardar_snapshot_si_ausente(factura_id, json_text, version, digest, conn=conn)
            self.assertEqual(resultado.codigo, CODIGO_SNAPSHOT_GUARDADO)
            self.assertEqual(conn.execute("SELECT snapshot_hash FROM factura_arca WHERE id=?", (factura_id,)).fetchone()[0], digest)
            conn.rollback()
        finally:
            conn.close()
        self.assertEqual(self._snapshot_db(factura_id), (None, None, None))

    def test_conexion_externa_no_se_cierra(self):
        factura_id = self._insertar_factura()
        json_text, version, digest = self._snapshot()
        conn = sqlite3.connect(self.ruta)
        try:
            self.service.guardar_snapshot_si_ausente(factura_id, json_text, version, digest, conn=conn)
            conn.execute("SELECT 1").fetchone()
            conn.rollback()
        finally:
            conn.close()

    def test_conexion_propia_confirma_correctamente(self):
        factura_id = self._insertar_factura()
        json_text, version, digest = self._snapshot()
        self.service.guardar_snapshot_si_ausente(factura_id, json_text, version, digest)
        self.assertEqual(self._snapshot_db(factura_id), (json_text, version, digest))


if __name__ == "__main__":
    unittest.main()