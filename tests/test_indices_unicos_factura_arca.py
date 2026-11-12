import io
import importlib
import sqlite3
import unittest
from contextlib import redirect_stdout

from tests._guardia_indices_fiscales import (
    HISTORICO_CAE, HISTORICO_IDENTIDAD, database, foto, guardia_fiscal,
)

migrar_indices_unicos_factura_arca = database.migrar_indices_unicos_factura_arca


def setUpModule():
    guardia = guardia_fiscal()
    guardia.__enter__()
    unittest.addModuleCleanup(guardia.__exit__, None, None, None)


def rechazar_sin_cambios(prueba, conexion, error=sqlite3.IntegrityError):
    antes = foto(conexion, "factura_arca")
    transaccion = conexion.in_transaction
    with prueba.assertRaises(error), redirect_stdout(io.StringIO()) as salida:
        migrar_indices_unicos_factura_arca(conexion.cursor())
    prueba.assertEqual(salida.getvalue(), "")
    prueba.assertEqual(foto(conexion, "factura_arca"), antes)
    prueba.assertEqual(conexion.in_transaction, transaccion)

INDICE_CAE = "idx_factura_arca_cae_unico"
INDICE_IDENTIDAD = "idx_factura_arca_identidad_unica"
INDICE_CAE_HISTORICO = "idx_factura_arca_cae_historico_unico"
INDICE_IDENTIDAD_HISTORICA = "idx_factura_arca_identidad_historica_unica"


