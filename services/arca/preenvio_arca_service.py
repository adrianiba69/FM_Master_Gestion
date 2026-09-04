from dataclasses import dataclass

from services.arca.contexto_fiscal_service import ContextoFiscalService
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

        return self._marcar_enviando_y_ejecutar(intento_id, enviar_fecae)

    def enviar_una_vez_con_contexto(self, snapshot, contexto_fiscal, enviar_fecae):
        """Igual que enviar_una_vez, pero exige contexto fiscal completo persistido
        (validado, serializado y hasheado) antes de marcar ENVIANDO o invocar el callback."""
        if not isinstance(snapshot, SnapshotFiscalEsperado):
            raise TypeError("snapshot debe ser SnapshotFiscalEsperado.")
        if not isinstance(contexto_fiscal, dict):
            raise TypeError("contexto_fiscal debe ser un dict validable por ContextoFiscalService.")
        if not callable(enviar_fecae):
            raise TypeError("enviar_fecae debe ser invocable.")

        # 1-2. validar contexto y obtener JSON canonico/version/hash.
        integridad = ContextoFiscalService.validar(contexto_fiscal)
        if not integridad.valido:
            return ResultadoPreenvioArca(
                False,
                errores=(f"Contexto fiscal inválido: {'; '.join(integridad.errores)}",),
            )

        # 3-4. crear intento con contexto fiscal en el mismo INSERT/transaccion.
        try:
            intento_id = self._intentos_service.crear_intento(
                snapshot,
                EstadoIntentoEmision.PENDIENTE_RECONCILIAR,
                contexto_fiscal_json=integridad.json_canonico,
                contexto_fiscal_version=integridad.version,
                contexto_fiscal_hash=integridad.hash_calculado,
            )
        except Exception as error:
            return ResultadoPreenvioArca(False, errores=(f"No se pudo persistir el intento ARCA: {error}",))

        # 5-6. releer y verificar hash/integridad de lo realmente persistido.
        error_verificacion = self._verificar_contexto_persistido(intento_id, integridad.hash_calculado)
        if error_verificacion:
            return ResultadoPreenvioArca(False, intento_id=intento_id, errores=(error_verificacion,))

        # 7-8. recien aqui se marca ENVIANDO y se ejecuta el callback FECAESolicitar.
        return self._marcar_enviando_y_ejecutar(intento_id, enviar_fecae)

    def _verificar_contexto_persistido(self, intento_id, hash_esperado):
        try:
            intento = self._intentos_service.obtener(intento_id)
        except Exception as error:
            return f"No se pudo releer el contexto fiscal persistido: {error}"
        if intento is None:
            return "El intento ARCA no existe al verificar el contexto fiscal persistido."

        integridad = ContextoFiscalService.validar_integridad(
            intento.contexto_fiscal_json,
            intento.contexto_fiscal_version,
            intento.contexto_fiscal_hash,
        )
        if not integridad.valido:
            return f"Contexto fiscal persistido inválido ({integridad.codigo}): {'; '.join(integridad.errores)}"
        if integridad.hash_calculado != hash_esperado:
            return "El hash del contexto fiscal persistido no coincide con el esperado."
        return None

    def _marcar_enviando_y_ejecutar(self, intento_id, enviar_fecae):
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