"""Tests puros del resolver de carpeta fiscal por ambiente (POST-E2E 3B.2).

Modulo bajo prueba: services/arca/carpeta_facturas_resolver.py
CERO DB. CERO filesystem real. CERO ARCA/WSAA/WSFE.
"""

import unittest
from pathlib import Path

from services.arca import ambiente_arca
from services.arca.carpeta_facturas_resolver import (
    CarpetaFacturasNoConfiguradaError,
    resolver_carpeta_facturas_por_ambiente,
)


class ResolverCarpetaFacturasPorAmbienteTest(unittest.TestCase):

    # A) raiz neutral + HOMOLOGACION -> raiz\Homologacion\facturas
    def test_raiz_neutral_homologacion(self):
        resultado = resolver_carpeta_facturas_por_ambiente(
            r"C:\FM_Master_Certificados\ClienteX", ambiente_arca.AMBIENTE_HOMOLOGACION
        )
        self.assertEqual(resultado, Path(r"C:\FM_Master_Certificados\ClienteX\Homologacion\facturas"))

    # B) raiz neutral + PRODUCCION -> raiz\Produccion\facturas
    def test_raiz_neutral_produccion(self):
        resultado = resolver_carpeta_facturas_por_ambiente(
            r"C:\FM_Master_Certificados\ClienteX", ambiente_arca.AMBIENTE_PRODUCCION
        )
        self.assertEqual(resultado, Path(r"C:\FM_Master_Certificados\ClienteX\Produccion\facturas"))

    # C) legacy Homologacion\facturas + HOMOLOGACION -> no duplica segmentos
    def test_legacy_homologacion_facturas_con_homologacion_no_duplica(self):
        configurada = r"C:\FM_Master_Certificados\Publicidad_y_Servicios_SH\Homologacion\facturas"
        resultado = resolver_carpeta_facturas_por_ambiente(configurada, ambiente_arca.AMBIENTE_HOMOLOGACION)
        self.assertEqual(resultado, Path(configurada))
        self.assertNotIn("Homologacion\\facturas\\Homologacion\\facturas", str(resultado))

    # D) legacy Homologacion\facturas + PRODUCCION -> cambia solo el bucket
    def test_legacy_homologacion_facturas_con_produccion_cambia_bucket(self):
        configurada = r"C:\FM_Master_Certificados\Publicidad_y_Servicios_SH\Homologacion\facturas"
        resultado = resolver_carpeta_facturas_por_ambiente(configurada, ambiente_arca.AMBIENTE_PRODUCCION)
        self.assertEqual(
            resultado,
            Path(r"C:\FM_Master_Certificados\Publicidad_y_Servicios_SH\Produccion\facturas"),
        )

    # E) legacy Produccion\facturas + HOMOLOGACION -> cambia solo el bucket
    def test_legacy_produccion_facturas_con_homologacion_cambia_bucket(self):
        configurada = r"C:\FM_Master_Certificados\Publicidad_y_Servicios_SH\Produccion\facturas"
        resultado = resolver_carpeta_facturas_por_ambiente(configurada, ambiente_arca.AMBIENTE_HOMOLOGACION)
        self.assertEqual(
            resultado,
            Path(r"C:\FM_Master_Certificados\Publicidad_y_Servicios_SH\Homologacion\facturas"),
        )

    # F) mismo nombre/PV/numero en H y P -> rutas fisicas distintas
    def test_mismo_nombre_en_ambos_ambientes_produce_rutas_distintas(self):
        configurada = r"C:\FM_Master_Certificados\Publicidad_y_Servicios_SH\Homologacion\facturas"
        nombre_pdf = "COQUETTE_PERFUMERIA_Factura_A_00002-00000010.pdf"

        carpeta_homologacion = resolver_carpeta_facturas_por_ambiente(configurada, ambiente_arca.AMBIENTE_HOMOLOGACION)
        carpeta_produccion = resolver_carpeta_facturas_por_ambiente(configurada, ambiente_arca.AMBIENTE_PRODUCCION)

        ruta_homologacion = carpeta_homologacion / nombre_pdf
        ruta_produccion = carpeta_produccion / nombre_pdf

        self.assertNotEqual(ruta_homologacion, ruta_produccion)
        self.assertEqual(ruta_homologacion.name, ruta_produccion.name)

    # G) case-insensitive: homologacion\FACTURAS reconocido correctamente
    def test_legacy_case_insensitive_reconocido(self):
        configurada = r"C:\FM_Master_Certificados\ClienteY\homologacion\FACTURAS"
        resultado = resolver_carpeta_facturas_por_ambiente(configurada, ambiente_arca.AMBIENTE_PRODUCCION)
        self.assertEqual(resultado, Path(r"C:\FM_Master_Certificados\ClienteY\Produccion\facturas"))

    # H) barra final -> resultado correcto
    def test_barra_final_no_afecta_resultado(self):
        configurada = r"C:\FM_Master_Certificados\Publicidad_y_Servicios_SH\Homologacion\facturas\ "[:-1]
        resultado = resolver_carpeta_facturas_por_ambiente(configurada, ambiente_arca.AMBIENTE_HOMOLOGACION)
        self.assertEqual(
            resultado,
            Path(r"C:\FM_Master_Certificados\Publicidad_y_Servicios_SH\Homologacion\facturas"),
        )

    # I) ambiente invalido -> error seguro, nunca Produccion
    def test_ambiente_invalido_bloquea(self):
        with self.assertRaises(ambiente_arca.AmbienteArcaInvalidoError):
            resolver_carpeta_facturas_por_ambiente(r"C:\FM_Master_Certificados\ClienteX", "TESTING")

    # J) ambiente ausente -> error seguro segun contrato explicito
    def test_ambiente_ausente_bloquea(self):
        with self.assertRaises(ambiente_arca.AmbienteArcaInvalidoError):
            resolver_carpeta_facturas_por_ambiente(r"C:\FM_Master_Certificados\ClienteX", None)
        with self.assertRaises(ambiente_arca.AmbienteArcaInvalidoError):
            resolver_carpeta_facturas_por_ambiente(r"C:\FM_Master_Certificados\ClienteX", "")

    # L) snapshot PRODUCCION + config terminada en Homologacion\facturas -> Produccion\facturas
    def test_snapshot_produccion_con_config_terminada_en_homologacion(self):
        configurada = r"C:\FM_Master_Certificados\Publicidad_y_Servicios_SH\Homologacion\facturas"
        resultado = resolver_carpeta_facturas_por_ambiente(configurada, ambiente_arca.AMBIENTE_PRODUCCION)
        self.assertEqual(
            resultado,
            Path(r"C:\FM_Master_Certificados\Publicidad_y_Servicios_SH\Produccion\facturas"),
        )

    def test_carpeta_no_configurada_bloquea(self):
        with self.assertRaises(CarpetaFacturasNoConfiguradaError):
            resolver_carpeta_facturas_por_ambiente("", ambiente_arca.AMBIENTE_HOMOLOGACION)
        with self.assertRaises(CarpetaFacturasNoConfiguradaError):
            resolver_carpeta_facturas_por_ambiente(None, ambiente_arca.AMBIENTE_HOMOLOGACION)

    def test_acepta_alias_con_tilde_minuscula(self):
        resultado = resolver_carpeta_facturas_por_ambiente(
            r"C:\FM_Master_Certificados\ClienteX", "Producción"
        )
        self.assertEqual(resultado, Path(r"C:\FM_Master_Certificados\ClienteX\Produccion\facturas"))


if __name__ == "__main__":
    unittest.main()
