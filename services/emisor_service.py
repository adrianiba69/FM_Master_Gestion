from database import conectar


class EmisorService:

    @staticmethod
    def listar(activos_solo=True):
        conn = conectar()
        cur = conn.cursor()
        if activos_solo:
            cur.execute(
                "SELECT id, alias, titular, nombre, cuit, condicion_iva, punto_venta, tipo_comprobante_default, orden_prioridad, direccion, localidad, telefono, email, activo, observaciones, certificado_path, clave_privada_path, arca_modo, arca_estado "
                "FROM emisores_facturacion WHERE activo=1 ORDER BY orden_prioridad, alias"
            )
        else:
            cur.execute(
                "SELECT id, alias, titular, nombre, cuit, condicion_iva, punto_venta, tipo_comprobante_default, orden_prioridad, direccion, localidad, telefono, email, activo, observaciones, certificado_path, clave_privada_path, arca_modo, arca_estado "
                "FROM emisores_facturacion ORDER BY orden_prioridad, alias"
            )
        filas = cur.fetchall()
        conn.close()
        return filas

    @staticmethod
    def obtener(id_):
        conn = conectar()
        cur = conn.cursor()
        cur.execute(
            "SELECT id, alias, titular, nombre, cuit, condicion_iva, punto_venta, tipo_comprobante_default, orden_prioridad, direccion, localidad, telefono, email, activo, observaciones, certificado_path, clave_privada_path, arca_modo, arca_estado "
            "FROM emisores_facturacion WHERE id=?",
            (id_,)
        )
        fila = cur.fetchone()
        conn.close()
        return fila

    @staticmethod
    def guardar(alias, titular, nombre, cuit, condicion_iva, punto_venta, tipo_comprobante_default, orden_prioridad, direccion, localidad, telefono, email, activo=1, observaciones="", certificado_path="", clave_privada_path="", arca_modo="Homologación", arca_estado="Desconocido"):
        conn = conectar()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO emisores_facturacion(alias, titular, nombre, cuit, condicion_iva, punto_venta, tipo_comprobante_default, orden_prioridad, direccion, localidad, telefono, email, activo, observaciones, certificado_path, clave_privada_path, arca_modo, arca_estado) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (alias, titular, nombre, cuit, condicion_iva, punto_venta, tipo_comprobante_default, orden_prioridad, direccion, localidad, telefono, email, activo, observaciones, certificado_path, clave_privada_path, arca_modo, arca_estado)
        )
        id_ = cur.lastrowid
        conn.commit()
        conn.close()
        return id_

    @staticmethod
    def actualizar(id_, alias, titular, nombre, cuit, condicion_iva, punto_venta, tipo_comprobante_default, orden_prioridad, direccion, localidad, telefono, email, activo=1, observaciones="", certificado_path="", clave_privada_path="", arca_modo="Homologación", arca_estado="Desconocido"):
        conn = conectar()
        cur = conn.cursor()
        cur.execute(
            "UPDATE emisores_facturacion SET alias=?, titular=?, nombre=?, cuit=?, condicion_iva=?, punto_venta=?, tipo_comprobante_default=?, orden_prioridad=?, direccion=?, localidad=?, telefono=?, email=?, activo=?, observaciones=?, certificado_path=?, clave_privada_path=?, arca_modo=?, arca_estado=? WHERE id=?",
            (alias, titular, nombre, cuit, condicion_iva, punto_venta, tipo_comprobante_default, orden_prioridad, direccion, localidad, telefono, email, activo, observaciones, certificado_path, clave_privada_path, arca_modo, arca_estado, id_)
        )
        conn.commit()
        conn.close()

    @staticmethod
    def recomendar_emisor_por_iva(iva):
        iva_text = (iva or "").strip().lower()
        emisores = EmisorService.listar(False)
        def es_monotributo(fila):
            return "monotributo" in (fila[5] or "").lower() or "monotributo" in (fila[1] or "").lower()
        def es_responsable(fila):
            return "responsable" in (fila[5] or "").lower() or "responsable" in (fila[1] or "").lower()

        if "responsable" in iva_text:
            for fila in emisores:
                if es_responsable(fila):
                    return fila[0]
            return emisores[0][0] if emisores else None

        if any(term in iva_text for term in ["monotributo", "consumidor final", "consumidor", "exento"]):
            for fila in emisores:
                if es_monotributo(fila):
                    return fila[0]
            return emisores[0][0] if emisores else None

        return emisores[0][0] if emisores else None

    @staticmethod
    def es_emisor_monotributo(emisor):
        if not emisor:
            return False
        return "monotributo" in (emisor[5] or "").lower() or "monotributo" in (emisor[1] or "").lower()

    @staticmethod
    def eliminar(id_):
        conn = conectar()
        cur = conn.cursor()
        cur.execute("DELETE FROM emisores_facturacion WHERE id=?", (id_,))
        conn.commit()
        conn.close()
