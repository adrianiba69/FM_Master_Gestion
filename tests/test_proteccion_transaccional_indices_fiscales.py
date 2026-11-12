"""Etapa 3B: prevalidacion de destinos y contexto transaccional, solo :memory:.

Aqui los auxiliares se prueban de forma aislada, sin ejecutar migraciones.
"""

import sqlite3
import sys
import unittest
from unittest.mock import patch

from tests.test_catalogo_indices_fiscales import ACTUALES, database


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


def _destino(definicion):
    nombre, tabla, sql = definicion
    clave, condicion = sql.split(f"ON {tabla}(", 1)[1].split(") WHERE ", 1)
    return nombre, tabla, clave, condicion


# Oraculo independiente: se deriva de las transcripciones literales de ACTUALES.
DESTINOS_ORACULO = tuple(_destino(definicion) for definicion in ACTUALES)


def _clase(sql):
    texto = " ".join(sql.split()).upper()
    if texto.startswith("ROLLBACK TO"):
        return "ROLLBACK TO"
    return texto.split(" ", 1)[0]


class _CursorInyector:
    """Delegado que falla en la n-esima sentencia de control indicada."""

    def __init__(self, cursor, clase=None, error=None, ocurrencia=1, sustituto=None,
                 database_list=None):
        self.cursor = cursor
        self.clase = clase
        self.error = error
        self.ocurrencia = ocurrencia
        self.sustituto = sustituto
        self.database_list = database_list
        self.vistas = 0
        self.fallos = 0
        self.ultima = ""

    def execute(self, sql, parametros=()):
        self.ultima = sql
        if self.clase is not None and _clase(sql) == self.clase:
            self.vistas += 1
            if self.vistas == self.ocurrencia:
                self.fallos += 1
                if self.sustituto is not None:
                    self.cursor.execute(self.sustituto)
                    return self
                raise self.error
        self.cursor.execute(sql, parametros)
        return self

    def fetchall(self):
        filas = self.cursor.fetchall()
        if self.database_list is not None and self.ultima.upper().startswith("PRAGMA DATABASE_LIST"):
            return self.database_list(filas)
        return filas

    def __getattr__(self, nombre):
        return getattr(self.cursor, nombre)


