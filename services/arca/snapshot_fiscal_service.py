"""
Snapshot fiscal inmutable v1.

Modulo puro: no consulta SQLite, servicios, red, WSAA/WSFE, UI ni ReportLab.
Construye, valida, serializa y verifica integridad del contrato fiscal v1.
"""

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any, Dict, List, Optional, Tuple


SNAPSHOT_VERSION = 1
CODIGO_VALIDO = "VALIDO"
CODIGO_JSON_INVALIDO = "JSON_INVALIDO"
CODIGO_VERSION_INVALIDA = "VERSION_INVALIDA"
CODIGO_ESTRUCTURA_INVALIDA = "ESTRUCTURA_INVALIDA"
CODIGO_HASH_INVALIDO = "HASH_INVALIDO"

_DECIMAL_MONETARIO = Decimal("0.01")
_DECIMAL_CANTIDAD = Decimal("0.000001")
_DECIMAL_COTIZACION = Decimal("0.000001")
_DECIMAL_PORCENTAJE = Decimal("0.01")

_RAIZ_KEYS = (
    "ambiente",
    "autorizacion",
    "comprobante",
    "creado_en",
    "emisor",
    "fuente",
    "importes",
    "items",
    "iva",
    "receptor",
    "version",
)
_EMISOR_KEYS = (
    "condicion_iva",
    "cuit",
    "domicilio",
    "emisor_fiscal_id",
    "emisor_id",
    "fecha_inicio_actividades",
    "ingresos_brutos",
    "nombre_fantasia",
    "punto_venta_num",
    "razon_social",
)
_RECEPTOR_KEYS = (
    "cliente_id",
    "condicion_iva",
    "documento_receptor",
    "documento_visible",
    "domicilio",
    "razon_social",
    "tipo_documento_receptor",
)
_COMPROBANTE_KEYS = (
    "concepto",
    "concepto_descripcion",
    "cotizacion",
    "fecha",
    "fecha_arca",
    "moneda",
    "numero_comprobante_num",
    "numero_textual",
    "periodo_servicio_desde",
    "periodo_servicio_hasta",
    "punto_venta_num",
    "tipo_comprobante_num",
    "tipo_comprobante_texto",
    "vencimiento_pago",
)
_IMPORTES_KEYS = ("exento", "iva", "neto", "no_gravado", "total", "tributos")
_IVA_KEYS = ("base_imponible", "id", "importe", "porcentaje")
_ITEM_KEYS = ("cantidad", "concepto", "descripcion", "precio_unitario", "subtotal")
_AUTORIZACION_KEYS = (
    "cae",
    "cerrado_en",
    "resultado",
    "tipo_cod_aut",
    "vencimiento_cae",
    "vencimiento_cae_arca",
)


class SnapshotFiscalError(ValueError):
    """Error deterministico de contrato snapshot fiscal."""


@dataclass(frozen=True)
class ResultadoIntegridadSnapshot:
    valido: bool
    codigo: str
    errores: Tuple[str, ...] = ()
    snapshot: Optional[Dict[str, Any]] = None


def construir_snapshot_fiscal_v1(
    *,
    fuente: str,
    creado_en: str,
    ambiente: str,
    emisor: Dict[str, Any],
    receptor: Dict[str, Any],
    comprobante: Dict[str, Any],
    importes: Dict[str, Any],
    iva: List[Dict[str, Any]],
    items: List[Dict[str, Any]],
    autorizacion: Dict[str, Any],
) -> Dict[str, Any]:
    """Construye un snapshot fiscal v1 desde datos ya resueltos."""
    snapshot = {
        "version": SNAPSHOT_VERSION,
        "fuente": _normalizar_fuente(fuente),
        "creado_en": _normalizar_datetime(creado_en, "creado_en"),
        "ambiente": _normalizar_ambiente(ambiente),
        "emisor": _construir_emisor(emisor),
        "receptor": _construir_receptor(receptor),
        "comprobante": _construir_comprobante(comprobante),
        "importes": _construir_importes(importes),
        "iva": [_construir_iva_item(item, indice) for indice, item in enumerate(list(iva or []))],
        "items": [_construir_item(item, indice) for indice, item in enumerate(list(items or []))],
        "autorizacion": _construir_autorizacion(autorizacion),
    }
    _validar_coherencia(snapshot)
    valido, errores = validar_snapshot_fiscal_v1(snapshot)
    if not valido:
        raise SnapshotFiscalError("; ".join(errores))
    return snapshot


