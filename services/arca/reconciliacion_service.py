import json
from dataclasses import dataclass

from models.intento_emision_arca import IntentoEmisionArca
from services.arca.homologacion_service import HomologacionService
from services.arca.reconciliacion_contracts import (
    ResultadoComparacionFiscal,
    ResultadoReconciliacion,
    SnapshotFiscalEsperado,
    comparar_snapshot_con_comprobante,
)
from services.emisor_fiscal_service import EmisorFiscalService
from services.intento_emision_arca_service import IntentoEmisionArcaService


@dataclass(frozen=True)
class ResultadoEjecucionReconciliacion:
    ok: bool
    intento_id: int
    resultado: ResultadoReconciliacion
    mensaje: str = ""
    comparacion: ResultadoComparacionFiscal = None
    consulta: dict = None


class ReconciliacionArcaService:
    """Orquesta únicamente la consulta y comparación de un intento ya persistido."""

    def __init__(
        self,
        intentos_service=None,
        emisor_fiscal_provider=None,
        consultar_comprobante=None,
    ):
        self._intentos_service = intentos_service or IntentoEmisionArcaService()
        self._emisor_fiscal_provider = emisor_fiscal_provider or EmisorFiscalService
        self._consultar_comprobante = consultar_comprobante or HomologacionService.consultar_comprobante_emitido

    @staticmethod
    def _snapshot_desde_intento(intento):
        if not isinstance(intento, IntentoEmisionArca):
            raise TypeError("intento debe ser IntentoEmisionArca.")
        return SnapshotFiscalEsperado(
            resumen_id=intento.resumen_id,
            cliente_id=intento.cliente_id,
            emisor_fiscal_id=intento.emisor_fiscal_id,
            emisor_id=intento.emisor_id,
            cuit_emisor=intento.cuit_emisor,
            punto_venta=intento.punto_venta,
            tipo_comprobante=intento.tipo_comprobante,
            numero_planificado=intento.numero_planificado,
            fecha_comprobante=intento.fecha_comprobante,
            concepto=intento.concepto,
            tipo_documento=intento.tipo_documento,
            documento_receptor=intento.documento_receptor,
            condicion_iva_receptor_id=intento.condicion_iva_receptor_id,
            importe_total=intento.importe_total,
            importe_neto=intento.importe_neto,
            importe_iva=intento.importe_iva,
            importe_exento=intento.importe_exento,
            importe_no_gravado=intento.importe_no_gravado,
            importe_tributos=intento.importe_tributos,
            moneda=intento.moneda,
            cotizacion=intento.cotizacion,
            alicuotas_iva=intento.alicuotas_iva,
        )

    @staticmethod
    def _detalle_consulta(consulta, comparacion=None):
        detalle = {"consulta": consulta if isinstance(consulta, dict) else {}}
        if comparacion is not None:
            detalle["resultado"] = comparacion.resultado.value
            detalle["diferencias"] = list(comparacion.diferencias_texto)
            detalle["campos_faltantes"] = list(comparacion.campos_faltantes)
        return json.dumps(detalle, ensure_ascii=True, sort_keys=True, default=str, separators=(",", ":"))

    def _guardar_consulta_incierta(self, intento_id, mensaje, consulta=None):
        self._intentos_service.guardar_resultado_reconciliacion(
            intento_id,
            ResultadoReconciliacion.CONSULTA_INCIERTA,
            error_codigo="CONSULTA_ARCA_INCIERTA",
            error_mensaje=mensaje,
            detalle_tecnico=self._detalle_consulta(consulta),
        )
        return ResultadoEjecucionReconciliacion(
            ok=False,
            intento_id=intento_id,
            resultado=ResultadoReconciliacion.CONSULTA_INCIERTA,
            mensaje=mensaje,
            consulta=consulta if isinstance(consulta, dict) else None,
        )

    def reconciliar_intento(self, intento_id):
        intento = self._intentos_service.obtener(intento_id)
        if not intento:
            raise LookupError(f"Intento de emisión ARCA inexistente: {intento_id}")

        emisor_fiscal = self._emisor_fiscal_provider.obtener(intento.emisor_fiscal_id)
        if not emisor_fiscal:
            return self._guardar_consulta_incierta(
                intento.id,
                "No se encontró el emisor fiscal del intento para consultar ARCA.",
            )

        ruta_certificado = str(emisor_fiscal[13] if len(emisor_fiscal) > 13 else "" or "").strip()
        ruta_clave = str(emisor_fiscal[14] if len(emisor_fiscal) > 14 else "" or "").strip()
        carpeta_trabajo = str(emisor_fiscal[15] if len(emisor_fiscal) > 15 else "" or "").strip()
        if not ruta_certificado or not ruta_clave or not carpeta_trabajo:
            return self._guardar_consulta_incierta(
                intento.id,
                "El emisor fiscal del intento no tiene credenciales o carpeta de trabajo completas.",
            )

        try:
            consulta = self._consultar_comprobante(
                ruta_certificado=ruta_certificado,
                ruta_clave=ruta_clave,
                cuit_emisor=intento.cuit_emisor,
                punto_venta=intento.punto_venta,
                tipo_comprobante=intento.tipo_comprobante,
                numero_comprobante=intento.numero_planificado,
                carpeta_trabajo=carpeta_trabajo,
            )
        except Exception as error:
            return self._guardar_consulta_incierta(
                intento.id,
                f"Error al consultar ARCA: {error}",
            )

        if not isinstance(consulta, dict) or not consulta.get("ok"):
            errores = consulta.get("errores") if isinstance(consulta, dict) else None
            mensaje = "; ".join(str(error) for error in list(errores or []))
            return self._guardar_consulta_incierta(
                intento.id,
                mensaje or "ARCA no confirmó el comprobante planificado.",
                consulta,
            )

        comparacion = comparar_snapshot_con_comprobante(self._snapshot_desde_intento(intento), consulta)
        es_conflicto = comparacion.resultado == ResultadoReconciliacion.CONFLICTO
        mensaje = "; ".join(comparacion.diferencias_texto)
        if comparacion.campos_faltantes:
            mensaje = "; ".join(f"Falta {campo}" for campo in comparacion.campos_faltantes)

        self._intentos_service.guardar_resultado_reconciliacion(
            intento.id,
            comparacion.resultado,
            cae=str(consulta.get("cae") or ""),
            vencimiento_cae=str(consulta.get("vencimiento_cae") or ""),
            error_codigo="CONFLICTO_FISCAL" if es_conflicto else None,
            error_mensaje=mensaje or None,
            detalle_tecnico=self._detalle_consulta(consulta, comparacion),
        )
        return ResultadoEjecucionReconciliacion(
            ok=comparacion.resultado == ResultadoReconciliacion.AUTORIZADO,
            intento_id=intento.id,
            resultado=comparacion.resultado,
            mensaje=mensaje,
            comparacion=comparacion,
            consulta=consulta,
        )