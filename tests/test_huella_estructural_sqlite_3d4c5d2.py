"""Etapa 3D.4C.5D.2: huella estructural canónica SQLite (solo bases ficticias).

Usa exclusivamente bases en memoria o en directorios temporales. No abre bases
reales, no ejecuta main.py y no escribe application_id ni user_version en ninguna
base inspeccionada.
"""

import ast
import hashlib
import re
import sqlite3
import tempfile
import unittest
from pathlib import Path

from services import sqlite_huella_estructural as modulo
from services.sqlite_huella_estructural import (
    FORMATO_HUELLA_ESTRUCTURAL,
    calcular_huella_estructural_sqlite as huella,
)
from tests.test_compatibilidad_esquemas_historicos_3d4c5c2 import ESQUEMAS_HISTORICOS, database

_CONECTAR = sqlite3.connect

BASE = (
    "CREATE TABLE padre(id INTEGER PRIMARY KEY, nombre TEXT NOT NULL DEFAULT '')",
    "CREATE TABLE par(a INTEGER, b INTEGER, PRIMARY KEY(a, b))",
    "CREATE TABLE hija(id INTEGER PRIMARY KEY AUTOINCREMENT, padre_id INTEGER NOT NULL, a INTEGER, b INTEGER, "
    "estado TEXT DEFAULT 'A' CHECK(estado IN ('A','B')), monto REAL, UNIQUE(padre_id, a), "
    "FOREIGN KEY(padre_id) REFERENCES padre(id), FOREIGN KEY(a, b) REFERENCES par(a, b))",
    "CREATE UNIQUE INDEX idx_hija ON hija(padre_id, estado) WHERE monto > 0",
    "CREATE INDEX idx_hija_monto ON hija(monto DESC)",
)


def _memoria(sentencias):
    conexion = _CONECTAR(":memory:")
    unittest.addModuleCleanup(conexion.close)
    for sql in sentencias:
        conexion.execute(sql)
    conexion.commit()
    return conexion


def _huella_de(sentencias):
    resultado = huella(_memoria(sentencias))
    assert resultado.confiable, resultado.razones
    return resultado.huella


def _mutar(*cambios, agregar=()):
    sql = "\n".join(BASE)
    for original, nuevo in cambios:
        assert original in sql, original
        sql = sql.replace(original, nuevo, 1)
    return tuple(sql.split("\n")) + tuple(agregar)


def _esquema_historico(nombre):
    return tuple(sql for _, _, _, sql in ESQUEMAS_HISTORICOS[nombre][2])


def _migrada_con_crear_base(nombre):
    conexion = _memoria(_esquema_historico(nombre))
    conexion.execute("BEGIN IMMEDIATE")
    database.crear_base(conexion=conexion)
    conexion.commit()
    return conexion


def _actual():
    conexion = _CONECTAR(":memory:")
    unittest.addModuleCleanup(conexion.close)
    conexion.execute("BEGIN IMMEDIATE")
    database.crear_base(conexion=conexion)
    conexion.commit()
    return conexion


class DeterminismoTest(unittest.TestCase):

    def test_resultado_confiable_con_formato_y_huella_sha256(self):
        resultado = huella(_memoria(BASE))
        self.assertTrue(resultado.confiable)
        self.assertEqual(resultado.formato, FORMATO_HUELLA_ESTRUCTURAL)
        self.assertRegex(resultado.huella, r"^[0-9a-f]{64}$")
        self.assertEqual(resultado.razones, ())

    def test_misma_estructura_misma_huella_en_memoria_y_en_archivo(self):
        with tempfile.TemporaryDirectory(prefix="fm_3d4c5d2_") as carpeta:
            ruta = Path(carpeta) / "ficticia.db"
            conexion = _CONECTAR(ruta)
            for sql in BASE:
                conexion.execute(sql)
            conexion.commit()
            conexion.close()
            solo_lectura = _CONECTAR(ruta.as_uri() + "?mode=ro", uri=True)
            try:
                self.assertEqual(huella(solo_lectura).huella, _huella_de(BASE))
            finally:
                solo_lectura.close()

    def test_datos_marcadores_y_sqlite_sequence_no_forman_parte_de_la_huella(self):
        referencia = _huella_de(BASE)
        conexion = _memoria(BASE)
        conexion.execute("INSERT INTO padre(id, nombre) VALUES (1, 'Dato ficticio')")
        conexion.execute("INSERT INTO hija(padre_id) VALUES (1)")
        conexion.execute("PRAGMA user_version=7")
        conexion.execute("PRAGMA application_id=1234")
        conexion.commit()
        self.assertEqual(huella(conexion).huella, referencia)

    def test_delete_y_wal_producen_la_misma_huella(self):
        with tempfile.TemporaryDirectory(prefix="fm_3d4c5d2_") as carpeta:
            resultados = {}
            for modo in ("DELETE", "WAL"):
                ruta = Path(carpeta) / f"{modo}.db"
                conexion = _CONECTAR(ruta)
                self.assertEqual(conexion.execute(f"PRAGMA journal_mode={modo}").fetchone()[0].upper(), modo)
                for sql in BASE:
                    conexion.execute(sql)
                conexion.commit()
                resultados[modo] = huella(conexion).huella
                conexion.close()
            self.assertEqual(resultados["DELETE"], resultados["WAL"])
            self.assertEqual(resultados["DELETE"], _huella_de(BASE))


