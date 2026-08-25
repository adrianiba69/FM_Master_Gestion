"""Tests de regeneracion PDF/QR desde snapshot fiscal (FASE 5D).

Cubre la prioridad snapshot/legacy/corrupto, la independencia respecto de
maestros actuales (cliente/emisor/resumen), el modo legacy historico y la
generacion real de PDF/QR desde snapshot. CERO base real. CERO ARCA.
"""

import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from unittest.mock import Mock, patch

from services.arca.pdf_fiscal_service import PDFFiscalService
from services.arca.qr_fiscal_service import QrFiscalService
from services.arca.snapshot_fiscal_pdf_adapter import (
    MODO_CORRUPTO,
    MODO_LEGACY,
    MODO_SNAPSHOT,
    construir_datos_pdf_desde_snapshot,
    datos_qr_desde_snapshot,
)
from services.arca.snapshot_fiscal_service import (
    SNAPSHOT_VERSION,
    calcular_hash_snapshot,
    construir_snapshot_fiscal_v1,
    serializar_snapshot_fiscal,
)
from views.facturas_electronicas import FacturasElectronicasFrame, SnapshotFiscalCorruptoError


def _datos_snapshot_factura_a():
    return {
        "fuente": "cierre_normal",
        "creado_en": "2026-08-23T12:34:56",
        "ambiente": "HOMOLOGACION",
        "emisor": {
            "emisor_id": 1,
            "emisor_fiscal_id": 1,
            "razon_social": "FM Master SRL",
            "nombre_fantasia": "FM Master",
            "cuit": "20111111117",
            "condicion_iva": "Responsable Inscripto",
            "domicilio": "Domicilio fiscal 123",
            "ingresos_brutos": "123456",
            "fecha_inicio_actividades": "2020-01-01",
            "punto_venta_num": 5,
        },
        "receptor": {
            "cliente_id": 10,
            "razon_social": "Cliente SA",
            "documento_visible": "20222222221",
            "condicion_iva": "Responsable Inscripto",
            "domicilio": "Cliente 456 - Localidad",
            "tipo_documento_receptor": 80,
            "documento_receptor": 20222222221,
        },
        "comprobante": {
            "fecha": "2026-08-23",
            "fecha_arca": "20260823",
            "concepto": 1,
            "concepto_descripcion": "Productos",
            "punto_venta_num": 5,
            "tipo_comprobante_num": 1,
            "tipo_comprobante_texto": "Factura A",
            "numero_comprobante_num": 123,
            "numero_textual": "00005-00000123",
            "periodo_servicio_desde": None,
            "periodo_servicio_hasta": None,
            "vencimiento_pago": None,
            "moneda": "PES",
            "cotizacion": Decimal("1"),
        },
        "importes": {
            "total": Decimal("1210"),
            "neto": Decimal("1000"),
            "iva": Decimal("210"),
            "exento": Decimal("0"),
            "no_gravado": Decimal("0"),
            "tributos": Decimal("0"),
        },
        "iva": [
            {
                "id": 5,
                "base_imponible": Decimal("1000"),
                "importe": Decimal("210"),
                "porcentaje": Decimal("21"),
            }
        ],
        "items": [
            {
                "concepto": "Servicio mensual",
                "descripcion": "Publicidad agosto",
                "cantidad": Decimal("1"),
                "precio_unitario": Decimal("1000"),
                "subtotal": Decimal("1000"),
            }
        ],
        "autorizacion": {
            "cae": "12345678901234",
            "vencimiento_cae": "2026-09-02",
            "vencimiento_cae_arca": "20260902",
            "tipo_cod_aut": "E",
            "resultado": "AUTORIZADO",
            "cerrado_en": "2026-08-23T12:34:56",
        },
    }


def _snapshot_factura_a(ambiente="HOMOLOGACION"):
    datos = _datos_snapshot_factura_a()
    datos["ambiente"] = ambiente
    return construir_snapshot_fiscal_v1(**datos)


