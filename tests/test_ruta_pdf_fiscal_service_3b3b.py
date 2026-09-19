"""Tests puros de POST-E2E 3B.3B: identidad documental y resolucion segura
del PDF fiscal.

Modulo bajo prueba: services/arca/ruta_pdf_fiscal_service.py
CERO DB. CERO filesystem real. CERO ARCA/WSAA/WSFE.
"""

import unittest
from decimal import Decimal
from pathlib import Path

from services.arca.ruta_pdf_fiscal_service import (
    RutaPdfFiscalInvalidaError,
    construir_rutas_pdf_persistibles,
    reconstruir_ruta_pdf_relativa,
    resolver_ruta_pdf_documental,
    validar_ruta_pdf_absoluta,
    validar_ruta_pdf_relativa,
)
from services.arca.snapshot_fiscal_service import (
    SNAPSHOT_VERSION,
    calcular_hash_snapshot,
    construir_snapshot_fiscal_v1,
    serializar_snapshot_fiscal,
)

AMBIENTE_H = "HOMOLOGACION"
AMBIENTE_P = "PRODUCCION"

RELATIVA_H = r"Homologacion\facturas\Cliente_Factura_A_00002-00000010.pdf"
RELATIVA_P = r"Produccion\facturas\Cliente_Factura_A_00002-00000010.pdf"

CARPETA_CONFIGURADA = r"C:\FM_Master_Certificados\ClienteX"


