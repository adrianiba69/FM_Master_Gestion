import json
from dataclasses import dataclass

from models.intento_emision_arca import IntentoEmisionArca
from services.arca.homologacion_service import HomologacionService
from services.arca.reconciliacion_contracts import (
    ResultadoComparacionFiscal,
    ResultadoReconciliacion,
    SnapshotFiscalEsperado,
    comparar_contexto_con_autorizacion,
)
from services.arca.contexto_fiscal_service import ContextoFiscalService
from services.arca.recuperacion_local_service import RecuperacionLocalArcaService
from services.arca.snapshot_fiscal_service import autorizacion_arca_desde_fe_comp_consultar
from services.arca import ambiente_arca
from services.emisor_fiscal_service import EmisorFiscalService
from services.intento_emision_arca_service import IntentoEmisionArcaService
from services.arca.reconciliacion_contracts import EstadoIntentoEmision


@dataclass(frozen=True)
class ResultadoEjecucionReconciliacion:
    ok: bool
    intento_id: int
    resultado: ResultadoReconciliacion
    mensaje: str = ""
    comparacion: ResultadoComparacionFiscal = None
    consulta: dict = None
    estado_intento: str = ""
    factura_arca_id: int = None
    cae: str = ""
    vencimiento_cae: str = ""
    recuperado: bool = False
    diferencias: tuple = ()
    campos_faltantes: tuple = ()
    errores: tuple = ()
    detalle: str = ""

    @property
    def resultado_reconciliacion(self):
        return self.resultado


