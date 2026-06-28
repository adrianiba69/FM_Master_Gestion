from database import conectar


class ClienteService:

    @staticmethod
    def listar():

        conn = conectar()
        cur = conn.cursor()

        cur.execute("""
            SELECT
                id,
                codigo,
                COALESCE(NULLIF(razon_social, ''), nombre) AS razon_social,
                telefono,
                localidad,
                estado
            FROM clientes
            ORDER BY razon_social
        """)

        datos = cur.fetchall()

        conn.close()

        return datos

    @staticmethod
    def guardar(cliente):

        conn = conectar()
        cur = conn.cursor()

        cur.execute("""
            INSERT INTO clientes(
                nombre,
                codigo,
                razon_social,
                nombre_comercial,
                responsable,
                direccion,
                localidad,
                telefono,
                whatsapp,
                email,
                cuit,
                iva,
                vencimiento,
                estado,
                observaciones,
                fecha_alta,
                fecha_modificacion
            )
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            cliente.razon_social,
            cliente.codigo,
            cliente.razon_social,
            cliente.nombre_comercial,
            cliente.responsable,
            cliente.direccion,
            cliente.localidad,
            cliente.telefono,
            cliente.whatsapp,
            cliente.email,
            cliente.cuit,
            cliente.iva,
            cliente.vencimiento,
            cliente.estado,
            cliente.observaciones,
            cliente.fecha_alta,
            cliente.fecha_modificacion
        ))

        conn.commit()
        conn.close()

    @staticmethod
    def obtener(id_cliente):

        conn = conectar()
        cur = conn.cursor()

        cur.execute("""
            SELECT
                id,
                codigo,
                COALESCE(NULLIF(razon_social, ''), nombre) AS razon_social,
                nombre_comercial,
                responsable,
                direccion,
                localidad,
                telefono,
                whatsapp,
                email,
                cuit,
                iva,
                vencimiento,
                estado,
                observaciones,
                fecha_alta,
                fecha_modificacion
            FROM clientes
            WHERE id=?
        """, (id_cliente,))

        fila = cur.fetchone()
        conn.close()

        return fila

    @staticmethod
    def actualizar(cliente):

        conn = conectar()
        cur = conn.cursor()

        cur.execute("""
            UPDATE clientes
            SET
                nombre=?,
                codigo=?,
                razon_social=?,
                nombre_comercial=?,
                responsable=?,
                direccion=?,
                localidad=?,
                telefono=?,
                whatsapp=?,
                email=?,
                cuit=?,
                iva=?,
                vencimiento=?,
                estado=?,
                observaciones=?,
                fecha_modificacion=?
            WHERE id=?
        """, (
            cliente.razon_social,
            cliente.codigo,
            cliente.razon_social,
            cliente.nombre_comercial,
            cliente.responsable,
            cliente.direccion,
            cliente.localidad,
            cliente.telefono,
            cliente.whatsapp,
            cliente.email,
            cliente.cuit,
            cliente.iva,
            cliente.vencimiento,
            cliente.estado,
            cliente.observaciones,
            cliente.fecha_modificacion,
            cliente.id
        ))

        conn.commit()
        conn.close()

    @staticmethod
    def eliminar(id_cliente):

        conn = conectar()
        cur = conn.cursor()

        cur.execute(
            "DELETE FROM clientes WHERE id=?",
            (id_cliente,)
        )

        conn.commit()
        conn.close()

    @staticmethod
    def buscar(texto):

        conn = conectar()
        cur = conn.cursor()

        cur.execute("""
            SELECT
                id,
                codigo,
                COALESCE(NULLIF(razon_social, ''), nombre) AS razon_social,
                telefono,
                localidad,
                estado
            FROM clientes
            WHERE COALESCE(NULLIF(razon_social, ''), nombre) LIKE ?
            ORDER BY COALESCE(NULLIF(razon_social, ''), nombre)
        """, ('%' + texto + '%',))

        datos = cur.fetchall()

        conn.close()

        return datos
