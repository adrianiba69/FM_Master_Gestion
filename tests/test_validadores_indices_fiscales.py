"""Validadores independientes: solo main en :memory:, sin migraciones."""

import sqlite3
import unittest
from dataclasses import FrozenInstanceError
from unittest.mock import patch

from tests.test_catalogo_indices_fiscales import ACTUALES, HISTORICAS, database


_CONNECT_ORIGINAL = sqlite3.connect


def _connect_solo_memoria(destino, *args, **kwargs):
    if destino != ":memory:" or kwargs.get("uri") or (len(args) > 6 and args[6]):
        raise AssertionError("Solo se permite :memory: sin URI.")
    return _CONNECT_ORIGINAL(destino, *args, **kwargs)


def setUpModule():
    global _guardia
    _guardia = patch("sqlite3.connect", _connect_solo_memoria)
    _guardia.start()


def tearDownModule():
    _guardia.stop()


def _solicitud(definicion):
    nombre, tabla, sql = definicion
    clave, condicion = sql.split(f"ON {tabla}(", 1)[1].split(") WHERE ", 1)
    return nombre, clave, condicion, tabla


class _CursorMetadatosAlterados:
    def __init__(self, cursor, pragma, transformar):
        self.cursor = cursor
        self.pragma = pragma
        self.transformar = transformar
        self.sql = ""
        self.intervenciones = 0

    def execute(self, sql, parametros=()):
        self.sql = sql
        self.cursor.execute(sql, parametros)
        return self

    def fetchall(self):
        filas = self.cursor.fetchall()
        if self.sql.startswith(self.pragma):
            self.intervenciones += 1
            return self.transformar(filas)
        return filas


class _BaseValidadores(unittest.TestCase):
    def conexion(self, **kwargs):
        conexion = sqlite3.connect(":memory:", **kwargs)
        self.addCleanup(conexion.close)
        return conexion

    def tablas(self, conexion, colacion="BINARY"):
        conexion.execute(
            "CREATE TABLE main.factura_arca(id INTEGER PRIMARY KEY, "
            f"ambiente_arca TEXT COLLATE {colacion}, emisor_id INTEGER, punto_venta_num INTEGER, "
            "tipo_comprobante_num INTEGER, numero_comprobante_num INTEGER, cae TEXT)"
        )
        conexion.execute(
            "CREATE TABLE main.intentos_emision_arca(id INTEGER PRIMARY KEY, ambiente_arca TEXT, "
            f"cuit_emisor TEXT COLLATE {colacion}, punto_venta INTEGER, tipo_comprobante INTEGER, "
            "numero_planificado INTEGER, estado TEXT)"
        )

    def foto(self, conexion):
        return (
            conexion.execute("SELECT * FROM main.sqlite_master ORDER BY type, name").fetchall(),
            conexion.execute("PRAGMA main.user_version").fetchone(),
            conexion.total_changes,
            conexion.in_transaction,
        )


