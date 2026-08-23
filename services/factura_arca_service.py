from datetime import datetime

from database import conectar
from models.factura_arca import FacturaArca
from services.arca.fiscal_normalization import normalizar_identidad_factura


class FacturaArcaService:

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
        consulta = "SELECT id, cliente_id, emisor_id, resumen_id, fecha, punto_venta, tipo_comprobante, importe_total, estado, numero_factura, cae, vencimiento_cae, observaciones, fecha_creacion, punto_venta_num, tipo_comprobante_num, numero_comprobante_num, tipo_documento_receptor, documento_receptor FROM factura_arca"
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
            "SELECT id, cliente_id, emisor_id, resumen_id, fecha, punto_venta, tipo_comprobante, importe_total, estado, numero_factura, cae, vencimiento_cae, observaciones, fecha_creacion, punto_venta_num, tipo_comprobante_num, numero_comprobante_num, tipo_documento_receptor, documento_receptor FROM factura_arca WHERE id=?",
            (id_,),
        )
        fila = cur.fetchone()
        conn.close()
        return fila

    @staticmethod
    def guardar(factura: FacturaArca):
        conn = conectar()
        cur = conn.cursor()
        punto_num, tipo_num, numero_num = normalizar_identidad_factura(
            factura.punto_venta, factura.tipo_comprobante, factura.numero_factura
        )
        cur.execute(
            "INSERT INTO factura_arca(cliente_id, emisor_id, resumen_id, fecha, punto_venta, tipo_comprobante, importe_total, estado, numero_factura, cae, vencimiento_cae, observaciones, fecha_creacion, punto_venta_num, tipo_comprobante_num, numero_comprobante_num, tipo_documento_receptor, documento_receptor) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
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
            ),
        )
        factura_id = cur.lastrowid
        conn.commit()
        conn.close()
        return factura_id

    @staticmethod
    def actualizar(factura: FacturaArca):
        conn = conectar()
        cur = conn.cursor()
        cur.execute(
            "UPDATE factura_arca SET cliente_id=?, emisor_id=?, resumen_id=?, fecha=?, punto_venta=?, tipo_comprobante=?, importe_total=?, estado=?, numero_factura=?, cae=?, vencimiento_cae=?, observaciones=? WHERE id=?",
            (
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
                factura.id,
            ),
        )
        conn.commit()
        conn.close()

    @staticmethod
    def listar_por_resumen(resumen_id):
        conn = conectar()
        cur = conn.cursor()
        cur.execute(
            "SELECT id, cliente_id, emisor_id, resumen_id, fecha, punto_venta, tipo_comprobante, importe_total, estado, numero_factura, cae, vencimiento_cae, observaciones, fecha_creacion FROM factura_arca WHERE resumen_id=?",
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
                "SELECT id, cliente_id, emisor_id, resumen_id, fecha, punto_venta, tipo_comprobante, importe_total, estado, numero_factura, cae, vencimiento_cae, observaciones, fecha_creacion FROM factura_arca WHERE cae=? ORDER BY id",
                (str(cae or "").strip(),),
            )
            return cur.fetchall()
        finally:
            conn.close()

    @staticmethod
    def buscar_por_identidad_fiscal(emisor_id, punto_venta, tipo_comprobante, numero_factura):
        conn = conectar()
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT id, cliente_id, emisor_id, resumen_id, fecha, punto_venta, tipo_comprobante, importe_total, estado, numero_factura, cae, vencimiento_cae, observaciones, fecha_creacion FROM factura_arca WHERE emisor_id=? AND TRIM(COALESCE(punto_venta, ''))=? AND TRIM(COALESCE(tipo_comprobante, ''))=? AND TRIM(COALESCE(numero_factura, ''))=? ORDER BY id",
                (
                    int(emisor_id),
                    str(punto_venta or "").strip(),
                    str(tipo_comprobante or "").strip(),
                    str(numero_factura or "").strip(),
                ),
            )
            return cur.fetchall()
        finally:
            conn.close()
