"""POST-E2E 3B.4D.1: certificacion de la cadena de ambiente H/P. Solo mocks, sin red real."""

import tempfile
import unittest
from contextlib import ExitStack
from unittest.mock import MagicMock, patch

from services.arca import ambiente_arca
from services.arca.homologacion_service import HomologacionService
from services.arca.preenvio_arca_service import PreenvioArcaService
from services.arca.reconciliacion_contracts import ResultadoReconciliacion
from services.arca.reconciliacion_service import ReconciliacionArcaService
from services.arca.recuperacion_local_service import RecuperacionLocalArcaService
from services.arca.wsaa_login_service import WSAALoginService
from services.arca.wsaa_service import WSAAService
from services.arca.wsfe_service import WSFEService
from services.intento_emision_arca_service import IntentoEmisionArcaService
from tests.test_ambiente_intentos_3b4c import (
    CUIT, H, P, Base3B4C, EmisorFake, consulta_autorizada, contexto,
)

URL_POR_AMBIENTE = {
    H: "https://wswhomo.afip.gov.ar/wsfev1/service.asmx",
    P: "https://servicios1.afip.gov.ar/wsfev1/service.asmx",
}


class CadenaReconciliacionTest(Base3B4C):
    """Reconciliacion real hasta HomologacionService.consultar_comprobante_emitido."""

    def reconciliar(self, ambiente, respuesta=None):
        intento_id = self.crear(ambiente)
        # consultar_comprobante=None: se usa la funcion real HomologacionService.consultar_comprobante_emitido.
        servicio = ReconciliacionArcaService(
            self.intentos, EmisorFake(), None, RecuperacionLocalArcaService(self.factory)
        )
        with ExitStack() as pila:
            mocks = {
                "tra": pila.enter_context(patch.object(WSAAService, "guardar_tra", return_value="tra.xml")),
                "login": pila.enter_context(patch.object(
                    WSAALoginService, "login_homologacion", return_value={"ok": True, "token": "tk", "sign": "sg"}
                )),
                "consulta": pila.enter_context(patch.object(
                    WSFEService, "fe_comp_consultar",
                    return_value=consulta_autorizada() if respuesta is None else respuesta,
                )),
                "ultimo": pila.enter_context(patch.object(WSFEService, "fe_comp_ultimo_autorizado")),
                "fecae": pila.enter_context(patch.object(WSFEService, "fe_cae_solicitar")),
                "red": pila.enter_context(patch("urllib.request.urlopen", side_effect=AssertionError("red real"))),
            }
            resultado = servicio.reconciliar_intento(intento_id)
        return intento_id, resultado, mocks

    def certificar_cadena(self, ambiente, opuesto):
        intento_id, resultado, mocks = self.reconciliar(ambiente)

        self.assertTrue(resultado.ok, resultado.errores)
        self.assertEqual(resultado.resultado, ResultadoReconciliacion.AUTORIZADO)
        # WSAA recibe el ambiente congelado, aunque el emisor vivo diga Homologacion.
        mocks["login"].assert_called_once()
        self.assertEqual(mocks["login"].call_args.kwargs["ambiente"], ambiente)
        self.assertEqual(mocks["login"].call_args.kwargs["ruta_certificado"], "c.crt")
        # FECompConsultar: endpoint del ambiente y identidad congelada del contexto.
        mocks["consulta"].assert_called_once()
        enviado = mocks["consulta"].call_args.kwargs
        self.assertEqual(enviado["url"], URL_POR_AMBIENTE[ambiente])
        self.assertNotEqual(enviado["url"], URL_POR_AMBIENTE[opuesto])
        self.assertEqual(
            (enviado["cuit"], enviado["punto_venta"], enviado["tipo_comprobante"], enviado["numero_comprobante"]),
            (CUIT, 5, 11, 123),
        )
        self.assertEqual((enviado["token"], enviado["sign"]), ("tk", "sg"))
        # Solo consulta: nada de emision ni de ultimo autorizado, y ninguna red real.
        mocks["fecae"].assert_not_called()
        mocks["ultimo"].assert_not_called()
        mocks["red"].assert_not_called()
        # La recuperacion real persistio la factura en el mismo ambiente.
        self.assertEqual(self.intentos.obtener(intento_id).estado, "RECONCILIADO")
        self.assertEqual(self.sql("SELECT ambiente_arca FROM factura_arca"), [(ambiente,)])

    def test_m_cadena_real_reconciliacion_h_usa_endpoint_homologacion(self):
        self.certificar_cadena(H, opuesto=P)

    def test_n_cadena_real_reconciliacion_p_usa_endpoint_produccion(self):
        # Consulta historica de un intento P ya existente; no simula ninguna emision nueva.
        self.certificar_cadena(P, opuesto=H)

    def test_o_reconciliacion_h_y_p_nunca_llama_fecae_solicitar(self):
        conflicto = dict(consulta_autorizada(), importe_total="999.00")
        respuestas = {
            "autorizada": consulta_autorizada(),
            "conflicto": conflicto,
            "consulta_fallida": {"ok": False, "errores": ["sin respuesta"]},
        }
        for ambiente in (H, P):
            for nombre, respuesta in respuestas.items():
                with self.subTest(ambiente=ambiente, respuesta=nombre):
                    self.sql("DELETE FROM factura_arca")
                    self.sql("DELETE FROM intentos_emision_arca")
                    _, _, mocks = self.reconciliar(ambiente, respuesta)
                    mocks["consulta"].assert_called_once()
                    mocks["fecae"].assert_not_called()
                    mocks["ultimo"].assert_not_called()
                    mocks["red"].assert_not_called()


