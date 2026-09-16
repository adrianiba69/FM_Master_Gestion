import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch, Mock

from services.arca import ambiente_arca
from services.arca.wsaa_login_service import WSAALoginService
from services.arca.wsfe_service import WSFEService
from services.arca.homologacion_service import HomologacionService
from services.arca.pdf_fiscal_service import PDFFiscalService


class NormalizacionAmbienteTest(unittest.TestCase):

    def test_homologacion_variantes(self):
        for valor in ("Homologación", "HOMOLOGACION", "homologacion", "  Homologación  "):
            self.assertEqual(ambiente_arca.normalizar_ambiente_arca(valor), ambiente_arca.AMBIENTE_HOMOLOGACION)

    def test_produccion_variantes(self):
        for valor in ("Producción", "PRODUCCION", "produccion", "  Producción  "):
            self.assertEqual(ambiente_arca.normalizar_ambiente_arca(valor), ambiente_arca.AMBIENTE_PRODUCCION)

    def test_valor_desconocido_error_seguro(self):
        for invalido in ("", None, "otra_cosa", "Homolog", "PRODX"):
            with self.assertRaises(ambiente_arca.AmbienteArcaInvalidoError):
                ambiente_arca.normalizar_ambiente_arca(invalido)


class EndpointsPorAmbienteTest(unittest.TestCase):

    def test_homologacion_selecciona_url_wsaa_homologacion(self):
        self.assertEqual(
            ambiente_arca.resolver_endpoint_wsaa(ambiente_arca.AMBIENTE_HOMOLOGACION),
            WSAALoginService.WSAA_HOMOLOGACION_URL,
        )

    def test_homologacion_selecciona_url_wsfe_homologacion(self):
        self.assertEqual(
            ambiente_arca.resolver_endpoint_wsfe(ambiente_arca.AMBIENTE_HOMOLOGACION),
            WSFEService.WSFE_HOMOLOGACION_URL,
        )

    def test_produccion_selecciona_url_wsaa_productiva(self):
        url = ambiente_arca.resolver_endpoint_wsaa(ambiente_arca.AMBIENTE_PRODUCCION)
        self.assertEqual(url, WSAALoginService.WSAA_PRODUCCION_URL)
        self.assertNotEqual(url, WSAALoginService.WSAA_HOMOLOGACION_URL)

    def test_produccion_selecciona_url_wsfe_productiva(self):
        url = ambiente_arca.resolver_endpoint_wsfe(ambiente_arca.AMBIENTE_PRODUCCION)
        self.assertEqual(url, WSFEService.WSFE_PRODUCCION_URL)
        self.assertNotEqual(url, WSFEService.WSFE_HOMOLOGACION_URL)

    def test_cache_homologacion_y_produccion_tienen_prefijos_distintos(self):
        prefijo_homo = ambiente_arca.prefijo_cache_wsaa(ambiente_arca.AMBIENTE_HOMOLOGACION)
        prefijo_prod = ambiente_arca.prefijo_cache_wsaa(ambiente_arca.AMBIENTE_PRODUCCION)
        self.assertNotEqual(prefijo_homo, prefijo_prod)

        ruta_homo = WSAALoginService._ruta_cache_disco("C:/trabajo/tra.xml", "abc123", prefijo_homo)
        ruta_prod = WSAALoginService._ruta_cache_disco("C:/trabajo/tra.xml", "abc123", prefijo_prod)
        self.assertNotEqual(str(ruta_homo), str(ruta_prod))
        self.assertIn("homologacion", str(ruta_homo))
        self.assertIn("produccion", str(ruta_prod))

    def test_cache_key_separa_certificado_clave_y_url(self):
        base = WSAALoginService._cache_key("cert-a.crt", "clave-a.key", WSAALoginService.WSAA_HOMOLOGACION_URL)
        self.assertNotEqual(
            base,
            WSAALoginService._cache_key("cert-b.crt", "clave-a.key", WSAALoginService.WSAA_HOMOLOGACION_URL),
        )
        self.assertNotEqual(
            base,
            WSAALoginService._cache_key("cert-a.crt", "clave-b.key", WSAALoginService.WSAA_HOMOLOGACION_URL),
        )
        self.assertNotEqual(
            base,
            WSAALoginService._cache_key("cert-a.crt", "clave-a.key", WSAALoginService.WSAA_PRODUCCION_URL),
        )