class SolicitudesIndicesFiscalesTest(unittest.TestCase):
    def test_seis_destinos_actuales_con_oraculo_independiente(self):
        for definicion in ACTUALES:
            with self.subTest(nombre=definicion[0]):
                self.assertEqual(
                    database._validar_solicitud_indice_fiscal(*_solicitud(definicion)), definicion
                )

    def test_historicos_no_son_destinos_autorizados(self):
        for definicion in HISTORICAS:
            with self.subTest(nombre=definicion[0]), self.assertRaises(ValueError):
                database._validar_solicitud_indice_fiscal(*_solicitud(definicion))

    def test_rechaza_nombre_tabla_clave_predicado_y_literal_distintos(self):
        for definicion in ACTUALES:
            nombre, clave, condicion, tabla = _solicitud(definicion)
            variantes = [
                (nombre + "_otro", clave, condicion, tabla),
                (nombre, clave, condicion, "resumenes"),
                (nombre, clave + ", id", condicion, tabla),
                (nombre, clave, condicion + " OR 1=1", tabla),
                (nombre.upper(), clave, condicion, tabla),
            ]
            if "'ENVIANDO'" in condicion:
                variantes.append((nombre, clave, condicion.replace("'ENVIANDO'", "'enviando'"), tabla))
            for variante in variantes:
                with self.subTest(variante=variante), self.assertRaises(ValueError):
                    database._validar_solicitud_indice_fiscal(*variante)

    def test_tipo_invalido_produce_error_explicito(self):
        solicitud = list(_solicitud(ACTUALES[0]))
        for posicion in range(4):
            variante = solicitud.copy()
            variante[posicion] = None
            with self.subTest(posicion=posicion), self.assertRaises(TypeError):
                database._validar_solicitud_indice_fiscal(*variante)

    def test_no_conecta_y_no_modifica_catalogos(self):
        antes = (
            database._DEFINICIONES_INDICES_FISCALES_ACTUALES,
            database._DEFINICIONES_INDICES_FISCALES_HISTORICAS,
        )
        with patch("sqlite3.connect", side_effect=AssertionError("Conexion no permitida")):
            for definicion in ACTUALES:
                database._validar_solicitud_indice_fiscal(*_solicitud(definicion))
        self.assertEqual(antes, (
            database._DEFINICIONES_INDICES_FISCALES_ACTUALES,
            database._DEFINICIONES_INDICES_FISCALES_HISTORICAS,
        ))