class PrevalidacionDestinosTest(unittest.TestCase):
    def test_catalogo_de_destinos_coincide_con_oraculo(self):
        self.assertEqual(database._DESTINOS_INDICES_FISCALES, DESTINOS_ORACULO)

    def test_seis_destinos_validos_devuelven_catalogo_actual(self):
        self.assertEqual(database._prevalidar_destinos_indices_fiscales(), ACTUALES)
        self.assertEqual(database._prevalidar_destinos_indices_fiscales(DESTINOS_ORACULO), ACTUALES)
        self.assertEqual(
            database._prevalidar_destinos_indices_fiscales(list(DESTINOS_ORACULO)), ACTUALES
        )

    def test_alteraciones_de_cada_campo_se_rechazan(self):
        for posicion, destino in enumerate(DESTINOS_ORACULO):
            nombre, tabla, clave, condicion = destino
            otra = "intentos_emision_arca" if tabla == "factura_arca" else "factura_arca"
            variantes = {
                "nombre": (nombre + "_x", tabla, clave, condicion),
                "nombre_mayusculas": (nombre.upper(), tabla, clave, condicion),
                "tabla": (nombre, otra, clave, condicion),
                "clave": (nombre, tabla, clave.split(", ", 1)[-1] + ", id", condicion),
                "predicado": (nombre, tabla, clave, condicion.replace("IS NULL", "IS NOT NULL", 1)
                              if "IS NULL" in condicion else condicion + " AND id > 0"),
                "formato": (nombre, tabla, clave, condicion.replace(" AND ", "  AND ", 1)),
            }
            if "''" in condicion:
                variantes["literal"] = (nombre, tabla, clave, condicion.replace("''", "' '", 1))
            if "'ENVIANDO'" in condicion:
                variantes["enviando"] = (nombre, tabla, clave, condicion.replace("'ENVIANDO'", "'enviando'"))
            for motivo, variante in variantes.items():
                with self.subTest(destino=nombre, motivo=motivo):
                    self.assertNotEqual(variante, destino, "CONFIGURACION: variante sin cambios")
                    destinos = list(DESTINOS_ORACULO)
                    destinos[posicion] = variante
                    with self.assertRaises(ValueError):
                        database._prevalidar_destinos_indices_fiscales(tuple(destinos))

    def test_faltantes_adicionales_repetidos_y_orden_se_rechazan(self):
        casos = {
            "faltante": DESTINOS_ORACULO[:-1],
            "vacio": (),
            "repetido": DESTINOS_ORACULO + (DESTINOS_ORACULO[0],),
            "repetido_sustituye": (DESTINOS_ORACULO[0],) + DESTINOS_ORACULO[:-1],
            "orden": DESTINOS_ORACULO[::-1],
        }
        mensajes = {
            "faltante": "faltantes", "vacio": "faltantes", "repetido": "repetidos",
            "repetido_sustituye": "repetidos", "orden": "orden",
        }
        for motivo, destinos in casos.items():
            with self.subTest(motivo=motivo):
                with self.assertRaisesRegex(ValueError, mensajes[motivo]):
                    database._prevalidar_destinos_indices_fiscales(destinos)

    def test_adicional_no_catalogado_se_rechaza(self):
        extra = ("idx_factura_arca_extra", "factura_arca", "cae", "cae IS NOT NULL")
        with self.assertRaisesRegex(ValueError, "no catalogado"):
            database._prevalidar_destinos_indices_fiscales(DESTINOS_ORACULO + (extra,))

    def test_tipos_invalidos(self):
        for destinos in ("texto", 42, ((1, 2, 3),), (DESTINOS_ORACULO[0][:3],),
                         ((None,) + DESTINOS_ORACULO[0][1:],)):
            with self.subTest(destinos=destinos):
                with self.assertRaises(TypeError):
                    database._prevalidar_destinos_indices_fiscales(destinos)

    def test_no_ejecuta_sql_ni_altera_catalogos(self):
        antes = (database._DESTINOS_INDICES_FISCALES,
                 database._DEFINICIONES_INDICES_FISCALES_ACTUALES,
                 database._DEFINICIONES_INDICES_FISCALES_HISTORICAS)
        llamadas_sqlite = []

        def vigilar(_frame, evento, argumento):
            if evento != "c_call":
                return
            propietario = getattr(argumento, "__self__", None)
            modulos = (getattr(argumento, "__module__", None) or "",
                       type(propietario).__module__ if propietario is not None else "")
            if any("sqlite3" in modulo for modulo in modulos):
                llamadas_sqlite.append(argumento.__qualname__)

        perfil_previo = sys.getprofile()
        with patch("sqlite3.connect", side_effect=AssertionError("SQL prohibido")):
            sys.setprofile(vigilar)
            try:
                database._prevalidar_destinos_indices_fiscales()
                with self.assertRaises(ValueError):
                    database._prevalidar_destinos_indices_fiscales(DESTINOS_ORACULO[:-1])
            finally:
                sys.setprofile(perfil_previo)
        self.assertEqual(llamadas_sqlite, [])
        sys.setprofile(vigilar)
        try:
            sqlite3.complete_statement("SELECT 1;")
        finally:
            sys.setprofile(perfil_previo)
        self.assertEqual(len(llamadas_sqlite), 1, "Control: el detector debe ver llamadas sqlite3")
        self.assertEqual(antes, (database._DESTINOS_INDICES_FISCALES,
                                 database._DEFINICIONES_INDICES_FISCALES_ACTUALES,
                                 database._DEFINICIONES_INDICES_FISCALES_HISTORICAS))


