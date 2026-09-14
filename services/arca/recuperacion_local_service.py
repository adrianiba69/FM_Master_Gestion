from dataclasses import dataclass
from datetime import datetime

from database import conectar
from models.intento_emision_arca import IntentoEmisionArca
from services.arca.contexto_fiscal_service import ContextoFiscalService
from services.arca.reconciliacion_contracts import (
    ResultadoReconciliacion,
    SnapshotFiscalEsperado,
    comparar_contexto_con_autorizacion,
    normalizar_importe,
)
from services.arca.fiscal_normalization import normalizar_identidad_factura
from services.arca.snapshot_fiscal_persistence_service import SnapshotFiscalPersistenceService
from services.arca.snapshot_fiscal_service import (
    SnapshotFiscalError,
    autorizacion_arca_desde_fe_comp_consultar,
    construir_snapshot_final_desde_contexto_persistido,
)
from services.intento_emision_arca_service import IntentoEmisionArcaService


@dataclass(frozen=True)
class ResultadoRecuperacionLocal:
    resultado: ResultadoReconciliacion
    factura_arca_id: int = None
    insertada: bool = False
    mensaje: str = ""


class RecuperacionLocalArcaService:
    """Reconstruye localmente una autorización ARCA ya consultada y validada."""

    def __init__(self, conexion_factory=conectar, intentos_service=None):
        self._conexion_factory = conexion_factory
        self._intentos_service = intentos_service or IntentoEmisionArcaService(conexion_factory)

    @staticmethod
    def _ahora():
        return datetime.now().isoformat(timespec="seconds")

    @staticmethod
    def _tipo_factura(tipo_comprobante):
        tipos = {1: "Factura A", 11: "Factura C"}
        return tipos.get(int(tipo_comprobante), str(tipo_comprobante))

    @staticmethod
    def _numero_factura(punto_venta, numero):
        return f"{int(punto_venta):05d}-{int(numero):08d}"

    @staticmethod
    def _identidad_receptor_desde_consulta(consulta):
        """Usa DocTipo/DocNro de la respuesta ARCA (FECompConsultar) si estan disponibles.
        Nunca los infiere del cliente ni de otra fuente: ante ausencia o dato invalido, NULL."""
        if not isinstance(consulta, dict) or "doc_tipo" not in consulta or "doc_nro" not in consulta:
            return None, None
        try:
            return int(consulta["doc_tipo"]), int(consulta["doc_nro"])
        except (TypeError, ValueError):
            return None, None

    @staticmethod
    def _snapshot_desde_intento(intento):
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

    @classmethod
    def _fila_compatible(cls, fila, intento, snapshot_final, consulta):
        if not fila:
            return False
        emisor = snapshot_final["emisor"]
        receptor = snapshot_final["receptor"]
        comprobante = snapshot_final["comprobante"]
        importes = snapshot_final["importes"]
        numero = comprobante["numero_textual"]
        if (
            int(fila[1]) != int(receptor["cliente_id"])
            or int(fila[2]) != int(emisor["emisor_id"])
            or int(fila[3]) != int(intento.resumen_id)
        ):
            return False

        esperados = (
            (fila[5], str(comprobante["punto_venta_num"])),
            (fila[6], cls._tipo_factura(comprobante["tipo_comprobante_num"])),
            (fila[7], normalizar_importe(importes["total"])),
            (fila[9], numero),
            (fila[10], str(consulta.get("cae") or "").strip()),
            (fila[11], str(consulta.get("vencimiento_cae") or "").strip()),
        )
        for actual, esperado in esperados:
            if actual in (None, ""):
                continue
            valor_actual = normalizar_importe(actual) if isinstance(esperado, type(normalizar_importe(0))) else str(actual).strip()
            if valor_actual != esperado:
                return False
        return True

    @staticmethod
    def _resumen_compatible(fila, numero_factura, cae):
        estado = str(fila[0] or "").strip().lower()
        if estado != "facturado":
            return True
        return str(fila[3] or "").strip() == numero_factura and str(fila[1] or "").strip() == cae

    @staticmethod
    def _buscar_facturas(cursor, intento, snapshot_final, consulta):
        seleccion = "id, cliente_id, emisor_id, resumen_id, fecha, punto_venta, tipo_comprobante, importe_total, estado, numero_factura, cae, vencimiento_cae"
        candidatas = []

        if intento.factura_arca_id:
            cursor.execute(f"SELECT {seleccion} FROM factura_arca WHERE id=?", (intento.factura_arca_id,))
            fila = cursor.fetchone()
            if fila:
                candidatas.append(fila)

        cursor.execute(f"SELECT {seleccion} FROM factura_arca WHERE resumen_id=? ORDER BY id", (intento.resumen_id,))
        candidatas.extend(cursor.fetchall())

        emisor = snapshot_final["emisor"]
        comprobante = snapshot_final["comprobante"]
        numero = comprobante["numero_textual"]
        cursor.execute(
            f"SELECT {seleccion} FROM factura_arca WHERE emisor_id=? AND TRIM(COALESCE(punto_venta, ''))=? AND TRIM(COALESCE(tipo_comprobante, ''))=? AND TRIM(COALESCE(numero_factura, ''))=? ORDER BY id",
            (
                emisor["emisor_id"],
                str(comprobante["punto_venta_num"]),
                RecuperacionLocalArcaService._tipo_factura(comprobante["tipo_comprobante_num"]),
                numero,
            ),
        )
        candidatas.extend(cursor.fetchall())

        cursor.execute(f"SELECT {seleccion} FROM factura_arca WHERE cae=? ORDER BY id", (str(consulta.get("cae") or "").strip(),))
        candidatas.extend(cursor.fetchall())

        unicas = {fila[0]: fila for fila in candidatas}
        compatibles = [
            fila
            for fila in unicas.values()
            if RecuperacionLocalArcaService._fila_compatible(fila, intento, snapshot_final, consulta)
        ]
        incompatibles = [fila for fila in unicas.values() if fila not in compatibles]
        return compatibles, incompatibles

    def registrar_factura_recuperada(self, intento, snapshot, consulta):
        if not isinstance(intento, IntentoEmisionArca):
            raise TypeError("intento debe ser IntentoEmisionArca.")
        if not isinstance(snapshot, SnapshotFiscalEsperado):
            raise TypeError("snapshot debe ser SnapshotFiscalEsperado.")

        intento_persistido = self._intentos_service.obtener(intento.id)
        if intento_persistido is None or not intento_persistido.contexto_fiscal_json:
            return ResultadoRecuperacionLocal(
                ResultadoReconciliacion.CONSULTA_INCIERTA,
                mensaje="El intento no tiene contexto fiscal persistido para recuperar el snapshot.",
            )
        integridad_contexto = ContextoFiscalService.validar_integridad(
            intento_persistido.contexto_fiscal_json,
            intento_persistido.contexto_fiscal_version,
            intento_persistido.contexto_fiscal_hash,
        )
        if not integridad_contexto.valido:
            return ResultadoRecuperacionLocal(
                ResultadoReconciliacion.CONSULTA_INCIERTA,
                mensaje="Contexto fiscal persistido inválido: " + "; ".join(integridad_contexto.errores),
            )
        try:
            snapshot_construido = construir_snapshot_final_desde_contexto_persistido(
                intento_persistido.contexto_fiscal_json,
                intento_persistido.contexto_fiscal_version,
                intento_persistido.contexto_fiscal_hash,
                autorizacion_arca_desde_fe_comp_consultar(consulta),
                "recuperacion",
                creado_en=intento_persistido.creado_en,
            )
        except SnapshotFiscalError as error:
            return ResultadoRecuperacionLocal(
                ResultadoReconciliacion.CONSULTA_INCIERTA,
                mensaje=f"No se pudo construir el snapshot fiscal de recuperacion: {error}",
            )
        intento = intento_persistido

        comparacion = comparar_contexto_con_autorizacion(
            integridad_contexto.contexto,
            autorizacion_arca_desde_fe_comp_consultar(consulta),
        )
        if comparacion.resultado != ResultadoReconciliacion.AUTORIZADO:
            return ResultadoRecuperacionLocal(
                comparacion.resultado,
                mensaje="; ".join(comparacion.diferencias_texto or comparacion.campos_faltantes),
            )

        snapshot_final = snapshot_construido.snapshot
        emisor_final = snapshot_final["emisor"]
        receptor_final = snapshot_final["receptor"]
        comprobante_final = snapshot_final["comprobante"]
        importes_final = snapshot_final["importes"]

        conexion = self._conexion_factory()
        try:
            cursor = conexion.cursor()
            cursor.execute("BEGIN IMMEDIATE")

            compatibles, incompatibles = self._buscar_facturas(cursor, intento, snapshot_final, consulta)
            if incompatibles or len(compatibles) > 1:
                conexion.rollback()
                return ResultadoRecuperacionLocal(ResultadoReconciliacion.CONFLICTO, mensaje="Factura local incompatible o duplicada.")

            numero_factura = comprobante_final["numero_textual"]
            cae = str(consulta.get("cae") or "").strip()
            vencimiento = str(consulta.get("vencimiento_cae") or "").strip()
            tipo_documento_receptor, documento_receptor = self._identidad_receptor_desde_consulta(consulta)
            cursor.execute(
                "SELECT estado_facturacion, cae, vencimiento_cae, numero_factura FROM resumenes WHERE id=?",
                (intento.resumen_id,),
            )
            resumen = cursor.fetchone()
            if not resumen:
                raise LookupError(f"Resumen inexistente: {intento.resumen_id}")
            if not self._resumen_compatible(resumen, numero_factura, cae):
                conexion.rollback()
                return ResultadoRecuperacionLocal(ResultadoReconciliacion.CONFLICTO, mensaje="Resumen local facturado con datos incompatibles.")

            insertada = False
            if compatibles:
                factura_id = int(compatibles[0][0])
                resultado_snapshot = SnapshotFiscalPersistenceService().guardar_snapshot_si_ausente(
                    factura_id,
                    snapshot_construido.snapshot_json,
                    snapshot_construido.snapshot_version,
                    snapshot_construido.snapshot_hash,
                    conn=conexion,
                )
                if not resultado_snapshot.ok:
                    conexion.rollback()
                    return ResultadoRecuperacionLocal(
                        ResultadoReconciliacion.CONFLICTO,
                        factura_arca_id=factura_id,
                        mensaje=f"{resultado_snapshot.codigo}: {resultado_snapshot.mensaje}",
                    )
                cursor.execute(
                    """
                    UPDATE factura_arca
                    SET fecha=?, punto_venta=?, tipo_comprobante=?, importe_total=?, estado=?,
                        numero_factura=?, cae=?, vencimiento_cae=?, tipo_documento_receptor=?, documento_receptor=?
                    WHERE id=?
                    """,
                    (
                        comprobante_final["fecha_arca"], str(comprobante_final["punto_venta_num"]),
                        self._tipo_factura(comprobante_final["tipo_comprobante_num"]),
                        float(importes_final["total"]), "Facturada manualmente", numero_factura, cae, vencimiento,
                        tipo_documento_receptor, documento_receptor,
                        factura_id,
                    ),
                )
            else:
                punto_num, tipo_num, numero_num = normalizar_identidad_factura(
                    comprobante_final["punto_venta_num"],
                    self._tipo_factura(comprobante_final["tipo_comprobante_num"]),
                    numero_factura,
                )
                cursor.execute(
                    """
                    INSERT INTO factura_arca(
                        cliente_id, emisor_id, resumen_id, fecha, punto_venta, tipo_comprobante,
                        importe_total, estado, numero_factura, cae, vencimiento_cae, observaciones, fecha_creacion,
                        punto_venta_num, tipo_comprobante_num, numero_comprobante_num,
                        tipo_documento_receptor, documento_receptor,
                        snapshot_fiscal_json, snapshot_version, snapshot_hash
                    ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        receptor_final["cliente_id"], emisor_final["emisor_id"], intento.resumen_id,
                        comprobante_final["fecha_arca"], str(comprobante_final["punto_venta_num"]),
                        self._tipo_factura(comprobante_final["tipo_comprobante_num"]),
                        float(importes_final["total"]), "Facturada manualmente", numero_factura, cae, vencimiento,
                        "Factura recuperada desde comprobante autorizado ARCA.", self._ahora(),
                        punto_num, tipo_num, numero_num,
                        tipo_documento_receptor, documento_receptor,
                        snapshot_construido.snapshot_json,
                        snapshot_construido.snapshot_version,
                        snapshot_construido.snapshot_hash,
                    ),
                )
                factura_id = cursor.lastrowid
                insertada = True

            cursor.execute(
                """
                UPDATE resumenes
                SET estado_facturacion='Facturado', fecha_facturacion=?, cae=?, vencimiento_cae=?, numero_factura=?
                WHERE id=?
                """,
                (self._ahora(), cae, vencimiento, numero_factura, intento.resumen_id),
            )
            ahora = self._ahora()
            cursor.execute(
                """
                UPDATE intentos_emision_arca
                SET estado='RECONCILIADO', cae=?, vencimiento_cae=?, factura_arca_id=?,
                    error_codigo=NULL, error_mensaje=NULL, actualizado_en=?, reconciliado_en=?
                WHERE id=?
                """,
                (cae, vencimiento, factura_id, ahora, ahora, intento.id),
            )
            if cursor.rowcount != 1:
                raise LookupError(f"Intento inexistente: {intento.id}")
            conexion.commit()
            return ResultadoRecuperacionLocal(ResultadoReconciliacion.AUTORIZADO, factura_id, insertada)
        except Exception:
            conexion.rollback()
            raise
        finally:
            conexion.close()