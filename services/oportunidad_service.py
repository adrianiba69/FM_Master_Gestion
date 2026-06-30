from datetime import date, datetime, timedelta

from database import conectar


class OportunidadService:
    ESTADOS = (
        "Nueva", "Contactado", "Presupuesto enviado",
        "En negociación", "Ganada", "Perdida",
    )
    ORIGENES = (
        "Referido", "WhatsApp", "Redes sociales", "Web",
        "Llamada", "Email", "Visita", "Otro",
    )
    FILTROS_CONTACTO = ("Todos", "Hoy", "Atrasadas", "Esta semana", "Sin fecha")

    @staticmethod
    def listar(texto="", estado="Todos", proximo="Todos"):
        condiciones, parametros = [], []
        if texto.strip():
            patron = f"%{texto.strip()}%"
            condiciones.append("""
                (o.nombre_potencial LIKE ? OR o.telefono LIKE ? OR
                 o.whatsapp LIKE ? OR o.email LIKE ? OR o.servicio_interes LIKE ? OR
                 COALESCE(NULLIF(c.razon_social, ''), c.nombre, '') LIKE ?)
            """)
            parametros.extend((patron,) * 6)
        if estado and estado != "Todos":
            condiciones.append("o.estado=?")
            parametros.append(estado)
        OportunidadService._agregar_filtro_contacto(condiciones, parametros, proximo)
        consulta = """
            SELECT o.id, o.cliente_id, o.nombre_potencial, o.telefono,
                   o.whatsapp, o.email, o.fecha, o.origen, o.servicio_interes,
                   o.importe_estimado, o.probabilidad, o.estado,
                   o.proximo_contacto, o.observaciones, o.creado,
                   COALESCE(NULLIF(c.razon_social, ''), c.nombre, '')
            FROM oportunidades o LEFT JOIN clientes c ON c.id=o.cliente_id
        """
        if condiciones:
            consulta += " WHERE " + " AND ".join(f"({x})" for x in condiciones)
        consulta += " ORDER BY CASE WHEN o.proximo_contacto IS NULL OR o.proximo_contacto='' THEN 1 ELSE 0 END, o.proximo_contacto, o.fecha DESC, o.id DESC"
        conn = conectar()
        cur = conn.cursor()
        cur.execute(consulta, parametros)
        filas = cur.fetchall()
        conn.close()
        return filas

    @staticmethod
    def obtener(oportunidad_id):
        conn = conectar()
        cur = conn.cursor()
        cur.execute("""
            SELECT id, cliente_id, nombre_potencial, telefono, whatsapp,
                   email, fecha, origen, servicio_interes, importe_estimado,
                   probabilidad, estado, proximo_contacto, observaciones, creado
            FROM oportunidades WHERE id=?
        """, (oportunidad_id,))
        fila = cur.fetchone()
        conn.close()
        return fila

    @staticmethod
    def guardar(oportunidad):
        OportunidadService.validar(oportunidad)
        conn = conectar()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO oportunidades(
                cliente_id, nombre_potencial, telefono, whatsapp, email,
                fecha, origen, servicio_interes, importe_estimado,
                probabilidad, estado, proximo_contacto, observaciones, creado
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            oportunidad.cliente_id, oportunidad.nombre_potencial,
            oportunidad.telefono, oportunidad.whatsapp, oportunidad.email,
            oportunidad.fecha, oportunidad.origen, oportunidad.servicio_interes,
            oportunidad.importe_estimado, oportunidad.probabilidad,
            oportunidad.estado, oportunidad.proximo_contacto or None,
            oportunidad.observaciones,
            oportunidad.creado or datetime.now().isoformat(timespec="seconds"),
        ))
        oportunidad_id = cur.lastrowid
        conn.commit()
        conn.close()
        return oportunidad_id

    @staticmethod
    def actualizar(oportunidad):
        OportunidadService.validar(oportunidad)
        conn = conectar()
        cur = conn.cursor()
        cur.execute("""
            UPDATE oportunidades SET cliente_id=?, nombre_potencial=?,
                telefono=?, whatsapp=?, email=?, fecha=?, origen=?,
                servicio_interes=?, importe_estimado=?, probabilidad=?,
                estado=?, proximo_contacto=?, observaciones=? WHERE id=?
        """, (
            oportunidad.cliente_id, oportunidad.nombre_potencial,
            oportunidad.telefono, oportunidad.whatsapp, oportunidad.email,
            oportunidad.fecha, oportunidad.origen, oportunidad.servicio_interes,
            oportunidad.importe_estimado, oportunidad.probabilidad,
            oportunidad.estado, oportunidad.proximo_contacto or None,
            oportunidad.observaciones, oportunidad.id,
        ))
        actualizado = cur.rowcount > 0
        conn.commit()
        conn.close()
        return actualizado

    @staticmethod
    def eliminar(oportunidad_id):
        conn = conectar()
        cur = conn.cursor()
        cur.execute("DELETE FROM oportunidades WHERE id=?", (oportunidad_id,))
        eliminado = cur.rowcount > 0
        conn.commit()
        conn.close()
        return eliminado

    @staticmethod
    def metricas(texto="", estado="Todos", proximo="Todos"):
        filas = OportunidadService.listar(texto, estado, proximo)
        importes = [float(fila[9] or 0) for fila in filas]
        probabilidades = [float(fila[10] or 0) for fila in filas]
        return {
            "cantidad": len(filas),
            "importe_total": sum(importes),
            "probabilidad_promedio": (
                sum(probabilidades) / len(probabilidades) if probabilidades else 0
            ),
        }

    @staticmethod
    def resumen_dashboard():
        hoy = date.today()
        inicio_mes = hoy.replace(day=1)
        if inicio_mes.month == 12:
            fin_mes = inicio_mes.replace(year=inicio_mes.year + 1, month=1)
        else:
            fin_mes = inicio_mes.replace(month=inicio_mes.month + 1)
        conn = conectar()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM oportunidades WHERE estado='Nueva'")
        nuevas = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM oportunidades WHERE estado='En negociación'")
        negociacion = cur.fetchone()[0]
        cur.execute("""
            SELECT COUNT(*) FROM oportunidades
            WHERE estado='Ganada' AND fecha>=? AND fecha<?
        """, (inicio_mes.isoformat(), fin_mes.isoformat()))
        ganadas_mes = cur.fetchone()[0]
        cur.execute("""
            SELECT COALESCE(SUM(importe_estimado), 0) FROM oportunidades
            WHERE estado NOT IN ('Ganada', 'Perdida')
        """)
        importe = float(cur.fetchone()[0] or 0)
        conn.close()
        return {
            "nuevas": nuevas, "negociacion": negociacion,
            "ganadas_mes": ganadas_mes, "importe_estimado": importe,
        }

    @staticmethod
    def validar(oportunidad):
        if not oportunidad.cliente_id and not oportunidad.nombre_potencial.strip():
            raise ValueError("Indique un cliente o un nombre potencial.")
        try:
            datetime.strptime(oportunidad.fecha, "%Y-%m-%d")
            if oportunidad.proximo_contacto:
                datetime.strptime(oportunidad.proximo_contacto, "%Y-%m-%d")
        except ValueError as error:
            raise ValueError("Las fechas no tienen un formato válido.") from error
        if oportunidad.estado not in OportunidadService.ESTADOS:
            raise ValueError("El estado no es válido.")
        if not 0 <= float(oportunidad.probabilidad) <= 100:
            raise ValueError("La probabilidad debe estar entre 0 y 100.")
        if float(oportunidad.importe_estimado) < 0:
            raise ValueError("El importe estimado no puede ser negativo.")

    @staticmethod
    def _agregar_filtro_contacto(condiciones, parametros, filtro):
        hoy = date.today()
        if filtro == "Hoy":
            condiciones.append("o.proximo_contacto=?")
            parametros.append(hoy.isoformat())
        elif filtro == "Atrasadas":
            condiciones.append("o.proximo_contacto<?")
            parametros.append(hoy.isoformat())
        elif filtro == "Esta semana":
            fin = hoy + timedelta(days=6 - hoy.weekday())
            condiciones.append("o.proximo_contacto BETWEEN ? AND ?")
            parametros.extend((hoy.isoformat(), fin.isoformat()))
        elif filtro == "Sin fecha":
            condiciones.append("COALESCE(o.proximo_contacto, '')='' ")
