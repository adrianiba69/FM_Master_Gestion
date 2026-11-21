"""Etapa 3D.4C.5C.4: contraste del detector SQLite con el esquema creado por crear_base().

Solo bases ficticias: un archivo en un directorio temporal aislado y bases en memoria.
``crear_base`` recibe siempre una conexión externa; ``sqlite3.connect`` y
``database.conectar`` quedan bloqueados mientras se ejecuta, de modo que no puede
abrirse ninguna otra base (ni la real). No se ejecuta main.py ni se integra el
detector al arranque.
"""

import hashlib
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tests.test_compatibilidad_esquemas_historicos_3d4c5c2 import ESQUEMAS_HISTORICOS, database

_CONECTAR_REAL = sqlite3.connect
_FKS_NUEVAS = (
    ("resumenes", "emisor_fiscal_id", "emisores_fiscales"),
    ("servicio_renovaciones", "resumen_id", "resumenes"),
)


def _crear_en_memoria():
    conexion = _CONECTAR_REAL(":memory:")
    conexion.execute("BEGIN IMMEDIATE")
    database.crear_base(conexion=conexion)
    conexion.commit()
    return conexion


class _EsquemaActualTest(unittest.TestCase):
    """Genera una única vez la base ficticia con el crear_base() actual."""

    @classmethod
    def setUpClass(cls):
        cls._directorio = tempfile.TemporaryDirectory(prefix="fm_3d4c5c4_")
        cls.raiz = Path(cls._directorio.name).resolve()
        cls.ruta = cls.raiz / "ficticia_crear_base.db"
        conexion = _CONECTAR_REAL(cls.ruta)
        try:
            conexion.execute("BEGIN IMMEDIATE")
            with patch.object(sqlite3, "connect", side_effect=AssertionError("connect prohibido")), \
                    patch.object(database, "conectar", side_effect=AssertionError("conectar prohibido")):
                database.crear_base(conexion=conexion)
            cls.en_transaccion_tras_crear = conexion.in_transaction
            conexion.commit()
        finally:
            conexion.close()

    @classmethod
    def tearDownClass(cls):
        cls._directorio.cleanup()

    def abrir_ro(self):
        conexion = _CONECTAR_REAL(self.ruta.as_uri() + "?mode=ro", uri=True)
        self.addCleanup(conexion.close)
        return conexion

    @staticmethod
    def _tablas(conexion):
        return {
            n for (n,) in conexion.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            )
        }


class AislamientoTest(_EsquemaActualTest):

    def test_la_base_ficticia_vive_solo_en_el_directorio_temporal(self):
        self.assertTrue(self.ruta.is_file())
        self.assertIn(self.raiz, self.ruta.parents)
        self.assertNotEqual(self.ruta.name.lower(), "fm_master.db")
        archivo = self.abrir_ro().execute("PRAGMA database_list").fetchone()[2]
        self.assertEqual(Path(archivo).resolve(), self.ruta)

    def test_crear_base_dejo_la_transaccion_al_llamador(self):
        self.assertTrue(self.en_transaccion_tras_crear)

    def test_crear_base_sin_conexion_externa_exige_conectar_y_aqui_esta_bloqueado(self):
        with patch.object(database, "conectar", side_effect=AssertionError("conectar prohibido")):
            with self.assertRaises(AssertionError):
                database.crear_base()


