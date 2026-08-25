"""
Adaptador puro snapshot fiscal v1 -> PDF/QR (FASE 5D).

Convierte un snapshot fiscal v1 ya validado en las estructuras que hoy
consumen PDFFiscalService.generar_factura_c(...) y QrFiscalService.

Tambien centraliza la decision de modo de regeneracion (snapshot valido /
legacy sin snapshot / snapshot corrupto), usando exclusivamente las
funciones de validacion de services/arca/snapshot_fiscal_service.py.

Modulo puro: no consulta SQLite, ClienteService, EmisorFiscalService,
ResumenService ni ARCA. No importa Tkinter ni ReportLab.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from services.arca.snapshot_fiscal_service import validar_integridad_snapshot

MODO_SNAPSHOT = "snapshot"
MODO_LEGACY = "legacy"
MODO_CORRUPTO = "corrupto"


@dataclass(frozen=True)
class DecisionRegeneracion:
    """Resultado centralizado y testeable de la prioridad snapshot/legacy/corrupto."""

    modo: str
    snapshot: Optional[Dict[str, Any]] = None
    codigo: Optional[str] = None
    errores: Tuple[str, ...] = field(default_factory=tuple)


def resolver_modo_regeneracion(
    snapshot_fiscal_json: Optional[str],
    snapshot_version: Optional[int],
    snapshot_hash: Optional[str],
) -> DecisionRegeneracion:
    """Decide el modo de regeneracion segun lo persistido en factura_arca.

    - snapshot_fiscal_json ausente/vacio -> MODO_LEGACY.
    - snapshot_fiscal_json presente pero JSON/version/hash/estructura invalida -> MODO_CORRUPTO.
    - snapshot presente y valido -> MODO_SNAPSHOT (con snapshot ya parseado).
    """
    texto = str(snapshot_fiscal_json).strip() if snapshot_fiscal_json is not None else ""
    if not texto:
        return DecisionRegeneracion(modo=MODO_LEGACY)

    try:
        version_normalizada = int(snapshot_version)
    except (TypeError, ValueError):
        return DecisionRegeneracion(
            modo=MODO_CORRUPTO,
            codigo="VERSION_INVALIDA",
            errores=("snapshot_version ausente o invalida",),
        )

    hash_texto = str(snapshot_hash).strip() if snapshot_hash is not None else ""
    if not hash_texto:
        return DecisionRegeneracion(
            modo=MODO_CORRUPTO,
            codigo="HASH_INVALIDO",
            errores=("snapshot_hash ausente",),
        )

    resultado = validar_integridad_snapshot(texto, version_normalizada, hash_texto)
    if not resultado.valido:
        return DecisionRegeneracion(
            modo=MODO_CORRUPTO,
            codigo=resultado.codigo,
            errores=resultado.errores,
        )

    return DecisionRegeneracion(modo=MODO_SNAPSHOT, snapshot=resultado.snapshot)


def _fecha_iso_a_yyyymmdd(valor: Any) -> str:
    """Convierte YYYY-MM-DD a YYYYMMDD para conservar el formateo visual historico."""
    texto = str(valor or "").strip()
    if len(texto) == 10 and texto[4] == "-" and texto[7] == "-":
        return texto.replace("-", "")
    return texto


def datos_emisor_desde_snapshot(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    """snapshot['emisor'] -> datos_emisor de PDFFiscalService. Sin lectura de emisores_fiscales."""
    emisor = dict(snapshot.get("emisor") or {})
    punto_venta_num = emisor.get("punto_venta_num")
    return {
        "razon_social": str(emisor.get("razon_social") or ""),
        "nombre_fantasia": str(emisor.get("nombre_fantasia") or ""),
        "cuit": str(emisor.get("cuit") or ""),
        "condicion_iva": str(emisor.get("condicion_iva") or ""),
        "domicilio": str(emisor.get("domicilio") or ""),
        "ingresos_brutos": str(emisor.get("ingresos_brutos") or ""),
        "fecha_inicio_actividades": _fecha_iso_a_yyyymmdd(emisor.get("fecha_inicio_actividades")),
        "punto_venta": str(punto_venta_num) if punto_venta_num is not None else "",
    }


def datos_receptor_desde_snapshot(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    """snapshot['receptor'] -> datos_receptor de PDFFiscalService. Sin consultar cliente actual."""
    receptor = dict(snapshot.get("receptor") or {})
    documento_visible = str(receptor.get("documento_visible") or "")
    return {
        "razon_social": str(receptor.get("razon_social") or ""),
        "cuit": documento_visible,
        "documento": documento_visible,
        "condicion_iva": str(receptor.get("condicion_iva") or ""),
        "domicilio": str(receptor.get("domicilio") or ""),
    }


def _alicuota_iva_desde_snapshot(snapshot: Dict[str, Any]) -> str:
    iva_items = list(snapshot.get("iva") or [])
    if not iva_items:
        return "0"
    primero = iva_items[0]
    return str(primero.get("porcentaje") if isinstance(primero, dict) else "0") or "0"


def _items_desde_snapshot(snapshot: Dict[str, Any]) -> List[Dict[str, Any]]:
    filas = []
    for item in list(snapshot.get("items") or []):
        if not isinstance(item, dict):
            continue
        concepto = str(item.get("concepto") or "").strip()
        descripcion = str(item.get("descripcion") or "").strip()
        texto_item = f"{concepto} - {descripcion}" if concepto else descripcion
        filas.append(
            {
                "cantidad": item.get("cantidad"),
                "descripcion": texto_item or "Servicio",
                "precio_unitario": item.get("precio_unitario"),
                "importe": item.get("subtotal"),
            }
        )
    return filas


def datos_comprobante_desde_snapshot(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    """snapshot['comprobante'|'importes'|'iva'|'items'|'autorizacion'|'ambiente'] -> datos_comprobante."""
    comprobante = dict(snapshot.get("comprobante") or {})
    importes = dict(snapshot.get("importes") or {})
    autorizacion = dict(snapshot.get("autorizacion") or {})

    concepto_num = str(comprobante.get("concepto") or "").strip()
    concepto_descripcion = str(comprobante.get("concepto_descripcion") or "").strip()
    concepto_texto = f"{concepto_num} - {concepto_descripcion}" if concepto_num else concepto_descripcion

    punto_venta_num = comprobante.get("punto_venta_num")
    tipo_comprobante_num = comprobante.get("tipo_comprobante_num")
    numero_comprobante_num = comprobante.get("numero_comprobante_num")

    return {
        "tipo": str(comprobante.get("tipo_comprobante_texto") or ""),
        "numero": numero_comprobante_num,
        "numero_comprobante": numero_comprobante_num,
        "fecha": _fecha_iso_a_yyyymmdd(comprobante.get("fecha")),
        "concepto": concepto_texto,
        "periodo_servicio_desde": _fecha_iso_a_yyyymmdd(comprobante.get("periodo_servicio_desde")),
        "periodo_servicio_hasta": _fecha_iso_a_yyyymmdd(comprobante.get("periodo_servicio_hasta")),
        "vencimiento_pago": _fecha_iso_a_yyyymmdd(comprobante.get("vencimiento_pago")),
        "importe_neto": importes.get("neto"),
        "importe_iva": importes.get("iva"),
        "alicuota_iva": _alicuota_iva_desde_snapshot(snapshot),
        "importe_total": importes.get("total"),
        "items": _items_desde_snapshot(snapshot),
        "moneda": str(comprobante.get("moneda") or "PES"),
        "cotizacion": comprobante.get("cotizacion"),
        "cae": str(autorizacion.get("cae") or ""),
        "vencimiento_cae": _fecha_iso_a_yyyymmdd(autorizacion.get("vencimiento_cae")),
        "ambiente": str(snapshot.get("ambiente") or "HOMOLOGACION"),
        "punto_venta_num": punto_venta_num,
        "tipo_comprobante_num": tipo_comprobante_num,
        "numero_comprobante_num": numero_comprobante_num,
        "tipo_documento_receptor": (snapshot.get("receptor") or {}).get("tipo_documento_receptor"),
        "documento_receptor": (snapshot.get("receptor") or {}).get("documento_receptor"),
        "punto_venta": str(punto_venta_num) if punto_venta_num is not None else "",
    }


def datos_qr_desde_snapshot(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    """Construye los parametros de payload QR exclusivamente desde el snapshot."""
    emisor = dict(snapshot.get("emisor") or {})
    receptor = dict(snapshot.get("receptor") or {})
    comprobante = dict(snapshot.get("comprobante") or {})
    importes = dict(snapshot.get("importes") or {})
    autorizacion = dict(snapshot.get("autorizacion") or {})

    return {
        "ver": 1,
        "fecha": str(comprobante.get("fecha") or ""),
        "cuit_emisor": int(emisor.get("cuit") or 0),
        "punto_venta_num": int(comprobante.get("punto_venta_num") or 0),
        "tipo_comprobante_num": int(comprobante.get("tipo_comprobante_num") or 0),
        "numero_comprobante_num": int(comprobante.get("numero_comprobante_num") or 0),
        "importe": float(importes.get("total") or 0),
        "cae": str(autorizacion.get("cae") or ""),
        "tipo_documento_receptor": receptor.get("tipo_documento_receptor"),
        "numero_documento_receptor": receptor.get("documento_receptor"),
        "moneda": str(comprobante.get("moneda") or "PES"),
        "cotizacion": float(comprobante.get("cotizacion") or 1),
    }


def construir_datos_pdf_desde_snapshot(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    """Snapshot v1 valido -> dict con datos_emisor/datos_receptor/datos_comprobante para PDFFiscalService."""
    return {
        "datos_emisor": datos_emisor_desde_snapshot(snapshot),
        "datos_receptor": datos_receptor_desde_snapshot(snapshot),
        "datos_comprobante": datos_comprobante_desde_snapshot(snapshot),
    }
