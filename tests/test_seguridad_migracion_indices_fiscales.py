"""Contrato de seguridad para las migraciones de índices únicos fiscales.

Solo se ejecutan las funciones de migración de índices sobre bases ``:memory:``
creadas por cada prueba. Política verificada:

- No eliminar un índice fiscal existente sin garantizar y verificar su reemplazo.
- Ante duplicados, definiciones desconocidas o errores de creación, detenerse
  sin perder protecciones existentes.
- Reemplazar índices históricos reconocidos solo de forma atómica y verificada.
- No modificar ni eliminar registros fiscales para resolver duplicados.

Las pruebas ``expectedFailure`` documentan protecciones todavía ausentes.
"""

import importlib.util
import io
import sqlite3
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from types import ModuleType
from unittest.mock import patch


_CONNECT_ORIGINAL = sqlite3.connect


def _connect_solo_memoria(base, *args, **kwargs):
    if base != ":memory:" or kwargs.get("uri"):
        raise AssertionError(f"Conexión SQLite no permitida en esta prueba: {base!r}")
    return _CONNECT_ORIGINAL(base, *args, **kwargs)


def _cargar_database_aislado():
    nombre_modulo = "_database_seguridad_migracion_indices_test"
    ruta_database = Path(__file__).resolve().parents[1] / "database.py"
    spec = importlib.util.spec_from_file_location(nombre_modulo, ruta_database)
    modulo = importlib.util.module_from_spec(spec)
    runtime_paths_falso = ModuleType("runtime_paths")
    runtime_paths_falso.DATABASE_PATH = Path(":memory:")
    sys.modules[nombre_modulo] = modulo
    try:
        with patch.dict(sys.modules, {"runtime_paths": runtime_paths_falso}), patch(
            "sqlite3.connect", _connect_solo_memoria
        ):
            spec.loader.exec_module(modulo)
    except Exception:
        sys.modules.pop(nombre_modulo, None)
        raise
    return modulo


database = _cargar_database_aislado()

# Únicas funciones ejecutables: las migraciones de índices y sus auxiliares directos.
_FUNCIONES_PERMITIDAS = {
    "_migrar_indice_factura_arca",
    "migrar_indices_unicos_factura_arca",
    "migrar_indices_activos_intentos_emision_arca",
    "migrar_intentos_emision_arca_ambiente",
    "agregar_columna_si_falta",
}
_FUNCIONES_PROHIBIDAS = sorted(
    nombre for nombre in vars(database)
    if callable(getattr(database, nombre))
    and nombre not in _FUNCIONES_PERMITIDAS
    and (
        nombre in ("crear_base", "conectar")
        or nombre.startswith(("migrar_", "_migrar", "completar_", "crear_tabla_"))
    )
)


def _prohibida(nombre):
    def _funcion(*_args, **_kwargs):
        raise AssertionError(f"Función prohibida en estas pruebas: {nombre}")
    return _funcion


_guardias = [patch("sqlite3.connect", _connect_solo_memoria)] + [
    patch.object(database, nombre, _prohibida(nombre)) for nombre in _FUNCIONES_PROHIBIDAS
]


def setUpModule():
    for guardia in _guardias:
        guardia.start()


def tearDownModule():
    for guardia in reversed(_guardias):
        guardia.stop()


ESTADOS_ACTIVOS = "('PENDIENTE_RECONCILIAR', 'ENVIANDO', 'CONFLICTO_MANUAL')"

# Definiciones históricas tomadas literalmente del historial Git (0fe8ac7 y af3e31e).
HISTORICO_IDENTIDAD_0FE8AC7 = (
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_factura_arca_identidad_unica "
    "ON factura_arca(emisor_id, punto_venta_num, tipo_comprobante_num, numero_comprobante_num) "
    "WHERE numero_comprobante_num IS NOT NULL"
)
HISTORICO_CAE_0FE8AC7 = (
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_factura_arca_cae_unico "
    "ON factura_arca(cae) WHERE TRIM(COALESCE(cae, '')) <> ''"
)
HISTORICO_INTENTOS_GLOBAL_AF3E31E = (
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_intentos_emision_arca_clave_activa "
    "ON intentos_emision_arca(cuit_emisor, punto_venta, tipo_comprobante, numero_planificado) "
    f"WHERE estado IN {ESTADOS_ACTIVOS}"
)
INDICE_GLOBAL_INTENTOS = "idx_intentos_emision_arca_clave_activa"