class EquivalenciasDeFormatoTest(unittest.TestCase):
    """Diferencias irrelevantes no deben producir falsos rechazos."""

    def test_formato_comentarios_identificadores_y_orden_de_objetos(self):
        variante = (
            "-- comentario\nCREATE TABLE IF NOT EXISTS \"par\" (\n  A integer,\n  [b] INTEGER ,\n  PRIMARY KEY ( a , b )\n)",
            "CREATE TABLE padre ( id integer PRIMARY KEY , `nombre` text NOT NULL /* c */ DEFAULT ''\n)",
            "create table hija(\n id INTEGER PRIMARY KEY AUTOINCREMENT,\n padre_id INTEGER NOT NULL,\n a INTEGER,\n b INTEGER,\n"
            " estado TEXT DEFAULT 'A' CHECK ( estado   IN ('A', 'B') ),\n monto real,\n UNIQUE ( padre_id , a ),\n"
            " FOREIGN KEY (padre_id) REFERENCES padre (id),\n FOREIGN KEY (a,b) REFERENCES par(a,b)\n)",
            "CREATE INDEX idx_hija_monto ON hija ( monto DESC )",
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_hija ON hija(padre_id, estado)\n WHERE monto>0",
        )
        self.assertEqual(_huella_de(variante), _huella_de(BASE))

    def test_columna_agregada_con_alter_no_cambia_la_identidad(self):
        sentencias = list(BASE)
        sentencias[2] = sentencias[2].replace(", monto REAL", "")
        sentencias.insert(3, "ALTER TABLE hija ADD COLUMN monto REAL")
        self.assertEqual(_huella_de(tuple(sentencias)), _huella_de(BASE))

    def test_referencia_implicita_a_la_pk_equivale_a_la_explicita(self):
        implicita = _mutar(("REFERENCES padre(id)", "REFERENCES padre"), ("REFERENCES par(a, b)", "REFERENCES par"))
        self.assertEqual(_huella_de(implicita), _huella_de(BASE))

    def test_clave_foranea_en_linea_equivale_a_la_de_tabla(self):
        en_linea = _mutar(
            ("padre_id INTEGER NOT NULL,", "padre_id INTEGER NOT NULL REFERENCES padre(id),"),
            ("FOREIGN KEY(padre_id) REFERENCES padre(id), ", ""),
        )
        self.assertEqual(_huella_de(en_linea), _huella_de(BASE))

    def test_asc_explicito_nombre_de_restriccion_y_mayusculas_de_tipos(self):
        variante = _mutar(
            ("hija(padre_id, estado)", "hija(padre_id ASC, estado ASC)"),
            ("UNIQUE(padre_id, a)", "CONSTRAINT uq_hija UNIQUE(padre_id, a)"),
            ("monto REAL", "monto real"),
        )
        self.assertEqual(_huella_de(variante), _huella_de(BASE))


