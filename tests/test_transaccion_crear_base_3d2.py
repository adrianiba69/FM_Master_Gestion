"""Inicializacion real aislada en memoria, sin arranque, archivos ni red."""

import ast
import importlib.util
import socket
import sqlite3
import sys
import unittest
from contextlib import ExitStack, contextmanager
from pathlib import Path
from types import ModuleType
from unittest.mock import patch


_RAIZ = Path(__file__).resolve().parents[1]
_CONNECT = sqlite3.connect
_CONEXIONES = []
_DENEGACIONES = []


def _autorizar(accion, argumento, valor, _base, _origen):
    if accion == sqlite3.SQLITE_ATTACH or (
        accion == sqlite3.SQLITE_PRAGMA
        and argumento.lower() == "user_version" and valor is not None
    ):
        _DENEGACIONES.append((accion, argumento, valor))
        return sqlite3.SQLITE_DENY
    return sqlite3.SQLITE_OK


def _conectar_memoria(base, *args, **kwargs):
    if base != ":memory:" or kwargs.get("uri") or (len(args) > 6 and args[6]):
        _DENEGACIONES.append(("connect", base))
        raise AssertionError("Solo se permite SQLite :memory: sin URI.")
    conn = _CONNECT(base, *args, **kwargs)
    conn.set_authorizer(_autorizar)
    _CONEXIONES.append(base)
    return conn


@contextmanager
def _guardia():
    perfil_anterior = sys.getprofile()

    def vigilar(frame, evento, argumento):
        if evento == "call":
            archivo = Path(frame.f_code.co_filename)
            if archivo == _RAIZ / "main.py" or (
                archivo == _RAIZ / "database.py" and frame.f_code.co_name == "conectar"
            ):
                raise AssertionError("Arranque y apertura operativa prohibidos.")
        if perfil_anterior is not None:
            perfil_anterior(frame, evento, argumento)

    with ExitStack() as pila:
        pila.enter_context(patch("sqlite3.connect", _conectar_memoria))
        pila.enter_context(patch("sqlite3.dbapi2.connect", _conectar_memoria))
        pila.enter_context(patch("socket.socket.connect", side_effect=AssertionError("Red prohibida.")))
        pila.enter_context(patch("socket.create_connection", side_effect=AssertionError("Red prohibida.")))
        pila.enter_context(patch.dict(sys.modules, {"main": None}))
        sys.setprofile(vigilar)
        try:
            yield
        finally:
            sys.setprofile(perfil_anterior)


with _guardia():
    _runtime = ModuleType("runtime_paths")
    _runtime.DATABASE_PATH = Path(":memory:")
    with patch.dict(sys.modules, {"runtime_paths": _runtime}):
        _spec = importlib.util.spec_from_file_location(
            "_database_transaccion_3d2", _RAIZ / "database.py"
        )
        database = importlib.util.module_from_spec(_spec)
        sys.modules[_spec.name] = database
        _spec.loader.exec_module(database)


def _foto(conn):
    esquema = sqlite3.Connection.execute(
        conn, "SELECT type, name, tbl_name, sql FROM main.sqlite_master ORDER BY type, name"
    ).fetchall()
    tablas = [nombre for tipo, nombre, _, _ in esquema if tipo == "table"]
    datos = {
        tabla: sqlite3.Connection.execute(
            conn, f'SELECT * FROM main."{tabla}" ORDER BY rowid'
        ).fetchall()
        for tabla in tablas
    }
    indices = {
        nombre: sqlite3.Connection.execute(
            conn, f'PRAGMA main.index_xinfo("{nombre}")'
        ).fetchall()
        for tipo, nombre, _, _ in esquema if tipo == "index"
    }
    return esquema, datos, indices, conn.execute("PRAGMA main.user_version").fetchone()


class _Cursor(sqlite3.Cursor):
    def execute(self, sql, parameters=()):
        conn = self.connection
        sentencia = " ".join(sql.split()).upper()
        conn.eventos.append(sentencia)
        coincide = conn.destino is not None and sentencia.startswith(conn.destino)
        if coincide and not conn.despues:
            conn.alcances += 1
            raise conn.error
        resultado = super().execute(sql, parameters)
        if coincide and conn.despues:
            conn.alcances += 1
            raise conn.error
        return resultado


