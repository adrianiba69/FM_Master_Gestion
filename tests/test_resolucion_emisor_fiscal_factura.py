import unittest
from unittest.mock import patch

from services.arca.snapshot_fiscal_pdf_adapter import (
    DecisionRegeneracion,
    MODO_CORRUPTO,
    MODO_SNAPSHOT,
)
from services.emisor_fiscal_service import EmisorFiscalService
from services.emisor_service import EmisorService
from views.facturas_electronicas import (
    FacturasElectronicasFrame,
    ResolucionEmisorFiscalError,
    SnapshotFiscalCorruptoError,
)


CUIT_A = "30-71217861-9"
CUIT_B = "20-26385888-4"


def _emisor_interno(id_, cuit=CUIT_A, emisor_fiscal_id=None):
    return (
        id_,
        f"Interno {id_}",
        "Titular",
        f"Nombre {id_}",
        cuit,
        "Responsable Inscripto",
        "2",
        "Factura A",
        0,
        "",
        "",
        "",
        "",
        1,
        "",
        "",
        "",
        "Homologación",
        "Configurado",
        emisor_fiscal_id,
    )


def _emisor_fiscal(id_, cuit=CUIT_A):
    return (
        id_,
        f"Fiscal {id_}",
        f"Fantasia {id_}",
        cuit,
        "Responsable Inscripto",
        "Factura A",
        "2",
        1,
        "",
        "Homologación",
        "",
        "",
        "",
        "cert.crt",
        "clave.key",
        f"C:/Facturas/{id_}",
        1,
    )


