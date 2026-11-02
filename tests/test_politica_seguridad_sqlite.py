"""Política de seguridad de estados SQLite previa a una futura migración protegida.

Estas pruebas documentan qué estados deben impedir una migración automática.
Todas las bases son SQLite en memoria y su esquema está escrito a mano, sin
derivarlo de las constantes del detector, para que una divergencia entre el
detector y una estructura real pueda descubrirse.

Las pruebas marcadas con ``expectedFailure`` documentan requisitos futuros que
el detector actual todavía no cumple. No deben corregirse modificando estas
pruebas: cuando el detector implemente la política, pasarán inesperadamente y
habrá que retirar la marca.
"""

import importlib.util
import sqlite3
import sys
import unittest
from pathlib import Path
from types import ModuleType
from unittest.mock import patch

from services.arca.fiscal_normalization import normalizar_identidad_factura


_CONNECT_ORIGINAL = sqlite3.connect


def _connect_solo_memoria(base, *args, **kwargs):
    """Rechaza cualquier conexión que no sea una base SQLite en memoria."""
    if base != ":memory:" or kwargs.get("uri"):
        raise AssertionError(f"Conexión SQLite no permitida en esta prueba: {base!r}")
    return _CONNECT_ORIGINAL(base, *args, **kwargs)


def _cargar_database_aislado():
    """Carga database.py con runtime_paths falso para no resolver rutas reales."""
    nombre_modulo = "_database_politica_seguridad_sqlite_test"
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

_guardia_connect = patch("sqlite3.connect", _connect_solo_memoria)


def setUpModule():
    _guardia_connect.start()


def tearDownModule():
    _guardia_connect.stop()


BLOQUEANTES = {"BLOQUEADA", "VERSION_INCOMPATIBLE"}

# Esquema histórico escrito a mano con tipos, claves primarias y restricciones
# similares a las de una instalación real. Incluye columnas adicionales que el
# detector no exige, para no limitarse a su lista mínima.
_TABLAS_BASE = {
    "clientes": (
        "id INTEGER PRIMARY KEY AUTOINCREMENT",
        "nombre TEXT NOT NULL",
        "cuit TEXT",
        "emisor_id INTEGER",
        "emisor_recomendado_id INTEGER",
        "modalidad_comprobante TEXT DEFAULT 'FACTURA'",
        "emisor_habitual TEXT",
    ),
    "servicios": (
        "id INTEGER PRIMARY KEY AUTOINCREMENT",
        "cliente_id INTEGER",
        "nombre TEXT",
        "fecha_inicio TEXT",
        "fecha_fin TEXT",
        "renovable INTEGER DEFAULT 0",
        "estado_periodo TEXT",
    ),
    "catalogo_servicios": (
        "id INTEGER PRIMARY KEY AUTOINCREMENT",
        "nombre TEXT NOT NULL UNIQUE",
        "descripcion TEXT",
        "precio REAL DEFAULT 0",
        "activo INTEGER DEFAULT 1",
    ),
    "emisores_facturacion": (
        "id INTEGER PRIMARY KEY AUTOINCREMENT",
        "alias TEXT NOT NULL",
        "cuit TEXT",
        "activo INTEGER DEFAULT 1",
        "emisor_fiscal_id INTEGER",
    ),
    "emisores_fiscales": (
        "id INTEGER PRIMARY KEY AUTOINCREMENT",
        "razon_social TEXT",
        "cuit TEXT NOT NULL",
        "condicion_iva TEXT",
        "tipo_factura TEXT",
        "ambiente_arca TEXT",
        "punto_venta INTEGER",
        "ruta_certificado TEXT",
        "ruta_clave_privada TEXT",
        "carpeta_facturas TEXT",
    ),
    "emisor_fiscal_arca_config": (
        "id INTEGER PRIMARY KEY AUTOINCREMENT",
        "emisor_fiscal_id INTEGER NOT NULL",
        "ambiente_arca TEXT NOT NULL",
        "punto_venta INTEGER",
        "ruta_certificado TEXT",
        "ruta_clave_privada TEXT",
        "carpeta_facturas TEXT",
    ),
    "arca_config": (
        "id INTEGER PRIMARY KEY CHECK (id = 1)",
        "modo_trabajo TEXT NOT NULL DEFAULT 'MANUAL'",
    ),
    "servicio_renovaciones": (
        "id INTEGER PRIMARY KEY AUTOINCREMENT",
        "servicio_id INTEGER NOT NULL",
        "cliente_id INTEGER",
        "fecha_renovacion TEXT",
        "resumen_id INTEGER",
    ),
    "resumenes": (
        "id INTEGER PRIMARY KEY AUTOINCREMENT",
        "numero TEXT",
        "cliente_id INTEGER",
        "emisor_fiscal_id INTEGER",
        "fecha TEXT",
        "fecha_vencimiento TEXT",
        "total REAL DEFAULT 0",
        "estado_facturacion TEXT",
        "fecha_facturacion TEXT",
        "cae TEXT",
        "vencimiento_cae TEXT",
        "numero_factura TEXT",
    ),
    "resumen_conceptos": (
        "id INTEGER PRIMARY KEY AUTOINCREMENT",
        "resumen_id INTEGER NOT NULL",
        "servicio_id INTEGER",
        "concepto TEXT",
        "importe REAL DEFAULT 0",
        "fecha_inicio TEXT",
        "fecha_fin TEXT",
    ),
    "cobros": (
        "id INTEGER PRIMARY KEY AUTOINCREMENT",
        "cliente_id INTEGER",
        "fecha TEXT",
        "importe REAL NOT NULL DEFAULT 0",
        "factura_arca_id INTEGER",
    ),
    "tareas": (
        "id INTEGER PRIMARY KEY AUTOINCREMENT",
        "cliente_id INTEGER",
        "fecha TEXT",
        "hora TEXT",
        "tipo TEXT",
        "estado TEXT",
    ),
    "contactos": (
        "id INTEGER PRIMARY KEY AUTOINCREMENT",
        "cliente_id INTEGER",
        "fecha TEXT",
        "hora TEXT",
        "tipo TEXT",
        "resultado TEXT",
    ),
    "intentos_emision_arca": (
        "id INTEGER PRIMARY KEY AUTOINCREMENT",
        "resumen_id INTEGER",
        "cliente_id INTEGER",
        "emisor_fiscal_id INTEGER",
        "emisor_id INTEGER",
        "cuit_emisor TEXT",
        "punto_venta INTEGER",
        "tipo_comprobante INTEGER",
        "numero_planificado INTEGER",
        "concepto INTEGER",
        "estado TEXT NOT NULL",
        "cae TEXT",
        "ambiente_arca TEXT",
        "contexto_fiscal_json TEXT",
        "contexto_fiscal_version INTEGER",
        "contexto_fiscal_hash TEXT",
    ),
    "oportunidades": (
        "id INTEGER PRIMARY KEY AUTOINCREMENT",
        "cliente_id INTEGER",
        "nombre_potencial TEXT",
        "fecha TEXT",
        "estado TEXT",
    ),
    "notificaciones": (
        "id INTEGER PRIMARY KEY AUTOINCREMENT",
        "tipo TEXT",
        "titulo TEXT",
        "estado TEXT",
        "fecha TEXT",
        "clave TEXT",
    ),
    "usuarios": (
        "id INTEGER PRIMARY KEY AUTOINCREMENT",
        "usuario TEXT NOT NULL",
        "clave TEXT NOT NULL",
        "rol TEXT DEFAULT 'operador'",
        "activo INTEGER DEFAULT 1",
    ),
}

_COLUMNAS_FACTURA_ARCA = (
    ("id", "INTEGER PRIMARY KEY AUTOINCREMENT"),
    ("cliente_id", "INTEGER"),
    ("emisor_id", "INTEGER"),
    ("resumen_id", "INTEGER"),
    ("fecha", "TEXT"),
    ("punto_venta", "TEXT"),
    ("tipo_comprobante", "TEXT"),
    ("importe_total", "REAL DEFAULT 0"),
    ("estado", "TEXT"),
    ("numero_factura", "TEXT"),
    ("cae", "TEXT"),
    ("vencimiento_cae", "TEXT"),
    ("punto_venta_num", "INTEGER"),
    ("tipo_comprobante_num", "INTEGER"),
    ("numero_comprobante_num", "INTEGER"),
    ("tipo_documento_receptor", "INTEGER"),
    ("documento_receptor", "TEXT"),
    ("snapshot_fiscal_json", "TEXT"),
    ("snapshot_version", "INTEGER"),
    ("snapshot_hash", "TEXT"),
    ("ambiente_arca", "TEXT"),
    ("ruta_pdf_relativa", "TEXT"),
    ("ruta_pdf_absoluta", "TEXT"),
)

# SQL tal como lo emiten las migraciones de índices únicos de database.py.
_INDICES_UNICOS = {
    "idx_factura_arca_identidad_unica": (
        "CREATE UNIQUE INDEX idx_factura_arca_identidad_unica ON factura_arca("
        "ambiente_arca, emisor_id, punto_venta_num, tipo_comprobante_num, numero_comprobante_num) "
        "WHERE ambiente_arca IS NOT NULL AND numero_comprobante_num IS NOT NULL AND emisor_id > 0 "
        "AND punto_venta_num > 0 AND tipo_comprobante_num > 0 AND numero_comprobante_num > 0"
    ),
    "idx_factura_arca_identidad_historica_unica": (
        "CREATE UNIQUE INDEX idx_factura_arca_identidad_historica_unica ON factura_arca("
        "emisor_id, punto_venta_num, tipo_comprobante_num, numero_comprobante_num) "
        "WHERE ambiente_arca IS NULL AND numero_comprobante_num IS NOT NULL AND emisor_id > 0 "
        "AND punto_venta_num > 0 AND tipo_comprobante_num > 0 AND numero_comprobante_num > 0"
    ),
    "idx_factura_arca_cae_unico": (
        "CREATE UNIQUE INDEX idx_factura_arca_cae_unico ON factura_arca(ambiente_arca, TRIM(cae)) "
        "WHERE ambiente_arca IS NOT NULL AND TRIM(COALESCE(cae, '')) <> ''"
    ),
    "idx_factura_arca_cae_historico_unico": (
        "CREATE UNIQUE INDEX idx_factura_arca_cae_historico_unico ON factura_arca(TRIM(cae)) "
        "WHERE ambiente_arca IS NULL AND TRIM(COALESCE(cae, '')) <> ''"
    ),
    "idx_intentos_emision_arca_clave_activa_ambiente": (
        "CREATE UNIQUE INDEX idx_intentos_emision_arca_clave_activa_ambiente ON intentos_emision_arca("
        "ambiente_arca, cuit_emisor, punto_venta, tipo_comprobante, numero_planificado) "
        "WHERE ambiente_arca IS NOT NULL AND TRIM(COALESCE(cuit_emisor, '')) <> '' AND punto_venta > 0 "
        "AND tipo_comprobante > 0 AND numero_planificado > 0 "
        "AND estado IN ('PENDIENTE_RECONCILIAR', 'ENVIANDO', 'CONFLICTO_MANUAL')"
    ),
    "idx_intentos_emision_arca_clave_activa_historica": (
        "CREATE UNIQUE INDEX idx_intentos_emision_arca_clave_activa_historica ON intentos_emision_arca("
        "cuit_emisor, punto_venta, tipo_comprobante, numero_planificado) "
        "WHERE ambiente_arca IS NULL AND TRIM(COALESCE(cuit_emisor, '')) <> '' AND punto_venta > 0 "
        "AND tipo_comprobante > 0 AND numero_planificado > 0 "
        "AND estado IN ('PENDIENTE_RECONCILIAR', 'ENVIANDO', 'CONFLICTO_MANUAL')"
    ),
}

_INDICES_FACTURA = tuple(nombre for nombre in _INDICES_UNICOS if nombre.startswith("idx_factura_arca_"))
_INDICES_INTENTOS = tuple(nombre for nombre in _INDICES_UNICOS if nombre.startswith("idx_intentos_emision_arca_"))
_INDICES_POR_TABLA = {"factura_arca": _INDICES_FACTURA, "intentos_emision_arca": _INDICES_INTENTOS}

# Clasificación de tablas escrita a mano, independiente de las constantes del detector.
_TABLAS_ESENCIALES_NEGOCIO = (
    "clientes", "servicios", "resumenes", "resumen_conceptos", "cobros", "factura_arca",
    "emisores_facturacion", "emisores_fiscales", "usuarios",
)
_TABLAS_ESENCIALES_OPERATIVAS = (
    "servicio_renovaciones", "tareas", "contactos", "oportunidades", "notificaciones",
    "catalogo_servicios", "arca_config",
)
_TABLAS_EXTENSION_HISTORICA = ("intentos_emision_arca", "emisor_fiscal_arca_config")


