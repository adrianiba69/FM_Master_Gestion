import importlib.util
import sqlite3
import sys
import unittest
from pathlib import Path
from types import ModuleType
from unittest.mock import patch


def _cargar_database_aislado():
    """Carga database.py con runtime_paths falso para evitar preparar rutas reales."""
    nombre_modulo = "_database_inspeccion_estado_sqlite_test"
    ruta_database = Path(__file__).resolve().parents[1] / "database.py"
    spec = importlib.util.spec_from_file_location(nombre_modulo, ruta_database)
    modulo = importlib.util.module_from_spec(spec)
    runtime_paths_falso = ModuleType("runtime_paths")
    runtime_paths_falso.DATABASE_PATH = Path(":memory:")
    sys.modules[nombre_modulo] = modulo
    try:
        with patch.dict(sys.modules, {"runtime_paths": runtime_paths_falso}):
            spec.loader.exec_module(modulo)
    except Exception:
        sys.modules.pop(nombre_modulo, None)
        raise
    return modulo


database = _cargar_database_aislado()


def _crear_esquema_completo(
    conexion, tabla_omitida=None, columna_omitida=None, indice_omitido=None, crear_indices=True
):
    cursor = conexion.cursor()
    for tabla, columnas in database._ESTRUCTURAS_INSPECCION_ESPERADAS.items():
        if tabla == tabla_omitida:
            continue
        columnas_tabla = [columna for columna in columnas if (tabla, columna) != columna_omitida]
        columnas_sql = ", ".join(f'"{columna}"' for columna in columnas_tabla)
        cursor.execute(f'CREATE TABLE "{tabla}" ({columnas_sql})')

    if not crear_indices:
        return

    for nombre, tabla, clave, condicion in database._INDICES_UNICOS_INSPECCION_ESPERADOS:
        if nombre == indice_omitido:
            continue
        cursor.execute(
            f'CREATE UNIQUE INDEX {nombre} ON {tabla}({clave}) WHERE {condicion}'
        )


