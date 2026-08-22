"""Representación centralizada del ambiente ARCA (Homologación/Producción).

Este módulo NO realiza llamadas de red. Solo normaliza el valor de ambiente,
resuelve los endpoints WSAA/WSFE correspondientes, deriva el prefijo de
cache TA por ambiente, y bloquea de forma explícita cualquier emisión real
en Producción hasta completar los requisitos pre-Producción pendientes.
"""

AMBIENTE_HOMOLOGACION = "HOMOLOGACION"
AMBIENTE_PRODUCCION = "PRODUCCION"

_AMBIENTES_VALIDOS = (AMBIENTE_HOMOLOGACION, AMBIENTE_PRODUCCION)

# Variantes textuales históricas/configuradas aceptadas (con/sin tilde, mayúsculas/minúsculas).
_ALIAS_AMBIENTE = {
    "homologacion": AMBIENTE_HOMOLOGACION,
    "homologación": AMBIENTE_HOMOLOGACION,
    "produccion": AMBIENTE_PRODUCCION,
    "producción": AMBIENTE_PRODUCCION,
}

# Endpoints reales de AFIP/ARCA. Las URLs de Homologación son las que ya
# funcionan hoy en el sistema. Las de Producción son las oficiales documentadas
# por AFIP; deben re-verificarse contra la documentación vigente antes de
# habilitar emisión real (ver `asegurar_emision_habilitada`).
WSAA_URLS = {
    AMBIENTE_HOMOLOGACION: "https://wsaahomo.afip.gov.ar/ws/services/LoginCms",
    AMBIENTE_PRODUCCION: "https://wsaa.afip.gov.ar/ws/services/LoginCms",
}

WSFE_URLS = {
    AMBIENTE_HOMOLOGACION: "https://wswhomo.afip.gov.ar/wsfev1/service.asmx",
    AMBIENTE_PRODUCCION: "https://servicio1.afip.gov.ar/wsfev1/service.asmx",
}

_CACHE_PREFIJOS = {
    AMBIENTE_HOMOLOGACION: "ta_cache_homologacion",
    AMBIENTE_PRODUCCION: "ta_cache_produccion",
}


class AmbienteArcaInvalidoError(ValueError):
    """Error de configuración: el ambiente ARCA no es un valor reconocido."""


class EmisionProduccionNoHabilitadaError(RuntimeError):
    """Bloqueo explícito: la emisión real en Producción todavía no está habilitada."""


def normalizar_ambiente_arca(valor):
    """Normaliza el ambiente a AMBIENTE_HOMOLOGACION/AMBIENTE_PRODUCCION.

    Nunca interpreta un valor vacío o desconocido como Producción: ante
    cualquier duda, se levanta AmbienteArcaInvalidoError (error de
    configuración explícito, nunca una emisión productiva accidental).
    """
    texto = str(valor or "").strip().upper()
    if texto in _AMBIENTES_VALIDOS:
        return texto
    alias = _ALIAS_AMBIENTE.get(str(valor or "").strip().lower())
    if alias:
        return alias
    raise AmbienteArcaInvalidoError(
        f"Ambiente ARCA inválido o no configurado: {valor!r}. "
        f"Valores aceptados: 'Homologación'/'HOMOLOGACION' o 'Producción'/'PRODUCCION'."
    )


def resolver_endpoint_wsaa(ambiente):
    return WSAA_URLS[normalizar_ambiente_arca(ambiente)]


def resolver_endpoint_wsfe(ambiente):
    return WSFE_URLS[normalizar_ambiente_arca(ambiente)]


def prefijo_cache_wsaa(ambiente):
    return _CACHE_PREFIJOS[normalizar_ambiente_arca(ambiente)]


def asegurar_emision_habilitada(ambiente):
    """Bloquea explícitamente cualquier emisión real en Producción.

    Debe invocarse ANTES de crear cualquier intento durable o de llamar a
    FECAESolicitar. Homologación no se ve afectada.
    """
    ambiente_normalizado = normalizar_ambiente_arca(ambiente)
    if ambiente_normalizado == AMBIENTE_PRODUCCION:
        raise EmisionProduccionNoHabilitadaError(
            "Emisión ARCA en Producción todavía no habilitada. "
            "Complete la configuración productiva antes de emitir comprobantes reales."
        )
    return ambiente_normalizado
