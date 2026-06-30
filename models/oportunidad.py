from dataclasses import dataclass


@dataclass
class Oportunidad:
    id: int = None
    cliente_id: int = None
    nombre_potencial: str = ""
    telefono: str = ""
    whatsapp: str = ""
    email: str = ""
    fecha: str = ""
    origen: str = ""
    servicio_interes: str = ""
    importe_estimado: float = 0
    probabilidad: float = 0
    estado: str = "Nueva"
    proximo_contacto: str = ""
    observaciones: str = ""
    creado: str = ""
