from database import conectar


class ServicioService:

    @staticmethod
    def listar(cliente_id):
        conn = conectar()
        cur = conn.cursor()

        cur.execute("""
            SELECT
                id,
                cliente_id,
                concepto,
                descripcion,
                cantidad,
                importe,
                descuento,
                activo,
                (cantidad * importe) - descuento AS total
            FROM servicios
            WHERE cliente_id=?
            ORDER BY concepto
        """, (cliente_id,))

        datos = cur.fetchall()
        conn.close()
        return datos

    @staticmethod
    def obtener(id_servicio):
        conn = conectar()
        cur = conn.cursor()

        cur.execute("""
            SELECT
                id,
                cliente_id,
                concepto,
                descripcion,
                cantidad,
                importe,
                descuento,
                activo
            FROM servicios
            WHERE id=?
        """, (id_servicio,))

        fila = cur.fetchone()
        conn.close()
        return fila

    @staticmethod
    def guardar(servicio):
        conn = conectar()
        cur = conn.cursor()

        cur.execute("""
            INSERT INTO servicios(
                cliente_id,
                concepto,
                descripcion,
                cantidad,
                importe,
                descuento,
                activo
            )
            VALUES(?,?,?,?,?,?,?)
        """, (
            servicio.cliente_id,
            servicio.concepto,
            servicio.descripcion,
            servicio.cantidad,
            servicio.importe,
            servicio.descuento,
            servicio.activo,
        ))

        conn.commit()
        servicio_id = cur.lastrowid
        conn.close()
        return servicio_id

    @staticmethod
    def actualizar(servicio):
        conn = conectar()
        cur = conn.cursor()

        cur.execute("""
            UPDATE servicios
            SET
                concepto=?,
                descripcion=?,
                cantidad=?,
                importe=?,
                descuento=?,
                activo=?
            WHERE id=?
        """, (
            servicio.concepto,
            servicio.descripcion,
            servicio.cantidad,
            servicio.importe,
            servicio.descuento,
            servicio.activo,
            servicio.id,
        ))

        conn.commit()
        conn.close()

    @staticmethod
    def eliminar(id_servicio):
        conn = conectar()
        cur = conn.cursor()

        cur.execute("DELETE FROM servicios WHERE id=?", (id_servicio,))

        conn.commit()
        conn.close()

    @staticmethod
    def total_cliente(cliente_id):
        conn = conectar()
        cur = conn.cursor()

        cur.execute("""
            SELECT IFNULL(SUM((cantidad * importe) - descuento), 0)
            FROM servicios
            WHERE cliente_id=?
            AND activo=1
        """, (cliente_id,))

        total = cur.fetchone()[0]
        conn.close()
        return total
