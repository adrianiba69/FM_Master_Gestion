"""Aislamiento previo a imports para las pruebas fiscales antiguas."""

import importlib.util
import sqlite3
import sys
from contextlib import ExitStack, contextmanager
from pathlib import Path
from types import ModuleType
from unittest.mock import patch


_CONNECT = sqlite3.connect
_RAIZ = Path(__file__).resolve().parents[1]
_PERMITIDAS = {
    "_migrar_indice_factura_arca",
    "migrar_indices_unicos_factura_arca",
    "migrar_indices_activos_intentos_emision_arca",
}


@contextmanager
def _sustituir_modulos(modulos):
    ausente = object()
    anteriores = {nombre: sys.modules.get(nombre, ausente) for nombre in modulos}
    sys.modules.update(modulos)
    try:
        yield
    finally:
        for nombre, anterior in anteriores.items():
            if anterior is ausente:
                sys.modules.pop(nombre, None)
            else:
                sys.modules[nombre] = anterior


def _autorizar(accion, argumento, valor, _base, _origen):
    if accion == sqlite3.SQLITE_ATTACH or (
        accion == sqlite3.SQLITE_PRAGMA
        and argumento.lower() == "user_version" and valor is not None
    ):
        return sqlite3.SQLITE_DENY
    return sqlite3.SQLITE_OK


def conectar_memoria(base, *args, **kwargs):
    if base != ":memory:" or kwargs.get("uri") or (len(args) > 6 and args[6]):
        raise AssertionError("Solo se permite SQLite :memory: sin URI.")
    conexion = _CONNECT(base, *args, **kwargs)
    conexion.set_authorizer(_autorizar)
    return conexion


@contextmanager
def guardia_fiscal():
    perfil_anterior = sys.getprofile()

    def vigilar(frame, evento, arg):
        if evento == "call":
            archivo = Path(frame.f_code.co_filename)
            nombre = frame.f_code.co_name
            if archivo == _RAIZ / "main.py" or (
                archivo == _RAIZ / "database.py" and nombre not in _PERMITIDAS
                and (nombre in ("crear_base", "conectar", "agregar_columna_si_falta")
                     or nombre.startswith(("migrar_", "_migrar", "crear_tabla_", "completar_")))
            ):
                raise AssertionError(f"Funcion prohibida: {nombre}")
        if perfil_anterior is not None:
            perfil_anterior(frame, evento, arg)

    runtime = ModuleType("runtime_paths")
    runtime.DATABASE_PATH = Path(":memory:")
    with ExitStack() as pila:
        pila.enter_context(patch("sqlite3.connect", conectar_memoria))
        pila.enter_context(patch("sqlite3.dbapi2.connect", conectar_memoria))
        pila.enter_context(_sustituir_modulos({"runtime_paths": runtime, "main": None}))
        sys.setprofile(vigilar)
        try:
            yield
        finally:
            sys.setprofile(perfil_anterior)


with guardia_fiscal():
    _spec = importlib.util.spec_from_file_location("_database_indices_antiguos", _RAIZ / "database.py")
    database = importlib.util.module_from_spec(_spec)
    sys.modules[_spec.name] = database
    _spec.loader.exec_module(database)


@contextmanager
def imports_fiscales():
    with guardia_fiscal(), _sustituir_modulos({"database": database}):
        yield


def foto(conexion, tabla):
    indices = conexion.execute(
        "SELECT name, sql FROM main.sqlite_master WHERE type='index' ORDER BY name"
    ).fetchall()
    return (
        conexion.execute(f"SELECT * FROM main.{tabla} ORDER BY id").fetchall(),
        conexion.execute("SELECT type, name, tbl_name, sql FROM main.sqlite_master ORDER BY name").fetchall(),
        [(nombre, conexion.execute(f"PRAGMA main.index_list({tabla})").fetchall(),
          conexion.execute(f"PRAGMA main.index_xinfo({nombre})").fetchall())
         for nombre, _sql in indices],
        conexion.execute("PRAGMA main.user_version").fetchone(),
    )


# SQL literal de database.py en 0fe8ac7 y af3e31e, respectivamente.
HISTORICO_IDENTIDAD = (
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_factura_arca_identidad_unica "
    "ON factura_arca(emisor_id, punto_venta_num, tipo_comprobante_num, numero_comprobante_num) "
    "WHERE numero_comprobante_num IS NOT NULL"
)
HISTORICO_CAE = (
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_factura_arca_cae_unico "
    "ON factura_arca(cae) WHERE TRIM(COALESCE(cae, '')) <> ''"
)
HISTORICO_INTENTOS = (
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_intentos_emision_arca_clave_activa "
    "ON intentos_emision_arca(cuit_emisor, punto_venta, tipo_comprobante, numero_planificado) "
    "WHERE estado IN ('PENDIENTE_RECONCILIAR', 'ENVIANDO', 'CONFLICTO_MANUAL')"
)
