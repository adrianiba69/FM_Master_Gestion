import unittest
from contextlib import ExitStack
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import patch

from services.facturacion_service import FacturacionService
from tests._cierre_contexto_helper import configuracion_arca_para_test


class ValidacionPeriodoFiscalServiciosTest(unittest.TestCase):
    def _ejecutar(self, periodos, vencimiento="2026-11-10"):
        conceptos = [
            SimpleNamespace(
                fecha_inicio=inicio, fecha_fin=fin, cantidad=1, importe=100,
                total=100, descuento=0, concepto="Servicio", descripcion="Prestacion ficticia",
            )
            for inicio, fin in periodos
        ]
        resumen = SimpleNamespace(
            id=10, cliente_id=20, emisor_fiscal_id=30, estado_facturacion="Pendiente",
            total=100 * len(conceptos), conceptos=conceptos, fecha_vencimiento=vencimiento,
        )
        original = deepcopy(vars(resumen))
        cliente = (20, "", "Cliente ficticio", "", "", "", "", "", "", "", "30712345678", "Responsable Inscripto")
        emisor = (
            30, "Emisor ficticio", "", "20206871629", "Responsable Inscripto",
            "Factura A", 5, 1, "", "Homologación", "", "", "",
            "cert.crt", "clave.key", "C:/trabajo",
        )
        with ExitStack() as pila:
            barreras = []
            for destino in (
                "sqlite3.connect", "urllib.request.urlopen", "socket.socket.connect",
                "reportlab.pdfgen.canvas.Canvas",
                "services.facturacion_service.HomologacionService.emitir_comprobante_prueba",
                "services.facturacion_service.IntentoEmisionArcaService.crear_intento",
                "services.facturacion_service.CierreLocalArcaService.cerrar_emision_confirmada",
                "services.facturacion_service.FacturacionService.generar_pdf_fiscal",
            ):
                barreras.append(pila.enter_context(patch(
                    destino, side_effect=AssertionError("Operacion real prohibida: " + destino),
                )))
            pila.enter_context(patch("services.facturacion_service.ResumenService.obtener", return_value=resumen))
            pila.enter_context(patch("services.facturacion_service.ClienteService.obtener", return_value=cliente))
            pila.enter_context(patch("services.facturacion_service.EmisorFiscalService.obtener", return_value=emisor))
            pila.enter_context(patch("services.facturacion_service.FacturaArcaService.listar_por_resumen", return_value=[]))
            pila.enter_context(patch("services.facturacion_service.IntentoEmisionArcaService.listar_activos_por_resumen", return_value=[]))
            pila.enter_context(patch(
                "services.facturacion_service.EmisorFiscalService.obtener_configuracion_arca",
                return_value=configuracion_arca_para_test(),
            ))
            pila.enter_context(patch.object(FacturacionService, "_resolver_emisor_facturacion_id", return_value=(40, "simulado")))
            pila.enter_context(patch("services.facturacion_service.FacturaArcaService.validar_pre_guardado", return_value={"ok": True}))
            enviar = pila.enter_context(patch.object(
                FacturacionService, "emitir_en_arca",
                return_value={"ok": False, "errores": ["Frontera de emision simulada"]},
            ))
            resultado = FacturacionService.emitir_desde_resumen(10, {
                "modalidad_comprobante": "Resumen + Factura", "tipo_factura": "Factura A",
                "condicion_iva": "Responsable Inscripto", "emisor_fiscal_id_confirmado": 30,
            })
            for barrera in barreras:
                barrera.assert_not_called()
        self.assertEqual(vars(resumen), original)
        return resultado, enviar, resumen

    def _verificar_valido(self, periodos):
        _resultado, enviar, resumen = self._ejecutar(periodos)
        self.assertEqual(FacturacionService._obtener_periodo_facturado(resumen), ("20261001", "20261031"))
        enviar.assert_called_once()
        comprobante = enviar.call_args.kwargs["contexto_fiscal_base"]["comprobante"]
        self.assertEqual(comprobante["periodo_servicio_desde"], "2026-10-01")
        self.assertEqual(comprobante["periodo_servicio_hasta"], "2026-10-31")
        self.assertEqual(comprobante["vencimiento_pago"], "2026-11-10")

    def _verificar_bloqueo(self, periodos, vencimiento="2026-11-10"):
        resultado, enviar, _resumen = self._ejecutar(periodos, vencimiento)
        enviar.assert_not_called()
        self.assertFalse(resultado["ok"])
        self.assertTrue(resultado["errores"])

    def _argumentos_emision_validos(self):
        _resultado, enviar, _resumen = self._ejecutar([("2026-10-01", "2026-10-31")])
        enviar.assert_called_once()
        return deepcopy(enviar.call_args.kwargs)

    def _invocar_emitir_en_arca(self, argumentos):
        with patch(
            "services.facturacion_service.HomologacionService.emitir_comprobante_prueba",
            return_value={"ok": False, "errores": ["Emision simulada"]},
        ) as homologacion:
            resultado = FacturacionService.emitir_en_arca(**argumentos)
        return resultado, homologacion

    def _verificar_bloqueo_contexto(self, mutar_comprobante):
        argumentos = self._argumentos_emision_validos()
        mutar_comprobante(argumentos["contexto_fiscal_base"]["comprobante"])
        resultado, homologacion = self._invocar_emitir_en_arca(argumentos)
        self.assertEqual(resultado["etapa"], "emision_bloqueada_fechas_servicio")
        self.assertTrue(resultado["errores"])
        homologacion.assert_not_called()

    def test_un_servicio_con_fechas_validas(self):
        for inicio, fin in (("2026-10-01", "2026-10-31"), ("20261001", "20261031")):
            with self.subTest(inicio=inicio, fin=fin):
                self._verificar_valido([(inicio, fin)])

    def test_varios_servicios_con_periodos_identicos(self):
        self._verificar_valido([("2026-10-01", "2026-10-31")] * 2)

    def test_periodos_diferentes_bloquean(self):
        self._verificar_bloqueo([("2026-10-01", "2026-10-31"), ("2026-09-01", "2026-09-30")])

    def test_inicio_faltante_bloquea_incluso_con_otro_item_completo(self):
        for inicio in (None, ""):
            with self.subTest(inicio=inicio):
                self._verificar_bloqueo([(inicio, "2026-10-31"), ("2026-10-01", "2026-10-31")])

    def test_fin_faltante_bloquea_incluso_con_otro_item_completo(self):
        for fin in (None, ""):
            with self.subTest(fin=fin):
                self._verificar_bloqueo([("2026-10-01", fin), ("2026-10-01", "2026-10-31")])

    def test_fechas_calendariamente_imposibles_bloquean(self):
        for periodo in (("2026-02-30", "2026-10-31"), ("2026-10-01", "2026-13-31")):
            with self.subTest(periodo=periodo):
                self._verificar_bloqueo([periodo])

    def test_fin_anterior_al_inicio_bloquea(self):
        self._verificar_bloqueo([("2026-10-31", "2026-10-01")])

    def test_vencimiento_faltante_o_invalido_bloquea(self):
        for vencimiento in (None, "", "invalido", "2026-02-30", "10/11/2026"):
            with self.subTest(vencimiento=vencimiento):
                self._verificar_bloqueo([("2026-10-01", "2026-10-31")], vencimiento)

    def test_formatos_de_prestacion_no_admitidos_bloquean(self):
        for periodo in (("01/10/2026", "31/10/2026"), ("2026/10/01", "2026/10/31"), ("2026-10-01T00:00:00", "2026-10-31T00:00:00")):
            with self.subTest(periodo=periodo):
                self._verificar_bloqueo([periodo])

    def test_emitir_en_arca_transmite_concepto_servicios_y_fechas_del_contexto(self):
        argumentos = self._argumentos_emision_validos()
        contexto_original = deepcopy(argumentos["contexto_fiscal_base"])
        comprobante = contexto_original["comprobante"]

        self.assertEqual(argumentos["concepto"], 2)
        self.assertEqual(comprobante["concepto"], 2)
        self.assertEqual(comprobante["concepto_descripcion"], "Servicios")
        self.assertEqual(comprobante["periodo_servicio_desde"], "2026-10-01")
        self.assertEqual(comprobante["periodo_servicio_hasta"], "2026-10-31")
        self.assertEqual(comprobante["vencimiento_pago"], "2026-11-10")

        _resultado, homologacion = self._invocar_emitir_en_arca(argumentos)
        homologacion.assert_called_once()
        enviados = homologacion.call_args.kwargs
        self.assertEqual(enviados["concepto"], 2)
        self.assertEqual(enviados["fecha_servicio_desde"], "20261001")
        self.assertEqual(enviados["fecha_servicio_hasta"], "20261031")
        self.assertEqual(enviados["fecha_vencimiento_pago"], "20261110")
        self.assertEqual(argumentos["contexto_fiscal_base"], contexto_original)

    def test_inicio_faltante_en_contexto_bloquea_antes_de_homologacion(self):
        self._verificar_bloqueo_contexto(lambda comprobante: comprobante.update(periodo_servicio_desde=None))

    def test_fin_faltante_en_contexto_bloquea_antes_de_homologacion(self):
        self._verificar_bloqueo_contexto(lambda comprobante: comprobante.update(periodo_servicio_hasta=None))

    def test_vencimiento_faltante_en_contexto_bloquea_antes_de_homologacion(self):
        self._verificar_bloqueo_contexto(lambda comprobante: comprobante.update(vencimiento_pago=None))

    def test_fechas_calendariamente_invalidas_en_contexto_bloquean_antes_de_homologacion(self):
        for campo, valor in (
            ("periodo_servicio_desde", "2026-02-30"),
            ("periodo_servicio_hasta", "2026-13-31"),
            ("vencimiento_pago", "2026-02-30"),
        ):
            with self.subTest(campo=campo, valor=valor):
                self._verificar_bloqueo_contexto(lambda comprobante: comprobante.update({campo: valor}))

    def test_inicio_posterior_a_fin_en_contexto_bloquea_antes_de_homologacion(self):
        def mutar(comprobante):
            comprobante["periodo_servicio_desde"] = "2026-10-31"
            comprobante["periodo_servicio_hasta"] = "2026-10-01"

        self._verificar_bloqueo_contexto(mutar)

    def test_concepto_contexto_discrepante_bloquea_antes_de_homologacion(self):
        self._verificar_bloqueo_contexto(lambda comprobante: comprobante.update(concepto=1))

    def test_concepto_uno_no_transmite_fechas_de_servicio(self):
        argumentos = self._argumentos_emision_validos()
        argumentos["concepto"] = 1
        comprobante = argumentos["contexto_fiscal_base"]["comprobante"]
        comprobante["concepto"] = 1
        comprobante["concepto_descripcion"] = "Productos"
        comprobante["periodo_servicio_desde"] = None
        comprobante["periodo_servicio_hasta"] = None
        comprobante["vencimiento_pago"] = None

        _resultado, homologacion = self._invocar_emitir_en_arca(argumentos)

        homologacion.assert_called_once()
        enviados = homologacion.call_args.kwargs
        self.assertEqual(enviados["concepto"], 1)
        self.assertNotIn("fecha_servicio_desde", enviados)
        self.assertNotIn("fecha_servicio_hasta", enviados)
        self.assertNotIn("fecha_vencimiento_pago", enviados)


if __name__ == "__main__":
    unittest.main()