class IndicesUnicosFacturaArcaTest(unittest.TestCase):

    def _crear_tabla(self, filas=()):
        conexion = sqlite3.connect(":memory:")
        self.addCleanup(conexion.close)
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

    @staticmethod
    def _preparar_normalizadas(conexion):
        # Preparacion del fixture, sin ejecutar migraciones ajenas a estos indices.
        columnas = {f[1] for f in conexion.execute("PRAGMA main.table_info(factura_arca)")}
        for columna in ("punto_venta_num", "tipo_comprobante_num", "numero_comprobante_num"):
            if columna not in columnas:
                conexion.execute(f"ALTER TABLE main.factura_arca ADD COLUMN {columna} INTEGER")
        for fila in conexion.execute(
            "SELECT id, punto_venta, tipo_comprobante, numero_factura FROM factura_arca "
            "WHERE punto_venta_num IS NULL OR tipo_comprobante_num IS NULL "
            "OR (TRIM(COALESCE(numero_factura, '')) <> '' AND numero_comprobante_num IS NULL)"
        ).fetchall():
            pv, tipo, numero = database.normalizar_identidad_factura(*fila[1:])
            if pv is not None and tipo is not None:
                conexion.execute(
                    "UPDATE factura_arca SET punto_venta_num=?, tipo_comprobante_num=?, "
                    "numero_comprobante_num=? WHERE id=?", (pv, tipo, numero, fila[0])
                )
        conexion.commit()

    def _rechazar_completo(self, conexion):
        self._preparar_normalizadas(conexion)
        rechazar_sin_cambios(self, conexion)

    def _migrar_completo(self, conexion):
        self._preparar_normalizadas(conexion)
        salida = io.StringIO()
        with redirect_stdout(salida):
            migrar_indices_unicos_factura_arca(conexion.cursor())
        conexion.commit()
        return salida.getvalue()

    def test_base_limpia_crea_ambos_indices(self):
        filas = [
            (1, 20, 1, 10, "2026-08-01", "00002", "Factura C", 100, "Facturada", "00002-00000001", "11111111111111", "20260811", "", ""),
            (2, 21, 2, 11, "2026-08-01", "00002", "Factura A", 200, "Facturada", "00002-00000001", "22222222222222", "20260811", "", ""),
        ]
        conexion = self._crear_tabla(filas)
        conexion.execute("ALTER TABLE factura_arca ADD COLUMN ambiente_arca TEXT")
        self._migrar_completo(conexion)
        indices = self._indices_existentes(conexion)
        self.assertIn(INDICE_CAE, indices)
        self.assertIn(INDICE_IDENTIDAD, indices)
        conexion.close()

    def test_identity_ambiente_distinto_permite_coexistencia(self):
        filas = [
            (1, 20, 1, 10, "2026-08-01", "00002", "Factura A", 100, "Facturada", "00002-00000010", "11111111111111", "20260811", "", "", "HOMOLOGACION"),
            (2, 21, 1, 10, "2026-08-01", "00002", "Factura A", 200, "Facturada", "00002-00000010", "22222222222222", "20260811", "", "", "PRODUCCION"),
        ]
        conexion = self._crear_tabla([])
        conexion.execute("ALTER TABLE factura_arca ADD COLUMN ambiente_arca TEXT")
        conexion.executemany(
            "INSERT INTO factura_arca(id,cliente_id,emisor_id,resumen_id,fecha,punto_venta,tipo_comprobante,importe_total,estado,numero_factura,cae,vencimiento_cae,observaciones,fecha_creacion,ambiente_arca) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            filas,
        )
        conexion.execute("ALTER TABLE factura_arca ADD COLUMN punto_venta_num INTEGER")
        conexion.execute("ALTER TABLE factura_arca ADD COLUMN tipo_comprobante_num INTEGER")
        conexion.execute("ALTER TABLE factura_arca ADD COLUMN numero_comprobante_num INTEGER")
        conexion.execute("UPDATE factura_arca SET punto_venta_num=2, tipo_comprobante_num=1, numero_comprobante_num=10 WHERE id IN (1, 2)")
        conexion.commit()
        self._migrar_completo(conexion)
        self.assertEqual(conexion.execute("SELECT COUNT(*) FROM factura_arca").fetchone()[0], 2)
        conexion.close()

    def test_identity_mismo_ambiente_sigue_bloqueada(self):
        filas = [
            (1, 20, 1, 10, "2026-08-01", "00002", "Factura A", 100, "Facturada", "00002-00000010", "11111111111111", "20260811", "", "", "HOMOLOGACION"),
            (2, 21, 1, 10, "2026-08-01", "00002", "Factura A", 200, "Facturada", "00002-00000010", "22222222222222", "20260811", "", "", "HOMOLOGACION"),
        ]
        conexion = self._crear_tabla([])
        conexion.execute("ALTER TABLE factura_arca ADD COLUMN ambiente_arca TEXT")
        conexion.execute("ALTER TABLE factura_arca ADD COLUMN punto_venta_num INTEGER")
        conexion.execute("ALTER TABLE factura_arca ADD COLUMN tipo_comprobante_num INTEGER")
        conexion.execute("ALTER TABLE factura_arca ADD COLUMN numero_comprobante_num INTEGER")
        conexion.executemany(
            "INSERT INTO factura_arca(id,cliente_id,emisor_id,resumen_id,fecha,punto_venta,tipo_comprobante,importe_total,estado,numero_factura,cae,vencimiento_cae,observaciones,fecha_creacion,ambiente_arca,punto_venta_num,tipo_comprobante_num,numero_comprobante_num) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            [(fila[0], fila[1], fila[2], fila[3], fila[4], fila[5], fila[6], fila[7], fila[8], fila[9], fila[10], fila[11], fila[12], fila[13], fila[14], 2, 1, 10) for fila in filas],
        )
        conexion.commit()
        self._rechazar_completo(conexion)
        self.assertNotIn(INDICE_IDENTIDAD, self._indices_existentes(conexion))
        conexion.close()

    def test_cae_mismo_ambiente_sigue_bloqueado_y_distinto_ambiente_permite(self):
        conexion = self._crear_tabla([])
        conexion.execute("ALTER TABLE factura_arca ADD COLUMN ambiente_arca TEXT")
        conexion.executemany(
            "INSERT INTO factura_arca(id,cliente_id,emisor_id,resumen_id,fecha,punto_venta,tipo_comprobante,importe_total,estado,numero_factura,cae,vencimiento_cae,observaciones,fecha_creacion,ambiente_arca) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            [
                (1, 20, 1, 10, "2026-08-01", "00002", "Factura A", 100, "Facturada", "00002-00000010", "11111111111111", "20260811", "", "", "HOMOLOGACION"),
                (2, 21, 1, 10, "2026-08-01", "00002", "Factura A", 200, "Facturada", "00002-00000011", "11111111111111", "20260811", "", "", "HOMOLOGACION"),
                (3, 22, 1, 10, "2026-08-01", "00002", "Factura A", 300, "Facturada", "00002-00000012", "11111111111111", "20260811", "", "", "PRODUCCION"),
            ],
        )
        conexion.commit()
        self._rechazar_completo(conexion)
        self.assertNotIn(INDICE_CAE, self._indices_existentes(conexion))
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
            (1, 20, 1, 10, "2026-08-01", "00002", "Factura C", 100, "Facturada", "00002-00000001", "11111111111111", "20260811", "", "", "HOMOLOGACION"),
            (2, 21, 2, 11, "2026-08-01", "00003", "Factura C", 200, "Facturada", "00003-00000005", "11111111111111", "20260811", "", "", "HOMOLOGACION"),
        ]
        conexion = self._crear_tabla([])
        conexion.execute("ALTER TABLE factura_arca ADD COLUMN ambiente_arca TEXT")
        conexion.executemany(
            "INSERT INTO factura_arca(id,cliente_id,emisor_id,resumen_id,fecha,punto_venta,tipo_comprobante,importe_total,estado,numero_factura,cae,vencimiento_cae,observaciones,fecha_creacion,ambiente_arca) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            filas,
        )
        conexion.commit()
        self._rechazar_completo(conexion)
        indices = self._indices_existentes(conexion)
        self.assertNotIn(INDICE_CAE, indices)
        conexion.close()

    def test_identidad_duplicada_no_crea_indice_identidad(self):
        filas = [
            (1, 20, 1, 10, "2026-08-01", "00002", "Factura C", 100, "Facturada", "00002-00000001", "11111111111111", "20260811", "", "", "HOMOLOGACION"),
            (2, 21, 1, 11, "2026-08-01", "00002", "Factura C", 200, "Facturada", "00002-00000001", "22222222222222", "20260811", "", "", "HOMOLOGACION"),
        ]
        conexion = self._crear_tabla([])
        conexion.execute("ALTER TABLE factura_arca ADD COLUMN ambiente_arca TEXT")
        conexion.execute("ALTER TABLE factura_arca ADD COLUMN punto_venta_num INTEGER")
        conexion.execute("ALTER TABLE factura_arca ADD COLUMN tipo_comprobante_num INTEGER")
        conexion.execute("ALTER TABLE factura_arca ADD COLUMN numero_comprobante_num INTEGER")
        conexion.executemany(
            "INSERT INTO factura_arca(id,cliente_id,emisor_id,resumen_id,fecha,punto_venta,tipo_comprobante,importe_total,estado,numero_factura,cae,vencimiento_cae,observaciones,fecha_creacion,ambiente_arca,punto_venta_num,tipo_comprobante_num,numero_comprobante_num) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            [(fila[0], fila[1], fila[2], fila[3], fila[4], fila[5], fila[6], fila[7], fila[8], fila[9], fila[10], fila[11], fila[12], fila[13], fila[14], 2, 11, 1) for fila in filas],
        )
        conexion.commit()
        self._rechazar_completo(conexion)
        indices = self._indices_existentes(conexion)
        self.assertNotIn(INDICE_IDENTIDAD, indices)
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
        self._rechazar_completo(conexion)
        indices = self._indices_existentes(conexion)
        self.assertNotIn(INDICE_IDENTIDAD_HISTORICA, indices)
        self.assertNotIn(INDICE_IDENTIDAD, indices)
        conexion.close()

    def test_insert_duplicado_por_cae_lanza_integrity_error(self):
        filas = [(1, 20, 1, 10, "2026-08-01", "00002", "Factura C", 100, "Facturada", "00002-00000001", "11111111111111", "20260811", "", "", "HOMOLOGACION")]
        conexion = self._crear_tabla([])
        conexion.execute("ALTER TABLE factura_arca ADD COLUMN ambiente_arca TEXT")
        conexion.executemany(
            "INSERT INTO factura_arca(id,cliente_id,emisor_id,resumen_id,fecha,punto_venta,tipo_comprobante,importe_total,estado,numero_factura,cae,vencimiento_cae,observaciones,fecha_creacion,ambiente_arca) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            filas,
        )
        conexion.commit()
        self._migrar_completo(conexion)
        with self.assertRaises(sqlite3.IntegrityError):
            conexion.execute(
                "INSERT INTO factura_arca(id,cliente_id,emisor_id,resumen_id,fecha,punto_venta,tipo_comprobante,importe_total,estado,numero_factura,cae,vencimiento_cae,observaciones,fecha_creacion,ambiente_arca) "
                "VALUES(99,20,1,10,'2026-08-02','00002','Factura C',100,'Facturada','00002-00000002','11111111111111','20260811','','','HOMOLOGACION')"
            )
        conexion.close()

    def test_insert_duplicado_por_identidad_lanza_integrity_error(self):
        filas = [(1, 20, 1, 10, "2026-08-01", "00002", "Factura C", 100, "Facturada", "00002-00000001", "11111111111111", "20260811", "", "", "HOMOLOGACION")]
        conexion = self._crear_tabla([])
        conexion.execute("ALTER TABLE factura_arca ADD COLUMN ambiente_arca TEXT")
        conexion.execute("ALTER TABLE factura_arca ADD COLUMN punto_venta_num INTEGER")
        conexion.execute("ALTER TABLE factura_arca ADD COLUMN tipo_comprobante_num INTEGER")
        conexion.execute("ALTER TABLE factura_arca ADD COLUMN numero_comprobante_num INTEGER")
        conexion.executemany(
            "INSERT INTO factura_arca(id,cliente_id,emisor_id,resumen_id,fecha,punto_venta,tipo_comprobante,importe_total,estado,numero_factura,cae,vencimiento_cae,observaciones,fecha_creacion,ambiente_arca,punto_venta_num,tipo_comprobante_num,numero_comprobante_num) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            [(fila[0], fila[1], fila[2], fila[3], fila[4], fila[5], fila[6], fila[7], fila[8], fila[9], fila[10], fila[11], fila[12], fila[13], fila[14], 2, 11, 1) for fila in filas],
        )
        conexion.commit()
        self._migrar_completo(conexion)
        with self.assertRaises(sqlite3.IntegrityError):
            conexion.execute(
                "INSERT INTO factura_arca(id,cliente_id,emisor_id,resumen_id,fecha,punto_venta,tipo_comprobante,importe_total,estado,numero_factura,cae,vencimiento_cae,observaciones,fecha_creacion,ambiente_arca,punto_venta_num,tipo_comprobante_num,numero_comprobante_num) "
                "VALUES(99,20,1,10,'2026-08-02','00002','Factura C',100,'Facturada','00002-00000001','33333333333333','20260811','','','HOMOLOGACION',2,11,1)"
            )
        conexion.close()

    def test_base_historica_con_duplicados_se_detiene_sin_cambios(self):
        filas = [
            (1, 20, 1, 10, "2026-08-01", "00002", "Factura C", 100, "Facturada", "00002-00000001", "11111111111111", "20260811", "", "", None),
            (2, 21, 1, 11, "2026-08-01", "00002", "Factura C", 200, "Facturada", "00002-00000001", "11111111111111", "20260811", "", "", None),
        ]
        conexion = self._crear_tabla([])
        conexion.execute("ALTER TABLE factura_arca ADD COLUMN ambiente_arca TEXT")
        conexion.executemany(
            "INSERT INTO factura_arca(id,cliente_id,emisor_id,resumen_id,fecha,punto_venta,tipo_comprobante,importe_total,estado,numero_factura,cae,vencimiento_cae,observaciones,fecha_creacion,ambiente_arca) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            filas,
        )
        conexion.commit()
        self._rechazar_completo(conexion)
        indices = self._indices_existentes(conexion)
        self.assertNotIn(INDICE_CAE, indices)
        self.assertNotIn(INDICE_IDENTIDAD, indices)
        self.assertNotIn(INDICE_CAE_HISTORICO, indices)
        self.assertNotIn(INDICE_IDENTIDAD_HISTORICA, indices)
        self.assertEqual(conexion.execute("SELECT COUNT(*) FROM factura_arca").fetchone()[0], 2)
        conexion.close()