def _crear_esquema_historico(
    conexion,
    *,
    omitir_tablas=(),
    reemplazar_tablas=None,
    omitir_columnas_factura=(),
    omitir_indices=(),
    reemplazar_indices=None,
):
    """Construye una base histórica sin versión a partir del esquema escrito a mano."""
    reemplazar_tablas = reemplazar_tablas or {}
    reemplazar_indices = reemplazar_indices or {}
    omitir_indices = set(omitir_indices)
    for tabla in omitir_tablas:
        omitir_indices.update(_INDICES_POR_TABLA.get(tabla, ()))
    cursor = conexion.cursor()
    for tabla, columnas in _TABLAS_BASE.items():
        if tabla in omitir_tablas:
            continue
        if tabla in reemplazar_tablas:
            cursor.execute(reemplazar_tablas[tabla])
            continue
        cursor.execute(f"CREATE TABLE {tabla} ({', '.join(columnas)})")

    if "factura_arca" not in omitir_tablas:
        if "factura_arca" in reemplazar_tablas:
            cursor.execute(reemplazar_tablas["factura_arca"])
        else:
            columnas_factura = [
                f"{nombre} {tipo}" for nombre, tipo in _COLUMNAS_FACTURA_ARCA if nombre not in omitir_columnas_factura
            ]
            cursor.execute(f"CREATE TABLE factura_arca ({', '.join(columnas_factura)})")

    for nombre, sql in _INDICES_UNICOS.items():
        if nombre in omitir_indices:
            continue
        cursor.execute(reemplazar_indices.get(nombre, sql))
    conexion.commit()


def _insertar_factura(conexion, **valores):
    columnas = ", ".join(valores)
    marcadores = ", ".join("?" for _ in valores)
    conexion.execute(f"INSERT INTO factura_arca ({columnas}) VALUES ({marcadores})", tuple(valores.values()))


def _factura_normalizada(**extra):
    valores = {
        "emisor_id": 1,
        "punto_venta": "00002",
        "tipo_comprobante": "Factura C",
        "numero_factura": "00002-00000001",
        "punto_venta_num": 2,
        "tipo_comprobante_num": 11,
        "numero_comprobante_num": 1,
        "ambiente_arca": "HOMOLOGACION",
    }
    valores.update(extra)
    return valores


class _PoliticaBase(unittest.TestCase):

    def setUp(self):
        self.conexion = sqlite3.connect(":memory:")
        self.addCleanup(self.conexion.close)

    def inspeccionar(self, **kwargs):
        return database.inspeccionar_estado_base_sqlite(self.conexion, **kwargs)


class AislamientoSQLiteTest(unittest.TestCase):

    def test_guardia_rechaza_rutas_de_archivo_y_uri(self):
        with self.assertRaises(AssertionError):
            sqlite3.connect("fm_master.db")
        with self.assertRaises(AssertionError):
            sqlite3.connect("file:fm_master.db?mode=rw", uri=True)
        with self.assertRaises(AssertionError):
            database.conectar()

    def test_database_aislado_no_apunta_a_una_ruta_real(self):
        self.assertEqual(str(database.DATABASE_PATH), ":memory:")


class EsquemaManualCoherenteTest(_PoliticaBase):
    """Valida que el esquema manual sea reconocido; si falla, el detector y el esquema real divergen."""

    def test_esquema_historico_completo_es_historica_sin_version_y_nunca_actual(self):
        _crear_esquema_historico(self.conexion)

        resultado = self.inspeccionar()

        self.assertEqual(resultado.estado, "HISTORICA_SIN_VERSION")
        self.assertNotEqual(resultado.estado, "ACTUAL")
        self.assertIsNone(resultado.version_registrada)
        self.assertEqual(resultado.estructuras_pendientes, ())
        self.assertEqual(resultado.condiciones_pendientes, ())

    def test_inspeccion_no_modifica_la_base(self):
        _crear_esquema_historico(self.conexion)
        _insertar_factura(self.conexion, **_factura_normalizada())
        self.conexion.commit()
        esquema_antes = self.conexion.execute(
            "SELECT type, name, sql FROM sqlite_master ORDER BY type, name"
        ).fetchall()
        cambios_antes = self.conexion.total_changes

        self.inspeccionar()

        self.assertEqual(self.conexion.total_changes, cambios_antes)
        self.assertFalse(self.conexion.in_transaction)
        self.assertEqual(
            self.conexion.execute("SELECT type, name, sql FROM sqlite_master ORDER BY type, name").fetchall(),
            esquema_antes,
        )
        self.assertEqual(self.conexion.execute("PRAGMA user_version").fetchone()[0], 0)


class BaseVaciaSinAutorizacionTest(_PoliticaBase):

    def test_base_vacia_sin_confirmacion_no_es_nueva(self):
        resultado = self.inspeccionar()

        self.assertEqual(resultado.estado, "BLOQUEADA")

    def test_confirmacion_no_booleana_no_autoriza_instalacion_nueva(self):
        for valor in (False, None, 0, "true", 1, "1", "NUEVA"):
            with self.subTest(valor=valor):
                self.assertEqual(self.inspeccionar(instalacion_nueva_confirmada=valor).estado, "BLOQUEADA")

    def test_base_vacia_sin_confirmacion_debe_bloquear_con_motivo_claro(self):
        resultado = self.inspeccionar()

        self.assertEqual(resultado.estado, "BLOQUEADA")
        self.assertIn("Base vacía bloqueada", " ".join(resultado.motivos))
        self.assertIn("falta confirmación explícita de instalación nueva", " ".join(resultado.motivos))


class BaseHistoricaSinVersionTest(_PoliticaBase):

    def test_historica_sin_version_no_se_considera_actual_ni_nueva(self):
        _crear_esquema_historico(self.conexion)

        resultado = self.inspeccionar(instalacion_nueva_confirmada=True)

        self.assertEqual(resultado.estado, "HISTORICA_SIN_VERSION")
        self.assertTrue(any("ACTUAL" in motivo for motivo in resultado.motivos))

    def test_trigger_desconocido_debe_bloquear(self):
        # Un trigger ajeno puede alterar datos durante una migración y debe bloquear.
        _crear_esquema_historico(self.conexion)
        self.conexion.execute(
            "CREATE TRIGGER trg_desconocido AFTER INSERT ON factura_arca "
            "BEGIN UPDATE factura_arca SET cae = NULL WHERE id = NEW.id; END"
        )

        resultado = self.inspeccionar()

        self.assertEqual(resultado.estado, "BLOQUEADA")
        self.assertIn("trigger_no_reconocido:trg_desconocido(factura_arca)", resultado.motivos)

    def test_tabla_esencial_sin_clave_primaria_debe_bloquear(self):
        _crear_esquema_historico(
            self.conexion,
            reemplazar_tablas={
                "clientes": (
                    "CREATE TABLE clientes (id TEXT, nombre TEXT, emisor_id INTEGER, "
                    "emisor_recomendado_id INTEGER, modalidad_comprobante TEXT, emisor_habitual TEXT)"
                )
            },
        )

        resultado = self.inspeccionar()

        self.assertEqual(resultado.estado, "BLOQUEADA")
        self.assertIn("clave_primaria_incompatible:clientes", resultado.motivos)


class ClavesPrimariasEsencialesTest(_PoliticaBase):

    def _crear_con_claves(self, definiciones, **opciones):
        reemplazos = {}
        for tabla, (definicion_id, restriccion) in definiciones.items():
            originales = (
                tuple(f"{nombre} {tipo}" for nombre, tipo in _COLUMNAS_FACTURA_ARCA)
                if tabla == "factura_arca" else _TABLAS_BASE[tabla]
            )
            columnas = [columna for columna in originales if columna.split()[0] != "id"]
            if definicion_id is not None:
                columnas.insert(0, f"id {definicion_id}")
            if restriccion is not None:
                columnas.append(restriccion)
            reemplazos[tabla] = f"CREATE TABLE {tabla} ({', '.join(columnas)})"
        _crear_esquema_historico(self.conexion, reemplazar_tablas=reemplazos, **opciones)

    def test_cada_tabla_esencial_con_id_integer_sin_pk_bloquea(self):
        for tabla in _TABLAS_ESENCIALES_NEGOCIO + _TABLAS_ESENCIALES_OPERATIVAS:
            with self.subTest(tabla=tabla):
                conexion = sqlite3.connect(":memory:")
                try:
                    originales = (
                        tuple(f"{nombre} {tipo}" for nombre, tipo in _COLUMNAS_FACTURA_ARCA)
                        if tabla == "factura_arca" else _TABLAS_BASE[tabla]
                    )
                    columnas = [
                        "id INTEGER" if columna.split()[0] == "id" else columna for columna in originales
                    ]
                    _crear_esquema_historico(
                        conexion, reemplazar_tablas={tabla: f"CREATE TABLE {tabla} ({', '.join(columnas)})"}
                    )

                    resultado = database.inspeccionar_estado_base_sqlite(conexion)

                    self.assertEqual(resultado.estado, "BLOQUEADA")
                    self.assertIn(f"clave_primaria_incompatible:{tabla}", resultado.motivos)
                finally:
                    conexion.close()

    def test_id_ausente_bloquea_y_conserva_columna_pendiente(self):
        self._crear_con_claves({"clientes": (None, None)})

        resultado = self.inspeccionar()

        self.assertEqual(resultado.estado, "BLOQUEADA")
        self.assertIn("clave_primaria_incompatible:clientes", resultado.motivos)
        self.assertIn("columna:clientes.id", resultado.estructuras_pendientes)

    def test_pk_con_tipo_text_int_o_bigint_bloquea(self):
        for tipo in ("TEXT", "INT", "BIGINT"):
            with self.subTest(tipo=tipo):
                # Cada variante usa una base independiente para conservar todo el esquema.
                conexion = sqlite3.connect(":memory:")
                try:
                    columnas = [f"id {tipo} PRIMARY KEY", *_TABLAS_BASE["clientes"][1:]]
                    _crear_esquema_historico(
                        conexion, reemplazar_tablas={"clientes": f"CREATE TABLE clientes ({', '.join(columnas)})"}
                    )

                    resultado = database.inspeccionar_estado_base_sqlite(conexion)

                    self.assertEqual(resultado.estado, "BLOQUEADA")
                    self.assertIn("clave_primaria_incompatible:clientes", resultado.motivos)
                finally:
                    conexion.close()

    def test_pk_en_otra_columna_bloquea(self):
        self._crear_con_claves({"clientes": ("INTEGER", "PRIMARY KEY(nombre)")})

        resultado = self.inspeccionar()

        self.assertEqual(resultado.estado, "BLOQUEADA")
        self.assertIn("clave_primaria_incompatible:clientes", resultado.motivos)

    def test_pk_compuesta_con_id_primero_bloquea(self):
        self._crear_con_claves({"clientes": ("INTEGER", "PRIMARY KEY(id, nombre)")})

        resultado = self.inspeccionar()

        self.assertEqual(resultado.estado, "BLOQUEADA")
        self.assertIn("clave_primaria_incompatible:clientes", resultado.motivos)

    def test_pk_compuesta_con_id_segundo_bloquea(self):
        self._crear_con_claves({"clientes": ("INTEGER", "PRIMARY KEY(nombre, id)")})

        resultado = self.inspeccionar()

        self.assertEqual(resultado.estado, "BLOQUEADA")
        self.assertIn("clave_primaria_incompatible:clientes", resultado.motivos)

    def test_pk_valida_con_y_sin_autoincrement_y_a_nivel_de_tabla(self):
        self._crear_con_claves({
            "clientes": ("INTEGER PRIMARY KEY", None),
            "servicios": ("INTEGER PRIMARY KEY AUTOINCREMENT", None),
            "cobros": ("INTEGER", "PRIMARY KEY(id)"),
            "tareas": ("integer PRIMARY KEY", None),
            "contactos": ('" integer " PRIMARY KEY', None),
        })

        resultado = self.inspeccionar()

        self.assertEqual(resultado.estado, "HISTORICA_SIN_VERSION")
        self.assertFalse(any(motivo.startswith("clave_primaria_incompatible:") for motivo in resultado.motivos))
        # INTEGER PRIMARY KEY puede tener notnull=0 en los metadatos de SQLite.
        info = self.conexion.execute("PRAGMA table_info(clientes)").fetchall()
        self.assertEqual(info[0][3], 0)

    def test_varias_incompatibilidades_y_duplicados_conservan_motivos(self):
        self._crear_con_claves(
            {"clientes": ("INTEGER", None), "tareas": ("TEXT PRIMARY KEY", None)},
            omitir_tablas=("cobros",),
        )
        self.conexion.executemany(
            "INSERT INTO usuarios (usuario, clave) VALUES (?, ?)", (("admin", "a"), ("admin", "b"))
        )

        resultado = self.inspeccionar()

        self.assertEqual(resultado.estado, "BLOQUEADA")
        self.assertIn("clave_primaria_incompatible:clientes", resultado.motivos)
        self.assertIn("clave_primaria_incompatible:tareas", resultado.motivos)
        self.assertIn("tabla_esencial_ausente:cobros; no se recreará automáticamente", resultado.motivos)
        self.assertIn("duplicados:usuarios(usuario)", resultado.motivos)

    def test_version_incompatible_prevalece_y_conserva_motivo_pk(self):
        self._crear_con_claves({"clientes": ("INTEGER", None)})
        self.conexion.execute("PRAGMA user_version = 3")

        resultado = self.inspeccionar()

        self.assertEqual(resultado.estado, "VERSION_INCOMPATIBLE")
        self.assertIn("clave_primaria_incompatible:clientes", resultado.motivos)

    def test_marcador_de_version_prevalece_sobre_pk_incompatible(self):
        self._crear_con_claves({"clientes": ("INTEGER", None)})
        self.conexion.execute("CREATE TABLE schema_migrations (version TEXT)")

        self.assertEqual(self.inspeccionar().estado, "VERSION_INCOMPATIBLE")

    def test_extensiones_presentes_sin_pk_no_se_validan_en_esta_etapa(self):
        self._crear_con_claves({
            "intentos_emision_arca": ("TEXT", None),
            "emisor_fiscal_arca_config": ("TEXT", None),
        })

        self.assertEqual(self.inspeccionar().estado, "HISTORICA_SIN_VERSION")

    def test_inspeccion_de_pk_incompatible_no_modifica_esquema_ni_datos(self):
        self._crear_con_claves({"clientes": ("INTEGER", None)})
        self.conexion.execute("INSERT INTO clientes (id, nombre) VALUES (7, 'Cliente ficticio')")
        self.conexion.commit()
        antes = tuple(self.conexion.iterdump())
        cambios = self.conexion.total_changes
        consultas = []
        self.conexion.set_trace_callback(consultas.append)
        try:
            resultado = self.inspeccionar()
        finally:
            self.conexion.set_trace_callback(None)

        self.assertEqual(resultado.estado, "BLOQUEADA")
        self.assertEqual(tuple(self.conexion.iterdump()), antes)
        self.assertEqual(self.conexion.total_changes, cambios)
        self.assertFalse(self.conexion.in_transaction)
        self.assertTrue(consultas)
        self.assertTrue(all(consulta.lstrip().upper().startswith(("SELECT", "PRAGMA")) for consulta in consultas))


