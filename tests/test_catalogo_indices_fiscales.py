"""Reconocimiento puro de SQL fiscal, con oraculo independiente y sin conexiones."""

import importlib.util
import sys
import unittest
from pathlib import Path
from types import ModuleType
from unittest.mock import patch


def _cargar_database_aislado():
    nombre = "_database_catalogo_indices_fiscales_test"
    ruta = Path(__file__).resolve().parents[1] / "database.py"
    spec = importlib.util.spec_from_file_location(nombre, ruta)
    modulo = importlib.util.module_from_spec(spec)
    runtime_paths_falso = ModuleType("runtime_paths")
    runtime_paths_falso.DATABASE_PATH = Path(":memory:")
    sys.modules[nombre] = modulo
    try:
        with patch.dict(sys.modules, {"runtime_paths": runtime_paths_falso}), patch(
            "sqlite3.connect", side_effect=AssertionError("Pruebas puras: SQLite prohibido")
        ):
            spec.loader.exec_module(modulo)
    except Exception:
        sys.modules.pop(nombre, None)
        raise
    return modulo


database = _cargar_database_aislado()

# Oraculo literal: no se deriva de constantes ni de funciones de database.
ACTUALES = (
    (
        "idx_factura_arca_identidad_unica", "factura_arca",
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_factura_arca_identidad_unica "
        "ON factura_arca(ambiente_arca, emisor_id, punto_venta_num, tipo_comprobante_num, numero_comprobante_num) "
        "WHERE ambiente_arca IS NOT NULL AND numero_comprobante_num IS NOT NULL AND emisor_id > 0 "
        "AND punto_venta_num > 0 AND tipo_comprobante_num > 0 AND numero_comprobante_num > 0",
    ),
    (
        "idx_factura_arca_identidad_historica_unica", "factura_arca",
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_factura_arca_identidad_historica_unica "
        "ON factura_arca(emisor_id, punto_venta_num, tipo_comprobante_num, numero_comprobante_num) "
        "WHERE ambiente_arca IS NULL AND numero_comprobante_num IS NOT NULL AND emisor_id > 0 "
        "AND punto_venta_num > 0 AND tipo_comprobante_num > 0 AND numero_comprobante_num > 0",
    ),
    (
        "idx_factura_arca_cae_unico", "factura_arca",
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_factura_arca_cae_unico "
        "ON factura_arca(ambiente_arca, TRIM(cae)) "
        "WHERE ambiente_arca IS NOT NULL AND TRIM(COALESCE(cae, '')) <> ''",
    ),
    (
        "idx_factura_arca_cae_historico_unico", "factura_arca",
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_factura_arca_cae_historico_unico "
        "ON factura_arca(TRIM(cae)) WHERE ambiente_arca IS NULL AND TRIM(COALESCE(cae, '')) <> ''",
    ),
    (
        "idx_intentos_emision_arca_clave_activa_ambiente", "intentos_emision_arca",
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_intentos_emision_arca_clave_activa_ambiente "
        "ON intentos_emision_arca(ambiente_arca, cuit_emisor, punto_venta, tipo_comprobante, numero_planificado) "
        "WHERE ambiente_arca IS NOT NULL AND TRIM(COALESCE(cuit_emisor, '')) <> '' AND punto_venta > 0 "
        "AND tipo_comprobante > 0 AND numero_planificado > 0 "
        "AND estado IN ('PENDIENTE_RECONCILIAR', 'ENVIANDO', 'CONFLICTO_MANUAL')",
    ),
    (
        "idx_intentos_emision_arca_clave_activa_historica", "intentos_emision_arca",
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_intentos_emision_arca_clave_activa_historica "
        "ON intentos_emision_arca(cuit_emisor, punto_venta, tipo_comprobante, numero_planificado) "
        "WHERE ambiente_arca IS NULL AND TRIM(COALESCE(cuit_emisor, '')) <> '' AND punto_venta > 0 "
        "AND tipo_comprobante > 0 AND numero_planificado > 0 "
        "AND estado IN ('PENDIENTE_RECONCILIAR', 'ENVIANDO', 'CONFLICTO_MANUAL')",
    ),
)

