from dataclasses import dataclass


@dataclass
class Tarea:
    id: int = None
    cliente_id: int = None
    fecha: str = ""
    hora: str = ""
    tipo: str = "Otro"
    titulo: str = ""
    descripcion: str = ""
    estado: str = "Pendiente"
    prioridad: str = "Media"
    fecha_creacion: str = ""
