CLAVES_SECRETAS_ARCA = {
    "token",
    "sign",
    "password",
    "contrasena",
    "contraseña",
    "clave",
    "clave_privada",
    "private_key",
    "certificado",
    "certificate",
    "secret",
    "credential",
    "credencial",
    "ruta_clave",
    "ruta_clave_privada",
    "ruta_certificado",
    "certificado_path",
    "clave_privada_path",
}


def _es_clave_secreta(clave):
    return str(clave or "").strip().lower() in CLAVES_SECRETAS_ARCA


def _extraer_textos(valor):
    if isinstance(valor, str):
        texto = valor.strip()
        return [texto] if len(texto) >= 4 else []
    if isinstance(valor, dict):
        secretos = []
        for contenido in valor.values():
            secretos.extend(_extraer_textos(contenido))
        return secretos
    if isinstance(valor, (list, tuple)):
        secretos = []
        for contenido in valor:
            secretos.extend(_extraer_textos(contenido))
        return secretos
    return []


def _extraer_secretos(valor):
    if isinstance(valor, dict):
        secretos = []
        for clave, contenido in valor.items():
            if _es_clave_secreta(clave):
                secretos.extend(_extraer_textos(contenido))
            else:
                secretos.extend(_extraer_secretos(contenido))
        return secretos
    if isinstance(valor, (list, tuple)):
        secretos = []
        for contenido in valor:
            secretos.extend(_extraer_secretos(contenido))
        return secretos
    return []


def _redactar_texto(texto, secretos):
    resultado = texto
    for secreto in secretos:
        if secreto:
            resultado = resultado.replace(secreto, "[REDACTED]")
    return resultado


def _sanitizar(valor, secretos):
    if isinstance(valor, dict):
        return {
            clave: _sanitizar(contenido, secretos)
            for clave, contenido in valor.items()
            if not _es_clave_secreta(clave)
        }
    if isinstance(valor, list):
        return [_sanitizar(contenido, secretos) for contenido in valor]
    if isinstance(valor, tuple):
        return tuple(_sanitizar(contenido, secretos) for contenido in valor)
    if isinstance(valor, str):
        return _redactar_texto(valor, secretos)
    return valor


def sanitizar_estructura_arca(valor, secretos_extra=()):
    secretos = tuple(dict.fromkeys(_extraer_secretos(valor) + _extraer_textos(tuple(secretos_extra or ()))))
    return _sanitizar(valor, secretos)