from database import conectar


class CobroService:

    @staticmethod
    def listar(cliente_id=None):
        conn = conectar()
        cur = conn.cursor()
        consulta = """
            SELECT
                co.id,
                co.cliente_id,
                co.fecha,
                co.importe,
                co.forma_pago,
                co.comprobante,
                co.observaciones,
                COALESCE(NULLIF(cl.razon_social, ''), cl.nombre) AS cliente
            FROM cobros co
            JOIN clientes cl ON cl.id=co.cliente_id
        """
        parametros = ()
        if cliente_id is not None:
            consulta += " WHERE co.cliente_id=?"
            parametros = (cliente_id,)
        consulta += " ORDER BY co.fecha DESC, co.id DESC"
        cur.execute(consulta, parametros)
        datos = cur.fetchall()
        conn.close()
        return datos

    @staticmethod
    def obtener(cobro_id):
        conn = conectar()
        cur = conn.cursor()
        cur.execute("""
            SELECT id, cliente_id, fecha, importe, forma_pago,
                   comprobante, observaciones
            FROM cobros
            WHERE id=?
        """, (cobro_id,))
        fila = cur.fetchone()
        conn.close()
        return fila

    @staticmethod
    def guardar(cobro):
        if float(cobro.importe) <= 0:
            raise ValueError("El importe del cobro debe ser mayor que cero.")

        conn = conectar()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO cobros(
                cliente_id, fecha, importe, forma_pago,
                comprobante, observaciones
            ) VALUES(?,?,?,?,?,?)
        """, (
            cobro.cliente_id,
            cobro.fecha,
            cobro.importe,
            cobro.forma_pago,
            cobro.comprobante,
            cobro.observaciones,
        ))
        cobro_id = cur.lastrowid
        conn.commit()
        conn.close()
        return cobro_id

    @staticmethod
    def actualizar(cobro):
        if cobro.id is None:
            raise ValueError("El cobro a modificar no tiene identificador.")
        if float(cobro.importe) <= 0:
            raise ValueError("El importe del cobro debe ser mayor que cero.")

        conn = conectar()
        cur = conn.cursor()
        cur.execute("""
            UPDATE cobros
            SET fecha=?, importe=?, forma_pago=?, comprobante=?, observaciones=?
            WHERE id=? AND cliente_id=?
        """, (
            cobro.fecha,
            cobro.importe,
            cobro.forma_pago,
            cobro.comprobante,
            cobro.observaciones,
            cobro.id,
            cobro.cliente_id,
        ))
        actualizado = cur.rowcount > 0
        conn.commit()
        conn.close()
        return actualizado

    @staticmethod
    def eliminar(cobro_id):
        conn = conectar()
        cur = conn.cursor()
        cur.execute("DELETE FROM cobros WHERE id=?", (cobro_id,))
        eliminado = cur.rowcount > 0
        conn.commit()
        conn.close()
        return eliminado

    @staticmethod
    def resumenes_cliente(cliente_id):
        conn = conectar()
        cur = conn.cursor()
        cur.execute("""
            SELECT id, numero, fecha, fecha_vencimiento, total, estado
            FROM resumenes
            WHERE cliente_id=?
            ORDER BY fecha DESC, numero DESC
        """, (cliente_id,))
        datos = cur.fetchall()
        conn.close()
        return datos

    @staticmethod
    def totales(cliente_id):
        conn = conectar()
        cur = conn.cursor()
        cur.execute(
            "SELECT COALESCE(SUM(total), 0) FROM resumenes WHERE cliente_id=?",
            (cliente_id,),
        )
        total_facturado = float(cur.fetchone()[0] or 0)
        cur.execute(
            "SELECT COALESCE(SUM(importe), 0) FROM cobros WHERE cliente_id=?",
            (cliente_id,),
        )
        total_cobrado = float(cur.fetchone()[0] or 0)
        conn.close()
        return {
            "total_facturado": total_facturado,
            "total_cobrado": total_cobrado,
            "saldo_pendiente": total_facturado - total_cobrado,
        }
