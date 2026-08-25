"""Fase 5E: el PDF/QR inicial (post-emision) reusa el mismo snapshot fiscal v1
construido y persistido en el cierre, sin reconsultar cliente/emisor/resumen.

CERO red, CERO ARCA real. Todo con fakes/mocks.
"""

import unittest
from decimal import Decimal
from unittest.mock import MagicMock, patch

from services.arca import ambiente_arca
from services.arca.pdf_fiscal_service import PDFFiscalService
from services.arca.snapshot_fiscal_pdf_adapter import (
    construir_datos_pdf_desde_snapshot,
    datos_qr_desde_snapshot,
)
from services.arca.snapshot_fiscal_service import construir_snapshot_fiscal_v1
from services.facturacion_service import FacturacionService


def _emisor_fiscal(cuit="20206871629", ambiente="Homologación"):
    return (
        30, "FM Master SRL", "FM Master", cuit, "Responsable Inscripto",
        "Factura A", 5, 1, "", ambiente, "Domicilio Fiscal 123",
        "123456", "20200101", "cert.crt", "clave.key", "C:/trabajo",
    )


def _snapshot_de_prueba(tipo_comprobante_texto="Factura A", ambiente="HOMOLOGACION"):
    es_a = tipo_comprobante_texto == "Factura A"
    return construir_snapshot_fiscal_v1(
        fuente="cierre_normal",
        creado_en="2026-08-24T10:00:00",
        ambiente=ambiente,
        emisor={
            "emisor_id": 1,
            "emisor_fiscal_id": 30,
            "razon_social": "FM Master SRL",
            "nombre_fantasia": "FM Master",
            "cuit": "20206871629",
            "condicion_iva": "Responsable Inscripto",
            "domicilio": "Domicilio Fiscal 123",
            "ingresos_brutos": "123456",
            "fecha_inicio_actividades": "2020-01-01",
            "punto_venta_num": 5,
        },
        receptor={
            "cliente_id": 20,
            "razon_social": "Cliente Responsable SA",
            "documento_visible": "20222222221" if es_a else "0",
            "condicion_iva": "Responsable Inscripto" if es_a else "Consumidor Final",
            "domicilio": "Calle 1 - Ciudad",
            "tipo_documento_receptor": 80 if es_a else 99,
            "documento_receptor": 20222222221 if es_a else 0,
        },
        comprobante={
            "fecha": "2026-08-23",
            "fecha_arca": "20260823",
            "concepto": 1,
            "concepto_descripcion": "Productos",
            "punto_venta_num": 5,
            "tipo_comprobante_num": 1 if es_a else 11,
            "tipo_comprobante_texto": tipo_comprobante_texto,
            "numero_comprobante_num": 123,
            "numero_textual": "00005-00000123",
            "periodo_servicio_desde": None,
            "periodo_servicio_hasta": None,
            "vencimiento_pago": None,
            "moneda": "PES",
            "cotizacion": Decimal("1"),
        },
        importes={
            "total": Decimal("1210") if es_a else Decimal("1000"),
            "neto": Decimal("1000"),
            "iva": Decimal("210") if es_a else Decimal("0"),
            "exento": Decimal("0"),
            "no_gravado": Decimal("0"),
            "tributos": Decimal("0"),
        },
        iva=(
            [{"id": 5, "base_imponible": Decimal("1000"), "importe": Decimal("210"), "porcentaje": Decimal("21")}]
            if es_a
            else []
        ),
        items=[
            {
                "concepto": "Servicio mensual",
                "descripcion": "Publicidad agosto",
                "cantidad": Decimal("1"),
                "precio_unitario": Decimal("1000"),
                "subtotal": Decimal("1000"),
            }
        ],
        autorizacion={
            "cae": "12345678901234",
            "vencimiento_cae": "2026-09-02",
            "vencimiento_cae_arca": "20260902",
            "tipo_cod_aut": "E",
            "resultado": "AUTORIZADO",
            "cerrado_en": "2026-08-23T10:00:00",
        },
    )


