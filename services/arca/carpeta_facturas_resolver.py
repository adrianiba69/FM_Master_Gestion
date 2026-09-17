"""Resuelve, de forma pura y determinista, la carpeta fiscal fisica de PDFs
segun el ambiente ARCA (HOMOLOGACION/PRODUCCION).

Modulo puro: no consulta DB, no toca filesystem (no crea carpetas, no
verifica existencia), no lee certificados ni llama ARCA. Solo calcula un
Path a partir de la carpeta configurada y el ambiente fiscal ya resuelto
(snapshot/contexto persistido), nunca del combo mutable del emisor.
"""

from pathlib import Path, PureWindowsPath

from services.arca import ambiente_arca

_BUCKET_POR_AMBIENTE = {
    ambiente_arca.AMBIENTE_HOMOLOGACION: "Homologacion",
    ambiente_arca.AMBIENTE_PRODUCCION: "Produccion",
}

_SEGMENTO_FACTURAS = "facturas"
_SEGMENTOS_AMBIENTE_LEGACY = {"homologacion", "produccion"}


class CarpetaFacturasNoConfiguradaError(ValueError):
    """La carpeta de facturas del emisor no esta configurada."""


def _raiz_sin_sufijo_legado(ruta):
    """Si `ruta` ya termina en '<Homologacion|Produccion>\\facturas' (cualquier
    capitalizacion), retorna la raiz anterior a ese sufijo. Caso contrario,
    retorna `ruta` sin cambios (raiz neutral)."""
    partes = ruta.parts
    if len(partes) < 2:
        return ruta

    ultimo = partes[-1].strip().lower()
    penultimo = partes[-2].strip().lower()
    if ultimo != _SEGMENTO_FACTURAS or penultimo not in _SEGMENTOS_AMBIENTE_LEGACY:
        return ruta

    raiz_partes = partes[:-2]
    if not raiz_partes:
        return PureWindowsPath(".")
    return PureWindowsPath(*raiz_partes)


def resolver_carpeta_facturas_por_ambiente(carpeta_configurada, ambiente_fiscal):
    """Deriva `<raiz>\\Homologacion\\facturas` o `<raiz>\\Produccion\\facturas`.

    - `ambiente_fiscal` debe ser el ambiente FISCAL persistido (snapshot o
      contexto), nunca el combo mutable de configuracion del emisor.
    - Reconoce y retira, de forma case-insensitive, un sufijo legacy
      'Homologacion\\facturas' o 'Produccion\\facturas' ya presente en la
      carpeta configurada, evitando duplicar segmentos.
    - Ante ambiente ausente, vacio, invalido o ambiguo, nunca elige
      Produccion: `ambiente_arca.normalizar_ambiente_arca` levanta
      `AmbienteArcaInvalidoError` (fail-safe explicito).
    """
    ambiente_normalizado = ambiente_arca.normalizar_ambiente_arca(ambiente_fiscal)

    texto = str(carpeta_configurada or "").strip()
    if not texto:
        raise CarpetaFacturasNoConfiguradaError("carpeta_facturas no configurada.")

    raiz = _raiz_sin_sufijo_legado(PureWindowsPath(texto))
    bucket = _BUCKET_POR_AMBIENTE[ambiente_normalizado]
    return Path(str(raiz / bucket / _SEGMENTO_FACTURAS))
