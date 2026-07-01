from datetime import datetime

from database import conectar
from models.factura_arca import FacturaArca


class FacturaArcaService:

    @staticmethod
    def listar(estado=None):
        conn = conectar()
        cur = conn.cursor()
        consulta = "SELECT id, cliente_id, emisor_id, resumen_id, fecha, punto_venta, tipo_comprobante, importe_total, estado, numero_factura, cae, vencimiento_cae, observaciones, fecha_creacion FROM factura_arca"
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
            "SELECT id, cliente_id, emisor_id, resumen_id, fecha, punto_venta, tipo_comprobante, importe_total, estado, numero_factura, cae, vencimiento_cae, observaciones, fecha_creacion FROM factura_arca WHERE id=?",
            (id_,),
        )
        fila = cur.fetchone()
        conn.close()
        return fila

    @staticmethod
    def guardar(factura: FacturaArca):
        conn = conectar()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO factura_arca(cliente_id, emisor_id, resumen_id, fecha, punto_venta, tipo_comprobante, importe_total, estado, numero_factura, cae, vencimiento_cae, observaciones, fecha_creacion) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
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