class TriggersNoReconocidosTest(_PoliticaBase):

    @staticmethod
    def _motivos_trigger(resultado):
        return [motivo for motivo in resultado.motivos if motivo.startswith("trigger_")]

    def _inspeccionar_en_base_nueva(self, *sentencias):
        conexion = sqlite3.connect(":memory:")
        try:
            _crear_esquema_historico(conexion)
            for sentencia in sentencias:
                conexion.execute(sentencia)
            return database.inspeccionar_estado_base_sqlite(conexion)
        finally:
            conexion.close()

    def test_before_y_after_sobre_insert_update_delete_bloquean(self):
        for momento in ("BEFORE", "AFTER"):
            for evento in ("INSERT", "UPDATE", "DELETE"):
                with self.subTest(momento=momento, evento=evento):
                    resultado = self._inspeccionar_en_base_nueva(
                        f"CREATE TRIGGER trg_prueba {momento} {evento} ON clientes BEGIN SELECT 1; END"
                    )

                    self.assertEqual(resultado.estado, "BLOQUEADA")
                    self.assertEqual(self._motivos_trigger(resultado), ["trigger_no_reconocido:trg_prueba(clientes)"])

    def test_trigger_sobre_tablas_esenciales_y_extensiones_historicas_bloquea(self):
        for tabla in _TABLAS_ESENCIALES_NEGOCIO + _TABLAS_ESENCIALES_OPERATIVAS + _TABLAS_EXTENSION_HISTORICA:
            with self.subTest(tabla=tabla):
                resultado = self._inspeccionar_en_base_nueva(
                    f"CREATE TRIGGER trg_{tabla} AFTER INSERT ON {tabla} BEGIN SELECT 1; END"
                )

                self.assertEqual(resultado.estado, "BLOQUEADA")
                self.assertEqual(self._motivos_trigger(resultado), [f"trigger_no_reconocido:trg_{tabla}({tabla})"])

    def test_trigger_sobre_tabla_desconocida_bloquea(self):
        resultado = self._inspeccionar_en_base_nueva(
            "CREATE TABLE auditoria_ajena (detalle TEXT)",
            "CREATE TRIGGER trg_auditoria BEFORE DELETE ON auditoria_ajena BEGIN SELECT 1; END",
        )

        self.assertEqual(resultado.estado, "BLOQUEADA")
        self.assertEqual(self._motivos_trigger(resultado), ["trigger_no_reconocido:trg_auditoria(auditoria_ajena)"])

    def test_trigger_instead_of_sobre_vista_bloquea(self):
        resultado = self._inspeccionar_en_base_nueva(
            "CREATE VIEW vista_clientes AS SELECT id, nombre FROM clientes",
            "CREATE TRIGGER trg_vista INSTEAD OF INSERT ON vista_clientes "
            "BEGIN INSERT INTO clientes (nombre) VALUES (NEW.nombre); END",
        )

        self.assertEqual(resultado.estado, "BLOQUEADA")
        self.assertEqual(self._motivos_trigger(resultado), ["trigger_no_reconocido:trg_vista(vista_clientes)"])

    def test_trigger_temporal_sobre_tabla_principal_bloquea(self):
        _crear_esquema_historico(self.conexion)
        self.conexion.execute("CREATE TEMP TRIGGER trg_temporal AFTER UPDATE ON clientes BEGIN SELECT 1; END")

        resultado = self.inspeccionar()

        self.assertEqual(resultado.estado, "BLOQUEADA")
        self.assertEqual(
            self._motivos_trigger(resultado), ["trigger_temporal_no_reconocido:trg_temporal(clientes)"]
        )

    def test_trigger_temporal_sobre_tabla_temporal_bloquea(self):
        _crear_esquema_historico(self.conexion)
        self.conexion.execute("CREATE TEMP TABLE auxiliar (valor TEXT)")
        self.conexion.execute("CREATE TEMP TRIGGER trg_auxiliar AFTER INSERT ON auxiliar BEGIN SELECT 1; END")

        resultado = self.inspeccionar()

        self.assertEqual(resultado.estado, "BLOQUEADA")
        self.assertEqual(
            self._motivos_trigger(resultado), ["trigger_temporal_no_reconocido:trg_auxiliar(auxiliar)"]
        )

    def test_base_vacia_con_trigger_temporal_no_es_nueva(self):
        self.conexion.execute("CREATE TEMP TABLE auxiliar (valor TEXT)")
        self.conexion.execute("CREATE TEMP TRIGGER trg_auxiliar AFTER INSERT ON auxiliar BEGIN SELECT 1; END")

        for confirmada in (True, False):
            with self.subTest(instalacion_nueva_confirmada=confirmada):
                resultado = self.inspeccionar(instalacion_nueva_confirmada=confirmada)

                self.assertEqual(resultado.estado, "BLOQUEADA")
                self.assertEqual(
                    self._motivos_trigger(resultado), ["trigger_temporal_no_reconocido:trg_auxiliar(auxiliar)"]
                )

    def test_varios_triggers_generan_motivos_completos_y_ordenados(self):
        _crear_esquema_historico(self.conexion)
        for sentencia in (
            "CREATE TRIGGER trg_zeta AFTER INSERT ON tareas BEGIN SELECT 1; END",
            "CREATE TRIGGER trg_alfa BEFORE UPDATE ON cobros BEGIN SELECT 1; END",
            "CREATE TRIGGER trg_medio AFTER DELETE ON factura_arca BEGIN SELECT 1; END",
            "CREATE TEMP TRIGGER trg_temp_b AFTER INSERT ON clientes BEGIN SELECT 1; END",
            "CREATE TEMP TRIGGER trg_temp_a AFTER INSERT ON servicios BEGIN SELECT 1; END",
        ):
            self.conexion.execute(sentencia)

        resultado = self.inspeccionar()

        self.assertEqual(resultado.estado, "BLOQUEADA")
        self.assertEqual(
            self._motivos_trigger(resultado),
            [
                "trigger_no_reconocido:trg_alfa(cobros)",
                "trigger_no_reconocido:trg_medio(factura_arca)",
                "trigger_no_reconocido:trg_zeta(tareas)",
                "trigger_temporal_no_reconocido:trg_temp_a(servicios)",
                "trigger_temporal_no_reconocido:trg_temp_b(clientes)",
            ],
        )

    def test_nombres_especiales_con_espacios_y_comillas(self):
        _crear_esquema_historico(self.conexion)
        self.conexion.execute('CREATE TABLE "tabla rara ""x""" (valor TEXT)')
        for sentencia in (
            'CREATE TRIGGER "trg con espacios" AFTER INSERT ON "tabla rara ""x""" BEGIN SELECT 1; END',
            'CREATE TRIGGER "trg ""comillas""" AFTER INSERT ON clientes BEGIN SELECT 1; END',
            "CREATE TRIGGER [Trg-Mayúsculas] AFTER INSERT ON clientes BEGIN SELECT 1; END",
            "CREATE TRIGGER 'trg ''simple''' AFTER INSERT ON clientes BEGIN SELECT 1; END",
        ):
            self.conexion.execute(sentencia)

        resultado = self.inspeccionar()

        esperados = sorted([
            ("trg con espacios", 'tabla rara "x"'),
            ('trg "comillas"', "clientes"),
            ("Trg-Mayúsculas", "clientes"),
            ("trg 'simple'", "clientes"),
        ])
        self.assertEqual(resultado.estado, "BLOQUEADA")
        self.assertEqual(
            self._motivos_trigger(resultado),
            [f"trigger_no_reconocido:{nombre}({tabla})" for nombre, tabla in esperados],
        )

    def test_version_incompatible_prevalece_y_conserva_motivos_de_trigger(self):
        casos = {
            "user_version": "PRAGMA user_version = 4",
            "marcador": "CREATE TABLE schema_migrations (version TEXT)",
        }
        for caso, sentencia in casos.items():
            with self.subTest(caso=caso):
                conexion = sqlite3.connect(":memory:")
                try:
                    _crear_esquema_historico(conexion)
                    conexion.execute("CREATE TRIGGER trg_permanente AFTER INSERT ON clientes BEGIN SELECT 1; END")
                    conexion.execute("CREATE TEMP TRIGGER trg_temporal AFTER INSERT ON clientes BEGIN SELECT 1; END")
                    conexion.execute(sentencia)

                    resultado = database.inspeccionar_estado_base_sqlite(conexion)

                    self.assertEqual(resultado.estado, "VERSION_INCOMPATIBLE")
                    self.assertEqual(
                        self._motivos_trigger(resultado),
                        [
                            "trigger_no_reconocido:trg_permanente(clientes)",
                            "trigger_temporal_no_reconocido:trg_temporal(clientes)",
                        ],
                    )
                finally:
                    conexion.close()

    def test_triggers_combinados_con_otras_causas_conservan_todos_los_motivos(self):
        _crear_esquema_historico(
            self.conexion,
            omitir_tablas=("cobros",),
            reemplazar_tablas={
                "clientes": f"CREATE TABLE clientes ({', '.join(['id INTEGER', *_TABLAS_BASE['clientes'][1:]])})"
            },
        )
        self.conexion.executemany(
            "INSERT INTO usuarios (usuario, clave) VALUES (?, ?)", (("admin", "a"), ("admin", "b"))
        )
        self.conexion.execute("CREATE TRIGGER trg_tareas AFTER INSERT ON tareas BEGIN SELECT 1; END")
        self.conexion.execute("CREATE TEMP TRIGGER trg_temporal AFTER INSERT ON servicios BEGIN SELECT 1; END")

        resultado = self.inspeccionar()

        self.assertEqual(resultado.estado, "BLOQUEADA")
        for motivo in (
            "tabla_esencial_ausente:cobros; no se recreará automáticamente",
            "clave_primaria_incompatible:clientes",
            "trigger_no_reconocido:trg_tareas(tareas)",
            "trigger_temporal_no_reconocido:trg_temporal(servicios)",
            "duplicados:usuarios(usuario)",
        ):
            self.assertIn(motivo, resultado.motivos)
        self.assertIn("tabla:cobros", resultado.estructuras_pendientes)

    def test_inspeccion_no_ejecuta_triggers_ni_modifica_datos(self):
        _crear_esquema_historico(self.conexion)
        self.conexion.execute("CREATE TABLE registro_disparos (detalle TEXT)")
        self.conexion.execute("INSERT INTO clientes (id, nombre) VALUES (1, 'Cliente ficticio')")
        for sentencia in (
            "CREATE TRIGGER trg_insert AFTER INSERT ON clientes "
            "BEGIN INSERT INTO registro_disparos VALUES ('insert'); END",
            "CREATE TRIGGER trg_update BEFORE UPDATE ON clientes "
            "BEGIN INSERT INTO registro_disparos VALUES ('update'); END",
            "CREATE TRIGGER trg_delete AFTER DELETE ON clientes "
            "BEGIN INSERT INTO registro_disparos VALUES ('delete'); END",
            "CREATE TEMP TRIGGER trg_temp AFTER UPDATE ON clientes "
            "BEGIN DELETE FROM clientes; END",
        ):
            self.conexion.execute(sentencia)
        self.conexion.commit()
        antes = tuple(self.conexion.iterdump())
        cambios = self.conexion.total_changes
        consultas = []
        self.conexion.set_trace_callback(consultas.append)
        try:
            resultado = self.inspeccionar()
        finally:
            self.conexion.set_trace_callback(None)

        self.assertEqual(resultado.estado, "BLOQUEADA")
        self.assertEqual(tuple(self.conexion.iterdump()), antes)
        self.assertEqual(self.conexion.total_changes, cambios)
        self.assertEqual(self.conexion.execute("SELECT COUNT(*) FROM registro_disparos").fetchone()[0], 0)
        self.assertEqual(self.conexion.execute("SELECT COUNT(*) FROM clientes").fetchone()[0], 1)
        self.assertEqual(
            self.conexion.execute("SELECT COUNT(*) FROM sqlite_temp_master WHERE type='trigger'").fetchone()[0], 1
        )
        self.assertFalse(self.conexion.in_transaction)
        self.assertTrue(consultas)
        # Un trigger ejecutado aparecería en el trace como "-- TRIGGER nombre".
        self.assertTrue(all(consulta.lstrip().upper().startswith(("SELECT", "PRAGMA")) for consulta in consultas))

    def test_bases_sin_triggers_mantienen_su_clasificacion(self):
        casos = (
            ("vacia_sin_confirmar", None, {}, "BLOQUEADA"),
            ("vacia_confirmada", None, {"instalacion_nueva_confirmada": True}, "NUEVA"),
            ("historica", {}, {}, "HISTORICA_SIN_VERSION"),
            ("historica_con_vista", {"vista": True}, {}, "HISTORICA_SIN_VERSION"),
            ("incompleta", {"omitir_tablas": ("intentos_emision_arca",)}, {}, "INCOMPLETA"),
        )
        for caso, esquema, opciones, esperado in casos:
            with self.subTest(caso=caso):
                conexion = sqlite3.connect(":memory:")
                try:
                    if esquema is not None:
                        esquema = dict(esquema)
                        crear_vista = esquema.pop("vista", False)
                        _crear_esquema_historico(conexion, **esquema)
                        if crear_vista:
                            conexion.execute("CREATE VIEW vista_clientes AS SELECT id, nombre FROM clientes")

                    resultado = database.inspeccionar_estado_base_sqlite(conexion, **opciones)

                    self.assertEqual(resultado.estado, esperado)
                    self.assertEqual(self._motivos_trigger(resultado), [])
                finally:
                    conexion.close()