class ResolucionEmisorFiscalFacturaTest(unittest.TestCase):

    def test_ids_coinciden_y_vinculo_correcto_resuelve_fiscal_3(self):
        interno = _emisor_interno(3, CUIT_A, emisor_fiscal_id=3)
        fiscal = _emisor_fiscal(3, CUIT_A)
        with (
            patch.object(EmisorService, "obtener", return_value=interno),
            patch.object(EmisorFiscalService, "obtener", return_value=fiscal) as obtener_fiscal,
            patch.object(EmisorFiscalService, "listar") as listar_fiscales,
        ):
            resultado = EmisorFiscalService.resolver_desde_emisor_facturacion(3, cuit_snapshot=CUIT_A)

        self.assertTrue(resultado["ok"])
        self.assertEqual(resultado["emisor_fiscal"][0], 3)
        self.assertEqual(resultado["codigo"], "VINCULO_EXPLICITO")
        obtener_fiscal.assert_called_once_with(3)
        listar_fiscales.assert_not_called()

    def test_colision_numerica_resuelve_vinculo_2_y_nunca_fiscal_1(self):
        interno = _emisor_interno(1, CUIT_B, emisor_fiscal_id=2)
        fiscal_correcto = _emisor_fiscal(2, CUIT_B)
        with (
            patch.object(EmisorService, "obtener", return_value=interno),
            patch.object(EmisorFiscalService, "obtener", return_value=fiscal_correcto) as obtener_fiscal,
            patch.object(EmisorFiscalService, "listar") as listar_fiscales,
        ):
            resultado = EmisorFiscalService.resolver_desde_emisor_facturacion(1)

        self.assertTrue(resultado["ok"])
        self.assertEqual(resultado["emisor_fiscal"][0], 2)
        obtener_fiscal.assert_called_once_with(2)
        listar_fiscales.assert_not_called()

    def test_vinculo_explicito_que_contradice_snapshot_bloquea_sin_fallback(self):
        interno = _emisor_interno(1, "", emisor_fiscal_id=2)
        fiscal_vinculado = _emisor_fiscal(2, CUIT_B)
        with (
            patch.object(EmisorService, "obtener", return_value=interno),
            patch.object(EmisorFiscalService, "obtener", return_value=fiscal_vinculado) as obtener_fiscal,
            patch.object(EmisorFiscalService, "listar") as listar_fiscales,
        ):
            resultado = EmisorFiscalService.resolver_desde_emisor_facturacion(1, cuit_snapshot=CUIT_A)

        self.assertFalse(resultado["ok"])
        self.assertIsNone(resultado["emisor_fiscal"])
        self.assertEqual(resultado["codigo"], "CUIT_SNAPSHOT_INCONSISTENTE")
        obtener_fiscal.assert_called_once_with(2)
        listar_fiscales.assert_not_called()

    def test_sin_vinculo_y_cuit_unico_permite_fallback(self):
        interno = _emisor_interno(4, CUIT_A, emisor_fiscal_id=None)
        fiscal = _emisor_fiscal(7, CUIT_A)
        with (
            patch.object(EmisorService, "obtener", return_value=interno),
            patch.object(EmisorFiscalService, "obtener") as obtener_fiscal,
            patch.object(EmisorFiscalService, "listar", return_value=[fiscal]),
        ):
            resultado = EmisorFiscalService.resolver_desde_emisor_facturacion(4)

        self.assertTrue(resultado["ok"])
        self.assertEqual(resultado["emisor_fiscal"][0], 7)
        self.assertEqual(resultado["codigo"], "FALLBACK_CUIT_UNICO")
        obtener_fiscal.assert_not_called()

    def test_sin_vinculo_y_cuit_ambiguo_bloquea(self):
        interno = _emisor_interno(4, CUIT_A, emisor_fiscal_id=None)
        with (
            patch.object(EmisorService, "obtener", return_value=interno),
            patch.object(
                EmisorFiscalService,
                "listar",
                return_value=[_emisor_fiscal(7, CUIT_A), _emisor_fiscal(8, CUIT_A)],
            ),
        ):
            resultado = EmisorFiscalService.resolver_desde_emisor_facturacion(4)

        self.assertFalse(resultado["ok"])
        self.assertIsNone(resultado["emisor_fiscal"])
        self.assertEqual(resultado["codigo"], "EMISOR_FISCAL_AMBIGUO")

    def test_sin_vinculo_y_sin_coincidencia_no_resuelve(self):
        interno = _emisor_interno(4, CUIT_A, emisor_fiscal_id=None)
        with (
            patch.object(EmisorService, "obtener", return_value=interno),
            patch.object(EmisorFiscalService, "listar", return_value=[_emisor_fiscal(7, CUIT_B)]),
        ):
            resultado = EmisorFiscalService.resolver_desde_emisor_facturacion(4)

        self.assertFalse(resultado["ok"])
        self.assertIsNone(resultado["emisor_fiscal"])
        self.assertEqual(resultado["codigo"], "EMISOR_FISCAL_NO_ENCONTRADO")

    def test_legacy_sin_snapshot_con_vinculo_correcto_sigue_funcionando(self):
        interno = _emisor_interno(3, CUIT_A, emisor_fiscal_id=3)
        fiscal = _emisor_fiscal(3, CUIT_A)
        with (
            patch.object(EmisorService, "obtener", return_value=interno),
            patch.object(EmisorFiscalService, "obtener", return_value=fiscal),
        ):
            resultado = EmisorFiscalService.resolver_desde_emisor_facturacion(3)

        self.assertTrue(resultado["ok"])
        self.assertEqual(resultado["emisor_fiscal"], fiscal)

    def test_mutacion_posterior_que_contradice_snapshot_bloquea(self):
        interno_mutado = _emisor_interno(3, CUIT_B, emisor_fiscal_id=3)
        fiscal_actual = _emisor_fiscal(3, CUIT_B)
        with (
            patch.object(EmisorService, "obtener", return_value=interno_mutado),
            patch.object(EmisorFiscalService, "obtener", return_value=fiscal_actual) as obtener_fiscal,
            patch.object(EmisorFiscalService, "listar") as listar_fiscales,
        ):
            resultado = EmisorFiscalService.resolver_desde_emisor_facturacion(3, cuit_snapshot=CUIT_A)

        self.assertFalse(resultado["ok"])
        self.assertIsNone(resultado["emisor_fiscal"])
        self.assertEqual(resultado["codigo"], "CUIT_INTERNO_CONTRADICE_SNAPSHOT")
        obtener_fiscal.assert_not_called()
        listar_fiscales.assert_not_called()

    def test_cuit_interno_presente_pero_invalido_bloquea(self):
        interno = _emisor_interno(3, "CUIT INVALIDO", emisor_fiscal_id=3)
        with (
            patch.object(EmisorService, "obtener", return_value=interno),
            patch.object(EmisorFiscalService, "obtener") as obtener_fiscal,
        ):
            resultado = EmisorFiscalService.resolver_desde_emisor_facturacion(3)

        self.assertFalse(resultado["ok"])
        self.assertEqual(resultado["codigo"], "CUIT_INTERNO_INVALIDO")
        obtener_fiscal.assert_not_called()

    def test_cuit_fiscal_presente_pero_invalido_bloquea(self):
        interno = _emisor_interno(3, CUIT_A, emisor_fiscal_id=3)
        fiscal = _emisor_fiscal(3, "CUIT INVALIDO")
        with (
            patch.object(EmisorService, "obtener", return_value=interno),
            patch.object(EmisorFiscalService, "obtener", return_value=fiscal),
        ):
            resultado = EmisorFiscalService.resolver_desde_emisor_facturacion(3)

        self.assertFalse(resultado["ok"])
        self.assertEqual(resultado["codigo"], "CUIT_FISCAL_INVALIDO")