class InspeccionEstadoBaseSQLiteTest(unittest.TestCase):

    def setUp(self):
        self.conexion = sqlite3.connect(":memory:")
        self.addCleanup(self.conexion.close)

    def inspeccionar(self, conexion=None, **kwargs):
        return database.inspeccionar_estado_base_sqlite(conexion or self.conexion, **kwargs)

    def test_base_vacia_es_nueva_solo_con_confirmacion_explicita(self):
        resultado = self.inspeccionar(instalacion_nueva_confirmada=True)

        self.assertEqual(resultado.estado, "NUEVA")
        self.assertIsNone(resultado.version_registrada)

    def test_base_vacia_sin_confirmacion_es_bloqueada(self):
        resultado = self.inspeccionar()

        self.assertEqual(resultado.estado, "BLOQUEADA")
        self.assertIsNone(resultado.version_registrada)
        self.assertIn("falta confirmación explícita de instalación nueva", " ".join(resultado.motivos))

    def test_base_historica_completa_sin_version_permanece_historica(self):
        _crear_esquema_completo(self.conexion)

        resultado = self.inspeccionar()

        self.assertEqual(resultado.estado, "HISTORICA_SIN_VERSION")
        self.assertIsNone(resultado.version_registrada)
        self.assertEqual(resultado.estructuras_pendientes, ())
        self.assertEqual(resultado.condiciones_pendientes, ())
        self.assertNotEqual(resultado.estado, "ACTUAL")

    def test_tabla_o_columna_obligatoria_faltante_es_incompleta(self):
        escenarios = (
            {"tabla_omitida": "clientes"},
            {"columna_omitida": ("clientes", "modalidad_comprobante")},
        )
        for escenario in escenarios:
            with self.subTest(escenario=escenario):
                conexion = sqlite3.connect(":memory:")
                self.addCleanup(conexion.close)
                _crear_esquema_completo(conexion, **escenario)

                resultado = self.inspeccionar(conexion)

                self.assertEqual(resultado.estado, "INCOMPLETA")
                self.assertTrue(resultado.estructuras_pendientes)

    def test_indice_unico_obligatorio_faltante_es_incompleta(self):
        _crear_esquema_completo(
            self.conexion, indice_omitido="idx_factura_arca_cae_historico_unico"
        )

        resultado = self.inspeccionar()

        self.assertEqual(resultado.estado, "INCOMPLETA")
        self.assertIn(
            "indice:idx_factura_arca_cae_historico_unico",
            resultado.estructuras_pendientes,
        )

    def test_duplicados_que_bloquean_indice_unico_clasifican_bloqueada(self):
        _crear_esquema_completo(self.conexion)
        self.conexion.executemany(
            "INSERT INTO emisor_fiscal_arca_config(emisor_fiscal_id, ambiente_arca) VALUES(?, ?)",
            ((30, "HOMOLOGACION"), (30, "HOMOLOGACION")),
        )

        resultado = self.inspeccionar()

        self.assertEqual(resultado.estado, "BLOQUEADA")
        self.assertIn(
            "duplicados:emisor_fiscal_arca_config(emisor_fiscal_id, ambiente_arca)",
            resultado.motivos,
        )

    def test_ambiente_historico_nulo_es_advertencia_no_bloqueante(self):
        _crear_esquema_completo(self.conexion)
        self.conexion.execute(
            "INSERT INTO factura_arca(id, emisor_id, numero_factura, cae, punto_venta_num, "
            "tipo_comprobante_num, numero_comprobante_num, ambiente_arca) "
            "VALUES(1, 40, '00002-00000001', 'CAE-1', 2, 11, 1, NULL)"
        )
        self.conexion.execute(
            "INSERT INTO intentos_emision_arca(id, cuit_emisor, punto_venta, tipo_comprobante, "
            "numero_planificado, estado, ambiente_arca) "
            "VALUES(1, '20206871629', 2, 11, 1, 'PENDIENTE_RECONCILIAR', NULL)"
        )

        resultado = self.inspeccionar()

        self.assertEqual(resultado.estado, "HISTORICA_SIN_VERSION")
        self.assertEqual(resultado.condiciones_pendientes, ())
        self.assertEqual(len(resultado.advertencias), 2)
        self.assertTrue(any("factura_arca.ambiente_historico_desconocido" in aviso for aviso in resultado.advertencias))
        self.assertTrue(any("intentos_emision_arca.ambiente_historico_desconocido" in aviso for aviso in resultado.advertencias))
        self.assertEqual(
            self.conexion.execute("SELECT ambiente_arca FROM factura_arca WHERE id=1").fetchone()[0],
            None,
        )
        self.assertEqual(
            self.conexion.execute("SELECT ambiente_arca FROM intentos_emision_arca WHERE id=1").fetchone()[0],
            None,
        )

    def test_backfill_objetivamente_pendiente_es_incompleta(self):
        _crear_esquema_completo(self.conexion)
        self.conexion.execute(
            "INSERT INTO servicios(id, fecha_inicio, fecha_fin) VALUES(1, '2026-10-01', '2026-10-31')"
        )
        self.conexion.execute(
            "INSERT INTO resumen_conceptos(id, servicio_id, fecha_inicio, fecha_fin) VALUES(1, 1, NULL, NULL)"
        )

        resultado = self.inspeccionar()

        self.assertEqual(resultado.estado, "INCOMPLETA")
        self.assertIn("resumen_conceptos.fecha_inicio_backfill:1", resultado.condiciones_pendientes)
        self.assertIn("resumen_conceptos.fecha_fin_backfill:1", resultado.condiciones_pendientes)

    def test_version_no_reconocida_o_marcador_desconocido_es_incompatible(self):
        escenarios = ("version", "marcador")
        for escenario in escenarios:
            with self.subTest(escenario=escenario):
                conexion = sqlite3.connect(":memory:")
                self.addCleanup(conexion.close)
                if escenario == "version":
                    conexion.execute("PRAGMA user_version = 99")
                else:
                    conexion.execute("CREATE TABLE schema_migrations (version INTEGER)")

                resultado = self.inspeccionar(conexion)

                self.assertEqual(resultado.estado, "VERSION_INCOMPATIBLE")
                self.assertNotEqual(resultado.estado, "ACTUAL")

    def test_error_de_inspeccion_bloquea_sin_intentar_reparar(self):
        class CursorFallido:
            def __init__(self):
                self.consultas = []

            def execute(self, consulta):
                self.consultas.append(consulta)
                raise sqlite3.OperationalError("conexion de solo lectura")

        class ConexionFallida:
            def __init__(self):
                self.cursor_falso = CursorFallido()

            def cursor(self):
                return self.cursor_falso

        conexion = ConexionFallida()

        resultado = self.inspeccionar(conexion)

        self.assertEqual(resultado.estado, "BLOQUEADA")
        self.assertIn("OperationalError", resultado.motivos[0])
        self.assertEqual(conexion.cursor_falso.consultas, ["PRAGMA user_version"])

    def test_inspeccion_no_modifica_version_esquema_ni_filas(self):
        _crear_esquema_completo(self.conexion)
        self.conexion.execute(
            "INSERT INTO resumenes(id, numero, estado_facturacion) VALUES(1, 100, 'Pendiente')"
        )
        user_version_antes = self.conexion.execute("PRAGMA user_version").fetchone()[0]
        esquema_antes = self.conexion.execute(
            "SELECT type, name, sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%' ORDER BY type, name"
        ).fetchall()
        filas_antes = self.conexion.execute("SELECT * FROM resumenes").fetchall()
        consultas = []
        self.conexion.set_trace_callback(consultas.append)

        self.inspeccionar()

        self.conexion.set_trace_callback(None)
        user_version_despues = self.conexion.execute("PRAGMA user_version").fetchone()[0]
        esquema_despues = self.conexion.execute(
            "SELECT type, name, sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%' ORDER BY type, name"
        ).fetchall()
        filas_despues = self.conexion.execute("SELECT * FROM resumenes").fetchall()

        self.assertEqual(user_version_despues, user_version_antes)
        self.assertEqual(esquema_despues, esquema_antes)
        self.assertEqual(filas_despues, filas_antes)
        self.assertTrue(consultas)
        self.assertTrue(
            all(consulta.lstrip().upper().startswith(("SELECT", "PRAGMA")) for consulta in consultas),
            consultas,
        )