class CambiosRelevantesTest(unittest.TestCase):
    """Cada cambio estructural debe modificar la huella."""

    def test_cada_alteracion_cambia_la_huella(self):
        referencia = _huella_de(BASE)
        casos = {
            "tipo_columna": _mutar(("monto REAL", "monto INTEGER")),
            "not_null_quitado": _mutar(("padre_id INTEGER NOT NULL", "padre_id INTEGER")),
            "default_valor": _mutar(("DEFAULT 'A'", "DEFAULT 'B'")),
            "default_mayusculas_de_literal": _mutar(("DEFAULT 'A'", "DEFAULT 'a'")),
            "default_texto_vacio_vs_espacio": _mutar(("DEFAULT ''", "DEFAULT ' '")),
            "pk_compuesta_orden": _mutar(("PRIMARY KEY(a, b)", "PRIMARY KEY(b, a)")),
            "autoincrement_quitado": _mutar(("PRIMARY KEY AUTOINCREMENT", "PRIMARY KEY")),
            "fk_on_delete": _mutar(("REFERENCES padre(id),", "REFERENCES padre(id) ON DELETE CASCADE,")),
            "fk_on_update": _mutar(("REFERENCES padre(id),", "REFERENCES padre(id) ON UPDATE CASCADE,")),
            "fk_diferible": _mutar(("REFERENCES padre(id),", "REFERENCES padre(id) DEFERRABLE INITIALLY DEFERRED,")),
            "fk_compuesta_columnas_padre": _mutar(("REFERENCES par(a, b)", "REFERENCES par(b, a)")),
            "fk_compuesta_columnas_hijas": _mutar(("FOREIGN KEY(a, b) REFERENCES par(a, b)", "FOREIGN KEY(b, a) REFERENCES par(a, b)")),
            "fk_eliminada": _mutar((", FOREIGN KEY(padre_id) REFERENCES padre(id)", "")),
            "fk_otra_tabla_padre": _mutar(("REFERENCES padre(id)", "REFERENCES par(a)")),
            "unique_orden": _mutar(("UNIQUE(padre_id, a)", "UNIQUE(a, padre_id)")),
            "unique_eliminada": _mutar((", UNIQUE(padre_id, a)", "")),
            "indice_deja_de_ser_unico": _mutar(("CREATE UNIQUE INDEX idx_hija", "CREATE INDEX idx_hija")),
            "indice_condicion_parcial": _mutar(("WHERE monto > 0", "WHERE monto > 1")),
            "indice_sin_condicion": _mutar((" WHERE monto > 0", "")),
            "indice_orden_columna": _mutar(("monto DESC", "monto ASC")),
            "indice_colacion": _mutar(("monto DESC", "monto COLLATE NOCASE DESC")),
            "indice_renombrado": _mutar(("idx_hija_monto", "idx_hija_importe")),
            "indice_columnas": _mutar(("hija(padre_id, estado)", "hija(estado, padre_id)")),
            "check_valor": _mutar(("('A','B')", "('A','C')")),
            "check_eliminado": _mutar((" CHECK(estado IN ('A','B'))", "")),
            "colacion_de_columna": _mutar(("estado TEXT", "estado TEXT COLLATE NOCASE")),
            "on_conflict": _mutar(("padre_id INTEGER NOT NULL", "padre_id INTEGER NOT NULL ON CONFLICT IGNORE")),
            "sin_rowid": _mutar(("PRIMARY KEY(a, b))", "PRIMARY KEY(a, b)) WITHOUT ROWID")),
            "estricta": _mutar(("DEFAULT '')", "DEFAULT '') STRICT")),
            "columna_extra": _mutar(("monto REAL,", "monto REAL, extra TEXT,")),
            "tabla_extra": _mutar(agregar=("CREATE TABLE ajena(id INTEGER PRIMARY KEY)",)),
            "indice_extra": _mutar(agregar=("CREATE INDEX idx_extra ON hija(a)",)),
            "trigger": _mutar(agregar=(
                "CREATE TRIGGER trg_ajeno AFTER INSERT ON hija BEGIN SELECT 1; END",
            )),
            "vista": _mutar(agregar=("CREATE VIEW v_hija AS SELECT id FROM hija",)),
        }
        huellas = {}
        for nombre, sentencias in casos.items():
            with self.subTest(cambio=nombre):
                valor = _huella_de(sentencias)
                self.assertNotEqual(valor, referencia)
                huellas[nombre] = valor
        self.assertEqual(len(set(huellas.values())), len(huellas), "dos alteraciones distintas coinciden")

    def test_tabla_faltante_y_nombre_distinto_cambian_la_huella(self):
        referencia = _huella_de(BASE)
        sin_padre = tuple(s for s in BASE if "TABLE padre" not in s)
        self.assertNotEqual(_huella_de(sin_padre), referencia)
        renombrada = _mutar(("CREATE TABLE padre(", "CREATE TABLE padre2("), ("REFERENCES padre(id)", "REFERENCES padre2(id)"))
        self.assertNotEqual(_huella_de(renombrada), referencia)

    def test_trigger_y_vista_cambian_con_su_cuerpo(self):
        t1 = _mutar(agregar=("CREATE TRIGGER t AFTER INSERT ON hija BEGIN SELECT 1; END",))
        t2 = _mutar(agregar=("CREATE TRIGGER t AFTER INSERT ON hija BEGIN SELECT 2; END",))
        self.assertNotEqual(_huella_de(t1), _huella_de(t2))
        v1 = _mutar(agregar=("CREATE VIEW v AS SELECT id FROM hija",))
        v2 = _mutar(agregar=("CREATE VIEW v AS SELECT id FROM hija WHERE id > 0",))
        self.assertNotEqual(_huella_de(v1), _huella_de(v2))


class EsquemasRealesFicticiosTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.actual = huella(_actual())
        cls.historicos = {nombre: huella(_memoria(_esquema_historico(nombre))) for nombre in ESQUEMAS_HISTORICOS}

    def test_esquema_actual_de_crear_base_es_confiable(self):
        self.assertTrue(self.actual.confiable, self.actual.razones)
        self.assertEqual(len(self.actual.representacion["tablas"]), 18)
        self.assertEqual(self.actual.representacion["triggers_y_vistas"], [])

    def test_los_ocho_historicos_son_confiables_y_distintos_entre_si(self):
        self.assertEqual(len(self.historicos), 8)
        for nombre, resultado in self.historicos.items():
            with self.subTest(esquema=nombre):
                self.assertTrue(resultado.confiable, resultado.razones)
        self.assertEqual(len({r.huella for r in self.historicos.values()}), 8)

    def test_el_historico_mas_reciente_coincide_con_el_actual_y_solo_ese(self):
        coincidentes = {n for n, r in self.historicos.items() if r.huella == self.actual.huella}
        self.assertEqual(coincidentes, {"arca_config_ambiente_599d0f5"})

    def test_ocho_historicos_migrados_en_memoria_con_crear_base(self):
        """Observación: no todo histórico migrado converge al esquema actual."""
        convergen = {
            "build_0_5_52b0189", "esenciales_16_8a362a5", "arca_intentos_af3e31e",
            "arca_indices_unicos_0fe8ac7", "arca_config_ambiente_599d0f5",
        }
        for nombre in ESQUEMAS_HISTORICOS:
            with self.subTest(esquema=nombre):
                resultado = huella(_migrada_con_crear_base(nombre))
                self.assertTrue(resultado.confiable)
                self.assertEqual(resultado.huella == self.actual.huella, nombre in convergen)

    def test_diferencias_de_los_migrados_que_no_convergen(self):
        actuales = {t["nombre"]: t for t in self.actual.representacion["tablas"]}
        esperado = {
            "build_0_2_2_9b6a850": {"clientes": ["columnas"]},
            "build_0_7_8c81526": {"resumenes": ["claves_foraneas"]},
            "build_1_7_4994dc6": {"resumenes": ["claves_foraneas"]},
        }
        for nombre, diferencias in esperado.items():
            with self.subTest(esquema=nombre):
                migrada = {t["nombre"]: t for t in huella(_migrada_con_crear_base(nombre)).representacion["tablas"]}
                observado = {
                    tabla: sorted(campo for campo in actuales[tabla] if actuales[tabla][campo] != migrada[tabla][campo])
                    for tabla in actuales if actuales[tabla] != migrada[tabla]
                }
                self.assertEqual(observado, diferencias)

    def test_una_alteracion_del_esquema_actual_se_detecta(self):
        alteraciones = (
            "ALTER TABLE clientes ADD COLUMN columna_ajena TEXT",
            "CREATE TABLE tabla_ajena(id INTEGER PRIMARY KEY)",
            "CREATE INDEX idx_ajeno ON clientes(id)",
            "DROP INDEX idx_factura_arca_estado",
            "CREATE TRIGGER trg_ajeno AFTER INSERT ON clientes BEGIN SELECT 1; END",
            "CREATE VIEW vista_ajena AS SELECT id FROM clientes",
        )
        for sql in alteraciones:
            with self.subTest(sql=sql):
                conexion = _actual()
                conexion.execute(sql)
                self.assertNotEqual(huella(conexion).huella, self.actual.huella)


