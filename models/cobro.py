from dataclasses import dataclass


@dataclass
class Cobro:
    id: int = None
    cliente_id: int = None
    fecha: str = ""
    importe: float = 0
    forma_pago: str = ""
    comprobante: str = ""
    factura_arca_id: int = None
    observaciones: str = ""
