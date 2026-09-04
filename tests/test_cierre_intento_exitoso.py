import unittest
from decimal import Decimal
from unittest.mock import MagicMock, patch

from services.arca.contexto_fiscal_service import ContextoFiscalService
from services.arca.reconciliacion_contracts import ResultadoReconciliacion
from services.facturacion_service import FacturacionService


class CierreIntentoExitosoTest(unittest.TestCase):

    def _contexto_minimo(self):
        return {
            "tipo": "contexto_fiscal_arca",
            "version": 1,
            "creado_en": "2026-08-16T10:00:00",
            "ambiente": "HOMOLOGACION",
            "emisor": {"emisor_id": 40, "emisor_fiscal_id": 30, "razon_social": "Emisor", "cuit": "20206871629", "punto_venta_num": 5},
            "receptor": {"cliente_id": 20, "razon_social": "Cliente", "documento_visible": "30712345678", "tipo_documento_receptor": 80, "documento_receptor": 30712345678},
            "comprobante": {"fecha": "20260816", "fecha_arca": "20260816", "tipo_comprobante_num": 11, "numero_comprobante_planificado": None},
            "importes": {"total": Decimal("100"), "neto": Decimal("100")},
            "iva": [],
            "items": [{"descripcion": "Servicio", "subtotal": Decimal("100")}],
        }

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
                contexto_fiscal_base=self._contexto_minimo(),
            )
        self.assertTrue(resultado["ok"])
        self.assertEqual(resultado["intento_id"], 77)

    def test_emitir_en_arca_exige_contexto_fiscal_base(self):
        with patch("services.facturacion_service.HomologacionService.emitir_comprobante_prueba") as emitir:
            resultado = FacturacionService.emitir_en_arca(
                ruta_certificado="cert.crt", ruta_clave="clave.key", cuit_emisor="20206871629",
                punto_venta=5, tipo_comprobante=11, condicion_iva_receptor_id=5,
                tipo_documento=80, documento_receptor=30712345678, importe_total=100,
                importe_neto=100, importe_iva=0, importe_exento=0, carpeta_trabajo="C:/trabajo",
                importe_tot_conc=0, importe_tributos=0, alicuotas_iva=[],
            )

        self.assertFalse(resultado["ok"])
        self.assertIn("Contexto fiscal base obligatorio", resultado["errores"][0])
        emitir.assert_not_called()

    def test_cierre_ocurre_tras_registro_y_antes_de_pdf(self):
        orden = []
        resultado_arca = {
            "ok": True, "intento_id": 77, "consulta": {}, "fecha_comprobante": "20260816",
            "numero_comprobante": 123, "punto_venta_num": 5, "cae": "71345678901234", "vencimiento_cae": "20260826",
        }
        registro = {"ok": True, "factura_id": 99}
        cierre = MagicMock(side_effect=lambda *args, **kwargs: orden.append("cierre") or type("Cierre", (), {"ok": True, "factura_arca_id": 99})())

        with (
            patch.object(FacturacionService, "emitir_en_arca", return_value=resultado_arca),
            patch.object(FacturacionService, "registrar_emision_aprobada", return_value=registro),
            patch.object(FacturacionService, "generar_pdf_fiscal", side_effect=lambda **kwargs: orden.append("pdf") or {"ok": False, "errores": ["pdf"]}),
            patch("services.facturacion_service.CierreLocalArcaService") as cierre_cls,
        ):
            cierre_cls.return_value.cerrar_emision_confirmada.side_effect = cierre
            resultado = self._emitir_desde_resumen_minimo()

        self.assertEqual(resultado["etapa"], "pdf")
        self.assertEqual(orden, ["cierre", "pdf"])
        cierre_cls.return_value.cerrar_emision_confirmada.assert_called_once()

    def test_fallo_cierre_local_no_genera_pdf(self):
        with (
            patch.object(FacturacionService, "emitir_en_arca", return_value=self._resultado_arca()),
            patch("services.facturacion_service.CierreLocalArcaService") as cierre_cls,
            patch.object(FacturacionService, "generar_pdf_fiscal") as pdf,
        ):
            cierre_cls.return_value.cerrar_emision_confirmada.return_value = type("Cierre", (), {"ok": False, "mensaje": "cierre"})()
            resultado = self._emitir_desde_resumen_minimo()
        self.assertEqual(resultado["etapa"], "cierre_local")
        cierre_cls.return_value.cerrar_emision_confirmada.assert_called_once()
        pdf.assert_not_called()

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