def _datos_snapshot(ambiente):
    return {
        "fuente": "cierre_normal",
        "creado_en": "2026-08-23T12:34:56",
        "ambiente": ambiente,
        "emisor": {
            "emisor_id": 1,
            "emisor_fiscal_id": 3,
            "razon_social": "FM Master SRL",
            "nombre_fantasia": "FM Master",
            "cuit": "20111111117",
            "condicion_iva": "Responsable Inscripto",
            "domicilio": "Domicilio fiscal 123",
            "ingresos_brutos": "123456",
            "fecha_inicio_actividades": "2020-01-01",
            "punto_venta_num": 2,
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
            "concepto_descripcion": "Productos",
            "punto_venta_num": 2,
            "tipo_comprobante_num": 1,
            "tipo_comprobante_texto": "Factura A",
            "numero_comprobante_num": 10,
            "numero_textual": "00002-00000010",
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
            {"id": 5, "base_imponible": Decimal("1000"), "importe": Decimal("210"), "porcentaje": Decimal("21")}
        ],
        "items": [
            {
                "concepto": "Servicio mensual",
                "descripcion": "Publicidad agosto",
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


def _snapshot_valido_persistido(ambiente):
    """Construye un snapshot v1 real y su hash canonico (nunca un hash inventado)."""
    snapshot = construir_snapshot_fiscal_v1(**_datos_snapshot(ambiente))
    serializado = serializar_snapshot_fiscal(snapshot)
    return serializado, SNAPSHOT_VERSION, calcular_hash_snapshot(serializado)


def _factura(ambiente=None, json_texto=None, version=1, hash_texto=None,
             ruta_pdf_relativa=None, ruta_pdf_absoluta=None):
    if json_texto is None and ambiente is not None:
        json_texto, version, hash_texto = _snapshot_valido_persistido(ambiente)
    return {
        "snapshot_fiscal_json": json_texto,
        "snapshot_version": version if json_texto else None,
        "snapshot_hash": hash_texto if json_texto else None,
        "ruta_pdf_relativa": ruta_pdf_relativa,
        "ruta_pdf_absoluta": ruta_pdf_absoluta,
    }


class ValidarRutaPdfRelativaTest(unittest.TestCase):
    # 1) snapshot Homologacion + ruta relativa Homologacion -> OK
    def test_relativa_homologacion_ok(self):
        ruta = validar_ruta_pdf_relativa(RELATIVA_H, AMBIENTE_H)
        self.assertEqual(ruta.parts[:2], ("Homologacion", "facturas"))

    # 2) snapshot Produccion + ruta relativa Produccion -> OK estructural
    def test_relativa_produccion_ok(self):
        ruta = validar_ruta_pdf_relativa(RELATIVA_P, AMBIENTE_P)
        self.assertEqual(ruta.parts[:2], ("Produccion", "facturas"))

    # 3) snapshot H + ruta relativa P -> bloquea
    def test_relativa_produccion_con_ambiente_homologacion_bloquea(self):
        with self.assertRaises(RutaPdfFiscalInvalidaError):
            validar_ruta_pdf_relativa(RELATIVA_P, AMBIENTE_H)

    # 4) snapshot P + ruta relativa H -> bloquea
    def test_relativa_homologacion_con_ambiente_produccion_bloquea(self):
        with self.assertRaises(RutaPdfFiscalInvalidaError):
            validar_ruta_pdf_relativa(RELATIVA_H, AMBIENTE_P)

    # 5) traversal -> bloquea
    def test_relativa_con_traversal_bloquea(self):
        with self.assertRaises(RutaPdfFiscalInvalidaError):
            validar_ruta_pdf_relativa(r"Homologacion\..\facturas\x.pdf", AMBIENTE_H)

    # 6) ruta relativa absoluta -> bloquea
    def test_relativa_absoluta_bloquea(self):
        with self.assertRaises(RutaPdfFiscalInvalidaError):
            validar_ruta_pdf_relativa(r"C:\Homologacion\facturas\x.pdf", AMBIENTE_H)

    def test_relativa_vacia_bloquea(self):
        with self.assertRaises(RutaPdfFiscalInvalidaError):
            validar_ruta_pdf_relativa("", AMBIENTE_H)

    def test_relativa_sin_extension_pdf_bloquea(self):
        with self.assertRaises(RutaPdfFiscalInvalidaError):
            validar_ruta_pdf_relativa(r"Homologacion\facturas\x.txt", AMBIENTE_H)


class ValidarRutaPdfAbsolutaTest(unittest.TestCase):
    def test_absoluta_dentro_de_bucket_homologacion_ok(self):
        ruta = validar_ruta_pdf_absoluta(
            r"C:\Raiz\Homologacion\facturas\x.pdf", AMBIENTE_H
        )
        self.assertEqual(ruta.name, "x.pdf")

    # 9) ruta absoluta persistida de ambiente contrario -> bloquea
    def test_absoluta_de_ambiente_contrario_bloquea(self):
        with self.assertRaises(RutaPdfFiscalInvalidaError):
            validar_ruta_pdf_absoluta(r"C:\Raiz\Produccion\facturas\x.pdf", AMBIENTE_H)

    def test_absoluta_relativa_bloquea(self):
        with self.assertRaises(RutaPdfFiscalInvalidaError):
            validar_ruta_pdf_absoluta(r"Homologacion\facturas\x.pdf", AMBIENTE_H)


class ConstruirRutasPdfPersistiblesTest(unittest.TestCase):
    def test_construye_relativa_y_absoluta_dentro_del_bucket(self):
        generada = r"C:\FM_Master_Certificados\ClienteX\Homologacion\facturas\x.pdf"
        relativa, absoluta = construir_rutas_pdf_persistibles(
            CARPETA_CONFIGURADA, AMBIENTE_H, generada
        )
        self.assertEqual(relativa, r"Homologacion\facturas\x.pdf")
        self.assertEqual(absoluta, generada)

    def test_pdf_generado_fuera_de_carpeta_canonica_bloquea(self):
        generada = r"C:\Otra_Carpeta\Homologacion\facturas\x.pdf"
        with self.assertRaises(RutaPdfFiscalInvalidaError):
            construir_rutas_pdf_persistibles(CARPETA_CONFIGURADA, AMBIENTE_H, generada)


class ReconstruirRutaPdfRelativaTest(unittest.TestCase):
    # 8) raiz configurada cambia -> misma ruta relativa/nombre bajo nueva raiz
    def test_reconstruye_bajo_nueva_raiz_conservando_nombre(self):
        raiz_vieja = r"C:\FM_Master_Certificados\ClienteX"
        raiz_nueva = r"D:\Nueva_Ubicacion\ClienteX"

        ruta_vieja = reconstruir_ruta_pdf_relativa(raiz_vieja, AMBIENTE_H, RELATIVA_H)
        ruta_nueva = reconstruir_ruta_pdf_relativa(raiz_nueva, AMBIENTE_H, RELATIVA_H)

        self.assertEqual(ruta_vieja.name, ruta_nueva.name)
        self.assertEqual(Path(str(ruta_vieja)), Path(raiz_vieja) / "Homologacion" / "facturas" / ruta_vieja.name)
        self.assertEqual(Path(str(ruta_nueva)), Path(raiz_nueva) / "Homologacion" / "facturas" / ruta_nueva.name)
        self.assertNotEqual(ruta_vieja, ruta_nueva)

    def test_reconstruir_con_bucket_contrario_bloquea(self):
        with self.assertRaises(RutaPdfFiscalInvalidaError):
            reconstruir_ruta_pdf_relativa(CARPETA_CONFIGURADA, AMBIENTE_H, RELATIVA_P)


class ResolverRutaPdfDocumentalTest(unittest.TestCase):
    NOMBRE_LEGACY = "Cliente_Factura_A_00002-00000010.pdf"

    # 7) snapshot corrupto + ruta persistida -> bloquea
    def test_snapshot_corrupto_bloquea_aunque_haya_ruta_persistida(self):
        factura = _factura(
            json_texto="{esto no es json valido",
            version=1,
            hash_texto="0" * 64,
            ruta_pdf_relativa=RELATIVA_H,
        )
        with self.assertRaises(RutaPdfFiscalInvalidaError):
            resolver_ruta_pdf_documental(factura, CARPETA_CONFIGURADA, self.NOMBRE_LEGACY)

    # 17) snapshot v1 historico sin rutas -> reconstruccion canonica 3B.2
    def test_snapshot_sin_rutas_persistidas_usa_reconstruccion_canonica(self):
        factura = _factura(ambiente=AMBIENTE_H)
        resuelta = resolver_ruta_pdf_documental(factura, CARPETA_CONFIGURADA, self.NOMBRE_LEGACY)
        self.assertFalse(resuelta.persistida)
        self.assertTrue(resuelta.snapshot)
        self.assertEqual(
            resuelta.ruta,
            Path(CARPETA_CONFIGURADA) / "Homologacion" / "facturas" / self.NOMBRE_LEGACY,
        )

    # 1) snapshot H + ruta relativa H persistida -> se usa tal cual (persistida=True)
    def test_snapshot_homologacion_con_ruta_relativa_homologacion_persistida(self):
        factura = _factura(ambiente=AMBIENTE_H, ruta_pdf_relativa=RELATIVA_H)
        resuelta = resolver_ruta_pdf_documental(factura, CARPETA_CONFIGURADA, self.NOMBRE_LEGACY)
        self.assertTrue(resuelta.persistida)
        self.assertTrue(resuelta.snapshot)
        self.assertEqual(resuelta.ruta.name, Path(RELATIVA_H).name)

    # 3) snapshot H + ruta relativa P persistida -> bloquea
    def test_snapshot_homologacion_con_ruta_relativa_produccion_bloquea(self):
        factura = _factura(ambiente=AMBIENTE_H, ruta_pdf_relativa=RELATIVA_P)
        with self.assertRaises(RutaPdfFiscalInvalidaError):
            resolver_ruta_pdf_documental(factura, CARPETA_CONFIGURADA, self.NOMBRE_LEGACY)

    # 4) snapshot P + ruta relativa H persistida -> bloquea
    def test_snapshot_produccion_con_ruta_relativa_homologacion_bloquea(self):
        factura = _factura(ambiente=AMBIENTE_P, ruta_pdf_relativa=RELATIVA_H)
        with self.assertRaises(RutaPdfFiscalInvalidaError):
            resolver_ruta_pdf_documental(factura, CARPETA_CONFIGURADA, self.NOMBRE_LEGACY)

    # 9) ruta absoluta persistida de ambiente contrario -> bloquea
    def test_snapshot_homologacion_con_ruta_absoluta_produccion_bloquea(self):
        factura = _factura(
            ambiente=AMBIENTE_H,
            ruta_pdf_absoluta=r"C:\FM_Master_Certificados\ClienteX\Produccion\facturas\x.pdf",
        )
        with self.assertRaises(RutaPdfFiscalInvalidaError):
            resolver_ruta_pdf_documental(factura, CARPETA_CONFIGURADA, self.NOMBRE_LEGACY)

    # 10) ruta relativa persistida manda sobre nombre recalculado desde cliente mutable
    def test_ruta_relativa_persistida_prevalece_sobre_nombre_legacy_recalculado(self):
        nombre_persistido = "Cliente_Original_Factura_A_00002-00000010.pdf"
        relativa = f"Homologacion\\facturas\\{nombre_persistido}"
        factura = _factura(ambiente=AMBIENTE_H, ruta_pdf_relativa=relativa)

        nombre_recalculado_tras_cambio_de_cliente = "Cliente_Renombrado_Factura_A_00002-00000010.pdf"
        resuelta = resolver_ruta_pdf_documental(
            factura, CARPETA_CONFIGURADA, nombre_recalculado_tras_cambio_de_cliente
        )
        self.assertEqual(resuelta.ruta.name, nombre_persistido)
        self.assertNotEqual(resuelta.ruta.name, nombre_recalculado_tras_cambio_de_cliente)

    # 18) legacy sin snapshot/rutas -> mantiene compatibilidad
    def test_legacy_sin_snapshot_ni_rutas_usa_carpeta_configurada(self):
        factura = _factura()
        resuelta = resolver_ruta_pdf_documental(factura, CARPETA_CONFIGURADA, self.NOMBRE_LEGACY)
        self.assertFalse(resuelta.persistida)
        self.assertFalse(resuelta.snapshot)
        self.assertEqual(resuelta.ruta, Path(CARPETA_CONFIGURADA) / self.NOMBRE_LEGACY)

    # 19) legacy con ruta absoluta persistida -> uso conservador
    def test_legacy_con_ruta_absoluta_persistida_se_usa_conservadoramente(self):
        absoluta = r"C:\FM_Master_Certificados\ClienteX\ClienteX_Factura_C_00001-00000005.pdf"
        factura = _factura(ruta_pdf_absoluta=absoluta)
        resuelta = resolver_ruta_pdf_documental(factura, CARPETA_CONFIGURADA, self.NOMBRE_LEGACY)
        self.assertTrue(resuelta.persistida)
        self.assertFalse(resuelta.snapshot)
        self.assertEqual(str(resuelta.ruta), absoluta)

    # 22) la reconstruccion canonica nunca sale del bucket de su ambiente
    def test_reconstruccion_canonica_siempre_dentro_del_bucket_del_ambiente(self):
        resuelta_h = resolver_ruta_pdf_documental(
            _factura(ambiente=AMBIENTE_H), CARPETA_CONFIGURADA, self.NOMBRE_LEGACY
        )
        resuelta_p = resolver_ruta_pdf_documental(
            _factura(ambiente=AMBIENTE_P), CARPETA_CONFIGURADA, self.NOMBRE_LEGACY
        )
        self.assertIn("Homologacion", resuelta_h.ruta.parts)
        self.assertIn("Produccion", resuelta_p.ruta.parts)
        self.assertNotEqual(resuelta_h.ruta, resuelta_p.ruta)

    # 24) rutas no se incorporan al snapshot fiscal (no mutan el dict del snapshot)
    def test_resolver_no_muta_snapshot_fiscal_json_de_la_factura(self):
        factura = _factura(ambiente=AMBIENTE_H, ruta_pdf_relativa=RELATIVA_H)
        json_antes = factura["snapshot_fiscal_json"]
        resolver_ruta_pdf_documental(factura, CARPETA_CONFIGURADA, self.NOMBRE_LEGACY)
        self.assertEqual(factura["snapshot_fiscal_json"], json_antes)


if __name__ == "__main__":
    unittest.main()
