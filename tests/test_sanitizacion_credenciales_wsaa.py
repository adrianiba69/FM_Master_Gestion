import io
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import Mock, patch

from services.arca.homologacion_service import HomologacionService
from services.arca.preenvio_arca_service import ResultadoPreenvioArca
from services.arca.sanitizacion_arca import sanitizar_estructura_arca
from services.arca.wsaa_login_service import WSAALoginService


TOKEN = "TOKEN_ULTRASECRETO_123"
SIGN = "SIGN_ULTRASECRETO_456"


class PreenvioInmediato:
    def enviar_una_vez_con_contexto(self, snapshot, contexto_fiscal, enviar_fecae):
        return ResultadoPreenvioArca(True, intento_id=77, respuesta=enviar_fecae())


def _contexto_fiscal_base():
    return {
        "tipo": "contexto_fiscal_arca",
        "version": 1,
        "creado_en": "2026-09-15T10:00:00",
        "ambiente": "HOMOLOGACION",
        "emisor": {"emisor_id": 40, "emisor_fiscal_id": 30, "razon_social": "Emisor", "cuit": "20206871629", "punto_venta_num": 5},
        "receptor": {"cliente_id": 20, "razon_social": "Cliente", "documento_visible": "30712345678", "tipo_documento_receptor": 80, "documento_receptor": 30712345678},
        "comprobante": {"fecha": "20260915", "fecha_arca": "20260915", "tipo_comprobante_num": 11, "numero_comprobante_planificado": None},
        "importes": {"total": 1210, "neto": 1210},
        "iva": [],
        "items": [{"descripcion": "Servicio", "subtotal": 1210}],
    }


def _solicitud():
    return {
        "Cuit": "20206871629",
        "FeCAEReq": {
            "FeCabReq": {"PtoVta": 5, "CbteTipo": 11},
            "FeDetReq": {"FECAEDetRequest": [{
                "CbteDesde": 123, "CbteFch": "20260915", "Concepto": 1,
                "DocTipo": 80, "DocNro": 30712345678, "CondicionIVAReceptorId": 5,
                "ImpTotal": 1210.0, "ImpNeto": 1210.0, "ImpIVA": 0.0,
                "ImpOpEx": 0.0, "ImpTotConc": 0.0, "ImpTrib": 0.0,
                "MonId": "PES", "MonCotiz": 1.0,
            }]},
        },
    }


