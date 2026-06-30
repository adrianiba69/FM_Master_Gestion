from dataclasses import dataclass


@dataclass
class Notificacion:
    id: int = None
    tipo: str = "Otro"
    titulo: str = ""
    mensaje: str = ""
    prioridad: str = "Media"
    estado: str = "Pendiente"
    fecha: str = ""
    vencimiento: str = ""
    referencia_tipo: str = ""
    referencia_id: int = None
    clave: str = ""
    automatica: int = 0
    creado: str = ""
    actualizado: str = ""