class _Conexion(sqlite3.Connection):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.eventos = []
        self.destino = None
        self.despues = False
        self.error = sqlite3.OperationalError("fallo inyectado")
        self.alcances = 0
        self.error_cursor = None
        self.error_commit = None
        self.error_rollback = None
        self.error_close = None
        self.foto_cierre = None
        self.transaccion_cierre = None
        self.cerrada = False

    def cursor(self, *args, **kwargs):
        if self.error_cursor is not None:
            raise self.error_cursor
        return super().cursor(factory=_Cursor)

    def commit(self):
        self.eventos.append("COMMIT")
        if self.error_commit is not None:
            raise self.error_commit
        return super().commit()

    def rollback(self):
        self.eventos.append("ROLLBACK")
        if self.error_rollback is not None:
            raise self.error_rollback
        return super().rollback()

    def close(self):
        self.eventos.append("CLOSE")
        self.transaccion_cierre = self.in_transaction
        self.foto_cierre = _foto(self)
        super().close()
        self.cerrada = True
        if self.error_close is not None:
            raise self.error_close


def _fixture(conn):
    sentencias = (
        "CREATE TABLE clientes(id INTEGER PRIMARY KEY AUTOINCREMENT, nombre TEXT)",
        "INSERT INTO clientes(nombre) VALUES('Cliente de prueba')",
        "CREATE UNIQUE INDEX idx_cliente_legacy ON clientes(nombre)",
        "CREATE TABLE servicios(id INTEGER PRIMARY KEY AUTOINCREMENT, cliente_id INTEGER, "
        "concepto TEXT, importe REAL, fecha_inicio TEXT, fecha_fin TEXT, renovable INTEGER)",
        "INSERT INTO servicios(cliente_id, concepto, importe, fecha_inicio, fecha_fin, renovable) "
        "VALUES(1, 'Servicio de prueba', 123.45, NULL, NULL, NULL)",
        "CREATE TABLE resumenes(id INTEGER PRIMARY KEY AUTOINCREMENT, numero INTEGER, "
        "cliente_id INTEGER, fecha TEXT, fecha_vencimiento TEXT, estado_facturacion TEXT)",
        "INSERT INTO resumenes(numero, cliente_id, estado_facturacion) VALUES(1, 1, '')",
        "CREATE TABLE factura_arca(id INTEGER PRIMARY KEY AUTOINCREMENT, cliente_id INTEGER, "
        "emisor_id INTEGER, resumen_id INTEGER, fecha TEXT, punto_venta TEXT, "
        "tipo_comprobante TEXT, importe_total REAL, estado TEXT, numero_factura TEXT, "
        "cae TEXT, vencimiento_cae TEXT, observaciones TEXT, fecha_creacion TEXT)",
        "INSERT INTO factura_arca(cliente_id, emisor_id, resumen_id, fecha, punto_venta, "
        "tipo_comprobante, importe_total, estado, numero_factura, cae) "
        "VALUES(1, 1, 1, '2026-01-01', '00002', 'Factura C', 123.45, "
        "'Autorizado', '00002-00000001', '12345678901234')",
    )
    for sql in sentencias:
        conn.execute(sql)
    sqlite3.Connection.commit(conn)


def _restaurar_fixture(conn, foto):
    esquema, datos, _, _ = foto
    for tipo, nombre, _, sql in esquema:
        if tipo == "table" and nombre != "sqlite_sequence":
            conn.execute(sql)
    for tabla, filas in datos.items():
        if tabla == "sqlite_sequence":
            conn.execute("DELETE FROM sqlite_sequence")
        for fila in filas:
            marcas = ", ".join("?" for _ in fila)
            conn.execute(f'INSERT INTO "{tabla}" VALUES({marcas})', fila)
    for tipo, _, _, sql in esquema:
        if tipo == "index" and sql is not None:
            conn.execute(sql)
    sqlite3.Connection.commit(conn)