class ClasificacionTest(_EsquemaActualTest):

    def test_esquema_actual_es_historico_sin_version_sin_incompatibilidades(self):
        resultado = database.inspeccionar_estado_base_sqlite(self.abrir_ro())
        self.assertEqual(resultado.estado, "HISTORICA_SIN_VERSION")
        self.assertIsNone(resultado.version_registrada)
        self.assertEqual(resultado.estructuras_pendientes, ())
        self.assertEqual(resultado.condiciones_pendientes, ())
        self.assertEqual(resultado.advertencias, ())
        texto = " | ".join(resultado.motivos)
        for prohibido in ("estructura_incompatible", "integridad_sqlite_fallida", "clave_foranea_huerfana"):
            self.assertNotIn(prohibido, texto)

    def test_la_politica_rechaza_el_resultado_y_cualquier_otro_estado(self):
        resultado = database.inspeccionar_estado_base_sqlite(self.abrir_ro())
        decision = database.evaluar_autorizacion_arranque_sqlite(resultado)
        self.assertFalse(decision.autorizado)
        self.assertTrue(decision.motivo_denegacion)
        for estado in ("NUEVA", "ACTUAL", "HISTORICA_SIN_VERSION", "INCOMPLETA", "BLOQUEADA", "VERSION_INCOMPATIBLE"):
            with self.subTest(estado=estado):
                construido = database.ResultadoInspeccionBaseSQLite(estado)
                self.assertFalse(database.evaluar_autorizacion_arranque_sqlite(construido).autorizado)

    def test_la_inspeccion_en_memoria_coincide_con_la_del_archivo(self):
        en_memoria = _crear_en_memoria()
        self.addCleanup(en_memoria.close)
        self.assertEqual(
            database.inspeccionar_estado_base_sqlite(en_memoria).estado,
            database.inspeccionar_estado_base_sqlite(self.abrir_ro()).estado,
        )


class ContrasteConCatalogoTest(_EsquemaActualTest):

    def setUp(self):
        self.con = self.abrir_ro()

    def _info(self, tabla):
        return {fila[1]: fila for fila in self.con.execute(f'PRAGMA table_info("{tabla}")')}

    def test_tablas_del_catalogo_existen_y_no_hay_tablas_adicionales(self):
        self.assertEqual(self._tablas(self.con), set(database._ESTRUCTURAS_INSPECCION_ESPERADAS))

    def test_columnas_del_catalogo_existen(self):
        for tabla, columnas in database._ESTRUCTURAS_INSPECCION_ESPERADAS.items():
            with self.subTest(tabla=tabla):
                self.assertEqual(set(columnas) - set(self._info(tabla)), set())

    def test_tipos_y_not_null_esperados_coinciden(self):
        for tabla, tipos in database._TIPOS_COLUMNAS_ESPERADOS.items():
            info = self._info(tabla)
            for columna, tipo in tipos.items():
                with self.subTest(tabla=tabla, columna=columna):
                    self.assertEqual(str(info[columna][2]).strip().upper(), tipo)
        for tabla, columnas in database._COLUMNAS_NOT_NULL_ESPERADAS.items():
            info = self._info(tabla)
            for columna in columnas:
                with self.subTest(tabla=tabla, columna=columna, regla="NOT NULL"):
                    self.assertTrue(info[columna][3])

    def test_claves_primarias_son_id_en_todas_las_tablas(self):
        for tabla in self._tablas(self.con):
            with self.subTest(tabla=tabla):
                self.assertEqual([c for c, f in self._info(tabla).items() if f[5]], ["id"])

    def test_restricciones_unicas_esperadas_existen(self):
        for tabla, clave in database._RESTRICCIONES_UNICAS_ESPERADAS:
            encontrada = False
            for fila in self.con.execute(f'PRAGMA index_list("{tabla}")').fetchall():
                if fila[2] == 1 and fila[4] == 0:
                    columnas = tuple(f[2] for f in self.con.execute(f'PRAGMA index_info("{fila[1]}")'))
                    encontrada = encontrada or columnas == tuple(clave)
            with self.subTest(tabla=tabla, clave=clave):
                self.assertTrue(encontrada)

    def test_claves_foraneas_catalogadas_coinciden_exactamente_con_las_reales(self):
        reales = {
            (tabla, fila[3], fila[2])
            for tabla in self._tablas(self.con)
            for fila in self.con.execute(f'PRAGMA foreign_key_list("{tabla}")')
        }
        catalogadas = {tuple(f) for f in database._CLAVES_FORANEAS_ESPERADAS}
        self.assertEqual(catalogadas, reales)
        for fk in _FKS_NUEVAS:
            self.assertIn(fk, catalogadas)
        self.assertEqual(self.con.execute("PRAGMA foreign_key_check").fetchall(), [])

    def test_indices_fiscales_actuales_existen_y_el_detector_los_valida(self):
        indices = {n for (n,) in self.con.execute("SELECT name FROM sqlite_master WHERE type='index'")}
        for nombre, tabla, _sql in database._DEFINICIONES_INDICES_FISCALES_ACTUALES:
            with self.subTest(indice=nombre):
                self.assertIn(nombre, indices)
                database._validar_indice_fiscal_sqlite(self.con.cursor(), nombre, tabla)
        for nombre, _, _, _ in database._INDICES_UNICOS_INSPECCION_ESPERADOS:
            self.assertIn(nombre, indices)

    def test_check_de_ambiente_y_ausencia_de_marcadores_y_objetos_ajenos(self):
        sql = self.con.execute(
            "SELECT sql FROM sqlite_master WHERE name='emisor_fiscal_arca_config'"
        ).fetchone()[0]
        self.assertIn("CHECK", sql.upper())
        self.assertEqual(self.con.execute("PRAGMA user_version").fetchone(), (0,))
        self.assertEqual(self.con.execute("PRAGMA application_id").fetchone(), (0,))
        self.assertEqual(
            self.con.execute("SELECT name FROM sqlite_master WHERE type IN ('trigger','view')").fetchall(), []
        )
        self.assertFalse(
            {t.casefold() for t in self._tablas(self.con)} & database._MARCADORES_VERSION_NO_RECONOCIDOS
        )
        self.assertEqual(self.con.execute("PRAGMA quick_check").fetchall(), [("ok",)])

    def test_el_detector_no_reporta_hallazgos_estructurales_sobre_el_esquema_actual(self):
        cursor = self.con.cursor()
        self.assertEqual(
            database._incompatibilidades_estructurales_sqlite(cursor, self._tablas(self.con)), []
        )


