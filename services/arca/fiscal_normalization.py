import re


_TIPOS = {
    "FACTURA A": 1,
    "FACTURA C": 11,
    "1": 1,
    "11": 11,
}


def normalizar_punto_venta(valor):
    texto = str(valor or "").strip()
    if not texto or not texto.isdigit():
        return None
    numero = int(texto)
    return numero if numero > 0 else None


def normalizar_tipo_comprobante(valor):
    texto = str(valor or "").strip().upper()
    return _TIPOS.get(texto)


def separar_numero_factura(valor):
    texto = str(valor or "").strip()
    if not re.fullmatch(r"\d{1,5}-\d{1,8}", texto):
        return None
    punto_venta, numero = texto.split("-", 1)
    punto_venta_num = int(punto_venta)
    numero_num = int(numero)
    if punto_venta_num <= 0 or numero_num <= 0:
        return None
    return punto_venta_num, numero_num


def normalizar_identidad_factura(punto_venta, tipo_comprobante, numero_factura):
    punto_venta_num = normalizar_punto_venta(punto_venta)
    tipo_comprobante_num = normalizar_tipo_comprobante(tipo_comprobante)
    separado = separar_numero_factura(numero_factura)
    if not punto_venta_num or not tipo_comprobante_num:
        return punto_venta_num, tipo_comprobante_num, None
    if not separado:
        return punto_venta_num, tipo_comprobante_num, None
    punto_numero, numero_comprobante_num = separado
    if punto_numero != punto_venta_num:
        return None, None, None
    return punto_venta_num, tipo_comprobante_num, numero_comprobante_num