class _BaseTransaccional(unittest.TestCase):
    def conexion(self, **kwargs):
        conexion = sqlite3.connect(":memory:", **kwargs)
        self.addCleanup(conexion.close)
        conexion.execute("CREATE TABLE datos(id INTEGER PRIMARY KEY, valor TEXT)")
        conexion.execute("INSERT INTO datos VALUES(1, 'base')")
        conexion.execute("PRAGMA user_version = 7")
        if conexion.in_transaction:
            conexion.commit()
        self.sentencias = []
        conexion.set_trace_callback(self.sentencias.append)
        return conexion

    def foto(self, conexion):
        return (
            conexion.execute("SELECT type, name, tbl_name, sql FROM sqlite_master ORDER BY name").fetchall(),
            conexion.execute("SELECT * FROM datos ORDER BY id").fetchall(),
            conexion.execute("PRAGMA user_version").fetchone()[0],
        )

    def control(self):
        return [_clase(s) for s in self.sentencias
                if _clase(s) in ("BEGIN", "SAVEPOINT", "RELEASE", "ROLLBACK", "ROLLBACK TO",
                                 "COMMIT", "END")]

    def assertSinCommitNiUserVersion(self):
        textos = [" ".join(s.split()).upper() for s in self.sentencias]
        self.assertFalse([t for t in textos if t.startswith(("COMMIT", "END"))])
        self.assertFalse([t for t in textos if t.startswith("PRAGMA USER_VERSION")
                          and "=" in t and t != "PRAGMA USER_VERSION = 7"])

    def escribir(self, conexion, cur=None):
        (cur or conexion.cursor()).execute("INSERT INTO datos VALUES(2, 'bloque')")
        (cur or conexion.cursor()).execute("CREATE INDEX idx_bloque ON datos(valor)")


