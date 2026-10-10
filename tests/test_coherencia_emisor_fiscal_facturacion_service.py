import unittest
from contextlib import ExitStack
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import patch

from services.facturacion_service import FacturacionService


class CoherenciaEmisorFiscalFacturacionServiceTest(unittest.TestCase):
    def _ejecutar(self, confirmado=30, persistido=30, seleccionado=30,
                  omitir_confirmado=False, omitir_resumen=False, registro_vacio=False):
        resumen = SimpleNamespace(
            id=10, cliente_id=20, estado_facturacion="Pendiente",
            emisor_fiscal_id=persistido, total=100, conceptos=["Servicio ficticio"],
        )
        contexto = {
            "modalidad_comprobante": "Resumen + Factura",
            "tipo_factura": "Factura A",
            "condicion_iva": "Responsable Inscripto",
        }
        if not omitir_confirmado:
            contexto["emisor_fiscal_id_confirmado"] = confirmado
        emisor = () if registro_vacio else (seleccionado, "Emisor ficticio")
        resolucion = {"ok": True, "emisor_fiscal": emisor}
        if not omitir_resumen:
            resolucion["resumen"] = resumen
        contexto_original = deepcopy(contexto)
        resumen_original = deepcopy(vars(resumen))

        with ExitStack() as pila:
            barreras = {}
            for destino in (
                "sqlite3.connect", "urllib.request.urlopen", "socket.socket.connect",
                "reportlab.pdfgen.canvas.Canvas",
                "services.facturacion_service.EmisorFiscalService.obtener_configuracion_arca",
                "services.facturacion_service.IntentoEmisionArcaService.crear_intento",
                "services.facturacion_service.CierreLocalArcaService.cerrar_emision_confirmada",
                "services.facturacion_service.HomologacionService.emitir_comprobante_prueba",
                "services.facturacion_service.HomologacionService.consultar_comprobante_emitido",
                "services.facturacion_service.FacturacionService.emitir_en_arca",
                "services.facturacion_service.FacturacionService.generar_pdf_fiscal",
            ):
                barreras[destino] = pila.enter_context(patch(
                    destino, side_effect=AssertionError("Operacion posterior prohibida: " + destino),
                ))
            pila.enter_context(patch(
                "services.facturacion_service.ResumenService.obtener", return_value=resumen,
            ))
            pila.enter_context(patch(
                "services.facturacion_service.IntentoEmisionArcaService.listar_activos_por_resumen",
                return_value=[],
            ))
            pila.enter_context(patch(
                "services.facturacion_service.FacturaArcaService.listar_por_resumen", return_value=[],
            ))
            for nombre, valor in (
                ("validar_resumen_para_facturar", {"ok": True}),
                ("resolver_cliente", {"ok": True, "cliente": (20,)}),
                ("resolver_conceptos", {"ok": True, "resumen": resumen, "conceptos": resumen.conceptos}),
                ("resolver_emisor", resolucion),
            ):
                pila.enter_context(patch.object(FacturacionService, nombre, return_value=valor))
            vinculo = pila.enter_context(patch.object(
                FacturacionService, "_resolver_emisor_facturacion_id",
                return_value=(None, "frontera_simulada"),
            ))

            resultado = FacturacionService.emitir_desde_resumen(10, contexto)

            for destino, barrera in barreras.items():
                with self.subTest(dependencia=destino):
                    barrera.assert_not_called()

        self.assertEqual(contexto, contexto_original)
        self.assertEqual(vars(resumen), resumen_original)
        return resultado, vinculo, emisor

    def _verificar_rechazo(self, **argumentos):
        resultado, vinculo, _ = self._ejecutar(**argumentos)
        self.assertFalse(resultado["ok"])
        self.assertEqual(resultado["etapa"], "coherencia_emisor_fiscal")
        self.assertEqual(resultado["errores"], ["emisor_fiscal_no_coincide_o_invalido"])
        self.assertIn("No se puede emitir", resultado["mensaje"])
        self.assertEqual(resultado["resumen_id"], 10)
        self.assertIsNone(resultado["factura_id"])
        vinculo.assert_not_called()

    def _verificar_aceptacion(self, **argumentos):
        resultado, vinculo, emisor = self._ejecutar(**argumentos)
        vinculo.assert_called_once_with(emisor)
        self.assertEqual(resultado["etapa"], "vinculo_emisor")
        self.assertFalse(resultado["ok"])
        self.assertEqual(resultado["errores"], [])

    def test_tres_ids_validos_iguales_alcanzan_siguiente_paso_simulado(self):
        self._verificar_aceptacion()

    def test_ids_enteros_y_cadenas_equivalentes_permiten_continuar(self):
        for ids in ((30, "30", "030"), (" 30 ", 30, "30"), ("030", "30", 30)):
            with self.subTest(ids=ids):
                self._verificar_aceptacion(confirmado=ids[0], persistido=ids[1], seleccionado=ids[2])

    def test_id_confirmado_ausente_rechaza(self):
        self._verificar_rechazo(omitir_confirmado=True)
        self._verificar_rechazo(confirmado=None)

    def test_id_persistido_ausente_rechaza(self):
        self._verificar_rechazo(persistido=None)
        self._verificar_rechazo(omitir_resumen=True)

    def test_id_seleccionado_ausente_rechaza(self):
        self._verificar_rechazo(seleccionado=None)
        self._verificar_rechazo(registro_vacio=True)

    def test_id_confirmado_distinto_del_persistido_rechaza(self):
        self._verificar_rechazo(confirmado=1, persistido=2, seleccionado=2)

    def test_id_persistido_distinto_del_seleccionado_rechaza(self):
        self._verificar_rechazo(confirmado=1, persistido=1, seleccionado=2)

    def test_valores_invalidos_rechazan_en_cualquiera_de_los_tres_ids(self):
        valores = (
            True, False, 0, -1, 30.0, 30.5, "", " ", "abc", "0", "-30",
            "+30", "30.0", "3e1", "0x1e", "3_0", "3 0", [], {},
        )
        for campo in ("confirmado", "persistido", "seleccionado"):
            for valor in valores:
                with self.subTest(campo=campo, valor=repr(valor)):
                    self._verificar_rechazo(**{campo: valor})


if __name__ == "__main__":
    unittest.main()