class InspeccionNoModificaTest(_EsquemaActualTest):

    def _volcado(self, conexion):
        maestro = conexion.execute("SELECT type, name, tbl_name, sql FROM sqlite_master ORDER BY type, name").fetchall()
        filas = {
            nombre: conexion.execute(f'SELECT * FROM "{nombre}" ORDER BY rowid').fetchall()
            for nombre in self._tablas(conexion)
        }
        return maestro, filas

    def test_inspeccion_no_cambia_archivo_esquema_ni_datos_y_solo_lee(self):
        antes_hash = hashlib.sha256(self.ruta.read_bytes()).hexdigest()
        auxiliares = {s for s in ("-journal", "-wal", "-shm") if Path(str(self.ruta) + s).exists()}
        con = self.abrir_ro()
        antes = self._volcado(con)
        sentencias = []
        con.set_trace_callback(sentencias.append)
        cambios = con.total_changes
        resultado = database.inspeccionar_estado_base_sqlite(con)
        con.set_trace_callback(None)

        self.assertEqual(resultado.estado, "HISTORICA_SIN_VERSION")
        self.assertEqual(con.total_changes, cambios)
        self.assertFalse(con.in_transaction)
        self.assertEqual(self._volcado(con), antes)
        self.assertEqual(hashlib.sha256(self.ruta.read_bytes()).hexdigest(), antes_hash)
        self.assertEqual(
            {s for s in ("-journal", "-wal", "-shm") if Path(str(self.ruta) + s).exists()}, auxiliares
        )
        self.assertTrue(sentencias)
        for sentencia in sentencias:
            self.assertTrue(sentencia.lstrip().upper().startswith(("SELECT", "PRAGMA", "WITH")), sentencia[:80])
            self.assertNotRegex(sentencia, r"(?i)^\s*PRAGMA\s+[\w.]+\s*=")

    def test_inspeccion_con_filas_ficticias_tampoco_modifica(self):
        con = _crear_en_memoria()
        self.addCleanup(con.close)
        con.execute("INSERT INTO clientes (id, nombre) VALUES (1, 'Cliente ficticio')")
        con.commit()
        antes = self._volcado(con)
        cambios = con.total_changes
        resultado = database.inspeccionar_estado_base_sqlite(con)
        self.assertEqual(resultado.estado, "HISTORICA_SIN_VERSION")
        self.assertEqual(self._volcado(con), antes)
        self.assertEqual(con.total_changes, cambios)