class ContextoTransaccionalTest(_BaseTransaccional):
    def test_sin_transaccion_previa_abre_begin_immediate_y_no_confirma(self):
        conexion = self.conexion()
        antes = self.foto(conexion)
        self.sentencias.clear()
        cur = conexion.cursor()
        with database._transaccion_indices_fiscales(cur):
            self.escribir(conexion, cur)
        self.assertTrue(conexion.in_transaction, "Debe quedar abierta para el llamador")
        self.assertEqual(self.control(), ["BEGIN", "SAVEPOINT", "RELEASE"])
        self.assertIn("BEGIN IMMEDIATE", " ".join(self.sentencias).upper())
        self.assertSinCommitNiUserVersion()
        conexion.rollback()
        self.assertEqual(self.foto(conexion), antes)

    def test_exito_queda_confirmable_por_el_llamador(self):
        conexion = self.conexion()
        cur = conexion.cursor()
        with database._transaccion_indices_fiscales(cur):
            self.escribir(conexion, cur)
        conexion.commit()
        self.assertEqual(conexion.execute("SELECT COUNT(*) FROM datos").fetchone()[0], 2)
        self.assertEqual(conexion.execute("PRAGMA user_version").fetchone()[0], 7)

    def test_fallo_sin_transaccion_previa_revierte_todo_y_relanza_mismo_error(self):
        conexion = self.conexion()
        antes = self.foto(conexion)
        original = sqlite3.IntegrityError("fallo del bloque")
        with self.assertRaises(sqlite3.IntegrityError) as capturado:
            with database._transaccion_indices_fiscales(conexion.cursor()):
                self.escribir(conexion)
                raise original
        self.assertIs(capturado.exception, original)
        self.assertFalse(conexion.in_transaction)
        self.assertEqual(self.foto(conexion), antes)
        self.assertEqual(self.control()[-3:], ["ROLLBACK TO", "RELEASE", "ROLLBACK"])
        self.assertSinCommitNiUserVersion()

    def test_transaccion_exterior_se_conserva_en_exito_y_fallo(self):
        for falla in (False, True):
            with self.subTest(falla=falla):
                conexion = self.conexion()
                antes = self.foto(conexion)
                conexion.execute("BEGIN")
                conexion.execute("INSERT INTO datos VALUES(10, 'llamador')")
                previo = self.foto(conexion)
                self.sentencias.clear()
                try:
                    with database._transaccion_indices_fiscales(conexion.cursor()):
                        self.escribir(conexion)
                        if falla:
                            raise ValueError("validacion")
                except ValueError:
                    self.assertTrue(falla)
                self.assertTrue(conexion.in_transaction)
                self.assertNotIn("BEGIN", self.control())
                self.assertNotIn("ROLLBACK", self.control())
                if falla:
                    self.assertEqual(self.foto(conexion), previo, "Cambios del llamador intactos")
                else:
                    self.assertIn((2, "bloque"), self.foto(conexion)[1])
                self.assertSinCommitNiUserVersion()
                conexion.rollback()
                self.assertEqual(self.foto(conexion), antes)

    def test_savepoint_exterior_con_y_sin_begin_se_conserva(self):
        for con_begin in (True, False):
            with self.subTest(con_begin=con_begin):
                conexion = self.conexion()
                antes = self.foto(conexion)
                if con_begin:
                    conexion.execute("BEGIN")
                conexion.execute("SAVEPOINT llamador")
                conexion.execute("INSERT INTO datos VALUES(10, 'llamador')")
                previo = self.foto(conexion)
                with self.assertRaises(sqlite3.OperationalError):
                    with database._transaccion_indices_fiscales(conexion.cursor()):
                        self.escribir(conexion)
                        raise sqlite3.OperationalError("fallo")
                self.assertEqual(self.foto(conexion), previo)
                with database._transaccion_indices_fiscales(conexion.cursor()):
                    self.escribir(conexion)
                self.assertTrue(conexion.in_transaction)
                conexion.execute("ROLLBACK TO llamador")
                conexion.execute("RELEASE llamador")
                if conexion.in_transaction:
                    conexion.rollback()
                self.assertEqual(self.foto(conexion), antes)
                self.assertSinCommitNiUserVersion()

    def test_anidado_usa_savepoints_unicos_y_revierte_solo_el_interior(self):
        conexion = self.conexion()
        cur = conexion.cursor()
        with database._transaccion_indices_fiscales(cur):
            cur.execute("INSERT INTO datos VALUES(2, 'exterior')")
            with self.assertRaises(ValueError):
                with database._transaccion_indices_fiscales(cur):
                    cur.execute("INSERT INTO datos VALUES(3, 'interior')")
                    raise ValueError("interior")
        nombres = [s.split()[1] for s in self.sentencias if s.upper().startswith("SAVEPOINT")]
        self.assertEqual(len(set(nombres)), 2)
        for nombre in nombres:
            self.assertRegex(nombre, r"^fm_indices_fiscales_[0-9]+$")
        self.assertEqual(conexion.execute("SELECT id FROM datos ORDER BY id").fetchall(), [(1,), (2,)])
        conexion.rollback()

    def test_base_exception_tambien_revierte(self):
        conexion = self.conexion()
        antes = self.foto(conexion)
        with self.assertRaises(KeyboardInterrupt):
            with database._transaccion_indices_fiscales(conexion.cursor()):
                self.escribir(conexion)
                raise KeyboardInterrupt
        self.assertFalse(conexion.in_transaction)
        self.assertEqual(self.foto(conexion), antes)


class ModosNoAdmitidosTest(_BaseTransaccional):
    def assertRechazadoSinEscribir(self, conexion, cur=None):
        antes = self.foto(conexion)
        estado = conexion.in_transaction
        self.sentencias.clear()
        ejecutado = []
        with self.assertRaises(database._ContextoTransaccionalNoAdmitido):
            with database._transaccion_indices_fiscales(cur or conexion.cursor()):
                ejecutado.append(True)
        self.assertEqual(ejecutado, [])
        self.assertEqual(self.control(), [])
        self.assertEqual(conexion.in_transaction, estado)
        self.assertEqual(self.foto(conexion), antes)

    def test_autocommit_true(self):
        self.assertRechazadoSinEscribir(self.conexion(autocommit=True))

    def test_journal_off(self):
        conexion = self.conexion()
        conexion.execute("PRAGMA journal_mode=OFF")
        self.assertRechazadoSinEscribir(conexion)

    def test_query_only(self):
        conexion = self.conexion()
        conexion.execute("PRAGMA query_only=1")
        self.assertRechazadoSinEscribir(conexion)

    def test_memory_sobre_archivo_simulado(self):
        conexion = self.conexion()
        cur = _CursorInyector(
            conexion.cursor(),
            database_list=lambda filas: [(f[0], f[1], "C:/simulado/base.db") for f in filas],
        )
        self.assertRechazadoSinEscribir(conexion, cur)

    def test_modos_admitidos_en_memoria(self):
        for kwargs in ({}, {"isolation_level": None}, {"autocommit": False},
                       {"autocommit": sqlite3.LEGACY_TRANSACTION_CONTROL}):
            with self.subTest(**{k: repr(v) for k, v in kwargs.items()}):
                conexion = self.conexion(**kwargs)
                antes = self.foto(conexion)
                with database._transaccion_indices_fiscales(conexion.cursor()):
                    self.escribir(conexion)
                self.assertTrue(conexion.in_transaction)
                conexion.rollback()
                self.assertEqual(self.foto(conexion), antes)


