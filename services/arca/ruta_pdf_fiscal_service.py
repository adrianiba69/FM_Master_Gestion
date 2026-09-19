"""Identidad operativa y resolucion segura de rutas de PDF fiscal."""

from dataclasses import dataclass
from pathlib import Path, PureWindowsPath

from services.arca.carpeta_facturas_resolver import resolver_carpeta_facturas_por_ambiente
from services.arca.snapshot_fiscal_pdf_adapter import MODO_CORRUPTO, MODO_SNAPSHOT, resolver_modo_regeneracion


class RutaPdfFiscalInvalidaError(ValueError):
    """La ruta persistida no coincide con la identidad fiscal esperada."""


@dataclass(frozen=True)
class RutaPdfFiscalResuelta:
    ruta: Path
    persistida: bool
    snapshot: bool


def _path_windows(valor, campo):
    texto = str(valor or "").strip()
    if not texto:
        raise RutaPdfFiscalInvalidaError(f"{campo} no informada.")
    ruta = PureWindowsPath(texto)
    if any(parte in {".", ".."} for parte in ruta.parts):
        raise RutaPdfFiscalInvalidaError(f"{campo} no puede contener traversal.")
    return ruta


def _partes_iguales(izquierda, derecha):
    return tuple(parte.casefold() for parte in izquierda) == tuple(parte.casefold() for parte in derecha)


def _validar_nombre_pdf(nombre, campo):
    if not nombre or PureWindowsPath(nombre).suffix.casefold() != ".pdf":
        raise RutaPdfFiscalInvalidaError(f"{campo} debe identificar un archivo PDF.")


def _carpeta_canonica_windows(carpeta_configurada, ambiente_fiscal):
    return PureWindowsPath(str(resolver_carpeta_facturas_por_ambiente(carpeta_configurada, ambiente_fiscal)))


def validar_ruta_pdf_relativa(ruta_pdf_relativa, ambiente_fiscal):
    """Valida una clave relativa `<ambiente>\\facturas\\archivo.pdf`."""
    ruta = _path_windows(ruta_pdf_relativa, "ruta_pdf_relativa")
    if ruta.is_absolute():
        raise RutaPdfFiscalInvalidaError("ruta_pdf_relativa no puede ser absoluta.")

    carpeta = _carpeta_canonica_windows(r"C:\raiz", ambiente_fiscal)
    partes_esperadas = carpeta.parts[-2:]
    if len(ruta.parts) != 3 or not _partes_iguales(ruta.parts[:2], partes_esperadas):
        raise RutaPdfFiscalInvalidaError("ruta_pdf_relativa no pertenece al bucket fiscal esperado.")
    _validar_nombre_pdf(ruta.name, "ruta_pdf_relativa")
    return ruta


def validar_ruta_pdf_absoluta(ruta_pdf_absoluta, ambiente_fiscal):
    """Valida que una ruta absoluta pertenezca al bucket del ambiente esperado."""
    ruta = _path_windows(ruta_pdf_absoluta, "ruta_pdf_absoluta")
    if not ruta.is_absolute():
        raise RutaPdfFiscalInvalidaError("ruta_pdf_absoluta debe ser absoluta.")

    carpeta = _carpeta_canonica_windows(r"C:\raiz", ambiente_fiscal)
    partes_esperadas = carpeta.parts[-2:]
    if len(ruta.parts) < 3 or not _partes_iguales(ruta.parts[-3:-1], partes_esperadas):
        raise RutaPdfFiscalInvalidaError("ruta_pdf_absoluta no pertenece al bucket fiscal esperado.")
    _validar_nombre_pdf(ruta.name, "ruta_pdf_absoluta")
    return ruta


def construir_rutas_pdf_persistibles(carpeta_configurada, ambiente_fiscal, ruta_pdf_absoluta):
    """Devuelve clave relativa canónica y última ruta absoluta conocida.

    La ruta generada debe estar dentro de la carpeta canónica del ambiente fiscal.
    """
    ruta_absoluta = validar_ruta_pdf_absoluta(ruta_pdf_absoluta, ambiente_fiscal)
    carpeta_canonica = _carpeta_canonica_windows(carpeta_configurada, ambiente_fiscal)
    if not _partes_iguales(ruta_absoluta.parts[:-1], carpeta_canonica.parts):
        raise RutaPdfFiscalInvalidaError("El PDF generado queda fuera de la carpeta fiscal canónica.")

    relativa = PureWindowsPath(*carpeta_canonica.parts[-2:], ruta_absoluta.name)
    return str(relativa), str(ruta_absoluta)


