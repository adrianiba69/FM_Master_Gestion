from datetime import date, timedelta

from database import conectar
from services.backup_service import BackupService
from services.resumen_service import ResumenService
from services.servicio_service import ServicioService
from services.tarea_service import TareaService


class DashboardService:

    @staticmethod
    def obtener_indicadores():
        hoy = date.today()
        inicio_mes = hoy.replace(day=1)
        if inicio_mes.month == 12:
            inicio_mes_siguiente = inicio_mes.replace(
                year=inicio_mes.year + 1,
                month=1,
            )
        else:
            inicio_mes_siguiente = inicio_mes.replace(month=inicio_mes.month + 1)
        limite_vencimientos = hoy + timedelta(days=30)
        limite_servicios = hoy + timedelta(days=7)
        ServicioService.actualizar_estados_periodo(hoy)
        resumenes_pendientes = ResumenService.contar_clientes_pendientes(hoy)
        agenda = TareaService.resumen_dashboard()

        conn = conectar()
        cur = conn.cursor()

        cur.execute("SELECT COUNT(*) FROM clientes")
        total_clientes = cur.fetchone()[0]
        cur.execute(
            "SELECT COUNT(*) FROM clientes WHERE LOWER(TRIM(COALESCE(estado, '')))='activo'"
        )
        clientes_activos = cur.fetchone()[0]

        cur.execute("""
            SELECT COUNT(*), COALESCE(SUM(total), 0)
            FROM resumenes
            WHERE fecha>=? AND fecha<?
        """, (inicio_mes.isoformat(), inicio_mes_siguiente.isoformat()))
        resumenes_mes, facturado_mes = cur.fetchone()

        cur.execute("""
            SELECT COALESCE(SUM(importe), 0)
            FROM cobros
            WHERE fecha>=? AND fecha<?
        """, (inicio_mes.isoformat(), inicio_mes_siguiente.isoformat()))
        cobrado_mes = float(cur.fetchone()[0] or 0)

        cur.execute("SELECT COALESCE(SUM(total), 0) FROM resumenes")
        total_facturado = float(cur.fetchone()[0] or 0)
        cur.execute("SELECT COALESCE(SUM(importe), 0) FROM cobros")
        total_cobrado = float(cur.fetchone()[0] or 0)

        cur.execute("""
            SELECT COUNT(*)
            FROM resumenes
            WHERE fecha_vencimiento<?
              AND saldo>0
              AND LOWER(COALESCE(estado, ''))!='pagado'
        """, (hoy.isoformat(),))
        resumenes_vencidos = cur.fetchone()[0]

        cur.execute("""
            SELECT COUNT(*)
            FROM resumenes
            WHERE fecha_vencimiento>=?
              AND fecha_vencimiento<=?
              AND saldo>0
              AND LOWER(COALESCE(estado, ''))!='pagado'
        """, (hoy.isoformat(), limite_vencimientos.isoformat()))
        proximos_vencimientos = cur.fetchone()[0]

        cur.execute("""
            SELECT COUNT(*) FROM servicios
            WHERE activo=1 AND fecha_fin=?
        """, (hoy.isoformat(),))
        servicios_vencen_hoy = cur.fetchone()[0]

        cur.execute("""
            SELECT COUNT(*) FROM servicios
            WHERE activo=1 AND fecha_fin<?
        """, (hoy.isoformat(),))
        servicios_vencidos = cur.fetchone()[0]

        cur.execute("""
            SELECT COUNT(*) FROM servicios
            WHERE activo=1 AND fecha_fin>?
              AND fecha_fin<=?
        """, (hoy.isoformat(), limite_servicios.isoformat()))
        servicios_proximos = cur.fetchone()[0]

        cur.execute("""
            SELECT COUNT(*) FROM servicios
            WHERE activo=1 AND renovable=1 AND fecha_fin=?
        """, (hoy.isoformat(),))
        renovaciones_hoy = cur.fetchone()[0]
        cur.execute("""
            SELECT COUNT(*) FROM servicios
            WHERE activo=1 AND renovable=1 AND fecha_fin>?
              AND fecha_fin<=?
        """, (hoy.isoformat(), limite_servicios.isoformat()))
        renovaciones_semana = cur.fetchone()[0]
        cur.execute("""
            SELECT COUNT(*) FROM servicios
            WHERE activo=1 AND renovable=1 AND fecha_fin<?
        """, (hoy.isoformat(),))
        renovaciones_vencidas = cur.fetchone()[0]
        cur.execute("""
            SELECT COUNT(DISTINCT servicio_id)
            FROM servicio_renovaciones
            WHERE DATE(fecha_renovacion)=?
        """, (hoy.isoformat(),))
        renovados_hoy = cur.fetchone()[0]
        conn.close()

        return {
            "clientes_activos": clientes_activos,
            "total_clientes": total_clientes,
            "resumenes_mes": resumenes_mes,
            "facturado_mes": float(facturado_mes or 0),
            "cobrado_mes": cobrado_mes,
            "saldo_pendiente": total_facturado - total_cobrado,
            "resumenes_vencidos": resumenes_vencidos,
            "proximos_vencimientos": proximos_vencimientos,
            "servicios_vencen_hoy": servicios_vencen_hoy,
            "servicios_vencidos": servicios_vencidos,
            "servicios_proximos": servicios_proximos,
            "resumenes_pendientes": resumenes_pendientes,
            "renovaciones_hoy": renovaciones_hoy,
            "renovaciones_semana": renovaciones_semana,
            "renovaciones_vencidas": renovaciones_vencidas,
            "renovados_hoy": renovados_hoy,
            "agenda": agenda,
        }

    @staticmethod
    def listar_proximos_vencimientos(dias=30):
        hoy = date.today()
        limite = hoy + timedelta(days=dias)
        conn = conectar()
        cur = conn.cursor()
        cur.execute("""
            SELECT
                r.id,
                r.numero,
                r.fecha_vencimiento,
                COALESCE(NULLIF(c.razon_social, ''), c.nombre) AS cliente,
                r.total,
                r.saldo,
                r.estado
            FROM resumenes r
            JOIN clientes c ON c.id=r.cliente_id
            WHERE r.fecha_vencimiento>=?
              AND r.fecha_vencimiento<=?
              AND r.saldo>0
              AND LOWER(COALESCE(r.estado, ''))!='pagado'
            ORDER BY r.fecha_vencimiento, r.numero
        """, (hoy.isoformat(), limite.isoformat()))
        datos = cur.fetchall()
        conn.close()
        return datos

    @staticmethod
    def crear_backup():
        return BackupService.crear_backup()
