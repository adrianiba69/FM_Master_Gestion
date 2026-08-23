from dataclasses import dataclass
from datetime import datetime

from database import conectar
from services.arca.fiscal_normalization import normalizar_identidad_factura
from services.arca.reconciliacion_contracts import ResultadoReconciliacion, normalizar_importe


@dataclass(frozen=True)
class ResultadoCierreLocalArca:
    ok: bool
    resultado: ResultadoReconciliacion = ResultadoReconciliacion.CONSULTA_INCIERTA
    factura_arca_id: int = None
    insertada: bool = False
    mensaje: str = ""


class CierreLocalArcaService:
    """Cierra una autorizacion ARCA confirmada en una unica transaccion local."""

    def __init__(self, conexion_factory=conectar):
        self._conexion_factory = conexion_factory

    @staticmethod
    def _ahora():
        return datetime.now().isoformat(timespec="seconds")

    @staticmethod
    def _fila_compatible(fila, datos):
        esperado = (
            int(datos["cliente_id"]),
            int(datos["emisor_id"]),
            int(datos["resumen_id"]),
            str(datos["punto_venta"]),
            str(datos["tipo_comprobante"]),
            normalizar_importe(datos["importe_total"]),
            str(datos["numero_factura"]),
            str(datos["cae"]),
            str(datos["vencimiento_cae"]),
        )
        actual = (
            int(fila[1]),
            int(fila[2]),
            int(fila[3]),
            str(fila[5] or "").strip(),
            str(fila[6] or "").strip(),
            normalizar_importe(fila[7]),
            str(fila[9] or "").strip(),
            str(fila[10] or "").strip(),
            str(fila[11] or "").strip(),
        )
        return actual == esperado

    @staticmethod
    def _seleccion_factura(cursor, datos):
        columnas = (
            "id, cliente_id, emisor_id, resumen_id, fecha, punto_venta, "
            "tipo_comprobante, importe_total, estado, numero_factura, cae, vencimiento_cae"
        )
        candidatas = []
        if datos.get("factura_arca_id"):
            cursor.execute(f"SELECT {columnas} FROM factura_arca WHERE id=?", (int(datos["factura_arca_id"]),))
            fila = cursor.fetchone()
            if fila:
                candidatas.append(fila)

        cursor.execute(f"SELECT {columnas} FROM factura_arca WHERE resumen_id=? ORDER BY id", (int(datos["resumen_id"]),))
        candidatas.extend(cursor.fetchall())

        cursor.execute(
            f"SELECT {columnas} FROM factura_arca WHERE emisor_id=? AND TRIM(COALESCE(punto_venta,''))=? "
            "AND TRIM(COALESCE(tipo_comprobante,''))=? AND TRIM(COALESCE(numero_factura,''))=? ORDER BY id",
            (int(datos["emisor_id"]), str(datos["punto_venta"]), str(datos["tipo_comprobante"]), str(datos["numero_factura"])),
        )
        candidatas.extend(cursor.fetchall())

        cursor.execute(f"SELECT {columnas} FROM factura_arca WHERE cae=? ORDER BY id", (str(datos["cae"]),))
        candidatas.extend(cursor.fetchall())

        unicas = {fila[0]: fila for fila in candidatas}
        compatibles = [fila for fila in unicas.values() if CierreLocalArcaService._fila_compatible(fila, datos)]
        incompatibles = [fila for fila in unicas.values() if fila not in compatibles]
        return compatibles, incompatibles

    def cerrar_emision_confirmada(
        self,
        intento_id,
        resumen_id,
        cliente_id,
        emisor_id,
        fecha,
        punto_venta,
        tipo_comprobante,
        importe_total,
        numero_factura,
        cae,
        vencimiento_cae,
        observaciones="",
        factura_arca_id=None,
        tipo_documento_receptor=None,
        documento_receptor=None,
    ):
        datos = {
            "intento_id": intento_id,
            "resumen_id": resumen_id,
            "cliente_id": cliente_id,
            "emisor_id": emisor_id,
            "fecha": fecha,
            "punto_venta": punto_venta,
            "tipo_comprobante": tipo_comprobante,
            "importe_total": importe_total,
            "numero_factura": str(numero_factura or "").strip(),
            "cae": str(cae or "").strip(),
            "vencimiento_cae": str(vencimiento_cae or "").strip(),
            "observaciones": str(observaciones or ""),
            "factura_arca_id": factura_arca_id,
            "tipo_documento_receptor": tipo_documento_receptor,
            "documento_receptor": documento_receptor,
        }
        conexion = self._conexion_factory()
        try:
            cursor = conexion.cursor()
            cursor.execute("BEGIN IMMEDIATE")
            compatibles, incompatibles = self._seleccion_factura(cursor, datos)
            if incompatibles or len(compatibles) > 1:
                conexion.rollback()
                return ResultadoCierreLocalArca(
                    False,
                    ResultadoReconciliacion.CONFLICTO,
                    mensaje="Existe una factura local incompatible o duplicada.",
                )

            insertada = False
            if compatibles:
                factura_id = int(compatibles[0][0])
            else:
                punto_num, tipo_num, numero_num = normalizar_identidad_factura(
                    punto_venta, tipo_comprobante, numero_factura
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
                        cliente_id, emisor_id, resumen_id, fecha, str(punto_venta), str(tipo_comprobante),
                        float(importe_total), "Facturada manualmente", datos["numero_factura"], datos["cae"],
                        datos["vencimiento_cae"], datos["observaciones"], self._ahora(),
                        punto_num, tipo_num, numero_num,
                        datos["tipo_documento_receptor"], datos["documento_receptor"],
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
                (self._ahora(), datos["cae"], datos["vencimiento_cae"], datos["numero_factura"], int(resumen_id)),
            )
            if cursor.rowcount != 1:
                raise LookupError(f"Resumen inexistente: {resumen_id}")

            ahora = self._ahora()
            cursor.execute(
                """
                UPDATE intentos_emision_arca
                SET estado='RECONCILIADO', cae=?, vencimiento_cae=?, factura_arca_id=?,
                    error_codigo=NULL, error_mensaje=NULL, actualizado_en=?, reconciliado_en=?
                WHERE id=?
                """,
                (datos["cae"], datos["vencimiento_cae"], factura_id, ahora, ahora, int(intento_id)),
            )
            if cursor.rowcount != 1:
                raise LookupError(f"Intento de emision ARCA inexistente: {intento_id}")

            conexion.commit()
            return ResultadoCierreLocalArca(True, ResultadoReconciliacion.AUTORIZADO, factura_id, insertada)
        except Exception:
            conexion.rollback()
            raise
        finally:
            conexion.close()