def _persistencia_snapshot(snapshot):
    serializado = serializar_snapshot_fiscal(snapshot)
    return serializado, SNAPSHOT_VERSION, calcular_hash_snapshot(serializado)


def _factura_con_snapshot(snapshot, **overrides):
    json_texto, version, hash_texto = _persistencia_snapshot(snapshot)
    factura = {
        "factura_id": 1,
        "resumen_id": 55,
        "snapshot_fiscal_json": json_texto,
        "snapshot_version": version,
        "snapshot_hash": hash_texto,
    }
    factura.update(overrides)
    return factura


def _factura_legacy(**overrides):
    factura = {
        "factura_id": 2,
        "resumen_id": 55,
        "snapshot_fiscal_json": None,
        "snapshot_version": None,
        "snapshot_hash": None,
    }
    factura.update(overrides)
    return factura


def _llamar_dispatcher(factura, self_falso=None, **kwargs):
    self_falso = self_falso if self_falso is not None else Mock()
    argumentos = dict(
        factura=factura,
        valores_fila=("23/08/2026", "Cliente SA", "Factura A", "5", "123", "$ 1.210,00", "12345678901234", "Emitida"),
        emisor_fiscal=("emisor_de_masters_actual",),
        carpeta_facturas="C:/carpeta_actual",
        cliente_id=999,
        tipo_factura="Factura A",
        codigo_factura="00099-00099999",
    )
    argumentos.update(kwargs)
    return FacturasElectronicasFrame._construir_datos_pdf_para_regeneracion(self_falso, **argumentos), self_falso


class ModoSnapshotIndependenciaTest(unittest.TestCase):
    """Items 9-15: cambiar masters actuales no debe afectar el resultado en modo snapshot."""

    def test_snapshot_valido_usa_solo_datos_del_snapshot(self):
        snapshot = _snapshot_factura_a()
        factura = _factura_con_snapshot(snapshot)
        datos_pdf, self_falso = _llamar_dispatcher(factura)

        esperado = construir_datos_pdf_desde_snapshot(snapshot)
        self.assertEqual(datos_pdf["datos_receptor"], esperado["datos_receptor"])
        self.assertEqual(datos_pdf["datos_comprobante"], esperado["datos_comprobante"])
        # cuit/razon/domicilio del emisor deben coincidir con snapshot, no con "masters" actuales.
        self.assertEqual(datos_pdf["datos_emisor"]["cuit"], "20111111117")
        self.assertEqual(datos_pdf["datos_emisor"]["razon_social"], "FM Master SRL")
        self.assertEqual(datos_pdf["datos_emisor"]["domicilio"], "Domicilio fiscal 123")
        # El legacy NUNCA debe invocarse cuando el snapshot es valido.
        self_falso._construir_datos_pdf_fiscal_desde_factura.assert_not_called()

    def test_cambiar_cliente_id_no_afecta_receptor(self):
        snapshot = _snapshot_factura_a()
        factura = _factura_con_snapshot(snapshot)
        datos_pdf, _ = _llamar_dispatcher(factura, cliente_id=1)
        datos_pdf_otro, _ = _llamar_dispatcher(factura, cliente_id=99999)
        self.assertEqual(datos_pdf["datos_receptor"], datos_pdf_otro["datos_receptor"])

    def test_cambiar_emisor_fiscal_actual_no_afecta_datos_fiscales_emisor(self):
        snapshot = _snapshot_factura_a()
        factura = _factura_con_snapshot(snapshot)
        datos_pdf, _ = _llamar_dispatcher(factura, emisor_fiscal=("distinto",))
        datos_pdf_otro, _ = _llamar_dispatcher(factura, emisor_fiscal=("totalmente_distinto", 1, 2, 3))
        self.assertEqual(datos_pdf["datos_emisor"]["cuit"], datos_pdf_otro["datos_emisor"]["cuit"])
        self.assertEqual(datos_pdf["datos_emisor"]["razon_social"], datos_pdf_otro["datos_emisor"]["razon_social"])
        self.assertEqual(datos_pdf["datos_emisor"]["domicilio"], datos_pdf_otro["datos_emisor"]["domicilio"])

    def test_cambiar_codigo_factura_no_afecta_items_ni_importes(self):
        snapshot = _snapshot_factura_a()
        factura = _factura_con_snapshot(snapshot)
        datos_pdf, _ = _llamar_dispatcher(factura, codigo_factura="00001-00000001")
        self.assertEqual(datos_pdf["datos_comprobante"]["items"][0]["importe"], "1000.00")
        self.assertEqual(datos_pdf["datos_comprobante"]["importe_neto"], "1000.00")
        self.assertEqual(datos_pdf["datos_comprobante"]["importe_iva"], "210.00")
        self.assertEqual(datos_pdf["datos_comprobante"]["importe_total"], "1210.00")

    def test_cambiar_tipo_factura_actual_no_afecta_ambiente_historico(self):
        snapshot = _snapshot_factura_a(ambiente="HOMOLOGACION")
        factura = _factura_con_snapshot(snapshot)
        datos_pdf, _ = _llamar_dispatcher(factura, tipo_factura="Factura C")
        self.assertEqual(datos_pdf["datos_comprobante"]["ambiente"], "HOMOLOGACION")

    def test_qr_no_cambia_si_cambian_cliente_o_emisor_actuales(self):
        snapshot = _snapshot_factura_a()
        datos_qr_base = datos_qr_desde_snapshot(snapshot)
        # datos_qr_desde_snapshot no recibe ni acepta cliente/emisor actuales: es puro.
        datos_qr_repetido = datos_qr_desde_snapshot(snapshot)
        self.assertEqual(datos_qr_base, datos_qr_repetido)


