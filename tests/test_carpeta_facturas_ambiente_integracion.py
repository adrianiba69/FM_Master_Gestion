"""Tests de integracion de la separacion canonica de PDFs por ambiente
(POST-E2E 3B.2): emision inicial (services.facturacion_service) y
regeneracion/localizacion (views.facturas_electronicas).

CERO DB real. CERO filesystem real (PDFFiscalService.generar_factura_c se
mockea). CERO ARCA/WSAA/WSFE.
"""

import unittest
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

from services.arca.snapshot_fiscal_service import (
    SNAPSHOT_VERSION,
    calcular_hash_snapshot,
    construir_snapshot_fiscal_v1,
    serializar_snapshot_fiscal,
)
from services.facturacion_service import FacturacionService
from views.facturas_electronicas import (
    FacturasElectronicasFrame,
    ResolucionEmisorFiscalError,
    SnapshotFiscalCorruptoError,
)


def _datos_snapshot(ambiente):
    return {
        "fuente": "cierre_normal",
        "creado_en": "2026-08-23T12:34:56",
        "ambiente": ambiente,
        "emisor": {
            "emisor_id": 1,
            "emisor_fiscal_id": 3,
            "razon_social": "FM Master SRL",
            "nombre_fantasia": "FM Master",
            "cuit": "20111111117",
            "condicion_iva": "Responsable Inscripto",
            "domicilio": "Domicilio fiscal 123",
            "ingresos_brutos": "123456",
            "fecha_inicio_actividades": "2020-01-01",
            "punto_venta_num": 2,
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
            "punto_venta_num": 2,
            "tipo_comprobante_num": 1,
            "tipo_comprobante_texto": "Factura A",
            "numero_comprobante_num": 10,
            "numero_textual": "00002-00000010",
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


def _snapshot(ambiente):
    return construir_snapshot_fiscal_v1(**_datos_snapshot(ambiente))


def _persistencia_snapshot(snapshot):
    serializado = serializar_snapshot_fiscal(snapshot)
    return serializado, SNAPSHOT_VERSION, calcular_hash_snapshot(serializado)


class EmisionInicialCarpetaPorAmbienteTest(unittest.TestCase):
    """Emision inicial (services.facturacion_service.generar_pdf_fiscal):
    la carpeta fisica se deriva del ambiente del snapshot, no de la
    configuracion mutable del emisor."""

    CARPETA_LEGACY_HOMOLOGACION = r"C:\FM_Master_Certificados\Publicidad_y_Servicios_SH\Homologacion\facturas"

    def _generar(self, ambiente, carpeta_facturas):
        snapshot = _snapshot(ambiente)
        with patch("services.facturacion_service.PDFFiscalService.generar_factura_c") as mock_generar:
            mock_generar.return_value = {"ok": True, "ruta_pdf": "capturada", "errores": []}
            FacturacionService.generar_pdf_fiscal(
                cliente_id=10,
                tipo_factura="Factura A",
                tipo_factura_comprobante="Factura A",
                numero_comprobante=10,
                codigo_factura="00002-00000010",
                carpeta_facturas=carpeta_facturas,
                emisor_fiscal=(3, "FM Master SRL", "FM Master", "20111111117"),
                cuit_emisor="20111111117",
                punto_venta_num=2,
                cliente=(10, "Cliente SA"),
                condicion_iva="Responsable Inscripto",
                documento_normalizado="20222222221",
                consulta={},
                fecha_comprobante="20260823",
                resumen_actual=None,
                periodo_desde="",
                periodo_hasta="",
                neto_factura=1000.0,
                importe_iva_factura=210.0,
                alicuota_iva=21.0,
                total_factura_fiscal=1210.0,
                items_factura=[],
                cae="12345678901234",
                vencimiento_cae="20260902",
                snapshot=snapshot,
            )
        return mock_generar.call_args.kwargs["ruta_destino"]

    def test_snapshot_homologacion_va_a_bucket_homologacion(self):
        ruta = self._generar("HOMOLOGACION", self.CARPETA_LEGACY_HOMOLOGACION)
        self.assertEqual(Path(ruta).parent, Path(self.CARPETA_LEGACY_HOMOLOGACION))

    def test_snapshot_produccion_va_a_bucket_produccion_aunque_config_apunte_a_homologacion(self):
        ruta = self._generar("PRODUCCION", self.CARPETA_LEGACY_HOMOLOGACION)
        self.assertEqual(
            Path(ruta).parent,
            Path(r"C:\FM_Master_Certificados\Publicidad_y_Servicios_SH\Produccion\facturas"),
        )


class ResolucionCarpetaCanonicaVistaTest(unittest.TestCase):
    """views.facturas_electronicas.FacturasElectronicasFrame._resolver_carpeta_facturas_canonica"""

    def test_snapshot_homologacion_ignora_carpeta_configurada_como_produccion(self):
        json_texto, version, hash_texto = _persistencia_snapshot(_snapshot("HOMOLOGACION"))
        factura = {
            "snapshot_fiscal_json": json_texto,
            "snapshot_version": version,
            "snapshot_hash": hash_texto,
        }
        carpeta_actual_del_emisor = r"C:\FM_Master_Certificados\Publicidad_y_Servicios_SH\Produccion\facturas"

        resultado = FacturasElectronicasFrame._resolver_carpeta_facturas_canonica(
            factura, carpeta_actual_del_emisor
        )

        self.assertEqual(
            resultado,
            Path(r"C:\FM_Master_Certificados\Publicidad_y_Servicios_SH\Homologacion\facturas"),
        )

    def test_legacy_sin_snapshot_conserva_carpeta_configurada(self):
        factura = {"snapshot_fiscal_json": None, "snapshot_version": None, "snapshot_hash": None}
        carpeta_legacy = r"C:\FM_Master_Certificados\CarpetaLegacySinBucket"

        resultado = FacturasElectronicasFrame._resolver_carpeta_facturas_canonica(factura, carpeta_legacy)

        self.assertEqual(resultado, Path(carpeta_legacy))

    def test_snapshot_corrupto_bloquea_y_no_cae_a_carpeta_mutable(self):
        factura = {
            "snapshot_fiscal_json": "{esto no es json valido",
            "snapshot_version": 1,
            "snapshot_hash": "0" * 64,
        }

        with self.assertRaises(SnapshotFiscalCorruptoError):
            FacturasElectronicasFrame._resolver_carpeta_facturas_canonica(
                factura, r"C:\FM_Master_Certificados\Publicidad_y_Servicios_SH\Homologacion\facturas"
            )


if __name__ == "__main__":
    unittest.main()
