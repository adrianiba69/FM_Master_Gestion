from dataclasses import dataclass


@dataclass
class FacturaArca:
    id: int = None
    cliente_id: int = None
    emisor_id: int = None
    resumen_id: int = None
    fecha: str = ""
    punto_venta: str = ""
    tipo_comprobante: str = ""
    importe_total: float = 0
    estado: str = "Pendiente"
    numero_factura: str = ""
    cae: str = ""
    vencimiento_cae: str = ""
    observaciones: str = ""
    fecha_creacion: str = ""
    punto_venta_num: int = None
    tipo_comprobante_num: int = None
    numero_comprobante_num: int = None
    tipo_documento_receptor: int = None
    documento_receptor: int = None
