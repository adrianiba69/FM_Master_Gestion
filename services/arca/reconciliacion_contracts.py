from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from enum import Enum


class EstadoIntentoEmision(str, Enum):
    PENDIENTE_RECONCILIAR = "PENDIENTE_RECONCILIAR"
    ENVIANDO = "ENVIANDO"
    RECONCILIADO = "RECONCILIADO"
    NO_AUTORIZADO = "NO_AUTORIZADO"
    RECHAZADO = "RECHAZADO"
    CONFLICTO_MANUAL = "CONFLICTO_MANUAL"


class ResultadoReconciliacion(str, Enum):
    AUTORIZADO = "AUTORIZADO"
    NO_AUTORIZADO = "NO_AUTORIZADO"
    CONFLICTO = "CONFLICTO"
    CONSULTA_INCIERTA = "CONSULTA_INCIERTA"


@dataclass(frozen=True)
class SnapshotFiscalEsperado:
    resumen_id: int
    cliente_id: int
    emisor_fiscal_id: int
    emisor_id: int
    cuit_emisor: str
    punto_venta: int
    tipo_comprobante: int
    numero_planificado: int
    fecha_comprobante: str
    concepto: int
    tipo_documento: int
    documento_receptor: int
    condicion_iva_receptor_id: int
    importe_total: Decimal
    importe_neto: Decimal
    importe_iva: Decimal
    importe_exento: Decimal
    importe_no_gravado: Decimal
    importe_tributos: Decimal
    moneda: str
    cotizacion: Decimal
    alicuotas_iva: tuple = field(default_factory=tuple)


@dataclass(frozen=True)
class DiferenciaFiscal:
    campo: str
    esperado: object
    arca: object

    def como_texto(self):
        return f"{self.campo} esperado {self.esperado} / ARCA {self.arca}"


@dataclass(frozen=True)
class ResultadoComparacionFiscal:
    resultado: ResultadoReconciliacion
    diferencias: tuple = field(default_factory=tuple)
    campos_faltantes: tuple = field(default_factory=tuple)

    @property
    def diferencias_texto(self):
        return tuple(diferencia.como_texto() for diferencia in self.diferencias)


DECIMAL_ESCALA = Decimal("0.01")
DECIMAL_TOLERANCIA = Decimal("0.00")

_CAMPOS_CONSULTA_OBLIGATORIOS = (
    "cuit_emisor",
    "punto_venta",
    "tipo_comprobante",
    "numero_comprobante",
    "fecha_comprobante",
    "doc_tipo",
    "doc_nro",
    "importe_total",
    "importe_neto",
    "importe_iva",
    "moneda",
    "cotizacion",
    "condicion_iva_receptor_id",
)


def normalizar_importe(valor):
    """Convierte importes a centavos Decimal, sin introducir errores binarios."""
    try:
        importe = Decimal(str(valor))
    except (InvalidOperation, TypeError, ValueError) as error:
        raise ValueError(f"Importe inválido: {valor!r}") from error
    return importe.quantize(DECIMAL_ESCALA, rounding=ROUND_HALF_UP)


def _normalizar_fecha(valor):
    texto = str(valor or "").strip()
    if len(texto) == 8 and texto.isdigit():
        return texto
    if len(texto) == 10 and texto[4] == "-" and texto[7] == "-":
        try:
            return datetime.strptime(texto, "%Y-%m-%d").strftime("%Y%m%d")
        except ValueError:
            return texto
    return texto


def _valor_faltante(datos, campo):
    if campo not in datos:
        return True
    valor = datos.get(campo)
    return valor is None or (isinstance(valor, str) and not valor.strip())


def _agregar_diferencia(diferencias, campo, esperado, arca):
    if esperado != arca:
        diferencias.append(DiferenciaFiscal(campo, esperado, arca))


def comparar_snapshot_con_comprobante(snapshot, comprobante):
    """Compara un snapshot local con un resultado ya normalizado de FECompConsultar."""
    if not isinstance(comprobante, dict):
        return ResultadoComparacionFiscal(
            ResultadoReconciliacion.CONSULTA_INCIERTA,
            campos_faltantes=("resultado_normalizado",),
        )

    campos_faltantes = tuple(
        campo
        for campo in _CAMPOS_CONSULTA_OBLIGATORIOS
        if _valor_faltante(comprobante, campo)
    )
    if campos_faltantes:
        return ResultadoComparacionFiscal(
            ResultadoReconciliacion.CONSULTA_INCIERTA,
            campos_faltantes=campos_faltantes,
        )

    diferencias = []
    _agregar_diferencia(diferencias, "cuit_emisor", snapshot.cuit_emisor, str(comprobante["cuit_emisor"]).strip())
    _agregar_diferencia(diferencias, "punto_venta", snapshot.punto_venta, int(comprobante["punto_venta"]))
    _agregar_diferencia(diferencias, "tipo_comprobante", snapshot.tipo_comprobante, int(comprobante["tipo_comprobante"]))
    _agregar_diferencia(diferencias, "numero_comprobante", snapshot.numero_planificado, int(comprobante["numero_comprobante"]))
    _agregar_diferencia(
        diferencias,
        "fecha_comprobante",
        _normalizar_fecha(snapshot.fecha_comprobante),
        _normalizar_fecha(comprobante["fecha_comprobante"]),
    )
    _agregar_diferencia(diferencias, "tipo_documento", snapshot.tipo_documento, int(comprobante["doc_tipo"]))
    _agregar_diferencia(diferencias, "documento_receptor", snapshot.documento_receptor, int(comprobante["doc_nro"]))

    for campo_snapshot, campo_arca in (
        ("importe_total", "importe_total"),
        ("importe_neto", "importe_neto"),
        ("importe_iva", "importe_iva"),
        ("cotizacion", "cotizacion"),
    ):
        esperado = normalizar_importe(getattr(snapshot, campo_snapshot))
        arca = normalizar_importe(comprobante[campo_arca])
        if abs(esperado - arca) > DECIMAL_TOLERANCIA:
            diferencias.append(DiferenciaFiscal(campo_snapshot, esperado, arca))

    _agregar_diferencia(diferencias, "moneda", snapshot.moneda, str(comprobante["moneda"]).strip())
    _agregar_diferencia(
        diferencias,
        "condicion_iva_receptor_id",
        snapshot.condicion_iva_receptor_id,
        int(comprobante["condicion_iva_receptor_id"]),
    )

    if not str(comprobante["cae"]).strip():
        diferencias.append(DiferenciaFiscal("cae", "presente", "ausente"))
    if not str(comprobante["vencimiento_cae"]).strip():
        diferencias.append(DiferenciaFiscal("vencimiento_cae", "presente", "ausente"))

    resultado = ResultadoReconciliacion.AUTORIZADO if not diferencias else ResultadoReconciliacion.CONFLICTO
    return ResultadoComparacionFiscal(resultado, diferencias=tuple(diferencias))