class BaseIncompletaTest(_PoliticaBase):

    def _inspeccionar_sin_tabla(self, tabla):
        conexion = sqlite3.connect(":memory:")
        self.addCleanup(conexion.close)
        _crear_esquema_historico(conexion, omitir_tablas=(tabla,))
        return database.inspeccionar_estado_base_sqlite(conexion)

    def _verificar_tabla_esencial_bloquea(self, tablas):
        for tabla in tablas:
            with self.subTest(tabla=tabla):
                resultado = self._inspeccionar_sin_tabla(tabla)

                self.assertEqual(resultado.estado, "BLOQUEADA")
                self.assertIn(f"tabla:{tabla}", resultado.estructuras_pendientes)
                self.assertIn(
                    f"tabla_esencial_ausente:{tabla}; no se recreará automáticamente", resultado.motivos
                )

    def test_falta_tabla_esencial_no_es_historica(self):
        _crear_esquema_historico(self.conexion, omitir_tablas=("clientes",))

        resultado = self.inspeccionar()

        self.assertNotEqual(resultado.estado, "HISTORICA_SIN_VERSION")
        self.assertIn("tabla:clientes", resultado.estructuras_pendientes)

    def test_falta_extension_conocida_es_incompleta(self):
        _crear_esquema_historico(
            self.conexion, omitir_columnas_factura=("ruta_pdf_relativa", "ruta_pdf_absoluta")
        )

        resultado = self.inspeccionar()

        self.assertEqual(resultado.estado, "INCOMPLETA")
        self.assertIn("columna:factura_arca.ruta_pdf_relativa", resultado.estructuras_pendientes)

    def test_falta_tabla_esencial_debe_bloquear(self):
        _crear_esquema_historico(self.conexion, omitir_tablas=("clientes",))

        self.assertIn(self.inspeccionar().estado, BLOQUEANTES)

    def test_vista_en_lugar_de_tabla_esencial_debe_bloquear(self):
        # El detector solo reconoce objetos de tipo tabla: la vista cuenta como
        # tabla esencial ausente y no se intentará crear una tabla encima.
        _crear_esquema_historico(
            self.conexion,
            reemplazar_tablas={"clientes": "CREATE VIEW clientes AS SELECT 1 AS id, 'x' AS nombre"},
        )

        resultado = self.inspeccionar()

        self.assertEqual(resultado.estado, "BLOQUEADA")
        self.assertIn("tabla_esencial_ausente:clientes; no se recreará automáticamente", resultado.motivos)

    def test_grupo_a_tabla_esencial_de_negocio_ausente_bloquea(self):
        self._verificar_tabla_esencial_bloquea(_TABLAS_ESENCIALES_NEGOCIO)

    def test_grupo_b_tabla_esencial_operativa_ausente_bloquea(self):
        self._verificar_tabla_esencial_bloquea(_TABLAS_ESENCIALES_OPERATIVAS)

    def test_grupo_c_extension_historica_ausente_es_incompleta_no_bloqueada(self):
        # INCOMPLETA no autoriza recrear la tabla ni migrar; solo indica que
        # su ausencia no basta por sí sola para bloquear.
        for tabla in _TABLAS_EXTENSION_HISTORICA:
            with self.subTest(tabla=tabla):
                resultado = self._inspeccionar_sin_tabla(tabla)

                self.assertEqual(resultado.estado, "INCOMPLETA")
                self.assertIn(f"tabla:{tabla}", resultado.estructuras_pendientes)
                self.assertFalse(any("tabla_esencial_ausente" in motivo for motivo in resultado.motivos))

    def test_grupos_cubren_exactamente_las_tablas_del_detector(self):
        grupos = (
            set(_TABLAS_ESENCIALES_NEGOCIO) | set(_TABLAS_ESENCIALES_OPERATIVAS) | set(_TABLAS_EXTENSION_HISTORICA)
        )

        self.assertEqual(grupos, set(database._ESTRUCTURAS_INSPECCION_ESPERADAS))
        self.assertEqual(set(_TABLAS_EXTENSION_HISTORICA), set(database._TABLAS_EXTENSION_HISTORICA))
        self.assertIsInstance(database._TABLAS_EXTENSION_HISTORICA, frozenset)

    def test_tabla_desconocida_agregada_al_detector_se_bloquea_por_defecto(self):
        estructuras = dict(database._ESTRUCTURAS_INSPECCION_ESPERADAS)
        estructuras["tabla_futura"] = ("id",)
        _crear_esquema_historico(self.conexion)

        with patch.object(database, "_ESTRUCTURAS_INSPECCION_ESPERADAS", estructuras):
            resultado = self.inspeccionar()

        self.assertEqual(resultado.estado, "BLOQUEADA")
        self.assertIn("tabla_esencial_ausente:tabla_futura; no se recreará automáticamente", resultado.motivos)

    def test_varias_tablas_esenciales_ausentes_se_informan_todas(self):
        _crear_esquema_historico(self.conexion, omitir_tablas=("clientes", "tareas", "intentos_emision_arca"))

        resultado = self.inspeccionar()

        self.assertEqual(resultado.estado, "BLOQUEADA")
        ausentes = [motivo for motivo in resultado.motivos if motivo.startswith("tabla_esencial_ausente:")]
        self.assertEqual(
            ausentes,
            [
                "tabla_esencial_ausente:clientes; no se recreará automáticamente",
                "tabla_esencial_ausente:tareas; no se recreará automáticamente",
            ],
        )
        self.assertIn("tabla:intentos_emision_arca", resultado.estructuras_pendientes)

    def test_version_incompatible_prevalece_sobre_tabla_esencial_ausente(self):
        _crear_esquema_historico(self.conexion, omitir_tablas=("clientes",))
        self.conexion.execute("PRAGMA user_version = 4")

        resultado = self.inspeccionar()

        self.assertEqual(resultado.estado, "VERSION_INCOMPATIBLE")
        self.assertIn("tabla:clientes", resultado.estructuras_pendientes)

    def test_tabla_esencial_ausente_y_duplicados_informan_ambos_motivos(self):
        _crear_esquema_historico(self.conexion, omitir_tablas=("clientes",))
        self.conexion.executemany(
            "INSERT INTO usuarios (usuario, clave) VALUES (?, ?)", (("admin", "a"), ("admin", "b"))
        )

        resultado = self.inspeccionar()

        self.assertEqual(resultado.estado, "BLOQUEADA")
        self.assertIn("tabla_esencial_ausente:clientes; no se recreará automáticamente", resultado.motivos)
        self.assertIn("duplicados:usuarios(usuario)", resultado.motivos)

    def test_inspeccion_con_tabla_esencial_ausente_no_modifica_la_base(self):
        _crear_esquema_historico(self.conexion, omitir_tablas=("clientes",))
        esquema_antes = self.conexion.execute("SELECT type, name, sql FROM sqlite_master ORDER BY type, name").fetchall()
        cambios_antes = self.conexion.total_changes

        self.inspeccionar()

        self.assertEqual(self.conexion.total_changes, cambios_antes)
        self.assertEqual(
            self.conexion.execute("SELECT type, name, sql FROM sqlite_master ORDER BY type, name").fetchall(),
            esquema_antes,
        )

    @unittest.expectedFailure
    def test_requisito_futuro_identidad_normalizada_sin_tabla_de_intentos_debe_bloquear(self):
        # Pendiente: combinación histórica contradictoria. Las columnas normalizadas
        # de factura_arca (22/08) son posteriores a intentos_emision_arca (16/08);
        # tenerlas sin esa tabla no corresponde a ninguna versión legítima. Hoy la
        # ausencia de la extensión se clasifica como INCOMPLETA.
        _crear_esquema_historico(self.conexion, omitir_tablas=("intentos_emision_arca",))

        self.assertIn(self.inspeccionar().estado, BLOQUEANTES)


class VersionIncompatibleTest(_PoliticaBase):

    def test_user_version_no_reconocida_es_incompatible(self):
        for version in (3, -1):
            with self.subTest(version=version):
                conexion = sqlite3.connect(":memory:")
                self.addCleanup(conexion.close)
                _crear_esquema_historico(conexion)
                conexion.execute(f"PRAGMA user_version = {version}")

                resultado = database.inspeccionar_estado_base_sqlite(conexion)

                self.assertEqual(resultado.estado, "VERSION_INCOMPATIBLE")
                self.assertEqual(resultado.version_registrada, version)

    def test_tabla_de_versionado_desconocida_es_incompatible(self):
        _crear_esquema_historico(self.conexion)
        self.conexion.execute("CREATE TABLE schema_migrations (version TEXT PRIMARY KEY)")

        self.assertEqual(self.inspeccionar().estado, "VERSION_INCOMPATIBLE")

    def test_version_incompatible_prevalece_sobre_duplicados(self):
        _crear_esquema_historico(self.conexion, omitir_indices=("idx_factura_arca_identidad_unica",))
        _insertar_factura(self.conexion, **_factura_normalizada(cae="111"))
        _insertar_factura(self.conexion, **_factura_normalizada(cae="222"))
        self.conexion.execute("PRAGMA user_version = 7")

        self.assertEqual(self.inspeccionar().estado, "VERSION_INCOMPATIBLE")

    def test_base_vacia_con_version_no_puede_ser_nueva(self):
        self.conexion.execute("PRAGMA user_version = 1")

        resultado = self.inspeccionar(instalacion_nueva_confirmada=True)

        self.assertEqual(resultado.estado, "VERSION_INCOMPATIBLE")