class MetadatosIndicesFiscalesTest(_BaseValidadores):
    def test_actuales_e_historicos_se_validan_con_sqlite_real_en_memoria(self):
        for estado, definiciones in (("ACTUAL", ACTUALES), ("HISTORICA", HISTORICAS)):
            for nombre, tabla, sql in definiciones:
                with self.subTest(nombre=nombre, estado=estado):
                    conexion = self.conexion()
                    self.tablas(conexion)
                    conexion.execute(sql)
                    antes = self.foto(conexion)
                    self.assertEqual(
                        database._validar_indice_fiscal_sqlite(conexion.cursor(), nombre, tabla),
                        estado,
                    )
                    self.assertEqual(self.foto(conexion), antes)

    def test_ausencia_no_autoriza_creacion_ni_escrituras(self):
        conexion = self.conexion()
        self.tablas(conexion)
        antes = self.foto(conexion)
        for nombre, tabla, _sql in ACTUALES + HISTORICAS:
            self.assertEqual(
                database._validar_indice_fiscal_sqlite(conexion.cursor(), nombre, tabla), "AUSENTE"
            )
        self.assertEqual(self.foto(conexion), antes)

    def test_tabla_main_ausente_se_rechaza(self):
        conexion = self.conexion()
        with self.assertRaisesRegex(ValueError, "Tabla fiscal ausente"):
            database._validar_indice_fiscal_sqlite(conexion.cursor(), *ACTUALES[0][:2])

    def test_solicitud_ajena_se_rechaza_antes_de_consultar(self):
        conexion = self.conexion()
        sentencias = []
        conexion.set_trace_callback(sentencias.append)
        for nombre, tabla in (("otro", "factura_arca"), (ACTUALES[0][0], "resumenes")):
            with self.assertRaisesRegex(ValueError, "no catalogado"):
                database._validar_indice_fiscal_sqlite(conexion.cursor(), nombre, tabla)
        self.assertEqual(sentencias, [])

    def test_sql_desconocido_unicidad_predicados_y_literales_se_rechazan(self):
        for nombre, tabla, sql in ACTUALES + HISTORICAS:
            variantes = [
                sql.replace("CREATE UNIQUE INDEX", "CREATE INDEX"),
                sql.split(" WHERE ")[0],
                sql + " AND 1=1",
                sql.replace(", ", ","),
            ]
            if "'ENVIANDO'" in sql:
                variantes.append(sql.replace("'ENVIANDO'", "'enviando'"))
            for variante in variantes:
                with self.subTest(nombre=nombre, sql=variante):
                    conexion = self.conexion()
                    self.tablas(conexion)
                    conexion.execute(variante)
                    antes = self.foto(conexion)
                    with self.assertRaisesRegex(ValueError, "desconocida"):
                        database._validar_indice_fiscal_sqlite(conexion.cursor(), nombre, tabla)
                    self.assertEqual(self.foto(conexion), antes)

    def test_homonimo_sobre_otra_tabla_se_conserva(self):
        conexion = self.conexion()
        self.tablas(conexion)
        conexion.execute("CREATE TABLE main.resumenes(cae TEXT)")
        nombre, tabla, _sql = ACTUALES[2]
        conexion.execute(f"CREATE UNIQUE INDEX {nombre} ON resumenes(cae)")
        antes = self.foto(conexion)
        with self.assertRaisesRegex(ValueError, "homonimo"):
            database._validar_indice_fiscal_sqlite(conexion.cursor(), nombre, tabla)
        self.assertEqual(self.foto(conexion), antes)

    def test_objetos_de_otro_tipo_se_conservan(self):
        for tipo, cuerpo in (("TABLE", "(id INTEGER)"), ("VIEW", "AS SELECT 1 AS id")):
            with self.subTest(tipo=tipo):
                conexion = self.conexion()
                self.tablas(conexion)
                nombre, tabla, _sql = ACTUALES[0]
                conexion.execute(f"CREATE {tipo} main.{nombre} {cuerpo}")
                antes = self.foto(conexion)
                with self.assertRaisesRegex(ValueError, "homonimo"):
                    database._validar_indice_fiscal_sqlite(conexion.cursor(), nombre, tabla)
                self.assertEqual(self.foto(conexion), antes)

    def test_nombre_con_mayusculas_no_se_confunde_con_ausente(self):
        conexion = self.conexion()
        self.tablas(conexion)
        nombre, tabla, sql = ACTUALES[0]
        conexion.execute(sql.replace(nombre, nombre.upper()))
        with self.assertRaisesRegex(ValueError, "homonimo"):
            database._validar_indice_fiscal_sqlite(conexion.cursor(), nombre, tabla)

    def test_main_no_se_confunde_con_tablas_e_indices_temporales(self):
        conexion = self.conexion()
        self.tablas(conexion)
        nombre, tabla, sql = ACTUALES[2]
        conexion.execute(sql)
        conexion.execute("CREATE TEMP TABLE factura_arca(cae TEXT)")
        conexion.execute(f"CREATE UNIQUE INDEX temp.{nombre} ON factura_arca(cae)")
        self.assertEqual(
            database._validar_indice_fiscal_sqlite(conexion.cursor(), nombre, tabla), "ACTUAL"
        )

    def test_indice_solo_temporal_no_se_acepta_como_main(self):
        conexion = self.conexion()
        self.tablas(conexion)
        nombre, tabla, _sql = ACTUALES[2]
        conexion.execute("CREATE TEMP TABLE factura_arca(cae TEXT)")
        conexion.execute(f"CREATE UNIQUE INDEX temp.{nombre} ON factura_arca(cae)")
        self.assertEqual(
            database._validar_indice_fiscal_sqlite(conexion.cursor(), nombre, tabla), "AUSENTE"
        )

    def test_colaciones_heredadas_incompatibles_no_se_aceptan_por_sql(self):
        for definicion in (ACTUALES[0], ACTUALES[4]):
            with self.subTest(nombre=definicion[0]):
                conexion = self.conexion()
                self.tablas(conexion, colacion="NOCASE")
                nombre, tabla, sql = definicion
                conexion.execute(sql)
                with self.assertRaisesRegex(ValueError, "colaciones"):
                    database._validar_indice_fiscal_sqlite(conexion.cursor(), nombre, tabla)

    def test_tabla_sin_rowid_no_se_certifica_por_la_sola_definicion_sql(self):
        conexion = self.conexion()
        conexion.execute(
            "CREATE TABLE main.factura_arca(id INTEGER PRIMARY KEY, ambiente_arca TEXT, "
            "cae TEXT) WITHOUT ROWID"
        )
        nombre, tabla, sql = ACTUALES[2]
        conexion.execute(sql)
        with self.assertRaisesRegex(ValueError, "rowid"):
            database._validar_indice_fiscal_sqlite(conexion.cursor(), nombre, tabla)

    def test_row_factory_sqlite_row_no_altera_la_validacion(self):
        conexion = self.conexion()
        self.tablas(conexion)
        nombre, tabla, sql = ACTUALES[2]
        conexion.execute(sql)
        conexion.row_factory = sqlite3.Row
        self.assertEqual(
            database._validar_indice_fiscal_sqlite(conexion.cursor(), nombre, tabla), "ACTUAL"
        )

    def test_metadatos_incompatibles_aunque_el_sql_sea_actual(self):
        cambios = [
            ("PRAGMA main.index_list", 0, 2, 0),
            ("PRAGMA main.index_list", 0, 3, "u"),
            ("PRAGMA main.index_list", 0, 4, 0),
            ("PRAGMA main.index_xinfo", 0, 0, 9),
            ("PRAGMA main.index_xinfo", 0, 1, 99),
            ("PRAGMA main.index_xinfo", 0, 2, "otra"),
            ("PRAGMA main.index_xinfo", 0, 3, 1),
            ("PRAGMA main.index_xinfo", 0, 4, "NOCASE"),
            ("PRAGMA main.index_xinfo", 0, 5, 0),
            ("PRAGMA main.index_xinfo", -1, 1, -2),
        ]
        for pragma, fila, campo, valor in cambios:
            with self.subTest(pragma=pragma, campo=campo, valor=valor):
                conexion = self.conexion()
                self.tablas(conexion)
                nombre, tabla, sql = ACTUALES[0]
                conexion.execute(sql)

                def transformar(filas):
                    filas = [list(f) for f in filas]
                    filas[fila][campo] = valor
                    return filas

                cursor = _CursorMetadatosAlterados(conexion.cursor(), pragma, transformar)
                antes = self.foto(conexion)
                with self.assertRaises(ValueError):
                    database._validar_indice_fiscal_sqlite(cursor, nombre, tabla)
                self.assertEqual(cursor.intervenciones, 1)
                self.assertEqual(self.foto(conexion), antes)

    def test_metadatos_ausentes_o_extra_no_se_aceptan(self):
        for pragma in ("PRAGMA main.index_list", "PRAGMA main.index_xinfo"):
            for transformar in (lambda filas: [], lambda filas: filas + filas):
                with self.subTest(pragma=pragma, transformar=transformar):
                    conexion = self.conexion()
                    self.tablas(conexion)
                    nombre, tabla, sql = ACTUALES[0]
                    conexion.execute(sql)
                    cursor = _CursorMetadatosAlterados(conexion.cursor(), pragma, transformar)
                    with self.assertRaises(ValueError):
                        database._validar_indice_fiscal_sqlite(cursor, nombre, tabla)
                    self.assertEqual(cursor.intervenciones, 1)

    def test_solo_lectura_incluso_en_transaccion_con_filas_pendientes(self):
        conexion = self.conexion()
        self.tablas(conexion)
        nombre, tabla, sql = ACTUALES[0]
        conexion.execute(sql)
        conexion.execute("INSERT INTO main.factura_arca(id) VALUES(1)")
        antes = self.foto(conexion)
        sentencias = []
        conexion.set_trace_callback(sentencias.append)
        database._validar_indice_fiscal_sqlite(conexion.cursor(), nombre, tabla)
        conexion.set_trace_callback(None)
        self.assertEqual(self.foto(conexion), antes)
        self.assertEqual(conexion.execute("SELECT id FROM main.factura_arca").fetchall(), [(1,)])
        self.assertTrue(all(s.startswith(("SELECT", "PRAGMA main.")) for s in sentencias))
        conexion.rollback()
        self.assertEqual(conexion.execute("SELECT id FROM main.factura_arca").fetchall(), [])

    def test_errores_sqlite_no_se_convierten_en_exito(self):
        conexion = self.conexion()
        cursor = conexion.cursor()
        conexion.close()
        with self.assertRaises(sqlite3.ProgrammingError):
            database._validar_indice_fiscal_sqlite(cursor, *ACTUALES[0][:2])


