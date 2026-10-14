import unittest
from copy import deepcopy
from decimal import Decimal
from unittest.mock import patch

from services.arca.contexto_fiscal_service import ContextoFiscalService
from services.arca.homologacion_service import HomologacionService
from services.arca.preenvio_arca_service import ResultadoPreenvioArca
from services.arca.wsfe_service import WSFEService


class PreenvioCapturador:

    def __init__(self):
        self.snapshots = []

    def enviar_una_vez(self, snapshot, enviar_fecae):
        self.snapshots.append(snapshot)
        return ResultadoPreenvioArca(True, intento_id=77, respuesta=enviar_fecae())


class PreenvioCapturadorConContexto:

    def __init__(self):
        self.snapshots = []
        self.contextos = []
        self.enviar_una_vez_llamado = False

    def enviar_una_vez(self, snapshot, enviar_fecae):
        self.enviar_una_vez_llamado = True
        self.snapshots.append(snapshot)
        return ResultadoPreenvioArca(True, intento_id=77, respuesta=enviar_fecae())

    def enviar_una_vez_con_contexto(self, snapshot, contexto_fiscal, enviar_fecae):
        self.snapshots.append(snapshot)
        self.contextos.append(contexto_fiscal)
        return ResultadoPreenvioArca(True, intento_id=77, respuesta=enviar_fecae())


