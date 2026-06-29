import calendar
from datetime import date, datetime, timedelta

from database import conectar


class ServicioService:

    @staticmethod
    def sumar_un_mes(fecha):
        if isinstance(fecha, str):
            fecha = datetime.strptime(fecha, "%Y-%m-%d").date()
        anio = fecha.year + (1 if fecha.month == 12 else 0)
        mes = 1 if fecha.month == 12 else fecha.month + 1
        dia = min(fecha.day, calendar.monthrange(anio, mes)[1])
        return date(anio, mes, dia)

    @staticmethod
    def actualizar_estados_periodo(fecha_referencia=None):
        referencia = fecha_referencia or date.today()
        if isinstance(referencia, str):
            referencia = datetime.strptime(referencia, "%Y-%m-%d").date()
        conn = conectar()
        cur = conn.cursor()
        cur.execute("""
            UPDATE servicios
            SET estado_periodo = CASE
                WHEN fecha_fin < ? AND COALESCE(renovable, 1)=1 THEN 'Vencido'
                WHEN fecha_fin < ? AND COALESCE(renovable, 1)=0 THEN 'Finalizado'
                ELSE 'Activo'
            END
        """, (referencia.isoformat(), referencia.isoformat()))
        conn.commit()
        conn.close()

    @staticmethod
    def listar(cliente_id):
        ServicioService.actualizar_estados_periodo()
        conn = conectar()
        cur = conn.cursor()
        cur.execute("""
            SELECT
                id, cliente_id, concepto, descripcion, cantidad, importe,
                descuento, activo, (cantidad * importe) - descuento AS total,
                fecha_inicio, fecha_fin, renovable, estado_periodo
            FROM servicios
            WHERE cliente_id=?
            ORDER BY concepto
        """, (cliente_id,))
        datos = cur.fetchall()
        conn.close()
        return datos

    @staticmethod
    def obtener(id_servicio):
        ServicioService.actualizar_estados_periodo()
        conn = conectar()
        cur = conn.cursor()
        cur.execute("""
            SELECT
                id, cliente_id, concepto, descripcion, cantidad, importe,
                descuento, activo, fecha_inicio, fecha_fin, renovable,
                estado_periodo
            FROM servicios
            WHERE id=?
        """, (id_servicio,))
        fila = cur.fetchone()
        conn.close()
        return fila

    @staticmethod
    def guardar(servicio):
        inicio = ServicioService._fecha(servicio.fecha_inicio or date.today())
        fin = ServicioService.sumar_un_mes(inicio)
        conn = conectar()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO servicios(
                cliente_id, concepto, descripcion, cantidad, importe,
                descuento, activo, fecha_inicio, fecha_fin, renovable,
                estado_periodo
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?)
        """, (
            servicio.cliente_id, servicio.concepto, servicio.descripcion,
            servicio.cantidad, servicio.importe, servicio.descuento,
            servicio.activo, inicio.isoformat(), fin.isoformat(),
            1 if servicio.renovable else 0, "Activo",
        ))
        servicio_id = cur.lastrowid
        conn.commit()
        conn.close()
        return servicio_id

    @staticmethod
    def actualizar(servicio):
        inicio = ServicioService._fecha(servicio.fecha_inicio or date.today())
        fin = ServicioService.sumar_un_mes(inicio)
        referencia = date.today()
        if fin < referencia:
            estado = "Vencido" if servicio.renovable else "Finalizado"
        else:
            estado = "Activo"
        conn = conectar()
        cur = conn.cursor()
        cur.execute("""
            UPDATE servicios
            SET concepto=?, descripcion=?, cantidad=?, importe=?, descuento=?,
                activo=?, fecha_inicio=?, fecha_fin=?, renovable=?,
                estado_periodo=?
            WHERE id=?
        """, (
            servicio.concepto, servicio.descripcion, servicio.cantidad,
            servicio.importe, servicio.descuento, servicio.activo,
            inicio.isoformat(), fin.isoformat(), 1 if servicio.renovable else 0,
            estado, servicio.id,
        ))
        conn.commit()
        conn.close()

    @staticmethod
    def renovar_periodo(id_servicio):
        resultado = ServicioService.renovar_periodos([id_servicio])
        if not resultado["renovados"]:
            detalle = resultado["errores"][0] if resultado["errores"] else "No se pudo renovar."
            raise ValueError(detalle)
        renovacion = resultado["renovados"][0]
        return renovacion["fecha_inicio_nueva"], renovacion["fecha_fin_nueva"]

    @staticmethod
    def listar_para_renovacion(fecha_referencia=None):
        referencia = ServicioService._fecha(fecha_referencia or date.today())
        fin_mes = ServicioService._fin_de_mes(referencia)
        ServicioService.actualizar_estados_periodo(referencia)
        conn = conectar()
        cur = conn.cursor()
        cur.execute("""
            SELECT
                s.id,
                s.cliente_id,
                COALESCE(NULLIF(c.razon_social, ''), c.nombre) AS cliente,
                s.concepto,
                s.fecha_inicio,
                s.fecha_fin,
                s.importe,
                s.descuento,
                s.estado_periodo,
                (
                    SELECT sr.fecha_renovacion
                    FROM servicio_renovaciones sr
                    WHERE sr.servicio_id=s.id
                    ORDER BY sr.id DESC LIMIT 1
                ) AS ultima_renovacion
            FROM servicios s
            JOIN clientes c ON c.id=s.cliente_id
            WHERE s.activo=1
              AND s.renovable=1
              AND (
                    s.fecha_fin<=?
                    OR (s.fecha_fin>? AND s.fecha_fin<=?)
                    OR EXISTS (
                        SELECT 1 FROM servicio_renovaciones sr_hoy
                        WHERE sr_hoy.servicio_id=s.id
                          AND DATE(sr_hoy.fecha_renovacion)=?
                    )
                  )
            ORDER BY s.fecha_fin, cliente, s.concepto
        """, (
            referencia.isoformat(),
            referencia.isoformat(),
            fin_mes.isoformat(),
            referencia.isoformat(),
        ))
        filas = cur.fetchall()
        conn.close()

        resultado = []
        limite_semana = referencia + timedelta(days=7)
        for fila in filas:
            fin = ServicioService._fecha(fila[5])
            renovado_hoy = bool(fila[9] and str(fila[9])[:10] == referencia.isoformat())
            if renovado_hoy:
                estado = "Renovado"
            elif fin < referencia:
                estado = "Vencido"
            elif fin == referencia:
                estado = "Vence hoy"
            elif fin <= limite_semana:
                estado = "Proximo"
            else:
                estado = "Este mes"
            resultado.append({
                "id": fila[0],
                "cliente_id": fila[1],
                "cliente": fila[2],
                "concepto": fila[3],
                "fecha_inicio": fila[4],
                "fecha_fin": fila[5],
                "importe": float(fila[6] or 0),
                "descuento": float(fila[7] or 0),
                "estado": estado,
            })
        return resultado

    @staticmethod
    def renovar_periodos(servicio_ids):
        ids = list(dict.fromkeys(int(servicio_id) for servicio_id in servicio_ids))
        resultado = {"renovados": [], "omitidos": 0, "errores": []}
        conn = conectar()
        cur = conn.cursor()
        try:
            for servicio_id in ids:
                cur.execute("""
                    SELECT
                        id, cliente_id, concepto, descripcion, cantidad,
                        importe, descuento, activo, fecha_inicio, fecha_fin,
                        renovable
                    FROM servicios WHERE id=?
                """, (servicio_id,))
                fila = cur.fetchone()
                if fila is None:
                    resultado["errores"].append(f"Servicio {servicio_id}: no encontrado.")
                    continue
                if not fila[7] or not fila[10]:
                    resultado["omitidos"] += 1
                    continue

                inicio_nuevo = ServicioService._fecha(fila[9])
                fin_nuevo = ServicioService.sumar_un_mes(inicio_nuevo)
                estado = "Activo" if fin_nuevo >= date.today() else "Vencido"
                fecha_renovacion = datetime.now().isoformat(timespec="seconds")
                cur.execute("""
                    INSERT INTO servicio_renovaciones(
                        servicio_id, cliente_id, fecha_renovacion,
                        fecha_inicio_anterior, fecha_fin_anterior,
                        fecha_inicio_nueva, fecha_fin_nueva,
                        concepto, descripcion, cantidad, importe, descuento
                    ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
                """, (
                    fila[0], fila[1], fecha_renovacion, fila[8], fila[9],
                    inicio_nuevo.isoformat(), fin_nuevo.isoformat(), fila[2],
                    fila[3], fila[4], fila[5], fila[6],
                ))
                renovacion_id = cur.lastrowid
                cur.execute("""
                    UPDATE servicios
                    SET fecha_inicio=?, fecha_fin=?, estado_periodo=?
                    WHERE id=?
                """, (
                    inicio_nuevo.isoformat(), fin_nuevo.isoformat(),
                    estado, servicio_id,
                ))
                resultado["renovados"].append({
                    "renovacion_id": renovacion_id,
                    "servicio_id": servicio_id,
                    "cliente_id": fila[1],
                    "fecha_inicio_nueva": inicio_nuevo.isoformat(),
                    "fecha_fin_nueva": fin_nuevo.isoformat(),
                })
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
        return resultado

    @staticmethod
    def _fin_de_mes(fecha):
        ultimo_dia = calendar.monthrange(fecha.year, fecha.month)[1]
        return fecha.replace(day=ultimo_dia)

    @staticmethod
    def eliminar(id_servicio):
        conn = conectar()
        cur = conn.cursor()
        cur.execute("DELETE FROM servicios WHERE id=?", (id_servicio,))
        conn.commit()
        conn.close()

    @staticmethod
    def total_cliente(cliente_id, fecha_referencia=None):
        referencia = ServicioService._fecha(fecha_referencia or date.today()).isoformat()
        conn = conectar()
        cur = conn.cursor()
        cur.execute("""
            SELECT IFNULL(SUM((cantidad * importe) - descuento), 0)
            FROM servicios
            WHERE cliente_id=? AND activo=1
              AND fecha_inicio<=? AND fecha_fin>=?
        """, (cliente_id, referencia, referencia))
        total = cur.fetchone()[0]
        conn.close()
        return total

    @staticmethod
    def _fecha(valor):
        if isinstance(valor, datetime):
            return valor.date()
        if isinstance(valor, date):
            return valor
        return datetime.strptime(str(valor), "%Y-%m-%d").date()
