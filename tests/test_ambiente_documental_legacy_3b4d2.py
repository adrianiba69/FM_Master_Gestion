"""POST-E2E 3B.4D.2: una factura legacy de ambiente historico no demostrado no se presenta como H ni P.

Sin DB real ni red: canvas falso para inspeccionar el texto del PDF, mocks de ResumenService
y urlopen bloqueado.
"""

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from services.arca.pdf_fiscal_service import PDFFiscalService
from tests import test_ambiente_arca
from tests._cierre_contexto_helper import construir_snapshot_cierre_para_test
from views.facturas_electronicas import FacturasElectronicasFrame, SnapshotFiscalCorruptoError

H, P = "HOMOLOGACION", "PRODUCCION"
DESCONOCIDO = PDFFiscalService.AMBIENTE_DESCONOCIDO
TEXTO_DESCONOCIDO = "Desconocido / histórico"
MARCA_H = "HOMOLOGACION - SIN VALIDEZ FISCAL"
FOOTER_H = "Documento generado localmente para pruebas de homologacion"
CanvasFalso = test_ambiente_arca.PdfLeyendaAmbienteTest._CanvasFalso


class EmisorVivo(tuple):
    """Emisor fiscal cuyo ambiente vivo (indice 9) no debe leerse en la ruta legacy."""

    def __getitem__(self, indice):
        if indice == 9:
            raise AssertionError("se leyo el ambiente vivo del emisor (indice 9)")
        return super().__getitem__(indice)


def emisor_vivo(ambiente):
    return (
        30, "Emisor SRL", "Emisor", "20206871629", "Responsable Inscripto", "Factura C", 5, 1, "",
        ambiente, "Domicilio 1", "123", "20200101", "c.crt", "k.key", "C:/f", 1,
    )


def cliente_fila():
    return (20, "", "Cliente SA", "", "", "Calle 1", "Ciudad", "", "", "20222222221", "Responsable Inscripto", "", "", "")


def factura_legacy(**extra):
    base = {
        "factura_id": 7, "resumen_id": 10, "importe_total": 100.0, "vencimiento": "20260901",
        "snapshot_fiscal_json": None, "snapshot_version": None, "snapshot_hash": None,
        "ruta_pdf_relativa": None, "ruta_pdf_absoluta": None, "ambiente_arca": None,
        "punto_venta_raw": "5", "numero_factura_raw": "00005-00000123", "punto_venta_num": 5,
        "tipo_comprobante_num": 11, "numero_comprobante_num": 123,
        "tipo_documento_receptor": 80, "documento_receptor": 20222222221,
    }
    base.update(extra)
    return base


def factura_con_snapshot(ambiente):
    resultado = construir_snapshot_cierre_para_test(ambiente=ambiente)
    return {
        "factura_id": 8, "snapshot_fiscal_json": resultado["snapshot_json"],
        "snapshot_version": resultado["snapshot_version"], "snapshot_hash": resultado["snapshot_hash"],
        "ruta_pdf_relativa": None, "ruta_pdf_absoluta": None, "ambiente_arca": ambiente,
    }


VALORES_FILA = ("17/08/2026", "Cliente SA", "Factura C", "00005", "00000123", "$ 100,00", "86330766550000")


class Base3B4D2(unittest.TestCase):
    def setUp(self):
        self.frame = object.__new__(FacturasElectronicasFrame)
        resumen = SimpleNamespace(conceptos=[], total=100.0)
        parches = (
            patch("views.facturas_electronicas.ResumenService.obtener", return_value=resumen),
            patch("views.facturas_electronicas.ResumenService.obtener_cliente", return_value=cliente_fila()),
            patch("urllib.request.urlopen", side_effect=AssertionError("red real")),
        )
        for parche in parches:
            parche.start()
            self.addCleanup(parche.stop)

    def datos_pdf(self, factura, emisor):
        return self.frame._construir_datos_pdf_para_regeneracion(
            factura=factura, valores_fila=VALORES_FILA, emisor_fiscal=emisor, carpeta_facturas="C:/f",
            cliente_id=20, tipo_factura="Factura C", codigo_factura="00005-00000123",
        )

    @staticmethod
    def renderizar(datos_pdf):
        """Genera el PDF con canvas falso; devuelve (textos, subject, qr_service_mock)."""
        canvas_falso = CanvasFalso()
        with tempfile.TemporaryDirectory() as carpeta, patch(
            "services.arca.pdf_fiscal_service.canvas.Canvas", side_effect=canvas_falso.asignar_ruta
        ), patch("services.arca.pdf_fiscal_service.QrFiscalService") as qr, patch.object(
            PDFFiscalService, "_dibujar_qr_fiscal", return_value=True
        ):
            qr.return_value.construir_qr_completo.return_value = ("https://x/fe/qr/?p=abc", None)
            resultado = PDFFiscalService.generar_factura_c(
                ruta_destino=str(Path(carpeta) / "f.pdf"),
                datos_emisor=datos_pdf["datos_emisor"],
                datos_receptor=datos_pdf["datos_receptor"],
                datos_comprobante=datos_pdf["datos_comprobante"],
            )
        assert resultado["ok"], resultado
        return canvas_falso.textos, canvas_falso.subject, qr.return_value.construir_qr_completo