def validar_snapshot_fiscal_v1(snapshot: Dict[str, Any]) -> Tuple[bool, Tuple[str, ...]]:
    """Valida estructura, tipos, formatos y valores permitidos del snapshot v1."""
    errores: List[str] = []
    if not isinstance(snapshot, dict):
        return False, ("snapshot debe ser objeto",)

    _validar_keys(snapshot, _RAIZ_KEYS, "snapshot", errores)
    if errores:
        return False, tuple(errores)

    if snapshot.get("version") != SNAPSHOT_VERSION:
        errores.append("version debe ser 1")
    if snapshot.get("fuente") not in {"cierre_normal", "recuperacion"}:
        errores.append("fuente invalida")
    _validar_datetime_valor(snapshot.get("creado_en"), "creado_en", errores)
    if snapshot.get("ambiente") not in {"HOMOLOGACION", "PRODUCCION"}:
        errores.append("ambiente invalido")

    _validar_emisor(snapshot.get("emisor"), errores)
    _validar_receptor(snapshot.get("receptor"), errores)
    _validar_comprobante(snapshot.get("comprobante"), errores)
    _validar_importes(snapshot.get("importes"), errores)
    _validar_iva(snapshot.get("iva"), errores)
    _validar_items(snapshot.get("items"), errores)
    _validar_autorizacion(snapshot.get("autorizacion"), errores)
    _validar_sin_float(snapshot, "snapshot", errores)
    if not errores:
        try:
            _validar_coherencia(snapshot)
        except SnapshotFiscalError as error:
            errores.append(str(error))
    return not errores, tuple(errores)


