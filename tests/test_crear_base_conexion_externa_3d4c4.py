"""crear_base(conexion=...) sobre bases ficticias en directorios temporales.

Las guardias se instalan antes de importar database.py: solo se admiten bases
dentro del directorio temporal de cada prueba, sin ATTACH, red ni main.py.
"""

import importlib.util
import os
import re
import sqlite3
import sys
import tempfile
import unittest
from contextlib import ExitStack, contextmanager
from pathlib import Path
from types import ModuleType
from unittest.mock import patch
from urllib.parse import unquote, urlsplit


_RAIZ = Path(__file__).resolve().parents[1]
_CONNECT = sqlite3.connect
_PERMITIDA = [None]
_CREADAS = []
_DENEGACIONES = []
_CONTROL = re.compile(
    r"^(BEGIN|COMMIT|END|ROLLBACK)(\s+(DEFERRED|IMMEDIATE|EXCLUSIVE|TRANSACTION))?\s*;?$"
)


def _autorizar(accion, argumento, valor, _base, _origen):
    if accion == sqlite3.SQLITE_ATTACH or (
        accion == sqlite3.SQLITE_PRAGMA
        and argumento.lower() == "user_version" and valor is not None
    ):
        _DENEGACIONES.append((accion, argumento, valor))
        return sqlite3.SQLITE_DENY
    return sqlite3.SQLITE_OK


def _denegar(motivo):
    _DENEGACIONES.append(motivo)
    raise AssertionError(motivo)


def _conectar_temporal(base, *args, **kwargs):
    if args:
        _denegar("Argumentos posicionales no autorizados.")
    texto = os.fspath(base)
    if kwargs.get("uri"):
        uri = urlsplit(texto)
        if (uri.scheme != "file" or uri.netloc or uri.fragment
                or uri.query not in ("mode=rw", "mode=ro")):
            _denegar("URI no autorizada.")
        texto = unquote(uri.path)
        if os.name == "nt" and texto.startswith("/"):
            texto = texto[1:]
    ruta = Path(texto)
    raiz = _PERMITIDA[0]
    # Se rechaza antes de resolver para no consultar rutas ajenas al temporal.
    if raiz is None or not ruta.is_absolute() or not ruta.is_relative_to(raiz):
        _denegar("Ruta SQLite fuera del temporal.")
    if not ruta.resolve().is_relative_to(raiz) or "fm_master" in ruta.name.lower():
        _denegar("Ruta SQLite no autorizada.")
    kwargs.setdefault("factory", _Conexion)
    kwargs["timeout"] = 0.05
    conn = _CONNECT(base, **kwargs)
    conn.set_authorizer(_autorizar)
    _CREADAS.append(conn)
    return conn


@contextmanager
def _guardia(raiz=None):
    perfil_anterior = sys.getprofile()

    def vigilar(frame, evento, argumento):
        if evento == "call" and Path(frame.f_code.co_filename) == _RAIZ / "main.py":
            raise AssertionError("Arranque prohibido.")
        if perfil_anterior is not None:
            perfil_anterior(frame, evento, argumento)

    with ExitStack() as pila:
        pila.enter_context(patch("sqlite3.connect", _conectar_temporal))
        pila.enter_context(patch("sqlite3.dbapi2.connect", _conectar_temporal))
        pila.enter_context(patch("socket.socket.connect", side_effect=AssertionError("Red prohibida.")))
        pila.enter_context(patch("socket.create_connection", side_effect=AssertionError("Red prohibida.")))
        pila.enter_context(patch.dict(sys.modules, {"main": None}))
        anterior, _PERMITIDA[0] = _PERMITIDA[0], raiz
        sys.setprofile(vigilar)
        try:
            yield
        finally:
            sys.setprofile(perfil_anterior)
            _PERMITIDA[0] = anterior


class _Cursor(sqlite3.Cursor):
    def execute(self, sql, parameters=()):
        conn = self.connection
        if conn.destino is not None and " ".join(sql.split()).upper().startswith(conn.destino):
            raise conn.error
        return super().execute(sql, parameters)


class _Conexion(sqlite3.Connection):
    inyectar = (None, None)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.llamadas = []
        self.sql = []
        self.destino, self.error = type(self).inyectar
        self.set_trace_callback(lambda sql: self.sql.append(" ".join(sql.split()).upper()))

    def cursor(self, *args, **kwargs):
        return super().cursor(factory=_Cursor)

    def commit(self):
        self.llamadas.append("commit")
        return super().commit()

    def rollback(self):
        self.llamadas.append("rollback")
        return super().rollback()

    def close(self):
        self.llamadas.append("close")
        return super().close()

    def control_desde(self, inicio):
        return [sql for sql in self.sql[inicio:] if _CONTROL.match(sql)]


