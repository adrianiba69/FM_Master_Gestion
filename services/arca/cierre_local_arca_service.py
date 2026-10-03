from dataclasses import dataclass
from datetime import datetime

from database import conectar
from services.arca.fiscal_normalization import normalizar_identidad_factura
from services.arca.reconciliacion_contracts import ResultadoReconciliacion, normalizar_importe
from services.arca.snapshot_fiscal_persistence_service import SnapshotFiscalPersistenceService
from services.arca.snapshot_fiscal_service import CODIGO_VALIDO, validar_integridad_snapshot


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
        ambiente_esperado = str(datos.get("ambiente_arca") or "").strip()
        if ambiente_esperado and len(fila) > 12:
            ambiente_actual = str(fila[12] if len(fila) > 12 and fila[12] is not None else "").strip()
            if ambiente_actual != ambiente_esperado:
                return False

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
    def _seleccion_factura(cursor, datos, tiene_ambiente=False):
        columnas = (
            "id, cliente_id, emisor_id, resumen_id, fecha, punto_venta, "
            "tipo_comprobante, importe_total, estado, numero_factura, cae, vencimiento_cae"
        )
        if tiene_ambiente:
            columnas += ", ambiente_arca"
        candidatas = []
        ambiente_filtro = str(datos.get("ambiente_arca") or "").strip()
        cursor.execute("PRAGMA table_info(factura_arca)")
        disponibles = {fila[1] for fila in cursor.fetchall()}
        normalizadas = {"punto_venta_num", "tipo_comprobante_num", "numero_comprobante_num"}
        identidad = (
            "emisor_id=? AND punto_venta_num=? AND tipo_comprobante_num=? AND numero_comprobante_num=?"
            if normalizadas.issubset(disponibles) else
            "emisor_id=? AND TRIM(COALESCE(punto_venta,''))=? "
            "AND TRIM(COALESCE(tipo_comprobante,''))=? AND TRIM(COALESCE(numero_factura,''))=?"
        )
        valores_identidad = (
            (int(datos["emisor_id"]), *normalizar_identidad_factura(
                datos["punto_venta"], datos["tipo_comprobante"], datos["numero_factura"]
            )) if normalizadas.issubset(disponibles) else
            (int(datos["emisor_id"]), str(datos["punto_venta"]),
             str(datos["tipo_comprobante"]), str(datos["numero_factura"]))
        )
        if datos.get("factura_arca_id"):
            consulta = f"SELECT {columnas} FROM factura_arca WHERE id=?"
            params = [int(datos["factura_arca_id"])]
            cursor.execute(consulta, tuple(params))
            fila = cursor.fetchone()
            if fila:
                candidatas.append(fila)

        consulta = f"SELECT {columnas} FROM factura_arca WHERE resumen_id=?"
        params = [int(datos["resumen_id"])]
        consulta += " ORDER BY id"
        cursor.execute(consulta, tuple(params))
        candidatas.extend(cursor.fetchall())

        consulta = f"SELECT {columnas} FROM factura_arca WHERE {identidad}"
        params = list(valores_identidad)
        if tiene_ambiente and ambiente_filtro:
            consulta += " AND (ambiente_arca=? OR ambiente_arca IS NULL)"
            params.append(ambiente_filtro)
        consulta += " ORDER BY id"
        cursor.execute(consulta, tuple(params))
        candidatas.extend(cursor.fetchall())

        if normalizadas.issubset(disponibles):
            consulta = (
                f"SELECT {columnas} FROM factura_arca WHERE emisor_id=? AND "
                "(punto_venta_num IS NULL OR tipo_comprobante_num IS NULL OR numero_comprobante_num IS NULL)"
            )
            params = [int(datos["emisor_id"])]
            if tiene_ambiente and ambiente_filtro:
                consulta += " AND (ambiente_arca=? OR ambiente_arca IS NULL)"
                params.append(ambiente_filtro)
            cursor.execute(consulta, tuple(params))
            candidatas.extend(
                fila for fila in cursor.fetchall()
                if normalizar_identidad_factura(fila[5], fila[6], fila[9]) == valores_identidad[1:]
            )

        consulta = f"SELECT {columnas} FROM factura_arca WHERE TRIM(cae)=?"
        params = [str(datos["cae"])]
        if tiene_ambiente and ambiente_filtro:
            consulta += f" AND (ambiente_arca=? OR ambiente_arca IS NULL OR NOT COALESCE(({identidad}), 0))"
            params.append(ambiente_filtro)
            params.extend(valores_identidad)
        consulta += " ORDER BY id"
        cursor.execute(consulta, tuple(params))
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
        snapshot_fiscal_json=None,
        snapshot_version=None,
        snapshot_hash=None,
    ):
        ambiente_snapshot = None
        if snapshot_fiscal_json is not None:
            integridad = validar_integridad_snapshot(snapshot_fiscal_json, snapshot_version, snapshot_hash)
            if integridad.codigo != CODIGO_VALIDO:
                return ResultadoCierreLocalArca(
                    False,
                    ResultadoReconciliacion.CONFLICTO,
                    mensaje=f"snapshot_fiscal_invalido ({integridad.codigo}): {'; '.join(integridad.errores)}",
                )
            ambiente_snapshot = integridad.snapshot["ambiente"]

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
            "snapshot_fiscal_json": snapshot_fiscal_json,
            "snapshot_version": snapshot_version,
            "snapshot_hash": snapshot_hash,
            "ambiente_arca": ambiente_snapshot,
        }
        conexion = self._conexion_factory()
        try:
            cursor = conexion.cursor()
            cursor.execute("BEGIN IMMEDIATE")
            cursor.execute("PRAGMA table_info(factura_arca)")
            tiene_ambiente = any(fila[1] == "ambiente_arca" for fila in cursor.fetchall())
            if tiene_ambiente and ambiente_snapshot is None:
                conexion.rollback()
                return ResultadoCierreLocalArca(
                    False, ResultadoReconciliacion.CONFLICTO, mensaje="Falta snapshot fiscal con ambiente ARCA."
                )
            compatibles, incompatibles = self._seleccion_factura(cursor, datos, tiene_ambiente=tiene_ambiente)
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
                if datos["snapshot_fiscal_json"] is not None:
                    resultado_snapshot = SnapshotFiscalPersistenceService().guardar_snapshot_si_ausente(
                        factura_id,
                        datos["snapshot_fiscal_json"],
                        datos["snapshot_version"],
                        datos["snapshot_hash"],
                        conn=conexion,
                    )
                    if not resultado_snapshot.ok:
                        conexion.rollback()
                        return ResultadoCierreLocalArca(
                            False,
                            ResultadoReconciliacion.CONFLICTO,
                            mensaje=f"{resultado_snapshot.codigo}: {resultado_snapshot.mensaje}",
                        )
            else:
                punto_num, tipo_num, numero_num = normalizar_identidad_factura(
                    punto_venta, tipo_comprobante, numero_factura
                )
                columnas_insert = [
                    "cliente_id", "emisor_id", "resumen_id", "fecha", "punto_venta", "tipo_comprobante",
                    "importe_total", "estado", "numero_factura", "cae", "vencimiento_cae", "observaciones",
                    "fecha_creacion", "punto_venta_num", "tipo_comprobante_num", "numero_comprobante_num",
                    "tipo_documento_receptor", "documento_receptor",
                ]
                valores_insert = [
                    cliente_id, emisor_id, resumen_id, fecha, str(punto_venta), str(tipo_comprobante),
                    float(importe_total), "Facturada manualmente", datos["numero_factura"], datos["cae"],
                    datos["vencimiento_cae"], datos["observaciones"], self._ahora(),
                    punto_num, tipo_num, numero_num,
                    datos["tipo_documento_receptor"], datos["documento_receptor"],
                ]
                if datos["snapshot_fiscal_json"] is not None:
                    columnas_insert.extend(["snapshot_fiscal_json", "snapshot_version", "snapshot_hash"])
                    valores_insert.extend(
                        [datos["snapshot_fiscal_json"], datos["snapshot_version"], datos["snapshot_hash"]]
                    )
                if tiene_ambiente:
                    columnas_insert.append("ambiente_arca")
                    valores_insert.append(ambiente_snapshot)
                placeholders = ",".join("?" for _ in columnas_insert)
                cursor.execute(
                    f"INSERT INTO factura_arca({','.join(columnas_insert)}) VALUES({placeholders})",
                    tuple(valores_insert),
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
