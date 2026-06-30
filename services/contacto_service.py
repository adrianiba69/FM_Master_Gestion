from datetime import date, datetime, timedelta

from database import conectar


class ContactoService:
    TIPOS = (
        "Llamada", "WhatsApp", "Email", "Visita", "Reunión",
        "Renovación", "Cobro", "Otro",
    )
    RESULTADOS = (
        "Pendiente", "Interesado", "Confirmado", "Sin respuesta",
        "Rechazó", "Vendido",
    )

    @staticmethod
    def listar(cliente_id=None, fecha="", tipo="Todos", resultado="Todos", cliente=""):
        condiciones, parametros = [], []
        if cliente_id is not None:
            condiciones.append("co.cliente_id=?")
            parametros.append(cliente_id)
        elif cliente.strip():
            condiciones.append("COALESCE(NULLIF(cl.razon_social, ''), cl.nombre) LIKE ?")
            parametros.append(f"%{cliente.strip()}%")
        if fecha:
            condiciones.append("co.fecha=?")
            parametros.append(fecha)
        if tipo and tipo != "Todos":
            condiciones.append("co.tipo=?")
            parametros.append(tipo)
        if resultado and resultado != "Todos":
            condiciones.append("co.resultado=?")
            parametros.append(resultado)
        consulta = """
            SELECT co.id, co.cliente_id, co.fecha, co.hora, co.tipo,
                   co.resultado, co.observaciones, co.proximo_contacto,
                   co.vendedor, co.creado,
                   COALESCE(NULLIF(cl.razon_social, ''), cl.nombre, 'Sin cliente')
            FROM contactos co JOIN clientes cl ON cl.id=co.cliente_id
        """
        if condiciones:
            consulta += " WHERE " + " AND ".join(condiciones)
        consulta += " ORDER BY co.fecha DESC, co.hora DESC, co.id DESC"
        conn = conectar()
        cur = conn.cursor()
        cur.execute(consulta, parametros)
        filas = cur.fetchall()
        conn.close()
        return filas

    @staticmethod
    def obtener(contacto_id):
        conn = conectar()
        cur = conn.cursor()
        cur.execute("""
            SELECT id, cliente_id, fecha, hora, tipo, resultado,
                   observaciones, proximo_contacto, vendedor, creado
            FROM contactos WHERE id=?
        """, (contacto_id,))
        fila = cur.fetchone()
        conn.close()
        return fila

    @staticmethod
    def guardar(contacto):
        ContactoService.validar(contacto)
        conn = conectar()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO contactos(
                cliente_id, fecha, hora, tipo, resultado, observaciones,
                proximo_contacto, vendedor, creado
            ) VALUES(?,?,?,?,?,?,?,?,?)
        """, (
            contacto.cliente_id, contacto.fecha, contacto.hora, contacto.tipo,
            contacto.resultado, contacto.observaciones,
            contacto.proximo_contacto or None, contacto.vendedor,
            contacto.creado or datetime.now().isoformat(timespec="seconds"),
        ))
        contacto_id = cur.lastrowid
        conn.commit()
        conn.close()
        return contacto_id

    @staticmethod
    def actualizar(contacto):
        ContactoService.validar(contacto)
        conn = conectar()
        cur = conn.cursor()
        cur.execute("""
            UPDATE contactos SET cliente_id=?, fecha=?, hora=?, tipo=?,
                resultado=?, observaciones=?, proximo_contacto=?, vendedor=?
            WHERE id=?
        """, (
            contacto.cliente_id, contacto.fecha, contacto.hora, contacto.tipo,
            contacto.resultado, contacto.observaciones,
            contacto.proximo_contacto or None, contacto.vendedor, contacto.id,
        ))
        actualizado = cur.rowcount > 0
        conn.commit()
        conn.close()
        return actualizado

    @staticmethod
    def eliminar(contacto_id):
        conn = conectar()
        cur = conn.cursor()
        cur.execute("DELETE FROM contactos WHERE id=?", (contacto_id,))
        eliminado = cur.rowcount > 0
        conn.commit()
        conn.close()
        return eliminado

    @staticmethod
    def resumen_cliente(cliente_id):
        hoy = date.today().isoformat()
        conn = conectar()
        cur = conn.cursor()
        cur.execute("""
            SELECT fecha, hora, tipo, resultado FROM contactos
            WHERE cliente_id=? ORDER BY fecha DESC, hora DESC, id DESC LIMIT 1
        """, (cliente_id,))
        ultimo = cur.fetchone()
        cur.execute("""
            SELECT proximo_contacto FROM contactos
            WHERE cliente_id=? AND proximo_contacto>=?
            ORDER BY proximo_contacto LIMIT 1
        """, (cliente_id, hoy))
        proximo = cur.fetchone()
        cur.execute("""
            SELECT COUNT(*), SUM(CASE WHEN resultado='Vendido' THEN 1 ELSE 0 END)
            FROM contactos WHERE cliente_id=?
        """, (cliente_id,))
        cantidad, ventas = cur.fetchone()
        cur.execute("""
            SELECT COALESCE(SUM(total), 0), COALESCE(SUM(saldo), 0)
            FROM resumenes WHERE cliente_id=?
        """, (cliente_id,))
        facturacion, saldo = cur.fetchone()
        conn.close()
        return {
            "ultimo": ultimo, "proximo": proximo[0] if proximo else "",
            "cantidad": cantidad or 0, "ventas": ventas or 0,
            "facturacion": float(facturacion or 0), "saldo": float(saldo or 0),
        }

    @staticmethod
    def resumen_dashboard():
        hoy = date.today()
        fin_semana = hoy + timedelta(days=6 - hoy.weekday())
        conn = conectar()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM contactos WHERE proximo_contacto=?", (hoy.isoformat(),))
        hoy_total = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM contactos WHERE proximo_contacto<?", (hoy.isoformat(),))
        atrasados = cur.fetchone()[0]
        cur.execute("""
            SELECT COUNT(*) FROM contactos
            WHERE proximo_contacto>=? AND proximo_contacto<=?
        """, (hoy.isoformat(), fin_semana.isoformat()))
        semana = cur.fetchone()[0]
        conn.close()
        return {"hoy": hoy_total, "atrasados": atrasados, "semana": semana}

    @staticmethod
    def semaforo_cliente(cliente_id):
        conn = conectar()
        cur = conn.cursor()
        cur.execute("""
            SELECT estado, fecha_alta,
                   (SELECT MAX(fecha) FROM contactos WHERE cliente_id=clientes.id)
            FROM clientes WHERE id=?
        """, (cliente_id,))
        fila = cur.fetchone()
        conn.close()
        if not fila:
            return "Rojo"
        estado, fecha_alta, ultimo = fila
        referencia = ContactoService._convertir_fecha(ultimo)
        if referencia is None:
            referencia = ContactoService._convertir_fecha(fecha_alta)
        dias = (date.today() - referencia).days if referencia else 9999
        if dias > 90 or str(estado or "").strip().lower() != "activo":
            return "Rojo"
        if dias > 30:
            return "Amarillo"
        return "Verde"

    @staticmethod
    def validar(contacto):
        if not contacto.cliente_id:
            raise ValueError("Debe seleccionar un cliente.")
        try:
            datetime.strptime(contacto.fecha, "%Y-%m-%d")
            datetime.strptime(contacto.hora, "%H:%M")
            if contacto.proximo_contacto:
                datetime.strptime(contacto.proximo_contacto, "%Y-%m-%d")
        except ValueError as error:
            raise ValueError("La fecha o la hora no tienen un formato válido.") from error
        if contacto.tipo not in ContactoService.TIPOS:
            raise ValueError("El tipo de contacto no es válido.")
        if contacto.resultado not in ContactoService.RESULTADOS:
            raise ValueError("El resultado no es válido.")

    @staticmethod
    def _convertir_fecha(valor):
        for formato in ("%Y-%m-%d", "%d/%m/%Y"):
            try:
                return datetime.strptime(valor or "", formato).date()
            except ValueError:
                pass
        return None