class SanitizacionCredencialesWsaaTest(unittest.TestCase):
    def test_sanitizador_recursivo_elimina_secretos_y_conserva_datos_fiscales(self):
        tecnico = {
            "estado": "ERROR",
            "token": "TOKEN_SECRETO",
            "nivel": {"sign": "SIGN_SECRETO", "lista": [{"password": "PASSWORD_SECRETO"}, {"dato_fiscal": "OK"}]},
        }
        limpio = sanitizar_estructura_arca(tecnico)
        self.assertNotIn("TOKEN_SECRETO", repr(limpio))
        self.assertNotIn("SIGN_SECRETO", repr(limpio))
        self.assertNotIn("PASSWORD_SECRETO", repr(limpio))
        self.assertEqual(limpio["nivel"]["lista"][1]["dato_fiscal"], "OK")
        self.assertIn("token", tecnico)

    def test_emision_no_expone_token_sign_y_wsfe_los_recibe_internamente(self):
        solicitar = Mock(return_value={"ok": True, "resultado": "A", "cae": "71345678901234", "vencimiento_cae": "20260925", "numero_comprobante": 123, "fecha_comprobante": "20260915"})
        with (
            patch("services.arca.homologacion_service.WSAAService.guardar_tra", return_value="tra.xml"),
            patch("services.arca.homologacion_service.WSAALoginService.login_homologacion", return_value={"ok": True, "token": TOKEN, "sign": SIGN}),
            patch("services.arca.homologacion_service.WSFEService.fe_comp_ultimo_autorizado", return_value={"ok": True, "ultimo_numero": 122}) as ultimo,
            patch("services.arca.homologacion_service.WSFEService.construir_solicitud_cae", return_value={"ok": True, "solicitud": _solicitud()}),
        ):
            resultado = HomologacionService.emitir_comprobante_prueba(
                ruta_certificado="cert.crt", ruta_clave="clave.key", cuit_emisor="20206871629",
                punto_venta=5, tipo_comprobante=11, condicion_iva_receptor_id=5,
                concepto=1, tipo_documento=80, documento_receptor=30712345678,
                importe_total=1210.0, importe_neto=1210.0, importe_iva=0.0, importe_exento=0.0,
                fecha_comprobante="20260915", carpeta_trabajo="C:/trabajo", alicuotas_iva=[],
                datos_intento={"resumen_id": 10, "cliente_id": 20, "emisor_fiscal_id": 30, "emisor_id": 40},
                contexto_fiscal_base=_contexto_fiscal_base(), exigir_contexto_fiscal=True,
                preenvio_service=PreenvioInmediato(), solicitar_cae=solicitar,
            )
        self.assertTrue(resultado["ok"])
        self.assertEqual(ultimo.call_args.kwargs["token"], TOKEN)
        self.assertEqual(ultimo.call_args.kwargs["sign"], SIGN)
        self.assertEqual(solicitar.call_args.kwargs["token"], TOKEN)
        self.assertEqual(solicitar.call_args.kwargs["sign"], SIGN)
        self.assertNotIn("token", resultado)
        self.assertNotIn("sign", resultado)
        self.assertNotIn(TOKEN, repr(resultado))
        self.assertNotIn(SIGN, repr(resultado))

    def test_consulta_recibe_credenciales_internamente_sin_exponerlas(self):
        with (
            patch("services.arca.homologacion_service.WSAAService.guardar_tra", return_value="tra.xml"),
            patch("services.arca.homologacion_service.WSAALoginService.login_homologacion", return_value={"ok": True, "token": TOKEN, "sign": SIGN}),
            patch("services.arca.homologacion_service.WSFEService.fe_comp_consultar", return_value={"ok": True}) as consulta,
        ):
            resultado = HomologacionService.consultar_comprobante_emitido(
                "cert.crt", "clave.key", "20206871629", 5, 11, 123, "C:/trabajo"
            )
        self.assertTrue(resultado["ok"])
        self.assertEqual(consulta.call_args.kwargs["token"], TOKEN)
        self.assertEqual(consulta.call_args.kwargs["sign"], SIGN)
        self.assertNotIn(TOKEN, repr(resultado))
        self.assertNotIn(SIGN, repr(resultado))

    def test_error_post_login_no_expone_credenciales(self):
        with (
            patch("services.arca.homologacion_service.WSAAService.guardar_tra", return_value="tra.xml"),
            patch("services.arca.homologacion_service.WSAALoginService.login_homologacion", return_value={"ok": True, "token": TOKEN, "sign": SIGN}),
            patch("services.arca.homologacion_service.WSFEService.fe_comp_ultimo_autorizado", return_value={"ok": False, "errores": [f"fallo {TOKEN}", f"fallo {SIGN}"]}),
        ):
            resultado = HomologacionService.emitir_comprobante_prueba(
                ruta_certificado="cert.crt", ruta_clave="clave.key", cuit_emisor="20206871629",
                punto_venta=5, tipo_comprobante=11, condicion_iva_receptor_id=5,
                concepto=1, tipo_documento=80, documento_receptor=30712345678,
                importe_total=1210.0, importe_neto=1210.0, importe_iva=0.0, importe_exento=0.0,
                fecha_comprobante="20260915", carpeta_trabajo="C:/trabajo", alicuotas_iva=[],
                datos_intento={"resumen_id": 10, "cliente_id": 20, "emisor_fiscal_id": 30, "emisor_id": 40},
                contexto_fiscal_base=_contexto_fiscal_base(), exigir_contexto_fiscal=True,
            )
        self.assertFalse(resultado["ok"])
        self.assertNotIn(TOKEN, repr(resultado))
        self.assertNotIn(SIGN, repr(resultado))

    def test_login_wsaa_no_imprime_token_ni_sign(self):
        class RespuestaFake:
            status = 200

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self):
                inner = (
                    "<loginTicketResponse><credentials>"
                    f"<token>{TOKEN}</token><sign>{SIGN}</sign>"
                    "</credentials><header><expirationTime>2030-01-01T00:00:00Z</expirationTime></header>"
                    "</loginTicketResponse>"
                )
                return f"<Envelope><Body><loginCmsReturn>{inner.replace('<', '&lt;').replace('>', '&gt;')}</loginCmsReturn></Body></Envelope>".encode()

        with tempfile.TemporaryDirectory() as carpeta:
            cms = Path(carpeta) / "tra.cms"
            cms.write_text("-----BEGIN CMS-----\nabc\n-----END CMS-----", encoding="utf-8")
            WSAALoginService._ta_cache.clear()
            salida = io.StringIO()
            with (
                patch("services.arca.wsaa_login_service.CertificadoService.firmar_tra_cms", return_value={"firmado": True, "ruta_cms": str(cms)}),
                patch("services.arca.wsaa_login_service.urllib.request.urlopen", return_value=RespuestaFake()),
                redirect_stdout(salida),
            ):
                resultado = WSAALoginService.login_homologacion(
                    ruta_tra=str(Path(carpeta) / "tra.xml"),
                    ruta_certificado="cert.crt",
                    ruta_clave="clave.key",
                )
        self.assertTrue(resultado["ok"])
        self.assertEqual(resultado["token"], TOKEN)
        self.assertEqual(resultado["sign"], SIGN)
        self.assertNotIn(TOKEN, salida.getvalue())
        self.assertNotIn(SIGN, salida.getvalue())


if __name__ == "__main__":
    unittest.main()