with _guardia():
    _runtime = ModuleType("runtime_paths")
    _runtime.DATABASE_PATH = Path(tempfile.gettempdir()) / "fm_3d4c4_no_utilizar" / "ficticia.sqlite"
    with patch.dict(sys.modules, {"runtime_paths": _runtime}):
        _spec = importlib.util.spec_from_file_location(
            "_database_conexion_externa_3d4c4", _RAIZ / "database.py"
        )
        database = importlib.util.module_from_spec(_spec)
        sys.modules[_spec.name] = database
        _spec.loader.exec_module(database)
_CONEXIONES_AL_IMPORTAR = len(_CREADAS)


_FIXTURE = (
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
_DUPLICADO_FISCAL = (
    "INSERT INTO factura_arca(cliente_id, emisor_id, resumen_id, fecha, punto_venta, "
    "tipo_comprobante, numero_factura, cae) VALUES(1, 1, 1, '2026-01-01', "
    "'00002', 'Factura C', '00002-00000001', '12345678901234')"
)


def _foto(conn):
    esquema = conn.execute(
        "SELECT type, name, tbl_name, sql FROM main.sqlite_master ORDER BY type, name"
    ).fetchall()
    datos = {
        nombre: conn.execute(f'SELECT * FROM main."{nombre}" ORDER BY rowid').fetchall()
        for tipo, nombre, _, _ in esquema if tipo == "table"
    }
    return esquema, datos, conn.execute("PRAGMA main.user_version").fetchone()


def _resumen(foto):
    esquema, datos, version = foto
    return esquema, {tabla: len(filas) for tabla, filas in datos.items()}, version


class CrearBaseConexionExternaTests(unittest.TestCase):
    def setUp(self):
        pila = ExitStack()
        self.addCleanup(pila.close)
        self.raiz = Path(pila.enter_context(
            tempfile.TemporaryDirectory(prefix="fm_3d4c4_")
        )).resolve()
        pila.enter_context(_guardia(self.raiz))
        self.contador = 0

    def abrir(self, base, **kwargs):
        conn = sqlite3.connect(base, **kwargs)
        self.addCleanup(sqlite3.Connection.close, conn)
        return conn

    def historica(self, duplicado=False):
        self.contador += 1
        base = self.raiz / f"historica_ficticia_{self.contador}.sqlite"
        conn = self.abrir(base)
        for sql in _FIXTURE + ((_DUPLICADO_FISCAL,) if duplicado else ()):
            conn.execute(sql)
        sqlite3.Connection.commit(conn)
        sqlite3.Connection.close(conn)
        return base

    def foto(self, base):
        conn = self.abrir(base.as_uri() + "?mode=ro", uri=True)
        try:
            return _foto(conn)
        finally:
            sqlite3.Connection.close(conn)

    def externa(self, base, **kwargs):
        conn = self.abrir(base, **kwargs)
        conn.execute("BEGIN IMMEDIATE")
        conn.llamadas.clear()
        return conn

    def ejecutar_externa(self, conn):
        creadas = len(_CREADAS)
        inicio = len(conn.sql)
        with patch.object(database, "conectar", side_effect=AssertionError("Segunda conexion.")) as apertura:
            try:
                return database.crear_base(conexion=conn)
            finally:
                apertura.assert_not_called()
                self.assertEqual(len(_CREADAS), creadas)
                self.assertEqual(conn.control_desde(inicio), [])
                self.assertEqual(conn.llamadas, [])

    def ejecutar_tradicional(self, base):
        creadas = len(_CREADAS)
        with patch.object(database, "DB_NAME", str(base)), \
                patch.object(database, "conectar", wraps=database.conectar) as apertura:
            try:
                database.crear_base()
            finally:
                apertura.assert_called_once_with()
                self.assertEqual(len(_CREADAS), creadas + 1)
        return _CREADAS[-1]

    def comprobar_reserva_vigente(self, base):
        competidor = self.abrir(base)
        with self.assertRaises(sqlite3.OperationalError) as ocupado:
            competidor.execute("UPDATE clientes SET nombre='competidor' WHERE id=1")
        self.assertEqual(ocupado.exception.sqlite_errorcode, sqlite3.SQLITE_BUSY)
        sqlite3.Connection.rollback(competidor)
        sqlite3.Connection.close(competidor)

    # --- Contrato tradicional, sin argumentos ---

    def test_tradicional_confirma_una_vez_y_cierra(self):
        base = self.historica()
        conn = self.ejecutar_tradicional(base)
        self.assertEqual(conn.llamadas, ["commit", "close"])
        self.assertEqual(conn.control_desde(0), ["BEGIN IMMEDIATE", "COMMIT"])
        with self.assertRaises(sqlite3.ProgrammingError):
            conn.execute("SELECT 1")
        esquema, datos, version = self.foto(base)
        nombres = {fila[1] for fila in esquema}
        self.assertIn("emisores_fiscales", nombres)
        for nombre, _, _, _ in database._DESTINOS_INDICES_FISCALES:
            self.assertIn(nombre, nombres)
        self.assertEqual(datos["clientes"][0][1], "Cliente de prueba")
        self.assertEqual(version, (0,))

    def test_tradicional_revierte_y_cierra_ante_error(self):
        base = self.historica()
        previa = self.foto(base)
        error = sqlite3.OperationalError("fallo inyectado")
        with patch.object(_Conexion, "inyectar", ("UPDATE SERVICIOS SET ", error)):
            with self.assertRaises(sqlite3.OperationalError) as fallo:
                self.ejecutar_tradicional(base)
        self.assertIs(fallo.exception, error)
        conn = _CREADAS[-1]
        self.assertEqual(conn.llamadas, ["rollback", "close"])
        self.assertEqual(conn.control_desde(0), ["BEGIN IMMEDIATE", "ROLLBACK"])
        self.assertEqual(self.foto(base), previa)

    # --- Conexion externa ---

    def test_externa_protegida_sin_control_propio(self):
        base = self.historica()
        previa = self.foto(base)
        conn = self.externa(base)
        self.assertIsNone(self.ejecutar_externa(conn))
        self.assertTrue(conn.in_transaction)
        self.assertIn("emisores_fiscales", {fila[1] for fila in _foto(conn)[0]})
        # Otro escritor sigue bloqueado y nada se confirmo por cuenta propia.
        self.comprobar_reserva_vigente(base)
        self.assertEqual(self.foto(base), previa)
        self.assertEqual(conn.execute("SELECT 1").fetchone(), (1,))

    def test_llamador_confirma_e_inicializacion_es_equivalente_e_idempotente(self):
        base_tradicional, base = self.historica(), self.historica()
        self.ejecutar_tradicional(base_tradicional)
        conn = self.externa(base)
        self.ejecutar_externa(conn)
        conn.commit()
        self.assertEqual(conn.llamadas, ["commit"])
        self.assertFalse(conn.in_transaction)
        confirmada = self.foto(base)
        self.assertEqual(_resumen(confirmada), _resumen(self.foto(base_tradicional)))
        self.assertEqual(confirmada[1]["clientes"][0][1], "Cliente de prueba")

        conn.execute("BEGIN IMMEDIATE")
        conn.llamadas.clear()
        self.ejecutar_externa(conn)
        self.assertEqual(_foto(conn), confirmada)
        conn.commit()
        self.assertEqual(self.foto(base), confirmada)

    def test_llamador_revierte(self):
        base = self.historica()
        previa = self.foto(base)
        conn = self.externa(base)
        self.ejecutar_externa(conn)
        self.assertNotEqual(_foto(conn), previa)
        conn.rollback()
        self.assertEqual(conn.llamadas, ["rollback"])
        self.assertEqual(_foto(conn), previa)
        self.assertEqual(self.foto(base), previa)

    def test_errores_reales_se_propagan_sin_finalizar_la_transaccion(self):
        for destino in (
            "ALTER TABLE CLIENTES ADD COLUMN CODIGO ",
            "UPDATE SERVICIOS SET ",
            "CREATE UNIQUE INDEX IF NOT EXISTS MAIN.IDX_FACTURA_ARCA_IDENTIDAD_UNICA ",
            "CREATE UNIQUE INDEX IF NOT EXISTS IDX_USUARIOS_USUARIO ",
        ):
            with self.subTest(destino=destino):
                base = self.historica()
                previa = self.foto(base)
                conn = self.externa(base)
                conn.destino, conn.error = destino, sqlite3.OperationalError("fallo inyectado")
                with self.assertRaises(sqlite3.OperationalError) as fallo:
                    self.ejecutar_externa(conn)
                self.assertIs(fallo.exception, conn.error)
                self.assertTrue(conn.in_transaction)
                self.comprobar_reserva_vigente(base)
                conn.rollback()
                self.assertEqual(self.foto(base), previa)

    def test_duplicado_fiscal_real_se_propaga(self):
        base = self.historica(duplicado=True)
        previa = self.foto(base)
        conn = self.externa(base)
        with self.assertRaises(sqlite3.IntegrityError):
            self.ejecutar_externa(conn)
        self.assertTrue(conn.in_transaction)
        conn.rollback()
        self.assertEqual(self.foto(base), previa)

    def test_errores_de_inicializar_base_se_propagan_identicos(self):
        for error in (ValueError("valor"), RuntimeError("inesperado"), KeyboardInterrupt("interrupcion")):
            with self.subTest(error=type(error).__name__):
                base = self.historica()
                conn = self.externa(base)
                with patch.object(database, "_inicializar_base", side_effect=error) as inicializar:
                    with self.assertRaises(type(error)) as fallo:
                        self.ejecutar_externa(conn)
                self.assertIs(fallo.exception, error)
                self.assertIs(inicializar.call_args.args[0].connection, conn)
                self.assertTrue(conn.in_transaction)
                conn.rollback()

    def test_transaccion_finalizada_durante_inicializacion_se_informa(self):
        base = self.historica()
        conn = self.externa(base)
        inicio = len(conn.sql)
        with patch.object(database, "_inicializar_base", side_effect=lambda cur: cur.execute("COMMIT")):
            with self.assertRaisesRegex(RuntimeError, "transaccion externa finalizo"):
                database.crear_base(conexion=conn)
        self.assertEqual(conn.control_desde(inicio), ["COMMIT"])
        self.assertEqual(conn.llamadas, [])

    def test_rechaza_conexion_sin_transaccion(self):
        for isolation_level in ("", None):
            with self.subTest(isolation_level=isolation_level):
                base = self.historica()
                previa = self.foto(base)
                conn = self.abrir(base, isolation_level=isolation_level)
                inicio = len(conn.sql)
                with patch.object(database, "_inicializar_base") as inicializar:
                    with self.assertRaisesRegex(ValueError, "transaccion activa"):
                        self.ejecutar_externa(conn)
                inicializar.assert_not_called()
                self.assertEqual(conn.sql[inicio:], [])
                self.assertFalse(conn.in_transaction)
                self.assertEqual(self.foto(base), previa)

    def test_rechaza_tipo_incorrecto_sin_abrir_conexiones(self):
        base = self.historica()
        conn = self.abrir(base)
        for valor in (object(), "ficticia.sqlite", base, conn.cursor(), False, 0, ""):
            with self.subTest(valor=type(valor).__name__):
                creadas = len(_CREADAS)
                with patch.object(database, "conectar") as apertura, \
                        patch.object(database, "_inicializar_base") as inicializar:
                    with self.assertRaises(TypeError):
                        database.crear_base(conexion=valor)
                apertura.assert_not_called()
                inicializar.assert_not_called()
                self.assertEqual(len(_CREADAS), creadas)

    def test_rechaza_conexion_cerrada(self):
        conn = self.abrir(self.historica())
        sqlite3.Connection.close(conn)
        with patch.object(database, "conectar") as apertura:
            with self.assertRaises(sqlite3.ProgrammingError):
                database.crear_base(conexion=conn)
        apertura.assert_not_called()

    @unittest.skipUnless(hasattr(sqlite3, "LEGACY_TRANSACTION_CONTROL"), "Requiere Python 3.12+")
    def test_rechaza_autocommit_verdadero(self):
        base = self.historica()
        previa = self.foto(base)
        conn = self.abrir(base, autocommit=True)
        conn.execute("BEGIN IMMEDIATE")
        with patch.object(database, "_inicializar_base") as inicializar:
            with self.assertRaisesRegex(ValueError, "autocommit"):
                self.ejecutar_externa(conn)
        inicializar.assert_not_called()
        conn.execute("ROLLBACK")
        self.assertEqual(self.foto(base), previa)

    def test_guardias_activas(self):
        self.assertEqual(_CONEXIONES_AL_IMPORTAR, 0)
        for base, kwargs in (
            (self.raiz.parent / "ajena_ficticia.sqlite", {}),
            (self.raiz.parent.as_uri() + "/ajena_ficticia.sqlite?mode=rw", {"uri": True}),
            (self.raiz / ".." / "ajena_ficticia.sqlite", {}),
            (self.raiz / "fm_master.db", {}),
            (":memory:", {}),
        ):
            for conectar in (sqlite3.connect, sqlite3.dbapi2.connect):
                with self.subTest(base=str(base), conectar=conectar):
                    with self.assertRaises(AssertionError):
                        conectar(base, **kwargs)
        with self.assertRaises(AssertionError):
            database.conectar()
        conn = self.abrir(self.historica())
        with self.assertRaises(sqlite3.DatabaseError):
            conn.execute("ATTACH ':memory:' AS ajena")
        with self.assertRaises(sqlite3.DatabaseError):
            conn.execute("PRAGMA user_version=99")
        with self.assertRaises(ModuleNotFoundError):
            __import__("main")
        self.assertEqual(
            [fila[1:] for fila in conn.execute("PRAGMA database_list").fetchall()],
            [("main", str(self.raiz / f"historica_ficticia_{self.contador}.sqlite"))],
        )


if __name__ == "__main__":
    unittest.main()
