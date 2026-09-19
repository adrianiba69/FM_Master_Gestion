"""Tests de integracion de POST-E2E 3B.3B: persistencia de ruta PDF fiscal
DESPUES de una generacion de PDF exitosa (services.facturacion_service).

Reutiliza el andamiaje de mocks de tests.test_cierre_intento_exitoso para
aislar la etapa de persistencia de ruta sin depender de ARCA/WSAA/WSFE real
ni de SQLite real.
"""

import unittest
from unittest.mock import patch

from services.facturacion_service import FacturacionService
from tests._cierre_contexto_helper import resultado_snapshot_cierre_para_test

RUTA_PDF_CANONICA_HOMOLOGACION = r"C:\trabajo\Homologacion\facturas\x.pdf"


class PersistenciaRutaPdfPostGeneracionTest(unittest.TestCase):

    def _resultado_arca(self):
        return {
            "ok": True, "intento_id": 77, "consulta": {}, "fecha_comprobante": "20260816",
            "numero_comprobante": 123, "punto_venta_num": 5, "cae": "71345678901234", "vencimiento_cae": "20260826",
        }

    def _emitir_desde_resumen_minimo(self, pdf_resultado, actualizar_ruta_pdf_side_effect=None):
        resumen = type("Resumen", (), {
            "id": 10, "estado_facturacion": "Pendiente", "cliente_id": 20, "total": 100, "conceptos": [object()],
        })()
        cliente = (20, "", "Cliente", "", "", "", "", "", "", "", "30712345678", "Responsable Inscripto")
        emisor = (
            30, "Emisor", "", "20206871629", "Responsable Inscripto", "Factura A", 5, 1, "",
            "Homologación", "", "", "", "cert.crt", "clave.key", "C:/trabajo",
        )
        fiscal = {
            "ok": True, "tipo_comprobante": 1, "neto_factura": 100, "alicuota_iva": 21,
            "importe_iva_factura": 21, "total_factura_fiscal": 121, "importe_exento_factura": 0,
            "importe_tot_conc": 0, "importe_tributos": 0, "alicuotas_iva": [], "condicion_iva_receptor_id": 1,
        }
        cierre_obj = type("Cierre", (), {"ok": True, "factura_arca_id": 99, "mensaje": ""})()

        with (
            patch("services.facturacion_service.ResumenService.obtener", return_value=resumen),
            patch("services.facturacion_service.FacturaArcaService.listar_por_resumen", return_value=[]),
            patch("services.facturacion_service.IntentoEmisionArcaService.listar_activos_por_resumen", return_value=[]),
            patch.object(FacturacionService, "validar_resumen_para_facturar", return_value={"ok": True}),
            patch.object(FacturacionService, "resolver_cliente", return_value={"ok": True, "cliente": cliente}),
            patch.object(FacturacionService, "resolver_conceptos", return_value={"ok": True, "resumen": resumen, "conceptos": [object()]}),
            patch.object(FacturacionService, "resolver_emisor", return_value={"ok": True, "emisor_fiscal": emisor}),
            patch.object(FacturacionService, "_resolver_emisor_facturacion_id", return_value=(40, "id")),
            patch.object(
                FacturacionService,
                "_armar_items_factura_desde_resumen",
                return_value=[{"importe": 100, "cantidad": 1, "precio_unitario": 100, "descripcion": "Servicio"}],
            ),
            patch.object(FacturacionService, "calcular_importes_fiscales", return_value=fiscal),
            patch("services.facturacion_service.FacturaArcaService.validar_pre_guardado", return_value={"ok": True}),
            patch.object(FacturacionService, "_sumar_importes_items", return_value=100),
            patch.object(FacturacionService, "_obtener_periodo_facturado", return_value=("", "")),
            patch.object(FacturacionService, "emitir_en_arca", return_value=self._resultado_arca()),
            patch("services.facturacion_service.CierreLocalArcaService") as cierre_cls,
            patch.object(
                FacturacionService,
                "_construir_snapshot_desde_contexto_persistido",
                return_value=resultado_snapshot_cierre_para_test(),
            ),
            patch.object(FacturacionService, "generar_pdf_fiscal", return_value=pdf_resultado),
            patch(
                "services.facturacion_service.FacturaArcaService.actualizar_ruta_pdf",
                side_effect=actualizar_ruta_pdf_side_effect,
            ) as actualizar_ruta_pdf,
        ):
            cierre_cls.return_value.cerrar_emision_confirmada.return_value = cierre_obj
            resultado = FacturacionService.emitir_desde_resumen(
                10, {"tipo_factura": "Factura A", "condicion_iva": "Responsable Inscripto"}
            )
        return resultado, actualizar_ruta_pdf

    # 11) PDF exitoso -> persiste ruta
    def test_pdf_exitoso_persiste_ruta(self):
        pdf_ok = {"ok": True, "ruta_pdf": RUTA_PDF_CANONICA_HOMOLOGACION, "errores": []}
        resultado, actualizar_ruta_pdf = self._emitir_desde_resumen_minimo(pdf_ok)

        self.assertTrue(resultado["ok"])
        actualizar_ruta_pdf.assert_called_once()
        self.assertEqual(actualizar_ruta_pdf.call_args.args[0], 99)
        self.assertNotIn("advertencias", resultado)

    # 12) PDF fallido -> no persiste ruta
    def test_pdf_fallido_no_persiste_ruta(self):
        pdf_fail = {"ok": False, "errores": ["no se pudo generar el pdf"]}
        resultado, actualizar_ruta_pdf = self._emitir_desde_resumen_minimo(pdf_fail)

        self.assertFalse(resultado["ok"])
        self.assertEqual(resultado["etapa"], "pdf")
        actualizar_ruta_pdf.assert_not_called()

    # 13) PDF exitoso + fallo UPDATE ruta -> factura/PDF siguen validos + advertencia
    def test_pdf_exitoso_con_fallo_de_persistencia_no_revierte_nada(self):
        pdf_ok = {"ok": True, "ruta_pdf": RUTA_PDF_CANONICA_HOMOLOGACION, "errores": []}
        resultado, actualizar_ruta_pdf = self._emitir_desde_resumen_minimo(
            pdf_ok, actualizar_ruta_pdf_side_effect=RuntimeError("db bloqueada")
        )

        actualizar_ruta_pdf.assert_called_once()
        self.assertTrue(resultado["ok"])
        self.assertEqual(resultado["etapa"], "ok")
        self.assertEqual(resultado["factura_id"], 99)
        self.assertEqual(resultado["cae"], "71345678901234")
        self.assertIn("advertencias", resultado)
        self.assertTrue(any("no se pudo persistir" in adv.lower() for adv in resultado["advertencias"]))


if __name__ == "__main__":
    unittest.main()
