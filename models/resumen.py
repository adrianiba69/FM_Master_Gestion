from dataclasses import dataclass, field


@dataclass
class ResumenConcepto:
    id: int = None
    resumen_id: int = None
    servicio_id: int = None
    concepto: str = ""
    descripcion: str = ""
    cantidad: float = 1
    importe: float = 0
    descuento: float = 0
    total: float = 0
    fecha_inicio: str = ""
    fecha_fin: str = ""


@dataclass
class Resumen:
    id: int = None
    numero: int = None
    cliente_id: int = None
    emisor_fiscal_id: int = None
    fecha: str = ""
    fecha_vencimiento: str = ""
    tipo_factura: str = ""
    punto_venta: str = ""
    total: float = 0
    saldo: float = 0
    estado: str = "Pendiente"
    pdf_path: str = ""
    fecha_creacion: str = ""
    estado_facturacion: str = "Pendiente"
    fecha_facturacion: str = ""
    cae: str = ""
    vencimiento_cae: str = ""
    numero_factura: str = ""
    conceptos: list = field(default_factory=list)