class FallosDeControlTest(_BaseTransaccional):
    def ejecutar(self, conexion, cur, cuerpo_falla=False):
        with database._transaccion_indices_fiscales(cur):
            self.escribir(conexion, cur)
            if cuerpo_falla:
                raise ValueError("cuerpo")

    def test_fallo_en_begin(self):
        conexion = self.conexion()
        antes = self.foto(conexion)
        error = sqlite3.OperationalError("database is locked")
        cur = _CursorInyector(conexion.cursor(), "BEGIN", error)
        with self.assertRaises(sqlite3.OperationalError) as capturado:
            self.ejecutar(conexion, cur)
        self.assertIs(capturado.exception, error)
        self.assertEqual(cur.fallos, 1)
        self.assertFalse(conexion.in_transaction)
        self.assertEqual(self.foto(conexion), antes)

    def test_fallo_en_savepoint_propio_y_exterior(self):
        for exterior in (False, True):
            with self.subTest(exterior=exterior):
                conexion = self.conexion()
                if exterior:
                    conexion.execute("BEGIN")
                    conexion.execute("INSERT INTO datos VALUES(10, 'llamador')")
                previo = self.foto(conexion)
                error = sqlite3.OperationalError("savepoint")
                cur = _CursorInyector(conexion.cursor(), "SAVEPOINT", error)
                with self.assertRaises(sqlite3.OperationalError) as capturado:
                    self.ejecutar(conexion, cur)
                self.assertIs(capturado.exception, error)
                self.assertEqual(cur.fallos, 1)
                self.assertEqual(conexion.in_transaction, exterior)
                self.assertEqual(self.foto(conexion), previo)
                if exterior:
                    conexion.rollback()

    def test_fallo_en_release_de_exito_revierte_y_relanza(self):
        for exterior in (False, True):
            with self.subTest(exterior=exterior):
                conexion = self.conexion()
                if exterior:
                    conexion.execute("BEGIN")
                    conexion.execute("INSERT INTO datos VALUES(10, 'llamador')")
                previo = self.foto(conexion)
                error = sqlite3.OperationalError("release")
                cur = _CursorInyector(conexion.cursor(), "RELEASE", error)
                with self.assertRaises(sqlite3.OperationalError) as capturado:
                    self.ejecutar(conexion, cur)
                self.assertIs(capturado.exception, error)
                self.assertEqual(cur.fallos, 1)
                self.assertEqual(conexion.in_transaction, exterior)
                self.assertEqual(self.foto(conexion), previo)
                if exterior:
                    conexion.rollback()

    def test_fallo_en_rollback_to_con_transaccion_exterior_informa_estado_incierto(self):
        conexion = self.conexion()
        antes = self.foto(conexion)
        conexion.execute("BEGIN")
        conexion.execute("INSERT INTO datos VALUES(10, 'llamador')")
        cur = _CursorInyector(conexion.cursor(), "ROLLBACK TO", sqlite3.OperationalError("rt"))
        with self.assertRaises(database._RestauracionTransaccionalFallida) as capturado:
            self.ejecutar(conexion, cur, cuerpo_falla=True)
        self.assertIsInstance(capturado.exception.error_original, ValueError)
        self.assertIs(capturado.exception.__cause__, capturado.exception.error_original)
        self.assertIsInstance(capturado.exception.error_restauracion, sqlite3.OperationalError)
        self.assertTrue(conexion.in_transaction, "No debe confirmar ni revertir lo ajeno")
        self.assertSinCommitNiUserVersion()
        conexion.rollback()
        self.assertEqual(self.foto(conexion), antes)

    def test_fallo_en_rollback_to_propio_revierte_con_rollback_y_conserva_original(self):
        conexion = self.conexion()
        antes = self.foto(conexion)
        cur = _CursorInyector(conexion.cursor(), "ROLLBACK TO", sqlite3.OperationalError("rt"))
        with self.assertRaises(ValueError) as capturado:
            self.ejecutar(conexion, cur, cuerpo_falla=True)
        self.assertIn("Restauracion parcial fallida", " ".join(capturado.exception.__notes__))
        self.assertFalse(conexion.in_transaction)
        self.assertEqual(self.foto(conexion), antes)

    def test_fallo_en_rollback_propio_informa_estado_incierto(self):
        conexion = self.conexion()
        cur = _CursorInyector(conexion.cursor(), "ROLLBACK", sqlite3.OperationalError("rb"))
        with self.assertRaises(database._RestauracionTransaccionalFallida) as capturado:
            self.ejecutar(conexion, cur, cuerpo_falla=True)
        self.assertEqual(cur.fallos, 1)
        self.assertIsInstance(capturado.exception.error_original, ValueError)
        self.assertIsInstance(capturado.exception.error_restauracion, sqlite3.OperationalError)
        # El SAVEPOINT ya se revirtio; solo queda la transaccion propia abierta.
        self.assertEqual(conexion.execute("SELECT COUNT(*) FROM datos").fetchone()[0], 1)
        conexion.rollback()

    def test_release_que_finaliza_transaccion_se_informa(self):
        conexion = self.conexion()
        conexion.execute("BEGIN")
        cur = _CursorInyector(conexion.cursor(), "RELEASE", sustituto="COMMIT")
        with self.assertRaises(database._TransaccionIndicesFiscalesPerdida):
            self.ejecutar(conexion, cur)
        self.assertFalse(conexion.in_transaction)


