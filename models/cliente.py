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
    tipo_factura: str = "No factura"
    monotributo_facturacion: str = "No aplica"
    modalidad_comprobante: str = "Solo Resumen"
    emisor_habitual: str = "FM Master 98.3"
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