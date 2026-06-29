from dataclasses import dataclass


@dataclass
class Servicio:
    id: int = None
    cliente_id: int = None
    concepto: str = ""
    descripcion: str = ""
    cantidad: float = 1
    importe: float = 0
    descuento: float = 0
    activo: int = 1
    fecha_inicio: str = ""
    fecha_fin: str = ""
    renovable: int = 1
    estado_periodo: str = "Activo"

    @property
    def total(self):
        return (self.cantidad * self.importe) - self.descuento


@dataclass
class RenovacionServicio:
    id: int = None
    servicio_id: int = None
    cliente_id: int = None
    fecha_renovacion: str = ""
    fecha_inicio_anterior: str = ""
    fecha_fin_anterior: str = ""
    fecha_inicio_nueva: str = ""
    fecha_fin_nueva: str = ""
    concepto: str = ""
    descripcion: str = ""
    cantidad: float = 1
    importe: float = 0
    descuento: float = 0
    resumen_id: int = None