class TransaccionCrearBaseTests(unittest.TestCase):
    def setUp(self):
        self.pila = ExitStack()
        self.addCleanup(self.pila.close)
        self.pila.enter_context(_guardia())

    def conexion(self, historica=True, **kwargs):
        conn = sqlite3.connect(":memory:", factory=_Conexion, **kwargs)
        self.addCleanup(lambda: sqlite3.Connection.close(conn) if not conn.cerrada else None)
        if historica:
            _fixture(conn)
        conn.eventos.clear()
        return conn

    def ejecutar(self, conn):
        with patch.object(database, "conectar", return_value=conn) as apertura:
            resultado = database.crear_base()
        apertura.assert_called_once_with()
        return resultado

    def comprobar_cierre(self, conn):
        self.assertTrue(conn.cerrada)
        self.assertEqual(conn.eventos[-1], "CLOSE")
        with self.assertRaises(sqlite3.ProgrammingError):
            conn.execute("SELECT 1")

    def comprobar_fallo(self, conn, previa):
        with self.assertRaises(type(conn.error)) as fallo:
            self.ejecutar(conn)
        self.assertIs(fallo.exception, conn.error)
        self.assertEqual(conn.alcances, 1)
        self.assertNotIn("COMMIT", conn.eventos)
        self.assertEqual(conn.eventos.count("ROLLBACK"), 1)
        self.assertFalse(conn.transaccion_cierre)
        self.assertEqual(conn.foto_cierre, previa)
        self.comprobar_cierre(conn)

    def test_ddl_inicial_antes_y_despues(self):
        for despues in (False, True):
            with self.subTest(despues=despues):
                conn = self.conexion(historica=False)
                previa = _foto(conn)
                conn.destino = "CREATE TABLE IF NOT EXISTS CLIENTES("
                conn.despues = despues
                self.comprobar_fallo(conn, previa)
                self.assertEqual(conn.eventos[0], "BEGIN IMMEDIATE")

    def test_alter_historico_antes_y_despues(self):
        for despues in (False, True):
            with self.subTest(despues=despues):
                conn = self.conexion()
                previa = _foto(conn)
                conn.destino = "ALTER TABLE CLIENTES ADD COLUMN CODIGO "
                conn.despues = despues
                self.comprobar_fallo(conn, previa)

    def test_escrituras_intermedias_antes_y_despues(self):
        for destino in (
            "INSERT INTO EMISORES_FISCALES(",
            "INSERT INTO EMISOR_FISCAL_ARCA_CONFIG(",
            "INSERT INTO ARCA_CONFIG(",
            "UPDATE SERVICIOS SET ",
            "UPDATE RESUMENES SET ",
        ):
            for despues in (False, True):
                with self.subTest(destino=destino, despues=despues):
                    conn = self.conexion()
                    previa = _foto(conn)
                    conn.destino, conn.despues = destino, despues
                    self.comprobar_fallo(conn, previa)

    def test_indices_fiscales_antes_y_despues(self):
        for destino in (
            "CREATE UNIQUE INDEX IF NOT EXISTS MAIN.IDX_FACTURA_ARCA_IDENTIDAD_UNICA ",
            "CREATE UNIQUE INDEX IF NOT EXISTS MAIN.IDX_INTENTOS_EMISION_ARCA_CLAVE_ACTIVA_AMBIENTE ",
        ):
            for despues in (False, True):
                with self.subTest(destino=destino, despues=despues):
                    conn = self.conexion()
                    previa = _foto(conn)
                    conn.destino, conn.despues = destino, despues
                    self.comprobar_fallo(conn, previa)
                    self.assertTrue(any(sql.startswith("SAVEPOINT ") for sql in conn.eventos))

    def test_fallo_tardio_revierte_incluso_indices_fiscales(self):
        conn = self.conexion()
        previa = _foto(conn)
        conn.destino = "CREATE UNIQUE INDEX IF NOT EXISTS IDX_USUARIOS_USUARIO "
        conn.despues = True
        self.comprobar_fallo(conn, previa)
        self.assertTrue(any("MAIN.IDX_INTENTOS_EMISION_ARCA" in sql for sql in conn.eventos))

    def test_duplicados_fiscales_reales(self):
        conn = self.conexion()
        conn.execute(
            "INSERT INTO factura_arca(cliente_id, emisor_id, resumen_id, fecha, punto_venta, "
            "tipo_comprobante, numero_factura, cae) VALUES(1, 1, 1, '2026-01-01', "
            "'00002', 'Factura C', '00002-00000001', '12345678901234')"
        )
        sqlite3.Connection.commit(conn)
        previa = _foto(conn)
        with self.assertRaises(sqlite3.IntegrityError):
            self.ejecutar(conn)
        self.assertNotIn("COMMIT", conn.eventos)
        self.assertEqual(conn.foto_cierre, previa)
        self.assertFalse(conn.transaccion_cierre)
        self.comprobar_cierre(conn)

    def test_indice_desconocido_real(self):
        conn = self.conexion()
        conn.execute("CREATE INDEX idx_factura_arca_identidad_unica ON factura_arca(fecha)")
        previa = _foto(conn)
        with self.assertRaises(ValueError):
            self.ejecutar(conn)
        self.assertNotIn("COMMIT", conn.eventos)
        self.assertEqual(conn.foto_cierre, previa)
        self.comprobar_cierre(conn)

    def test_error_begin_y_cursor(self):
        for punto in ("begin", "cursor"):
            with self.subTest(punto=punto):
                conn = self.conexion()
                previa = _foto(conn)
                if punto == "begin":
                    conn.destino = "BEGIN IMMEDIATE"
                else:
                    conn.error_cursor = conn.error
                with self.assertRaises(sqlite3.OperationalError) as fallo:
                    self.ejecutar(conn)
                self.assertIs(fallo.exception, conn.error)
                self.assertEqual(conn.foto_cierre, previa)
                self.assertNotIn("COMMIT", conn.eventos)
                self.assertEqual(conn.eventos.count("ROLLBACK"), 1)
                self.comprobar_cierre(conn)

    def test_error_commit_revierte(self):
        conn = self.conexion()
        previa = _foto(conn)
        conn.error_commit = conn.error
        with self.assertRaises(sqlite3.OperationalError) as fallo:
            self.ejecutar(conn)
        self.assertIs(fallo.exception, conn.error)
        self.assertEqual(conn.eventos[-3:], ["COMMIT", "ROLLBACK", "CLOSE"])
        self.assertEqual(conn.foto_cierre, previa)
        self.assertFalse(conn.transaccion_cierre)
        self.comprobar_cierre(conn)

    def test_errores_secundarios_no_ocultan_original(self):
        for rollback, cierre in ((True, False), (False, True), (True, True)):
            with self.subTest(rollback=rollback, cierre=cierre):
                conn = self.conexion()
                conn.destino = "UPDATE SERVICIOS SET "
                if rollback:
                    conn.error_rollback = RuntimeError("rollback inyectado")
                if cierre:
                    conn.error_close = RuntimeError("cierre inyectado")
                with self.assertRaises(sqlite3.OperationalError) as fallo:
                    self.ejecutar(conn)
                self.assertIs(fallo.exception, conn.error)
                self.assertEqual(len(fallo.exception.__notes__), int(rollback) + int(cierre))
                self.assertEqual(conn.eventos[-2:], ["ROLLBACK", "CLOSE"])
                self.assertNotIn("COMMIT", conn.eventos)
                self.comprobar_cierre(conn)

    def test_cierre_fallido_en_exito_es_explicito(self):
        conn = self.conexion()
        conn.error_close = RuntimeError("cierre inyectado")
        with self.assertRaises(RuntimeError) as fallo:
            self.ejecutar(conn)
        self.assertIs(fallo.exception, conn.error_close)
        self.assertEqual(conn.eventos.count("COMMIT"), 1)
        self.assertNotIn("ROLLBACK", conn.eventos)
        self.comprobar_cierre(conn)

    def test_baseexception_tambien_revierte(self):
        conn = self.conexion()
        previa = _foto(conn)
        conn.destino = "UPDATE SERVICIOS SET "
        conn.error = KeyboardInterrupt("interrupcion inyectada")
        self.comprobar_fallo(conn, previa)

    def test_error_apertura_se_preserva(self):
        error = sqlite3.OperationalError("apertura inyectada")
        with patch.object(database, "conectar", side_effect=error):
            with self.assertRaises(sqlite3.OperationalError) as fallo:
                database.crear_base()
        self.assertIs(fallo.exception, error)

    def test_exito_e_idempotencia(self):
        conn = self.conexion()
        self.assertIsNone(self.ejecutar(conn))
        self.assertEqual(conn.eventos[0], "BEGIN IMMEDIATE")
        self.assertEqual(conn.eventos.count("BEGIN IMMEDIATE"), 1)
        self.assertEqual(conn.eventos.count("COMMIT"), 1)
        self.assertNotIn("ROLLBACK", conn.eventos)
        self.assertFalse(conn.transaccion_cierre)
        self.comprobar_cierre(conn)
        foto = conn.foto_cierre
        self.assertEqual(foto[3], (0,))
        self.assertEqual(len(foto[1]["emisores_fiscales"]), 3)
        self.assertEqual(len(foto[1]["emisor_fiscal_arca_config"]), 3)
        self.assertEqual(len(foto[1]["arca_config"]), 1)
        self.assertEqual(foto[1]["factura_arca"][0][8:11],
                         ("Autorizado", "00002-00000001", "12345678901234"))
        nombres = {fila[1] for fila in foto[0]}
        for nombre, _, _, _ in database._DESTINOS_INDICES_FISCALES:
            self.assertIn(nombre, nombres)
        segunda = self.conexion(historica=False)
        _restaurar_fixture(segunda, foto)
        self.ejecutar(segunda)
        self.assertEqual(segunda.foto_cierre, foto)
        self.assertEqual(segunda.eventos.count("COMMIT"), 1)
        self.assertFalse(segunda.transaccion_cierre)
        self.comprobar_cierre(segunda)

    def test_exito_desde_memoria_vacia_y_autocommit_legacy_desactivado(self):
        for isolation_level in ("", None):
            with self.subTest(isolation_level=isolation_level):
                conn = self.conexion(historica=False, isolation_level=isolation_level)
                self.ejecutar(conn)
                self.assertEqual(conn.eventos[0], "BEGIN IMMEDIATE")
                self.assertEqual(conn.eventos.count("COMMIT"), 1)
                self.assertFalse(conn.transaccion_cierre)
                self.assertEqual(conn.foto_cierre[3], (0,))
                self.comprobar_cierre(conn)

    def test_guardias_activas(self):
        for ruta, kwargs in (
            ("prohibida.db", {}),
            ("file::memory:", {"uri": True}),
            (":memory:", {"uri": True}),
        ):
            for conectar in (sqlite3.connect, sqlite3.dbapi2.connect):
                with self.subTest(ruta=ruta, kwargs=kwargs, conectar=conectar):
                    with self.assertRaises(AssertionError):
                        conectar(ruta, **kwargs)
        conn = self.conexion(historica=False)
        with self.assertRaises(sqlite3.DatabaseError):
            conn.execute("ATTACH ':memory:' AS ajena")
        with self.assertRaises(sqlite3.DatabaseError):
            conn.execute("PRAGMA user_version=123")
        self.assertEqual(conn.execute("PRAGMA user_version").fetchone(), (0,))
        self.assertEqual(conn.execute("PRAGMA database_list").fetchall(), [(0, "main", "")])
        with self.assertRaises(AssertionError):
            database.conectar()
        with self.assertRaises(ModuleNotFoundError):
            __import__("main")
        self.assertTrue(_CONEXIONES)
        self.assertEqual(set(_CONEXIONES), {":memory:"})

    def test_cuerpo_no_puede_confirmar_ni_abrir_conexiones(self):
        arbol = ast.parse((_RAIZ / "database.py").read_text(encoding="utf-8"))
        funciones = {n.name: n for n in arbol.body if isinstance(n, ast.FunctionDef)}
        pendientes, vistas = ["_inicializar_base"], set()
        while pendientes:
            nombre = pendientes.pop()
            if nombre in vistas:
                continue
            vistas.add(nombre)
            for nodo in ast.walk(funciones[nombre]):
                if not isinstance(nodo, ast.Call):
                    continue
                if isinstance(nodo.func, ast.Name) and nodo.func.id in funciones:
                    self.assertNotEqual(nodo.func.id, "conectar")
                    pendientes.append(nodo.func.id)
                if isinstance(nodo.func, ast.Attribute):
                    self.assertNotIn(nodo.func.attr, ("commit", "rollback", "connect", "executescript"))
        self.assertIn("_transaccion_indices_fiscales", vistas)
        self.assertIn("migrar_emisor_fiscal_arca_config", vistas)


if __name__ == "__main__":
    unittest.main()