class IntegracionResolucionEmisorFiscalVistaTest(unittest.TestCase):

    def test_snapshot_valido_aporta_cuit_historico_al_resolver(self):
        factura = {
            "emisor_id": 3,
            "snapshot_fiscal_json": "snapshot-valido",
            "snapshot_version": 1,
            "snapshot_hash": "hash-valido",
        }
        fiscal = _emisor_fiscal(3, CUIT_A)
        decision = DecisionRegeneracion(
            modo=MODO_SNAPSHOT,
            snapshot={"emisor": {"cuit": CUIT_A, "razon_social": "Emisor histórico"}, "ambiente": "HOMOLOGACION"},
        )
        frame = object.__new__(FacturasElectronicasFrame)

        with (
            patch("views.facturas_electronicas.resolver_modo_regeneracion", return_value=decision),
            patch.object(
                EmisorFiscalService,
                "resolver_desde_emisor_facturacion",
                return_value={"ok": True, "emisor_fiscal": fiscal, "codigo": "VINCULO_EXPLICITO", "mensaje": ""},
            ) as resolver,
        ):
            resultado = frame._resolver_emisor_fiscal_desde_factura(factura)

        self.assertEqual(resultado, fiscal)
        resolver.assert_called_once_with(3, cuit_snapshot=CUIT_A)

    def test_snapshot_corrupto_bloquea_antes_de_resolver_emisor(self):
        factura = {
            "emisor_id": 3,
            "snapshot_fiscal_json": "{mal",
            "snapshot_version": 1,
            "snapshot_hash": "hash-invalido",
        }
        decision = DecisionRegeneracion(
            modo=MODO_CORRUPTO,
            codigo="JSON_INVALIDO",
            errores=("snapshot invalido",),
        )
        frame = object.__new__(FacturasElectronicasFrame)

        with (
            patch("views.facturas_electronicas.resolver_modo_regeneracion", return_value=decision),
            patch.object(EmisorFiscalService, "resolver_desde_emisor_facturacion") as resolver,
        ):
            with self.assertRaises(SnapshotFiscalCorruptoError):
                frame._resolver_emisor_fiscal_desde_factura(factura)

        resolver.assert_not_called()

    def test_inconsistencia_del_resolver_se_propaga_y_no_devuelve_emisor(self):
        factura = {
            "emisor_id": 3,
            "snapshot_fiscal_json": None,
            "snapshot_version": None,
            "snapshot_hash": None,
        }
        frame = object.__new__(FacturasElectronicasFrame)

        with patch.object(
            EmisorFiscalService,
            "resolver_desde_emisor_facturacion",
            return_value={
                "ok": False,
                "emisor_fiscal": None,
                "codigo": "EMISOR_FISCAL_AMBIGUO",
                "mensaje": "Hay mas de un emisor fiscal con el mismo CUIT.",
            },
        ):
            with self.assertRaises(ResolucionEmisorFiscalError) as contexto:
                frame._resolver_emisor_fiscal_desde_factura(factura)

        self.assertEqual(contexto.exception.codigo, "EMISOR_FISCAL_AMBIGUO")


if __name__ == "__main__":
    unittest.main()