class BloqueoEmisionProduccionTest(Base3B4C):
    """La emision NUEVA en Produccion debe cortar antes de intento, TRA, WSAA y WSFE."""

    def emitir(self, ambiente, contexto_base):
        preenvio = PreenvioArcaService(self.intentos)
        with ExitStack() as pila:
            mocks = {
                "tra": pila.enter_context(patch.object(WSAAService, "guardar_tra")),
                "login": pila.enter_context(patch.object(WSAALoginService, "login_homologacion")),
                "ultimo": pila.enter_context(patch.object(WSFEService, "fe_comp_ultimo_autorizado")),
                "consulta": pila.enter_context(patch.object(WSFEService, "fe_comp_consultar")),
                "fecae": pila.enter_context(patch.object(WSFEService, "fe_cae_solicitar")),
                "crear": pila.enter_context(patch.object(IntentoEmisionArcaService, "crear_intento")),
                "con_contexto": pila.enter_context(patch.object(PreenvioArcaService, "enviar_una_vez_con_contexto")),
                "sin_contexto": pila.enter_context(patch.object(PreenvioArcaService, "enviar_una_vez")),
                "red": pila.enter_context(patch("urllib.request.urlopen", side_effect=AssertionError("red real"))),
            }
            resultado = HomologacionService.emitir_comprobante_prueba(
                ruta_certificado="c.crt", ruta_clave="k.key", cuit_emisor=CUIT, punto_venta=5,
                tipo_comprobante=11, condicion_iva_receptor_id=5, concepto=1, tipo_documento=80,
                documento_receptor=30712345678, importe_total=100, importe_neto=100, importe_iva=0,
                importe_exento=0, fecha_comprobante="20260817", carpeta_trabajo=tempfile.gettempdir(),
                contexto_fiscal_base=contexto_base, exigir_contexto_fiscal=contexto_base is not None,
                datos_intento={"resumen_id": 10, "cliente_id": 20, "emisor_fiscal_id": 30, "emisor_id": 40},
                preenvio_service=preenvio, ambiente=ambiente,
            )
        for nombre, mock in mocks.items():
            with self.subTest(frontera=nombre):
                mock.assert_not_called()
        self.assertEqual(self.sql("SELECT COUNT(*) FROM intentos_emision_arca"), [(0,)])
        return resultado

    def certificar_bloqueo(self, contexto_base):
        for ambiente in (ambiente_arca.AMBIENTE_PRODUCCION, "Producción", "produccion"):
            with self.subTest(ambiente=ambiente):
                resultado = self.emitir(ambiente, contexto_base)
                self.assertFalse(resultado["ok"])
                self.assertEqual(resultado["numero_comprobante"], 0)
                self.assertIsNone(resultado.get("intento_id"))
                self.assertTrue(any("Producción" in e for e in resultado["errores"]), resultado["errores"])

    def test_p_emision_nueva_con_contexto_p_valido_bloqueada_antes_de_todo(self):
        self.certificar_bloqueo(contexto(P))

    def test_p_emision_nueva_sin_contexto_legacy_bloqueada_antes_de_todo(self):
        self.certificar_bloqueo(None)


if __name__ == "__main__":
    unittest.main()