_ESPERADOS = {
    nombre: (tabla, clave, condicion)
    for nombre, tabla, clave, condicion in database._INDICES_UNICOS_INSPECCION_ESPERADOS
}
INDICES_FACTURA = tuple(n for n in _ESPERADOS if n.startswith("idx_factura_arca_"))
INDICES_INTENTOS = tuple(n for n in _ESPERADOS if n.startswith("idx_intentos_emision_arca_"))


def _ddl_esperado(nombre):
    tabla, clave, condicion = _ESPERADOS[nombre]
    return f"CREATE UNIQUE INDEX {nombre} ON {tabla}({clave}) WHERE {condicion}"


class _CursorConFalloDeCreacion:
    """Delegado de cursor que falla al crear un índice concreto."""

    def __init__(self, cursor, nombre_indice, error):
        self._cursor = cursor
        self._nombre = nombre_indice
        self._error = error
        self.fallos = 0

    def execute(self, sql, *args):
        texto = " ".join(str(sql).split()).upper()
        if texto.startswith("CREATE UNIQUE INDEX") and f" {self._nombre.upper()} " in f"{texto} ":
            self.fallos += 1
            raise self._error
        self._cursor.execute(sql, *args)
        return self

    def __getattr__(self, nombre):
        return getattr(self._cursor, nombre)


class _BaseSeguridadIndices(unittest.TestCase):

    def setUp(self):
        self.conexion = sqlite3.connect(":memory:")
        self.addCleanup(self.conexion.close)
        self.conexion.execute(
            "CREATE TABLE factura_arca(id INTEGER PRIMARY KEY, ambiente_arca TEXT, emisor_id INTEGER, "
            "punto_venta_num INTEGER, tipo_comprobante_num INTEGER, numero_comprobante_num INTEGER, cae TEXT)"
        )
        self.conexion.execute(
            "CREATE TABLE intentos_emision_arca(id INTEGER PRIMARY KEY, ambiente_arca TEXT, cuit_emisor TEXT, "
            "punto_venta INTEGER, tipo_comprobante INTEGER, numero_planificado INTEGER, estado TEXT NOT NULL)"
        )
        self.conexion.execute("CREATE TABLE resumenes(id INTEGER PRIMARY KEY, cae TEXT)")
        self.conexion.commit()

    def factura(self, ambiente="HOMOLOGACION", numero=8, cae="111", emisor=1, pv=2, tipo=11):
        self.conexion.execute(
            "INSERT INTO factura_arca(ambiente_arca, emisor_id, punto_venta_num, tipo_comprobante_num, "
            "numero_comprobante_num, cae) VALUES(?,?,?,?,?,?)",
            (ambiente, emisor, pv, tipo, numero, cae),
        )

    def intento(self, ambiente="HOMOLOGACION", estado="ENVIANDO", numero=10):
        self.conexion.execute(
            "INSERT INTO intentos_emision_arca(ambiente_arca, cuit_emisor, punto_venta, tipo_comprobante, "
            "numero_planificado, estado) VALUES(?, '20123456789', 2, 11, ?, ?)",
            (ambiente, numero, estado),
        )

    def indices(self):
        return self.conexion.execute(
            "SELECT type, name, tbl_name, sql FROM sqlite_master WHERE type='index' ORDER BY name"
        ).fetchall()

    def sql_indice(self, nombre):
        fila = self.conexion.execute(
            "SELECT sql FROM sqlite_master WHERE type='index' AND name=?", (nombre,)
        ).fetchone()
        return fila[0] if fila else None

    def filas(self):
        return {
            tabla: self.conexion.execute(f"SELECT * FROM {tabla} ORDER BY id").fetchall()
            for tabla in ("factura_arca", "intentos_emision_arca", "resumenes")
        }

    def foto(self):
        return {
            "indices": self.indices(),
            "objetos": self.conexion.execute(
                "SELECT type, name, tbl_name, sql FROM sqlite_master ORDER BY type, name"
            ).fetchall(),
            "filas": self.filas(),
            "user_version": self.conexion.execute("PRAGMA user_version").fetchone()[0],
        }

    def migrar(self, funcion, *args, cursor=None):
        """Ejecuta una migración permitida; devuelve (salida, excepción)."""
        self.conexion.commit()
        salida = io.StringIO()
        error = None
        with redirect_stdout(salida):
            try:
                funcion(cursor or self.conexion.cursor(), *args)
            except AssertionError:
                raise
            except Exception as excepcion:  # noqa: BLE001 - se evalúa como detención
                error = excepcion
        return salida.getvalue(), error

    def assertDetenidaSinPerderProtecciones(self, antes, error):
        self.assertEqual(
            self.indices(), antes["indices"],
            "PROTECCION_PERDIDA: la migración alteró o eliminó índices existentes",
        )
        self.assertEqual(self.filas(), antes["filas"], "FILAS_MODIFICADAS")
        self.assertEqual(self.foto(), antes, "ESQUEMA_MODIFICADO")
        self.assertIsNotNone(error, "NO_SE_DETUVO: la migración continuó sin detenerse")