class NoConfiableTest(unittest.TestCase):

    def test_columna_generada_no_produce_huella(self):
        for ddl in (
            "CREATE TABLE g(a INTEGER, b INTEGER GENERATED ALWAYS AS (a+1) VIRTUAL)",
            "CREATE TABLE g(a INTEGER, b INTEGER AS (a+1) STORED)",
        ):
            with self.subTest(ddl=ddl):
                resultado = huella(_memoria((ddl,)))
                self.assertFalse(resultado.confiable)
                self.assertIsNone(resultado.huella)
                self.assertIsNone(resultado.representacion)
                self.assertTrue(resultado.razones)

    def test_tabla_virtual_no_produce_huella(self):
        conexion = _CONECTAR(":memory:")
        self.addCleanup(conexion.close)
        try:
            conexion.execute("CREATE VIRTUAL TABLE v USING rtree(id, minx, maxx)")
        except sqlite3.Error:
            self.skipTest("rtree no disponible")
        resultado = huella(conexion)
        self.assertFalse(resultado.confiable)
        self.assertIsNone(resultado.huella)

    def test_sql_no_analizable_se_rechaza(self):
        for sql in ("CREATE TABLE t(a TEXT DEFAULT 'sin cierre)", "CREATE TABLE t(a /* sin cierre"):
            with self.subTest(sql=sql):
                with self.assertRaises(modulo._NoRepresentable):
                    modulo._tokenizar(sql)

    def test_error_de_sqlite_es_cerrado_y_sanitizado(self):
        class Falla(sqlite3.Connection):
            def cursor(self, *args, **kwargs):
                raise sqlite3.OperationalError("no such table: clientes_secretos en C:\\ruta\\privada.db")

        conexion = _CONECTAR(":memory:", factory=Falla)
        self.addCleanup(conexion.close)
        resultado = huella(conexion)
        self.assertFalse(resultado.confiable)
        self.assertEqual(resultado.razones, ("error_sqlite",))
        self.assertNotIn("privada", repr(resultado))

    def test_conexion_cerrada_no_produce_huella(self):
        conexion = _memoria(BASE)
        conexion.close()
        resultado = huella(conexion)
        self.assertFalse(resultado.confiable)
        self.assertIsNone(resultado.huella)

    def test_cambio_de_esquema_durante_la_lectura_se_rechaza(self):
        conexion = _memoria(BASE)

        class CursorQueCambia:
            lecturas = 0

            def __init__(self, real):
                self._real = real
                self._es_version = False

            def execute(self, sql, *args):
                self._es_version = sql == "PRAGMA schema_version"
                return self._real.execute(sql, *args)

            def fetchone(self):
                if self._es_version:
                    CursorQueCambia.lecturas += 1
                    return (CursorQueCambia.lecturas,)
                return self._real.fetchone()

            def __getattr__(self, nombre):
                return getattr(self._real, nombre)

        class Conexion(sqlite3.Connection):
            def cursor(self, *args, **kwargs):
                return CursorQueCambia(super().cursor(*args, **kwargs))

        envuelta = _CONECTAR(":memory:", factory=Conexion)
        self.addCleanup(envuelta.close)
        for sql in BASE:
            envuelta.execute(sql)
        resultado = huella(envuelta)
        self.assertFalse(resultado.confiable)
        self.assertEqual(resultado.razones, ("esquema_cambio_durante_lectura",))
        self.assertTrue(huella(conexion).confiable)

    def test_entrada_ajena_lanza_typeerror(self):
        for valor in (None, ":memory:", object()):
            with self.subTest(valor=valor):
                with self.assertRaises(TypeError):
                    huella(valor)


