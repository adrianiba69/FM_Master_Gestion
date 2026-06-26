from dataclasses import dataclass

@dataclass
class Cliente:
    id: int = None
    codigo: str = ""
    razon_social: str = ""
    responsable: str = ""
    direccion: str = ""
    localidad: str = ""
    telefono: str = ""
    whatsapp: str = ""
    email: str = ""
    cuit: str = ""
    iva: str = ""
    servicio: str = ""
    importe: float = 0.0
    descuento: float = 0.0
    vencimiento: int = 1
    estado: str = "ACTIVO"
    observaciones: str = ""
    fecha_alta: str = ""