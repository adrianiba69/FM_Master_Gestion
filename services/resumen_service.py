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
    def _resolver_datos_fiscales_cliente(cur, cliente_id):
        cur.execute(
            "SELECT monotributo_facturacion FROM clientes WHERE id=?",
            (cliente_id,),
        )
        fila = cur.fetchone()
        referencia_emisor = (fila[0] or "").strip() if fila else ""
        if not referencia_emisor or referencia_emisor == "No aplica":
            return None, None, None

        emisor = None
        if referencia_emisor.startswith("EMISOR:"):
            try:
                emisor_id = int(referencia_emisor.split(":", 1)[1])
            except (TypeError, ValueError):
                emisor_id = None
            if emisor_id is not None:
                cur.execute(
                    "SELECT id, tipo_factura, punto_venta FROM emisores_fiscales WHERE id=?",
                    (emisor_id,),
                )
                emisor = cur.fetchone()
        elif referencia_emisor in ("Monotributo 1", "Monotributo 2"):
            indice = 0 if referencia_emisor.endswith("1") else 1
            cur.execute(
                "SELECT id, tipo_factura, punto_venta FROM emisores_fiscales WHERE activo=1 ORDER BY id"
            )
            emisores = cur.fetchall()
            if len(emisores) > indice:
                emisor = emisores[indice]
        else:
            cur.execute(
                """
                SELECT id, tipo_factura, punto_venta
                FROM emisores_fiscales
                WHERE nombre_fantasia=? OR razon_social=?
                ORDER BY activo DESC, id
                LIMIT 1
                """,
                (referencia_emisor, referencia_emisor),
            )
            emisor = cur.fetchone()

        if emisor is None:
            return None, None, None

        return emisor[0], emisor[1] or None, emisor[2] or None

    @staticmethod
    def _insertar_resumen(cur, numero, cliente_id, fecha_emision, vencimiento, total):
        emisor_fiscal_id, tipo_factura, punto_venta = ResumenService._resolver_datos_fiscales_cliente(
            cur,
            cliente_id,
        )
        cur.execute(
            """
            INSERT INTO resumenes(
                numero, cliente_id, emisor_fiscal_id, fecha, fecha_vencimiento,
                tipo_factura, punto_venta, total, saldo, estado,
                estado_facturacion, fecha_creacion
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                numero,
                cliente_id,
                emisor_fiscal_id,
                fecha_emision.isoformat(),
                vencimiento.isoformat(),
                tipo_factura,
                punto_venta,
                total,
                total,
                "Pendiente",
                "Pendiente",
                datetime.now().isoformat(timespec="seconds"),
            ),
        )
        return cur.lastrowid

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
                SELECT
                    s.id, s.concepto, s.descripcion, s.cantidad, s.importe,
                    s.descuento, s.fecha_inicio, s.fecha_fin
                FROM servicios s
                WHERE s.cliente_id=? AND s.activo=1
                  AND s.fecha_inicio<=?
                  AND s.fecha_fin>=?
                  AND NOT EXISTS (
                      SELECT 1 FROM resumen_conceptos rc
                      WHERE rc.servicio_id=s.id
                        AND rc.fecha_inicio=s.fecha_inicio
                        AND rc.fecha_fin=s.fecha_fin
                  )
                ORDER BY s.concepto
            """, (
                cliente_id,
                fecha_emision.isoformat(),
                fecha_emision.isoformat(),
            ))
            servicios = cur.fetchall()
            if not servicios:
                raise ValueError(
                    "El cliente no tiene servicios activos vigentes para el periodo seleccionado."
                )

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

            resumen_id = ResumenService._insertar_resumen(
                cur,
                numero,
                cliente_id,
                fecha_emision,
                vencimiento,
                total,
            )

            for servicio in servicios:
                cantidad = float(servicio[3] or 0)
                importe = float(servicio[4] or 0)
                descuento = float(servicio[5] or 0)
                subtotal = (cantidad * importe) - descuento
                cur.execute("""
                    INSERT INTO resumen_conceptos(
                        resumen_id, servicio_id, concepto, descripcion,
                        cantidad, importe, descuento, total,
                        fecha_inicio, fecha_fin
                    ) VALUES(?,?,?,?,?,?,?,?,?,?)
                """, (
                    resumen_id, servicio[0], servicio[1], servicio[2],
                    cantidad, importe, descuento, subtotal,
                    servicio[6], servicio[7],
                ))

            conn.commit()
            return ResumenService.obtener(resumen_id)
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    @staticmethod
    def listar_pendientes(fecha_referencia=None):
        referencia = fecha_referencia or date.today()
        if isinstance(referencia, str):
            referencia = datetime.strptime(referencia, "%Y-%m-%d").date()

        conn = conectar()
        cur = conn.cursor()
        cur.execute("""
            SELECT
                s.id,
                s.cliente_id,
                COALESCE(NULLIF(c.razon_social, ''), c.nombre),
                s.concepto,
                s.descripcion,
                s.cantidad,
                s.importe,
                s.descuento,
                s.fecha_inicio,
                s.fecha_fin
            FROM servicios s
            JOIN clientes c ON c.id=s.cliente_id
            WHERE s.activo=1
              AND s.fecha_fin<=?
              AND NOT EXISTS (
                  SELECT 1 FROM resumen_conceptos rc
                  WHERE rc.servicio_id=s.id
                    AND rc.fecha_inicio=s.fecha_inicio
                    AND rc.fecha_fin=s.fecha_fin
              )
            ORDER BY c.razon_social, s.fecha_fin, s.concepto
        """, (referencia.isoformat(),))
        filas = cur.fetchall()
        conn.close()

        agrupados = {}
        for fila in filas:
            cliente_id = fila[1]
            grupo = agrupados.setdefault(cliente_id, {
                "cliente_id": cliente_id,
                "cliente": fila[2],
                "servicios": [],
                "fecha_inicio": fila[8],
                "fecha_fin": fila[9],
                "total": 0.0,
            })
            subtotal = (
                float(fila[5] or 0) * float(fila[6] or 0)
                - float(fila[7] or 0)
            )
            grupo["servicios"].append({
                "id": fila[0],
                "concepto": fila[3],
                "fecha_inicio": fila[8],
                "fecha_fin": fila[9],
                "total": subtotal,
            })
            grupo["fecha_inicio"] = min(grupo["fecha_inicio"], fila[8])
            grupo["fecha_fin"] = max(grupo["fecha_fin"], fila[9])
            grupo["total"] += subtotal

        return list(agrupados.values())

    @staticmethod
    def contar_clientes_pendientes(fecha_referencia=None):
        return len(ResumenService.listar_pendientes(fecha_referencia))

    @staticmethod
    def generar_pendiente_cliente(cliente_id, fecha=None):
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
                SELECT
                    s.id, s.concepto, s.descripcion, s.cantidad, s.importe,
                    s.descuento, s.fecha_inicio, s.fecha_fin
                FROM servicios s
                WHERE s.cliente_id=? AND s.activo=1
                  AND s.fecha_fin<=?
                  AND NOT EXISTS (
                      SELECT 1 FROM resumen_conceptos rc
                      WHERE rc.servicio_id=s.id
                        AND rc.fecha_inicio=s.fecha_inicio
                        AND rc.fecha_fin=s.fecha_fin
                  )
                ORDER BY s.fecha_fin, s.concepto
            """, (cliente_id, fecha_emision.isoformat()))
            servicios = cur.fetchall()
            if not servicios:
                conn.rollback()
                return None

            vencimiento = ResumenService.calcular_vencimiento(cliente, fecha_emision)
            cur.execute("SELECT COALESCE(MAX(numero), 0) + 1 FROM resumenes")
            numero = cur.fetchone()[0]
            total = sum(
                float(servicio[3] or 0) * float(servicio[4] or 0)
                - float(servicio[5] or 0)
                for servicio in servicios
            )
            resumen_id = ResumenService._insertar_resumen(
                cur,
                numero,
                cliente_id,
                fecha_emision,
                vencimiento,
                total,
            )

            for servicio in servicios:
                cantidad = float(servicio[3] or 0)
                importe = float(servicio[4] or 0)
                descuento = float(servicio[5] or 0)
                subtotal = cantidad * importe - descuento
                cur.execute("""
                    INSERT INTO resumen_conceptos(
                        resumen_id, servicio_id, concepto, descripcion,
                        cantidad, importe, descuento, total,
                        fecha_inicio, fecha_fin
                    ) VALUES(?,?,?,?,?,?,?,?,?,?)
                """, (
                    resumen_id, servicio[0], servicio[1], servicio[2],
                    cantidad, importe, descuento, subtotal,
                    servicio[6], servicio[7],
                ))

            conn.commit()
            return ResumenService.obtener(resumen_id)
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    @staticmethod
    def eliminar_generacion(resumen_id):
        conn = conectar()
        cur = conn.cursor()
        cur.execute(
            "UPDATE servicio_renovaciones SET resumen_id=NULL WHERE resumen_id=?",
            (resumen_id,),
        )
        cur.execute("DELETE FROM resumen_conceptos WHERE resumen_id=?", (resumen_id,))
        cur.execute("DELETE FROM resumenes WHERE id=?", (resumen_id,))
        conn.commit()
        conn.close()

    @staticmethod
    def generar_desde_renovaciones(renovacion_ids, fecha=None):
        ids = list(dict.fromkeys(int(valor) for valor in renovacion_ids))
        resultado = {"generados": [], "omitidos": 0, "errores": []}
        if not ids:
            return resultado

        fecha_emision = fecha or date.today()
        if isinstance(fecha_emision, str):
            fecha_emision = datetime.strptime(fecha_emision, "%Y-%m-%d").date()
        marcadores = ",".join("?" for _ in ids)

        conn = conectar()
        cur = conn.cursor()
        try:
            cur.execute(f"""
                SELECT
                    sr.id, sr.servicio_id, sr.cliente_id,
                    COALESCE(NULLIF(c.razon_social, ''), c.nombre),
                    sr.concepto, sr.descripcion, sr.cantidad, sr.importe,
                    sr.descuento, sr.fecha_inicio_anterior,
                    sr.fecha_fin_anterior, c.vencimiento
                FROM servicio_renovaciones sr
                JOIN clientes c ON c.id=sr.cliente_id
                WHERE sr.id IN ({marcadores})
                  AND sr.resumen_id IS NULL
                  AND NOT EXISTS (
                      SELECT 1 FROM resumen_conceptos rc
                      WHERE rc.servicio_id=sr.servicio_id
                        AND rc.fecha_inicio=sr.fecha_inicio_anterior
                        AND rc.fecha_fin=sr.fecha_fin_anterior
                  )
                ORDER BY sr.cliente_id, sr.id
            """, ids)
            filas = cur.fetchall()
            resultado["omitidos"] = len(ids) - len(filas)
            grupos = {}
            for fila in filas:
                grupos.setdefault(fila[2], []).append(fila)

            resumen_ids = []
            for cliente_id, renovaciones in grupos.items():
                cur.execute("SELECT COALESCE(MAX(numero), 0) + 1 FROM resumenes")
                numero = cur.fetchone()[0]
                total = sum(
                    float(fila[6] or 0) * float(fila[7] or 0)
                    - float(fila[8] or 0)
                    for fila in renovaciones
                )
                dia = max(1, min(int(renovaciones[0][11] or 1), 28))
                if dia >= fecha_emision.day:
                    vencimiento = fecha_emision.replace(day=dia)
                elif fecha_emision.month == 12:
                    vencimiento = fecha_emision.replace(
                        year=fecha_emision.year + 1, month=1, day=dia
                    )
                else:
                    vencimiento = fecha_emision.replace(
                        month=fecha_emision.month + 1, day=dia
                    )
                resumen_id = ResumenService._insertar_resumen(
                    cur,
                    numero,
                    cliente_id,
                    fecha_emision,
                    vencimiento,
                    total,
                )
                resumen_ids.append(resumen_id)

                for fila in renovaciones:
                    cantidad = float(fila[6] or 0)
                    importe = float(fila[7] or 0)
                    descuento = float(fila[8] or 0)
                    subtotal = cantidad * importe - descuento
                    cur.execute("""
                        INSERT INTO resumen_conceptos(
                            resumen_id, servicio_id, concepto, descripcion,
                            cantidad, importe, descuento, total,
                            fecha_inicio, fecha_fin
                        ) VALUES(?,?,?,?,?,?,?,?,?,?)
                    """, (
                        resumen_id, fila[1], fila[4], fila[5], cantidad,
                        importe, descuento, subtotal, fila[9], fila[10],
                    ))
                    cur.execute(
                        "UPDATE servicio_renovaciones SET resumen_id=? WHERE id=?",
                        (resumen_id, fila[0]),
                    )

            conn.commit()
            resultado["generados"] = [
                ResumenService.obtener(resumen_id) for resumen_id in resumen_ids
            ]
            return resultado
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
             SELECT id, numero, cliente_id, emisor_fiscal_id, fecha, fecha_vencimiento,
                 tipo_factura, punto_venta, total, saldo, estado, pdf_path, fecha_creacion,
                 COALESCE(estado_facturacion, 'Pendiente'),
                 COALESCE(fecha_facturacion, ''),
                 COALESCE(cae, ''),
                 COALESCE(vencimiento_cae, ''),
                 COALESCE(numero_factura, '')
            FROM resumenes WHERE id=?
        """, (resumen_id,))
        fila = cur.fetchone()
        if fila is None:
            conn.close()
            return None

        resumen = Resumen(*fila)
        cur.execute("""
            SELECT id, resumen_id, servicio_id, concepto, descripcion,
                   cantidad, importe, descuento, total, fecha_inicio, fecha_fin
            FROM resumen_conceptos
            WHERE resumen_id=? ORDER BY id
        """, (resumen_id,))
        resumen.conceptos = [ResumenConcepto(*concepto) for concepto in cur.fetchall()]
        conn.close()
        return resumen

    @staticmethod
    def obtener_datos_facturacion(resumen_id):
        conn = conectar()
        cur = conn.cursor()
        cur.execute(
            """
            SELECT
                emisor_fiscal_id,
                tipo_factura,
                punto_venta,
                COALESCE(estado_facturacion, 'Pendiente'),
                COALESCE(fecha_facturacion, ''),
                COALESCE(cae, ''),
                COALESCE(vencimiento_cae, ''),
                COALESCE(numero_factura, '')
            FROM resumenes WHERE id=?
            """,
            (resumen_id,),
        )
        fila = cur.fetchone()
        conn.close()
        if not fila:
            return None
        return {
            "emisor_fiscal_id": fila[0],
            "tipo_factura": fila[1] or "",
            "punto_venta": fila[2] or "",
            "estado_facturacion": fila[3] or "Pendiente",
            "fecha_facturacion": fila[4] or "",
            "cae": fila[5] or "",
            "vencimiento_cae": fila[6] or "",
            "numero_factura": fila[7] or "",
        }

    @staticmethod
    def marcar_facturado(
        resumen_id,
        numero_factura="",
        cae="",
        vencimiento_cae="",
        fecha_facturacion=None,
        estado_facturacion="Facturado",
    ):
        fecha_valor = fecha_facturacion
        if fecha_valor is None:
            fecha_valor = datetime.now().isoformat(timespec="seconds")
        elif isinstance(fecha_valor, (date, datetime)):
            fecha_valor = fecha_valor.isoformat()

        conn = conectar()
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE resumenes
            SET estado_facturacion=?,
                fecha_facturacion=?,
                cae=?,
                vencimiento_cae=?,
                numero_factura=?
            WHERE id=?
            """,
            (
                estado_facturacion or "Facturado",
                fecha_valor,
                cae or "",
                vencimiento_cae or "",
                numero_factura or "",
                resumen_id,
            ),
        )
        conn.commit()
        conn.close()

    @staticmethod
    def obtener_pendientes_facturacion():
        conn = conectar()
        cur = conn.cursor()
        cur.execute(
            """
            SELECT
                r.id,
                r.numero,
                r.cliente_id,
                COALESCE(NULLIF(c.razon_social, ''), c.nombre),
                r.fecha,
                r.total,
                COALESCE(r.estado_facturacion, 'Pendiente'),
                r.emisor_fiscal_id,
                COALESCE(r.tipo_factura, ''),
                COALESCE(r.punto_venta, '')
            FROM resumenes r
            JOIN clientes c ON c.id = r.cliente_id
            WHERE COALESCE(r.estado_facturacion, 'Pendiente') = 'Pendiente'
            ORDER BY r.numero DESC
            """
        )
        filas = cur.fetchall()
        conn.close()
        return filas

    @staticmethod
    def obtener_facturados():
        conn = conectar()
        cur = conn.cursor()
        cur.execute(
            """
            SELECT
                r.id,
                r.numero,
                r.cliente_id,
                COALESCE(NULLIF(c.razon_social, ''), c.nombre),
                r.fecha,
                r.total,
                COALESCE(r.estado_facturacion, 'Pendiente'),
                COALESCE(r.fecha_facturacion, ''),
                COALESCE(r.numero_factura, ''),
                COALESCE(r.cae, ''),
                COALESCE(r.vencimiento_cae, '')
            FROM resumenes r
            JOIN clientes c ON c.id = r.cliente_id
            WHERE COALESCE(r.estado_facturacion, 'Pendiente') <> 'Pendiente'
            ORDER BY COALESCE(r.fecha_facturacion, r.fecha_creacion, r.fecha) DESC, r.numero DESC
            """
        )
        filas = cur.fetchall()
        conn.close()
        return filas

    @staticmethod
    def obtener_cliente(resumen_id):
        conn = conectar()
        cur = conn.cursor()
        cur.execute("""
            SELECT c.id, c.codigo,
                   COALESCE(NULLIF(c.razon_social, ''), c.nombre),
                   c.nombre_comercial, c.responsable, c.direccion,
                   c.localidad, c.telefono, c.email, c.cuit, c.iva, c.emisor_id
            FROM resumenes r
            JOIN clientes c ON c.id=r.cliente_id
            WHERE r.id=?
        """, (resumen_id,))
        cliente = cur.fetchone()
        conn.close()
        return cliente

    @staticmethod
    def obtener_emisor_de_cliente(resumen_id):
        conn = conectar()
        cur = conn.cursor()
        cur.execute("SELECT c.emisor_id FROM resumenes r JOIN clientes c ON c.id=r.cliente_id WHERE r.id=?", (resumen_id,))
        fila = cur.fetchone()
        if not fila or not fila[0]:
            conn.close()
            return None
        emisor_id = fila[0]
        cur.execute("SELECT id, nombre, cuit, condicion_iva, direccion, localidad, telefono, email, activo FROM emisores_facturacion WHERE id=?", (emisor_id,))
        emisor = cur.fetchone()
        conn.close()
        return emisor

    @staticmethod
    def actualizar_pdf_path(resumen_id, ruta):
        conn = conectar()
        cur = conn.cursor()
        cur.execute("UPDATE resumenes SET pdf_path=? WHERE id=?", (ruta, resumen_id))
        conn.commit()
        conn.close()
