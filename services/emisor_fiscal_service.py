from database import conectar


class EmisorFiscalService:

    @staticmethod
    def etiqueta_visible(emisor):
        if not emisor:
            return "No aplica"
        nombre_fantasia = (emisor[2] or "").strip()
        razon_social = (emisor[1] or "").strip()
        return nombre_fantasia or razon_social or "No aplica"

    @staticmethod
    def listar_activos_ordenados_por_id():
        emisores = EmisorFiscalService.listar_activos()
        return sorted(emisores, key=lambda fila: fila[0] or 0)

    @staticmethod
    def resolver_etiqueta(valor):
        texto = (valor or "").strip()
        if not texto or texto == "No aplica":
            return "No aplica"

        if texto.startswith("EMISOR:"):
            try:
                emisor_id = int(texto.split(":", 1)[1])
            except ValueError:
                return texto
            emisor = EmisorFiscalService.obtener(emisor_id)
            return EmisorFiscalService.etiqueta_visible(emisor)

        if texto in ("Monotributo 1", "Monotributo 2"):
            indice = 0 if texto.endswith("1") else 1
            emisores = EmisorFiscalService.listar_activos_ordenados_por_id()
            if len(emisores) > indice:
                return EmisorFiscalService.etiqueta_visible(emisores[indice])
            return "No aplica"

        emisores = EmisorFiscalService.listar()
        for emisor in emisores:
            if texto == EmisorFiscalService.etiqueta_visible(emisor):
                return texto
        return texto

    @staticmethod
    def codificar_seleccion(valor):
        texto = (valor or "").strip()
        if not texto or texto == "No aplica":
            return "No aplica"

        if texto.startswith("EMISOR:"):
            return texto

        emisores = EmisorFiscalService.listar()
        for emisor in emisores:
            if texto == EmisorFiscalService.etiqueta_visible(emisor):
                return f"EMISOR:{emisor[0]}"

        return texto

    @staticmethod
    def listar():
        conn = conectar()
        cur = conn.cursor()
        cur.execute(
            """
            SELECT
                id,
                razon_social,
                nombre_fantasia,
                cuit,
                condicion_iva,
                tipo_factura,
                punto_venta,
                activo,
                observaciones
            FROM emisores_fiscales
            ORDER BY
                CASE WHEN activo=1 THEN 0 ELSE 1 END,
                COALESCE(NULLIF(nombre_fantasia, ''), razon_social)
            """
        )
        filas = cur.fetchall()
        conn.close()
        return filas

    @staticmethod
    def listar_activos():
        conn = conectar()
        cur = conn.cursor()
        cur.execute(
            """
            SELECT
                id,
                razon_social,
                nombre_fantasia,
                cuit,
                condicion_iva,
                tipo_factura,
                punto_venta,
                activo,
                observaciones
            FROM emisores_fiscales
            WHERE activo=1
            ORDER BY COALESCE(NULLIF(nombre_fantasia, ''), razon_social)
            """
        )
        filas = cur.fetchall()
        conn.close()
        return filas

    @staticmethod
    def obtener(id_):
        conn = conectar()
        cur = conn.cursor()
        cur.execute(
            """
            SELECT
                id,
                razon_social,
                nombre_fantasia,
                cuit,
                condicion_iva,
                tipo_factura,
                punto_venta,
                activo,
                observaciones
            FROM emisores_fiscales
            WHERE id=?
            """,
            (id_,),
        )
        fila = cur.fetchone()
        conn.close()
        return fila

    @staticmethod
    def guardar(
        razon_social,
        nombre_fantasia,
        cuit,
        condicion_iva,
        tipo_factura,
        punto_venta,
        activo=1,
        observaciones="",
    ):
        conn = conectar()
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO emisores_fiscales(
                razon_social,
                nombre_fantasia,
                cuit,
                condicion_iva,
                tipo_factura,
                punto_venta,
                activo,
                observaciones
            ) VALUES(?,?,?,?,?,?,?,?)
            """,
            (
                razon_social,
                nombre_fantasia,
                cuit,
                condicion_iva,
                tipo_factura,
                punto_venta,
                activo,
                observaciones,
            ),
        )
        emisor_id = cur.lastrowid
        conn.commit()
        conn.close()
        return emisor_id

    @staticmethod
    def actualizar(
        id_,
        razon_social,
        nombre_fantasia,
        cuit,
        condicion_iva,
        tipo_factura,
        punto_venta,
        activo=1,
        observaciones="",
    ):
        conn = conectar()
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE emisores_fiscales
            SET razon_social=?,
                nombre_fantasia=?,
                cuit=?,
                condicion_iva=?,
                tipo_factura=?,
                punto_venta=?,
                activo=?,
                observaciones=?
            WHERE id=?
            """,
            (
                razon_social,
                nombre_fantasia,
                cuit,
                condicion_iva,
                tipo_factura,
                punto_venta,
                activo,
                observaciones,
                id_,
            ),
        )
        conn.commit()
        conn.close()

    @staticmethod
    def cambiar_estado(id_, activo):
        conn = conectar()
        cur = conn.cursor()
        cur.execute(
            "UPDATE emisores_fiscales SET activo=? WHERE id=?",
            (1 if activo else 0, id_),
        )
        conn.commit()
        conn.close()
