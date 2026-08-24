"""Persistencia inmutable del snapshot fiscal v1."""

from dataclasses import dataclass
from typing import Optional

from database import conectar
from services.arca.snapshot_fiscal_service import (
    CODIGO_VALIDO,
    SNAPSHOT_VERSION,
    validar_integridad_snapshot,
)


CODIGO_SNAPSHOT_GUARDADO = "SNAPSHOT_GUARDADO"
CODIGO_SNAPSHOT_IDEMPOTENTE = "SNAPSHOT_IDEMPOTENTE"
CODIGO_FACTURA_INEXISTENTE = "FACTURA_INEXISTENTE"
CODIGO_SNAPSHOT_INVALIDO = "SNAPSHOT_INVALIDO"
CODIGO_SNAPSHOT_DIFERENTE = "SNAPSHOT_DIFERENTE"
CODIGO_SNAPSHOT_CORRUPTO = "SNAPSHOT_CORRUPTO"


@dataclass(frozen=True)
class ResultadoPersistenciaSnapshot:
    ok: bool
    codigo: str
    mensaje: str = ""
    actualizado: bool = False
    idempotente: bool = False


class SnapshotFiscalPersistenciaError(RuntimeError):
    pass


class SnapshotFiscalPersistenceService:
    def __init__(self, conexion_factory=conectar):
        self._conexion_factory = conexion_factory

    def guardar_snapshot_si_ausente(
        self,
        factura_arca_id,
        snapshot_fiscal_json,
        snapshot_version,
        snapshot_hash,
        conn=None,
    ):
        validacion = validar_integridad_snapshot(snapshot_fiscal_json, snapshot_version, snapshot_hash)
        if validacion.codigo != CODIGO_VALIDO:
            return ResultadoPersistenciaSnapshot(False, CODIGO_SNAPSHOT_INVALIDO, "; ".join(validacion.errores))

        conexion_externa = conn is not None
        conexion = conn if conexion_externa else self._conexion_factory()
        try:
            if not conexion_externa:
                conexion.execute("BEGIN IMMEDIATE")

            resultado = self._guardar_en_conexion(
                conexion,
                int(factura_arca_id),
                snapshot_fiscal_json,
                int(snapshot_version),
                str(snapshot_hash),
            )

            if not conexion_externa:
                conexion.commit()
            return resultado
        except Exception:
            if not conexion_externa:
                conexion.rollback()
            raise
        finally:
            if not conexion_externa:
                conexion.close()

    def _guardar_en_conexion(self, conexion, factura_arca_id, snapshot_fiscal_json, snapshot_version, snapshot_hash):
        fila = conexion.execute(
            "SELECT snapshot_fiscal_json, snapshot_version, snapshot_hash FROM factura_arca WHERE id=?",
            (factura_arca_id,),
        ).fetchone()
        if fila is None:
            return ResultadoPersistenciaSnapshot(False, CODIGO_FACTURA_INEXISTENTE, "factura_arca inexistente")

        actual_json, actual_version, actual_hash = fila
        if actual_json is None and actual_version is None and actual_hash is None:
            conexion.execute(
                "UPDATE factura_arca SET snapshot_fiscal_json=?, snapshot_version=?, snapshot_hash=? WHERE id=?",
                (snapshot_fiscal_json, snapshot_version, snapshot_hash, factura_arca_id),
            )
            return ResultadoPersistenciaSnapshot(True, CODIGO_SNAPSHOT_GUARDADO, actualizado=True)

        if actual_json is None or actual_version is None or actual_hash is None:
            return ResultadoPersistenciaSnapshot(False, CODIGO_SNAPSHOT_CORRUPTO, "snapshot almacenado incompleto")

        actual_integridad = validar_integridad_snapshot(actual_json, actual_version, actual_hash)
        if actual_integridad.codigo != CODIGO_VALIDO:
            return ResultadoPersistenciaSnapshot(False, CODIGO_SNAPSHOT_CORRUPTO, "; ".join(actual_integridad.errores))

        if int(actual_version) == SNAPSHOT_VERSION and str(actual_hash) == snapshot_hash:
            return ResultadoPersistenciaSnapshot(True, CODIGO_SNAPSHOT_IDEMPOTENTE, idempotente=True)

        return ResultadoPersistenciaSnapshot(False, CODIGO_SNAPSHOT_DIFERENTE, "snapshot existente diferente")


def guardar_snapshot_si_ausente(
    factura_arca_id,
    snapshot_fiscal_json,
    snapshot_version,
    snapshot_hash,
    conn=None,
    conexion_factory=conectar,
):
    return SnapshotFiscalPersistenceService(conexion_factory).guardar_snapshot_si_ausente(
        factura_arca_id,
        snapshot_fiscal_json,
        snapshot_version,
        snapshot_hash,
        conn=conn,
    )