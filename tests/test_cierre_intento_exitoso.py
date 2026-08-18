import unittest
from unittest.mock import MagicMock, patch

from services.arca.reconciliacion_contracts import ResultadoReconciliacion
from services.facturacion_service import FacturacionService


class CierreIntentoExitosoTest(unittest.TestCase):

    def test_emitir_en_arca_propagates_intento_id(self):
        emision = {
            "ok": True,
            "intento_id": 77,
            "numero_comprobante": 123,
            "cae": "71345678901234",
            "vencimiento_cae": "20260826",
            "token": "token",
            "sign": "sign",
        }
        consulta = {
            "ok": True,
            "numero_comprobante": 123,
            "punto_venta": 5,
            "cae": "71345678901234",
            "vencimiento_cae": "20260826",
        }
        with (
            patch("services.facturacion_service.HomologacionService.emitir_comprobante_prueba", return_value=emision),
            patch("services.facturacion_service.HomologacionService.consultar_comprobante_emitido", return_value=consulta),
        ):
            resultado = FacturacionService.emitir_en_arca(
                ruta_certificado="cert.crt", ruta_clave="clave.key", cuit_emisor="20206871629",
                punto_venta=5, tipo_comprobante=11, condicion_iva_receptor_id=5,
                tipo_documento=80, documento_receptor=30712345678, importe_total=100,
                importe_neto=100, importe_iva=0, importe_exento=0, carpeta_trabajo="C:/trabajo",
                importe_tot_conc=0, importe_tributos=0, alicuotas_iva=[],
            )
        self.assertTrue(resultado["ok"])
        self.assertEqual(resultado["intento_id"], 77)

    def test_cierre_ocurre_tras_registro_y_antes_de_pdf(self):
        orden = []
        resultado_arca = {
            "ok": True, "intento_id": 77, "consulta": {}, "fecha_comprobante": "20260816",
            "numero_comprobante": 123, "punto_venta_num": 5, "cae": "71345678901234", "vencimiento_cae": "20260826",
        }
        registro = {"ok": True, "factura_id": 99}
        cierre = MagicMock(side_effect=lambda *args, **kwargs: orden.append("cierre"))

        with (
            patch.object(FacturacionService, "emitir_en_arca", return_value=resultado_arca),
            patch.object(FacturacionService, "registrar_emision_aprobada", return_value=registro),
            patch.object(FacturacionService, "generar_pdf_fiscal", side_effect=lambda **kwargs: orden.append("pdf") or {"ok": False, "errores": ["pdf"]}),
            patch("services.facturacion_service.IntentoEmisionArcaService") as intentos_cls,
        ):
            intentos_cls.return_value.listar_activos_por_resumen.return_value = []
            intentos_cls.return_value.guardar_resultado_reconciliacion.side_effect = cierre
            resultado = self._emitir_desde_resumen_minimo()

        self.assertEqual(resultado["etapa"], "pdf")
        self.assertEqual(orden, ["cierre", "pdf"])
        intentos_cls.return_value.guardar_resultado_reconciliacion.assert_called_once_with(
            77,
            ResultadoReconciliacion.AUTORIZADO,
            cae="71345678901234",
            vencimiento_cae="20260826",
            factura_arca_id=99,
        )

    def test_fallo_registro_no_cierra_intento(self):
        with (
            patch.object(FacturacionService, "emitir_en_arca", return_value=self._resultado_arca()),
            patch.object(FacturacionService, "registrar_emision_aprobada", return_value={"ok": False, "errores": ["db"]}),
            patch("services.facturacion_service.IntentoEmisionArcaService") as intentos_cls,
        ):
            intentos_cls.return_value.listar_activos_por_resumen.return_value = []
            resultado = self._emitir_desde_resumen_minimo()
        self.assertEqual(resultado["etapa"], "registro")
        intentos_cls.return_value.guardar_resultado_reconciliacion.assert_not_called()

    def test_fallo_guardar_factura_no_marca_resumen(self):
        with (
            patch("services.facturacion_service.FacturaArcaService.guardar", side_effect=OSError("db")),
            patch("services.facturacion_service.ResumenService.marcar_facturado") as marcar_resumen,
        ):
            resultado = FacturacionService.registrar_emision_aprobada(
                cliente_id=20, emisor_id=40, resumen_id=10, fecha="2026-08-16", punto_venta="5",
                tipo_comprobante="Factura C", importe_total=100, numero_factura="00005-00000123",
                cae="71345678901234", vencimiento_cae="20260826", observaciones="",
            )
        self.assertFalse(resultado["ok"])
        marcar_resumen.assert_not_called()

    def test_fallo_marcar_resumen_no_cierra_intento(self):
        with (
            patch("services.facturacion_service.FacturaArcaService.guardar", return_value=99),
            patch("services.facturacion_service.ResumenService.marcar_facturado", side_effect=OSError("resumen")),
        ):
            resultado = FacturacionService.registrar_emision_aprobada(
                cliente_id=20, emisor_id=40, resumen_id=10, fecha="2026-08-16", punto_venta="5",
                tipo_comprobante="Factura C", importe_total=100, numero_factura="00005-00000123",
                cae="71345678901234", vencimiento_cae="20260826", observaciones="",
            )
        self.assertFalse(resultado["ok"])

    def _resultado_arca(self):
        return {
            "ok": True, "intento_id": 77, "consulta": {}, "fecha_comprobante": "20260816",
            "numero_comprobante": 123, "punto_venta_num": 5, "cae": "71345678901234", "vencimiento_cae": "20260826",
        }

    def _emitir_desde_resumen_minimo(self):
        resumen = type("Resumen", (), {"id": 10, "estado_facturacion": "Pendiente", "cliente_id": 20, "total": 100, "conceptos": [object()]})()
        cliente = (20, "", "Cliente", "", "", "", "", "", "", "", "30712345678", "Responsable Inscripto")
        emisor = (30, "Emisor", "", "20206871629", "Responsable Inscripto", "Factura A", 5, 1, "", "Homologación", "", "", "", "cert.crt", "clave.key", "C:/trabajo")
        fiscal = {
            "ok": True, "tipo_comprobante": 1, "neto_factura": 100, "alicuota_iva": 21,
            "importe_iva_factura": 21, "total_factura_fiscal": 121, "importe_exento_factura": 0,
            "importe_tot_conc": 0, "importe_tributos": 0, "alicuotas_iva": [], "condicion_iva_receptor_id": 1,
        }
        with (
            patch("services.facturacion_service.ResumenService.obtener", return_value=resumen),
            patch("services.facturacion_service.FacturaArcaService.listar_por_resumen", return_value=[]),
            patch("services.facturacion_service.IntentoEmisionArcaService.listar_activos_por_resumen", return_value=[]),
            patch.object(FacturacionService, "validar_resumen_para_facturar", return_value={"ok": True}),
            patch.object(FacturacionService, "resolver_cliente", return_value={"ok": True, "cliente": cliente}),
            patch.object(FacturacionService, "resolver_conceptos", return_value={"ok": True, "resumen": resumen, "conceptos": [object()]}),
            patch.object(FacturacionService, "resolver_emisor", return_value={"ok": True, "emisor_fiscal": emisor}),
            patch.object(FacturacionService, "_resolver_emisor_facturacion_id", return_value=(40, "id")),
            patch.object(FacturacionService, "_armar_items_factura_desde_resumen", return_value=[{"importe": 100, "cantidad": 1, "precio_unitario": 100, "descripcion": "Servicio"}]),
            patch.object(FacturacionService, "calcular_importes_fiscales", return_value=fiscal),
            patch("services.facturacion_service.FacturaArcaService.validar_pre_guardado", return_value={"ok": True}),
            patch.object(FacturacionService, "_sumar_importes_items", return_value=100),
            patch.object(FacturacionService, "_obtener_periodo_facturado", return_value=("", "")),
        ):
            return FacturacionService.emitir_desde_resumen(10, {"tipo_factura": "Factura A", "condicion_iva": "Responsable Inscripto"})


if __name__ == "__main__":
    unittest.main()