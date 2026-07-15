from pathlib import Path

from services.arca.wsaa_login_service import WSAALoginService
from services.arca.wsaa_service import WSAAService
from services.arca.wsfe_service import WSFEService


class HomologacionService:

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
    ):
        tipo_comprobante = 11
        resultado = {
            "ok": False,
            "resultado": "",
            "cae_recibido": False,
            "cae": "",
            "vencimiento_cae": "",
            "numero_comprobante": 0,
            "punto_venta": int(punto_venta or 0) if str(punto_venta or "").strip().isdigit() else 0,
            "tipo_comprobante": tipo_comprobante,
            "fecha_comprobante": str(fecha_comprobante or "").strip(),
            "observaciones": [],
            "errores_arca": [],
            "eventos": [],
            "expiration_ticket": "",
            "errores": [],
        }

        carpeta_texto = str(carpeta_trabajo or "").strip()
        if not carpeta_texto:
            resultado["errores"].append("Carpeta de trabajo no informada.")
            return resultado

        # Guardia explicita: esta orquestacion solo puede operar contra Homologacion.
        if "wswhomo.afip.gov.ar" not in str(WSFEService.WSFE_HOMOLOGACION_URL or ""):
            resultado["errores"].append("Endpoint WSFE invalido para Homologacion.")
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
        resultado["expiration_ticket"] = str(login.get("expiration") or "")

        if not token or not sign:
            resultado["errores"].append("WSAA no devolvio credenciales de acceso validas.")
            return resultado

        consulta_ultimo = WSFEService.fe_comp_ultimo_autorizado(
            token=token,
            sign=sign,
            cuit=cuit_emisor,
            punto_venta=punto_venta,
            tipo_comprobante=tipo_comprobante,
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

        armado = WSFEService.construir_solicitud_cae(
            cuit=cuit_emisor,
            punto_venta=punto_venta,
            tipo_comprobante=tipo_comprobante,
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
            moneda="PES",
            cotizacion=1.0,
        )
        if not armado.get("ok"):
            resultado["errores"].extend(armado.get("errores") or ["No se pudo construir la solicitud CAE."])
            return resultado

        solicitud = armado.get("solicitud") or {}
        emision = WSFEService.fe_cae_solicitar(
            token=token,
            sign=sign,
            cuit=cuit_emisor,
            solicitud=solicitud,
        )

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
