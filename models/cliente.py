from dataclasses import dataclass


@dataclass
class Cliente:
    id: int = None
    codigo: str = ""
    razon_social: str = ""
    nombre_comercial: str = ""
    responsable: str = ""
    direccion: str = ""
    localidad: str = ""
    telefono: str = ""
    whatsapp: str = ""
    email: str = ""
    cuit: str = ""
    iva: str = ""
    emisor_id: int = None
    emisor_recomendado_id: int = None
    servicio: str = ""
    importe: float = 0
    descuento: float = 0
    vencimiento: int = 1
    estado: str = "Activo"
    observaciones: str = ""
    fecha_alta: str = ""
    fecha_modificacion: str = ""