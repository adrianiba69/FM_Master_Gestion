from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class IntentoEmisionArca:
    id: int
    resumen_id: int
    cliente_id: int
    emisor_fiscal_id: int
    emisor_id: int
    cuit_emisor: str
    punto_venta: int
    tipo_comprobante: int
    numero_planificado: int
    fecha_comprobante: str
    concepto: int
    tipo_documento: int
    documento_receptor: int
    condicion_iva_receptor_id: int
    importe_total: Decimal
    importe_neto: Decimal
    importe_iva: Decimal
    importe_exento: Decimal
    importe_no_gravado: Decimal
    importe_tributos: Decimal
    moneda: str
    cotizacion: Decimal
    alicuotas_iva: tuple
    estado: str
    cae: str
    vencimiento_cae: str
    error_codigo: str
    error_mensaje: str
    detalle_tecnico: str
    factura_arca_id: int
    creado_en: str
    actualizado_en: str
    reconciliado_en: str
    contexto_fiscal_json: str = None
    contexto_fiscal_version: int = None
    contexto_fiscal_hash: str = None