class DuplicadosFiscalesTest(_PoliticaBase):

    def test_identidad_duplicada_en_mismo_ambiente_bloquea(self):
        _crear_esquema_historico(self.conexion, omitir_indices=("idx_factura_arca_identidad_unica",))
        _insertar_factura(self.conexion, **_factura_normalizada(cae="111"))
        _insertar_factura(self.conexion, **_factura_normalizada(cae="222"))

        resultado = self.inspeccionar()

        self.assertEqual(resultado.estado, "BLOQUEADA")
        self.assertIn("duplicados:factura_arca.identidad_fiscal", resultado.motivos)

    def test_identidad_duplicada_con_ambiente_desconocido_bloquea(self):
        _crear_esquema_historico(
            self.conexion, omitir_indices=("idx_factura_arca_identidad_historica_unica",)
        )
        _insertar_factura(self.conexion, **_factura_normalizada(ambiente_arca=None, cae="111"))
        _insertar_factura(self.conexion, **_factura_normalizada(ambiente_arca=None, cae="222"))

        self.assertEqual(self.inspeccionar().estado, "BLOQUEADA")

    def test_misma_identidad_en_homologacion_y_produccion_no_bloquea(self):
        _crear_esquema_historico(self.conexion)
        _insertar_factura(self.conexion, **_factura_normalizada(ambiente_arca="HOMOLOGACION", cae="111"))
        _insertar_factura(self.conexion, **_factura_normalizada(ambiente_arca="PRODUCCION", cae="222"))

        self.assertEqual(self.inspeccionar().estado, "HISTORICA_SIN_VERSION")

    def test_intento_activo_duplicado_bloquea(self):
        _crear_esquema_historico(
            self.conexion, omitir_indices=("idx_intentos_emision_arca_clave_activa_ambiente",)
        )
        for _ in range(2):
            self.conexion.execute(
                "INSERT INTO intentos_emision_arca (cuit_emisor, punto_venta, tipo_comprobante, "
                "numero_planificado, estado, ambiente_arca) VALUES ('20111111112', 2, 11, 5, 'ENVIANDO', 'HOMOLOGACION')"
            )

        resultado = self.inspeccionar()

        self.assertEqual(resultado.estado, "BLOQUEADA")
        self.assertIn("duplicados:intentos_emision_arca.clave_activa", resultado.motivos)

    def test_usuario_duplicado_bloquea(self):
        _crear_esquema_historico(self.conexion)
        self.conexion.executemany(
            "INSERT INTO usuarios (usuario, clave) VALUES (?, ?)", (("admin", "a"), ("admin", "b"))
        )

        self.assertEqual(self.inspeccionar().estado, "BLOQUEADA")

    def test_normalizador_confirma_colision_entre_formatos_textuales(self):
        self.assertEqual(
            normalizar_identidad_factura("00002", "Factura C", "00002-00000001"),
            normalizar_identidad_factura("00002", "Factura C", "2-1"),
        )

    def test_cae_duplicado_tras_trim_debe_bloquear(self):
        # Sin el índice único de CAE, la migración actual (_migrar_indice_factura_arca)
        # advierte los duplicados y omite crear el índice, sin necesariamente lanzar
        # una excepción; el detector debe bloquear antes de llegar a ese punto.
        _crear_esquema_historico(self.conexion, omitir_indices=("idx_factura_arca_cae_unico",))
        _insertar_factura(self.conexion, **_factura_normalizada(cae="12345678901234"))
        _insertar_factura(
            self.conexion,
            **_factura_normalizada(
                numero_factura="00002-00000002", numero_comprobante_num=2, cae=" 12345678901234 "
            ),
        )

        resultado = self.inspeccionar()

        self.assertEqual(resultado.estado, "BLOQUEADA")
        self.assertIn("duplicados:factura_arca.cae", resultado.motivos)
        self.assertNotIn("duplicados:factura_arca.identidad_fiscal", resultado.motivos)

    def test_requisito_futuro_colision_tras_normalizar_debe_bloquear(self):
        # Con el índice presente, el segundo UPDATE de normalización fallaría.
        # Sin él, la migración de índices advertiría y omitiría crearlo.
        _crear_esquema_historico(self.conexion)
        for numero, cae in (("00002-00000001", "111"), ("2-1", "222")):
            _insertar_factura(
                self.conexion,
                **_factura_normalizada(
                    numero_factura=numero,
                    punto_venta_num=None,
                    tipo_comprobante_num=None,
                    numero_comprobante_num=None,
                    cae=cae,
                ),
            )

        resultado = self.inspeccionar()
        self.assertEqual(resultado.estado, "BLOQUEADA")
        self.assertIn("duplicados:factura_arca.identidad_fiscal_proyectada", resultado.motivos)

    def test_requisito_futuro_duplicados_en_factura_sin_ambiente_debe_bloquear(self):
        # La migración agrega ambiente_arca sin backfill: ambas filas quedan en
        # el grupo histórico NULL, cuyo índice no podría crearse por duplicados.
        _crear_esquema_historico(
            self.conexion, omitir_columnas_factura=("ambiente_arca",), omitir_indices=_INDICES_FACTURA
        )
        for cae in ("111", "222"):
            datos = _factura_normalizada(cae=cae)
            datos.pop("ambiente_arca")
            _insertar_factura(self.conexion, **datos)

        resultado = self.inspeccionar()
        self.assertEqual(resultado.estado, "BLOQUEADA")
        self.assertIn("duplicados:factura_arca.identidad_fiscal_proyectada", resultado.motivos)


_MOTIVO_PROYECCION = "duplicados:factura_arca.identidad_fiscal_proyectada"
_COLUMNAS_NORMALIZADAS = ("punto_venta_num", "tipo_comprobante_num", "numero_comprobante_num")


def _factura_pendiente(**extra):
    valores = dict.fromkeys(_COLUMNAS_NORMALIZADAS)
    valores.update(extra)
    return _factura_normalizada(**valores)


class IdentidadFiscalProyectadaTest(_PoliticaBase):

    def _preparar(self, *facturas, **esquema):
        conexion = sqlite3.connect(":memory:")
        self.addCleanup(conexion.close)
        _crear_esquema_historico(conexion, **esquema)
        omitidas = esquema.get("omitir_columnas_factura", ())
        for factura in facturas:
            _insertar_factura(conexion, **{k: v for k, v in factura.items() if k not in omitidas})
        return conexion

    def _comprobar_colision(self, conexion):
        resultado = database.inspeccionar_estado_base_sqlite(conexion)
        self.assertEqual(resultado.estado, "BLOQUEADA")
        self.assertEqual(resultado.motivos.count(_MOTIVO_PROYECCION), 1)
        return resultado

    def test_variantes_textuales_colisionan(self):
        for punto, tipo, numero in (
            ("2", "11", "2-1"),
            (" 0002 ", " factura c ", " 0002-001 "),
            ("\t2\n", "\tFACTURA C\n", "\t2-1\n"),
            ("\u00a02\u00a0", "11", "\u00a02-1\u00a0"),
        ):
            with self.subTest(punto=punto, tipo=tipo, numero=numero):
                conexion = self._preparar(
                    _factura_pendiente(cae="111"),
                    _factura_pendiente(punto_venta=punto, tipo_comprobante=tipo, numero_factura=numero, cae="222"),
                )
                resultado = self._comprobar_colision(conexion)
                self.assertNotIn("duplicados:factura_arca.identidad_fiscal", resultado.motivos)

    def test_alias_factura_a_colisionan(self):
        conexion = self._preparar(
            _factura_pendiente(tipo_comprobante="Factura A"),
            _factura_pendiente(tipo_comprobante=" 1 ", numero_factura="2-1"),
        )
        self._comprobar_colision(conexion)

    def test_fila_normalizada_y_pendiente_colisionan(self):
        conexion = self._preparar(
            _factura_normalizada(cae="111"), _factura_pendiente(numero_factura="2-1", cae="222")
        )
        self._comprobar_colision(conexion)

    def test_cada_combinacion_parcial_se_recalcula_completa(self):
        for mascara in range(1, 8):
            with self.subTest(mascara=mascara):
                parcial = {
                    columna: None if mascara & (1 << posicion) else 99
                    for posicion, columna in enumerate(_COLUMNAS_NORMALIZADAS)
                }
                conexion = self._preparar(
                    _factura_normalizada(), _factura_normalizada(numero_factura="2-1", **parcial)
                )
                self._comprobar_colision(conexion)

    def test_cada_columna_normalizada_ausente_se_proyecta_como_null(self):
        for omitidas in [(columna,) for columna in _COLUMNAS_NORMALIZADAS] + [_COLUMNAS_NORMALIZADAS]:
            with self.subTest(omitidas=omitidas):
                conexion = self._preparar(
                    _factura_pendiente(), _factura_pendiente(numero_factura="2-1"),
                    omitir_columnas_factura=omitidas,
                    omitir_indices=_INDICES_FACTURA,
                )
                self._comprobar_colision(conexion)

    def test_sin_ambiente_ni_columnas_normalizadas(self):
        conexion = self._preparar(
            _factura_pendiente(), _factura_pendiente(numero_factura="2-1"),
            omitir_columnas_factura=("ambiente_arca", *_COLUMNAS_NORMALIZADAS),
            omitir_indices=_INDICES_FACTURA,
        )
        self._comprobar_colision(conexion)

    def test_colisiones_en_cada_ambiente_y_grupo_historico(self):
        for ambiente in ("HOMOLOGACION", "PRODUCCION", None):
            with self.subTest(ambiente=ambiente):
                conexion = self._preparar(
                    _factura_pendiente(ambiente_arca=ambiente),
                    _factura_pendiente(ambiente_arca=ambiente, numero_factura="2-1"),
                )
                self._comprobar_colision(conexion)

    def test_no_mezcla_ambientes_ni_infiere_null(self):
        conexion = self._preparar(
            *(_factura_pendiente(ambiente_arca=ambiente) for ambiente in ("HOMOLOGACION", "PRODUCCION", None))
        )
        resultado = database.inspeccionar_estado_base_sqlite(conexion)
        self.assertEqual(resultado.estado, "INCOMPLETA")
        self.assertNotIn(_MOTIVO_PROYECCION, resultado.motivos)

    def test_no_mezcla_emisores_aunque_compartan_cuit(self):
        conexion = self._preparar(_factura_pendiente(emisor_id=1), _factura_pendiente(emisor_id=2))
        conexion.executemany(
            "INSERT INTO emisores_facturacion(id, alias, cuit) VALUES (?, ?, ?)",
            ((1, "Uno", "20111111112"), (2, "Dos", "20111111112")),
        )
        resultado = database.inspeccionar_estado_base_sqlite(conexion)
        self.assertEqual(resultado.estado, "INCOMPLETA")
        self.assertNotIn(_MOTIVO_PROYECCION, resultado.motivos)

    def test_identidades_realmente_distintas_no_colisionan(self):
        for distinta in (
            {"punto_venta": "3", "numero_factura": "3-1"},
            {"tipo_comprobante": "Factura A"},
            {"numero_factura": "2-2"},
        ):
            with self.subTest(distinta=distinta):
                conexion = self._preparar(_factura_pendiente(), _factura_pendiente(**distinta))
                resultado = database.inspeccionar_estado_base_sqlite(conexion)
                self.assertEqual(resultado.estado, "INCOMPLETA")
                self.assertNotIn(_MOTIVO_PROYECCION, resultado.motivos)

    def test_no_recalcula_filas_completas_aunque_el_texto_contradiga(self):
        conexion = self._preparar(
            _factura_normalizada(),
            _factura_normalizada(numero_comprobante_num=2),
        )
        with patch.object(database, "normalizar_identidad_factura", side_effect=AssertionError("No debe normalizar")):
            resultado = database.inspeccionar_estado_base_sqlite(conexion)
        self.assertEqual(resultado.estado, "BLOQUEADA")
        self.assertIn("contradiccion:factura_arca.identidad_fiscal", resultado.motivos)
        self.assertNotIn(_MOTIVO_PROYECCION, resultado.motivos)

    def test_filas_incompletas_o_contradictorias_no_colisionan(self):
        for datos in (
            {"punto_venta": None},
            {"punto_venta": "0"},
            {"tipo_comprobante": None},
            {"tipo_comprobante": "Factura B"},
            {"numero_factura": None},
            {"numero_factura": ""},
            {"numero_factura": "   "},
            {"numero_factura": "sin numero"},
            {"numero_factura": "3-1"},
            {"numero_factura": "2-0"},
            {"numero_factura": "000002-000000001"},
        ):
            with self.subTest(datos=datos):
                factura = _factura_pendiente(**datos)
                conexion = self._preparar(factura, factura)
                resultado = database.inspeccionar_estado_base_sqlite(conexion)
                estado_esperado = (
                    "HISTORICA_SIN_VERSION" if datos.get("numero_factura", "2-1") in (None, "", "   ")
                    else "INCOMPLETA"
                )
                self.assertEqual(resultado.estado, estado_esperado)
                self.assertNotIn(_MOTIVO_PROYECCION, resultado.motivos)

    def test_emisor_null_cero_o_negativo_no_participa(self):
        for emisor in (None, 0, -1):
            with self.subTest(emisor=emisor):
                factura = _factura_pendiente(emisor_id=emisor)
                conexion = self._preparar(factura, factura)
                self.assertNotIn(_MOTIVO_PROYECCION, database.inspeccionar_estado_base_sqlite(conexion).motivos)

    def test_componentes_guardados_cero_o_negativos_no_participan_ni_se_corrigen(self):
        for columna in _COLUMNAS_NORMALIZADAS:
            for valor in (0, -1):
                with self.subTest(columna=columna, valor=valor):
                    factura = _factura_normalizada(**{columna: valor})
                    conexion = self._preparar(factura, factura)
                    resultado = database.inspeccionar_estado_base_sqlite(conexion)
                    self.assertEqual(resultado.estado, "HISTORICA_SIN_VERSION")
                    self.assertNotIn(_MOTIVO_PROYECCION, resultado.motivos)

    def test_seleccion_respeta_trim_sqlite_y_no_strip_python(self):
        for numero, seleccionada in (("", False), ("   ", False), (None, False), ("\t", True)):
            with self.subTest(numero=repr(numero)):
                conexion = self._preparar(
                    _factura_normalizada(numero_factura=numero, numero_comprobante_num=None)
                )
                with patch.object(
                    database, "normalizar_identidad_factura", wraps=normalizar_identidad_factura
                ) as normalizador:
                    resultado = database.inspeccionar_estado_base_sqlite(conexion)
                self.assertEqual(normalizador.call_count, int(seleccionada))
                self.assertNotIn(_MOTIVO_PROYECCION, resultado.motivos)
                self.assertNotEqual(resultado.estado, "BLOQUEADA")

    def test_digitos_unicode_equivalentes_colisionan(self):
        conexion = self._preparar(
            _factura_pendiente(), _factura_pendiente(punto_venta="\u0662", numero_factura="\u0662-\u0661")
        )
        self._comprobar_colision(conexion)

    def test_error_de_normalizacion_bloquea_sin_omitir_fila(self):
        conexion = self._preparar(_factura_pendiente(punto_venta="\u00b2"))
        resultado = database.inspeccionar_estado_base_sqlite(conexion)
        self.assertEqual(resultado.estado, "BLOQUEADA")
        self.assertIn("No se pudo inspeccionar la conexión SQLite de forma confiable (ValueError).", resultado.motivos)

    def test_no_deja_de_inspeccionar_al_encontrar_colision(self):
        conexion = self._preparar(
            _factura_pendiente(), _factura_pendiente(), _factura_pendiente(punto_venta="\u00b2")
        )
        resultado = database.inspeccionar_estado_base_sqlite(conexion)
        self.assertEqual(resultado.estado, "BLOQUEADA")
        self.assertTrue(any("ValueError" in motivo for motivo in resultado.motivos))

    def test_acumula_cae_triggers_y_problemas_estructurales(self):
        conexion = self._preparar(
            _factura_pendiente(cae="111"), _factura_pendiente(cae=" 111 "),
            omitir_tablas=("cobros",),
            omitir_indices=_INDICES_FACTURA,
            reemplazar_tablas={
                "clientes": f"CREATE TABLE clientes ({', '.join(['id INTEGER', *_TABLAS_BASE['clientes'][1:]])})"
            },
        )
        conexion.execute("CREATE TRIGGER trg_proyeccion AFTER INSERT ON factura_arca BEGIN SELECT 1; END")
        resultado = self._comprobar_colision(conexion)
        for motivo in (
            "duplicados:factura_arca.cae",
            "trigger_no_reconocido:trg_proyeccion(factura_arca)",
            "clave_primaria_incompatible:clientes",
            "tabla_esencial_ausente:cobros; no se recreará automáticamente",
        ):
            self.assertIn(motivo, resultado.motivos)

    def test_conserva_control_de_duplicados_ya_normalizados(self):
        conexion = self._preparar(
            _factura_normalizada(), _factura_normalizada(), omitir_indices=_INDICES_FACTURA
        )
        resultado = self._comprobar_colision(conexion)
        self.assertIn("duplicados:factura_arca.identidad_fiscal", resultado.motivos)

    def test_version_incompatible_prevalece_y_conserva_colision(self):
        for sentencia in ("PRAGMA user_version=9", "CREATE TABLE schema_migrations(version TEXT)"):
            with self.subTest(sentencia=sentencia):
                conexion = self._preparar(_factura_pendiente(), _factura_pendiente(numero_factura="2-1"))
                conexion.execute(sentencia)
                resultado = database.inspeccionar_estado_base_sqlite(conexion)
                self.assertEqual(resultado.estado, "VERSION_INCOMPATIBLE")
                self.assertIn(_MOTIVO_PROYECCION, resultado.motivos)

    def test_inspeccion_solo_lectura_no_ejecuta_trigger_ni_backfill(self):
        conexion = self._preparar(_factura_pendiente(), _factura_pendiente(numero_factura="2-1"))
        conexion.execute(
            "CREATE TRIGGER trg_no_actualizar BEFORE UPDATE ON factura_arca "
            "BEGIN SELECT RAISE(ABORT, 'No actualizar'); END"
        )
        conexion.commit()
        antes = tuple(conexion.iterdump())
        cambios = conexion.total_changes
        consultas = []
        conexion.set_trace_callback(consultas.append)
        try:
            self._comprobar_colision(conexion)
        finally:
            conexion.set_trace_callback(None)
        self.assertEqual(tuple(conexion.iterdump()), antes)
        self.assertEqual(conexion.total_changes, cambios)
        self.assertFalse(conexion.in_transaction)
        self.assertEqual(
            conexion.execute(
                "SELECT punto_venta_num, tipo_comprobante_num, numero_comprobante_num FROM factura_arca"
            ).fetchall(),
            [(None, None, None), (None, None, None)],
        )
        self.assertTrue(consultas)
        self.assertTrue(all(consulta.lstrip().upper().startswith(("SELECT", "PRAGMA")) for consulta in consultas))

    def test_equivalencia_con_indices_creados_manualmente_sin_migrar(self):
        # Los resultados esperados se escriben a mano; no se obtienen del detector.
        for ambiente in ("HOMOLOGACION", "PRODUCCION", None):
            for cambios, normalizada, colision in (
                ({"punto_venta": "2", "tipo_comprobante": "11", "numero_factura": "2-1"}, (2, 11, 1), True),
                ({"tipo_comprobante": "Factura A"}, (2, 1, 1), False),
                ({"punto_venta": "3", "numero_factura": "3-1"}, (3, 11, 1), False),
                ({"numero_factura": "2-2"}, (2, 11, 2), False),
            ):
                with self.subTest(ambiente=ambiente, cambios=cambios):
                    primera = _factura_normalizada(ambiente_arca=ambiente)
                    pendiente = _factura_pendiente(ambiente_arca=ambiente, **cambios)
                    conexion = self._preparar(primera, pendiente)
                    resultado = database.inspeccionar_estado_base_sqlite(conexion)
                    self.assertEqual(_MOTIVO_PROYECCION in resultado.motivos, colision)
                    self.assertEqual(
                        normalizar_identidad_factura(
                            pendiente["punto_venta"], pendiente["tipo_comprobante"], pendiente["numero_factura"]
                        ),
                        normalizada,
                    )
                    equivalente = self._preparar(primera)
                    candidata = dict(pendiente, **dict(zip(_COLUMNAS_NORMALIZADAS, normalizada)))
                    if colision:
                        with self.assertRaises(sqlite3.IntegrityError):
                            _insertar_factura(equivalente, **candidata)
                    else:
                        _insertar_factura(equivalente, **candidata)