def construir_rutas_pdf_persistibles_para_factura(factura, carpeta_configurada, ruta_pdf_absoluta):
    """Construye rutas persistibles sin inventar ambiente para una factura legacy."""
    if not isinstance(factura, dict):
        raise RutaPdfFiscalInvalidaError("Factura fiscal inválida.")

    decision = resolver_modo_regeneracion(
        factura.get("snapshot_fiscal_json"),
        factura.get("snapshot_version"),
        factura.get("snapshot_hash"),
    )
    if decision.modo == MODO_CORRUPTO:
        raise RutaPdfFiscalInvalidaError("Snapshot fiscal corrupto; no se puede persistir el PDF.")
    if decision.modo == MODO_SNAPSHOT:
        return construir_rutas_pdf_persistibles(
            carpeta_configurada,
            decision.snapshot.get("ambiente"),
            ruta_pdf_absoluta,
        )

    ruta_legacy = _path_windows(ruta_pdf_absoluta, "ruta_pdf_absoluta")
    if not ruta_legacy.is_absolute() or ruta_legacy.suffix.casefold() != ".pdf":
        raise RutaPdfFiscalInvalidaError("La ruta PDF legacy generada debe ser absoluta.")
    return None, str(ruta_legacy)


def reconstruir_ruta_pdf_relativa(carpeta_configurada, ambiente_fiscal, ruta_pdf_relativa):
    """Reconstruye una clave relativa validada bajo la raíz fiscal actual."""
    relativa = validar_ruta_pdf_relativa(ruta_pdf_relativa, ambiente_fiscal)
    carpeta_canonica = _carpeta_canonica_windows(carpeta_configurada, ambiente_fiscal)
    raiz_actual = PureWindowsPath(*carpeta_canonica.parts[:-2])
    return Path(str(raiz_actual / relativa))


def resolver_ruta_pdf_documental(factura, carpeta_configurada, nombre_legacy):
    """Prioriza la identidad persistida y bloquea snapshots corruptos.

    Las facturas legacy sin snapshot ni ruta conservan la ubicación configurada.
    """
    if not isinstance(factura, dict):
        raise RutaPdfFiscalInvalidaError("Factura fiscal inválida.")

    decision = resolver_modo_regeneracion(
        factura.get("snapshot_fiscal_json"),
        factura.get("snapshot_version"),
        factura.get("snapshot_hash"),
    )
    if decision.modo == MODO_CORRUPTO:
        raise RutaPdfFiscalInvalidaError("Snapshot fiscal corrupto; no se puede resolver el PDF.")

    relativa = str(factura.get("ruta_pdf_relativa") or "").strip()
    absoluta = str(factura.get("ruta_pdf_absoluta") or "").strip()
    if decision.modo == MODO_SNAPSHOT:
        ambiente = decision.snapshot.get("ambiente")
        if absoluta:
            validar_ruta_pdf_absoluta(absoluta, ambiente)
        if relativa:
            return RutaPdfFiscalResuelta(
                reconstruir_ruta_pdf_relativa(carpeta_configurada, ambiente, relativa),
                persistida=True,
                snapshot=True,
            )
        carpeta = resolver_carpeta_facturas_por_ambiente(carpeta_configurada, ambiente)
        return RutaPdfFiscalResuelta(Path(carpeta) / str(nombre_legacy), persistida=False, snapshot=True)

    if absoluta:
        ruta_legacy = _path_windows(absoluta, "ruta_pdf_absoluta")
        if ruta_legacy.is_absolute() and ruta_legacy.suffix.casefold() == ".pdf":
            return RutaPdfFiscalResuelta(Path(str(ruta_legacy)), persistida=True, snapshot=False)
    return RutaPdfFiscalResuelta(Path(str(carpeta_configurada or "").strip()) / str(nombre_legacy), persistida=False, snapshot=False)
