from datetime import date, datetime, timedelta

from database import conectar


class TareaService:
    TIPOS = (
        "Llamar cliente",
        "Renovar publicidad",
        "Cobrar",
        "Enviar resumen",
        "Reunión",
        "Visita",
        "Otro",
    )
    ESTADOS = ("Pendiente", "En proceso", "Completada", "Cancelada")
    PRIORIDADES = ("Baja", "Media", "Alta")

    @staticmethod
    def listar(filtro="Todas", cliente_id=None, texto=""):
        hoy = date.today()
        condiciones = []
        parametros = []

        if filtro == "Hoy":
            condiciones.append("t.fecha=?")
            parametros.append(hoy.isoformat())
        elif filtro == "Mañana":
            condiciones.append("t.fecha=?")
            parametros.append((hoy + timedelta(days=1)).isoformat())
        elif filtro == "Esta semana":
            inicio = hoy - timedelta(days=hoy.weekday())
            fin = inicio + timedelta(days=6)
            condiciones.append("t.fecha BETWEEN ? AND ?")
            parametros.extend((inicio.isoformat(), fin.isoformat()))
        elif filtro == "Vencidas":
            condiciones.append("""
                (t.fecha<? OR (t.fecha=? AND t.hora<?))
                AND t.estado NOT IN ('Completada', 'Cancelada')
            """)
            parametros.extend((hoy.isoformat(), hoy.isoformat(), datetime.now().strftime("%H:%M")))

        if cliente_id is not None:
            condiciones.append("t.cliente_id=?")
            parametros.append(cliente_id)
        if texto.strip():
            patron = f"%{texto.strip()}%"
            condiciones.append("""
                (t.titulo LIKE ? OR t.descripcion LIKE ? OR t.tipo LIKE ?
                 OR COALESCE(NULLIF(c.razon_social, ''), c.nombre) LIKE ?)
            """)
            parametros.extend((patron, patron, patron, patron))

        consulta = """
            SELECT
                t.id, t.cliente_id, t.fecha, t.hora, t.tipo, t.titulo,
                t.descripcion, t.estado, t.prioridad, t.fecha_creacion,
                COALESCE(NULLIF(c.razon_social, ''), c.nombre, 'Sin cliente')
            FROM tareas t
            LEFT JOIN clientes c ON c.id=t.cliente_id
        """
        if condiciones:
            consulta += " WHERE " + " AND ".join(f"({condicion})" for condicion in condiciones)
        consulta += " ORDER BY t.fecha, t.hora, t.id"

        conn = conectar()
        cur = conn.cursor()
        cur.execute(consulta, parametros)
        datos = cur.fetchall()
        conn.close()
        return datos

    @staticmethod
    def obtener(tarea_id):
        conn = conectar()
        cur = conn.cursor()
        cur.execute("""
            SELECT id, cliente_id, fecha, hora, tipo, titulo, descripcion,
                   estado, prioridad, fecha_creacion
            FROM tareas WHERE id=?
        """, (tarea_id,))
        fila = cur.fetchone()
        conn.close()
        return fila

    @staticmethod
    def guardar(tarea):
        TareaService.validar(tarea)
        conn = conectar()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO tareas(
                cliente_id, fecha, hora, tipo, titulo, descripcion,
                estado, prioridad, fecha_creacion
            ) VALUES(?,?,?,?,?,?,?,?,?)
        """, (
            tarea.cliente_id, tarea.fecha, tarea.hora, tarea.tipo,
            tarea.titulo, tarea.descripcion, tarea.estado, tarea.prioridad,
            tarea.fecha_creacion or datetime.now().isoformat(timespec="seconds"),
        ))
        tarea_id = cur.lastrowid
        conn.commit()
        conn.close()
        return tarea_id

    @staticmethod
    def actualizar(tarea):
        TareaService.validar(tarea)
        conn = conectar()
        cur = conn.cursor()
        cur.execute("""
            UPDATE tareas
            SET cliente_id=?, fecha=?, hora=?, tipo=?, titulo=?,
                descripcion=?, estado=?, prioridad=?
            WHERE id=?
        """, (
            tarea.cliente_id, tarea.fecha, tarea.hora, tarea.tipo,
            tarea.titulo, tarea.descripcion, tarea.estado, tarea.prioridad,
            tarea.id,
        ))
        actualizado = cur.rowcount > 0
        conn.commit()
        conn.close()
        return actualizado

    @staticmethod
    def eliminar(tarea_id):
        conn = conectar()
        cur = conn.cursor()
        cur.execute("DELETE FROM tareas WHERE id=?", (tarea_id,))
        eliminado = cur.rowcount > 0
        conn.commit()
        conn.close()
        return eliminado

    @staticmethod
    def marcar_completada(tarea_id):
        conn = conectar()
        cur = conn.cursor()
        cur.execute("UPDATE tareas SET estado='Completada' WHERE id=?", (tarea_id,))
        actualizado = cur.rowcount > 0
        conn.commit()
        conn.close()
        return actualizado

    @staticmethod
    def resumen_dashboard():
        hoy = date.today().isoformat()
        ahora = datetime.now().strftime("%H:%M")
        conn = conectar()
        cur = conn.cursor()
        cur.execute("""
            SELECT COUNT(*) FROM tareas
            WHERE fecha=? AND estado IN ('Pendiente', 'En proceso')
        """, (hoy,))
        pendientes_hoy = cur.fetchone()[0]
        cur.execute("""
            SELECT COUNT(*) FROM tareas
            WHERE (fecha<? OR (fecha=? AND hora<?))
              AND estado IN ('Pendiente', 'En proceso')
        """, (hoy, hoy, ahora))
        vencidas = cur.fetchone()[0]
        cur.execute("""
            SELECT COUNT(*) FROM tareas
            WHERE fecha=? AND estado='Completada'
        """, (hoy,))
        completadas_hoy = cur.fetchone()[0]
        cur.execute("""
            SELECT hora, titulo FROM tareas
            WHERE (fecha>? OR (fecha=? AND hora>=?))
              AND estado IN ('Pendiente', 'En proceso')
            ORDER BY fecha, hora LIMIT 1
        """, (hoy, hoy, ahora))
        proxima = cur.fetchone()
        conn.close()
        return {
            "pendientes_hoy": pendientes_hoy,
            "vencidas": vencidas,
            "completadas_hoy": completadas_hoy,
            "proxima": f"{proxima[0]} - {proxima[1]}" if proxima else "Sin tareas próximas",
        }

    @staticmethod
    def validar(tarea):
        if not tarea.titulo.strip():
            raise ValueError("El título de la tarea es obligatorio.")
        try:
            datetime.strptime(tarea.fecha, "%Y-%m-%d")
            datetime.strptime(tarea.hora, "%H:%M")
        except ValueError as error:
            raise ValueError("La fecha o la hora no tienen un formato válido.") from error
        if tarea.tipo not in TareaService.TIPOS:
            raise ValueError("El tipo de tarea no es válido.")
        if tarea.estado not in TareaService.ESTADOS:
            raise ValueError("El estado de la tarea no es válido.")
        if tarea.prioridad not in TareaService.PRIORIDADES:
            raise ValueError("La prioridad de la tarea no es válida.")