class PoliticaAIndices3B4BTest(unittest.TestCase):

    def _conexion(self):
        conexion = sqlite3.connect(":memory:")
        self.addCleanup(conexion.close)
        conexion.execute(
            "CREATE TABLE factura_arca(id INTEGER PRIMARY KEY, ambiente_arca TEXT, "
            "emisor_id INTEGER, punto_venta_num INTEGER, tipo_comprobante_num INTEGER, "
            "numero_comprobante_num INTEGER, cae TEXT)"
        )
        return conexion

    def _insertar(self, conexion, ambiente, numero=8, cae="111", emisor=1, pv=2, tipo=11):
        conexion.execute(
            "INSERT INTO factura_arca(ambiente_arca, emisor_id, punto_venta_num, "
            "tipo_comprobante_num, numero_comprobante_num, cae) VALUES(?,?,?,?,?,?)",
            (ambiente, emisor, pv, tipo, numero, cae),
        )

    def test_identidad_y_cae_bloqueados_en_cada_espacio(self):
        for ambiente in ("HOMOLOGACION", "PRODUCCION", None):
            with self.subTest(ambiente=ambiente):
                conexion = self._conexion()
                migrar_indices_unicos_factura_arca(conexion.cursor())
                self._insertar(conexion, ambiente)
                with self.assertRaises(sqlite3.IntegrityError):
                    self._insertar(conexion, ambiente, cae="222")
                with self.assertRaises(sqlite3.IntegrityError):
                    self._insertar(conexion, ambiente, numero=9, cae=" 111 ")

    def test_h_p_y_null_coexisten_en_indices(self):
        conexion = self._conexion()
        migrar_indices_unicos_factura_arca(conexion.cursor())
        for ambiente in ("HOMOLOGACION", "PRODUCCION", None):
            self._insertar(conexion, ambiente)
        self.assertEqual(conexion.execute("SELECT COUNT(*) FROM factura_arca").fetchone()[0], 3)

    def test_cae_vacio_y_componentes_inutilizables_no_imponen_unicidad(self):
        for ambiente in ("HOMOLOGACION", "PRODUCCION", None):
            with self.subTest(ambiente=ambiente):
                conexion = self._conexion()
                migrar_indices_unicos_factura_arca(conexion.cursor())
                for campo in ("emisor", "pv", "tipo", "numero"):
                    for valor in (None, 0, -1):
                        for _repeticion in range(2):
                            self._insertar(conexion, ambiente, cae=" ", **{campo: valor})
                self.assertEqual(conexion.execute("SELECT COUNT(*) FROM factura_arca").fetchone()[0], 24)

    def test_duplicados_historicos_rechazan_grupo_sin_cambiar_datos(self):
        for clave in ("identidad", "cae"):
            with self.subTest(clave=clave):
                conexion = self._conexion()
                self._insertar(conexion, None)
                self._insertar(conexion, None, numero=8 if clave == "identidad" else 9,
                               cae="222" if clave == "identidad" else " 111 ")
                rechazar_sin_cambios(self, conexion)
                rechazar_sin_cambios(self, conexion)
                indices = IndicesUnicosFacturaArcaTest._indices_existentes(conexion)
                self.assertEqual(indices, set())

    def test_migra_indices_anteriores_y_repite_sin_cambiar_ddl_ni_datos(self):
        conexion = self._conexion()
        self._insertar(conexion, "HOMOLOGACION")
        conexion.execute(HISTORICO_IDENTIDAD)
        conexion.execute(HISTORICO_CAE)
        for nombre in (INDICE_IDENTIDAD, INDICE_CAE):
            self.assertEqual(database._validar_indice_fiscal_sqlite(
                conexion.cursor(), nombre, "factura_arca"), "HISTORICA")
        with redirect_stdout(io.StringIO()):
            migrar_indices_unicos_factura_arca(conexion.cursor())
        self._insertar(conexion, "PRODUCCION")
        self._insertar(conexion, None)
        ddl = conexion.execute("SELECT name,sql FROM sqlite_master WHERE type='index' ORDER BY name").fetchall()
        antes = conexion.execute("SELECT * FROM factura_arca").fetchall()
        salida = io.StringIO()
        with redirect_stdout(salida):
            migrar_indices_unicos_factura_arca(conexion.cursor())
        self.assertEqual(salida.getvalue(), "")
        self.assertEqual(conexion.execute("SELECT name,sql FROM sqlite_master WHERE type='index' ORDER BY name").fetchall(), ddl)
        self.assertEqual(conexion.execute("SELECT * FROM factura_arca").fetchall(), antes)

    def test_indice_historico_se_conserva_si_trim_impide_reemplazo(self):
        for ambiente in ("HOMOLOGACION", None):
            with self.subTest(ambiente=ambiente):
                conexion = self._conexion()
                self._insertar(conexion, ambiente)
                self._insertar(conexion, ambiente, numero=9, cae=" 111 ")
                conexion.execute(HISTORICO_CAE)
                antes = conexion.execute("SELECT * FROM factura_arca").fetchall()
                rechazar_sin_cambios(self, conexion)
                indices = IndicesUnicosFacturaArcaTest._indices_existentes(conexion)
                self.assertEqual(indices, {INDICE_CAE})
                self.assertEqual(conexion.execute("SELECT * FROM factura_arca").fetchall(), antes)

    def test_sql_artificial_desconocido_se_rechaza_sin_eliminar_indice(self):
        conexion = self._conexion()
        self._insertar(conexion, None)
        conexion.execute(
            f"CREATE UNIQUE INDEX {INDICE_CAE} ON factura_arca(cae) "
            "WHERE TRIM(COALESCE(cae,'')) <> ''"
        )
        rechazar_sin_cambios(self, conexion, ValueError)

    def test_migracion_y_repeticion_respetan_savepoint_y_rollback_del_llamador(self):
        conexion = self._conexion()
        conexion.execute(HISTORICO_CAE)
        conexion.commit()
        antes = foto(conexion, "factura_arca")
        conexion.execute("BEGIN")
        self._insertar(conexion, None)
        pendiente = foto(conexion, "factura_arca")
        conexion.execute("SAVEPOINT llamador")
        migrar_indices_unicos_factura_arca(conexion.cursor())
        actual = foto(conexion, "factura_arca")
        migrar_indices_unicos_factura_arca(conexion.cursor())
        self.assertEqual(foto(conexion, "factura_arca"), actual)
        self.assertTrue(conexion.in_transaction)
        conexion.execute("ROLLBACK TO llamador")
        self.assertEqual(foto(conexion, "factura_arca"), pendiente)
        conexion.execute("RELEASE llamador")
        conexion.rollback()
        self.assertEqual(foto(conexion, "factura_arca"), antes)

    def test_rechazo_conserva_cambios_pendientes_y_savepoint_exterior(self):
        conexion = self._conexion()
        conexion.execute(HISTORICO_CAE)
        conexion.commit()
        self._insertar(conexion, None)
        self._insertar(conexion, None, numero=9, cae=" 111 ")
        conexion.execute("SAVEPOINT llamador")
        rechazar_sin_cambios(self, conexion)
        conexion.execute("ROLLBACK TO llamador")
        conexion.execute("RELEASE llamador")
        self.assertEqual(conexion.execute("SELECT COUNT(*) FROM factura_arca").fetchone(), (2,))
        conexion.rollback()
        self.assertEqual(conexion.execute("SELECT COUNT(*) FROM factura_arca").fetchone(), (0,))


