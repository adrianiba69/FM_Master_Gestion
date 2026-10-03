from datetime import datetime

from database import conectar
from models.factura_arca import FacturaArca
from services.arca.fiscal_normalization import normalizar_identidad_factura
from services.arca import ambiente_arca
from services.arca.snapshot_fiscal_service import CODIGO_VALIDO, validar_integridad_snapshot


class FacturaArcaService:

    COLUMNAS_BASE = (
        "id, cliente_id, emisor_id, resumen_id, fecha, punto_venta, tipo_comprobante, "
        "importe_total, estado, numero_factura, cae, vencimiento_cae, observaciones, fecha_creacion, "
        "punto_venta_num, tipo_comprobante_num, numero_comprobante_num, tipo_documento_receptor, "
        "documento_receptor, snapshot_fiscal_json, snapshot_version, snapshot_hash, "
        "ruta_pdf_relativa, ruta_pdf_absoluta, ambiente_arca"
    )

    @staticmethod
    def _columnas_existentes(cur):
        cur.execute("PRAGMA table_info(factura_arca)")
        return {fila[1] for fila in cur.fetchall()}

    @staticmethod
    def _select_columnas(cur):
        columnas = FacturaArcaService._columnas_existentes(cur)
        tiene_snapshot = {"snapshot_fiscal_json", "snapshot_version", "snapshot_hash"}.issubset(columnas)
        tiene_ruta_pdf = {"ruta_pdf_relativa", "ruta_pdf_absoluta"}.issubset(columnas)
        tiene_ambiente = "ambiente_arca" in columnas
        if tiene_snapshot and tiene_ruta_pdf and tiene_ambiente:
            return FacturaArcaService.COLUMNAS_BASE

        partes_snapshot = (
            "snapshot_fiscal_json, snapshot_version, snapshot_hash"
            if tiene_snapshot
            else "NULL AS snapshot_fiscal_json, NULL AS snapshot_version, NULL AS snapshot_hash"
        )
        partes_ruta_pdf = (
            "ruta_pdf_relativa, ruta_pdf_absoluta"
            if tiene_ruta_pdf
            else "NULL AS ruta_pdf_relativa, NULL AS ruta_pdf_absoluta"
        )
        parte_ambiente = "ambiente_arca" if tiene_ambiente else "NULL AS ambiente_arca"
        return (
            "id, cliente_id, emisor_id, resumen_id, fecha, punto_venta, tipo_comprobante, "
            "importe_total, estado, numero_factura, cae, vencimiento_cae, observaciones, fecha_creacion, "
            "punto_venta_num, tipo_comprobante_num, numero_comprobante_num, tipo_documento_receptor, "
            f"documento_receptor, {partes_snapshot}, {partes_ruta_pdf}, {parte_ambiente}"
        )

    @staticmethod
    def validar_pre_guardado(
        cliente_id,
        emisor_id,
        resumen_id,
        fecha,
        punto_venta,
        tipo_comprobante,
        importe_total,
        estado,
    ):
        errores = []

        try:
            cliente_val = int(cliente_id)
            if cliente_val <= 0:
                raise ValueError()
        except (TypeError, ValueError):
            errores.append("cliente_id obligatorio e invalido.")

        try:
            emisor_val = int(emisor_id)
            if emisor_val <= 0:
                raise ValueError()
        except (TypeError, ValueError):
            errores.append("emisor_id obligatorio e invalido.")

        try:
            resumen_val = int(resumen_id)
            if resumen_val <= 0:
                raise ValueError()
        except (TypeError, ValueError):
            resumen_val = 0
            errores.append("resumen_id obligatorio e invalido.")

        fecha_texto = str(fecha or "").strip()
        if not fecha_texto:
            errores.append("fecha obligatoria.")

        if not str(punto_venta or "").strip():
            errores.append("punto_venta obligatorio.")

        if not str(tipo_comprobante or "").strip():
            errores.append("tipo_comprobante obligatorio.")

        try:
            importe_val = float(importe_total)
            if importe_val <= 0:
                raise ValueError()
        except (TypeError, ValueError):
            errores.append("importe_total obligatorio y debe ser mayor a cero.")

        if not str(estado or "").strip():
            errores.append("estado obligatorio.")

        if errores:
            return {"ok": False, "errores": errores}

        conn = conectar()
        try:
            cur = conn.cursor()
            cur.execute("SELECT 1 FROM resumenes WHERE id=?", (resumen_val,))
            if cur.fetchone() is None:
                errores.append("resumen_id no existe en base local.")
        finally:
            conn.close()

        return {"ok": not errores, "errores": errores}

    @staticmethod
    def listar(estado=None):
        conn = conectar()
        cur = conn.cursor()
        consulta = f"SELECT {FacturaArcaService._select_columnas(cur)} FROM factura_arca"
        params = ()
        if estado:
            consulta += " WHERE estado=?"
            params = (estado,)
        consulta += " ORDER BY fecha DESC, id DESC"
        cur.execute(consulta, params)
        filas = cur.fetchall()
        conn.close()
        return filas

    @staticmethod
    def obtener(id_):
        conn = conectar()
        cur = conn.cursor()
        cur.execute(
            f"SELECT {FacturaArcaService._select_columnas(cur)} FROM factura_arca WHERE id=?",
            (id_,),
        )
        fila = cur.fetchone()
        conn.close()
        return fila

    @staticmethod
    def guardar(factura: FacturaArca):
        ambiente_informado = (
            ambiente_arca.normalizar_ambiente_arca(factura.ambiente_arca)
            if factura.ambiente_arca is not None else None
        )
        conn = conectar()
        cur = conn.cursor()
        columnas_existentes = FacturaArcaService._columnas_existentes(cur)
        punto_num, tipo_num, numero_num = normalizar_identidad_factura(
            factura.punto_venta, factura.tipo_comprobante, factura.numero_factura
        )
        ambiente = None
        if "ambiente_arca" in columnas_existentes:
            if any(valor is not None for valor in (
                factura.snapshot_fiscal_json, factura.snapshot_version, factura.snapshot_hash
            )):
                validacion = validar_integridad_snapshot(
                    factura.snapshot_fiscal_json, factura.snapshot_version, factura.snapshot_hash
                )
                if validacion.codigo != CODIGO_VALIDO:
                    conn.close()
                    raise ValueError("Snapshot fiscal inválido para guardar factura ARCA.")
                snapshot = validacion.snapshot
                comprobante = snapshot["comprobante"]
                if (
                    (punto_num, tipo_num, numero_num) != (
                        comprobante["punto_venta_num"], comprobante["tipo_comprobante_num"],
                        comprobante["numero_comprobante_num"],
                    )
                    or factura.emisor_id != snapshot["emisor"]["emisor_id"]
                    or factura.cliente_id != snapshot["receptor"]["cliente_id"]
                    or str(factura.cae or "").strip() != snapshot["autorizacion"]["cae"]
                ):
                    conn.close()
                    raise ValueError("Identidad fiscal contradictoria con el snapshot.")
                ambiente = snapshot["ambiente"]
                if ambiente_informado is not None and ambiente_informado != ambiente:
                    conn.close()
                    raise ValueError("Ambiente ARCA contradictorio con el snapshot.")
            elif factura.cae or (factura.numero_factura and str(factura.estado or "").lower().startswith("facturad")):
                conn.close()
                raise ValueError("Una factura fiscal confirmada requiere snapshot y ambiente ARCA.")
            else:
                ambiente = ambiente_informado
        columnas = [
            "cliente_id", "emisor_id", "resumen_id", "fecha", "punto_venta", "tipo_comprobante",
            "importe_total", "estado", "numero_factura", "cae", "vencimiento_cae", "observaciones",
            "fecha_creacion", "punto_venta_num", "tipo_comprobante_num", "numero_comprobante_num",
            "tipo_documento_receptor", "documento_receptor",
        ]
        valores = [
            factura.cliente_id,
            factura.emisor_id,
            factura.resumen_id,
            factura.fecha,
            factura.punto_venta,
            factura.tipo_comprobante,
            factura.importe_total,
            factura.estado,
            factura.numero_factura,
            factura.cae,
            factura.vencimiento_cae,
            factura.observaciones,
            factura.fecha_creacion or datetime.now().isoformat(timespec="seconds"),
            punto_num,
            tipo_num,
            numero_num,
            factura.tipo_documento_receptor,
            factura.documento_receptor,
        ]
        if {"snapshot_fiscal_json", "snapshot_version", "snapshot_hash"}.issubset(columnas_existentes):
            columnas.extend(["snapshot_fiscal_json", "snapshot_version", "snapshot_hash"])
            valores.extend([factura.snapshot_fiscal_json, factura.snapshot_version, factura.snapshot_hash])
        if {"ruta_pdf_relativa", "ruta_pdf_absoluta"}.issubset(columnas_existentes):
            columnas.extend(["ruta_pdf_relativa", "ruta_pdf_absoluta"])
            valores.extend([factura.ruta_pdf_relativa, factura.ruta_pdf_absoluta])
        if "ambiente_arca" in columnas_existentes:
            columnas.append("ambiente_arca")
            valores.append(ambiente)
        try:
            placeholders = ",".join("?" for _ in columnas)
            cur.execute(
                f"INSERT INTO factura_arca({','.join(columnas)}) VALUES({placeholders})",
                tuple(valores),
            )
            factura_id = cur.lastrowid
            conn.commit()
            return factura_id
        finally:
            conn.close()

    @staticmethod
    def actualizar(factura: FacturaArca):
        conn = conectar()
        try:
            cur = conn.cursor()
            columnas = FacturaArcaService._columnas_existentes(cur)
            cur.execute(
                "SELECT emisor_id, punto_venta, tipo_comprobante, numero_factura, cae, "
                + ("ambiente_arca" if "ambiente_arca" in columnas else "NULL")
                + (", snapshot_fiscal_json" if "snapshot_fiscal_json" in columnas else ", NULL")
                + " FROM factura_arca WHERE id=?", (factura.id,),
            )
            actual = cur.fetchone()
            if actual and (actual[5] is not None or actual[6] is not None):
                if (factura.emisor_id, factura.punto_venta, factura.tipo_comprobante,
                    factura.numero_factura, factura.cae) != actual[:5]:
                    raise ValueError("No se puede modificar la identidad de una factura fiscal congelada.")
            punto_num, tipo_num, numero_num = normalizar_identidad_factura(
                factura.punto_venta, factura.tipo_comprobante, factura.numero_factura
            )
            cur.execute(
                "UPDATE factura_arca SET cliente_id=?, emisor_id=?, resumen_id=?, fecha=?, punto_venta=?, "
                "tipo_comprobante=?, importe_total=?, estado=?, numero_factura=?, cae=?, vencimiento_cae=?, "
                "observaciones=?, punto_venta_num=?, tipo_comprobante_num=?, numero_comprobante_num=? WHERE id=?",
                (
                    factura.cliente_id, factura.emisor_id, factura.resumen_id, factura.fecha,
                    factura.punto_venta, factura.tipo_comprobante, factura.importe_total,
                    factura.estado, factura.numero_factura, factura.cae, factura.vencimiento_cae,
                    factura.observaciones, punto_num, tipo_num, numero_num, factura.id,
                ),
            )
            conn.commit()
        finally:
            conn.close()

    @staticmethod
    def actualizar_ruta_pdf(factura_id, ruta_pdf_relativa, ruta_pdf_absoluta):
        """Actualiza exclusivamente la ubicacion operativa del PDF fiscal.
        No toca CAE, snapshot, estado ni identidad fiscal de la factura."""
        conn = conectar()
        cur = conn.cursor()
        cur.execute(
            "UPDATE factura_arca SET ruta_pdf_relativa=?, ruta_pdf_absoluta=? WHERE id=?",
            (ruta_pdf_relativa, ruta_pdf_absoluta, int(factura_id)),
        )
        conn.commit()
        conn.close()

    @staticmethod
    def listar_por_resumen(resumen_id):
        conn = conectar()
        cur = conn.cursor()
        cur.execute(
            f"SELECT {FacturaArcaService._select_columnas(cur)} FROM factura_arca WHERE resumen_id=?",
            (resumen_id,),
        )
        filas = cur.fetchall()
        conn.close()
        return filas

    @staticmethod
    def buscar_por_resumen_id(resumen_id):
        return FacturaArcaService.listar_por_resumen(resumen_id)

    @staticmethod
    def buscar_por_factura_arca_id(factura_arca_id):
        return FacturaArcaService.obtener(factura_arca_id)

    @staticmethod
    def buscar_por_cae(cae):
        conn = conectar()
        try:
            cur = conn.cursor()
            cur.execute(
                f"SELECT {FacturaArcaService._select_columnas(cur)} FROM factura_arca WHERE cae=? ORDER BY id",
                (str(cae or "").strip(),),
            )
            return cur.fetchall()
        finally:
            conn.close()

    @staticmethod
    def buscar_por_identidad_fiscal(emisor_id, punto_venta, tipo_comprobante, numero_factura, ambiente_arca=None):
        conn = conectar()
        try:
            cur = conn.cursor()
            columnas = FacturaArcaService._columnas_existentes(cur)
            sql = (
                f"SELECT {FacturaArcaService._select_columnas(cur)} FROM factura_arca "
                "WHERE emisor_id=? AND TRIM(COALESCE(punto_venta, ''))=? "
                "AND TRIM(COALESCE(tipo_comprobante, ''))=? AND TRIM(COALESCE(numero_factura, ''))=?"
            )
            params = (
                int(emisor_id),
                str(punto_venta or "").strip(),
                str(tipo_comprobante or "").strip(),
                str(numero_factura or "").strip(),
            )
            if "ambiente_arca" in columnas and ambiente_arca is not None:
                sql += " AND ambiente_arca=?"
                params += (str(ambiente_arca).strip(),)
            sql += " ORDER BY id"
            cur.execute(sql, params)
            return cur.fetchall()
        finally:
            conn.close()