# Transcripciones de 0fe8ac7 (las dos primeras) y af3e31e (la tercera).
HISTORICAS = (
    (
        "idx_factura_arca_identidad_unica", "factura_arca",
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_factura_arca_identidad_unica "
        "ON factura_arca(emisor_id, punto_venta_num, tipo_comprobante_num, numero_comprobante_num) "
        "WHERE numero_comprobante_num IS NOT NULL",
    ),
    (
        "idx_factura_arca_cae_unico", "factura_arca",
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_factura_arca_cae_unico "
        "ON factura_arca(cae) WHERE TRIM(COALESCE(cae, '')) <> ''",
    ),
    (
        "idx_intentos_emision_arca_clave_activa", "intentos_emision_arca",
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_intentos_emision_arca_clave_activa "
        "ON intentos_emision_arca(cuit_emisor, punto_venta, tipo_comprobante, numero_planificado) "
        "WHERE estado IN ('PENDIENTE_RECONCILIAR', 'ENVIANDO', 'CONFLICTO_MANUAL')",
    ),
)


class CatalogoIndicesFiscalesTest(unittest.TestCase):

    def assertDesconocida(self, nombre, tabla, sql):
        self.assertEqual(
            database._reconocer_definicion_indice_fiscal(nombre, tabla, sql), "DESCONOCIDA"
        )

    def test_catalogos_completos_coinciden_con_oraculo_independiente(self):
        self.assertEqual(database._DEFINICIONES_INDICES_FISCALES_ACTUALES, ACTUALES)
        self.assertEqual(database._DEFINICIONES_INDICES_FISCALES_HISTORICAS, HISTORICAS)

    def test_seis_definiciones_actuales(self):
        for definicion in ACTUALES:
            with self.subTest(nombre=definicion[0]):
                self.assertEqual(database._reconocer_definicion_indice_fiscal(*definicion), "ACTUAL")

    def test_tres_definiciones_historicas(self):
        for definicion in HISTORICAS:
            with self.subTest(nombre=definicion[0]):
                self.assertEqual(database._reconocer_definicion_indice_fiscal(*definicion), "HISTORICA")

    def test_formato_admitido_por_normalizador_sin_variantes_nuevas(self):
        for estado, definiciones in (("ACTUAL", ACTUALES), ("HISTORICA", HISTORICAS)):
            for nombre, tabla, sql in definiciones:
                for variante in (
                    sql.replace(" IF NOT EXISTS", ""),
                    "\t" + sql.replace("CREATE UNIQUE INDEX", "create \n unique index") + "\r\n",
                ):
                    with self.subTest(nombre=nombre, sql=variante):
                        self.assertEqual(
                            database._reconocer_definicion_indice_fiscal(nombre, tabla, variante), estado
                        )

    def test_literal_enviando_alterado_no_se_reconoce(self):
        for nombre, tabla, sql in ACTUALES + HISTORICAS:
            if "'ENVIANDO'" not in sql:
                continue
            for literal in ("'enviando'", "'Enviando'", "'EN VIANDO'", "'EN  VIANDO'"):
                with self.subTest(nombre=nombre, literal=literal):
                    self.assertDesconocida(nombre, tabla, sql.replace("'ENVIANDO'", literal))

    def test_nombre_de_metadatos_incorrecto(self):
        for nombre, tabla, sql in ACTUALES + HISTORICAS:
            with self.subTest(nombre=nombre):
                self.assertDesconocida(nombre + "_ajeno", tabla, sql)
                self.assertDesconocida(nombre.upper(), tabla, sql)

    def test_nombre_dentro_del_sql_incorrecto(self):
        for nombre, tabla, sql in ACTUALES + HISTORICAS:
            with self.subTest(nombre=nombre):
                self.assertDesconocida(nombre, tabla, sql.replace(nombre, nombre + "_ajeno"))

    def test_homonimo_sobre_tabla_incorrecta(self):
        for nombre, tabla, sql in ACTUALES + HISTORICAS:
            with self.subTest(nombre=nombre):
                self.assertDesconocida(nombre, "resumenes", sql.replace(f"ON {tabla}(", "ON resumenes("))

    def test_tabla_de_metadatos_y_sql_se_validan_por_separado(self):
        for nombre, tabla, sql in ACTUALES + HISTORICAS:
            with self.subTest(nombre=nombre):
                self.assertDesconocida(nombre, "resumenes", sql)
                self.assertDesconocida(nombre, tabla.upper(), sql)
                self.assertDesconocida(nombre, tabla, sql.replace(f"ON {tabla}(", "ON resumenes("))

    def test_predicados_alterados_y_ausentes(self):
        for nombre, tabla, sql in ACTUALES + HISTORICAS:
            with self.subTest(nombre=nombre):
                self.assertDesconocida(nombre, tabla, sql + " AND 1=1")
                self.assertDesconocida(nombre, tabla, sql.split(" WHERE ")[0])
                self.assertDesconocida(nombre, tabla, sql + " OR 1=1")
                if "IS NOT NULL" in sql:
                    self.assertDesconocida(nombre, tabla, sql.replace("IS NOT NULL", "IS NULL", 1))

    def test_unicidad_no_puede_omitirse(self):
        for nombre, tabla, sql in ACTUALES + HISTORICAS:
            with self.subTest(nombre=nombre):
                self.assertDesconocida(nombre, tabla, sql.replace("CREATE UNIQUE INDEX", "CREATE INDEX"))

    def test_expresiones_orden_colacion_y_limites_no_se_equiparan(self):
        for nombre, tabla, sql in ACTUALES:
            variantes = (
                sql.replace("TRIM(cae)", "cae"),
                sql.replace("emisor_id, punto_venta_num", "punto_venta_num, emisor_id"),
                sql.replace("cuit_emisor, punto_venta", "cuit_emisor COLLATE NOCASE, punto_venta"),
                sql.replace("punto_venta > 0", "punto_venta >= 0"),
            )
            for variante in variantes:
                if variante != sql:
                    with self.subTest(nombre=nombre, sql=variante):
                        self.assertDesconocida(nombre, tabla, variante)

    def test_variantes_textuales_no_acreditadas_se_rechazan(self):
        for nombre, tabla, sql in ACTUALES + HISTORICAS:
            for variante in (
                sql.replace(", ", ","),
                sql + " /* variante */",
                sql.replace(f"ON {tabla}(", f'ON "{tabla}"('),
                sql + "; DROP TABLE factura_arca",
            ):
                with self.subTest(nombre=nombre, sql=variante):
                    self.assertNotEqual(variante, sql)
                    self.assertDesconocida(nombre, tabla, variante)

    def test_sql_ausente_vacio_o_ajeno_no_se_reconoce(self):
        nombre, tabla, _sql = ACTUALES[0]
        for sql in (None, "", " ", "CREATE TABLE factura_arca(id INTEGER)"):
            with self.subTest(sql=sql):
                self.assertDesconocida(nombre, tabla, sql)

    def test_nombres_compartidos_distinguen_actual_e_historica_por_sql(self):
        for historica in HISTORICAS[:2]:
            actual = next(definicion for definicion in ACTUALES if definicion[0] == historica[0])
            self.assertEqual(database._reconocer_definicion_indice_fiscal(*actual), "ACTUAL")
            self.assertEqual(database._reconocer_definicion_indice_fiscal(*historica), "HISTORICA")

    def test_reconocimiento_no_conecta_ni_modifica_catalogos(self):
        antes = (
            database._DEFINICIONES_INDICES_FISCALES_ACTUALES,
            database._DEFINICIONES_INDICES_FISCALES_HISTORICAS,
            database._INDICES_UNICOS_INSPECCION_ESPERADOS,
        )
        with patch.object(database, "conectar") as conectar, patch("sqlite3.connect") as connect:
            for _repeticion in range(2):
                for definicion in ACTUALES + HISTORICAS:
                    database._reconocer_definicion_indice_fiscal(*definicion)
            conectar.assert_not_called()
            connect.assert_not_called()
        self.assertEqual(antes, (
            database._DEFINICIONES_INDICES_FISCALES_ACTUALES,
            database._DEFINICIONES_INDICES_FISCALES_HISTORICAS,
            database._INDICES_UNICOS_INSPECCION_ESPERADOS,
        ))


if __name__ == "__main__":
    unittest.main()