_MOTIVO_CONTRADICCION = "contradiccion:factura_arca.identidad_fiscal"


class IdentidadFiscalContradictoriaTest(_PoliticaBase):

    def _preparar(self, *facturas, **esquema):
        conexion = sqlite3.connect(":memory:")
        self.addCleanup(conexion.close)
        _crear_esquema_historico(conexion, **esquema)
        omitidas = esquema.get("omitir_columnas_factura", ())
        for factura in facturas:
            _insertar_factura(conexion, **{k: v for k, v in factura.items() if k not in omitidas})
        return conexion

    def _comprobar_contradiccion(self, conexion):
        resultado = database.inspeccionar_estado_base_sqlite(conexion)
        self.assertEqual(resultado.estado, "BLOQUEADA")
        self.assertEqual(resultado.motivos.count(_MOTIVO_CONTRADICCION), 1)
        return resultado

    def test_cada_comparacion_detecta_contradiccion(self):
        for cambios in (
            {"punto_venta": "3", "numero_factura": None},
            {"punto_venta": None, "numero_factura": "3-1"},
            {"numero_factura": "2-5"},
            {"tipo_comprobante": "Factura A"},
        ):
            with self.subTest(cambios=cambios):
                conexion = self._preparar(_factura_normalizada(**cambios))
                self._comprobar_contradiccion(conexion)

    def test_textos_internamente_incoherentes_no_ocultan_comparaciones(self):
        conexion = self._preparar(_factura_normalizada(numero_factura="3-1"))
        self._comprobar_contradiccion(conexion)

    def test_varias_contradicciones_generan_un_solo_motivo(self):
        conexion = self._preparar(
            _factura_normalizada(punto_venta="3", tipo_comprobante="Factura A", numero_factura="3-5"),
            _factura_normalizada(numero_comprobante_num=2),
        )
        self._comprobar_contradiccion(conexion)

    def test_compara_valores_originales_de_filas_parciales(self):
        for columna, guardado in zip(_COLUMNAS_NORMALIZADAS, (3, 1, 5)):
            with self.subTest(columna=columna):
                conexion = self._preparar(_factura_pendiente(**{columna: guardado}))
                self._comprobar_contradiccion(conexion)
                self.assertEqual(
                    conexion.execute(f"SELECT {columna} FROM factura_arca").fetchone()[0], guardado
                )

    def test_equivalencias_legitimas_no_bloquean(self):
        for punto, tipo, numero, tipo_num in (
            ("2", "11", "2-1", 11),
            (" 0002 ", " factura c ", " 0002-001 ", 11),
            ("\t2\n", "\tFACTURA C\n", "\t2-1\n", 11),
            ("\u00a02\u00a0", "11", "\u00a02-1\u00a0", 11),
            ("\u0662", "Factura C", "\u0662-\u0661", 11),
            (2, "Factura A", "2-1", 1),
            ("00002", " 1 ", "00002-00000001", 1),
        ):
            with self.subTest(punto=punto, tipo=tipo, numero=numero):
                conexion = self._preparar(_factura_normalizada(
                    punto_venta=punto, tipo_comprobante=tipo, numero_factura=numero,
                    tipo_comprobante_num=tipo_num,
                ))
                resultado = database.inspeccionar_estado_base_sqlite(conexion)
                self.assertEqual(resultado.estado, "HISTORICA_SIN_VERSION")
                self.assertNotIn(_MOTIVO_CONTRADICCION, resultado.motivos)

    def test_textos_ambiguos_completos_conservan_clasificacion(self):
        casos = [
            {"punto_venta": valor} for valor in (None, "", "0", "-2", "+2", "2.0", 2.0, "\u00b2", "\u2460")
        ] + [
            {"tipo_comprobante": valor} for valor in (None, "", "Factura B", "6", "011", "C", "FACTURA  C")
        ] + [
            {"numero_factura": valor} for valor in (None, "", "   ", "000002-1", "2 - 1", "2-0", "\u00b2-1")
        ]
        for cambios in casos:
            with self.subTest(cambios=cambios):
                conexion = self._preparar(_factura_normalizada(**cambios))
                resultado = database.inspeccionar_estado_base_sqlite(conexion)
                self.assertEqual(resultado.estado, "HISTORICA_SIN_VERSION")
                self.assertNotIn(_MOTIVO_CONTRADICCION, resultado.motivos)

    def test_error_ambiguo_no_oculta_otro_campo_ni_otra_fila(self):
        for facturas in (
            (_factura_normalizada(punto_venta="\u00b2", tipo_comprobante="Factura A"),),
            (
                _factura_normalizada(punto_venta="\u00b2"),
                _factura_normalizada(numero_comprobante_num=2),
            ),
        ):
            with self.subTest(facturas=facturas):
                resultado = self._comprobar_contradiccion(self._preparar(*facturas))
                self.assertFalse(any("No se pudo inspeccionar" in motivo for motivo in resultado.motivos))

    def test_error_en_fila_pendiente_sigue_bloqueando_por_sexta_proteccion(self):
        conexion = self._preparar(_factura_pendiente(punto_venta="\u00b2"))
        resultado = database.inspeccionar_estado_base_sqlite(conexion)
        self.assertEqual(resultado.estado, "BLOQUEADA")
        self.assertNotIn(_MOTIVO_CONTRADICCION, resultado.motivos)
        self.assertTrue(any("ValueError" in motivo for motivo in resultado.motivos))

    def test_no_captura_otros_errores_del_normalizador(self):
        conexion = self._preparar(_factura_normalizada())
        with patch.object(database, "normalizar_punto_venta", side_effect=TypeError("Error inesperado")):
            resultado = database.inspeccionar_estado_base_sqlite(conexion)
        self.assertEqual(resultado.estado, "BLOQUEADA")
        self.assertTrue(any("TypeError" in motivo for motivo in resultado.motivos))
        self.assertNotIn(_MOTIVO_CONTRADICCION, resultado.motivos)

    def test_guardados_no_enteros_positivos_no_se_comparan(self):
        for columna in _COLUMNAS_NORMALIZADAS:
            for valor in (None, 0, -1, 2.5, "abc"):
                with self.subTest(columna=columna, valor=valor):
                    conexion = self._preparar(_factura_normalizada(**{columna: valor}))
                    resultado = database.inspeccionar_estado_base_sqlite(conexion)
                    self.assertNotEqual(resultado.estado, "BLOQUEADA")
                    self.assertNotIn(_MOTIVO_CONTRADICCION, resultado.motivos)

    def test_bool_devuelto_por_conexion_no_se_compara_como_entero(self):
        conexion = self._preparar(_factura_normalizada())
        columnas = (
            "punto_venta", "tipo_comprobante", "numero_factura",
            "punto_venta_num", "tipo_comprobante_num", "numero_comprobante_num",
        )

        def fila_con_bool(cursor, fila):
            # SQLite almacena bool como INTEGER; simula una conexión que devuelve bool.
            if tuple(columna[0] for columna in cursor.description) == columnas:
                return (*fila[:3], True, True, True)
            return fila

        conexion.row_factory = fila_con_bool
        resultado = database.inspeccionar_estado_base_sqlite(conexion)
        self.assertEqual(resultado.estado, "HISTORICA_SIN_VERSION")
        self.assertNotIn(_MOTIVO_CONTRADICCION, resultado.motivos)

    def test_textos_ausentes_no_impiden_comparar_los_presentes(self):
        for omitidas, cambios in (
            (("punto_venta", "tipo_comprobante"), {"numero_factura": "3-1"}),
            (("punto_venta", "numero_factura"), {"tipo_comprobante": "Factura A"}),
            (("tipo_comprobante", "numero_factura"), {"punto_venta": "3"}),
        ):
            with self.subTest(omitidas=omitidas):
                conexion = self._preparar(
                    _factura_normalizada(**cambios), omitir_columnas_factura=omitidas
                )
                self._comprobar_contradiccion(conexion)

    def test_sin_columnas_normalizadas_o_textos_no_inventa_contradiccion(self):
        for omitidas in (
            _COLUMNAS_NORMALIZADAS,
            ("punto_venta", "tipo_comprobante", "numero_factura"),
        ):
            with self.subTest(omitidas=omitidas):
                conexion = self._preparar(
                    _factura_normalizada(), omitir_columnas_factura=omitidas,
                    omitir_indices=_INDICES_FACTURA,
                )
                resultado = database.inspeccionar_estado_base_sqlite(conexion)
                self.assertEqual(resultado.estado, "INCOMPLETA")
                self.assertNotIn(_MOTIVO_CONTRADICCION, resultado.motivos)

    def test_compara_dentro_de_fila_sin_depender_de_ambiente_o_emisor(self):
        for ambiente, emisor in (("HOMOLOGACION", 1), ("PRODUCCION", 2), (None, 3)):
            with self.subTest(ambiente=ambiente, emisor=emisor):
                conexion = self._preparar(_factura_normalizada(
                    ambiente_arca=ambiente, emisor_id=emisor, tipo_comprobante="Factura A"
                ))
                self._comprobar_contradiccion(conexion)

    def test_acumula_motivos_de_protecciones_anteriores(self):
        conexion = self._preparar(
            _factura_normalizada(tipo_comprobante="Factura A", cae="111"),
            _factura_normalizada(cae=" 111 "),
            _factura_pendiente(numero_factura="2-1", cae="222"),
            omitir_tablas=("cobros",), omitir_indices=_INDICES_FACTURA,
            reemplazar_tablas={
                "clientes": f"CREATE TABLE clientes ({', '.join(['id INTEGER', *_TABLAS_BASE['clientes'][1:]])})"
            },
        )
        conexion.execute("CREATE TRIGGER trg_contradiccion AFTER INSERT ON factura_arca BEGIN SELECT 1; END")
        resultado = self._comprobar_contradiccion(conexion)
        for motivo in (
            "duplicados:factura_arca.identidad_fiscal",
            _MOTIVO_PROYECCION,
            "duplicados:factura_arca.cae",
            "trigger_no_reconocido:trg_contradiccion(factura_arca)",
            "clave_primaria_incompatible:clientes",
            "tabla_esencial_ausente:cobros; no se recreará automáticamente",
        ):
            self.assertIn(motivo, resultado.motivos)

    def test_version_incompatible_prevalece_y_conserva_motivos(self):
        for sentencia in ("PRAGMA user_version=9", "CREATE TABLE schema_migrations(version TEXT)"):
            with self.subTest(sentencia=sentencia):
                conexion = self._preparar(
                    _factura_normalizada(tipo_comprobante="Factura A", cae="111"),
                    _factura_normalizada(cae=" 111 "),
                    omitir_indices=_INDICES_FACTURA,
                )
                conexion.execute("CREATE TRIGGER trg_version AFTER INSERT ON factura_arca BEGIN SELECT 1; END")
                conexion.execute(sentencia)
                resultado = database.inspeccionar_estado_base_sqlite(conexion)
                self.assertEqual(resultado.estado, "VERSION_INCOMPATIBLE")
                for motivo in (_MOTIVO_CONTRADICCION, _MOTIVO_PROYECCION, "duplicados:factura_arca.cae",
                               "trigger_no_reconocido:trg_version(factura_arca)"):
                    self.assertIn(motivo, resultado.motivos)

    def test_inspeccion_no_escribe_ni_ejecuta_trigger(self):
        conexion = self._preparar(_factura_normalizada(tipo_comprobante="Factura A"))
        conexion.execute(
            "CREATE TRIGGER trg_no_corregir BEFORE UPDATE ON factura_arca "
            "BEGIN SELECT RAISE(ABORT, 'No corregir'); END"
        )
        conexion.commit()
        antes = tuple(conexion.iterdump())
        cambios = conexion.total_changes
        consultas = []
        conexion.set_trace_callback(consultas.append)
        try:
            self._comprobar_contradiccion(conexion)
        finally:
            conexion.set_trace_callback(None)
        self.assertEqual(tuple(conexion.iterdump()), antes)
        self.assertEqual(conexion.total_changes, cambios)
        self.assertFalse(conexion.in_transaction)
        self.assertTrue(consultas)
        self.assertTrue(all(consulta.lstrip().upper().startswith(("SELECT", "PRAGMA")) for consulta in consultas))


