from datetime import date, datetime, timedelta

from database import conectar
from services.backup_service import BackupService


class NotificacionService:
    TIPOS = (
        "Servicio vencido", "Servicio próximo a vencer", "Resumen pendiente",
        "Cobro vencido", "Cliente con deuda", "Contacto pendiente",
        "Oportunidad pendiente", "Backup pendiente", "Otro",
    )
    ESTADOS = ("Pendiente", "Leída", "Resuelta", "Descartada")
    PRIORIDADES = ("Baja", "Media", "Alta", "Urgente")

    @classmethod
    def generar_automaticas(cls):
        hoy = date.today()
        limite = hoy + timedelta(days=7)
        conn = conectar()
        cur = conn.cursor()
        alertas = []

        cur.execute("""
            SELECT s.id, s.concepto, s.fecha_fin,
                   COALESCE(NULLIF(c.razon_social,''), c.nombre, 'Cliente')
            FROM servicios s JOIN clientes c ON c.id=s.cliente_id
            WHERE s.activo=1 AND s.fecha_fin<?
        """, (hoy.isoformat(),))
        for servicio_id, concepto, vencimiento, cliente in cur.fetchall():
            alertas.append(cls._alerta(
                f"servicio_vencido:{servicio_id}", "Servicio vencido",
                f"Servicio vencido: {concepto or 'Sin concepto'}",
                f"{cliente} · venció el {cls._mostrar_fecha(vencimiento)}",
                "Urgente", vencimiento, "servicio", servicio_id,
            ))

        cur.execute("""
            SELECT s.id, s.concepto, s.fecha_fin,
                   COALESCE(NULLIF(c.razon_social,''), c.nombre, 'Cliente')
            FROM servicios s JOIN clientes c ON c.id=s.cliente_id
            WHERE s.activo=1 AND s.fecha_fin>=? AND s.fecha_fin<=?
        """, (hoy.isoformat(), limite.isoformat()))
        for servicio_id, concepto, vencimiento, cliente in cur.fetchall():
            alertas.append(cls._alerta(
                f"servicio_proximo:{servicio_id}", "Servicio próximo a vencer",
                f"Próximo vencimiento: {concepto or 'Sin concepto'}",
                f"{cliente} · vence el {cls._mostrar_fecha(vencimiento)}",
                "Alta", vencimiento, "servicio", servicio_id,
            ))

        cur.execute("""
            SELECT r.id, r.numero, r.fecha_vencimiento, r.saldo,
                   COALESCE(NULLIF(c.razon_social,''), c.nombre, 'Cliente')
            FROM resumenes r JOIN clientes c ON c.id=r.cliente_id
            WHERE r.saldo>0 AND LOWER(COALESCE(r.estado,''))!='pagado'
        """)
        resumenes = cur.fetchall()
        for resumen_id, numero, vencimiento, saldo, cliente in resumenes:
            alertas.append(cls._alerta(
                f"resumen_pendiente:{resumen_id}", "Resumen pendiente",
                f"Resumen pendiente #{int(numero):06d}",
                f"{cliente} · saldo {cls._moneda(saldo)}",
                "Media", vencimiento, "resumen", resumen_id,
            ))
            if vencimiento and vencimiento < hoy.isoformat():
                alertas.append(cls._alerta(
                    f"cobro_vencido:{resumen_id}", "Cobro vencido",
                    f"Cobro vencido del resumen #{int(numero):06d}",
                    f"{cliente} · saldo {cls._moneda(saldo)}",
                    "Urgente", vencimiento, "resumen", resumen_id,
                ))

        cur.execute("""
            SELECT c.id, COALESCE(NULLIF(c.razon_social,''), c.nombre, 'Cliente'),
                   COALESCE(SUM(r.saldo),0)
            FROM clientes c JOIN resumenes r ON r.cliente_id=c.id
            WHERE r.saldo>0 GROUP BY c.id HAVING SUM(r.saldo)>0
        """)
        for cliente_id, cliente, deuda in cur.fetchall():
            alertas.append(cls._alerta(
                f"cliente_deuda:{cliente_id}", "Cliente con deuda",
                f"Cliente con deuda: {cliente}", f"Saldo pendiente {cls._moneda(deuda)}",
                "Alta", hoy.isoformat(), "cliente", cliente_id,
            ))

        cur.execute("""
            SELECT co.id, co.proximo_contacto,
                   COALESCE(NULLIF(c.razon_social,''), c.nombre, 'Cliente')
            FROM contactos co JOIN clientes c ON c.id=co.cliente_id
            WHERE co.proximo_contacto IS NOT NULL AND co.proximo_contacto!=''
              AND co.proximo_contacto<=?
        """, (hoy.isoformat(),))
        for contacto_id, vencimiento, cliente in cur.fetchall():
            prioridad = "Urgente" if vencimiento < hoy.isoformat() else "Alta"
            alertas.append(cls._alerta(
                f"contacto_pendiente:{contacto_id}", "Contacto pendiente",
                f"Contacto pendiente: {cliente}",
                f"Programado para {cls._mostrar_fecha(vencimiento)}",
                prioridad, vencimiento, "contacto", contacto_id,
            ))

        cur.execute("""
            SELECT id, COALESCE(NULLIF(nombre_potencial,''), 'Oportunidad'),
                   proximo_contacto, estado
            FROM oportunidades
            WHERE estado NOT IN ('Ganada','Perdida')
              AND proximo_contacto IS NOT NULL AND proximo_contacto!=''
              AND proximo_contacto<=?
        """, (hoy.isoformat(),))
        for oportunidad_id, nombre, vencimiento, estado in cur.fetchall():
            prioridad = "Urgente" if vencimiento < hoy.isoformat() else "Alta"
            alertas.append(cls._alerta(
                f"oportunidad_pendiente:{oportunidad_id}", "Oportunidad pendiente",
                f"Seguimiento de oportunidad: {nombre}",
                f"Estado {estado} · contacto {cls._mostrar_fecha(vencimiento)}",
                prioridad, vencimiento, "oportunidad", oportunidad_id,
            ))

        if not BackupService.existe_backup_del_dia(hoy):
            alertas.append(cls._alerta(
                f"backup_pendiente:{hoy.isoformat()}", "Backup pendiente",
                "Backup diario pendiente", "Todavía no se generó la copia de seguridad de hoy.",
                "Alta", hoy.isoformat(), "backup", None,
            ))

        ahora = datetime.now().isoformat(timespec="seconds")
        claves_activas = []
        for alerta in alertas:
            claves_activas.append(alerta[0])
            cur.execute("""
                INSERT INTO notificaciones(
                    tipo, titulo, mensaje, prioridad, estado, fecha, vencimiento,
                    referencia_tipo, referencia_id, clave, automatica, creado, actualizado
                ) VALUES(?,?,?,?,?,?,?,?,?,?,1,?,?)
                ON CONFLICT(clave) DO UPDATE SET
                    tipo=excluded.tipo, titulo=excluded.titulo, mensaje=excluded.mensaje,
                    prioridad=excluded.prioridad, vencimiento=excluded.vencimiento,
                    referencia_tipo=excluded.referencia_tipo,
                    referencia_id=excluded.referencia_id, actualizado=excluded.actualizado
            """, (
                alerta[1], alerta[2], alerta[3], alerta[4], "Pendiente",
                hoy.isoformat(), alerta[5], alerta[6], alerta[7], alerta[0], ahora, ahora,
            ))
        if claves_activas:
            marcadores = ",".join("?" for _ in claves_activas)
            cur.execute(f"""
                UPDATE notificaciones SET estado='Resuelta', actualizado=?
                WHERE automatica=1 AND estado IN ('Pendiente','Leída')
                  AND clave NOT IN ({marcadores})
            """, (ahora, *claves_activas))
        else:
            cur.execute("""
                UPDATE notificaciones SET estado='Resuelta', actualizado=?
                WHERE automatica=1 AND estado IN ('Pendiente','Leída')
            """, (ahora,))
        conn.commit()
        conn.close()
        return len(alertas)

    @staticmethod
    def listar(tipo="Todos", prioridad="Todas", estado="Todos"):
        condiciones, parametros = [], []
        if tipo not in (None, "", "Todos"):
            condiciones.append("tipo=?"); parametros.append(tipo)
        if prioridad not in (None, "", "Todas"):
            condiciones.append("prioridad=?"); parametros.append(prioridad)
        if estado not in (None, "", "Todos"):
            condiciones.append("estado=?"); parametros.append(estado)
        consulta = """
            SELECT id, tipo, titulo, mensaje, prioridad, estado, fecha,
                   vencimiento, referencia_tipo, referencia_id, clave,
                   automatica, creado, actualizado
            FROM notificaciones
        """
        if condiciones:
            consulta += " WHERE " + " AND ".join(condiciones)
        consulta += " ORDER BY CASE prioridad WHEN 'Urgente' THEN 1 WHEN 'Alta' THEN 2 WHEN 'Media' THEN 3 ELSE 4 END, CASE estado WHEN 'Pendiente' THEN 1 WHEN 'Leída' THEN 2 ELSE 3 END, vencimiento, id DESC"
        conn = conectar(); cur = conn.cursor(); cur.execute(consulta, parametros)
        filas = cur.fetchall(); conn.close(); return filas

    @staticmethod
    def marcar_leida(notificacion_id):
        return NotificacionService._cambiar_estado(notificacion_id, "Leída", estados=("Pendiente",))

    @staticmethod
    def marcar_resuelta(notificacion_id):
        return NotificacionService._cambiar_estado(notificacion_id, "Resuelta", estados=("Pendiente", "Leída"))

    @staticmethod
    def descartar(notificacion_id):
        return NotificacionService._cambiar_estado(notificacion_id, "Descartada", estados=("Pendiente", "Leída"))

    @staticmethod
    def resumen_dashboard():
        hoy = date.today().isoformat()
        conn = conectar(); cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM notificaciones WHERE prioridad='Urgente' AND estado IN ('Pendiente','Leída')")
        urgentes = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM notificaciones WHERE estado='Pendiente'")
        pendientes = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM notificaciones WHERE vencimiento<? AND estado IN ('Pendiente','Leída')", (hoy,))
        vencidas = cur.fetchone()[0]
        conn.close()
        return {"urgentes": urgentes, "pendientes": pendientes, "vencidas": vencidas}

    @staticmethod
    def _cambiar_estado(notificacion_id, estado, estados):
        ahora = datetime.now().isoformat(timespec="seconds")
        marcadores = ",".join("?" for _ in estados)
        conn = conectar(); cur = conn.cursor()
        cur.execute(
            f"UPDATE notificaciones SET estado=?, actualizado=? WHERE id=? AND estado IN ({marcadores})",
            (estado, ahora, notificacion_id, *estados),
        )
        actualizado = cur.rowcount > 0
        conn.commit(); conn.close(); return actualizado

    @staticmethod
    def _alerta(clave, tipo, titulo, mensaje, prioridad, vencimiento, referencia_tipo, referencia_id):
        return (clave, tipo, titulo, mensaje, prioridad, vencimiento, referencia_tipo, referencia_id)

    @staticmethod
    def _mostrar_fecha(valor):
        try: return datetime.strptime(valor, "%Y-%m-%d").strftime("%d/%m/%Y")
        except (TypeError, ValueError): return valor or "Sin fecha"

    @staticmethod
    def _moneda(valor):
        numero = f"{float(valor or 0):,.2f}"
        return "$ " + numero.replace(",", "X").replace(".", ",").replace("X", ".")