class SoloLecturaTest(unittest.TestCase):

    def test_no_escribe_ni_altera_la_base_ni_deja_archivos_auxiliares(self):
        with tempfile.TemporaryDirectory(prefix="fm_3d4c5d2_") as carpeta:
            ruta = Path(carpeta) / "ficticia.db"
            origen = _CONECTAR(ruta)
            origen.execute("BEGIN IMMEDIATE")
            database.crear_base(conexion=origen)
            origen.execute("INSERT INTO clientes(id, nombre) VALUES (1, 'Cliente ficticio')")
            origen.commit()
            origen.close()

            hash_antes = hashlib.sha256(ruta.read_bytes()).hexdigest()
            archivos_antes = sorted(p.name for p in Path(carpeta).iterdir())
            conexion = _CONECTAR(ruta.as_uri() + "?mode=ro", uri=True)
            try:
                esquema_antes = conexion.execute("SELECT type, name, sql FROM sqlite_master ORDER BY name").fetchall()
                sentencias = []
                conexion.set_trace_callback(sentencias.append)
                cambios = conexion.total_changes
                resultado = huella(conexion)
                conexion.set_trace_callback(None)
                self.assertTrue(resultado.confiable)
                self.assertEqual(conexion.total_changes, cambios)
                self.assertFalse(conexion.in_transaction)
                self.assertEqual(
                    conexion.execute("SELECT type, name, sql FROM sqlite_master ORDER BY name").fetchall(),
                    esquema_antes,
                )
                self.assertEqual(conexion.execute("SELECT COUNT(*) FROM clientes").fetchone(), (1,))
                self.assertEqual(conexion.execute("PRAGMA user_version").fetchone(), (0,))
                self.assertEqual(conexion.execute("PRAGMA application_id").fetchone(), (0,))
            finally:
                conexion.close()
            self.assertEqual(hashlib.sha256(ruta.read_bytes()).hexdigest(), hash_antes)
            self.assertEqual(sorted(p.name for p in Path(carpeta).iterdir()), archivos_antes)
            self.assertTrue(sentencias)
            for sentencia in sentencias:
                self.assertTrue(sentencia.lstrip().upper().startswith(("SELECT", "PRAGMA")), sentencia[:80])
                self.assertNotRegex(sentencia, r"(?i)^\s*PRAGMA\s+[\w.]+\s*=")

    def test_el_modulo_no_contiene_sentencias_de_escritura_ni_rutas(self):
        arbol = ast.parse(Path(modulo.__file__).read_text(encoding="utf-8"))
        docstrings = {
            id(nodo.body[0].value)
            for nodo in ast.walk(arbol)
            if isinstance(nodo, (ast.Module, ast.FunctionDef, ast.ClassDef))
            and nodo.body and isinstance(nodo.body[0], ast.Expr) and isinstance(nodo.body[0].value, ast.Constant)
        }
        literales = [
            n.value for n in ast.walk(arbol)
            if isinstance(n, ast.Constant) and isinstance(n.value, str) and id(n) not in docstrings
        ]
        escritura = re.compile(
            r"^\s*(INSERT|UPDATE|DELETE|DROP|ALTER|REPLACE|VACUUM|ATTACH|CREATE|BEGIN|COMMIT|ROLLBACK)\b"
            r"|^\s*PRAGMA\s+[\w.]+\s*=",
            re.IGNORECASE,
        )
        self.assertEqual([s for s in literales if escritura.search(s)], [])
        importados = {
            alias.name for n in ast.walk(arbol) if isinstance(n, (ast.Import, ast.ImportFrom))
            for alias in n.names
        } | {n.module for n in ast.walk(arbol) if isinstance(n, ast.ImportFrom)}
        self.assertEqual(importados & {"runtime_paths", "database", "backup_service"}, set())
        atributos = {n.attr for n in ast.walk(arbol) if isinstance(n, ast.Attribute)}
        self.assertFalse(atributos & {"connect", "backup", "executescript", "commit", "rollback"})

    def test_objetos_temporales_se_informan_y_no_alteran_la_huella(self):
        conexion = _memoria(BASE)
        referencia = huella(conexion)
        conexion.execute("CREATE TEMP TABLE temporal_ficticia(id INTEGER)")
        resultado = huella(conexion)
        self.assertEqual(resultado.huella, referencia.huella)
        self.assertEqual(referencia.objetos_temporales, 0)
        self.assertGreater(resultado.objetos_temporales, 0)


class PoliticaIntactaTest(unittest.TestCase):

    def test_la_huella_no_esta_integrada_y_la_politica_rechaza_todo(self):
        self.assertFalse(hasattr(database, "calcular_huella_estructural_sqlite"))
        for estado in ("NUEVA", "ACTUAL", "HISTORICA_SIN_VERSION", "INCOMPLETA", "BLOQUEADA", "VERSION_INCOMPATIBLE"):
            with self.subTest(estado=estado):
                decision = database.evaluar_autorizacion_arranque_sqlite(
                    database.ResultadoInspeccionBaseSQLite(estado)
                )
                self.assertFalse(decision.autorizado)


if __name__ == "__main__":
    unittest.main()