def serializar_snapshot_fiscal(snapshot: Dict[str, Any]) -> str:
    """Serializa el snapshot con el formato canonico persistible."""
    valido, errores = validar_snapshot_fiscal_v1(snapshot)
    if not valido:
        raise SnapshotFiscalError("; ".join(errores))
    return json.dumps(snapshot, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def calcular_hash_snapshot(serializado: str) -> str:
    """Calcula SHA-256 hexadecimal lowercase sobre UTF-8 del JSON canonico."""
    if not isinstance(serializado, str) or not serializado:
        raise SnapshotFiscalError("serializado debe ser string no vacio")
    return hashlib.sha256(serializado.encode("utf-8")).hexdigest()


def validar_integridad_snapshot(json_text: str, version: int, snapshot_hash: str) -> ResultadoIntegridadSnapshot:
    """Valida parseo, version, contrato y hash del snapshot persistido."""
    try:
        snapshot = json.loads(json_text)
    except (TypeError, json.JSONDecodeError):
        return ResultadoIntegridadSnapshot(False, CODIGO_JSON_INVALIDO, ("JSON invalido",))

    if not isinstance(snapshot, dict):
        return ResultadoIntegridadSnapshot(False, CODIGO_ESTRUCTURA_INVALIDA, ("raiz no es objeto",))

    if snapshot.get("version") != SNAPSHOT_VERSION or version != SNAPSHOT_VERSION:
        return ResultadoIntegridadSnapshot(False, CODIGO_VERSION_INVALIDA, ("version invalida",), snapshot)

    valido, errores = validar_snapshot_fiscal_v1(snapshot)
    if not valido:
        return ResultadoIntegridadSnapshot(False, CODIGO_ESTRUCTURA_INVALIDA, errores, snapshot)

    serializado = serializar_snapshot_fiscal(snapshot)
    hash_calculado = calcular_hash_snapshot(serializado)
    if not isinstance(snapshot_hash, str) or not re.fullmatch(r"[0-9a-f]{64}", snapshot_hash or ""):
        return ResultadoIntegridadSnapshot(False, CODIGO_HASH_INVALIDO, ("hash invalido",), snapshot)
    if hash_calculado != snapshot_hash:
        return ResultadoIntegridadSnapshot(False, CODIGO_HASH_INVALIDO, ("hash no coincide",), snapshot)

    return ResultadoIntegridadSnapshot(True, CODIGO_VALIDO, (), snapshot)


def _construir_emisor(datos: Dict[str, Any]) -> Dict[str, Any]:
    _requerir_dict(datos, "emisor")
    return {
        "emisor_id": _normalizar_int(datos.get("emisor_id"), "emisor.emisor_id", minimo=1),
        "emisor_fiscal_id": _normalizar_int(datos.get("emisor_fiscal_id"), "emisor.emisor_fiscal_id", minimo=1),
        "razon_social": _normalizar_str(datos.get("razon_social"), "emisor.razon_social"),
        "nombre_fantasia": _normalizar_str_nullable(datos.get("nombre_fantasia"), "emisor.nombre_fantasia"),
        "cuit": _normalizar_cuit(datos.get("cuit"), "emisor.cuit"),
        "condicion_iva": _normalizar_str(datos.get("condicion_iva"), "emisor.condicion_iva"),
        "domicilio": _normalizar_str_nullable(datos.get("domicilio"), "emisor.domicilio"),
        "ingresos_brutos": _normalizar_str_nullable(datos.get("ingresos_brutos"), "emisor.ingresos_brutos"),
        "fecha_inicio_actividades": _normalizar_fecha_nullable(
            datos.get("fecha_inicio_actividades"), "emisor.fecha_inicio_actividades"
        ),
        "punto_venta_num": _normalizar_int(datos.get("punto_venta_num"), "emisor.punto_venta_num", minimo=1),
    }


def _construir_receptor(datos: Dict[str, Any]) -> Dict[str, Any]:
    _requerir_dict(datos, "receptor")
    return {
        "cliente_id": _normalizar_int(datos.get("cliente_id"), "receptor.cliente_id", minimo=1),
        "razon_social": _normalizar_str(datos.get("razon_social"), "receptor.razon_social"),
        "documento_visible": _normalizar_str(datos.get("documento_visible"), "receptor.documento_visible"),
        "condicion_iva": _normalizar_str(datos.get("condicion_iva"), "receptor.condicion_iva"),
        "domicilio": _normalizar_str_nullable(datos.get("domicilio"), "receptor.domicilio"),
        "tipo_documento_receptor": _normalizar_int(
            datos.get("tipo_documento_receptor"), "receptor.tipo_documento_receptor", minimo=0
        ),
        "documento_receptor": _normalizar_int(datos.get("documento_receptor"), "receptor.documento_receptor", minimo=0),
    }


def _construir_comprobante(datos: Dict[str, Any]) -> Dict[str, Any]:
    _requerir_dict(datos, "comprobante")
    return {
        "fecha": _normalizar_fecha(datos.get("fecha"), "comprobante.fecha"),
        "fecha_arca": _normalizar_fecha_arca(datos.get("fecha_arca"), "comprobante.fecha_arca"),
        "concepto": _normalizar_concepto(datos.get("concepto")),
        "concepto_descripcion": _normalizar_str(datos.get("concepto_descripcion"), "comprobante.concepto_descripcion"),
        "punto_venta_num": _normalizar_int(datos.get("punto_venta_num"), "comprobante.punto_venta_num", minimo=1),
        "tipo_comprobante_num": _normalizar_int(
            datos.get("tipo_comprobante_num"), "comprobante.tipo_comprobante_num", minimo=1
        ),
        "tipo_comprobante_texto": _normalizar_str(
            datos.get("tipo_comprobante_texto"), "comprobante.tipo_comprobante_texto"
        ),
        "numero_comprobante_num": _normalizar_int(
            datos.get("numero_comprobante_num"), "comprobante.numero_comprobante_num", minimo=1
        ),
        "numero_textual": _normalizar_str(datos.get("numero_textual"), "comprobante.numero_textual"),
        "periodo_servicio_desde": _normalizar_fecha_nullable(
            datos.get("periodo_servicio_desde"), "comprobante.periodo_servicio_desde"
        ),
        "periodo_servicio_hasta": _normalizar_fecha_nullable(
            datos.get("periodo_servicio_hasta"), "comprobante.periodo_servicio_hasta"
        ),
        "vencimiento_pago": _normalizar_fecha_nullable(datos.get("vencimiento_pago"), "comprobante.vencimiento_pago"),
        "moneda": _normalizar_str(datos.get("moneda"), "comprobante.moneda"),
        "cotizacion": _normalizar_decimal(datos.get("cotizacion"), "comprobante.cotizacion", _DECIMAL_COTIZACION),
    }


def _construir_importes(datos: Dict[str, Any]) -> Dict[str, Any]:
    _requerir_dict(datos, "importes")
    return {
        "total": _normalizar_decimal(datos.get("total"), "importes.total", _DECIMAL_MONETARIO),
        "neto": _normalizar_decimal(datos.get("neto"), "importes.neto", _DECIMAL_MONETARIO),
        "iva": _normalizar_decimal(datos.get("iva"), "importes.iva", _DECIMAL_MONETARIO),
        "exento": _normalizar_decimal(datos.get("exento"), "importes.exento", _DECIMAL_MONETARIO),
        "no_gravado": _normalizar_decimal(datos.get("no_gravado"), "importes.no_gravado", _DECIMAL_MONETARIO),
        "tributos": _normalizar_decimal(datos.get("tributos"), "importes.tributos", _DECIMAL_MONETARIO),
    }


def _construir_iva_item(datos: Dict[str, Any], indice: int) -> Dict[str, Any]:
    _requerir_dict(datos, f"iva[{indice}]")
    return {
        "id": _normalizar_int(datos.get("id"), f"iva[{indice}].id", minimo=1),
        "base_imponible": _normalizar_decimal(
            datos.get("base_imponible"), f"iva[{indice}].base_imponible", _DECIMAL_MONETARIO
        ),
        "importe": _normalizar_decimal(datos.get("importe"), f"iva[{indice}].importe", _DECIMAL_MONETARIO),
        "porcentaje": _normalizar_decimal(datos.get("porcentaje"), f"iva[{indice}].porcentaje", _DECIMAL_PORCENTAJE),
    }


def _construir_item(datos: Dict[str, Any], indice: int) -> Dict[str, Any]:
    _requerir_dict(datos, f"items[{indice}]")
    return {
        "concepto": _normalizar_str_nullable(datos.get("concepto"), f"items[{indice}].concepto"),
        "descripcion": _normalizar_str(datos.get("descripcion"), f"items[{indice}].descripcion"),
        "cantidad": _normalizar_decimal(datos.get("cantidad"), f"items[{indice}].cantidad", _DECIMAL_CANTIDAD),
        "precio_unitario": _normalizar_decimal(
            datos.get("precio_unitario"), f"items[{indice}].precio_unitario", _DECIMAL_MONETARIO
        ),
        "subtotal": _normalizar_decimal(datos.get("subtotal"), f"items[{indice}].subtotal", _DECIMAL_MONETARIO),
    }


def _construir_autorizacion(datos: Dict[str, Any]) -> Dict[str, Any]:
    _requerir_dict(datos, "autorizacion")
    resultado = str(datos.get("resultado") or "").strip().upper()
    if resultado == "A":
        resultado = "AUTORIZADO"
    return {
        "cae": _normalizar_cae(datos.get("cae")),
        "vencimiento_cae": _normalizar_fecha(datos.get("vencimiento_cae"), "autorizacion.vencimiento_cae"),
        "vencimiento_cae_arca": _normalizar_fecha_arca(
            datos.get("vencimiento_cae_arca"), "autorizacion.vencimiento_cae_arca"
        ),
        "tipo_cod_aut": _normalizar_tipo_cod_aut(datos.get("tipo_cod_aut")),
        "resultado": resultado,
        "cerrado_en": _normalizar_datetime(datos.get("cerrado_en"), "autorizacion.cerrado_en"),
    }


def _normalizar_fuente(valor: Any) -> str:
    texto = str(valor or "").strip()
    if texto not in {"cierre_normal", "recuperacion"}:
        raise SnapshotFiscalError("fuente invalida")
    return texto


def _normalizar_ambiente(valor: Any) -> str:
    texto = str(valor or "").strip().upper()
    if texto not in {"HOMOLOGACION", "PRODUCCION"}:
        raise SnapshotFiscalError("ambiente invalido")
    return texto


def _normalizar_str(valor: Any, campo: str) -> str:
    if valor is None:
        raise SnapshotFiscalError(f"{campo} obligatorio")
    texto = str(valor).strip()
    if not texto:
        raise SnapshotFiscalError(f"{campo} obligatorio")
    return texto


def _normalizar_str_nullable(valor: Any, campo: str) -> Optional[str]:
    if valor is None:
        return None
    texto = str(valor).strip()
    return texto if texto else None


def _normalizar_int(valor: Any, campo: str, minimo: int) -> int:
    if isinstance(valor, bool) or valor is None:
        raise SnapshotFiscalError(f"{campo} debe ser entero")
    try:
        numero = int(str(valor).strip())
    except (TypeError, ValueError) as error:
        raise SnapshotFiscalError(f"{campo} debe ser entero") from error
    if numero < minimo:
        raise SnapshotFiscalError(f"{campo} fuera de rango")
    return numero


def _normalizar_decimal(valor: Any, campo: str, quantum: Decimal) -> str:
    if isinstance(valor, float):
        raise SnapshotFiscalError(f"{campo} no acepta float")
    if valor is None or isinstance(valor, bool):
        raise SnapshotFiscalError(f"{campo} decimal invalido")
    try:
        decimal = Decimal(str(valor).strip())
    except (InvalidOperation, ValueError, TypeError, AttributeError) as error:
        raise SnapshotFiscalError(f"{campo} decimal invalido") from error
    if not decimal.is_finite():
        raise SnapshotFiscalError(f"{campo} decimal invalido")
    if decimal < 0:
        raise SnapshotFiscalError(f"{campo} no puede ser negativo")
    return format(decimal.quantize(quantum, rounding=ROUND_HALF_UP), "f")


def _normalizar_fecha(valor: Any, campo: str) -> str:
    texto = str(valor or "").strip()
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", texto):
        raise SnapshotFiscalError(f"{campo} debe tener formato YYYY-MM-DD")
    try:
        datetime.strptime(texto, "%Y-%m-%d")
    except ValueError as error:
        raise SnapshotFiscalError(f"{campo} fecha invalida") from error
    return texto


def _normalizar_fecha_nullable(valor: Any, campo: str) -> Optional[str]:
    if valor is None:
        return None
    return _normalizar_fecha(valor, campo)


def _normalizar_fecha_arca(valor: Any, campo: str) -> str:
    texto = str(valor or "").strip()
    if not re.fullmatch(r"\d{8}", texto):
        raise SnapshotFiscalError(f"{campo} debe tener formato YYYYMMDD")
    try:
        datetime.strptime(texto, "%Y%m%d")
    except ValueError as error:
        raise SnapshotFiscalError(f"{campo} fecha invalida") from error
    return texto


def _normalizar_datetime(valor: Any, campo: str) -> str:
    texto = str(valor or "").strip()
    if not texto:
        raise SnapshotFiscalError(f"{campo} obligatorio")
    try:
        datetime.fromisoformat(texto)
    except ValueError as error:
        raise SnapshotFiscalError(f"{campo} datetime invalido") from error
    return texto


def _normalizar_cuit(valor: Any, campo: str) -> str:
    texto = str(valor or "").strip()
    if not re.fullmatch(r"\d{11}", texto):
        raise SnapshotFiscalError(f"{campo} debe contener 11 digitos")
    return texto


def _normalizar_cae(valor: Any) -> str:
    texto = str(valor or "").strip()
    if not re.fullmatch(r"\d{14}", texto):
        raise SnapshotFiscalError("autorizacion.cae debe contener 14 digitos")
    return texto


def _normalizar_tipo_cod_aut(valor: Any) -> str:
    texto = str(valor or "").strip().upper()
    if texto != "E":
        raise SnapshotFiscalError("autorizacion.tipo_cod_aut debe ser E")
    return texto


def _normalizar_concepto(valor: Any) -> int:
    concepto = _normalizar_int(valor, "comprobante.concepto", minimo=1)
    if concepto not in {1, 2, 3}:
        raise SnapshotFiscalError("comprobante.concepto invalido")
    return concepto


def _requerir_dict(valor: Any, campo: str) -> None:
    if not isinstance(valor, dict):
        raise SnapshotFiscalError(f"{campo} debe ser objeto")


def _validar_keys(objeto: Dict[str, Any], esperadas: Tuple[str, ...], campo: str, errores: List[str]) -> None:
    actuales = set(objeto.keys()) if isinstance(objeto, dict) else set()
    esperadas_set = set(esperadas)
    faltantes = sorted(esperadas_set - actuales)
    extras = sorted(actuales - esperadas_set)
    if faltantes:
        errores.append(f"{campo} claves faltantes: {', '.join(faltantes)}")
    if extras:
        errores.append(f"{campo} claves no permitidas: {', '.join(extras)}")


def _validar_emisor(valor: Any, errores: List[str]) -> None:
    if not isinstance(valor, dict):
        errores.append("emisor debe ser objeto")
        return
    _validar_keys(valor, _EMISOR_KEYS, "emisor", errores)
    for campo in ("emisor_id", "emisor_fiscal_id", "punto_venta_num"):
        _validar_entero_valor(valor.get(campo), f"emisor.{campo}", errores, minimo=1)
    for campo in ("razon_social", "condicion_iva"):
        _validar_str_obligatorio(valor.get(campo), f"emisor.{campo}", errores)
    _validar_cuit_valor(valor.get("cuit"), "emisor.cuit", errores)
    _validar_fecha_nullable_valor(valor.get("fecha_inicio_actividades"), "emisor.fecha_inicio_actividades", errores)


def _validar_receptor(valor: Any, errores: List[str]) -> None:
    if not isinstance(valor, dict):
        errores.append("receptor debe ser objeto")
        return
    _validar_keys(valor, _RECEPTOR_KEYS, "receptor", errores)
    _validar_entero_valor(valor.get("cliente_id"), "receptor.cliente_id", errores, minimo=1)
    _validar_entero_valor(valor.get("tipo_documento_receptor"), "receptor.tipo_documento_receptor", errores, minimo=0)
    _validar_entero_valor(valor.get("documento_receptor"), "receptor.documento_receptor", errores, minimo=0)
    for campo in ("razon_social", "documento_visible", "condicion_iva"):
        _validar_str_obligatorio(valor.get(campo), f"receptor.{campo}", errores)


def _validar_comprobante(valor: Any, errores: List[str]) -> None:
    if not isinstance(valor, dict):
        errores.append("comprobante debe ser objeto")
        return
    _validar_keys(valor, _COMPROBANTE_KEYS, "comprobante", errores)
    _validar_fecha_valor(valor.get("fecha"), "comprobante.fecha", errores)
    _validar_fecha_arca_valor(valor.get("fecha_arca"), "comprobante.fecha_arca", errores)
    _validar_entero_valor(valor.get("concepto"), "comprobante.concepto", errores, minimo=1)
    if valor.get("concepto") not in {1, 2, 3}:
        errores.append("comprobante.concepto invalido")
    for campo in ("punto_venta_num", "tipo_comprobante_num", "numero_comprobante_num"):
        _validar_entero_valor(valor.get(campo), f"comprobante.{campo}", errores, minimo=1)
    for campo in ("concepto_descripcion", "tipo_comprobante_texto", "numero_textual", "moneda", "cotizacion"):
        _validar_str_obligatorio(valor.get(campo), f"comprobante.{campo}", errores)
    _validar_decimal_string(valor.get("cotizacion"), "comprobante.cotizacion", 6, errores)
    for campo in ("periodo_servicio_desde", "periodo_servicio_hasta", "vencimiento_pago"):
        _validar_fecha_nullable_valor(valor.get(campo), f"comprobante.{campo}", errores)


def _validar_importes(valor: Any, errores: List[str]) -> None:
    if not isinstance(valor, dict):
        errores.append("importes debe ser objeto")
        return
    _validar_keys(valor, _IMPORTES_KEYS, "importes", errores)
    for campo in _IMPORTES_KEYS:
        _validar_decimal_string(valor.get(campo), f"importes.{campo}", 2, errores)


def _validar_iva(valor: Any, errores: List[str]) -> None:
    if not isinstance(valor, list):
        errores.append("iva debe ser lista")
        return
    for indice, item in enumerate(valor):
        if not isinstance(item, dict):
            errores.append(f"iva[{indice}] debe ser objeto")
            continue
        _validar_keys(item, _IVA_KEYS, f"iva[{indice}]", errores)
        _validar_entero_valor(item.get("id"), f"iva[{indice}].id", errores, minimo=1)
        _validar_decimal_string(item.get("base_imponible"), f"iva[{indice}].base_imponible", 2, errores)
        _validar_decimal_string(item.get("importe"), f"iva[{indice}].importe", 2, errores)
        _validar_decimal_string(item.get("porcentaje"), f"iva[{indice}].porcentaje", 2, errores)


def _validar_items(valor: Any, errores: List[str]) -> None:
    if not isinstance(valor, list):
        errores.append("items debe ser lista")
        return
    for indice, item in enumerate(valor):
        if not isinstance(item, dict):
            errores.append(f"items[{indice}] debe ser objeto")
            continue
        _validar_keys(item, _ITEM_KEYS, f"items[{indice}]", errores)
        if item.get("concepto") is not None and not isinstance(item.get("concepto"), str):
            errores.append(f"items[{indice}].concepto debe ser string o null")
        _validar_str_obligatorio(item.get("descripcion"), f"items[{indice}].descripcion", errores)
        _validar_decimal_string(item.get("cantidad"), f"items[{indice}].cantidad", 6, errores)
        _validar_decimal_string(item.get("precio_unitario"), f"items[{indice}].precio_unitario", 2, errores)
        _validar_decimal_string(item.get("subtotal"), f"items[{indice}].subtotal", 2, errores)


def _validar_autorizacion(valor: Any, errores: List[str]) -> None:
    if not isinstance(valor, dict):
        errores.append("autorizacion debe ser objeto")
        return
    _validar_keys(valor, _AUTORIZACION_KEYS, "autorizacion", errores)
    if not isinstance(valor.get("cae"), str) or not re.fullmatch(r"\d{14}", valor.get("cae") or ""):
        errores.append("autorizacion.cae invalido")
    _validar_fecha_valor(valor.get("vencimiento_cae"), "autorizacion.vencimiento_cae", errores)
    _validar_fecha_arca_valor(valor.get("vencimiento_cae_arca"), "autorizacion.vencimiento_cae_arca", errores)
    if valor.get("tipo_cod_aut") != "E":
        errores.append("autorizacion.tipo_cod_aut invalido")
    if valor.get("resultado") != "AUTORIZADO":
        errores.append("autorizacion.resultado invalido")
    _validar_datetime_valor(valor.get("cerrado_en"), "autorizacion.cerrado_en", errores)


def _validar_coherencia(snapshot: Dict[str, Any]) -> None:
    comprobante = snapshot["comprobante"]
    emisor = snapshot["emisor"]
    autorizacion = snapshot["autorizacion"]
    if emisor["punto_venta_num"] != comprobante["punto_venta_num"]:
        raise SnapshotFiscalError("punto_venta_num de emisor y comprobante no coincide")
    if comprobante["fecha"].replace("-", "") != comprobante["fecha_arca"]:
        raise SnapshotFiscalError("fecha y fecha_arca no coinciden")
    if autorizacion["vencimiento_cae"].replace("-", "") != autorizacion["vencimiento_cae_arca"]:
        raise SnapshotFiscalError("vencimiento_cae y vencimiento_cae_arca no coinciden")


def _validar_sin_float(valor: Any, ruta: str, errores: List[str]) -> None:
    if isinstance(valor, float):
        errores.append(f"{ruta} contiene float")
    elif isinstance(valor, dict):
        for clave, contenido in valor.items():
            _validar_sin_float(contenido, f"{ruta}.{clave}", errores)
    elif isinstance(valor, list):
        for indice, contenido in enumerate(valor):
            _validar_sin_float(contenido, f"{ruta}[{indice}]", errores)


def _validar_entero_valor(valor: Any, campo: str, errores: List[str], minimo: int) -> None:
    if isinstance(valor, bool) or not isinstance(valor, int) or valor < minimo:
        errores.append(f"{campo} entero invalido")


def _validar_str_obligatorio(valor: Any, campo: str, errores: List[str]) -> None:
    if not isinstance(valor, str) or not valor.strip():
        errores.append(f"{campo} obligatorio")


def _validar_cuit_valor(valor: Any, campo: str, errores: List[str]) -> None:
    if not isinstance(valor, str) or not re.fullmatch(r"\d{11}", valor):
        errores.append(f"{campo} invalido")


def _validar_fecha_valor(valor: Any, campo: str, errores: List[str]) -> None:
    try:
        _normalizar_fecha(valor, campo)
    except SnapshotFiscalError as error:
        errores.append(str(error))


def _validar_fecha_nullable_valor(valor: Any, campo: str, errores: List[str]) -> None:
    if valor is None:
        return
    _validar_fecha_valor(valor, campo, errores)


def _validar_fecha_arca_valor(valor: Any, campo: str, errores: List[str]) -> None:
    try:
        _normalizar_fecha_arca(valor, campo)
    except SnapshotFiscalError as error:
        errores.append(str(error))


def _validar_datetime_valor(valor: Any, campo: str, errores: List[str]) -> None:
    try:
        _normalizar_datetime(valor, campo)
    except SnapshotFiscalError as error:
        errores.append(str(error))


def _validar_decimal_string(valor: Any, campo: str, escala: int, errores: List[str]) -> None:
    if not isinstance(valor, str) or not re.fullmatch(rf"\d+\.\d{{{escala}}}", valor):
        errores.append(f"{campo} decimal canonico invalido")
