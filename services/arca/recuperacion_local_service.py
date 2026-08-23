from dataclasses import dataclass
from datetime import datetime

from database import conectar
from models.intento_emision_arca import IntentoEmisionArca
from services.arca.reconciliacion_contracts import (
    ResultadoReconciliacion,
    SnapshotFiscalEsperado,
    comparar_snapshot_con_comprobante,
    normalizar_importe,
)
from services.arca.fiscal_normalization import normalizar_identidad_factura


@dataclass(frozen=True)
class ResultadoRecuperacionLocal:
    resultado: ResultadoReconciliacion
    factura_arca_id: int = None
    insertada: bool = False
    mensaje: str = ""


class RecuperacionLocalArcaService:
    """Reconstruye localmente una autorización ARCA ya consultada y validada."""

    def __init__(self, conexion_factory=conectar):
        self._conexion_factory = conexion_factory

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
    def _fila_compatible(cls, fila, intento, snapshot, consulta):
        if not fila:
            return False
        numero = cls._numero_factura(snapshot.punto_venta, snapshot.numero_planificado)
        if (
            int(fila[1]) != int(intento.cliente_id)
            or int(fila[2]) != int(intento.emisor_id)
            or int(fila[3]) != int(intento.resumen_id)
        ):
            return False

        esperados = (
            (fila[5], str(snapshot.punto_venta)),
            (fila[6], cls._tipo_factura(snapshot.tipo_comprobante)),
            (fila[7], normalizar_importe(snapshot.importe_total)),
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
    def _buscar_facturas(cursor, intento, snapshot, consulta):
        seleccion = "id, cliente_id, emisor_id, resumen_id, fecha, punto_venta, tipo_comprobante, importe_total, estado, numero_factura, cae, vencimiento_cae"
        candidatas = []

        if intento.factura_arca_id:
            cursor.execute(f"SELECT {seleccion} FROM factura_arca WHERE id=?", (intento.factura_arca_id,))
            fila = cursor.fetchone()
            if fila:
                candidatas.append(fila)

        cursor.execute(f"SELECT {seleccion} FROM factura_arca WHERE resumen_id=? ORDER BY id", (intento.resumen_id,))
        candidatas.extend(cursor.fetchall())

        numero = RecuperacionLocalArcaService._numero_factura(snapshot.punto_venta, snapshot.numero_planificado)
        cursor.execute(
            f"SELECT {seleccion} FROM factura_arca WHERE emisor_id=? AND TRIM(COALESCE(punto_venta, ''))=? AND TRIM(COALESCE(tipo_comprobante, ''))=? AND TRIM(COALESCE(numero_factura, ''))=? ORDER BY id",
            (intento.emisor_id, str(snapshot.punto_venta), RecuperacionLocalArcaService._tipo_factura(snapshot.tipo_comprobante), numero),
        )
        candidatas.extend(cursor.fetchall())

        cursor.execute(f"SELECT {seleccion} FROM factura_arca WHERE cae=? ORDER BY id", (str(consulta.get("cae") or "").strip(),))
        candidatas.extend(cursor.fetchall())

        unicas = {fila[0]: fila for fila in candidatas}
        compatibles = [fila for fila in unicas.values() if RecuperacionLocalArcaService._fila_compatible(fila, intento, snapshot, consulta)]
        incompatibles = [fila for fila in unicas.values() if fila not in compatibles]
        return compatibles, incompatibles

    def registrar_factura_recuperada(self, intento, snapshot, consulta):
        if not isinstance(intento, IntentoEmisionArca):
            raise TypeError("intento debe ser IntentoEmisionArca.")
        if not isinstance(snapshot, SnapshotFiscalEsperado):
            raise TypeError("snapshot debe ser SnapshotFiscalEsperado.")

        comparacion = comparar_snapshot_con_comprobante(snapshot, consulta)
        if comparacion.resultado != ResultadoReconciliacion.AUTORIZADO:
            return ResultadoRecuperacionLocal(
                comparacion.resultado,
                mensaje="; ".join(comparacion.diferencias_texto or comparacion.campos_faltantes),
            )

        conexion = self._conexion_factory()
        try:
            cursor = conexion.cursor()
            cursor.execute("BEGIN IMMEDIATE")

            compatibles, incompatibles = self._buscar_facturas(cursor, intento, snapshot, consulta)
            if incompatibles or len(compatibles) > 1:
                conexion.rollback()
                return ResultadoRecuperacionLocal(ResultadoReconciliacion.CONFLICTO, mensaje="Factura local incompatible o duplicada.")

            numero_factura = self._numero_factura(snapshot.punto_venta, snapshot.numero_planificado)
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
                cursor.execute(
                    """
                    UPDATE factura_arca
                    SET fecha=?, punto_venta=?, tipo_comprobante=?, importe_total=?, estado=?,
                        numero_factura=?, cae=?, vencimiento_cae=?, tipo_documento_receptor=?, documento_receptor=?
                    WHERE id=?
                    """,
                    (
                        snapshot.fecha_comprobante, str(snapshot.punto_venta), self._tipo_factura(snapshot.tipo_comprobante),
                        float(snapshot.importe_total), "Facturada manualmente", numero_factura, cae, vencimiento,
                        tipo_documento_receptor, documento_receptor,
                        factura_id,
                    ),
                )
            else:
                punto_num, tipo_num, numero_num = normalizar_identidad_factura(
                    snapshot.punto_venta, self._tipo_factura(snapshot.tipo_comprobante), numero_factura
                )
                cursor.execute(
                    """
                    INSERT INTO factura_arca(
                        cliente_id, emisor_id, resumen_id, fecha, punto_venta, tipo_comprobante,
                        importe_total, estado, numero_factura, cae, vencimiento_cae, observaciones, fecha_creacion,
                        punto_venta_num, tipo_comprobante_num, numero_comprobante_num,
                        tipo_documento_receptor, documento_receptor
                    ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        intento.cliente_id, intento.emisor_id, intento.resumen_id, snapshot.fecha_comprobante,
                        str(snapshot.punto_venta), self._tipo_factura(snapshot.tipo_comprobante),
                        float(snapshot.importe_total), "Facturada manualmente", numero_factura, cae, vencimiento,
                        "Factura recuperada desde comprobante autorizado ARCA.", self._ahora(),
                        punto_num, tipo_num, numero_num,
                        tipo_documento_receptor, documento_receptor,
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