class GuardiaPruebasTest(_BaseSeguridadIndices):

    def test_guardia_rechaza_archivos_y_uri(self):
        for destino, kwargs in (("fm_master.db", {}), ("file::memory:", {"uri": True}),
                                (":memory:", {"uri": True})):
            with self.subTest(destino=destino, kwargs=kwargs):
                with self.assertRaises(AssertionError):
                    sqlite3.connect(destino, **kwargs)

    def test_crear_base_y_otras_migraciones_estan_bloqueadas(self):
        self.assertIn("crear_base", _FUNCIONES_PROHIBIDAS)
        self.assertIn("migrar_factura_arca_columnas_normalizadas", _FUNCIONES_PROHIBIDAS)
        self.assertIn("crear_tabla_intentos_emision_arca", _FUNCIONES_PROHIBIDAS)
        with self.assertRaises(AssertionError):
            database.crear_base()
        self.assertEqual(sorted(_FUNCIONES_PERMITIDAS & set(_FUNCIONES_PROHIBIDAS)), [])


class IndicesFacturaArcaSeguridadTest(_BaseSeguridadIndices):

    def test_faltantes_sin_duplicados_se_crean_exactos_sin_tocar_filas(self):
        self.factura("HOMOLOGACION")
        self.factura(None, numero=9, cae="222")
        antes = self.filas()

        _salida, error = self.migrar(database.migrar_indices_unicos_factura_arca)

        self.assertIsNone(error)
        for nombre in INDICES_FACTURA:
            self.assertEqual(self.sql_indice(nombre), _ddl_esperado(nombre))
        self.assertEqual(self.filas(), antes)

    def test_indices_exactos_no_se_reemplazan(self):
        self.factura()
        self.migrar(database.migrar_indices_unicos_factura_arca)
        antes = self.foto()
        sentencias = []
        self.conexion.set_trace_callback(sentencias.append)

        salida, error = self.migrar(database.migrar_indices_unicos_factura_arca)

        self.conexion.set_trace_callback(None)
        self.assertIsNone(error)
        self.assertEqual(salida, "")
        self.assertEqual(self.foto(), antes)
        modificadoras = ("CREATE", "DROP", "ALTER", "INSERT", "UPDATE", "DELETE", "REPLACE")
        self.assertEqual([s for s in sentencias if s.lstrip().upper().startswith(modificadoras)], [])

    def test_historico_reconocido_sin_duplicados_se_reemplaza_y_verifica(self):
        self.factura("HOMOLOGACION")
        self.factura(None, numero=9, cae="222")
        self.conexion.execute(HISTORICO_IDENTIDAD_0FE8AC7)
        self.conexion.execute(HISTORICO_CAE_0FE8AC7)
        antes = self.filas()

        _salida, error = self.migrar(database.migrar_indices_unicos_factura_arca)

        self.assertIsNone(error)
        for nombre in INDICES_FACTURA:
            self.assertEqual(self.sql_indice(nombre), _ddl_esperado(nombre))
        self.assertEqual(self.filas(), antes)

    def test_objeto_ajeno_con_el_nombre_del_indice_no_se_elimina(self):
        self.factura()
        self.conexion.execute("CREATE TABLE idx_factura_arca_cae_unico(id INTEGER)")
        antes = self.foto()

        _salida, error = self.migrar(
            database._migrar_indice_factura_arca, "idx_factura_arca_cae_unico",
            *_ESPERADOS["idx_factura_arca_cae_unico"][1:],
        )

        self.assertDetenidaSinPerderProtecciones(antes, error)

    @unittest.expectedFailure
    def test_historico_con_duplicados_trim_se_detiene_y_conserva_indice(self):
        # Hoy: DROP del índice CAE histórico y omisión del reemplazo por duplicados.
        self.factura("HOMOLOGACION", numero=8, cae="111")
        self.factura("HOMOLOGACION", numero=9, cae=" 111 ")
        self.conexion.execute(HISTORICO_CAE_0FE8AC7)
        antes = self.foto()

        _salida, error = self.migrar(database.migrar_indices_unicos_factura_arca)

        self.assertDetenidaSinPerderProtecciones(antes, error)

    @unittest.expectedFailure
    def test_historico_null_con_duplicados_trim_se_detiene_y_conserva_indice(self):
        # Hoy: se reemplaza por el índice de ambiente conocido y las filas NULL
        # quedan sin unicidad de CAE.
        self.factura(None, numero=8, cae="111")
        self.factura(None, numero=9, cae=" 111 ")
        self.conexion.execute(HISTORICO_CAE_0FE8AC7)
        antes = self.foto()

        _salida, error = self.migrar(database.migrar_indices_unicos_factura_arca)

        self.assertDetenidaSinPerderProtecciones(antes, error)

    @unittest.expectedFailure
    def test_definicion_desconocida_se_detiene_sin_eliminarla(self):
        # Hoy: cualquier definición distinta se elimina y se recrea.
        self.factura()
        self.conexion.execute("CREATE UNIQUE INDEX idx_factura_arca_cae_unico ON factura_arca(cae)")
        antes = self.foto()

        _salida, error = self.migrar(database.migrar_indices_unicos_factura_arca)

        self.assertDetenidaSinPerderProtecciones(antes, error)

    @unittest.expectedFailure
    def test_indice_homonimo_sobre_otra_tabla_se_detiene_sin_eliminarlo(self):
        # Hoy: se elimina el índice de resumenes y se crea uno nuevo en factura_arca.
        self.factura()
        self.conexion.execute("INSERT INTO resumenes(cae) VALUES('111')")
        self.conexion.execute("CREATE UNIQUE INDEX idx_factura_arca_cae_unico ON resumenes(cae)")
        antes = self.foto()

        _salida, error = self.migrar(database.migrar_indices_unicos_factura_arca)

        self.assertDetenidaSinPerderProtecciones(antes, error)

    @unittest.expectedFailure
    def test_faltante_con_duplicados_se_detiene_sin_modificar_filas(self):
        # Hoy: imprime una advertencia y continúa sin la protección.
        self.factura(None, numero=8, cae="111")
        self.factura(None, numero=9, cae=" 111 ")
        antes = self.foto()

        _salida, error = self.migrar(
            database._migrar_indice_factura_arca, "idx_factura_arca_cae_historico_unico",
            *_ESPERADOS["idx_factura_arca_cae_historico_unico"][1:],
        )

        self.assertDetenidaSinPerderProtecciones(antes, error)

    @unittest.expectedFailure
    def test_error_de_creacion_restaura_el_historico_atomicamente(self):
        # Hoy: el DROP del histórico queda aplicado aunque falle la creación.
        for error_simulado in (sqlite3.IntegrityError("fallo simulado"),
                               sqlite3.OperationalError("fallo simulado")):
            with self.subTest(error=type(error_simulado).__name__):
                self.conexion.execute("DELETE FROM factura_arca")
                for fila in self.indices():
                    self.conexion.execute(f"DROP INDEX {fila[1]}")
                self.factura()
                self.conexion.execute(HISTORICO_CAE_0FE8AC7)
                antes = self.foto()
                cursor = _CursorConFalloDeCreacion(
                    self.conexion.cursor(), "idx_factura_arca_cae_unico", error_simulado
                )

                _salida, error = self.migrar(
                    database._migrar_indice_factura_arca, "idx_factura_arca_cae_unico",
                    *_ESPERADOS["idx_factura_arca_cae_unico"][1:], cursor=cursor,
                )

                self.assertEqual(cursor.fallos, 1, "CONFIGURACION: el fallo simulado no se ejecutó")
                self.assertDetenidaSinPerderProtecciones(antes, error)