class GenerarPdfFiscalDesdeSnapshotTest(unittest.TestCase):
    """Nivel unitario: FacturacionService.generar_pdf_fiscal con snapshot presente."""

    def _llamar(self, snapshot, **overrides):
        argumentos = dict(
            cliente_id=999,
            tipo_factura="Factura A",
            tipo_factura_comprobante="XXXX-actual-no-usado",
            numero_comprobante=999999,
            codigo_factura="99999-99999999",
            carpeta_facturas="C:/carpeta_actual",
            emisor_fiscal=("emisor_actual_no_usado",),
            cuit_emisor="99999999999",
            punto_venta_num=999,
            cliente=("cliente_actual_no_usado",),
            condicion_iva="Monotributo",
            documento_normalizado="99999999",
            consulta={"moneda": "USD", "cotizacion": 999},
            fecha_comprobante="20990101",
            resumen_actual=object(),
            periodo_desde="20990101",
            periodo_hasta="20990131",
            neto_factura=999999,
            importe_iva_factura=999999,
            alicuota_iva=999,
            total_factura_fiscal=999999,
            items_factura=[{"descripcion": "item actual no usado"}],
            cae="00000000000000",
            vencimiento_cae="20990101",
            snapshot=snapshot,
        )
        argumentos.update(overrides)
        with patch.object(PDFFiscalService, "generar_factura_c", return_value={"ok": True, "ruta_pdf": "ruta.pdf"}) as mock_pdf:
            resultado = FacturacionService.generar_pdf_fiscal(**argumentos)
        return resultado, mock_pdf

    def test_factura_a_pdf_inicial_usa_snapshot(self):
        snapshot = _snapshot_de_prueba("Factura A")
        resultado, mock_pdf = self._llamar(snapshot)
        self.assertTrue(resultado["ok"])
        esperado = construir_datos_pdf_desde_snapshot(snapshot)
        kwargs = mock_pdf.call_args.kwargs
        self.assertEqual(kwargs["datos_receptor"], esperado["datos_receptor"])
        self.assertEqual(kwargs["datos_comprobante"], esperado["datos_comprobante"])

    def test_factura_c_pdf_inicial_usa_snapshot(self):
        snapshot = _snapshot_de_prueba("Factura C")
        resultado, mock_pdf = self._llamar(snapshot)
        self.assertTrue(resultado["ok"])
        esperado = construir_datos_pdf_desde_snapshot(snapshot)
        kwargs = mock_pdf.call_args.kwargs
        self.assertEqual(kwargs["datos_receptor"], esperado["datos_receptor"])
        self.assertEqual(kwargs["datos_comprobante"], esperado["datos_comprobante"])
        self.assertEqual(kwargs["datos_comprobante"]["importe_iva"], "0.00")

    def test_emisor_visible_viene_del_snapshot_no_de_masters_actuales(self):
        snapshot = _snapshot_de_prueba("Factura A")
        _, mock_pdf = self._llamar(snapshot, emisor_fiscal=("otro_completamente_distinto",), cuit_emisor="1")
        datos_emisor = mock_pdf.call_args.kwargs["datos_emisor"]
        self.assertEqual(datos_emisor["cuit"], "20206871629")
        self.assertEqual(datos_emisor["razon_social"], "FM Master SRL")
        self.assertEqual(datos_emisor["domicilio"], "Domicilio Fiscal 123")

    def test_receptor_visible_viene_del_snapshot_no_del_cliente_actual(self):
        snapshot = _snapshot_de_prueba("Factura A")
        _, mock_pdf = self._llamar(snapshot, cliente=("otro_cliente_actual",), condicion_iva="Monotributo")
        datos_receptor = mock_pdf.call_args.kwargs["datos_receptor"]
        self.assertEqual(datos_receptor["razon_social"], "Cliente Responsable SA")
        self.assertEqual(datos_receptor["condicion_iva"], "Responsable Inscripto")

    def test_items_vienen_del_snapshot_no_del_resumen_actual(self):
        snapshot = _snapshot_de_prueba("Factura A")
        _, mock_pdf = self._llamar(snapshot, items_factura=[{"descripcion": "otro item actual"}])
        items = mock_pdf.call_args.kwargs["datos_comprobante"]["items"]
        self.assertEqual(len(items), 1)
        self.assertIn("Publicidad agosto", items[0]["descripcion"])
        self.assertEqual(items[0]["importe"], "1000.00")

    def test_neto_iva_total_vienen_del_snapshot(self):
        snapshot = _snapshot_de_prueba("Factura A")
        _, mock_pdf = self._llamar(snapshot, neto_factura=1, importe_iva_factura=1, total_factura_fiscal=1)
        datos_comprobante = mock_pdf.call_args.kwargs["datos_comprobante"]
        self.assertEqual(datos_comprobante["importe_neto"], "1000.00")
        self.assertEqual(datos_comprobante["importe_iva"], "210.00")
        self.assertEqual(datos_comprobante["importe_total"], "1210.00")

    def test_ambiente_viene_del_snapshot(self):
        snapshot_homologacion = _snapshot_de_prueba("Factura A", ambiente="HOMOLOGACION")
        _, mock_pdf = self._llamar(snapshot_homologacion, emisor_fiscal=_emisor_fiscal(ambiente="Producción"))
        self.assertEqual(mock_pdf.call_args.kwargs["datos_comprobante"]["ambiente"], "HOMOLOGACION")

        snapshot_produccion = _snapshot_de_prueba("Factura A", ambiente="PRODUCCION")
        _, mock_pdf = self._llamar(snapshot_produccion, emisor_fiscal=_emisor_fiscal(ambiente="Homologación"))
        self.assertEqual(mock_pdf.call_args.kwargs["datos_comprobante"]["ambiente"], "PRODUCCION")

    def test_qr_viene_del_snapshot(self):
        snapshot = _snapshot_de_prueba("Factura A")
        _, mock_pdf = self._llamar(snapshot)
        datos_comprobante = mock_pdf.call_args.kwargs["datos_comprobante"]
        datos_emisor = mock_pdf.call_args.kwargs["datos_emisor"]
        # Los campos que pdf_fiscal_service usa para construir el QR deben coincidir con el snapshot.
        self.assertEqual(datos_emisor["cuit"], "20206871629")
        self.assertEqual(datos_comprobante["punto_venta_num"], 5)
        self.assertEqual(datos_comprobante["tipo_comprobante_num"], 1)
        self.assertEqual(datos_comprobante["numero_comprobante_num"], 123)
        self.assertEqual(datos_comprobante["cae"], "12345678901234")

    def test_datos_enviados_igualan_adapter_directo(self):
        snapshot = _snapshot_de_prueba("Factura A")
        _, mock_pdf = self._llamar(snapshot)
        esperado = construir_datos_pdf_desde_snapshot(snapshot)
        esperado["datos_emisor"]["carpeta_facturas"] = "C:/carpeta_actual"
        self.assertEqual(mock_pdf.call_args.kwargs["datos_emisor"], esperado["datos_emisor"])
        self.assertEqual(mock_pdf.call_args.kwargs["datos_receptor"], esperado["datos_receptor"])
        self.assertEqual(mock_pdf.call_args.kwargs["datos_comprobante"], esperado["datos_comprobante"])

    def test_qr_inicial_igual_a_qr_de_regeneracion_del_mismo_snapshot(self):
        snapshot = _snapshot_de_prueba("Factura A")
        _, mock_pdf = self._llamar(snapshot)
        datos_comprobante_inicial = mock_pdf.call_args.kwargs["datos_comprobante"]
        datos_emisor_inicial = mock_pdf.call_args.kwargs["datos_emisor"]

        # "Regeneracion" (5D): mismo snapshot, mismo adapter, sin pasar por facturacion_service.
        datos_regeneracion = construir_datos_pdf_desde_snapshot(snapshot)
        datos_qr_directo = datos_qr_desde_snapshot(snapshot)

        for clave in (
            "punto_venta_num",
            "tipo_comprobante_num",
            "numero_comprobante_num",
            "cae",
            "moneda",
            "cotizacion",
            "tipo_documento_receptor",
            "documento_receptor",
        ):
            self.assertEqual(datos_comprobante_inicial[clave], datos_regeneracion["datos_comprobante"][clave])
        self.assertEqual(datos_emisor_inicial["cuit"], datos_regeneracion["datos_emisor"]["cuit"])
        self.assertEqual(int(datos_emisor_inicial["cuit"]), datos_qr_directo["cuit_emisor"])

    def test_cambiar_cliente_despues_del_cierre_no_altera_pdf(self):
        snapshot = _snapshot_de_prueba("Factura A")
        _, mock_pdf_1 = self._llamar(snapshot, cliente_id=1, cliente=("cliente_1",))
        _, mock_pdf_2 = self._llamar(snapshot, cliente_id=2, cliente=("cliente_2_muy_distinto",))
        self.assertEqual(
            mock_pdf_1.call_args.kwargs["datos_receptor"],
            mock_pdf_2.call_args.kwargs["datos_receptor"],
        )

    def test_cambiar_emisor_despues_del_cierre_no_altera_cuit(self):
        snapshot = _snapshot_de_prueba("Factura A")
        _, mock_pdf_1 = self._llamar(snapshot, emisor_fiscal=("a",), cuit_emisor="111")
        _, mock_pdf_2 = self._llamar(snapshot, emisor_fiscal=("b", "c", "d"), cuit_emisor="222")
        self.assertEqual(
            mock_pdf_1.call_args.kwargs["datos_emisor"]["cuit"],
            mock_pdf_2.call_args.kwargs["datos_emisor"]["cuit"],
        )

    def test_cambiar_resumen_despues_no_altera_items_ni_importes(self):
        snapshot = _snapshot_de_prueba("Factura A")
        _, mock_pdf_1 = self._llamar(snapshot, items_factura=[{"descripcion": "x1"}], neto_factura=1)
        _, mock_pdf_2 = self._llamar(snapshot, items_factura=[{"descripcion": "x2"}, {"descripcion": "x3"}], neto_factura=2)
        self.assertEqual(
            mock_pdf_1.call_args.kwargs["datos_comprobante"]["items"],
            mock_pdf_2.call_args.kwargs["datos_comprobante"]["items"],
        )
        self.assertEqual(
            mock_pdf_1.call_args.kwargs["datos_comprobante"]["importe_neto"],
            mock_pdf_2.call_args.kwargs["datos_comprobante"]["importe_neto"],
        )