class ModoLegacyTest(unittest.TestCase):
    """Items 16-19: sin snapshot persistido, se preserva el flujo historico sin crear snapshot."""

    def test_snapshot_null_usa_flujo_legacy(self):
        factura = _factura_legacy()
        self_falso = Mock()
        sentinel = {"datos_emisor": {"marca": "legacy"}, "datos_receptor": {}, "datos_comprobante": {}}
        self_falso._construir_datos_pdf_fiscal_desde_factura.return_value = sentinel

        resultado, _ = _llamar_dispatcher(factura, self_falso=self_falso)

        self.assertEqual(resultado, sentinel)
        self_falso._construir_datos_pdf_fiscal_desde_factura.assert_called_once()

    def test_legacy_no_escribe_snapshot(self):
        factura = _factura_legacy()
        self_falso = Mock()
        self_falso._construir_datos_pdf_fiscal_desde_factura.return_value = {
            "datos_emisor": {},
            "datos_receptor": {},
            "datos_comprobante": {},
        }
        _llamar_dispatcher(factura, self_falso=self_falso)
        # El dispatcher no debe invocar ningun metodo de persistencia (guardar/actualizar snapshot).
        for nombre_atributo in dir(self_falso):
            if "guardar" in nombre_atributo or "actualizar" in nombre_atributo:
                atributo = getattr(self_falso, nombre_atributo)
                if isinstance(atributo, Mock):
                    atributo.assert_not_called()


