"""Tests de integracion de POST-E2E 3B.3B: regeneracion de PDF fiscal desde
views.facturas_electronicas y resolucion documental (ambiguedad/legacy) desde
views.resumenes. Se instancian los frames sin Tk real (object.__new__) porque
los metodos bajo prueba no dependen de widgets, solo de logica pura + mocks.

CERO DB real. CERO filesystem real salvo un directorio temporal descartable
para probar la deteccion de ambiguedad de PDFs historicos. CERO ARCA.
"""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tests._cierre_contexto_helper import construir_snapshot_cierre_para_test
from views.facturas_electronicas import FacturasElectronicasFrame
from views.resumenes import ResumenesFrame


def _snapshot_persistido(ambiente="HOMOLOGACION"):
    resultado = construir_snapshot_cierre_para_test(ambiente=ambiente)
    return resultado["snapshot_json"], resultado["snapshot_version"], resultado["snapshot_hash"]


class RegeneracionPdfPersistenciaVistaTest(unittest.TestCase):
    """views.facturas_electronicas.FacturasElectronicasFrame._regenerar_pdf_fiscal_factura"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.carpeta_facturas = self._tmp.name
        self.ruta_estandar = str(Path(self.carpeta_facturas) / "Homologacion" / "facturas" / "x.pdf")

    def _frame(self):
        return object.__new__(FacturasElectronicasFrame)

    def _factura(self):
        json_texto, version, hash_texto = _snapshot_persistido("HOMOLOGACION")
        return {
            "factura_id": 99,
            "snapshot_fiscal_json": json_texto,
            "snapshot_version": version,
            "snapshot_hash": hash_texto,
            "ruta_pdf_relativa": None,
            "ruta_pdf_absoluta": None,
        }

    @staticmethod
    def _datos_pdf_dummy():
        return {"datos_emisor": {}, "datos_receptor": {}, "datos_comprobante": {}}

    # 14) regeneracion exitosa -> actualiza/persiste ruta
    def test_regeneracion_exitosa_persiste_ruta(self):
        frame = self._frame()
        factura = self._factura()
        with (
            patch.object(frame, "_construir_datos_pdf_para_regeneracion", return_value=self._datos_pdf_dummy()),
            patch("views.facturas_electronicas.PDFFiscalService.generar_factura_c",
                  return_value={"ok": True, "ruta_pdf": self.ruta_estandar}),
            patch("views.facturas_electronicas.FacturaArcaService.actualizar_ruta_pdf") as actualizar,
        ):
            ruta, regenerado, advertencia = frame._regenerar_pdf_fiscal_factura(
                factura=factura,
                valores_fila=(),
                emisor_fiscal=(),
                carpeta_facturas=self.carpeta_facturas,
                ruta_pdf_estandar=self.ruta_estandar,
                ruta_pdf_resuelta=self.ruta_estandar,
                cliente_id=10,
                tipo_factura="Factura A",
                codigo_factura="00002-00000010",
                forzar_regeneracion=True,
                forzar_reemplazo_estandar=True,
            )

        self.assertTrue(regenerado)
        self.assertIsNone(advertencia)
        actualizar.assert_called_once()
        self.assertEqual(actualizar.call_args.args[0], 99)
        self.assertEqual(factura["ruta_pdf_relativa"], r"Homologacion\facturas\x.pdf")

    # 15) regeneracion con fallo de persistencia -> PDF sigue valido + advertencia
    def test_regeneracion_con_fallo_de_persistencia_no_pierde_el_pdf(self):
        frame = self._frame()
        factura = self._factura()
        with (
            patch.object(frame, "_construir_datos_pdf_para_regeneracion", return_value=self._datos_pdf_dummy()),
            patch("views.facturas_electronicas.PDFFiscalService.generar_factura_c",
                  return_value={"ok": True, "ruta_pdf": self.ruta_estandar}),
            patch("views.facturas_electronicas.FacturaArcaService.actualizar_ruta_pdf",
                  side_effect=RuntimeError("db bloqueada")),
        ):
            ruta, regenerado, advertencia = frame._regenerar_pdf_fiscal_factura(
                factura=factura,
                valores_fila=(),
                emisor_fiscal=(),
                carpeta_facturas=self.carpeta_facturas,
                ruta_pdf_estandar=self.ruta_estandar,
                ruta_pdf_resuelta=self.ruta_estandar,
                cliente_id=10,
                tipo_factura="Factura A",
                codigo_factura="00002-00000010",
                forzar_regeneracion=True,
                forzar_reemplazo_estandar=True,
            )

        self.assertTrue(regenerado)
        self.assertEqual(str(ruta), self.ruta_estandar)
        self.assertIsNotNone(advertencia)
        self.assertIn("regener", advertencia.lower())

    # 16) factura recuperada con rutas NULL -> puede regenerar y persistir
    def test_factura_recuperada_con_rutas_null_puede_regenerar_y_persistir(self):
        frame = self._frame()
        factura = self._factura()
        self.assertIsNone(factura["ruta_pdf_relativa"])
        self.assertIsNone(factura["ruta_pdf_absoluta"])
        with (
            patch.object(frame, "_construir_datos_pdf_para_regeneracion", return_value=self._datos_pdf_dummy()),
            patch("views.facturas_electronicas.PDFFiscalService.generar_factura_c",
                  return_value={"ok": True, "ruta_pdf": self.ruta_estandar}),
            patch("views.facturas_electronicas.FacturaArcaService.actualizar_ruta_pdf") as actualizar,
        ):
            _, regenerado, advertencia = frame._regenerar_pdf_fiscal_factura(
                factura=factura,
                valores_fila=(),
                emisor_fiscal=(),
                carpeta_facturas=self.carpeta_facturas,
                ruta_pdf_estandar=self.ruta_estandar,
                ruta_pdf_resuelta=self.ruta_estandar,
                cliente_id=10,
                tipo_factura="Factura A",
                codigo_factura="00002-00000010",
                forzar_regeneracion=True,
                forzar_reemplazo_estandar=True,
            )

        self.assertTrue(regenerado)
        self.assertIsNone(advertencia)
        actualizar.assert_called_once()
        self.assertIsNotNone(factura["ruta_pdf_relativa"])


class AmbiguedadHistoricaResumenesTest(unittest.TestCase):
    """views.resumenes.ResumenesFrame._resolver_ruta_pdf_factura_existente"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.carpeta_facturas = self._tmp.name

    def _frame(self):
        return object.__new__(ResumenesFrame)

    def _emisor_fiscal(self):
        # indice 15 = carpeta_facturas, segun EmisorFiscalService.listar/obtener
        return (1, "Fiscal", "Fantasia", "20111111117", "RI", "Factura A", "2", 1, "", "Homologación",
                "", "", "", "cert.crt", "clave.key", self.carpeta_facturas, 1)

    # 20) multiples candidatos historicos -> NO elegir por mtime; bloquear ambiguedad
    def test_multiples_candidatos_historicos_bloquea_ambiguedad(self):
        carpeta = Path(self.carpeta_facturas)
        (carpeta / "ClienteX_Factura_A_00002-00000010.pdf").write_bytes(b"%PDF-1.4 viejo")
        (carpeta / "ClienteX_Renombrado_Factura_A_00002-00000010.pdf").write_bytes(b"%PDF-1.4 nuevo")

        frame = self._frame()
        resultado = frame._resolver_ruta_pdf_factura_existente(
            cliente_id=10,
            tipo_factura="Factura A",
            codigo_factura="00002-00000010",
            emisor_fiscal=self._emisor_fiscal(),
            factura=None,
        )
        self.assertEqual(resultado, "")

    # 21) un solo candidato historico compatible -> puede resolverse
    def test_un_solo_candidato_historico_se_resuelve(self):
        carpeta = Path(self.carpeta_facturas)
        unico = carpeta / "ClienteX_Factura_A_00002-00000010.pdf"
        unico.write_bytes(b"%PDF-1.4 unico")

        frame = self._frame()
        with patch("views.resumenes.nombre_factura_pdf", return_value="Nombre_Estandar_No_Coincide.pdf"):
            resultado = frame._resolver_ruta_pdf_factura_existente(
                cliente_id=10,
                tipo_factura="Factura A",
                codigo_factura="00002-00000010",
                emisor_fiscal=self._emisor_fiscal(),
                factura=None,
            )
        self.assertEqual(resultado, str(unico))


if __name__ == "__main__":
    unittest.main()