class HomologacionPreenvioIntegrationTest(unittest.TestCase):

    def _emitir(self, tipo_comprobante):
        preenvio = PreenvioCapturador()
        solicitar = unittest.mock.Mock(return_value={
            "ok": True,
            "resultado": "A",
            "cae": "71345678901234",
            "vencimiento_cae": "20260826",
            "numero_comprobante": 123,
            "fecha_comprobante": "20260816",
        })
        with (
            patch("services.arca.homologacion_service.WSAAService.guardar_tra", return_value="tra.xml"),
            patch("services.arca.homologacion_service.WSAALoginService.login_homologacion", return_value={"ok": True, "token": "t", "sign": "s"}),
            patch("services.arca.homologacion_service.WSFEService.fe_comp_ultimo_autorizado", return_value={"ok": True, "ultimo_numero": 122}),
            patch(
                "services.arca.homologacion_service.WSFEService.construir_solicitud_cae",
                return_value={
                    "ok": True,
                    "solicitud": {
                        "Cuit": "20206871629",
                        "FeCAEReq": {
                            "FeCabReq": {"PtoVta": 5, "CbteTipo": tipo_comprobante},
                            "FeDetReq": {
                                "FECAEDetRequest": [{
                                    "CbteDesde": 123, "CbteFch": "20260816", "Concepto": 1,
                                    "DocTipo": 80, "DocNro": 30712345678,
                                    "CondicionIVAReceptorId": 1 if tipo_comprobante == 1 else 5,
                                    "ImpTotal": 12100.0, "ImpNeto": 10000.0 if tipo_comprobante == 1 else 12100.0,
                                    "ImpIVA": 2100.0 if tipo_comprobante == 1 else 0.0,
                                    "ImpOpEx": 0.0, "ImpTotConc": 0.0, "ImpTrib": 0.0,
                                    "MonId": "PES", "MonCotiz": 1.0,
                                }]
                            },
                        },
                    },
                },
            ),
        ):
            resultado = HomologacionService.emitir_comprobante_prueba(
                ruta_certificado="cert.crt",
                ruta_clave="clave.key",
                cuit_emisor="20206871629",
                punto_venta=5,
                tipo_comprobante=tipo_comprobante,
                condicion_iva_receptor_id=1 if tipo_comprobante == 1 else 5,
                concepto=1,
                tipo_documento=80,
                documento_receptor=30712345678,
                importe_total=12100.0,
                importe_neto=10000.0 if tipo_comprobante == 1 else 12100.0,
                importe_iva=2100.0 if tipo_comprobante == 1 else 0.0,
                importe_exento=0.0,
                fecha_comprobante="20260816",
                carpeta_trabajo="C:/trabajo",
                alicuotas_iva=[] if tipo_comprobante == 11 else [{"id": 5, "base_imponible": 10000.0, "importe": 2100.0}],
                datos_intento={"resumen_id": 10, "cliente_id": 20, "emisor_fiscal_id": 30, "emisor_id": 40},
                preenvio_service=preenvio,
                solicitar_cae=solicitar,
            )
        return resultado, preenvio, solicitar

    def _contexto_fiscal_base(self, tipo_comprobante):
        return {
            "tipo": "contexto_fiscal_arca",
            "version": 1,
            "creado_en": "2026-08-16T10:00:00",
            "ambiente": "HOMOLOGACION",
            "emisor": {"emisor_id": 40, "emisor_fiscal_id": 30, "razon_social": "Emisor SA", "cuit": "20206871629", "punto_venta_num": 5},
            "receptor": {"cliente_id": 20, "razon_social": "Cliente SA", "documento_visible": "30712345678", "tipo_documento_receptor": 80, "documento_receptor": 30712345678},
            "comprobante": {
                "fecha": "2026-08-16", "fecha_arca": "20260816",
                "punto_venta_num": 5,
                "tipo_comprobante_num": tipo_comprobante,
                "numero_comprobante_planificado": None,
                "numero_textual_planificado": None,
            },
            "importes": {"total": Decimal("12100.00"), "neto": Decimal("12100.00")},
            "iva": [] if tipo_comprobante == 11 else [{"id": 5, "base_imponible": Decimal("10000.00"), "importe": Decimal("2100.00")}],
            "items": [{"descripcion": "Servicio", "subtotal": Decimal("12100.00")}],
        }

    def _emitir_con_contexto(self, tipo_comprobante, contexto_fiscal_base=None):
        preenvio = PreenvioCapturadorConContexto()
        solicitar = unittest.mock.Mock(return_value={
            "ok": True,
            "resultado": "A",
            "cae": "71345678901234",
            "vencimiento_cae": "20260826",
            "numero_comprobante": 123,
            "fecha_comprobante": "20260816",
        })
        if contexto_fiscal_base is None:
            contexto_fiscal_base = self._contexto_fiscal_base(tipo_comprobante)
        with (
            patch("services.arca.homologacion_service.WSAAService.guardar_tra", return_value="tra.xml"),
            patch("services.arca.homologacion_service.WSAALoginService.login_homologacion", return_value={"ok": True, "token": "t", "sign": "s"}),
            patch("services.arca.homologacion_service.WSFEService.fe_comp_ultimo_autorizado", return_value={"ok": True, "ultimo_numero": 122}),
            patch(
                "services.arca.homologacion_service.WSFEService.construir_solicitud_cae",
                return_value={
                    "ok": True,
                    "solicitud": {
                        "Cuit": "20206871629",
                        "FeCAEReq": {
                            "FeCabReq": {"PtoVta": 5, "CbteTipo": tipo_comprobante},
                            "FeDetReq": {
                                "FECAEDetRequest": [{
                                    "CbteDesde": 123, "CbteFch": "20260816", "Concepto": 1,
                                    "DocTipo": 80, "DocNro": 30712345678,
                                    "CondicionIVAReceptorId": 1 if tipo_comprobante == 1 else 5,
                                    "ImpTotal": 12100.0, "ImpNeto": 10000.0 if tipo_comprobante == 1 else 12100.0,
                                    "ImpIVA": 2100.0 if tipo_comprobante == 1 else 0.0,
                                    "ImpOpEx": 0.0, "ImpTotConc": 0.0, "ImpTrib": 0.0,
                                    "MonId": "PES", "MonCotiz": 1.0,
                                }]
                            },
                        },
                    },
                },
            ),
        ):
            resultado = HomologacionService.emitir_comprobante_prueba(
                ruta_certificado="cert.crt",
                ruta_clave="clave.key",
                cuit_emisor="20206871629",
                punto_venta=5,
                tipo_comprobante=tipo_comprobante,
                condicion_iva_receptor_id=1 if tipo_comprobante == 1 else 5,
                concepto=1,
                tipo_documento=80,
                documento_receptor=30712345678,
                importe_total=12100.0,
                importe_neto=10000.0 if tipo_comprobante == 1 else 12100.0,
                importe_iva=2100.0 if tipo_comprobante == 1 else 0.0,
                importe_exento=0.0,
                fecha_comprobante="20260816",
                carpeta_trabajo="C:/trabajo",
                alicuotas_iva=[] if tipo_comprobante == 11 else [{"id": 5, "base_imponible": 10000.0, "importe": 2100.0}],
                datos_intento={"resumen_id": 10, "cliente_id": 20, "emisor_fiscal_id": 30, "emisor_id": 40},
                contexto_fiscal_base=contexto_fiscal_base,
                exigir_contexto_fiscal=True,
                preenvio_service=preenvio,
                solicitar_cae=solicitar,
            )
        return resultado, preenvio, solicitar

    def _emitir_servicios(self):
        preenvio = PreenvioCapturadorConContexto()
        solicitar = unittest.mock.Mock(return_value={
            "ok": True,
            "resultado": "A",
            "cae": "71345678901234",
            "vencimiento_cae": "20261110",
            "numero_comprobante": 123,
            "fecha_comprobante": "20261014",
        })
        contexto = self._contexto_fiscal_base(11)
        contexto["comprobante"].update({
            "concepto": 2,
            "concepto_descripcion": "Servicios",
            "periodo_servicio_desde": "2026-10-01",
            "periodo_servicio_hasta": "2026-10-31",
            "vencimiento_pago": "2026-11-10",
        })
        contexto_original = deepcopy(contexto)
        with (
            patch("services.arca.homologacion_service.WSAAService.guardar_tra", return_value="tra.xml"),
            patch("services.arca.homologacion_service.WSAALoginService.login_homologacion", return_value={"ok": True, "token": "t", "sign": "s"}),
            patch("services.arca.homologacion_service.WSFEService.fe_comp_ultimo_autorizado", return_value={"ok": True, "ultimo_numero": 122}),
            patch.object(WSFEService, "construir_solicitud_cae", wraps=WSFEService.construir_solicitud_cae) as construir,
        ):
            resultado = HomologacionService.emitir_comprobante_prueba(
                ruta_certificado="cert.crt",
                ruta_clave="clave.key",
                cuit_emisor="20206871629",
                punto_venta=5,
                tipo_comprobante=11,
                condicion_iva_receptor_id=5,
                concepto=2,
                tipo_documento=80,
                documento_receptor=30712345678,
                importe_total=12100.0,
                importe_neto=12100.0,
                importe_iva=0.0,
                importe_exento=0.0,
                fecha_comprobante="20261014",
                carpeta_trabajo="C:/trabajo",
                alicuotas_iva=[],
                fecha_servicio_desde="20261001",
                fecha_servicio_hasta="20261031",
                fecha_vencimiento_pago="20261110",
                datos_intento={"resumen_id": 10, "cliente_id": 20, "emisor_fiscal_id": 30, "emisor_id": 40},
                contexto_fiscal_base=contexto,
                exigir_contexto_fiscal=True,
                preenvio_service=preenvio,
                solicitar_cae=solicitar,
            )
        return resultado, preenvio, solicitar, construir, contexto, contexto_original

    def test_factura_a_y_c_pasan_por_preenvio_con_numero_planificado(self):
        for tipo_comprobante in (1, 11):
            with self.subTest(tipo_comprobante=tipo_comprobante):
                resultado, preenvio, solicitar = self._emitir(tipo_comprobante)
                self.assertTrue(resultado["ok"])
                self.assertEqual(resultado["intento_id"], 77)
                self.assertEqual(len(preenvio.snapshots), 1)
                self.assertEqual(preenvio.snapshots[0].tipo_comprobante, tipo_comprobante)
                self.assertEqual(preenvio.snapshots[0].numero_planificado, 123)
                solicitar.assert_called_once()

    def test_numero_planificado_se_incorpora_al_contexto_en_homologacion(self):
        for tipo_comprobante in (1, 11):
            with self.subTest(tipo_comprobante=tipo_comprobante):
                resultado, preenvio, solicitar = self._emitir_con_contexto(tipo_comprobante)
                self.assertTrue(resultado["ok"])
                self.assertFalse(preenvio.enviar_una_vez_llamado)
                self.assertEqual(len(preenvio.contextos), 1)
                comprobante = preenvio.contextos[0]["comprobante"]
                self.assertEqual(comprobante["numero_comprobante_planificado"], 123)
                self.assertEqual(comprobante["numero_textual_planificado"], "00005-00000123")
                solicitar.assert_called_once()

    def test_contexto_fiscal_invalido_bloquea_antes_de_construir_solicitud(self):
        contexto_invalido = self._contexto_fiscal_base(11)
        contexto_invalido["version"] = 99
        resultado, preenvio, solicitar = self._emitir_con_contexto(11, contexto_fiscal_base=contexto_invalido)
        self.assertFalse(resultado["ok"])
        solicitar.assert_not_called()
        self.assertEqual(preenvio.contextos, [])
        self.assertEqual(preenvio.snapshots, [])

    def test_ruta_real_exige_contexto_fiscal_base_antes_de_wsaa(self):
        preenvio = PreenvioCapturadorConContexto()
        solicitar = unittest.mock.Mock()
        with (
            patch("services.arca.homologacion_service.WSAAService.guardar_tra") as guardar_tra,
            patch("services.arca.homologacion_service.WSAALoginService.login_homologacion") as login,
            patch("services.arca.homologacion_service.WSFEService.fe_comp_ultimo_autorizado") as ultimo,
        ):
            resultado = HomologacionService.emitir_comprobante_prueba(
                ruta_certificado="cert.crt",
                ruta_clave="clave.key",
                cuit_emisor="20206871629",
                punto_venta=5,
                tipo_comprobante=11,
                condicion_iva_receptor_id=5,
                concepto=1,
                tipo_documento=80,
                documento_receptor=30712345678,
                importe_total=12100.0,
                importe_neto=12100.0,
                importe_iva=0.0,
                importe_exento=0.0,
                fecha_comprobante="20260816",
                carpeta_trabajo="C:/trabajo",
                alicuotas_iva=[],
                datos_intento={"resumen_id": 10, "cliente_id": 20, "emisor_fiscal_id": 30, "emisor_id": 40},
                exigir_contexto_fiscal=True,
                preenvio_service=preenvio,
                solicitar_cae=solicitar,
            )

        self.assertFalse(resultado["ok"])
        self.assertIn("Contexto fiscal base obligatorio", resultado["errores"][0])
        guardar_tra.assert_not_called()
        login.assert_not_called()
        ultimo.assert_not_called()
        solicitar.assert_not_called()
        self.assertEqual(preenvio.contextos, [])

    def test_servicios_transmite_fechas_hasta_solicitud_wsfe_sin_alterar_otros_datos(self):
        resultado, preenvio, solicitar, construir, contexto, contexto_original = self._emitir_servicios()

        self.assertTrue(resultado["ok"], resultado["errores"])
        construir.assert_called_once()
        argumentos_construccion = construir.call_args.kwargs
        self.assertEqual(argumentos_construccion["concepto"], 2)
        self.assertEqual(argumentos_construccion["fecha_servicio_desde"], "20261001")
        self.assertEqual(argumentos_construccion["fecha_servicio_hasta"], "20261031")
        self.assertEqual(argumentos_construccion["fecha_vencimiento_pago"], "20261110")

        solicitar.assert_called_once()
        detalle = solicitar.call_args.kwargs["solicitud"]["FeCAEReq"]["FeDetReq"]["FECAEDetRequest"][0]
        self.assertEqual(detalle, {
            "Concepto": 2,
            "DocTipo": 80,
            "DocNro": 30712345678,
            "CbteDesde": 123,
            "CbteHasta": 123,
            "CbteFch": "20261014",
            "FchServDesde": "20261001",
            "FchServHasta": "20261031",
            "FchVtoPago": "20261110",
            "CondicionIVAReceptorId": 5,
            "ImpTotal": 12100.0,
            "ImpTotConc": 0.0,
            "ImpNeto": 12100.0,
            "ImpOpEx": 0.0,
            "ImpTrib": 0.0,
            "ImpIVA": 0.0,
            "MonId": "PES",
            "MonCotiz": 1.0,
        })
        self.assertEqual(contexto, contexto_original)
        contexto_con_numero = deepcopy(contexto_original)
        contexto_con_numero["comprobante"]["numero_comprobante_planificado"] = 123
        contexto_con_numero["comprobante"]["numero_textual_planificado"] = "00005-00000123"
        self.assertEqual(preenvio.contextos, [contexto_con_numero])

    def test_constructor_wsfe_concepto_uno_no_agrega_fechas_de_servicio(self):
        resultado = WSFEService.construir_solicitud_cae(
            cuit="20206871629",
            punto_venta=5,
            tipo_comprobante=11,
            numero_comprobante=123,
            condicion_iva_receptor_id=5,
            concepto=1,
            documento_receptor=30712345678,
            tipo_documento=80,
            importe=12100.0,
            importe_neto=12100.0,
            importe_iva=0.0,
            importe_exento=0.0,
            fecha_comprobante="20261014",
            moneda="PES",
            cotizacion=1.0,
            importe_tot_conc=0.0,
            importe_tributos=0.0,
            alicuotas_iva=[],
        )

        self.assertTrue(resultado["ok"])
        detalle = resultado["solicitud"]["FeCAEReq"]["FeDetReq"]["FECAEDetRequest"][0]
        self.assertEqual(detalle, {
            "Concepto": 1,
            "DocTipo": 80,
            "DocNro": 30712345678,
            "CbteDesde": 123,
            "CbteHasta": 123,
            "CbteFch": "20261014",
            "CondicionIVAReceptorId": 5,
            "ImpTotal": 12100.0,
            "ImpTotConc": 0.0,
            "ImpNeto": 12100.0,
            "ImpOpEx": 0.0,
            "ImpTrib": 0.0,
            "ImpIVA": 0.0,
            "MonId": "PES",
            "MonCotiz": 1.0,
        })


if __name__ == "__main__":
    unittest.main()