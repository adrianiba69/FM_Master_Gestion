import unittest
from unittest.mock import patch

from services.arca.homologacion_service import HomologacionService
from services.arca.preenvio_arca_service import ResultadoPreenvioArca


class PreenvioCapturador:

    def __init__(self):
        self.snapshots = []

    def enviar_una_vez(self, snapshot, enviar_fecae):
        self.snapshots.append(snapshot)
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


if __name__ == "__main__":
    unittest.main()