class ContextoTransaccionalSQLiteTest(_BaseValidadores):
    def test_sin_transaccion_no_inicia_ni_configura_nada(self):
        conexion = self.conexion()
        antes = (conexion.in_transaction, conexion.autocommit, conexion.isolation_level, conexion.total_changes)
        sentencias = []
        conexion.set_trace_callback(sentencias.append)
        contexto = database._inspeccionar_contexto_transaccional_sqlite(conexion)
        conexion.set_trace_callback(None)
        self.assertFalse(contexto.en_transaccion)
        self.assertEqual(contexto.journal_mode, "memory")
        self.assertFalse(contexto.query_only)
        self.assertEqual(antes, (
            conexion.in_transaction, contexto.autocommit, contexto.isolation_level, conexion.total_changes
        ))
        self.assertEqual(sentencias, ["PRAGMA main.journal_mode", "PRAGMA query_only"])
        with self.assertRaises(FrozenInstanceError):
            contexto.en_transaccion = True

    def test_transaccion_exterior_y_savepoint_no_se_confirman_ni_revierten(self):
        conexion = self.conexion()
        conexion.execute("CREATE TABLE main.test(id INTEGER)")
        conexion.execute("BEGIN")
        conexion.execute("INSERT INTO main.test VALUES(1)")
        conexion.execute("SAVEPOINT llamador")
        conexion.execute("INSERT INTO main.test VALUES(2)")
        self.assertTrue(database._inspeccionar_contexto_transaccional_sqlite(conexion).en_transaccion)
        self.assertEqual(conexion.execute("SELECT id FROM main.test").fetchall(), [(1,), (2,)])
        conexion.execute("ROLLBACK TO llamador")
        conexion.execute("RELEASE llamador")
        self.assertEqual(conexion.execute("SELECT id FROM main.test").fetchall(), [(1,)])
        conexion.rollback()
        self.assertEqual(conexion.execute("SELECT id FROM main.test").fetchall(), [])

    def test_modos_de_conexion_se_informan_sin_habilitarlos(self):
        for opciones in (
            {}, {"isolation_level": None}, {"isolation_level": "IMMEDIATE"},
            {"autocommit": True}, {"autocommit": False},
        ):
            with self.subTest(opciones=opciones):
                conexion = self.conexion(**opciones)
                antes = (conexion.in_transaction, conexion.autocommit, conexion.isolation_level)
                contexto = database._inspeccionar_contexto_transaccional_sqlite(conexion)
                self.assertEqual(antes, (
                    contexto.en_transaccion, contexto.autocommit, contexto.isolation_level
                ))
                self.assertEqual(antes, (
                    conexion.in_transaction, conexion.autocommit, conexion.isolation_level
                ))

    def test_journal_off_y_query_only_solo_se_informan(self):
        conexion = self.conexion()
        conexion.execute("PRAGMA main.journal_mode=OFF")
        conexion.execute("PRAGMA query_only=ON")
        contexto = database._inspeccionar_contexto_transaccional_sqlite(conexion)
        self.assertEqual(contexto.journal_mode, "off")
        self.assertTrue(contexto.query_only)
        self.assertFalse(contexto.en_transaccion)
        self.assertEqual(conexion.execute("PRAGMA main.journal_mode").fetchone(), ("off",))
        self.assertEqual(conexion.execute("PRAGMA query_only").fetchone(), (1,))

    def test_error_de_conexion_cerrada_se_propaga(self):
        conexion = self.conexion()
        conexion.close()
        with self.assertRaises(sqlite3.ProgrammingError):
            database._inspeccionar_contexto_transaccional_sqlite(conexion)


if __name__ == "__main__":
    unittest.main()
