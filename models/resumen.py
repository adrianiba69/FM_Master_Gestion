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


@dataclass
class Resumen:
    id: int = None
    numero: int = None
    cliente_id: int = None
    fecha: str = ""
    fecha_vencimiento: str = ""
    total: float = 0
    saldo: float = 0
    estado: str = "Pendiente"
    pdf_path: str = ""
    fecha_creacion: str = ""
    conceptos: list = field(default_factory=list)