class GenerarPdfFiscalNoReconsultaTest(unittest.TestCase):
    """Con snapshot presente, no debe reconsultarse cliente/emisor/resumen."""

    @patch("services.cliente_service.ClienteService.obtener")
    @patch("services.emisor_fiscal_service.EmisorFiscalService.obtener")
    @patch("services.resumen_service.ResumenService.obtener")
    def test_no_reconsulta_cliente_emisor_ni_resumen(self, mock_resumen, mock_emisor, mock_cliente):
        snapshot = _snapshot_de_prueba("Factura A")
        with patch.object(PDFFiscalService, "generar_factura_c", return_value={"ok": True, "ruta_pdf": "ruta.pdf"}):
            resultado = FacturacionService.generar_pdf_fiscal(
                cliente_id=1,
                tipo_factura="Factura A",
                tipo_factura_comprobante="Factura A",
                numero_comprobante=123,
                codigo_factura="00005-00000123",
                carpeta_facturas="C:/carpeta",
                emisor_fiscal=(),
                cuit_emisor="",
                punto_venta_num=5,
                cliente=(),
                condicion_iva="",
                documento_normalizado="",
                consulta={},
                fecha_comprobante="",
                resumen_actual=None,
                periodo_desde="",
                periodo_hasta="",
                neto_factura=0,
                importe_iva_factura=0,
                alicuota_iva=0,
                total_factura_fiscal=0,
                items_factura=[],
                cae="",
                vencimiento_cae="",
                snapshot=snapshot,
            )
        self.assertTrue(resultado["ok"])
        mock_cliente.assert_not_called()
        mock_emisor.assert_not_called()
        mock_resumen.assert_not_called()


