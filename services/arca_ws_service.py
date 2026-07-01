import os
from pathlib import Path


class ArcaWsService:
    """Soporte técnico de conexión ARCA Web Service.

    Por ahora sólo prepara la estructura y validaciones para homologación/producción.
    """

    @staticmethod
    def validar_certificado_ruta(ruta):
        if not ruta:
            return False
        return Path(ruta).is_file()

    @staticmethod
    def validar_clave_privada_ruta(ruta):
        if not ruta:
            return False
        return Path(ruta).is_file()

    @staticmethod
    def validar_cuit(cuit):
        if not cuit:
            return False
        valor = str(cuit).strip()
        return len(valor) >= 10 and len(valor) <= 13 and valor.replace('-', '').isdigit()

    @staticmethod
    def validar_punto_venta(punto_venta):
        if not punto_venta:
            return False
        texto = str(punto_venta).strip()
        return texto.isdigit() and int(texto) > 0

    @staticmethod
    def validar_configuracion_emisor(emisor):
        errores = []
        if not ArcaWsService.validar_cuit(emisor[4]):
            errores.append("CUIT inválido")
        if not ArcaWsService.validar_punto_venta(emisor[6]):
            errores.append("Punto de venta inválido")
        if not ArcaWsService.validar_certificado_ruta(emisor[14]):
            errores.append("Certificado no encontrado")
        if not ArcaWsService.validar_clave_privada_ruta(emisor[15]):
            errores.append("Clave privada no encontrada")
        return errores

    @staticmethod
    def probar_conexion(emisor):
        errores = ArcaWsService.validar_configuracion_emisor(emisor)
        if errores:
            return False, errores
        modo = (emisor[16] or "").strip().lower()
        if modo == "producción" and errores:
            return False, ["No es posible activar Producción sin configuración completa"]
        if modo not in {"manual", "homologación", "producción"}:
            return False, ["Modo ARCA inválido"]
        return True, ["Configuración lista para homologación"]
