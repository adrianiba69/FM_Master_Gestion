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

    @property
    def total(self):
        return (self.cantidad * self.importe) - self.descuento
