import io
import os
import sqlite3
import tempfile
import unittest
from contextlib import redirect_stdout

from database import migrar_factura_arca_columnas_normalizadas, migrar_indices_unicos_factura_arca

INDICE_CAE = "idx_factura_arca_cae_unico"
INDICE_IDENTIDAD = "idx_factura_arca_identidad_unica"
INDICE_CAE_HISTORICO = "idx_factura_arca_cae_historico_unico"
INDICE_IDENTIDAD_HISTORICA = "idx_factura_arca_identidad_historica_unica"


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
        salida = self._migrar_completo(conexion)
        self.assertNotIn(INDICE_IDENTIDAD, self._indices_existentes(conexion))
        self.assertIn("ADVERTENCIA", salida)
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
        salida = self._migrar_completo(conexion)
        self.assertIn("ADVERTENCIA", salida)
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
        salida = self._migrar_completo(conexion)
        indices = self._indices_existentes(conexion)
        self.assertNotIn(INDICE_CAE, indices)
        self.assertIn("HOMOLOGACION", salida)
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
        salida = self._migrar_completo(conexion)
        indices = self._indices_existentes(conexion)
        self.assertNotIn(INDICE_IDENTIDAD, indices)
        self.assertIn("ADVERTENCIA", salida)
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
        self.assertNotIn(INDICE_IDENTIDAD_HISTORICA, indices)
        self.assertIn(INDICE_IDENTIDAD, indices)
        self.assertIn("ADVERTENCIA", salida)
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

    def test_base_historica_con_duplicados_no_interrumpe_apertura(self):
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
        try:
            salida = self._migrar_completo(conexion)
        except Exception as error:  # noqa: BLE001 - la migracion no debe interrumpir el arranque
            self.fail(f"La migracion no debe lanzar excepciones sobre historicos conflictivos: {error}")
        indices = self._indices_existentes(conexion)
        self.assertIn(INDICE_CAE, indices)
        self.assertIn(INDICE_IDENTIDAD, indices)
        self.assertNotIn(INDICE_CAE_HISTORICO, indices)
        self.assertNotIn(INDICE_IDENTIDAD_HISTORICA, indices)
        self.assertIn("ADVERTENCIA", salida)
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

    def test_duplicados_historicos_omiten_solo_indice_afectado_sin_cambiar_datos(self):
        for clave in ("identidad", "cae"):
            with self.subTest(clave=clave):
                conexion = self._conexion()
                self._insertar(conexion, None)
                self._insertar(conexion, None, numero=8 if clave == "identidad" else 9,
                               cae="222" if clave == "identidad" else " 111 ")
                antes = conexion.execute("SELECT * FROM factura_arca").fetchall()
                salida = io.StringIO()
                with redirect_stdout(salida):
                    migrar_indices_unicos_factura_arca(conexion.cursor())
                    migrar_indices_unicos_factura_arca(conexion.cursor())
                omitido = INDICE_IDENTIDAD_HISTORICA if clave == "identidad" else INDICE_CAE_HISTORICO
                indices = IndicesUnicosFacturaArcaTest._indices_existentes(conexion)
                self.assertEqual(indices, {INDICE_IDENTIDAD, INDICE_CAE,
                                          INDICE_IDENTIDAD_HISTORICA, INDICE_CAE_HISTORICO} - {omitido})
                self.assertIn(omitido, salida.getvalue())
                self.assertIn("ADVERTENCIA", salida.getvalue())
                self.assertEqual(conexion.execute("SELECT * FROM factura_arca").fetchall(), antes)

    def test_migra_indices_anteriores_y_repite_sin_cambiar_ddl_ni_datos(self):
        conexion = self._conexion()
        self._insertar(conexion, "HOMOLOGACION")
        conexion.execute(f"CREATE UNIQUE INDEX {INDICE_IDENTIDAD} ON factura_arca"
                         "(emisor_id,punto_venta_num,tipo_comprobante_num,numero_comprobante_num) "
                         "WHERE numero_comprobante_num IS NOT NULL")
        conexion.execute(f"CREATE UNIQUE INDEX {INDICE_CAE} ON factura_arca(cae) "
                         "WHERE TRIM(COALESCE(cae,'')) <> ''")
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

    def test_indice_viejo_se_retira_aunque_trim_impida_reemplazo(self):
        for ambiente in ("HOMOLOGACION", None):
            with self.subTest(ambiente=ambiente):
                conexion = self._conexion()
                self._insertar(conexion, ambiente)
                self._insertar(conexion, ambiente, numero=9, cae=" 111 ")
                conexion.execute(f"CREATE UNIQUE INDEX {INDICE_CAE} ON factura_arca(cae) "
                                 "WHERE TRIM(COALESCE(cae,'')) <> ''")
                antes = conexion.execute("SELECT * FROM factura_arca").fetchall()
                with redirect_stdout(io.StringIO()):
                    migrar_indices_unicos_factura_arca(conexion.cursor())
                indices = IndicesUnicosFacturaArcaTest._indices_existentes(conexion)
                self.assertNotIn(INDICE_CAE if ambiente else INDICE_CAE_HISTORICO, indices)
                if ambiente is None:
                    self.assertIn(INDICE_CAE, indices)
                self.assertEqual(conexion.execute("SELECT * FROM factura_arca").fetchall(), antes)


if __name__ == "__main__":
    unittest.main()