class CacheTaDiscoTest(unittest.TestCase):

    @staticmethod
    def _expiration_futura():
        return (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()

    def test_cache_escritura_lectura_y_sin_temporales_residuales(self):
        with tempfile.TemporaryDirectory() as carpeta:
            ruta_tra = str(Path(carpeta) / "tra.xml")
            WSAALoginService._guardar_cache_disco(ruta_tra, "abc123", "TOKEN_TEST_NO_REAL", "SIGN_TEST_NO_REAL", self._expiration_futura())
            ruta_cache = WSAALoginService._ruta_cache_disco(ruta_tra, "abc123")

            self.assertTrue(ruta_cache.is_file())
            datos_json = json.loads(ruta_cache.read_text(encoding="utf-8"))
            self.assertEqual(
                datos_json,
                {"token": "TOKEN_TEST_NO_REAL", "sign": "SIGN_TEST_NO_REAL", "expiration": datos_json["expiration"]},
            )
            self.assertEqual(WSAALoginService._leer_cache_disco(ruta_tra, "abc123")["token"], "TOKEN_TEST_NO_REAL")
            self.assertEqual(list(Path(carpeta).glob("*.tmp")), [])

    def test_cache_replace_sobrescribe_con_json_completo(self):
        with tempfile.TemporaryDirectory() as carpeta:
            ruta_tra = str(Path(carpeta) / "tra.xml")
            WSAALoginService._guardar_cache_disco(ruta_tra, "abc123", "TOKEN_A", "SIGN_A", self._expiration_futura())
            WSAALoginService._guardar_cache_disco(ruta_tra, "abc123", "TOKEN_B", "SIGN_B", self._expiration_futura())
            datos = WSAALoginService._leer_cache_disco(ruta_tra, "abc123")

            self.assertEqual(datos["token"], "TOKEN_B")
            self.assertEqual(datos["sign"], "SIGN_B")
            self.assertNotIn("TOKEN_A", Path(WSAALoginService._ruta_cache_disco(ruta_tra, "abc123")).read_text(encoding="utf-8"))

    def test_cache_atomicidad_no_reemplaza_final_si_replace_falla(self):
        with tempfile.TemporaryDirectory() as carpeta:
            ruta_tra = str(Path(carpeta) / "tra.xml")
            WSAALoginService._guardar_cache_disco(ruta_tra, "abc123", "TOKEN_A", "SIGN_A", self._expiration_futura())
            ruta_cache = WSAALoginService._ruta_cache_disco(ruta_tra, "abc123")
            original = ruta_cache.read_text(encoding="utf-8")

            with patch("services.arca.wsaa_login_service.os.replace", side_effect=OSError("replace")):
                WSAALoginService._guardar_cache_disco(ruta_tra, "abc123", "TOKEN_B", "SIGN_B", self._expiration_futura())

            self.assertEqual(ruta_cache.read_text(encoding="utf-8"), original)
            self.assertEqual(WSAALoginService._leer_cache_disco(ruta_tra, "abc123")["token"], "TOKEN_A")
            self.assertEqual(list(Path(carpeta).glob("*.tmp")), [])

    def test_cache_proteccion_se_invoca_antes_de_replace(self):
        eventos = []
        replace_real = os.replace
        with tempfile.TemporaryDirectory() as carpeta:
            ruta_tra = str(Path(carpeta) / "tra.xml")

            def proteger(_ruta):
                eventos.append("proteger")
                return True

            def reemplazar(_origen, _destino):
                eventos.append("replace")
                replace_real(_origen, _destino)

            with (
                patch.object(WSAALoginService, "_proteger_cache_disco_best_effort", side_effect=proteger),
                patch("services.arca.wsaa_login_service.os.replace", side_effect=reemplazar),
            ):
                WSAALoginService._guardar_cache_disco(ruta_tra, "abc123", "TOKEN_A", "SIGN_A", self._expiration_futura())

        self.assertGreaterEqual(eventos.count("proteger"), 1)
        self.assertIn("replace", eventos)
        self.assertLess(eventos.index("proteger"), eventos.index("replace"))

    def test_cache_falla_proteccion_no_reemplaza_y_limpia_temporal(self):
        with tempfile.TemporaryDirectory() as carpeta:
            ruta_tra = str(Path(carpeta) / "tra.xml")
            WSAALoginService._guardar_cache_disco(ruta_tra, "abc123", "TOKEN_A", "SIGN_A", self._expiration_futura())
            ruta_cache = WSAALoginService._ruta_cache_disco(ruta_tra, "abc123")
            original = ruta_cache.read_text(encoding="utf-8")

            with patch.object(WSAALoginService, "_proteger_cache_disco_best_effort", return_value=False):
                WSAALoginService._guardar_cache_disco(ruta_tra, "abc123", "TOKEN_B", "SIGN_B", self._expiration_futura())

            self.assertEqual(ruta_cache.read_text(encoding="utf-8"), original)
            self.assertEqual(list(Path(carpeta).glob("*.tmp")), [])

    def test_cache_json_corrupto_se_ignora(self):
        with tempfile.TemporaryDirectory() as carpeta:
            ruta_tra = str(Path(carpeta) / "tra.xml")
            ruta_cache = WSAALoginService._ruta_cache_disco(ruta_tra, "abc123")
            ruta_cache.write_text("{mal", encoding="utf-8")

            self.assertIsNone(WSAALoginService._leer_cache_disco(ruta_tra, "abc123"))


class PropagacionAmbienteEmisionTest(unittest.TestCase):

    class _PreenvioCentinela:
        def __init__(self):
            self.llamadas = 0

        def enviar_una_vez(self, snapshot, enviar_fecae):
            self.llamadas += 1
            from services.arca.preenvio_arca_service import ResultadoPreenvioArca
            return ResultadoPreenvioArca(True, intento_id=1, respuesta=enviar_fecae())

    def _datos_emision(self, ambiente=None):
        datos = dict(
            ruta_certificado="cert.crt",
            ruta_clave="clave.key",
            cuit_emisor="20206871629",
            punto_venta=5,
            tipo_comprobante=11,
            condicion_iva_receptor_id=5,
            concepto=1,
            tipo_documento=80,
            documento_receptor=30712345678,
            importe_total=1210.0,
            importe_neto=1210.0,
            importe_iva=0.0,
            importe_exento=0.0,
            fecha_comprobante="20260816",
            carpeta_trabajo="C:/trabajo",
            alicuotas_iva=[],
            datos_intento={"resumen_id": 10, "cliente_id": 20, "emisor_fiscal_id": 30, "emisor_id": 40},
        )
        if ambiente is not None:
            datos["ambiente"] = ambiente
        return datos

    def test_homologacion_mantiene_flujo_actual(self):
        preenvio = self._PreenvioCentinela()
        solicitar = Mock(return_value={
            "ok": True, "resultado": "A", "cae": "71345678901234",
            "vencimiento_cae": "20260826", "numero_comprobante": 123, "fecha_comprobante": "20260816",
        })
        with (
            patch("services.arca.homologacion_service.WSAAService.guardar_tra", return_value="tra.xml"),
            patch("services.arca.homologacion_service.WSAALoginService.login_homologacion", return_value={"ok": True, "token": "t", "sign": "s"}) as mock_login,
            patch("services.arca.homologacion_service.WSFEService.fe_comp_ultimo_autorizado", return_value={"ok": True, "ultimo_numero": 122}) as mock_ultimo,
            patch(
                "services.arca.homologacion_service.WSFEService.construir_solicitud_cae",
                return_value={
                    "ok": True,
                    "solicitud": {
                        "Cuit": "20206871629",
                        "FeCAEReq": {
                            "FeCabReq": {"PtoVta": 5, "CbteTipo": 11},
                            "FeDetReq": {"FECAEDetRequest": [{
                                "CbteDesde": 123, "CbteFch": "20260816", "Concepto": 1,
                                "DocTipo": 80, "DocNro": 30712345678, "CondicionIVAReceptorId": 5,
                                "ImpTotal": 1210.0, "ImpNeto": 1210.0, "ImpIVA": 0.0,
                                "ImpOpEx": 0.0, "ImpTotConc": 0.0, "ImpTrib": 0.0,
                                "MonId": "PES", "MonCotiz": 1.0,
                            }]},
                        },
                    },
                },
            ),
        ):
            resultado = HomologacionService.emitir_comprobante_prueba(
                **self._datos_emision(),
                preenvio_service=preenvio,
                solicitar_cae=solicitar,
            )

        self.assertTrue(resultado["ok"])
        self.assertEqual(preenvio.llamadas, 1)
        mock_login.assert_called_once()
        self.assertEqual(mock_login.call_args.kwargs["ambiente"], ambiente_arca.AMBIENTE_HOMOLOGACION)
        self.assertEqual(mock_ultimo.call_args.kwargs["url"], WSFEService.WSFE_HOMOLOGACION_URL)
        solicitar.assert_called_once()
        self.assertEqual(solicitar.call_args.kwargs["url"], WSFEService.WSFE_HOMOLOGACION_URL)

    def test_operacion_completa_mantiene_mismo_ambiente(self):
        # Reutiliza el mismo mock de login para verificar que WSAA y WSFE
        # reciben exactamente el mismo ambiente/URL resuelto en una operación.
        preenvio = self._PreenvioCentinela()
        solicitar = Mock(return_value={"ok": True, "resultado": "A", "cae": "1", "vencimiento_cae": "20260826"})
        with (
            patch("services.arca.homologacion_service.WSAAService.guardar_tra", return_value="tra.xml"),
            patch("services.arca.homologacion_service.WSAALoginService.login_homologacion", return_value={"ok": True, "token": "t", "sign": "s"}) as mock_login,
            patch("services.arca.homologacion_service.WSFEService.fe_comp_ultimo_autorizado", return_value={"ok": True, "ultimo_numero": 1}) as mock_ultimo,
            patch(
                "services.arca.homologacion_service.WSFEService.construir_solicitud_cae",
                return_value={
                    "ok": True,
                    "solicitud": {
                        "Cuit": "20206871629",
                        "FeCAEReq": {
                            "FeCabReq": {"PtoVta": 5, "CbteTipo": 11},
                            "FeDetReq": {"FECAEDetRequest": [{
                                "CbteDesde": 2, "CbteFch": "20260816", "Concepto": 1,
                                "DocTipo": 80, "DocNro": 30712345678, "CondicionIVAReceptorId": 5,
                                "ImpTotal": 1210.0, "ImpNeto": 1210.0, "ImpIVA": 0.0,
                                "ImpOpEx": 0.0, "ImpTotConc": 0.0, "ImpTrib": 0.0,
                                "MonId": "PES", "MonCotiz": 1.0,
                            }]},
                        },
                    },
                },
            ),
        ):
            HomologacionService.emitir_comprobante_prueba(
                **self._datos_emision(ambiente="Homologación"),
                preenvio_service=preenvio,
                solicitar_cae=solicitar,
            )

        ambiente_login = mock_login.call_args.kwargs["ambiente"]
        url_ultimo = mock_ultimo.call_args.kwargs["url"]
        url_solicitar = solicitar.call_args.kwargs["url"]
        self.assertEqual(ambiente_login, ambiente_arca.AMBIENTE_HOMOLOGACION)
        self.assertEqual(url_ultimo, ambiente_arca.resolver_endpoint_wsfe(ambiente_login))
        self.assertEqual(url_solicitar, ambiente_arca.resolver_endpoint_wsfe(ambiente_login))

    def test_produccion_bloqueada_antes_de_red(self):
        preenvio = self._PreenvioCentinela()
        with (
            patch("services.arca.homologacion_service.WSAAService.guardar_tra") as mock_guardar_tra,
            patch("services.arca.homologacion_service.WSAALoginService.login_homologacion") as mock_login,
            patch("services.arca.homologacion_service.WSFEService.fe_comp_ultimo_autorizado") as mock_ultimo,
            patch("services.arca.homologacion_service.WSFEService.fe_cae_solicitar") as mock_solicitar,
        ):
            resultado = HomologacionService.emitir_comprobante_prueba(
                **self._datos_emision(ambiente=ambiente_arca.AMBIENTE_PRODUCCION),
                preenvio_service=preenvio,
            )

        self.assertFalse(resultado["ok"])
        self.assertTrue(any("Producción" in error or "Produccion" in error for error in resultado["errores"]))
        mock_guardar_tra.assert_not_called()
        mock_login.assert_not_called()
        mock_ultimo.assert_not_called()
        mock_solicitar.assert_not_called()
        # El bloqueo no debe crear ningun intento (preenvio ni siquiera se invoca).
        self.assertEqual(preenvio.llamadas, 0)

    def test_consultar_comprobante_emitido_usa_ambiente_recibido(self):
        with (
            patch("services.arca.homologacion_service.WSAAService.guardar_tra", return_value="tra.xml"),
            patch(
                "services.arca.homologacion_service.WSAALoginService.login_homologacion",
                return_value={"ok": True, "token": "t", "sign": "s"},
            ) as mock_login,
            patch(
                "services.arca.homologacion_service.WSFEService.fe_comp_consultar",
                return_value={"ok": True},
            ) as mock_consulta,
        ):
            resultado = HomologacionService.consultar_comprobante_emitido(
                ruta_certificado="cert.crt",
                ruta_clave="clave.key",
                cuit_emisor="20206871629",
                punto_venta=5,
                tipo_comprobante=11,
                numero_comprobante=123,
                carpeta_trabajo="C:/trabajo",
                ambiente=ambiente_arca.AMBIENTE_PRODUCCION,
            )

        self.assertTrue(resultado["ok"])
        self.assertEqual(mock_login.call_args.kwargs["ambiente"], ambiente_arca.AMBIENTE_PRODUCCION)
        self.assertEqual(mock_consulta.call_args.kwargs["url"], WSFEService.WSFE_PRODUCCION_URL)


class PdfLeyendaAmbienteTest(unittest.TestCase):

    class _CanvasFalso:
        def __init__(self):
            self.textos = []

        def saveState(self):
            pass

        def restoreState(self):
            pass

        def translate(self, *_a, **_k):
            pass

        def rotate(self, *_a, **_k):
            pass

        def setFillColor(self, *_a, **_k):
            pass

        def setFont(self, *_a, **_k):
            pass

        def drawCentredString(self, _x, _y, texto):
            self.textos.append(texto)

    def test_homologacion_mantiene_leyenda(self):
        canvas_falso = self._CanvasFalso()
        PDFFiscalService._dibujar_marca_homologacion(canvas_falso, 600, 800, mostrar=True)
        self.assertIn("HOMOLOGACION - SIN VALIDEZ FISCAL", canvas_falso.textos)

    def test_produccion_no_muestra_leyenda(self):
        canvas_falso = self._CanvasFalso()
        PDFFiscalService._dibujar_marca_homologacion(canvas_falso, 600, 800, mostrar=False)
        self.assertEqual(canvas_falso.textos, [])


if __name__ == "__main__":
    unittest.main()