class IndicesIntentosSeguridadTest(_BaseSeguridadIndices):

    def test_faltantes_sin_duplicados_se_crean_exactos_y_repetir_no_cambia(self):
        self.intento("HOMOLOGACION")
        self.intento(None)
        antes = self.filas()

        _salida, error = self.migrar(database.migrar_indices_activos_intentos_emision_arca)

        self.assertIsNone(error)
        for nombre in INDICES_INTENTOS:
            self.assertEqual(self.sql_indice(nombre), _ddl_esperado(nombre))
        self.assertEqual(self.filas(), antes)
        foto = self.foto()
        salida, error = self.migrar(database.migrar_indices_activos_intentos_emision_arca)
        self.assertIsNone(error)
        self.assertEqual(salida, "")
        self.assertEqual(self.foto(), foto)

    def test_global_historico_se_reemplaza_por_indices_por_ambiente(self):
        self.intento(None)
        self.conexion.execute(HISTORICO_INTENTOS_GLOBAL_AF3E31E)
        antes = self.filas()

        _salida, error = self.migrar(database.migrar_indices_activos_intentos_emision_arca)

        self.assertIsNone(error)
        self.assertIsNone(self.sql_indice(INDICE_GLOBAL_INTENTOS))
        for nombre in INDICES_INTENTOS:
            self.assertEqual(self.sql_indice(nombre), _ddl_esperado(nombre))
        self.assertEqual(self.filas(), antes)
        with self.assertRaises(sqlite3.IntegrityError):
            self.intento(None)
        self.intento("HOMOLOGACION")
        self.intento("PRODUCCION")

    @unittest.expectedFailure
    def test_literal_enviando_alterado_se_detiene(self):
        # Hoy: lower() equipara 'enviando' con 'ENVIANDO' y acepta el índice sin aviso.
        for nombre in INDICES_INTENTOS:
            self.conexion.execute(_ddl_esperado(nombre).replace("'ENVIANDO'", "'enviando'"))
        for con_duplicados in (False, True):
            with self.subTest(con_duplicados=con_duplicados):
                if con_duplicados:
                    self.intento("HOMOLOGACION")
                    self.intento("HOMOLOGACION")
                antes = self.foto()

                _salida, error = self.migrar(database.migrar_indices_activos_intentos_emision_arca)

                self.assertDetenidaSinPerderProtecciones(antes, error)

    @unittest.expectedFailure
    def test_global_de_definicion_desconocida_no_se_elimina(self):
        # Hoy: DROP INDEX incondicional del índice global anterior.
        self.intento(None)
        self.conexion.execute(
            f"CREATE UNIQUE INDEX {INDICE_GLOBAL_INTENTOS} ON intentos_emision_arca"
            "(cuit_emisor, punto_venta, tipo_comprobante, numero_planificado)"
        )
        antes = self.foto()

        _salida, error = self.migrar(database.migrar_indices_activos_intentos_emision_arca)

        self.assertDetenidaSinPerderProtecciones(antes, error)

    @unittest.expectedFailure
    def test_error_al_crear_reemplazo_conserva_global_historico(self):
        # Hoy: el global se elimina antes de crear los reemplazos.
        for error_simulado in (sqlite3.IntegrityError("fallo simulado"),
                               sqlite3.OperationalError("fallo simulado")):
            with self.subTest(error=type(error_simulado).__name__):
                for fila in self.indices():
                    self.conexion.execute(f"DROP INDEX {fila[1]}")
                self.conexion.execute("DELETE FROM intentos_emision_arca")
                self.intento(None)
                self.conexion.execute(HISTORICO_INTENTOS_GLOBAL_AF3E31E)
                antes = self.foto()
                cursor = _CursorConFalloDeCreacion(
                    self.conexion.cursor(), "idx_intentos_emision_arca_clave_activa_historica", error_simulado
                )

                _salida, error = self.migrar(
                    database.migrar_indices_activos_intentos_emision_arca, cursor=cursor
                )

                self.assertEqual(cursor.fallos, 1, "CONFIGURACION: el fallo simulado no se ejecutó")
                self.assertDetenidaSinPerderProtecciones(antes, error)

    @unittest.expectedFailure
    def test_faltante_con_intentos_activos_duplicados_se_detiene(self):
        # Hoy: crea el índice por ambiente, omite el histórico y continúa.
        self.intento(None)
        self.intento(None)
        antes = self.foto()

        _salida, error = self.migrar(database.migrar_indices_activos_intentos_emision_arca)

        self.assertDetenidaSinPerderProtecciones(antes, error)


if __name__ == "__main__":
    unittest.main()
