from dataclasses import dataclass, field

from services.arca.reconciliacion_contracts import (
    EstadoIntentoEmision,
    ResultadoReconciliacion,
)
from services.arca.reconciliacion_service import ReconciliacionArcaService
from services.intento_emision_arca_service import IntentoEmisionArcaService


@dataclass(frozen=True)
class ResultadoLoteReconciliacion:
    total: int = 0
    reconciliados: int = 0
    conflictos: int = 0
    inciertos: int = 0
    errores: int = 0
    detalle: tuple = field(default_factory=tuple)


class ReconciliacionPendientesService:

    def __init__(self, intentos_service=None, reconciliacion_service=None):
        self._intentos_service = intentos_service or IntentoEmisionArcaService()
        self._reconciliacion_service = reconciliacion_service or ReconciliacionArcaService(
            intentos_service=self._intentos_service,
        )

    def listar_pendientes(self):
        return self._intentos_service.listar_pendientes_reconciliacion()

    def reconciliar_uno(self, intento_id):
        return self._reconciliacion_service.reconciliar_intento(intento_id)

    def reconciliar_todos(self):
        pendientes = self.listar_pendientes()
        detalle = []
        reconciliados = conflictos = inciertos = errores = 0

        for intento in pendientes:
            try:
                resultado = self.reconciliar_uno(intento.id)
                resultado_valor = getattr(resultado.resultado, "value", str(resultado.resultado))
                if resultado_valor == ResultadoReconciliacion.AUTORIZADO.value and resultado.recuperado:
                    reconciliados += 1
                elif resultado_valor == ResultadoReconciliacion.CONFLICTO.value:
                    conflictos += 1
                else:
                    inciertos += 1
                detalle.append(resultado)
            except Exception as error:
                errores += 1
                detalle.append({
                    "intento_id": intento.id,
                    "estado_intento": EstadoIntentoEmision.PENDIENTE_RECONCILIAR.value,
                    "errores": (str(error),),
                })

        return ResultadoLoteReconciliacion(
            total=len(pendientes),
            reconciliados=reconciliados,
            conflictos=conflictos,
            inciertos=inciertos,
            errores=errores,
            detalle=tuple(detalle),
        )