class PerdidaTransaccionExteriorTest(_BaseTransaccional):
    def test_rollback_total_dentro_del_bloque_con_fallo(self):
        conexion = self.conexion()
        conexion.execute("BEGIN")
        conexion.execute("INSERT INTO datos VALUES(10, 'llamador')")
        original = sqlite3.OperationalError("disk I/O error simulado")
        with self.assertRaises(database._TransaccionIndicesFiscalesPerdida) as capturado:
            with database._transaccion_indices_fiscales(conexion.cursor()):
                conexion.execute("ROLLBACK")  # simula la reversion completa de SQLite
                raise original
        self.assertIs(capturado.exception.__cause__, original)
        self.assertIn("exterior", str(capturado.exception))
        self.assertFalse(conexion.in_transaction)
        self.assertSinCommitNiUserVersion()

    def test_transaccion_finalizada_sin_error_en_el_bloque(self):
        for exterior in (False, True):
            with self.subTest(exterior=exterior):
                conexion = self.conexion()
                if exterior:
                    conexion.execute("BEGIN")
                with self.assertRaises(database._TransaccionIndicesFiscalesPerdida):
                    with database._transaccion_indices_fiscales(conexion.cursor()):
                        conexion.execute("ROLLBACK")
                self.assertFalse(conexion.in_transaction)

    def test_rollback_total_de_transaccion_propia_relanza_original(self):
        conexion = self.conexion()
        antes = self.foto(conexion)
        original = sqlite3.OperationalError("propia perdida")
        with self.assertRaises(sqlite3.OperationalError) as capturado:
            with database._transaccion_indices_fiscales(conexion.cursor()):
                self.escribir(conexion)
                conexion.execute("ROLLBACK")
                raise original
        self.assertIs(capturado.exception, original)
        self.assertEqual(self.foto(conexion), antes)


if __name__ == "__main__":
    unittest.main()
