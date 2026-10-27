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
    cursor = conexion.cursor()
    for tabla, columnas in _TABLAS_BASE.items():
        if tabla in omitir_tablas:
            continue
        if tabla in reemplazar_tablas:
            cursor.execute(reemplazar_tablas[tabla])
            continue
        cursor.execute(f"CREATE TABLE {tabla} ({', '.join(columnas)})")

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

    @unittest.expectedFailure
    def test_requisito_futuro_trigger_desconocido_debe_bloquear(self):
        # El detector solo usa los triggers para saber si la base está vacía; un
        # trigger ajeno puede alterar datos durante una migración y debe bloquear.
        _crear_esquema_historico(self.conexion)
        self.conexion.execute(
            "CREATE TRIGGER trg_desconocido AFTER INSERT ON factura_arca "
            "BEGIN UPDATE factura_arca SET cae = NULL WHERE id = NEW.id; END"
        )

        self.assertIn(self.inspeccionar().estado, BLOQUEANTES)

    @unittest.expectedFailure
    def test_requisito_futuro_tabla_esencial_sin_clave_primaria_debe_bloquear(self):
        # PRAGMA table_info solo se usa para nombres de columnas; una tabla esencial
        # con id TEXT sin PRIMARY KEY no es una estructura histórica reconocible.
        _crear_esquema_historico(
            self.conexion,
            reemplazar_tablas={
                "clientes": (
                    "CREATE TABLE clientes (id TEXT, nombre TEXT, emisor_id INTEGER, "
                    "emisor_recomendado_id INTEGER, modalidad_comprobante TEXT, emisor_habitual TEXT)"
                )
            },
        )

        self.assertIn(self.inspeccionar().estado, BLOQUEANTES)


class BaseIncompletaTest(_PoliticaBase):

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

    @unittest.expectedFailure
    def test_requisito_futuro_falta_tabla_esencial_debe_bloquear(self):
        # Hoy una tabla esencial ausente se informa como INCOMPLETA, igual que una
        # columna de extensión faltante. Recrear clientes no es una migración
        # histórica conocida: debe bloquear.
        _crear_esquema_historico(self.conexion, omitir_tablas=("clientes",))

        self.assertIn(self.inspeccionar().estado, BLOQUEANTES)

    @unittest.expectedFailure
    def test_requisito_futuro_vista_en_lugar_de_tabla_esencial_debe_bloquear(self):
        # Una vista con el nombre de una tabla esencial se informa como tabla
        # faltante (INCOMPLETA); una migración intentaría crearla sobre la vista.
        _crear_esquema_historico(
            self.conexion,
            reemplazar_tablas={"clientes": "CREATE VIEW clientes AS SELECT 1 AS id, 'x' AS nombre"},
        )

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

    @unittest.expectedFailure
    def test_requisito_futuro_cae_duplicado_tras_trim_debe_bloquear(self):
        # El detector no busca duplicados de CAE; hoy solo informa el índice
        # faltante (INCOMPLETA) y la migración fallaría al crearlo.
        _crear_esquema_historico(self.conexion, omitir_indices=("idx_factura_arca_cae_unico",))
        _insertar_factura(self.conexion, **_factura_normalizada(cae="12345678901234"))
        _insertar_factura(
            self.conexion,
            **_factura_normalizada(
                numero_factura="00002-00000002", numero_comprobante_num=2, cae=" 12345678901234 "
            ),
        )

        self.assertEqual(self.inspeccionar().estado, "BLOQUEADA")

    @unittest.expectedFailure
    def test_requisito_futuro_colision_tras_normalizar_debe_bloquear(self):
        # Con columnas normalizadas en NULL el detector informa un backfill
        # pendiente (INCOMPLETA), pero no proyecta la normalización: ambas
        # facturas producirían la misma identidad y el índice único fallaría.
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

        self.assertEqual(self.inspeccionar().estado, "BLOQUEADA")

    @unittest.expectedFailure
    def test_requisito_futuro_duplicados_en_factura_sin_ambiente_debe_bloquear(self):
        # Sin la columna ambiente_arca el detector omite por completo la revisión
        # de identidad fiscal; los duplicados quedan ocultos tras INCOMPLETA.
        _crear_esquema_historico(
            self.conexion, omitir_columnas_factura=("ambiente_arca",), omitir_indices=_INDICES_FACTURA
        )
        for cae in ("111", "222"):
            datos = _factura_normalizada(cae=cae)
            datos.pop("ambiente_arca")
            _insertar_factura(self.conexion, **datos)

        self.assertEqual(self.inspeccionar().estado, "BLOQUEADA")


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

    @unittest.expectedFailure
    def test_requisito_futuro_identidad_textual_contradice_normalizada_debe_bloquear(self):
        # numero_factura indica punto de venta 3, pero la columna normalizada
        # registra 2. El detector solo revisa columnas normalizadas en NULL y hoy
        # devuelve HISTORICA_SIN_VERSION.
        _crear_esquema_historico(self.conexion)
        _insertar_factura(
            self.conexion,
            **_factura_normalizada(
                punto_venta="00003", numero_factura="00003-00000010", numero_comprobante_num=10, cae="111"
            ),
        )

        self.assertEqual(self.inspeccionar().estado, "BLOQUEADA")

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
