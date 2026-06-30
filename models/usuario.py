from dataclasses import dataclass


@dataclass
class Usuario:
    id: int = None
    nombre: str = ""
    usuario: str = ""
    clave: str = ""  # almacenada como hash
    rol: str = "Consulta"
    activo: int = 1
    fecha_creacion: str = ""
