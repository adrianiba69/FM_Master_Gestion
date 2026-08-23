"""Tests del snapshot fiscal inmutable v1."""

import json
import re
import unittest
from copy import deepcopy
from decimal import Decimal

from services.arca.snapshot_fiscal_service import (
    CODIGO_ESTRUCTURA_INVALIDA,
    CODIGO_HASH_INVALIDO,
    CODIGO_JSON_INVALIDO,
    CODIGO_VALIDO,
    CODIGO_VERSION_INVALIDA,
    SNAPSHOT_VERSION,
    SnapshotFiscalError,
    calcular_hash_snapshot,
    construir_snapshot_fiscal_v1,
    serializar_snapshot_fiscal,
    validar_integridad_snapshot,
    validar_snapshot_fiscal_v1,
)


class SnapshotFiscalServiceTest(unittest.TestCase):
    def _datos_factura_a(self):
        return {
            "fuente": "cierre_normal",
            "creado_en": "2026-08-23T12:34:56",
            "ambiente": "HOMOLOGACION",
            "emisor": {
                "emisor_id": 1,
                "emisor_fiscal_id": 1,
                "razon_social": "FM Master SRL",
                "nombre_fantasia": "FM Máster",
                "cuit": "20111111117",
                "condicion_iva": "Responsable Inscripto",
                "domicilio": "Domicilio fiscal 123",
                "ingresos_brutos": "123456",
                "fecha_inicio_actividades": "2020-01-01",
                "punto_venta_num": 5,
            },
            "receptor": {
                "cliente_id": 10,
                "razon_social": "Cliente SA",
                "documento_visible": "20222222221",
                "condicion_iva": "Responsable Inscripto",
                "domicilio": "Cliente 456 - Localidad",
                "tipo_documento_receptor": 80,
                "documento_receptor": 20222222221,
            },
            "comprobante": {
                "fecha": "2026-08-23",
                "fecha_arca": "20260823",
                "concepto": 1,
                "concepto_descripcion": "1 - Productos",
                "punto_venta_num": 5,
                "tipo_comprobante_num": 1,
                "tipo_comprobante_texto": "Factura A",
                "numero_comprobante_num": 123,
                "numero_textual": "00005-00000123",
                "periodo_servicio_desde": None,
                "periodo_servicio_hasta": None,
                "vencimiento_pago": None,
                "moneda": "PES",
                "cotizacion": Decimal("1"),
            },
            "importes": {
                "total": Decimal("1210"),
                "neto": Decimal("1000"),
                "iva": Decimal("210"),
                "exento": Decimal("0"),
                "no_gravado": Decimal("0"),
                "tributos": Decimal("0"),
            },
            "iva": [
                {
                    "id": 5,
                    "base_imponible": Decimal("1000"),
                    "importe": Decimal("210"),
                    "porcentaje": Decimal("21"),
                }
            ],
            "items": [
                {
                    "concepto": "Servicio mensual",
                    "descripcion": "Servicio mensual - Publicidad agosto",
                    "cantidad": Decimal("1"),
                    "precio_unitario": Decimal("1000"),
                    "subtotal": Decimal("1000"),
                }
            ],
            "autorizacion": {
                "cae": "12345678901234",
                "vencimiento_cae": "2026-09-02",
                "vencimiento_cae_arca": "20260902",
                "tipo_cod_aut": "E",
                "resultado": "AUTORIZADO",
                "cerrado_en": "2026-08-23T12:34:56",
            },
        }

    def _snapshot_a(self):
        return construir_snapshot_fiscal_v1(**self._datos_factura_a())

    def _datos_factura_c(self):
        datos = self._datos_factura_a()
        datos["emisor"]["condicion_iva"] = "Monotributo"
        datos["receptor"]["razon_social"] = "Cliente Consumidor"
        datos["receptor"]["condicion_iva"] = "Consumidor Final"
        datos["receptor"]["documento_visible"] = "0"
        datos["receptor"]["tipo_documento_receptor"] = 99
        datos["receptor"]["documento_receptor"] = 0
        datos["comprobante"]["tipo_comprobante_num"] = 11
        datos["comprobante"]["tipo_comprobante_texto"] = "Factura C"
        datos["comprobante"]["numero_comprobante_num"] = 124
        datos["comprobante"]["numero_textual"] = "00005-00000124"
        datos["importes"]["total"] = Decimal("1000")
        datos["importes"]["iva"] = Decimal("0")
        datos["iva"] = []
        datos["autorizacion"]["cae"] = "12345678901235"
        return datos

    def _assert_no_float(self, valor):
        self.assertNotIsInstance(valor, float)
        if isinstance(valor, dict):
            for contenido in valor.values():
                self._assert_no_float(contenido)
        elif isinstance(valor, list):
            for contenido in valor:
                self._assert_no_float(contenido)

    def test_construir_factura_a_completa(self):
        snapshot = self._snapshot_a()
        self.assertEqual(snapshot["version"], 1)
        self.assertEqual(snapshot["ambiente"], "HOMOLOGACION")
        self.assertEqual(snapshot["comprobante"]["tipo_comprobante_num"], 1)
        self.assertEqual(snapshot["importes"]["total"], "1210.00")

    def test_construir_factura_c_completa(self):
        snapshot = construir_snapshot_fiscal_v1(**self._datos_factura_c())
        self.assertEqual(snapshot["comprobante"]["tipo_comprobante_num"], 11)
        self.assertEqual(snapshot["iva"], [])
        self.assertEqual(snapshot["importes"]["iva"], "0.00")

    def test_todas_las_claves_contractuales_presentes(self):
        snapshot = self._snapshot_a()
        self.assertEqual(
            set(snapshot.keys()),
            {"version", "fuente", "creado_en", "ambiente", "emisor", "receptor", "comprobante", "importes", "iva", "items", "autorizacion"},
        )
        self.assertIn("nombre_fantasia", snapshot["emisor"])
        self.assertIn("periodo_servicio_desde", snapshot["comprobante"])

    def test_nullable_representado_como_none(self):
        snapshot = self._snapshot_a()
        self.assertIsNone(snapshot["comprobante"]["periodo_servicio_desde"])
        self.assertIsNone(snapshot["comprobante"]["periodo_servicio_hasta"])
        self.assertIsNone(snapshot["comprobante"]["vencimiento_pago"])

    def test_monetarios_a_2_decimales(self):
        snapshot = self._snapshot_a()
        for valor in snapshot["importes"].values():
            self.assertRegex(valor, r"^\d+\.\d{2}$")

    def test_cantidades_a_6_decimales(self):
        self.assertEqual(self._snapshot_a()["items"][0]["cantidad"], "1.000000")

    def test_cotizacion_a_6_decimales(self):
        self.assertEqual(self._snapshot_a()["comprobante"]["cotizacion"], "1.000000")

    def test_porcentaje_iva_a_2_decimales(self):
        self.assertEqual(self._snapshot_a()["iva"][0]["porcentaje"], "21.00")

    def test_ningun_float_en_arbol_final(self):
        self._assert_no_float(self._snapshot_a())

    def test_json_determinista(self):
        snapshot = self._snapshot_a()
        self.assertEqual(serializar_snapshot_fiscal(snapshot), serializar_snapshot_fiscal(snapshot))

    def test_orden_de_entrada_distinto_produce_mismo_json(self):
        datos = self._datos_factura_a()
        datos["emisor"] = dict(reversed(list(datos["emisor"].items())))
        snapshot_reordenado = construir_snapshot_fiscal_v1(**datos)
        self.assertEqual(serializar_snapshot_fiscal(self._snapshot_a()), serializar_snapshot_fiscal(snapshot_reordenado))

    def test_utf8_acentos(self):
        serializado = serializar_snapshot_fiscal(self._snapshot_a())
        self.assertIn("FM Máster", serializado)

    def test_sha256_reproducible(self):
        serializado = serializar_snapshot_fiscal(self._snapshot_a())
        self.assertEqual(calcular_hash_snapshot(serializado), calcular_hash_snapshot(serializado))

    def test_hash_64_lowercase(self):
        digest = calcular_hash_snapshot(serializar_snapshot_fiscal(self._snapshot_a()))
        self.assertRegex(digest, r"^[0-9a-f]{64}$")

    def test_cambio_de_un_dato_cambia_hash(self):
        snapshot = self._snapshot_a()
        serializado = serializar_snapshot_fiscal(snapshot)
        cambiado = deepcopy(snapshot)
        cambiado["receptor"]["razon_social"] = "Otro Cliente"
        self.assertNotEqual(calcular_hash_snapshot(serializado), calcular_hash_snapshot(serializar_snapshot_fiscal(cambiado)))

    def test_ambiente_homologacion_valido(self):
        self.assertEqual(self._snapshot_a()["ambiente"], "HOMOLOGACION")

    def test_ambiente_produccion_valido(self):
        datos = self._datos_factura_a()
        datos["ambiente"] = "PRODUCCION"
        self.assertEqual(construir_snapshot_fiscal_v1(**datos)["ambiente"], "PRODUCCION")

    def test_ambiente_invalido_falla(self):
        datos = self._datos_factura_a()
        datos["ambiente"] = "Testing"
        with self.assertRaisesRegex(SnapshotFiscalError, "ambiente"):
            construir_snapshot_fiscal_v1(**datos)

    def test_cuit_valido_estructural(self):
        self.assertEqual(self._snapshot_a()["emisor"]["cuit"], "20111111117")

    def test_cuit_invalido_falla(self):
        datos = self._datos_factura_a()
        datos["emisor"]["cuit"] = "20111"
        with self.assertRaisesRegex(SnapshotFiscalError, "cuit"):
            construir_snapshot_fiscal_v1(**datos)

    def test_fecha_valida(self):
        self.assertEqual(self._snapshot_a()["comprobante"]["fecha"], "2026-08-23")

    def test_fecha_invalida_falla(self):
        datos = self._datos_factura_a()
        datos["comprobante"]["fecha"] = "23/08/2026"
        with self.assertRaisesRegex(SnapshotFiscalError, "fecha"):
            construir_snapshot_fiscal_v1(**datos)

    def test_fecha_arca_valida(self):
        self.assertEqual(self._snapshot_a()["comprobante"]["fecha_arca"], "20260823")

    def test_fecha_arca_invalida_falla(self):
        datos = self._datos_factura_a()
        datos["comprobante"]["fecha_arca"] = "2026-08-23"
        with self.assertRaisesRegex(SnapshotFiscalError, "fecha_arca"):
            construir_snapshot_fiscal_v1(**datos)

    def test_cae_se_conserva_string(self):
        self.assertIsInstance(self._snapshot_a()["autorizacion"]["cae"], str)

    def test_iva_a_completo(self):
        iva = self._snapshot_a()["iva"][0]
        self.assertEqual(set(iva.keys()), {"id", "base_imponible", "importe", "porcentaje"})

    def test_iva_c_vacio(self):
        self.assertEqual(construir_snapshot_fiscal_v1(**self._datos_factura_c())["iva"], [])

    def test_item_completo(self):
        item = self._snapshot_a()["items"][0]
        self.assertEqual(set(item.keys()), {"concepto", "descripcion", "cantidad", "precio_unitario", "subtotal"})

    def test_concepto_item_null(self):
        datos = self._datos_factura_a()
        datos["items"][0]["concepto"] = None
        self.assertIsNone(construir_snapshot_fiscal_v1(**datos)["items"][0]["concepto"])

    def test_clave_obligatoria_ausente_falla(self):
        snapshot = self._snapshot_a()
        del snapshot["emisor"]["cuit"]
        valido, errores = validar_snapshot_fiscal_v1(snapshot)
        self.assertFalse(valido)
        self.assertTrue(any("cuit" in error for error in errores))

    def test_version_incorrecta_falla(self):
        snapshot = self._snapshot_a()
        snapshot["version"] = 2
        valido, errores = validar_snapshot_fiscal_v1(snapshot)
        self.assertFalse(valido)
        self.assertTrue(any("version" in error for error in errores))

    def test_json_invalido_detectado(self):
        resultado = validar_integridad_snapshot("{mal", SNAPSHOT_VERSION, "0" * 64)
        self.assertEqual(resultado.codigo, CODIGO_JSON_INVALIDO)

    def test_hash_incorrecto_detectado(self):
        serializado = serializar_snapshot_fiscal(self._snapshot_a())
        resultado = validar_integridad_snapshot(serializado, SNAPSHOT_VERSION, "0" * 64)
        self.assertEqual(resultado.codigo, CODIGO_HASH_INVALIDO)

    def test_estructura_corrupta_detectada(self):
        snapshot = self._snapshot_a()
        del snapshot["items"]
        json_text = json.dumps(snapshot, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        digest = calcular_hash_snapshot(json_text)
        resultado = validar_integridad_snapshot(json_text, SNAPSHOT_VERSION, digest)
        self.assertEqual(resultado.codigo, CODIGO_ESTRUCTURA_INVALIDA)

    def test_snapshot_externo_version_distinta_falla(self):
        serializado = serializar_snapshot_fiscal(self._snapshot_a())
        digest = calcular_hash_snapshot(serializado)
        resultado = validar_integridad_snapshot(serializado, 2, digest)
        self.assertEqual(resultado.codigo, CODIGO_VERSION_INVALIDA)

    def test_integridad_valida(self):
        serializado = serializar_snapshot_fiscal(self._snapshot_a())
        digest = calcular_hash_snapshot(serializado)
        resultado = validar_integridad_snapshot(serializado, SNAPSHOT_VERSION, digest)
        self.assertTrue(resultado.valido)
        self.assertEqual(resultado.codigo, CODIGO_VALIDO)

    def test_decimal_invalido_falla(self):
        datos = self._datos_factura_a()
        datos["importes"]["total"] = "abc"
        with self.assertRaisesRegex(SnapshotFiscalError, "decimal"):
            construir_snapshot_fiscal_v1(**datos)

    def test_float_de_entrada_decimal_falla(self):
        datos = self._datos_factura_a()
        datos["importes"]["total"] = 1210.0
        with self.assertRaisesRegex(SnapshotFiscalError, "float"):
            construir_snapshot_fiscal_v1(**datos)

    def test_float_dentro_snapshot_final_falla(self):
        snapshot = self._snapshot_a()
        snapshot["importes"]["total"] = 1210.0
        valido, errores = validar_snapshot_fiscal_v1(snapshot)
        self.assertFalse(valido)
        self.assertTrue(any("float" in error for error in errores))

    def test_estructura_iva_incorrecta_falla(self):
        snapshot = self._snapshot_a()
        del snapshot["iva"][0]["porcentaje"]
        valido, errores = validar_snapshot_fiscal_v1(snapshot)
        self.assertFalse(valido)
        self.assertTrue(any("iva[0]" in error for error in errores))

    def test_estructura_item_incorrecta_falla(self):
        snapshot = self._snapshot_a()
        del snapshot["items"][0]["subtotal"]
        valido, errores = validar_snapshot_fiscal_v1(snapshot)
        self.assertFalse(valido)
        self.assertTrue(any("items[0]" in error for error in errores))

    def test_sin_import_sqlite(self):
        import services.arca.snapshot_fiscal_service as modulo

        self.assertFalse(hasattr(modulo, "conectar"))
        self.assertNotIn("sqlite", " ".join(modulo.__dict__.keys()).lower())

    def test_sin_import_red(self):
        import services.arca.snapshot_fiscal_service as modulo

        nombres = " ".join(modulo.__dict__.keys()).lower()
        self.assertNotIn("urllib", nombres)
        self.assertNotIn("requests", nombres)

    def test_serializado_es_json_compacto(self):
        serializado = serializar_snapshot_fiscal(self._snapshot_a())
        self.assertNotIn(": ", serializado)
        self.assertNotIn(", ", serializado)
        self.assertIsInstance(json.loads(serializado), dict)

    def test_hash_no_esta_dentro_del_json(self):
        serializado = serializar_snapshot_fiscal(self._snapshot_a())
        self.assertNotIn("snapshot_hash", serializado)

    def test_hash_formato_lowercase(self):
        digest = calcular_hash_snapshot(serializar_snapshot_fiscal(self._snapshot_a()))
        self.assertIsNotNone(re.fullmatch(r"[0-9a-f]{64}", digest))


if __name__ == "__main__":
    unittest.main()