from pathlib import Path


class ArcaCertificadosService:
    """Gestiona rutas de certificados y claves para ARCA."""

    @staticmethod
    def validar_archivo(ruta, extensiones=None):
        if not ruta:
            return False
        path = Path(ruta)
        if not path.is_file():
            return False
        if extensiones is None:
            return True
        return path.suffix.lower() in [ext.lower() for ext in extensiones]

    @staticmethod
    def es_certificado_valido(ruta):
        return ArcaCertificadosService.validar_archivo(ruta, [".crt", ".pem"])

    @staticmethod
    def es_clave_privada_valida(ruta):
        return ArcaCertificadosService.validar_archivo(ruta, [".key", ".pem"])
