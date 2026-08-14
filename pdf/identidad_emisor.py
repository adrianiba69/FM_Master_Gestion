from pathlib import Path

from reportlab.lib.colors import HexColor

from runtime_paths import APP_DIR, ASSETS_DIR


LOGO_FM_MASTER_INSTITUCIONAL = ASSETS_DIR / "logos" / "logo_fm_master.png"
LOGO_PUBLICIDAD_SERVICIOS_INSTITUCIONAL = ASSETS_DIR / "logos" / "logo_publicidad_servicios.jpg"
LOGO_PUBLICIDAD_SERVICIOS_SH_INSTITUCIONAL = ASSETS_DIR / "logos" / "logo_publicidad_servicios_sh.jpg"

CUIT_FM_MASTER_NORMALIZADO = "20206871629"
CUIT_PUBLICIDAD_SERVICIOS_NORMALIZADO = "20263858884"
CUIT_PUBLICIDAD_SERVICIOS_SH_NORMALIZADO = "30712178619"

PALETA_FM_MASTER = {
    "principal": HexColor("#C00000"),
    "secundario": HexColor("#C00000"),
    "texto": HexColor("#111111"),
    "gris": HexColor("#EFEFEF"),
    "borde": HexColor("#BEBEBE"),
}

PALETA_PUBLICIDAD_SERVICIOS = {
    "principal": HexColor("#07324D"),
    "secundario": HexColor("#F57C00"),
    "texto": HexColor("#111111"),
    "gris": HexColor("#F5F5F5"),
    "borde": HexColor("#C8C8C8"),
}


def normalizar_cuit(cuit):
    return "".join(char for char in str(cuit or "") if char.isdigit())


def normalizar_nombre_emisor(valor):
    texto = str(valor or "").lower().strip()
    reemplazos = {
        "á": "a",
        "é": "e",
        "í": "i",
        "ó": "o",
        "ú": "u",
        "ü": "u",
        "ñ": "n",
    }
    for origen, destino in reemplazos.items():
        texto = texto.replace(origen, destino)
    return "".join(caracter if caracter.isalnum() else " " for caracter in texto)


def resolver_tipo_identidad_emisor(emisor):
    if not isinstance(emisor, dict):
        return "fm_master"

    cuit_normalizado = normalizar_cuit(emisor.get("cuit"))
    nombre_fantasia = normalizar_nombre_emisor(emisor.get("nombre_fantasia"))
    razon_social = normalizar_nombre_emisor(emisor.get("razon_social"))
    nombre_compuesto = f"{nombre_fantasia} {razon_social}".strip()
    tokens_nombre = {token for token in nombre_compuesto.split() if token}

    es_publicidad_servicios_sh = (
        cuit_normalizado == CUIT_PUBLICIDAD_SERVICIOS_SH_NORMALIZADO
        or (
            "publicidad" in tokens_nombre
            and "servicios" in tokens_nombre
            and (
                "sh" in tokens_nombre
                or ("s" in tokens_nombre and "h" in tokens_nombre)
            )
        )
    )
    if es_publicidad_servicios_sh:
        return "publicidad_servicios_sh"

    es_publicidad_servicios = (
        cuit_normalizado == CUIT_PUBLICIDAD_SERVICIOS_NORMALIZADO
        or ("publicidad" in tokens_nombre and "servicios" in tokens_nombre)
    )
    if es_publicidad_servicios:
        return "publicidad_servicios"

    emisor_id = int(emisor.get("id") or 0)
    es_fm_master = (
        emisor_id == 1
        or cuit_normalizado == CUIT_FM_MASTER_NORMALIZADO
        or ("fm" in tokens_nombre and "master" in tokens_nombre)
    )
    if es_fm_master:
        return "fm_master"

    return "fm_master"


def _ruta_existente(candidato):
    texto = str(candidato or "").strip()
    if not texto:
        return None

    ruta = Path(texto)
    rutas_candidatas = [ruta]
    if not ruta.is_absolute():
        rutas_candidatas.append(APP_DIR / ruta)

    for ruta_candidata in rutas_candidatas:
        try:
            ruta_resuelta = ruta_candidata.resolve()
        except OSError:
            continue
        if ruta_resuelta.is_file():
            return ruta_resuelta
    return None


def resolver_logo_emisor(emisor):
    if not isinstance(emisor, dict):
        return None

    candidatos_explicitos = [
        emisor.get("logo_path"),
        emisor.get("ruta_logo"),
        emisor.get("logo"),
    ]
    for candidato in candidatos_explicitos:
        ruta = _ruta_existente(candidato)
        if ruta:
            return ruta

    carpeta = str(emisor.get("carpeta_facturas") or "").strip()
    if carpeta:
        base = Path(carpeta)
        for candidato in (
            base / "logo.png",
            base / "logo.jpg",
            base / "logo.jpeg",
            base / "logo.webp",
            base / "logo_emisor.png",
            base / "logo_emisor.jpg",
        ):
            ruta = _ruta_existente(candidato)
            if ruta:
                return ruta

    identidad = resolver_tipo_identidad_emisor(emisor)
    if identidad == "publicidad_servicios_sh":
        ruta_sh = _ruta_existente(LOGO_PUBLICIDAD_SERVICIOS_SH_INSTITUCIONAL)
        if ruta_sh:
            return ruta_sh

    if identidad == "publicidad_servicios":
        ruta_publicidad = _ruta_existente(LOGO_PUBLICIDAD_SERVICIOS_INSTITUCIONAL)
        if ruta_publicidad:
            return ruta_publicidad

    if identidad == "fm_master":
        ruta_institucional = _ruta_existente(LOGO_FM_MASTER_INSTITUCIONAL)
        if ruta_institucional:
            return ruta_institucional

    return None


def obtener_paleta_emisor(emisor):
    identidad = resolver_tipo_identidad_emisor(emisor)
    if identidad in {"publicidad_servicios", "publicidad_servicios_sh"}:
        return PALETA_PUBLICIDAD_SERVICIOS
    return PALETA_FM_MASTER


def obtener_dimensiones_logo_emisor(emisor, logo_width, logo_height):
    identidad = resolver_tipo_identidad_emisor(emisor)
    if identidad in {"publicidad_servicios", "publicidad_servicios_sh"}:
        return logo_width * 2.07, logo_height * 2.07
    return float(logo_width), float(logo_height)


def obtener_configuracion_logo_fiscal(emisor):
    identidad = resolver_tipo_identidad_emisor(emisor)

    if identidad == "publicidad_servicios":
        return {
            "max_width": 190.0,
            "max_height": 127.0,
            "x_offset": -40.0,
            "y_offset": 7.0,
        }

    if identidad == "publicidad_servicios_sh":
        return {
            "max_width": 265.0,
            "max_height": 104.0,
            "x_offset": -21.0,
            "y_offset": 4.0,
        }

    return {
        "max_width": 120.0,
        "max_height": 44.0,
        "x_offset": 0.0,
        "y_offset": 0.0,
    }