from datetime import date, datetime

from database import conectar
from models.resumen import Resumen, ResumenConcepto


class ResumenService:

    @staticmethod
    def proximo_numero():
        conn = conectar()
        cur = conn.cursor()
        cur.execute("SELECT COALESCE(MAX(numero), 0) + 1 FROM resumenes")
        numero = cur.fetchone()[0]
        conn.close()
        return numero

    @staticmethod
    def calcular_vencimiento(cliente, fecha_emision=None):
        emision = fecha_emision or date.today()
        dia = int(cliente[12] or 1)
        dia = max(1, min(dia, 28))

        if dia >= emision.day:
            return emision.replace(day=dia)

        if emision.month == 12:
            return emision.replace(year=emision.year + 1, month=1, day=dia)
        return emision.replace(month=emision.month + 1, day=dia)

    @staticmethod
    def generar_desde_servicios(cliente_id, fecha=None, fecha_vencimiento=None):
        fecha_emision = fecha or date.today()
        if isinstance(fecha_emision, str):
            fecha_emision = datetime.strptime(fecha_emision, "%Y-%m-%d").date()

        conn = conectar()
        cur = conn.cursor()

        try:
            cur.execute("""
                SELECT
                    id, codigo,
                    COALESCE(NULLIF(razon_social, ''), nombre),
                    nombre_comercial, responsable, direccion, localidad,
                    telefono, whatsapp, email, cuit, iva, vencimiento,
                    estado, observaciones, fecha_alta, fecha_modificacion
                FROM clientes
                WHERE id=?
            """, (cliente_id,))
            cliente = cur.fetchone()
            if cliente is None:
                raise ValueError("No se encontro el cliente seleccionado.")

            cur.execute("""
                SELECT id, concepto, descripcion, cantidad, importe, descuento
                FROM servicios
                WHERE cliente_id=? AND activo=1
                ORDER BY concepto
            """, (cliente_id,))
            servicios = cur.fetchall()
            if not servicios:
                raise ValueError("El cliente no tiene servicios activos para resumir.")

            vencimiento = fecha_vencimiento
            if vencimiento is None:
                vencimiento = ResumenService.calcular_vencimiento(cliente, fecha_emision)
            if isinstance(vencimiento, str):
                vencimiento = datetime.strptime(vencimiento, "%Y-%m-%d").date()

            cur.execute("SELECT COALESCE(MAX(numero), 0) + 1 FROM resumenes")
            numero = cur.fetchone()[0]
            total = sum(
                (float(servicio[3] or 0) * float(servicio[4] or 0))
                - float(servicio[5] or 0)
                for servicio in servicios
            )

            cur.execute("""
                INSERT INTO resumenes(
                    numero, cliente_id, fecha, fecha_vencimiento, total,
                    saldo, estado, fecha_creacion
                ) VALUES(?,?,?,?,?,?,?,?)
            """, (
                numero,
                cliente_id,
                fecha_emision.isoformat(),
                vencimiento.isoformat(),
                total,
                total,
                "Pendiente",
                datetime.now().isoformat(timespec="seconds"),
            ))
            resumen_id = cur.lastrowid

            for servicio in servicios:
                cantidad = float(servicio[3] or 0)
                importe = float(servicio[4] or 0)
                descuento = float(servicio[5] or 0)
                subtotal = (cantidad * importe) - descuento
                cur.execute("""
                    INSERT INTO resumen_conceptos(
                        resumen_id, servicio_id, concepto, descripcion,
                        cantidad, importe, descuento, total
                    ) VALUES(?,?,?,?,?,?,?,?)
                """, (
                    resumen_id, servicio[0], servicio[1], servicio[2],
                    cantidad, importe, descuento, subtotal,
                ))

            conn.commit()
            return ResumenService.obtener(resumen_id)
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    @staticmethod
    def listar(cliente_id=None):
        conn = conectar()
        cur = conn.cursor()
        consulta = """
            SELECT r.id, r.numero, r.fecha, r.fecha_vencimiento,
                   COALESCE(NULLIF(c.razon_social, ''), c.nombre),
                   r.total, r.saldo, r.estado, r.pdf_path
            FROM resumenes r
            JOIN clientes c ON c.id = r.cliente_id
        """
        parametros = ()
        if cliente_id is not None:
            consulta += " WHERE r.cliente_id=?"
            parametros = (cliente_id,)
        consulta += " ORDER BY r.numero DESC"
        cur.execute(consulta, parametros)
        datos = cur.fetchall()
        conn.close()
        return datos

    @staticmethod
    def obtener(resumen_id):
        conn = conectar()
        cur = conn.cursor()
        cur.execute("""
            SELECT id, numero, cliente_id, fecha, fecha_vencimiento,
                   total, saldo, estado, pdf_path, fecha_creacion
            FROM resumenes WHERE id=?
        """, (resumen_id,))
        fila = cur.fetchone()
        if fila is None:
            conn.close()
            return None

        resumen = Resumen(*fila)
        cur.execute("""
            SELECT id, resumen_id, servicio_id, concepto, descripcion,
                   cantidad, importe, descuento, total
            FROM resumen_conceptos
            WHERE resumen_id=? ORDER BY id
        """, (resumen_id,))
        resumen.conceptos = [ResumenConcepto(*concepto) for concepto in cur.fetchall()]
        conn.close()
        return resumen

    @staticmethod
    def obtener_cliente(resumen_id):
        conn = conectar()
        cur = conn.cursor()
        cur.execute("""
            SELECT c.id, c.codigo,
                   COALESCE(NULLIF(c.razon_social, ''), c.nombre),
                   c.nombre_comercial, c.responsable, c.direccion,
                   c.localidad, c.telefono, c.email, c.cuit, c.iva
            FROM resumenes r
            JOIN clientes c ON c.id=r.cliente_id
            WHERE r.id=?
        """, (resumen_id,))
        cliente = cur.fetchone()
        conn.close()
        return cliente

    @staticmethod
    def actualizar_pdf_path(resumen_id, ruta):
        conn = conectar()
        cur = conn.cursor()
        cur.execute("UPDATE resumenes SET pdf_path=? WHERE id=?", (ruta, resumen_id))
        conn.commit()
        conn.close()
