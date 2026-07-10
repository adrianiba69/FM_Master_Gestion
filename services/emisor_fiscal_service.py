import os

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
                observaciones,
                ambiente_arca,
                ruta_certificado,
                ruta_clave_privada,
                carpeta_facturas,
                configuracion_arca_completa
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
                observaciones,
                ambiente_arca,
                ruta_certificado,
                ruta_clave_privada,
                carpeta_facturas,
                configuracion_arca_completa
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
                observaciones,
                ambiente_arca,
                ruta_certificado,
                ruta_clave_privada,
                carpeta_facturas,
                configuracion_arca_completa
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
        ambiente_arca="Homologación",
        ruta_certificado="",
        ruta_clave_privada="",
        carpeta_facturas="",
        configuracion_arca_completa=0,
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
                observaciones,
                ambiente_arca,
                ruta_certificado,
                ruta_clave_privada,
                carpeta_facturas,
                configuracion_arca_completa
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
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
                ambiente_arca,
                ruta_certificado,
                ruta_clave_privada,
                carpeta_facturas,
                int(bool(configuracion_arca_completa)),
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
        ambiente_arca="Homologación",
        ruta_certificado="",
        ruta_clave_privada="",
        carpeta_facturas="",
        configuracion_arca_completa=0,
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
                observaciones=?,
                ambiente_arca=?,
                ruta_certificado=?,
                ruta_clave_privada=?,
                carpeta_facturas=?,
                configuracion_arca_completa=?
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
                ambiente_arca,
                ruta_certificado,
                ruta_clave_privada,
                carpeta_facturas,
                int(bool(configuracion_arca_completa)),
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

    @staticmethod
    def validar_configuracion_arca(emisor_id):
        resultado = {
            "completa": False,
            "faltantes": [],
            "errores": [],
        }

        emisor = EmisorFiscalService.obtener(emisor_id)
        if not emisor:
            resultado["errores"].append("Emisor fiscal no encontrado.")
            return resultado

        cuit = str(emisor[3] or "").strip() if len(emisor) > 3 else ""
        punto_venta = str(emisor[6] or "").strip() if len(emisor) > 6 else ""
        ambiente_arca = str(emisor[9] or "").strip() if len(emisor) > 9 else ""
        ruta_certificado = str(emisor[10] or "").strip() if len(emisor) > 10 else ""
        ruta_clave_privada = str(emisor[11] or "").strip() if len(emisor) > 11 else ""
        carpeta_facturas = str(emisor[12] or "").strip() if len(emisor) > 12 else ""

        if not cuit:
            resultado["faltantes"].append("Falta CUIT")
        if not punto_venta:
            resultado["faltantes"].append("Falta punto de venta")
        if ambiente_arca not in {"Homologación", "Producción"}:
            resultado["faltantes"].append("Falta ambiente ARCA")

        if not ruta_certificado:
            resultado["faltantes"].append("Falta ruta del certificado digital")
        elif not os.path.isfile(ruta_certificado):
            resultado["errores"].append("No existe el archivo del certificado digital.")

        if not ruta_clave_privada:
            resultado["faltantes"].append("Falta ruta de la clave privada")
        elif not os.path.isfile(ruta_clave_privada):
            resultado["errores"].append("No existe el archivo de la clave privada.")

        if not carpeta_facturas:
            resultado["faltantes"].append("Falta carpeta de facturas")
        elif not os.path.isdir(carpeta_facturas):
            resultado["errores"].append("No existe la carpeta de facturas.")

        resultado["completa"] = not resultado["faltantes"] and not resultado["errores"]
        return resultado
