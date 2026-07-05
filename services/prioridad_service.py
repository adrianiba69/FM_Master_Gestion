from services.dashboard_service import DashboardService


class PrioridadService:

    @staticmethod
    def obtener_recomendacion():
        indicadores = DashboardService.obtener_indicadores() or {}
        agenda = indicadores.get("agenda") or {}
        seguimientos = indicadores.get("seguimientos") or {}

        resumenes_vencidos = int(indicadores.get("resumenes_vencidos", 0) or 0)
        servicios_vencidos = int(indicadores.get("servicios_vencidos", 0) or 0)
        tareas_vencidas = int(agenda.get("vencidas", 0) or 0)
        seguimientos_atrasados = int(seguimientos.get("atrasados", 0) or 0)
        clientes_con_deuda = int(indicadores.get("clientes_con_deuda", 0) or 0)
        resumenes_pendientes = int(indicadores.get("resumenes_pendientes", 0) or 0)
        servicios_proximos = int(indicadores.get("servicios_proximos", 0) or 0)

        motivos = []
        if resumenes_vencidos > 0:
            motivos.append(f"Resumenes vencidos: {resumenes_vencidos}")
        if servicios_vencidos > 0:
            motivos.append(f"Servicios vencidos: {servicios_vencidos}")
        if tareas_vencidas > 0:
            motivos.append(f"Tareas vencidas: {tareas_vencidas}")
        if seguimientos_atrasados > 0:
            motivos.append(f"Seguimientos atrasados: {seguimientos_atrasados}")
        if clientes_con_deuda > 0:
            motivos.append(f"Clientes con deuda: {clientes_con_deuda}")
        if resumenes_pendientes > 0:
            motivos.append(f"Clientes por resumir: {resumenes_pendientes}")
        if servicios_proximos > 0:
            motivos.append(f"Servicios proximos a vencer: {servicios_proximos}")

        if not motivos:
            return {
                "titulo": "Sistema al dia",
                "mensaje": "No se detectaron prioridades operativas.",
                "prioridad": "Baja",
                "motivos": [],
                "cliente_id": None,
                "accion": None,
            }

        prioridad = "Alta"
        if resumenes_vencidos > 0 or tareas_vencidas > 0 or seguimientos_atrasados > 0:
            prioridad = "Urgente"

        return {
            "titulo": "Prioridad operativa general",
            "mensaje": "Se detectaron alertas que requieren atencion del equipo.",
            "prioridad": prioridad,
            "motivos": motivos,
            "cliente_id": None,
            "accion": None,
        }