class EmitirDesdeResumenIntegraSnapshotEnPdfTest(unittest.TestCase):
    """Integracion: emitir_desde_resumen pasa el snapshot recien construido al PDF inicial."""

    def _emitir(self, pdf_ok=True, cierre_ok=True):
        orden = []
        resultado_arca = {
            "ok": True, "intento_id": 77, "consulta": {"moneda": "PES", "cotizacion": 1.0},
            "fecha_comprobante": "20260823", "numero_comprobante": 123, "punto_venta_num": 5,
            "cae": "12345678901234", "vencimiento_cae": "20260902",
        }
        cliente_final = (
            20, "", "Cliente Responsable SA", "", "", "Calle 1", "Ciudad",
            "", "", "", "20222222221", "Responsable Inscripto",
        )
        emisor = _emisor_fiscal(ambiente="Homologación")
        fiscal = {
            "ok": True, "tipo_comprobante": 1, "neto_factura": 1000.0, "alicuota_iva": 21.0,
            "importe_iva_factura": 210.0, "total_factura_fiscal": 1210.0, "importe_exento_factura": 0.0,
            "importe_tot_conc": 0.0, "importe_tributos": 0.0,
            "alicuotas_iva": [{"id": 5, "base_imponible": 1000.0, "importe": 210.0}],
            "condicion_iva_receptor_id": 1,
        }
        resumen = type(
            "Resumen", (), {
                "id": 10, "estado_facturacion": "Pendiente", "cliente_id": 20,
                "total": 1000.0, "conceptos": [object()], "fecha_vencimiento": "",
            },
        )()

        def cierre_side_effect(*_args, **kwargs):
            orden.append("cierre")
            self.snapshot_json_recibido = kwargs.get("snapshot_fiscal_json")
            if not cierre_ok:
                return type("Cierre", (), {"ok": False, "mensaje": "cierre fallo"})()
            return type("Cierre", (), {"ok": True, "factura_arca_id": 99})()

        cierre_mock = MagicMock(side_effect=cierre_side_effect)

        def pdf_side_effect(**kwargs):
            orden.append("pdf")
            self.snapshot_recibido_en_pdf = kwargs.get("snapshot")
            return {"ok": pdf_ok, "ruta_pdf": "ruta.pdf" if pdf_ok else "", "errores": [] if pdf_ok else ["pdf"]}

        with (
            patch("services.facturacion_service.ResumenService.obtener", return_value=resumen),
            patch("services.facturacion_service.FacturaArcaService.listar_por_resumen", return_value=[]),
            patch("services.facturacion_service.IntentoEmisionArcaService.listar_activos_por_resumen", return_value=[]),
            patch.object(FacturacionService, "validar_resumen_para_facturar", return_value={"ok": True}),
            patch.object(FacturacionService, "resolver_cliente", return_value={"ok": True, "cliente": cliente_final}),
            patch.object(FacturacionService, "resolver_conceptos", return_value={"ok": True, "resumen": resumen, "conceptos": [object()]}),
            patch.object(FacturacionService, "resolver_emisor", return_value={"ok": True, "emisor_fiscal": emisor}),
            patch.object(FacturacionService, "_resolver_emisor_facturacion_id", return_value=(40, "id")),
            patch.object(
                FacturacionService, "_armar_items_factura_desde_resumen",
                return_value=[{"importe": 1000.0, "cantidad": 1.0, "precio_unitario": 1000.0, "descripcion": "Servicio", "concepto": "Servicio"}],
            ),
            patch.object(FacturacionService, "calcular_importes_fiscales", return_value=fiscal),
            patch("services.facturacion_service.FacturaArcaService.validar_pre_guardado", return_value={"ok": True}),
            patch.object(FacturacionService, "_sumar_importes_items", return_value=1000.0),
            patch.object(FacturacionService, "emitir_en_arca", return_value=resultado_arca),
            patch("services.facturacion_service.CierreLocalArcaService") as cierre_cls,
            patch.object(FacturacionService, "generar_pdf_fiscal", side_effect=pdf_side_effect),
        ):
            cierre_cls.return_value.cerrar_emision_confirmada.side_effect = cierre_mock
            resultado = FacturacionService.emitir_desde_resumen(
                10, {"tipo_factura": "Factura A", "condicion_iva": "Responsable Inscripto"}
            )
        return resultado, orden

    def test_pdf_recibe_snapshot_no_nulo_con_ambiente_congelado(self):
        self.snapshot_recibido_en_pdf = None
        resultado, orden = self._emitir(pdf_ok=True)
        self.assertTrue(resultado["ok"])
        self.assertEqual(orden, ["cierre", "pdf"])
        self.assertIsNotNone(self.snapshot_recibido_en_pdf)
        self.assertEqual(self.snapshot_recibido_en_pdf["version"], 1)
        self.assertEqual(self.snapshot_recibido_en_pdf["ambiente"], "HOMOLOGACION")

    def test_cierre_ocurre_antes_del_pdf(self):
        self.snapshot_recibido_en_pdf = None
        resultado, orden = self._emitir(pdf_ok=True)
        self.assertEqual(orden, ["cierre", "pdf"])

    def test_si_cierre_falla_no_se_genera_pdf(self):
        self.snapshot_recibido_en_pdf = None
        resultado, orden = self._emitir(cierre_ok=False)
        self.assertEqual(resultado["etapa"], "cierre_local")
        self.assertEqual(orden, ["cierre"])
        self.assertIsNone(self.snapshot_recibido_en_pdf)

    def test_si_pdf_falla_snapshot_y_factura_permanecen(self):
        self.snapshot_json_recibido = None
        resultado, orden = self._emitir(pdf_ok=False)
        self.assertEqual(resultado["etapa"], "pdf")
        self.assertEqual(resultado["factura_id"], 99)
        self.assertEqual(orden, ["cierre", "pdf"])
        # El cierre (con snapshot) ya se habia confirmado antes del fallo del PDF.
        self.assertIsNotNone(self.snapshot_json_recibido)


if __name__ == "__main__":
    unittest.main()
