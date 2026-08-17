from dataclasses import dataclass

from services.arca.reconciliacion_contracts import (
    EstadoIntentoEmision,
    SnapshotFiscalEsperado,
)
from services.intento_emision_arca_service import IntentoEmisionArcaService


@dataclass(frozen=True)
class ResultadoPreenvioArca:
    ok: bool
    intento_id: int = None
    respuesta: dict = None
    errores: tuple = ()


class PreenvioArcaService:
    """Garantiza persistencia local antes de un único envío FECAESolicitar."""

    def __init__(self, intentos_service=None):
        self._intentos_service = intentos_service or IntentoEmisionArcaService()

    @staticmethod
    def _errores_respuesta(respuesta, predeterminado):
        if not isinstance(respuesta, dict):
            return (predeterminado,)
        errores = tuple(str(error) for error in list(respuesta.get("errores") or []) if str(error).strip())
        return errores or (predeterminado,)

    def enviar_una_vez(self, snapshot, enviar_fecae):
        if not isinstance(snapshot, SnapshotFiscalEsperado):
            raise TypeError("snapshot debe ser SnapshotFiscalEsperado.")
        if not callable(enviar_fecae):
            raise TypeError("enviar_fecae debe ser invocable.")

        try:
            intento_id = self._intentos_service.crear_intento(
                snapshot,
                EstadoIntentoEmision.PENDIENTE_RECONCILIAR,
            )
        except Exception as error:
            return ResultadoPreenvioArca(False, errores=(f"No se pudo persistir el intento ARCA: {error}",))

        try:
            self._intentos_service.actualizar_estado(intento_id, EstadoIntentoEmision.ENVIANDO)
        except Exception as error:
            return ResultadoPreenvioArca(
                False,
                intento_id=intento_id,
                errores=(f"No se pudo marcar el intento ARCA como enviando: {error}",),
            )

        try:
            respuesta = enviar_fecae()
        except Exception as error:
            self._intentos_service.actualizar_estado(
                intento_id,
                EstadoIntentoEmision.PENDIENTE_RECONCILIAR,
                error_codigo="ENVIO_ARCA_INCIERTO",
                error_mensaje=f"Excepción durante FECAESolicitar: {error}",
            )
            return ResultadoPreenvioArca(False, intento_id=intento_id, errores=(str(error),))

        resultado_arca = str(respuesta.get("resultado") or "") if isinstance(respuesta, dict) else ""
        if isinstance(respuesta, dict) and respuesta.get("ok"):
            self._intentos_service.actualizar_estado(intento_id, EstadoIntentoEmision.PENDIENTE_RECONCILIAR)
            return ResultadoPreenvioArca(True, intento_id=intento_id, respuesta=respuesta)

        if resultado_arca == "R":
            errores = self._errores_respuesta(respuesta, "ARCA rechazó explícitamente FECAESolicitar.")
            self._intentos_service.actualizar_estado(
                intento_id,
                EstadoIntentoEmision.RECHAZADO,
                error_codigo="ARCA_RECHAZO",
                error_mensaje="; ".join(errores),
            )
            return ResultadoPreenvioArca(False, intento_id=intento_id, respuesta=respuesta, errores=errores)

        errores = self._errores_respuesta(respuesta, "Resultado incierto de FECAESolicitar.")
        self._intentos_service.actualizar_estado(
            intento_id,
            EstadoIntentoEmision.PENDIENTE_RECONCILIAR,
            error_codigo="ENVIO_ARCA_INCIERTO",
            error_mensaje="; ".join(errores),
        )
        return ResultadoPreenvioArca(False, intento_id=intento_id, respuesta=respuesta, errores=errores)