class GuardiaIndicesAntiguosTest(unittest.TestCase):
    def test_conexiones_fisicas_y_uri_rechazadas(self):
        for conectar in (sqlite3.connect, sqlite3.dbapi2.connect):
            for base, opciones in (("prohibida.db", {}), ("file::memory:", {"uri": True}),
                                   (":memory:", {"uri": True})):
                with self.subTest(base=base, opciones=opciones), self.assertRaises(AssertionError):
                    conectar(base, **opciones)

    def test_attach_y_user_version_rechazados(self):
        conexion = sqlite3.connect(":memory:")
        self.addCleanup(conexion.close)
        for sql in ("ATTACH DATABASE ':memory:' AS ajena", "PRAGMA user_version=9",
                    "PRAGMA main.user_version=9"):
            with self.subTest(sql=sql), self.assertRaises(sqlite3.DatabaseError):
                conexion.execute(sql)
        self.assertEqual(conexion.execute("PRAGMA user_version").fetchone(), (0,))

    def test_arranque_y_migraciones_ajenas_rechazados(self):
        with self.assertRaises(ModuleNotFoundError):
            importlib.import_module("main")
        for nombre in ("crear_base", "conectar", "migrar_factura_arca_columnas_normalizadas",
                       "crear_tabla_intentos_emision_arca"):
            with self.subTest(nombre=nombre), self.assertRaisesRegex(AssertionError, "Funcion prohibida"):
                with guardia_fiscal():
                    argumentos = () if nombre in ("crear_base", "conectar") else (None,)
                    getattr(database, nombre)(*argumentos)


if __name__ == "__main__":
    unittest.main()