_INDICES_CAE = ("idx_factura_arca_cae_unico", "idx_factura_arca_cae_historico_unico")
_MOTIVO_CAE = "duplicados:factura_arca.cae"
_CAE = "12345678901234"


def _factura_cae(numero, cae, **extra):
    """Factura con identidad fiscal propia (número distinto) y el CAE indicado."""
    return _factura_normalizada(
        numero_factura=f"00002-{numero:08d}", numero_comprobante_num=numero, cae=cae, **extra
    )


class CaeDuplicadosTest(_PoliticaBase):

    def _insertar(self, *facturas, conexion=None):
        for factura in facturas:
            _insertar_factura(conexion or self.conexion, **factura)

    def test_cae_identico_en_facturas_distintas_bloquea(self):
        _crear_esquema_historico(self.conexion, omitir_indices=_INDICES_CAE)
        self._insertar(_factura_cae(1, _CAE), _factura_cae(2, _CAE))

        resultado = self.inspeccionar()

        self.assertEqual(resultado.estado, "BLOQUEADA")
        self.assertIn(_MOTIVO_CAE, resultado.motivos)
        self.assertNotIn("duplicados:factura_arca.identidad_fiscal", resultado.motivos)

    def test_cae_iguales_tras_trim_de_espacios_ordinarios_bloquea(self):
        for variante in (f"  {_CAE}", f"{_CAE}   ", f" {_CAE} "):
            with self.subTest(variante=repr(variante)):
                conexion = sqlite3.connect(":memory:")
                try:
                    _crear_esquema_historico(conexion, omitir_indices=_INDICES_CAE)
                    self._insertar(_factura_cae(1, _CAE), _factura_cae(2, variante), conexion=conexion)

                    resultado = database.inspeccionar_estado_base_sqlite(conexion)

                    self.assertEqual(resultado.estado, "BLOQUEADA")
                    self.assertIn(_MOTIVO_CAE, resultado.motivos)
                finally:
                    conexion.close()

    def test_cae_duplicado_con_ambiente_nulo_bloquea(self):
        _crear_esquema_historico(self.conexion, omitir_indices=_INDICES_CAE)
        self._insertar(
            _factura_cae(1, _CAE, ambiente_arca=None), _factura_cae(2, f" {_CAE}", ambiente_arca=None)
        )

        resultado = self.inspeccionar()

        self.assertEqual(resultado.estado, "BLOQUEADA")
        self.assertIn(_MOTIVO_CAE, resultado.motivos)

    def test_cae_duplicado_sin_columna_ambiente_se_trata_como_grupo_historico(self):
        _crear_esquema_historico(
            self.conexion, omitir_columnas_factura=("ambiente_arca",), omitir_indices=_INDICES_FACTURA
        )
        for factura in (_factura_cae(1, _CAE), _factura_cae(2, f"{_CAE} ")):
            factura.pop("ambiente_arca")
            _insertar_factura(self.conexion, **factura)

        resultado = self.inspeccionar()

        self.assertEqual(resultado.estado, "BLOQUEADA")
        self.assertIn(_MOTIVO_CAE, resultado.motivos)
        self.assertIn("columna:factura_arca.ambiente_arca", resultado.estructuras_pendientes)

    def test_mismo_cae_en_homologacion_y_produccion_no_bloquea(self):
        _crear_esquema_historico(self.conexion)
        self._insertar(
            _factura_cae(1, _CAE, ambiente_arca="HOMOLOGACION"),
            _factura_cae(2, _CAE, ambiente_arca="PRODUCCION"),
        )

        resultado = self.inspeccionar()

        self.assertEqual(resultado.estado, "HISTORICA_SIN_VERSION")
        self.assertNotIn(_MOTIVO_CAE, resultado.motivos)

    def test_mismo_cae_en_ambiente_conocido_y_desconocido_no_mezcla_grupos(self):
        _crear_esquema_historico(self.conexion)
        self._insertar(
            _factura_cae(1, _CAE, ambiente_arca="HOMOLOGACION"),
            _factura_cae(2, _CAE, ambiente_arca=None),
        )

        resultado = self.inspeccionar()

        self.assertEqual(resultado.estado, "HISTORICA_SIN_VERSION")
        self.assertNotIn(_MOTIVO_CAE, resultado.motivos)
        self.assertTrue(
            any(a.startswith("factura_arca.ambiente_historico_desconocido:1") for a in resultado.advertencias)
        )

    def test_mismo_cae_entre_emisores_distintos_del_mismo_ambiente_bloquea(self):
        _crear_esquema_historico(self.conexion, omitir_indices=_INDICES_CAE)
        self._insertar(_factura_cae(1, _CAE, emisor_id=1), _factura_cae(1, _CAE, emisor_id=2))

        resultado = self.inspeccionar()

        self.assertEqual(resultado.estado, "BLOQUEADA")
        self.assertIn(_MOTIVO_CAE, resultado.motivos)
        self.assertNotIn("duplicados:factura_arca.identidad_fiscal", resultado.motivos)

    def test_cae_nulos_vacios_o_solo_espacios_no_son_duplicados(self):
        _crear_esquema_historico(self.conexion)
        valores = (None, None, "", "", " ", "    ")
        self._insertar(*(_factura_cae(numero, cae) for numero, cae in enumerate(valores, start=1)))
        self._insertar(*(
            _factura_cae(numero, cae, ambiente_arca=None) for numero, cae in enumerate(valores, start=11)
        ))

        resultado = self.inspeccionar()

        self.assertEqual(resultado.estado, "HISTORICA_SIN_VERSION")
        self.assertNotIn(_MOTIVO_CAE, resultado.motivos)

    def test_ceros_iniciales_se_conservan_en_columna_text(self):
        _crear_esquema_historico(self.conexion)
        self._insertar(_factura_cae(1, "01234567890123"), _factura_cae(2, "1234567890123"))

        resultado = self.inspeccionar()

        self.assertEqual(resultado.estado, "HISTORICA_SIN_VERSION")
        self.assertNotIn(_MOTIVO_CAE, resultado.motivos)

    def test_cae_numerico_y_textual_iguales_se_detectan_como_duplicados(self):
        tipos = {"TEXT": "text", "sin_tipo": "integer"}
        for tipo, tipo_almacenado in tipos.items():
            with self.subTest(tipo=tipo):
                conexion = sqlite3.connect(":memory:")
                try:
                    definicion = "cae TEXT" if tipo == "TEXT" else "cae"
                    columnas = [
                        definicion if nombre == "cae" else f"{nombre} {tipo_sql}"
                        for nombre, tipo_sql in _COLUMNAS_FACTURA_ARCA
                    ]
                    _crear_esquema_historico(
                        conexion,
                        omitir_indices=_INDICES_CAE,
                        reemplazar_tablas={"factura_arca": f"CREATE TABLE factura_arca ({', '.join(columnas)})"},
                    )
                    self._insertar(
                        _factura_cae(1, int(_CAE)), _factura_cae(2, f" {_CAE} "), conexion=conexion
                    )
                    self.assertEqual(
                        conexion.execute("SELECT typeof(cae) FROM factura_arca WHERE id=1").fetchone()[0],
                        tipo_almacenado,
                    )

                    resultado = database.inspeccionar_estado_base_sqlite(conexion)

                    self.assertEqual(resultado.estado, "BLOQUEADA")
                    self.assertIn(_MOTIVO_CAE, resultado.motivos)
                finally:
                    conexion.close()

    def test_afinidad_numerica_pierde_ceros_iniciales_antes_de_la_inspeccion(self):
        # Limitación documentada: con afinidad NUMERIC SQLite guarda '0123...' como
        # entero y el detector ya no puede distinguirlo del CAE sin ceros.
        columnas = [
            "cae NUMERIC" if nombre == "cae" else f"{nombre} {tipo_sql}"
            for nombre, tipo_sql in _COLUMNAS_FACTURA_ARCA
        ]
        _crear_esquema_historico(
            self.conexion,
            omitir_indices=_INDICES_CAE,
            reemplazar_tablas={"factura_arca": f"CREATE TABLE factura_arca ({', '.join(columnas)})"},
        )
        self._insertar(_factura_cae(1, "01234567890123"), _factura_cae(2, "1234567890123"))

        self.assertIn(_MOTIVO_CAE, self.inspeccionar().motivos)

    def test_trim_de_sqlite_no_equivale_a_strip_de_python(self):
        # TRIM(x) de SQLite solo quita espacios ordinarios; str.strip() también quita
        # tabulaciones, saltos de línea y espacios Unicode. El detector reproduce el
        # contrato de los índices (TRIM), por lo que estas variantes no se detectan.
        for variante in (f"\t{_CAE}", f"{_CAE}\n", f"{_CAE}\r\n", f"\u00a0{_CAE}", f"{_CAE}\u2003"):
            with self.subTest(variante=repr(variante)):
                self.assertEqual(variante.strip(), _CAE)
                conexion = sqlite3.connect(":memory:")
                try:
                    _crear_esquema_historico(conexion)
                    self._insertar(_factura_cae(1, _CAE), _factura_cae(2, variante), conexion=conexion)
                    self.assertEqual(
                        conexion.execute("SELECT COUNT(DISTINCT TRIM(cae)) FROM factura_arca").fetchone()[0], 2
                    )

                    resultado = database.inspeccionar_estado_base_sqlite(conexion)

                    self.assertNotIn(_MOTIVO_CAE, resultado.motivos)
                    self.assertEqual(resultado.estado, "HISTORICA_SIN_VERSION")
                finally:
                    conexion.close()

    def test_deteccion_sin_ningun_indice_unico_de_factura(self):
        _crear_esquema_historico(self.conexion, omitir_indices=_INDICES_FACTURA)
        self._insertar(_factura_cae(1, _CAE), _factura_cae(2, f" {_CAE}"))

        resultado = self.inspeccionar()

        self.assertEqual(resultado.estado, "BLOQUEADA")
        self.assertIn(_MOTIVO_CAE, resultado.motivos)
        for nombre in _INDICES_FACTURA:
            self.assertIn(f"indice:{nombre}", resultado.estructuras_pendientes)

    def test_deteccion_sin_columnas_de_identidad_normalizada(self):
        normalizadas = ("punto_venta_num", "tipo_comprobante_num", "numero_comprobante_num")
        _crear_esquema_historico(
            self.conexion,
            omitir_columnas_factura=normalizadas,
            omitir_indices=("idx_factura_arca_identidad_unica", "idx_factura_arca_identidad_historica_unica")
            + _INDICES_CAE,
        )
        for factura in (_factura_cae(1, _CAE), _factura_cae(2, f"{_CAE} ")):
            for columna in normalizadas:
                factura.pop(columna)
            _insertar_factura(self.conexion, **factura)

        resultado = self.inspeccionar()

        self.assertEqual(resultado.estado, "BLOQUEADA")
        self.assertIn(_MOTIVO_CAE, resultado.motivos)

    def test_cae_duplicado_acumula_motivos_con_otros_problemas(self):
        _crear_esquema_historico(
            self.conexion,
            omitir_tablas=("cobros",),
            omitir_indices=_INDICES_CAE + ("idx_factura_arca_identidad_unica",),
            reemplazar_tablas={
                "clientes": f"CREATE TABLE clientes ({', '.join(['id INTEGER', *_TABLAS_BASE['clientes'][1:]])})"
            },
        )
        self._insertar(_factura_cae(1, _CAE), _factura_cae(1, f" {_CAE}"))
        self.conexion.execute("CREATE TRIGGER trg_cae AFTER INSERT ON factura_arca BEGIN SELECT 1; END")

        resultado = self.inspeccionar()

        self.assertEqual(resultado.estado, "BLOQUEADA")
        for motivo in (
            "tabla_esencial_ausente:cobros; no se recreará automáticamente",
            "clave_primaria_incompatible:clientes",
            "trigger_no_reconocido:trg_cae(factura_arca)",
            "duplicados:factura_arca.identidad_fiscal",
            _MOTIVO_CAE,
        ):
            self.assertIn(motivo, resultado.motivos)

    def test_version_incompatible_prevalece_y_conserva_motivo_cae(self):
        for caso, sentencia in (
            ("user_version", "PRAGMA user_version = 5"),
            ("marcador", "CREATE TABLE schema_migrations (version TEXT)"),
        ):
            with self.subTest(caso=caso):
                conexion = sqlite3.connect(":memory:")
                try:
                    _crear_esquema_historico(conexion, omitir_indices=_INDICES_CAE)
                    self._insertar(_factura_cae(1, _CAE), _factura_cae(2, _CAE), conexion=conexion)
                    conexion.execute(sentencia)

                    resultado = database.inspeccionar_estado_base_sqlite(conexion)

                    self.assertEqual(resultado.estado, "VERSION_INCOMPATIBLE")
                    self.assertIn(_MOTIVO_CAE, resultado.motivos)
                finally:
                    conexion.close()

    def test_inspeccion_no_modifica_datos_ni_esquema(self):
        _crear_esquema_historico(self.conexion, omitir_indices=_INDICES_CAE)
        self._insertar(_factura_cae(1, f" {_CAE} "), _factura_cae(2, _CAE), _factura_cae(3, None))
        self.conexion.commit()
        antes = tuple(self.conexion.iterdump())
        cambios = self.conexion.total_changes
        consultas = []
        self.conexion.set_trace_callback(consultas.append)
        try:
            resultado = self.inspeccionar()
        finally:
            self.conexion.set_trace_callback(None)

        self.assertEqual(resultado.estado, "BLOQUEADA")
        self.assertEqual(tuple(self.conexion.iterdump()), antes)
        self.assertEqual(self.conexion.total_changes, cambios)
        self.assertFalse(self.conexion.in_transaction)
        self.assertEqual(
            [fila[0] for fila in self.conexion.execute("SELECT cae FROM factura_arca ORDER BY id")],
            [f" {_CAE} ", _CAE, None],
        )
        self.assertTrue(consultas)
        self.assertTrue(all(consulta.lstrip().upper().startswith(("SELECT", "PRAGMA")) for consulta in consultas))