class LegacyDesconocidoTest(Base3B4D2):
    def test_a_b_legacy_null_no_se_presenta_como_p_ni_como_h_segun_el_emisor_vivo(self):
        for ambiente_vivo in ("Producción", "PRODUCCION", "Homologación", "HOMOLOGACION"):
            with self.subTest(emisor_vivo=ambiente_vivo):
                datos = self.datos_pdf(factura_legacy(), emisor_vivo(ambiente_vivo))
                self.assertEqual(datos["datos_comprobante"]["ambiente"], DESCONOCIDO)
                textos, subject, _ = self.renderizar(datos)
                self.assertNotIn(MARCA_H, textos)
                self.assertFalse(any(FOOTER_H in t for t in textos))
                self.assertNotIn("Ambiente: PRODUCCION", textos)
                self.assertNotIn("PRODUCCION", textos)
                self.assertNotIn("HOMOLOGACION", textos)
                self.assertNotIn("Homologacion", subject)

    def test_c_indicacion_inequivoca_de_ambiente_desconocido(self):
        for ambiente_vivo in ("Producción", "Homologación"):
            with self.subTest(emisor_vivo=ambiente_vivo):
                textos, subject, _ = self.renderizar(self.datos_pdf(factura_legacy(), emisor_vivo(ambiente_vivo)))
                self.assertIn(TEXTO_DESCONOCIDO, textos)
                self.assertIn(f"Ambiente: {TEXTO_DESCONOCIDO}", textos)
                self.assertTrue(any("Ambiente fiscal original no demostrado" in t for t in textos))
                self.assertEqual(subject, "Factura C - Ambiente desconocido")

    def test_d_no_se_usa_el_ambiente_vivo_del_emisor(self):
        # EmisorVivo lanza AssertionError si se lee el indice 9.
        for ambiente_vivo in ("Producción", "Homologación", "", "QA"):
            with self.subTest(emisor_vivo=ambiente_vivo):
                datos = self.datos_pdf(factura_legacy(), EmisorVivo(emisor_vivo(ambiente_vivo)))
                self.assertEqual(datos["datos_comprobante"]["ambiente"], DESCONOCIDO)

    def test_ambiente_persistido_no_canonico_sigue_siendo_desconocido(self):
        for valor in ("", "QA", "Producción", "produccion", 0):
            with self.subTest(valor=valor):
                datos = self.datos_pdf(factura_legacy(ambiente_arca=valor), emisor_vivo("Producción"))
                self.assertEqual(datos["datos_comprobante"]["ambiente"], DESCONOCIDO)

    def test_legacy_con_ambiente_persistido_canonico_lo_conserva(self):
        for ambiente in (H, P):
            with self.subTest(ambiente=ambiente):
                opuesto = emisor_vivo("Homologación" if ambiente == P else "Producción")
                datos = self.datos_pdf(factura_legacy(ambiente_arca=ambiente), opuesto)
                self.assertEqual(datos["datos_comprobante"]["ambiente"], ambiente)

    def test_j_qr_se_suprime_con_ambiente_desconocido_y_no_depende_del_emisor_vivo(self):
        for ambiente_vivo in ("Producción", "Homologación"):
            with self.subTest(emisor_vivo=ambiente_vivo):
                _, _, construir_qr = self.renderizar(self.datos_pdf(factura_legacy(), emisor_vivo(ambiente_vivo)))
                construir_qr.assert_not_called()

    def test_qr_se_conserva_cuando_el_ambiente_es_demostrable(self):
        _, _, qr_legacy = self.renderizar(self.datos_pdf(factura_legacy(ambiente_arca=P), emisor_vivo("Homologación")))
        qr_legacy.assert_called_once()
        for ambiente in (H, P):
            with self.subTest(snapshot=ambiente):
                _, _, qr = self.renderizar(self.datos_pdf(factura_con_snapshot(ambiente), emisor_vivo("Producción")))
                qr.assert_called_once()