class ClavesForaneasNuevasTest(unittest.TestCase):
    """FK resumenes.emisor_fiscal_id y servicio_renovaciones.resumen_id."""

    _SQL = {
        ("resumenes", "emisor_fiscal_id"): "CREATE TABLE resumenes(id INTEGER PRIMARY KEY AUTOINCREMENT, {col}{fk})",
        ("servicio_renovaciones", "resumen_id"): (
            "CREATE TABLE servicio_renovaciones(id INTEGER PRIMARY KEY AUTOINCREMENT, {col}{fk})"
        ),
    }
    _CORRECTA = {
        ("resumenes", "emisor_fiscal_id"): "FOREIGN KEY(emisor_fiscal_id) REFERENCES emisores_fiscales(id)",
        ("servicio_renovaciones", "resumen_id"): "FOREIGN KEY(resumen_id) REFERENCES resumenes(id)",
    }
    _INCORRECTA = {
        ("resumenes", "emisor_fiscal_id"): "FOREIGN KEY(emisor_fiscal_id) REFERENCES clientes(id)",
        ("servicio_renovaciones", "resumen_id"): "FOREIGN KEY(resumen_id) REFERENCES servicios(id)",
    }

    def _hallazgos(self, clave, columna_sql, fk):
        con = _CONECTAR_REAL(":memory:")
        self.addCleanup(con.close)
        con.execute(self._SQL[clave].format(col=columna_sql, fk=(", " + fk) if fk else ""))
        tabla, columna = clave
        hallazgos = database._incompatibilidades_estructurales_sqlite(con.cursor(), {tabla})
        return [h for h in hallazgos if h == f"clave_foranea_incompatible:{tabla}.{columna}"]

    def test_relacion_correcta_es_aceptada(self):
        for clave in self._SQL:
            with self.subTest(clave=clave):
                self.assertEqual(self._hallazgos(clave, f"{clave[1]} INTEGER", self._CORRECTA[clave]), [])

    def test_relacion_ausente_o_apuntando_a_otra_tabla_se_detecta(self):
        for clave in self._SQL:
            tabla, columna = clave
            esperado = [f"clave_foranea_incompatible:{tabla}.{columna}"]
            with self.subTest(clave=clave, caso="ausente"):
                self.assertEqual(self._hallazgos(clave, f"{columna} INTEGER", ""), esperado)
            with self.subTest(clave=clave, caso="otra_tabla"):
                self.assertEqual(self._hallazgos(clave, f"{columna} INTEGER", self._INCORRECTA[clave]), esperado)

    def test_columna_ausente_no_genera_hallazgo_de_clave_foranea(self):
        for clave in self._SQL:
            with self.subTest(clave=clave):
                self.assertEqual(self._hallazgos(clave, "otra INTEGER", ""), [])

    def test_los_ocho_esquemas_historicos_no_tienen_hallazgos_de_clave_foranea(self):
        self.assertEqual(len(ESQUEMAS_HISTORICOS), 8)
        for nombre, (_commit, _desc, objetos) in ESQUEMAS_HISTORICOS.items():
            with self.subTest(esquema=nombre):
                con = _CONECTAR_REAL(":memory:")
                self.addCleanup(con.close)
                for tipo, _n, _t, sql in objetos:
                    if tipo == "table":
                        con.execute(sql)
                tablas = {n for (n,) in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                hallazgos = database._incompatibilidades_estructurales_sqlite(con.cursor(), tablas)
                self.assertEqual([h for h in hallazgos if h.startswith("clave_foranea")], [])


if __name__ == "__main__":
    unittest.main()