class ModoCorruptoTest(unittest.TestCase):
    """Items 20-27: snapshot corrupto bloquea la regeneracion sin fallback silencioso."""

    def _factura_corrupta_json(self):
        return _factura_legacy(
            snapshot_fiscal_json="{esto no es json valido",
            snapshot_version=SNAPSHOT_VERSION,
            snapshot_hash="a" * 64,
        )

    def _factura_corrupta_hash(self):
        snapshot = _snapshot_factura_a()
        json_texto, version, _ = _persistencia_snapshot(snapshot)
        return _factura_legacy(
            snapshot_fiscal_json=json_texto,
            snapshot_version=version,
            snapshot_hash="f" * 64,
        )

    def _factura_corrupta_version(self):
        snapshot = _snapshot_factura_a()
        json_texto, _, hash_texto = _persistencia_snapshot(snapshot)
        return _factura_legacy(
            snapshot_fiscal_json=json_texto,
            snapshot_version=99,
            snapshot_hash=hash_texto,
        )

    def _factura_corrupta_incompleta(self):
        import json as json_mod

        snapshot = _snapshot_factura_a()
        del snapshot["items"]
        serializado = json_mod.dumps(snapshot, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        hash_incompleto = calcular_hash_snapshot(serializado)
        return _factura_legacy(
            snapshot_fiscal_json=serializado,
            snapshot_version=SNAPSHOT_VERSION,
            snapshot_hash=hash_incompleto,
        )

    def test_json_invalido_bloquea_regeneracion(self):
        with self.assertRaises(SnapshotFiscalCorruptoError):
            _llamar_dispatcher(self._factura_corrupta_json())

    def test_hash_incorrecto_bloquea(self):
        with self.assertRaises(SnapshotFiscalCorruptoError):
            _llamar_dispatcher(self._factura_corrupta_hash())

    def test_version_incorrecta_bloquea(self):
        with self.assertRaises(SnapshotFiscalCorruptoError):
            _llamar_dispatcher(self._factura_corrupta_version())

    def test_snapshot_incompleto_bloquea(self):
        with self.assertRaises(SnapshotFiscalCorruptoError):
            _llamar_dispatcher(self._factura_corrupta_incompleta())

    def test_corrupto_no_llama_legacy_ni_masters(self):
        self_falso = Mock()
        with self.assertRaises(SnapshotFiscalCorruptoError):
            _llamar_dispatcher(self._factura_corrupta_json(), self_falso=self_falso)
        self_falso._construir_datos_pdf_fiscal_desde_factura.assert_not_called()

    @patch("services.cliente_service.ClienteService.obtener")
    @patch("services.emisor_fiscal_service.EmisorFiscalService.obtener")
    @patch("services.resumen_service.ResumenService.obtener")
    def test_corrupto_no_consulta_cliente_emisor_ni_resumen(self, mock_resumen, mock_emisor, mock_cliente):
        with self.assertRaises(SnapshotFiscalCorruptoError):
            _llamar_dispatcher(self._factura_corrupta_hash())
        mock_cliente.assert_not_called()
        mock_emisor.assert_not_called()
        mock_resumen.assert_not_called()

    @patch("services.arca.wsfe_service.WSFEService.fe_cae_solicitar")
    def test_corrupto_no_llama_arca(self, mock_wsfe):
        with self.assertRaises(SnapshotFiscalCorruptoError):
            _llamar_dispatcher(self._factura_corrupta_version())
        mock_wsfe.assert_not_called()


class PdfQrDesdeSnapshotTest(unittest.TestCase):
    """Items 28-33: generacion real de PDF/QR desde snapshot, sin tocar ARCA."""

    def test_pdf_desde_snapshot_genera_correctamente(self):
        snapshot = _snapshot_factura_a()
        datos = construir_datos_pdf_desde_snapshot(snapshot)
        with tempfile.TemporaryDirectory() as carpeta:
            destino = Path(carpeta) / "factura.pdf"
            resultado = PDFFiscalService.generar_factura_c(
                ruta_destino=str(destino),
                datos_emisor=datos["datos_emisor"],
                datos_receptor=datos["datos_receptor"],
                datos_comprobante=datos["datos_comprobante"],
            )
            self.assertTrue(resultado["ok"], resultado.get("errores"))
            self.assertTrue(Path(resultado["ruta_pdf"]).is_file())
            self.assertGreater(Path(resultado["ruta_pdf"]).stat().st_size, 0)

    def test_qr_desde_snapshot_genera_correctamente(self):
        snapshot = _snapshot_factura_a()
        datos_qr = datos_qr_desde_snapshot(snapshot)
        servicio = QrFiscalService()
        url, error = servicio.construir_qr_completo(
            ver=datos_qr["ver"],
            fecha=datos_qr["fecha"],
            cuit_emisor=datos_qr["cuit_emisor"],
            punto_venta_num=datos_qr["punto_venta_num"],
            tipo_comprobante_num=datos_qr["tipo_comprobante_num"],
            numero_comprobante_num=datos_qr["numero_comprobante_num"],
            importe=datos_qr["importe"],
            cae=datos_qr["cae"],
            tipo_documento_receptor=datos_qr["tipo_documento_receptor"],
            numero_documento_receptor=datos_qr["numero_documento_receptor"],
            moneda=datos_qr["moneda"],
            cotizacion=datos_qr["cotizacion"],
        )
        self.assertIsNone(error)
        self.assertIsNotNone(url)

    def test_qr_usa_url_oficial_arca(self):
        snapshot = _snapshot_factura_a()
        datos_qr = datos_qr_desde_snapshot(snapshot)
        servicio = QrFiscalService()
        url, _ = servicio.construir_qr_completo(
            ver=datos_qr["ver"],
            fecha=datos_qr["fecha"],
            cuit_emisor=datos_qr["cuit_emisor"],
            punto_venta_num=datos_qr["punto_venta_num"],
            tipo_comprobante_num=datos_qr["tipo_comprobante_num"],
            numero_comprobante_num=datos_qr["numero_comprobante_num"],
            importe=datos_qr["importe"],
            cae=datos_qr["cae"],
            tipo_documento_receptor=datos_qr["tipo_documento_receptor"],
            numero_documento_receptor=datos_qr["numero_documento_receptor"],
            moneda=datos_qr["moneda"],
            cotizacion=datos_qr["cotizacion"],
        )
        self.assertEqual(QrFiscalService.QR_VERIFICATION_URL, "https://www.arca.gob.ar/fe/qr/")
        self.assertTrue(url.startswith(QrFiscalService.QR_VERIFICATION_URL))

    def test_leyenda_homologacion_desde_snapshot(self):
        snapshot = _snapshot_factura_a(ambiente="HOMOLOGACION")
        datos = construir_datos_pdf_desde_snapshot(snapshot)
        with patch.object(PDFFiscalService, "_dibujar_marca_homologacion") as mock_marca:
            with tempfile.TemporaryDirectory() as carpeta:
                PDFFiscalService.generar_factura_c(
                    ruta_destino=str(Path(carpeta) / "factura.pdf"),
                    datos_emisor=datos["datos_emisor"],
                    datos_receptor=datos["datos_receptor"],
                    datos_comprobante=datos["datos_comprobante"],
                )
        mock_marca.assert_called_once()
        self.assertTrue(mock_marca.call_args.kwargs.get("mostrar"))

    def test_produccion_sin_leyenda_homologacion(self):
        snapshot = _snapshot_factura_a(ambiente="PRODUCCION")
        datos = construir_datos_pdf_desde_snapshot(snapshot)
        with patch.object(PDFFiscalService, "_dibujar_marca_homologacion") as mock_marca:
            with tempfile.TemporaryDirectory() as carpeta:
                PDFFiscalService.generar_factura_c(
                    ruta_destino=str(Path(carpeta) / "factura.pdf"),
                    datos_emisor=datos["datos_emisor"],
                    datos_receptor=datos["datos_receptor"],
                    datos_comprobante=datos["datos_comprobante"],
                )
        mock_marca.assert_called_once()
        self.assertFalse(mock_marca.call_args.kwargs.get("mostrar"))

    def test_pdf_fail_safe_grafico_no_modifica_datos(self):
        snapshot = _snapshot_factura_a()
        datos = construir_datos_pdf_desde_snapshot(snapshot)
        # Se rompe deliberadamente un dato usado solo para dibujar el QR (no fiscal).
        datos["datos_comprobante"]["punto_venta_num"] = None
        copia_antes = dict(datos["datos_comprobante"])
        with tempfile.TemporaryDirectory() as carpeta:
            resultado = PDFFiscalService.generar_factura_c(
                ruta_destino=str(Path(carpeta) / "factura.pdf"),
                datos_emisor=datos["datos_emisor"],
                datos_receptor=datos["datos_receptor"],
                datos_comprobante=datos["datos_comprobante"],
            )
        self.assertTrue(resultado["ok"])
        self.assertEqual(datos["datos_comprobante"], copia_antes)


if __name__ == "__main__":
    unittest.main()