class IndicesMigradosFrenteAlDetectorTest(unittest.TestCase):
    """Crea los índices con las migraciones reales, no con las constantes del detector."""

    def setUp(self):
        self.conexion = sqlite3.connect(":memory:")
        self.addCleanup(self.conexion.close)
        _crear_esquema_completo(self.conexion, crear_indices=False)
        cursor = self.conexion.cursor()
        database.migrar_indices_unicos_factura_arca(cursor)
        database.migrar_indices_activos_intentos_emision_arca(cursor)
        self.conexion.commit()

    def test_detector_reconoce_indices_creados_por_migraciones_reales(self):
        indices_creados = {
            fila[0]
            for fila in self.conexion.execute(
                "SELECT name FROM sqlite_master WHERE type='index' AND sql IS NOT NULL"
            )
        }
        for nombre, *_ in database._INDICES_UNICOS_INSPECCION_ESPERADOS:
            self.assertIn(nombre, indices_creados)

        resultado = database.inspeccionar_estado_base_sqlite(self.conexion)

        pendientes_indices = [
            item for item in resultado.estructuras_pendientes if item.startswith("indice")
        ]
        self.assertEqual(pendientes_indices, [])
        self.assertEqual(resultado.estado, "HISTORICA_SIN_VERSION")

    def test_identidad_fiscal_es_unica_por_ambiente(self):
        insertar = (
            "INSERT INTO factura_arca(emisor_id, punto_venta_num, tipo_comprobante_num, "
            "numero_comprobante_num, ambiente_arca) VALUES(1, 2, 11, 5, ?)"
        )
        self.conexion.execute(insertar, ("HOMOLOGACION",))
        self.conexion.execute(insertar, ("PRODUCCION",))

        with self.assertRaises(sqlite3.IntegrityError):
            self.conexion.execute(insertar, ("HOMOLOGACION",))
        with self.assertRaises(sqlite3.IntegrityError):
            self.conexion.execute(insertar, ("PRODUCCION",))

        self.assertEqual(
            self.conexion.execute("SELECT COUNT(*) FROM factura_arca").fetchone()[0], 2
        )


if __name__ == "__main__":
    unittest.main()