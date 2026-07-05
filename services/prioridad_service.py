from datetime import date

from services.cliente_service import ClienteService
from services.cobro_service import CobroService
from services.contacto_service import ContactoService
from services.dashboard_service import DashboardService
from services.resumen_service import ResumenService
from services.servicio_service import ServicioService
from services.tarea_service import TareaService


class PrioridadService:

    @staticmethod
    def obtener_recomendacion():
        prioridad_cliente = PrioridadService._obtener_cliente_prioritario()
        if prioridad_cliente is not None:
            return prioridad_cliente

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
                "cliente_nombre": "",
                "puntaje": 0,
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
            "cliente_nombre": "",
            "puntaje": 0,
            "accion": None,
        }

    @staticmethod
    def _obtener_cliente_prioritario():
        hoy = date.today().isoformat()
        mejor = None

        for cliente in ClienteService.listar():
            cliente_id = cliente[0]
            cliente_nombre = cliente[2] or "Cliente"
            estado = str(cliente[5] or "").strip().lower()
            if estado and estado != "activo":
                continue

            puntaje = 0
            motivos = []

            totales = CobroService.totales(cliente_id)
            saldo_pendiente = float(totales.get("saldo_pendiente") or 0)
            if saldo_pendiente > 0:
                puntaje += 3
                motivos.append("Saldo pendiente de cobro")

            resumenes = ResumenService.listar(cliente_id)
            resumenes_vencidos = sum(
                1
                for resumen in resumenes
                if (resumen[3] or "") < hoy
                and float(resumen[6] or 0) > 0
                and str(resumen[7] or "").strip().lower() != "pagado"
            )
            if resumenes_vencidos > 0:
                puntaje += 4 + resumenes_vencidos
                motivos.append(f"Resumenes vencidos: {resumenes_vencidos}")

            tareas_vencidas = len(TareaService.listar("Vencidas", cliente_id=cliente_id))
            if tareas_vencidas > 0:
                puntaje += 2 + tareas_vencidas
                motivos.append(f"Tareas vencidas: {tareas_vencidas}")

            contactos = ContactoService.listar(cliente_id=cliente_id)
            seguimientos_atrasados = sum(
                1 for contacto in contactos if (contacto[7] or "") and contacto[7] < hoy
            )
            if seguimientos_atrasados > 0:
                puntaje += 2 + seguimientos_atrasados
                motivos.append(f"Seguimientos atrasados: {seguimientos_atrasados}")

            servicios = ServicioService.listar(cliente_id)
            servicios_vencidos = sum(
                1
                for servicio in servicios
                if int(servicio[7] or 0) == 1
                and str(servicio[12] or "").strip().lower() in ("vencido", "finalizado")
            )
            if servicios_vencidos > 0:
                puntaje += 3 + servicios_vencidos
                motivos.append(f"Servicios vencidos: {servicios_vencidos}")

            if puntaje <= 0:
                continue

            candidato = {
                "cliente_id": cliente_id,
                "cliente_nombre": cliente_nombre,
                "puntaje": puntaje,
                "motivos": motivos,
            }
            if mejor is None or candidato["puntaje"] > mejor["puntaje"]:
                mejor = candidato

        if mejor is None:
            return None

        prioridad = "Alta"
        if mejor["puntaje"] >= 10:
            prioridad = "Urgente"

        return {
            "titulo": f"Cliente prioritario: {mejor['cliente_nombre']}",
            "mensaje": "Se detecto un cliente con mayor urgencia operativa.",
            "prioridad": prioridad,
            "motivos": mejor["motivos"],
            "cliente_id": mejor["cliente_id"],
            "cliente_nombre": mejor["cliente_nombre"],
            "puntaje": mejor["puntaje"],
            "accion": None,
        }