class ContextoFiscalBaseFacturacionTest(unittest.TestCase):
    """FASE 3: el contexto fiscal BASE que arma FacturacionService antes de invocar
    a ARCA debe quedar completo, validable y sin numero planificado ni secretos."""

    def _emisor_fiscal(self):
        return (
            30, "Emisor SA", "Fantasia SA", "20206871629", "Responsable Inscripto",
            "Factura A", 5, 1, "", "Homologación",
            "Calle Falsa 123", "IB-123456-7", "20200101", "cert.crt", "clave.key", "C:/trabajo",
        )

    def _cliente(self):
        return (20, "", "Cliente SA", "", "Direccion 1", "Localidad 1", "", "", "", "", "30712345678", "Responsable Inscripto")

    def _construir(self, **overrides):
        base = dict(
            ambiente_normalizado="HOMOLOGACION",
            emisor_fiscal=self._emisor_fiscal(),
            emisor_facturacion_id=40,
            cuit_emisor_normalizado="20206871629",
            punto_venta_num=5,
            cliente=self._cliente(),
            condicion_iva="Responsable Inscripto",
            documento_normalizado="30712345678",
            tipo_documento=80,
            documento_receptor=30712345678,
            tipo_comprobante=1,
            tipo_factura_normalizado="Factura A",
            fecha_comprobante="20260828",
            periodo_desde="20260801",
            periodo_hasta="20260831",
            vencimiento_pago_arca="20260910",
            moneda="PES",
            cotizacion=1,
            neto_factura=1000.0,
            importe_iva_factura=210.0,
            alicuota_iva=21.0,
            total_factura_fiscal=1210.0,
            importe_exento_factura=0.0,
            importe_tot_conc=0.0,
            importe_tributos=0.0,
            alicuotas_iva=[{"id": 5, "base_imponible": 1000.0, "importe": 210.0}],
            items_factura=[{
                "concepto": "Servicio", "descripcion": "Servicio mensual",
                "cantidad": 1, "precio_unitario": 1000.0, "importe": 1000.0,
            }],
        )
        base.update(overrides)
        return FacturacionService._construir_contexto_fiscal_base(**base)

    def _construir_factura_c(self, **overrides):
        base = dict(
            condicion_iva="Consumidor Final",
            documento_normalizado="",
            tipo_documento=99,
            documento_receptor=0,
            tipo_comprobante=11,
            tipo_factura_normalizado="Factura C",
            periodo_desde="",
            periodo_hasta="",
            vencimiento_pago_arca="",
            importe_iva_factura=0.0,
            alicuota_iva=0.0,
            total_factura_fiscal=1000.0,
            alicuotas_iva=[],
        )
        base.update(overrides)
        return self._construir(**base)

    def test_factura_a_construye_contexto_completo_y_valido(self):
        resultado = self._construir()
        self.assertTrue(resultado["ok"])
        validacion = ContextoFiscalService.validar(resultado["contexto"])
        self.assertTrue(validacion.valido, validacion.errores)

    def test_factura_c_construye_contexto_completo_y_valido(self):
        resultado = self._construir_factura_c()
        self.assertTrue(resultado["ok"])
        validacion = ContextoFiscalService.validar(resultado["contexto"])
        self.assertTrue(validacion.valido, validacion.errores)

    def test_ambiente_congelado(self):
        contexto = self._construir()["contexto"]
        self.assertEqual(contexto["ambiente"], "HOMOLOGACION")

    def test_emisor_congelado(self):
        emisor = self._construir()["contexto"]["emisor"]
        self.assertEqual(emisor["cuit"], "20206871629")
        self.assertEqual(emisor["razon_social"], "Emisor SA")
        self.assertEqual(emisor["nombre_fantasia"], "Fantasia SA")
        self.assertEqual(emisor["condicion_iva"], "Responsable Inscripto")
        self.assertEqual(emisor["domicilio"], "Calle Falsa 123")
        self.assertEqual(emisor["ingresos_brutos"], "IB-123456-7")
        self.assertEqual(emisor["punto_venta_num"], 5)

    def test_receptor_congelado(self):
        receptor = self._construir()["contexto"]["receptor"]
        self.assertEqual(receptor["cliente_id"], 20)
        self.assertEqual(receptor["razon_social"], "Cliente SA")
        self.assertEqual(receptor["documento_visible"], "30712345678")
        self.assertEqual(receptor["condicion_iva"], "Responsable Inscripto")

    def test_doctipo_docnro_correctos(self):
        receptor = self._construir()["contexto"]["receptor"]
        self.assertEqual(receptor["tipo_documento_receptor"], 80)
        self.assertEqual(receptor["documento_receptor"], 30712345678)

    def test_tipo_y_pv_correctos_factura_a_y_c(self):
        comprobante_a = self._construir()["contexto"]["comprobante"]
        self.assertEqual(comprobante_a["tipo_comprobante_num"], 1)
        self.assertEqual(comprobante_a["tipo_comprobante_texto"], "Factura A")
        self.assertEqual(comprobante_a["punto_venta_num"], 5)

        comprobante_c = self._construir_factura_c()["contexto"]["comprobante"]
        self.assertEqual(comprobante_c["tipo_comprobante_num"], 11)
        self.assertEqual(comprobante_c["tipo_comprobante_texto"], "Factura C")

    def test_numero_planificado_ausente_en_contexto_base(self):
        comprobante = self._construir()["contexto"]["comprobante"]
        self.assertIsNone(comprobante["numero_comprobante_planificado"])
        self.assertIsNone(comprobante["numero_textual_planificado"])

    def test_importes_correctos(self):
        importes = self._construir()["contexto"]["importes"]
        self.assertEqual(importes["total"], Decimal("1210"))
        self.assertEqual(importes["neto"], Decimal("1000"))
        self.assertEqual(importes["iva"], Decimal("210"))
        self.assertEqual(importes["exento"], Decimal("0"))

    def test_iva_alicuotas_correctas(self):
        iva = self._construir()["contexto"]["iva"]
        self.assertEqual(len(iva), 1)
        self.assertEqual(iva[0]["id"], 5)
        self.assertEqual(iva[0]["base_imponible"], Decimal("1000"))
        self.assertEqual(iva[0]["importe"], Decimal("210"))

    def test_items_correctos(self):
        items = self._construir()["contexto"]["items"]
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["descripcion"], "Servicio mensual")
        self.assertEqual(items[0]["subtotal"], Decimal("1000"))

    def test_periodo_y_vencimiento_correctos_cuando_existen(self):
        comprobante = self._construir()["contexto"]["comprobante"]
        self.assertEqual(comprobante["periodo_servicio_desde"], "2026-08-01")
        self.assertEqual(comprobante["periodo_servicio_hasta"], "2026-08-31")
        self.assertEqual(comprobante["vencimiento_pago"], "2026-09-10")

    def test_periodo_y_vencimiento_ausentes_no_rompen_contexto(self):
        comprobante = self._construir_factura_c()["contexto"]["comprobante"]
        self.assertIsNone(comprobante["periodo_servicio_desde"])
        self.assertIsNone(comprobante["periodo_servicio_hasta"])
        self.assertIsNone(comprobante["vencimiento_pago"])

    def test_contradiccion_cuit_emisor_bloquea_contexto(self):
        resultado = self._construir(cuit_emisor_normalizado="20111111112")
        self.assertFalse(resultado["ok"])
        self.assertTrue(any("contradiccion_cuit_emisor" in error for error in resultado["errores"]))


if __name__ == "__main__":
    unittest.main()