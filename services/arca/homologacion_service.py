import copy
from pathlib import Path

from services.arca.wsaa_login_service import WSAALoginService
from services.arca.wsaa_service import WSAAService
from services.arca.wsfe_service import WSFEService
from services.arca.contexto_fiscal_service import ContextoFiscalService
from services.arca.preenvio_arca_service import PreenvioArcaService
from services.arca.reconciliacion_contracts import SnapshotFiscalEsperado
from services.arca import ambiente_arca


class HomologacionService:

    @staticmethod
    def _formatear_numero_textual_planificado(punto_venta, numero_comprobante):
        try:
            pv = int(punto_venta or 0)
        except (TypeError, ValueError):
            pv = 0
        try:
            nro = int(numero_comprobante or 0)
        except (TypeError, ValueError):
            nro = 0
        return f"{pv:05d}-{nro:08d}"

    @classmethod
    def _completar_contexto_fiscal_con_numero_planificado(cls, contexto_fiscal_base, numero_comprobante, punto_venta):
        """Completa EN MEMORIA el contexto fiscal base con el numero planificado ya
        obtenido via FECompUltimoAutorizado. No consulta maestros fiscales de nuevo
        ni persiste nada; la persistencia queda a cargo de PreenvioArcaService."""
        if not isinstance(contexto_fiscal_base, dict):
            raise TypeError("contexto_fiscal_base debe ser un dict.")
        contexto = copy.deepcopy(contexto_fiscal_base)
        comprobante = dict(contexto.get("comprobante") or {})
        comprobante["numero_comprobante_planificado"] = int(numero_comprobante)
        comprobante["numero_textual_planificado"] = cls._formatear_numero_textual_planificado(
            punto_venta, numero_comprobante
        )
        contexto["comprobante"] = comprobante
        return contexto

    @staticmethod
    def consultar_comprobante_emitido(
        ruta_certificado,
        ruta_clave,
        cuit_emisor,
        punto_venta,
        tipo_comprobante,
        numero_comprobante,
        carpeta_trabajo,
        token=None,
        sign=None,
        ambiente=ambiente_arca.AMBIENTE_HOMOLOGACION,
    ):
        ambiente_normalizado = ambiente_arca.normalizar_ambiente_arca(ambiente)
        wsfe_url = ambiente_arca.resolver_endpoint_wsfe(ambiente_normalizado)
        resultado = {
            "ok": False,
            "intento_id": None,
            "resultado": "",
            "cuit_emisor": "",
            "punto_venta": 0,
            "tipo_comprobante": 0,
            "numero_comprobante": 0,
            "fecha_comprobante": "",
            "doc_tipo": 0,
            "doc_nro": 0,
            "importe_total": 0.0,
            "importe_neto": 0.0,
            "importe_iva": 0.0,
            "moneda": "",
            "cotizacion": 0.0,
            "cae": "",
            "vencimiento_cae": "",
            "condicion_iva_receptor_id": 0,
            "observaciones": [],
            "errores_arca": [],
            "eventos": [],
            "status_http": 0,
            "faultcode": "",
            "faultstring": "",
            "errores": [],
        }

        carpeta_texto = str(carpeta_trabajo or "").strip()
        if not carpeta_texto:
            resultado["errores"].append("Carpeta de trabajo no informada.")
            return resultado

        token_texto = str(token or "").strip()
        sign_texto = str(sign or "").strip()
        if not token_texto or not sign_texto:
            ruta_tra = WSAAService.guardar_tra(
                Path(carpeta_texto) / "tra_wsfe_comp_consultar.xml",
                servicio="wsfe",
                duracion_segundos=3600,
            )

            login = WSAALoginService.login_homologacion(
                ruta_tra=ruta_tra,
                ruta_certificado=ruta_certificado,
                ruta_clave=ruta_clave,
                ambiente=ambiente_normalizado,
            )

            if not login.get("ok"):
                resultado["errores"].extend(login.get("errores") or ["No se pudo autenticar en WSAA."])
                if login.get("faultcode"):
                    resultado["faultcode"] = str(login.get("faultcode") or "")
                if login.get("faultstring"):
                    resultado["faultstring"] = str(login.get("faultstring") or "")
                return resultado

            token_texto = str(login.get("token") or "").strip()
            sign_texto = str(login.get("sign") or "").strip()

        if not token_texto or not sign_texto:
            resultado["errores"].append("WSAA no devolvio credenciales de acceso validas.")
            return resultado

        consulta = WSFEService.fe_comp_consultar(
            token=token_texto,
            sign=sign_texto,
            cuit=cuit_emisor,
            punto_venta=punto_venta,
            tipo_comprobante=tipo_comprobante,
            numero_comprobante=numero_comprobante,
            url=wsfe_url,
        )

        return consulta

    @staticmethod
    def emitir_comprobante_prueba(
        ruta_certificado,
        ruta_clave,
        cuit_emisor,
        punto_venta,
        tipo_comprobante,
        condicion_iva_receptor_id,
        concepto,
        tipo_documento,
        documento_receptor,
        importe_total,
        importe_neto,
        importe_iva,
        importe_exento,
        fecha_comprobante,
        carpeta_trabajo,
        importe_tot_conc=0.0,
        importe_tributos=0.0,
        alicuotas_iva=None,
        moneda="PES",
        cotizacion=1.0,
        fecha_servicio_desde=None,
        fecha_servicio_hasta=None,
        fecha_vencimiento_pago=None,
        datos_intento=None,
        contexto_fiscal_base=None,
        exigir_contexto_fiscal=False,
        preenvio_service=None,
        solicitar_cae=None,
        ambiente=ambiente_arca.AMBIENTE_HOMOLOGACION,
    ):
        try:
            tipo_comprobante_int = int(tipo_comprobante)
        except (TypeError, ValueError):
            tipo_comprobante_int = 0

        resultado = {
            "ok": False,
            "resultado": "",
            "cae_recibido": False,
            "cae": "",
            "vencimiento_cae": "",
            "token": "",
            "sign": "",
            "numero_comprobante": 0,
            "punto_venta": int(punto_venta or 0) if str(punto_venta or "").strip().isdigit() else 0,
            "tipo_comprobante": tipo_comprobante_int,
            "fecha_comprobante": str(fecha_comprobante or "").strip(),
            "observaciones": [],
            "errores_arca": [],
            "eventos": [],
            "expiration_ticket": "",
            "errores": [],
        }

        # Bloqueo explicito de pre-Produccion: debe ocurrir antes de crear
        # cualquier intento o de tocar WSAA/WSFE, para nunca emitir real todavia.
        try:
            ambiente_normalizado = ambiente_arca.asegurar_emision_habilitada(ambiente)
        except (ambiente_arca.AmbienteArcaInvalidoError, ambiente_arca.EmisionProduccionNoHabilitadaError) as error:
            resultado["errores"].append(str(error))
            return resultado

        carpeta_texto = str(carpeta_trabajo or "").strip()
        if not carpeta_texto:
            resultado["errores"].append("Carpeta de trabajo no informada.")
            return resultado

        wsfe_url = ambiente_arca.resolver_endpoint_wsfe(ambiente_normalizado)

        # Guardia explicita: en Homologacion, el endpoint WSFE resuelto debe seguir siendo el de Homologacion.
        if ambiente_normalizado == ambiente_arca.AMBIENTE_HOMOLOGACION and "wswhomo.afip.gov.ar" not in wsfe_url:
            resultado["errores"].append("Endpoint WSFE invalido para Homologacion.")
            return resultado

        if exigir_contexto_fiscal and contexto_fiscal_base is None:
            resultado["errores"].append("Contexto fiscal base obligatorio para la ruta de emision fiscal real.")
            return resultado

        ruta_tra = WSAAService.guardar_tra(
            Path(carpeta_texto) / "tra_wsfe_emitir.xml",
            servicio="wsfe",
            duracion_segundos=3600,
        )

        login = WSAALoginService.login_homologacion(
            ruta_tra=ruta_tra,
            ruta_certificado=ruta_certificado,
            ruta_clave=ruta_clave,
            ambiente=ambiente_normalizado,
        )
        if not login.get("ok"):
            resultado["errores"].extend(login.get("errores") or ["No se pudo autenticar en WSAA."])
            if login.get("faultcode"):
                resultado["errores"].append(f"WSAA faultcode: {login.get('faultcode')}")
            if login.get("faultstring"):
                resultado["errores"].append(f"WSAA faultstring: {login.get('faultstring')}")
            return resultado

        token = str(login.get("token") or "").strip()
        sign = str(login.get("sign") or "").strip()
        resultado["token"] = token
        resultado["sign"] = sign
        resultado["expiration_ticket"] = str(login.get("expiration") or "")

        if not token or not sign:
            resultado["errores"].append("WSAA no devolvio credenciales de acceso validas.")
            return resultado

        consulta_ultimo = WSFEService.fe_comp_ultimo_autorizado(
            token=token,
            sign=sign,
            cuit=cuit_emisor,
            punto_venta=punto_venta,
            tipo_comprobante=tipo_comprobante_int,
            url=wsfe_url,
        )
        if not consulta_ultimo.get("ok"):
            resultado["errores"].extend(
                consulta_ultimo.get("errores") or ["No se pudo consultar el ultimo comprobante."]
            )
            return resultado

        try:
            ultimo_numero = int(consulta_ultimo.get("ultimo_numero") or 0)
        except (TypeError, ValueError):
            resultado["errores"].append("Ultimo numero de comprobante invalido.")
            return resultado

        if ultimo_numero < 0:
            resultado["errores"].append("Ultimo numero de comprobante invalido.")
            return resultado

        numero_comprobante = ultimo_numero + 1
        resultado["numero_comprobante"] = numero_comprobante

        contexto_fiscal_completo = None
        if contexto_fiscal_base is not None:
            try:
                contexto_fiscal_completo = HomologacionService._completar_contexto_fiscal_con_numero_planificado(
                    contexto_fiscal_base, numero_comprobante, punto_venta
                )
            except TypeError as error:
                resultado["errores"].append(f"Contexto fiscal base inválido: {error}")
                return resultado

            validacion_contexto = ContextoFiscalService.validar(contexto_fiscal_completo)
            if not validacion_contexto.valido:
                resultado["errores"].append(
                    "Contexto fiscal inválido antes de emitir: " + "; ".join(validacion_contexto.errores)
                )
                return resultado

        armado = WSFEService.construir_solicitud_cae(
            cuit=cuit_emisor,
            punto_venta=punto_venta,
            tipo_comprobante=tipo_comprobante_int,
            numero_comprobante=numero_comprobante,
            condicion_iva_receptor_id=condicion_iva_receptor_id,
            concepto=concepto,
            documento_receptor=documento_receptor,
            tipo_documento=tipo_documento,
            importe=importe_total,
            importe_neto=importe_neto,
            importe_iva=importe_iva,
            importe_exento=importe_exento,
            fecha_comprobante=fecha_comprobante,
            moneda=moneda,
            cotizacion=cotizacion,
            importe_tot_conc=importe_tot_conc,
            importe_tributos=importe_tributos,
            alicuotas_iva=alicuotas_iva,
            fecha_servicio_desde=fecha_servicio_desde,
            fecha_servicio_hasta=fecha_servicio_hasta,
            fecha_vencimiento_pago=fecha_vencimiento_pago,
        )
        if not armado.get("ok"):
            resultado["errores"].extend(armado.get("errores") or ["No se pudo construir la solicitud CAE."])
            return resultado

        solicitud = armado.get("solicitud") or {}
        if not isinstance(datos_intento, dict):
            resultado["errores"].append("Faltan datos del intento persistente antes de enviar a ARCA.")
            return resultado

        try:
            solicitud_cae = solicitud["FeCAEReq"]
            cabecera = solicitud_cae["FeCabReq"]
            detalle = solicitud_cae["FeDetReq"]["FECAEDetRequest"][0]
            alicuotas_snapshot = detalle.get("Iva", {}).get("AlicIva", [])
            snapshot = SnapshotFiscalEsperado(
                resumen_id=int(datos_intento["resumen_id"]),
                cliente_id=int(datos_intento["cliente_id"]),
                emisor_fiscal_id=int(datos_intento["emisor_fiscal_id"]),
                emisor_id=int(datos_intento["emisor_id"]),
                cuit_emisor=str(solicitud.get("Cuit") or ""),
                punto_venta=int(cabecera["PtoVta"]),
                tipo_comprobante=int(cabecera["CbteTipo"]),
                numero_planificado=int(detalle["CbteDesde"]),
                fecha_comprobante=str(detalle["CbteFch"]),
                concepto=int(detalle["Concepto"]),
                tipo_documento=int(detalle["DocTipo"]),
                documento_receptor=int(detalle["DocNro"]),
                condicion_iva_receptor_id=int(detalle["CondicionIVAReceptorId"]),
                importe_total=detalle["ImpTotal"],
                importe_neto=detalle["ImpNeto"],
                importe_iva=detalle["ImpIVA"],
                importe_exento=detalle["ImpOpEx"],
                importe_no_gravado=detalle["ImpTotConc"],
                importe_tributos=detalle["ImpTrib"],
                moneda=str(detalle["MonId"]),
                cotizacion=detalle["MonCotiz"],
                alicuotas_iva=tuple(alicuotas_snapshot),
            )
        except (IndexError, KeyError, TypeError, ValueError) as error:
            resultado["errores"].append(f"No se pudo preparar el intento ARCA: {error}")
            return resultado

        enviar = solicitar_cae or WSFEService.fe_cae_solicitar
        preenvio = preenvio_service or PreenvioArcaService()
        enviar_fecae = lambda: enviar(token=token, sign=sign, cuit=cuit_emisor, solicitud=solicitud, url=wsfe_url)
        if contexto_fiscal_completo is not None:
            protegido = preenvio.enviar_una_vez_con_contexto(snapshot, contexto_fiscal_completo, enviar_fecae)
        else:
            protegido = preenvio.enviar_una_vez(snapshot, enviar_fecae)
        resultado["intento_id"] = protegido.intento_id
        if not protegido.ok:
            resultado["errores"].extend(protegido.errores or ("No se pudo enviar FECAESolicitar.",))
            return resultado

        emision = protegido.respuesta or {}

        resultado["resultado"] = str(emision.get("resultado") or "")
        resultado["cae"] = str(emision.get("cae") or "")
        resultado["vencimiento_cae"] = str(emision.get("vencimiento_cae") or "")
        resultado["fecha_comprobante"] = str(emision.get("fecha_comprobante") or resultado["fecha_comprobante"])
        resultado["observaciones"] = list(emision.get("observaciones") or [])
        resultado["errores_arca"] = list(emision.get("errores_arca") or [])
        resultado["eventos"] = list(emision.get("eventos") or [])
        if emision.get("numero_comprobante"):
            resultado["numero_comprobante"] = int(emision.get("numero_comprobante") or numero_comprobante)

        if not emision.get("ok"):
            resultado["errores"].extend(
                emision.get("errores") or ["ARCA rechazo la solicitud FECAESolicitar."]
            )
            return resultado

        resultado["ok"] = True
        resultado["cae_recibido"] = bool(resultado["cae"])
        return resultado

    @staticmethod
    def emitir_factura_c_prueba(
        ruta_certificado,
        ruta_clave,
        cuit_emisor,
        punto_venta,
        condicion_iva_receptor_id,
        concepto,
        tipo_documento,
        documento_receptor,
        importe_total,
        importe_neto,
        importe_iva,
        importe_exento,
        fecha_comprobante,
        carpeta_trabajo,
        fecha_servicio_desde=None,
        fecha_servicio_hasta=None,
        fecha_vencimiento_pago=None,
    ):
        return HomologacionService.emitir_comprobante_prueba(
            ruta_certificado=ruta_certificado,
            ruta_clave=ruta_clave,
            cuit_emisor=cuit_emisor,
            punto_venta=punto_venta,
            tipo_comprobante=11,
            condicion_iva_receptor_id=condicion_iva_receptor_id,
            concepto=concepto,
            tipo_documento=tipo_documento,
            documento_receptor=documento_receptor,
            importe_total=importe_total,
            importe_neto=importe_neto,
            importe_iva=importe_iva,
            importe_exento=importe_exento,
            fecha_comprobante=fecha_comprobante,
            carpeta_trabajo=carpeta_trabajo,
            fecha_servicio_desde=fecha_servicio_desde,
            fecha_servicio_hasta=fecha_servicio_hasta,
            fecha_vencimiento_pago=fecha_vencimiento_pago,
        )

    @staticmethod
    def consultar_ultimo_comprobante(
        ruta_certificado,
        ruta_clave,
        cuit,
        punto_venta,
        tipo_comprobante,
        carpeta_trabajo,
    ):
        resultado = {
            "ok": False,
            "ultimo_numero": 0,
            "punto_venta": punto_venta,
            "tipo_comprobante": tipo_comprobante,
            "expiration": "",
            "errores": [],
        }

        carpeta_texto = str(carpeta_trabajo or "").strip()
        if not carpeta_texto:
            resultado["errores"].append("Carpeta de trabajo no informada.")
            return resultado

        ruta_tra = WSAAService.guardar_tra(
            Path(carpeta_texto) / "tra_wsfe.xml",
            servicio="wsfe",
            duracion_segundos=3600,
        )

        login = WSAALoginService.login_homologacion(
            ruta_tra=ruta_tra,
            ruta_certificado=ruta_certificado,
            ruta_clave=ruta_clave,
        )

        if not login.get("ok"):
            resultado["errores"].extend(login.get("errores") or ["No se pudo autenticar en WSAA."])
            if login.get("faultcode"):
                resultado["errores"].append(f"WSAA faultcode: {login.get('faultcode')}")
            if login.get("faultstring"):
                resultado["errores"].append(f"WSAA faultstring: {login.get('faultstring')}")
            return resultado

        consulta = WSFEService.fe_comp_ultimo_autorizado(
            token=login.get("token", ""),
            sign=login.get("sign", ""),
            cuit=cuit,
            punto_venta=punto_venta,
            tipo_comprobante=tipo_comprobante,
        )

        resultado["ok"] = bool(consulta.get("ok"))
        resultado["ultimo_numero"] = int(consulta.get("ultimo_numero") or 0)
        resultado["expiration"] = login.get("expiration", "")
        if not resultado["ok"]:
            resultado["errores"].extend(consulta.get("errores") or ["No se pudo consultar el último comprobante."])
        return resultado