class FacturaModernaTest(Base3B4D2):
    def test_e_f_snapshot_conserva_su_ambiente_aunque_el_emisor_vivo_diga_otro(self):
        casos = ((H, "Producción"), (P, "Homologación"))
        for ambiente, vivo in casos:
            with self.subTest(snapshot=ambiente):
                datos = self.datos_pdf(factura_con_snapshot(ambiente), emisor_vivo(vivo))
                self.assertEqual(datos["datos_comprobante"]["ambiente"], ambiente)
                textos, subject, _ = self.renderizar(datos)
                self.assertNotIn(TEXTO_DESCONOCIDO, textos)
                if ambiente == H:
                    self.assertIn(MARCA_H, textos)
                    self.assertEqual(subject, "Factura A - Homologacion")
                else:
                    self.assertNotIn(MARCA_H, textos)
                    self.assertFalse(any(FOOTER_H in t for t in textos))
                    self.assertEqual(subject, "Factura A")

    def test_g_snapshot_corrupto_sigue_bloqueando(self):
        for vivo in ("Producción", "Homologación"):
            with self.subTest(emisor_vivo=vivo):
                factura = factura_con_snapshot(H)
                factura["snapshot_hash"] = "0" * 64
                with self.assertRaises(SnapshotFiscalCorruptoError):
                    self.datos_pdf(factura, emisor_vivo(vivo))
                factura = factura_con_snapshot(P)
                factura["snapshot_fiscal_json"] = "{mal"
                with self.assertRaises(SnapshotFiscalCorruptoError):
                    self.datos_pdf(factura, emisor_vivo(vivo))


class RutasTest(Base3B4D2):
    def test_h_legacy_desconocido_no_elige_ruta_produccion_por_el_emisor_vivo(self):
        carpeta = r"C:\raiz\facturas_neutral"
        for vivo in ("Producción", "Homologación"):
            with self.subTest(emisor_vivo=vivo):
                destino = self.frame._resolver_carpeta_facturas_canonica(factura_legacy(), carpeta)
                self.assertEqual(destino, Path(carpeta))
                self.assertNotIn("produccion", str(destino).lower())
                self.assertNotIn("homologacion", str(destino).lower())

    def test_h_regeneracion_legacy_desconocida_genera_y_persiste_sin_bucket_de_ambiente(self):
        with tempfile.TemporaryDirectory() as raiz:
            estandar = Path(self.frame._resolver_carpeta_facturas_canonica(factura_legacy(), raiz)) / "legacy.pdf"
            factura = factura_legacy()
            generar = MagicMock(return_value={"ok": True, "ruta_pdf": str(estandar)})
            with patch("views.facturas_electronicas.PDFFiscalService.generar_factura_c", generar), patch(
                "views.facturas_electronicas.FacturaArcaService.actualizar_ruta_pdf"
            ) as actualizar:
                ruta, regenerado, advertencia = self.frame._regenerar_pdf_fiscal_factura(
                    factura=factura, valores_fila=VALORES_FILA, emisor_fiscal=emisor_vivo("Producción"),
                    carpeta_facturas=raiz, ruta_pdf_estandar=str(estandar), ruta_pdf_resuelta=str(estandar),
                    cliente_id=20, tipo_factura="Factura C", codigo_factura="00005-00000123",
                    forzar_regeneracion=True, forzar_reemplazo_estandar=True,
                )
        self.assertTrue(regenerado)
        self.assertIsNone(advertencia)
        enviado = generar.call_args.kwargs
        self.assertEqual(enviado["datos_comprobante"]["ambiente"], DESCONOCIDO)
        self.assertEqual(Path(enviado["ruta_destino"]), estandar)
        self.assertNotIn("produccion", enviado["ruta_destino"].lower())
        # Legacy: no se inventa clave relativa de ambiente.
        self.assertIsNone(actualizar.call_args.args[1])

    def test_i_rutas_modernas_h_p_siguen_separadas(self):
        raiz = r"C:\raiz"
        for ambiente, bucket in ((H, "Homologacion"), (P, "Produccion")):
            with self.subTest(ambiente=ambiente):
                destino = self.frame._resolver_carpeta_facturas_canonica(factura_con_snapshot(ambiente), raiz)
                self.assertEqual(Path(destino), Path(raiz) / bucket / "facturas")


class PdfServiceMarcadorTest(unittest.TestCase):
    def test_solo_el_marcador_explicito_cuenta_como_desconocido(self):
        es = PDFFiscalService._es_ambiente_desconocido
        self.assertTrue(es({"ambiente": DESCONOCIDO}))
        self.assertTrue(es({"ambiente": " desconocido "}))
        for valor in (H, P, "", None, "QA"):
            self.assertFalse(es({"ambiente": valor}))
        self.assertFalse(es({}))
        self.assertFalse(es(None))
        self.assertFalse(PDFFiscalService._es_ambiente_produccion({"ambiente": DESCONOCIDO}))


if __name__ == "__main__":
    unittest.main()