class ReconciliacionArcaService:
    """Orquesta únicamente la consulta y comparación de un intento ya persistido."""

    def __init__(
        self,
        intentos_service=None,
        emisor_fiscal_provider=None,
        consultar_comprobante=None,
        recuperacion_service=None,
    ):
        self._intentos_service = intentos_service or IntentoEmisionArcaService()
        self._emisor_fiscal_provider = emisor_fiscal_provider or EmisorFiscalService
        self._consultar_comprobante = consultar_comprobante or HomologacionService.consultar_comprobante_emitido
        self._recuperacion_service = recuperacion_service or RecuperacionLocalArcaService()

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

    def _guardar_consulta_incierta(
        self,
        intento_id,
        mensaje,
        consulta=None,
        error_codigo="CONSULTA_ARCA_INCIERTA",
    ):
        self._intentos_service.guardar_resultado_reconciliacion(
            intento_id,
            ResultadoReconciliacion.CONSULTA_INCIERTA,
            error_codigo=error_codigo,
            error_mensaje=mensaje,
            detalle_tecnico=self._detalle_consulta(consulta),
        )
        return ResultadoEjecucionReconciliacion(
            ok=False,
            intento_id=intento_id,
            resultado=ResultadoReconciliacion.CONSULTA_INCIERTA,
            mensaje=mensaje,
            consulta=consulta if isinstance(consulta, dict) else None,
            estado_intento=EstadoIntentoEmision.PENDIENTE_RECONCILIAR.value,
            errores=(mensaje,),
            detalle=self._detalle_consulta(consulta),
        )

    @staticmethod
    def _coherencia_intento(intento, contexto):
        """(resultado, codigo, mensaje) si columna/contexto/identidad no son demostrablemente coherentes; si no, None."""
        _, codigo, errores = IntentoEmisionArcaService.evaluar_coherencia_contexto(
            contexto, intento.cuit_emisor, intento.punto_venta, intento.tipo_comprobante,
            intento.numero_planificado, intento.ambiente_arca,
        )
        if codigo is None and intento.ambiente_arca is None:
            codigo, errores = "AMBIENTE_INTENTO_AUSENTE", ("el intento no tiene ambiente_arca; no se atribuye uno",)
        if codigo is None:
            return None
        resultado = (
            ResultadoReconciliacion.CONFLICTO if codigo.startswith("CONFLICTO_")
            else ResultadoReconciliacion.CONSULTA_INCIERTA
        )
        return resultado, codigo, "; ".join(errores)

    def _validar_reconciliado_local(self, intento):
        """Valida sin red ni escrituras que el vinculo RECONCILIADO siga siendo coherente."""
        estado = EstadoIntentoEmision.RECONCILIADO.value

        def falla(resultado, mensaje):
            return ResultadoEjecucionReconciliacion(
                ok=False,
                intento_id=intento.id,
                resultado=resultado,
                estado_intento=estado,
                factura_arca_id=intento.factura_arca_id,
                errores=(mensaje,),
                detalle="RECONCILIADO sin validación local satisfactoria; no se consultó ARCA ni se modificó el intento.",
            )

        incierta, conflicto = ResultadoReconciliacion.CONSULTA_INCIERTA, ResultadoReconciliacion.CONFLICTO
        if not intento.factura_arca_id:
            return falla(incierta, "Intento RECONCILIADO sin factura_arca_id.")
        campos = (intento.contexto_fiscal_json, intento.contexto_fiscal_version, intento.contexto_fiscal_hash)
        if any(valor is None for valor in campos):
            return falla(incierta, "Intento RECONCILIADO sin contexto fiscal íntegro; requiere revisión manual.")
        integridad = ContextoFiscalService.validar_integridad(*campos)
        if not integridad.valido:
            return falla(incierta, "Contexto fiscal inválido en intento RECONCILIADO: " + "; ".join(integridad.errores))
        contexto = integridad.contexto
        incoherencia = self._coherencia_intento(intento, contexto)
        if incoherencia:
            return falla(incoherencia[0], f"Intento RECONCILIADO incoherente ({incoherencia[1]}): {incoherencia[2]}")

        factura = self._intentos_service.obtener_factura_para_validacion(intento.factura_arca_id)
        if factura is None:
            return falla(conflicto, f"La factura vinculada {intento.factura_arca_id} no existe.")
        if not factura.get("_esquema_con_ambiente"):
            return falla(incierta, "factura_arca sin columna ambiente_arca; no se puede demostrar el ambiente.")
        ambiente_factura = factura.get("ambiente_arca")
        if ambiente_factura is None:
            return falla(incierta, "La factura vinculada tiene ambiente desconocido; requiere revisión manual.")
        if ambiente_factura != intento.ambiente_arca:
            return falla(
                conflicto,
                f"La factura vinculada es de {ambiente_factura!r} y el intento de {intento.ambiente_arca!r}.",
            )
        if int(factura.get("resumen_id") or 0) != int(intento.resumen_id):
            return falla(conflicto, "La factura vinculada pertenece a otro resumen.")
        if int(factura.get("emisor_id") or 0) != int(intento.emisor_id):
            return falla(conflicto, "La factura vinculada pertenece a otro emisor.")

        comprobante = contexto["comprobante"]
        esperado = (
            int(comprobante["punto_venta_num"]), int(comprobante["tipo_comprobante_num"]),
            int(comprobante["numero_comprobante_planificado"]),
        )
        actual = (
            factura.get("punto_venta_num"), factura.get("tipo_comprobante_num"), factura.get("numero_comprobante_num"),
        )
        texto_factura = str(factura.get("numero_factura") or "").strip()
        if all(valor is not None for valor in actual):
            if tuple(int(valor) for valor in actual) != esperado:
                return falla(conflicto, "La identidad fiscal de la factura contradice el intento.")
        elif texto_factura:
            if texto_factura != str(comprobante.get("numero_textual_planificado") or "").strip():
                return falla(conflicto, "El número de la factura contradice el intento.")
        else:
            return falla(incierta, "La factura vinculada no tiene identidad fiscal verificable.")

        cae_factura = str(factura.get("cae") or "").strip()
        cae_intento = str(intento.cae or "").strip()
        if cae_factura and cae_intento and cae_factura != cae_intento:
            return falla(conflicto, "El CAE de la factura contradice el del intento.")

        return ResultadoEjecucionReconciliacion(
            ok=True,
            intento_id=intento.id,
            resultado=ResultadoReconciliacion.AUTORIZADO,
            estado_intento=estado,
            factura_arca_id=intento.factura_arca_id,
            cae=cae_intento or cae_factura,
            vencimiento_cae=str(intento.vencimiento_cae or ""),
            recuperado=True,
            detalle="Intento ya reconciliado; vínculo validado localmente, no se consultó ARCA.",
        )

    def _resultado_terminal(self, intento):
        estado = str(intento.estado or "").strip()
        if estado == EstadoIntentoEmision.RECONCILIADO.value:
            return self._validar_reconciliado_local(intento)

        if estado in {
            EstadoIntentoEmision.CONFLICTO_MANUAL.value,
            EstadoIntentoEmision.NO_AUTORIZADO.value,
            EstadoIntentoEmision.RECHAZADO.value,
        }:
            resultado = (
                ResultadoReconciliacion.CONFLICTO
                if estado == EstadoIntentoEmision.CONFLICTO_MANUAL.value
                else (
                    ResultadoReconciliacion.NO_AUTORIZADO
                    if estado == EstadoIntentoEmision.NO_AUTORIZADO.value
                    else ResultadoReconciliacion.CONSULTA_INCIERTA
                )
            )
            return ResultadoEjecucionReconciliacion(
                ok=False,
                intento_id=intento.id,
                resultado=resultado,
                estado_intento=estado,
                errores=(str(intento.error_mensaje or "Estado terminal; no se consultó ARCA."),),
                detalle="Intento terminal; no se consultó ARCA.",
            )
        return None

    def reconciliar_intento(self, intento_id):
        intento = self._intentos_service.obtener(intento_id)
        if not intento:
            raise LookupError(f"Intento de emisión ARCA inexistente: {intento_id}")

        terminal = self._resultado_terminal(intento)
        if terminal is not None:
            return terminal

        contexto_campos = (
            intento.contexto_fiscal_json,
            intento.contexto_fiscal_version,
            intento.contexto_fiscal_hash,
        )
        if all(valor is None for valor in contexto_campos):
            return self._guardar_consulta_incierta(
                intento.id,
                "Intento histórico sin contexto fiscal persistido; requiere intervención manual.",
                error_codigo="CONTEXTO_FISCAL_HISTORICO_AUSENTE",
            )
        if any(valor is None for valor in contexto_campos):
            return self._guardar_consulta_incierta(
                intento.id,
                "Contexto fiscal persistido incompleto; requiere intervención manual.",
                error_codigo="CONTEXTO_FISCAL_CORRUPTO",
            )
        integridad_contexto = ContextoFiscalService.validar_integridad(*contexto_campos)
        if not integridad_contexto.valido:
            return self._guardar_consulta_incierta(
                intento.id,
                "Contexto fiscal persistido inválido: " + "; ".join(integridad_contexto.errores),
                error_codigo=f"CONTEXTO_FISCAL_{integridad_contexto.codigo}",
            )
        contexto = integridad_contexto.contexto
        try:
            ambiente_contexto = ambiente_arca.normalizar_ambiente_arca(contexto.get("ambiente"))
            emisor_contexto = contexto["emisor"]
            comprobante_contexto = contexto["comprobante"]
            emisor_fiscal_id = int(emisor_contexto["emisor_fiscal_id"])
            cuit_consulta = str(emisor_contexto["cuit"] or "").strip()
            punto_venta_consulta = int(comprobante_contexto["punto_venta_num"])
            tipo_comprobante_consulta = int(comprobante_contexto["tipo_comprobante_num"])
            numero_comprobante_consulta = int(comprobante_contexto["numero_comprobante_planificado"])
            if not cuit_consulta or punto_venta_consulta <= 0 or tipo_comprobante_consulta <= 0 or numero_comprobante_consulta <= 0:
                raise ValueError("clave fiscal incompleta")
        except (ambiente_arca.AmbienteArcaInvalidoError, KeyError, TypeError, ValueError) as error:
            return self._guardar_consulta_incierta(
                intento.id,
                f"Contexto fiscal incompatible con reconciliación: {error}",
                error_codigo="CONTEXTO_FISCAL_INCOMPATIBLE",
            )

        incoherencia = self._coherencia_intento(intento, contexto)
        if incoherencia:
            resultado_incoherencia, codigo_incoherencia, mensaje_incoherencia = incoherencia
            mensaje_incoherencia = f"Intento sin coherencia ambiente/contexto/identidad: {mensaje_incoherencia}"
            if resultado_incoherencia == ResultadoReconciliacion.CONFLICTO:
                self._intentos_service.guardar_resultado_reconciliacion(
                    intento.id,
                    ResultadoReconciliacion.CONFLICTO,
                    error_codigo=codigo_incoherencia,
                    error_mensaje=mensaje_incoherencia,
                    detalle_tecnico=self._detalle_consulta(None),
                )
                return ResultadoEjecucionReconciliacion(
                    ok=False,
                    intento_id=intento.id,
                    resultado=ResultadoReconciliacion.CONFLICTO,
                    mensaje=mensaje_incoherencia,
                    estado_intento=EstadoIntentoEmision.CONFLICTO_MANUAL.value,
                    errores=(mensaje_incoherencia,),
                )
            return self._guardar_consulta_incierta(intento.id, mensaje_incoherencia, error_codigo=codigo_incoherencia)

        emisor_fiscal = self._emisor_fiscal_provider.obtener(emisor_fiscal_id)
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
                cuit_emisor=cuit_consulta,
                punto_venta=punto_venta_consulta,
                tipo_comprobante=tipo_comprobante_consulta,
                numero_comprobante=numero_comprobante_consulta,
                carpeta_trabajo=carpeta_trabajo,
                ambiente=ambiente_contexto,
            )
        except Exception as error:
            return self._guardar_consulta_incierta(
                intento.id,
                f"Error al consultar ARCA: {error}",
            )

        if not isinstance(consulta, dict):
            return self._guardar_consulta_incierta(
                intento.id,
                "FECompConsultar no devolvió una respuesta interpretable.",
            )

        autorizacion = autorizacion_arca_desde_fe_comp_consultar(consulta)
        comparacion = comparar_contexto_con_autorizacion(contexto, autorizacion)

        if not consulta.get("ok") and comparacion.resultado != ResultadoReconciliacion.NO_AUTORIZADO:
            errores = consulta.get("errores") if isinstance(consulta, dict) else None
            mensaje = "; ".join(str(error) for error in list(errores or []))
            return self._guardar_consulta_incierta(
                intento.id,
                mensaje or "ARCA no confirmó el comprobante planificado.",
                consulta,
            )

        es_conflicto = comparacion.resultado == ResultadoReconciliacion.CONFLICTO
        mensaje = comparacion.mensaje or "; ".join(comparacion.diferencias_texto)
        if comparacion.campos_faltantes:
            mensaje = "; ".join(f"Falta {campo}" for campo in comparacion.campos_faltantes)

        if comparacion.resultado == ResultadoReconciliacion.AUTORIZADO:
            try:
                recuperacion = self._recuperacion_service.registrar_factura_recuperada(
                    intento,
                    self._snapshot_desde_intento(intento),
                    consulta,
                )
            except Exception as error:
                mensaje_error = f"Falló la recuperación local: {error}"
                self._intentos_service.guardar_resultado_reconciliacion(
                    intento.id,
                    ResultadoReconciliacion.CONSULTA_INCIERTA,
                    error_codigo="RECUPERACION_LOCAL_INCIERTA",
                    error_mensaje=mensaje_error,
                    detalle_tecnico=self._detalle_consulta(consulta, comparacion),
                )
                return ResultadoEjecucionReconciliacion(
                    ok=False,
                    intento_id=intento.id,
                    resultado=ResultadoReconciliacion.CONSULTA_INCIERTA,
                    estado_intento=EstadoIntentoEmision.PENDIENTE_RECONCILIAR.value,
                    consulta=consulta,
                    comparacion=comparacion,
                    cae=str(consulta.get("cae") or ""),
                    vencimiento_cae=str(consulta.get("vencimiento_cae") or ""),
                    recuperado=False,
                    errores=(mensaje_error,),
                    detalle=self._detalle_consulta(consulta, comparacion),
                )

            if recuperacion.resultado != ResultadoReconciliacion.AUTORIZADO:
                mensaje_recuperacion = recuperacion.mensaje or "La recuperación local no se completó."
                estado = (
                    EstadoIntentoEmision.CONFLICTO_MANUAL.value
                    if recuperacion.resultado == ResultadoReconciliacion.CONFLICTO
                    else EstadoIntentoEmision.PENDIENTE_RECONCILIAR.value
                )
                if estado == EstadoIntentoEmision.CONFLICTO_MANUAL.value:
                    self._intentos_service.guardar_resultado_reconciliacion(
                        intento.id,
                        ResultadoReconciliacion.CONFLICTO,
                        error_codigo="CONFLICTO_RECUPERACION_LOCAL",
                        error_mensaje=mensaje_recuperacion,
                        detalle_tecnico=self._detalle_consulta(consulta, comparacion),
                    )
                else:
                    self._intentos_service.guardar_resultado_reconciliacion(
                        intento.id,
                        ResultadoReconciliacion.CONSULTA_INCIERTA,
                        error_codigo="RECUPERACION_LOCAL_INCIERTA",
                        error_mensaje=mensaje_recuperacion,
                        detalle_tecnico=self._detalle_consulta(consulta, comparacion),
                    )
                return ResultadoEjecucionReconciliacion(
                    ok=False,
                    intento_id=intento.id,
                    resultado=recuperacion.resultado,
                    estado_intento=estado,
                    factura_arca_id=recuperacion.factura_arca_id,
                    cae=str(consulta.get("cae") or ""),
                    vencimiento_cae=str(consulta.get("vencimiento_cae") or ""),
                    recuperado=False,
                    errores=(mensaje_recuperacion,),
                    detalle=self._detalle_consulta(consulta, comparacion),
                )

            return ResultadoEjecucionReconciliacion(
                ok=True,
                intento_id=intento.id,
                resultado=ResultadoReconciliacion.AUTORIZADO,
                estado_intento=EstadoIntentoEmision.RECONCILIADO.value,
                factura_arca_id=recuperacion.factura_arca_id,
                cae=str(consulta.get("cae") or ""),
                vencimiento_cae=str(consulta.get("vencimiento_cae") or ""),
                recuperado=True,
                diferencias=tuple(comparacion.diferencias_texto),
                campos_faltantes=tuple(comparacion.campos_faltantes),
                detalle="Comprobante autorizado y recuperación local completada.",
                comparacion=comparacion,
                consulta=consulta,
            )

        self._intentos_service.guardar_resultado_reconciliacion(
            intento.id,
            comparacion.resultado,
            cae=str(consulta.get("cae") or ""),
            vencimiento_cae=str(consulta.get("vencimiento_cae") or ""),
            error_codigo=(
                "CONFLICTO_FISCAL"
                if es_conflicto
                else (
                    "COMPROBANTE_NO_AUTORIZADO"
                    if comparacion.resultado == ResultadoReconciliacion.NO_AUTORIZADO
                    else comparacion.codigo or "CONSULTA_INCIERTA"
                )
            ),
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
            estado_intento=(
                EstadoIntentoEmision.CONFLICTO_MANUAL.value
                if es_conflicto
                else (
                    EstadoIntentoEmision.NO_AUTORIZADO.value
                    if comparacion.resultado == ResultadoReconciliacion.NO_AUTORIZADO
                    else EstadoIntentoEmision.PENDIENTE_RECONCILIAR.value
                )
            ),
            diferencias=tuple(comparacion.diferencias_texto),
            campos_faltantes=tuple(comparacion.campos_faltantes),
            errores=(mensaje,) if mensaje else (),
            detalle=self._detalle_consulta(consulta, comparacion),
        )