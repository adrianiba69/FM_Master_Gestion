from dataclasses import dataclass


@dataclass
class Contacto:
    id: int = None
    cliente_id: int = None
    fecha: str = ""
    hora: str = ""
    tipo: str = "Llamada"
    resultado: str = "Pendiente"
    observaciones: str = ""
    proximo_contacto: str = ""
    vendedor: str = ""
    creado: str = ""