class IndiceUnicoCaeEquivalenteTest(_PoliticaBase):
    """Índices de CAE creados a mano en memoria (SQL de _INDICES_UNICOS), sin migraciones."""

    def setUp(self):
        super().setUp()
        _crear_esquema_historico(self.conexion)
        _insertar_factura(self.conexion, **_factura_cae(1, _CAE))
        _insertar_factura(self.conexion, **_factura_cae(2, _CAE, ambiente_arca=None))

    def test_indice_rechaza_lo_que_el_detector_bloquea(self):
        for numero, ambiente, cae in (
            (3, "HOMOLOGACION", f" {_CAE} "),
            (4, "HOMOLOGACION", int(_CAE)),
            (5, None, f"{_CAE}  "),
        ):
            with self.subTest(ambiente=ambiente, cae=repr(cae)):
                with self.assertRaises(sqlite3.IntegrityError):
                    _insertar_factura(self.conexion, **_factura_cae(numero, cae, ambiente_arca=ambiente))

    def test_indice_acepta_lo_que_el_detector_no_bloquea(self):
        for numero, ambiente, cae in (
            (3, "PRODUCCION", _CAE),
            (4, "HOMOLOGACION", f"\t{_CAE}"),
            (5, "HOMOLOGACION", f"\u00a0{_CAE}"),
            (6, "HOMOLOGACION", None),
            (7, "HOMOLOGACION", None),
            (8, "HOMOLOGACION", "   "),
            (9, None, ""),
        ):
            _insertar_factura(self.conexion, **_factura_cae(numero, cae, ambiente_arca=ambiente))

        resultado = self.inspeccionar()

        self.assertNotIn(_MOTIVO_CAE, resultado.motivos)
        self.assertEqual(resultado.estado, "HISTORICA_SIN_VERSION")


class IndicesDesconocidosTest(_PoliticaBase):

    def test_indice_con_mismo_nombre_y_otra_definicion_no_es_historico(self):
        _crear_esquema_historico(
            self.conexion,
            reemplazar_indices={
                "idx_factura_arca_cae_unico": "CREATE UNIQUE INDEX idx_factura_arca_cae_unico ON factura_arca(cae)"
            },
        )

        resultado = self.inspeccionar()

        self.assertNotEqual(resultado.estado, "HISTORICA_SIN_VERSION")
        self.assertIn("indice_incompatible:idx_factura_arca_cae_unico", resultado.estructuras_pendientes)

    def test_indice_con_mismo_nombre_sobre_otra_tabla_no_es_historico(self):
        _crear_esquema_historico(
            self.conexion,
            reemplazar_indices={
                "idx_factura_arca_cae_unico": "CREATE UNIQUE INDEX idx_factura_arca_cae_unico ON resumenes(cae)"
            },
        )

        self.assertIn(
            "indice_incompatible:idx_factura_arca_cae_unico", self.inspeccionar().estructuras_pendientes
        )

    @unittest.expectedFailure
    def test_requisito_futuro_indice_de_definicion_desconocida_debe_bloquear(self):
        # Hoy se clasifica como INCOMPLETA y _migrar_indice_factura_arca eliminaría
        # el índice ajeno para recrearlo. Una definición desconocida debe bloquear.
        _crear_esquema_historico(
            self.conexion,
            reemplazar_indices={
                "idx_factura_arca_cae_unico": "CREATE UNIQUE INDEX idx_factura_arca_cae_unico ON factura_arca(cae)"
            },
        )

        self.assertIn(self.inspeccionar().estado, BLOQUEANTES)


class EstructurasContradictoriasTest(_PoliticaBase):

    def test_requisito_futuro_identidad_textual_contradice_normalizada_debe_bloquear(self):
        # La migración no recalcula esta fila completa: el punto de venta textual
        # 3 contradice el 2 guardado y requiere revisión, no una corrección automática.
        _crear_esquema_historico(self.conexion)
        _insertar_factura(
            self.conexion,
            **_factura_normalizada(
                punto_venta="00003", numero_factura="00003-00000010", numero_comprobante_num=10, cae="111"
            ),
        )

        resultado = self.inspeccionar()
        self.assertEqual(resultado.estado, "BLOQUEADA")
        self.assertIn("contradiccion:factura_arca.identidad_fiscal", resultado.motivos)

    @unittest.expectedFailure
    def test_requisito_futuro_columnas_modernas_sin_identidad_normalizada_debe_bloquear(self):
        # factura_arca tiene ambiente, snapshot y rutas PDF (etapas posteriores)
        # pero carece de las columnas normalizadas que esas etapas presuponen.
        # Ninguna base histórica legítima tiene esa combinación; hoy es INCOMPLETA.
        _crear_esquema_historico(
            self.conexion,
            omitir_columnas_factura=("punto_venta_num", "tipo_comprobante_num", "numero_comprobante_num"),
            omitir_indices=("idx_factura_arca_identidad_unica", "idx_factura_arca_identidad_historica_unica"),
        )

        self.assertIn(self.inspeccionar().estado, BLOQUEANTES)

    def test_conexion_inutilizable_bloquea(self):
        conexion = sqlite3.connect(":memory:")
        conexion.close()

        resultado = database.inspeccionar_estado_base_sqlite(conexion)

        self.assertEqual(resultado.estado, "BLOQUEADA")
        self.assertTrue(any("ProgrammingError" in motivo for motivo in resultado.motivos))


if __name__ == "__main__":
    unittest.main()
