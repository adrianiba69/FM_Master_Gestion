import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime
from decimal import Decimal, InvalidOperation

from services.arca import ambiente_arca


class WSFEService:
    WSFE_HOMOLOGACION_URL = ambiente_arca.WSFE_URLS[ambiente_arca.AMBIENTE_HOMOLOGACION]
    WSFE_PRODUCCION_URL = ambiente_arca.WSFE_URLS[ambiente_arca.AMBIENTE_PRODUCCION]
    SOAP_ACTION_FEDUMMY = "http://ar.gov.afip.dif.FEV1/FEDummy"
    SOAP_ACTION_ULTIMO_AUTORIZADO = "http://ar.gov.afip.dif.FEV1/FECompUltimoAutorizado"
    SOAP_ACTION_COMP_CONSULTAR = "http://ar.gov.afip.dif.FEV1/FECompConsultar"
    SOAP_ACTION_FECAE_SOLICITAR = "http://ar.gov.afip.dif.FEV1/FECAESolicitar"
    TIMEOUT_SEGUNDOS = 20

    @staticmethod
    def construir_solicitud_cae(
        cuit,
        punto_venta,
        tipo_comprobante,
        numero_comprobante,
        condicion_iva_receptor_id,
        concepto,
        documento_receptor,
        tipo_documento,
        importe,
        importe_neto,
        importe_iva,
        importe_exento,
        fecha_comprobante,
        moneda,
        cotizacion,
        importe_tot_conc=0.0,
        importe_tributos=0.0,
        alicuotas_iva=None,
        fecha_servicio_desde=None,
        fecha_servicio_hasta=None,
        fecha_vencimiento_pago=None,
    ):
        errores = []

        cuit_texto = str(cuit or "").strip()
        documento_raw = documento_receptor
        documento_texto = "" if documento_raw is None else str(documento_raw).strip()
        fecha_texto = str(fecha_comprobante or "").strip()
        fecha_serv_desde_texto = str(fecha_servicio_desde or "").strip()
        fecha_serv_hasta_texto = str(fecha_servicio_hasta or "").strip()
        fecha_vto_pago_texto = str(fecha_vencimiento_pago or "").strip()
        moneda_texto = str(moneda or "").strip()

        if not cuit_texto:
            errores.append("CUIT obligatorio.")
        if not fecha_texto:
            errores.append("Fecha comprobante obligatoria.")
        elif not WSFEService._es_fecha_yyyymmdd(fecha_texto):
            errores.append("Fecha comprobante inválida. Debe tener formato YYYYMMDD.")
        if not moneda_texto:
            errores.append("Moneda obligatoria.")

        try:
            pto_vta = int(punto_venta)
            if pto_vta <= 0:
                raise ValueError()
        except (TypeError, ValueError):
            errores.append("Punto de venta inválido.")
            pto_vta = 0

        try:
            cbte_tipo = int(tipo_comprobante)
            if cbte_tipo <= 0:
                raise ValueError()
        except (TypeError, ValueError):
            errores.append("Tipo de comprobante inválido.")
            cbte_tipo = 0

        try:
            cbte_numero = int(numero_comprobante)
            if cbte_numero <= 0:
                raise ValueError()
        except (TypeError, ValueError):
            errores.append("Número de comprobante inválido.")
            cbte_numero = 0

        try:
            cond_iva_receptor = int(condicion_iva_receptor_id)
            if cond_iva_receptor <= 0:
                raise ValueError()
        except (TypeError, ValueError):
            errores.append("Condición IVA receptor inválida.")
            cond_iva_receptor = 0

        try:
            concepto_val = int(concepto)
            if concepto_val not in {1, 2, 3}:
                raise ValueError()
        except (TypeError, ValueError):
            errores.append("Concepto inválido. Debe ser 1, 2 o 3.")
            concepto_val = 0

        try:
            doc_tipo = int(tipo_documento)
        except (TypeError, ValueError):
            errores.append("Tipo de documento inválido.")
            doc_tipo = 0

        if documento_raw is None or (isinstance(documento_raw, str) and documento_texto == ""):
            errores.append("Documento receptor obligatorio.")
            doc_nro = 0
        else:
            try:
                doc_nro = int(documento_texto)
            except (TypeError, ValueError):
                errores.append("Documento receptor inválido.")
                doc_nro = 0
            else:
                if doc_nro < 0:
                    errores.append("Documento receptor inválido.")
                elif doc_tipo == 99 and doc_nro != 0:
                    errores.append("Documento receptor inválido para DocTipo 99: debe ser 0.")
                elif doc_tipo != 99 and doc_nro <= 0:
                    errores.append("Documento receptor inválido: debe ser mayor que 0 para este tipo de documento.")

        try:
            imp_total = round(float(importe), 2)
        except (TypeError, ValueError):
            errores.append("Importe total inválido.")
            imp_total = 0.0

        try:
            imp_neto = round(float(importe_neto), 2)
        except (TypeError, ValueError):
            errores.append("Importe neto inválido.")
            imp_neto = 0.0

        try:
            imp_iva = round(float(importe_iva), 2)
        except (TypeError, ValueError):
            errores.append("Importe IVA inválido.")
            imp_iva = 0.0

        try:
            imp_exento = round(float(importe_exento), 2)
        except (TypeError, ValueError):
            errores.append("Importe exento inválido.")
            imp_exento = 0.0

        try:
            imp_tot_conc = round(float(importe_tot_conc), 2)
        except (TypeError, ValueError):
            errores.append("Importe no gravado inválido.")
            imp_tot_conc = 0.0

        try:
            imp_trib = round(float(importe_tributos), 2)
        except (TypeError, ValueError):
            errores.append("Importe tributos inválido.")
            imp_trib = 0.0

        try:
            mon_cotiz = round(float(cotizacion), 6)
            if mon_cotiz <= 0:
                raise ValueError()
        except (TypeError, ValueError):
            errores.append("Cotización inválida.")
            mon_cotiz = 0.0

        if imp_total <= 0:
            errores.append("El importe total debe ser mayor a cero.")
        if imp_neto < 0 or imp_iva < 0 or imp_exento < 0 or imp_tot_conc < 0 or imp_trib < 0:
            errores.append("Importes no pueden ser negativos.")

        suma_componentes = round(imp_neto + imp_iva + imp_exento + imp_tot_conc + imp_trib, 2)
        if round(imp_total, 2) != suma_componentes:
            errores.append("Los totales no cierran: importe total debe igualar neto + IVA + exento + no gravado + tributos.")

        if imp_iva > 0 and imp_neto <= 0:
            errores.append("IVA inválido: si hay IVA, el importe neto debe ser mayor a cero.")

        alicuotas = []
        if alicuotas_iva is None:
            alicuotas_iva = []

        if not isinstance(alicuotas_iva, list):
            errores.append("Alicuotas de IVA inválidas.")
            alicuotas_iva = []

        suma_iva_alicuotas = 0.0
        suma_base_alicuotas = 0.0
        for item in alicuotas_iva:
            if not isinstance(item, dict):
                errores.append("Alicuotas de IVA inválidas.")
                continue

            try:
                iva_id = int(item.get("id"))
                if iva_id <= 0:
                    raise ValueError()
            except (TypeError, ValueError):
                errores.append("ID de alícuota IVA inválido.")
                continue

            try:
                base_imp = round(float(item.get("base_imponible")), 2)
                if base_imp < 0:
                    raise ValueError()
            except (TypeError, ValueError):
                errores.append("Base imponible de alícuota IVA inválida.")
                continue

            try:
                importe_alic = round(float(item.get("importe")), 2)
                if importe_alic < 0:
                    raise ValueError()
            except (TypeError, ValueError):
                errores.append("Importe de alícuota IVA inválido.")
                continue

            alicuotas.append({
                "Id": iva_id,
                "BaseImp": base_imp,
                "Importe": importe_alic,
            })
            suma_base_alicuotas += base_imp
            suma_iva_alicuotas += importe_alic

        suma_base_alicuotas = round(suma_base_alicuotas, 2)
        suma_iva_alicuotas = round(suma_iva_alicuotas, 2)

        if imp_iva > 0 and not alicuotas:
            errores.append("Debe informar detalle de alícuotas IVA cuando ImpIVA es mayor a cero.")
        if imp_iva > 0 and alicuotas and round(imp_iva, 2) != suma_iva_alicuotas:
            errores.append("ImpIVA no coincide con la suma de alícuotas IVA.")
        if imp_iva > 0 and alicuotas and round(imp_neto, 2) != suma_base_alicuotas:
            errores.append("ImpNeto no coincide con la base imponible total de alícuotas IVA.")

        if concepto_val in {2, 3}:
            if not fecha_serv_desde_texto:
                errores.append("FchServDesde obligatoria para concepto 2/3.")
            elif not WSFEService._es_fecha_yyyymmdd(fecha_serv_desde_texto):
                errores.append("FchServDesde inválida. Debe tener formato YYYYMMDD.")

            if not fecha_serv_hasta_texto:
                errores.append("FchServHasta obligatoria para concepto 2/3.")
            elif not WSFEService._es_fecha_yyyymmdd(fecha_serv_hasta_texto):
                errores.append("FchServHasta inválida. Debe tener formato YYYYMMDD.")

            if not fecha_vto_pago_texto:
                errores.append("FchVtoPago obligatoria para concepto 2/3.")
            elif not WSFEService._es_fecha_yyyymmdd(fecha_vto_pago_texto):
                errores.append("FchVtoPago inválida. Debe tener formato YYYYMMDD.")

            if (
                WSFEService._es_fecha_yyyymmdd(fecha_serv_desde_texto)
                and WSFEService._es_fecha_yyyymmdd(fecha_serv_hasta_texto)
                and fecha_serv_desde_texto > fecha_serv_hasta_texto
            ):
                errores.append("Rango de servicio inválido: FchServDesde no puede ser mayor que FchServHasta.")

        if errores:
            return {
                "ok": False,
                "solicitud": {},
                "errores": errores,
            }

        print("DOC TIPO FINAL =", doc_tipo)
        print("DOC NRO FINAL =", doc_nro)

        detalle = {
            "Concepto": concepto_val,
            "DocTipo": doc_tipo,
            "DocNro": doc_nro,
            "CbteDesde": cbte_numero,
            "CbteHasta": cbte_numero,
            "CbteFch": fecha_texto,
        }

        if concepto_val in {2, 3}:
            detalle["FchServDesde"] = fecha_serv_desde_texto
            detalle["FchServHasta"] = fecha_serv_hasta_texto
            detalle["FchVtoPago"] = fecha_vto_pago_texto

        detalle.update({
            "CondicionIVAReceptorId": cond_iva_receptor,
            "ImpTotal": imp_total,
            "ImpTotConc": imp_tot_conc,
            "ImpNeto": imp_neto,
            "ImpOpEx": imp_exento,
            "ImpTrib": imp_trib,
            "ImpIVA": imp_iva,
            "MonId": moneda_texto,
            "MonCotiz": mon_cotiz,
        })

        if alicuotas:
            detalle["Iva"] = {"AlicIva": alicuotas}

        solicitud = {
            "FeCAEReq": {
                "FeCabReq": {
                    "CantReg": 1,
                    "PtoVta": pto_vta,
                    "CbteTipo": cbte_tipo,
                },
                "FeDetReq": {
                    "FECAEDetRequest": [detalle]
                },
            },
            "Cuit": cuit_texto,
        }

        return {
            "ok": True,
            "solicitud": solicitud,
        }

    @staticmethod
    def fedummy():
        resultado = {
            "ok": False,
            "appserver": "",
            "dbserver": "",
            "authserver": "",
            "status_http": 0,
            "faultcode": "",
            "faultstring": "",
            "errores": [],
        }

        soap_body = WSFEService._construir_soap_fedummy()
        request = urllib.request.Request(
            url=WSFEService.WSFE_HOMOLOGACION_URL,
            data=soap_body.encode("utf-8"),
            method="POST",
            headers={
                "Content-Type": "text/xml; charset=UTF-8",
                "SOAPAction": WSFEService.SOAP_ACTION_FEDUMMY,
            },
        )

        try:
            with urllib.request.urlopen(request, timeout=WSFEService.TIMEOUT_SEGUNDOS) as response:
                status_http = getattr(response, "status", getattr(response, "code", 200))
                response_xml = response.read().decode("utf-8", errors="replace")
                resultado["status_http"] = int(status_http or 200)
                if resultado["status_http"] >= 400:
                    resultado["errores"].append(f"HTTP {resultado['status_http']} al invocar FEDummy.")
                    parseo_http = WSFEService._parsear_fault_o_error(response_xml)
                    resultado["faultcode"] = parseo_http.get("faultcode", "")
                    resultado["faultstring"] = parseo_http.get("faultstring", "")
                    resultado["errores"].extend(parseo_http["errores"])
                    resultado.update({
                        "appserver": parseo_http.get("appserver", ""),
                        "dbserver": parseo_http.get("dbserver", ""),
                        "authserver": parseo_http.get("authserver", ""),
                    })
                    return resultado
        except urllib.error.HTTPError as error:
            resultado["status_http"] = int(getattr(error, "code", 0) or 0)
            cuerpo = ""
            try:
                cuerpo = error.read().decode("utf-8", errors="replace")
            except Exception:
                cuerpo = ""
            resultado["errores"].append(f"HTTP {error.code} al invocar FEDummy.")
            parseo_http = WSFEService._parsear_fault_o_error(cuerpo)
            resultado["faultcode"] = parseo_http.get("faultcode", "")
            resultado["faultstring"] = parseo_http.get("faultstring", "")
            resultado["errores"].extend(parseo_http["errores"])
            resultado.update({
                "appserver": parseo_http.get("appserver", ""),
                "dbserver": parseo_http.get("dbserver", ""),
                "authserver": parseo_http.get("authserver", ""),
            })
            return resultado
        except urllib.error.URLError as error:
            resultado["errores"].append(f"No se pudo conectar con WSFEv1 de Homologación: {error.reason}")
            return resultado
        except TimeoutError:
            resultado["errores"].append("Tiempo de espera agotado al invocar FEDummy.")
            return resultado
        except Exception as error:
            resultado["errores"].append(f"Error inesperado al invocar FEDummy: {error}")
            return resultado

        parseo = WSFEService._parsear_respuesta(response_xml)
        resultado["status_http"] = int(resultado.get("status_http") or 200)
        if not parseo["ok"]:
            resultado["faultcode"] = parseo.get("faultcode", "")
            resultado["faultstring"] = parseo.get("faultstring", "")
            resultado["errores"].extend(parseo["errores"])
            return resultado

        resultado["ok"] = True
        resultado["appserver"] = parseo["appserver"]
        resultado["dbserver"] = parseo["dbserver"]
        resultado["authserver"] = parseo["authserver"]
        return resultado

    @staticmethod
    def fe_comp_ultimo_autorizado(token, sign, cuit, punto_venta, tipo_comprobante, url=None):
        resultado = {
            "ok": False,
            "ultimo_numero": 0,
            "status_http": 0,
            "faultcode": "",
            "faultstring": "",
            "errores": [],
        }

        token_texto = str(token or "").strip()
        sign_texto = str(sign or "").strip()
        cuit_texto = "".join(ch for ch in str(cuit or "").strip() if ch.isdigit())

        if not token_texto:
            resultado["errores"].append("Token no informado.")
            return resultado
        if not sign_texto:
            resultado["errores"].append("Sign no informado.")
            return resultado
        if not cuit_texto:
            resultado["errores"].append("CUIT no informado.")
            return resultado
        if len(cuit_texto) != 11:
            resultado["errores"].append("CUIT inválido.")
            return resultado

        try:
            pto_vta = int(punto_venta)
        except (TypeError, ValueError):
            resultado["errores"].append("Punto de venta inválido.")
            return resultado

        try:
            cbte_tipo = int(tipo_comprobante)
        except (TypeError, ValueError):
            resultado["errores"].append("Tipo de comprobante inválido.")
            return resultado

        soap_body = WSFEService._construir_soap_ultimo_autorizado(
            token_texto,
            sign_texto,
            cuit_texto,
            pto_vta,
            cbte_tipo,
        )
        request = urllib.request.Request(
            url=(url or WSFEService.WSFE_HOMOLOGACION_URL),
            data=soap_body.encode("utf-8"),
            method="POST",
            headers={
                "Content-Type": "text/xml; charset=UTF-8",
                "SOAPAction": WSFEService.SOAP_ACTION_ULTIMO_AUTORIZADO,
            },
        )

        try:
            with urllib.request.urlopen(request, timeout=WSFEService.TIMEOUT_SEGUNDOS) as response:
                status_http = getattr(response, "status", getattr(response, "code", 200))
                response_xml = response.read().decode("utf-8", errors="replace")
                resultado["status_http"] = int(status_http or 200)
                if resultado["status_http"] >= 400:
                    resultado["errores"].append(
                        f"HTTP {resultado['status_http']} al invocar FECompUltimoAutorizado."
                    )
                    fault = WSFEService._parsear_fault_generico(response_xml)
                    resultado["faultcode"] = fault.get("faultcode", "")
                    resultado["faultstring"] = fault.get("faultstring", "")
                    resultado["errores"].extend(fault.get("errores", []))
                    return resultado
        except urllib.error.HTTPError as error:
            resultado["status_http"] = int(getattr(error, "code", 0) or 0)
            cuerpo = ""
            try:
                cuerpo = error.read().decode("utf-8", errors="replace")
            except Exception:
                cuerpo = ""
            resultado["errores"].append(f"HTTP {error.code} al invocar FECompUltimoAutorizado.")
            fault = WSFEService._parsear_fault_generico(cuerpo)
            resultado["faultcode"] = fault.get("faultcode", "")
            resultado["faultstring"] = fault.get("faultstring", "")
            resultado["errores"].extend(fault.get("errores", []))
            return resultado
        except urllib.error.URLError as error:
            resultado["errores"].append(
                f"No se pudo conectar con WSFEv1 de Homologación: {error.reason}"
            )
            return resultado
        except TimeoutError:
            resultado["errores"].append("Tiempo de espera agotado al invocar FECompUltimoAutorizado.")
            return resultado
        except Exception as error:
            resultado["errores"].append(f"Error inesperado al invocar FECompUltimoAutorizado: {error}")
            return resultado

        parseo = WSFEService._parsear_respuesta_ultimo_autorizado(response_xml)
        resultado["status_http"] = int(resultado.get("status_http") or 200)
        if not parseo["ok"]:
            resultado["faultcode"] = parseo.get("faultcode", "")
            resultado["faultstring"] = parseo.get("faultstring", "")
            resultado["errores"].extend(parseo["errores"])
            return resultado

        resultado["ok"] = True
        resultado["ultimo_numero"] = parseo["ultimo_numero"]
        return resultado

    @staticmethod
    def fe_cae_solicitar(token, sign, cuit, solicitud, url=None):
        resultado = {
            "ok": False,
            "resultado": "",
            "cae": "",
            "vencimiento_cae": "",
            "numero_comprobante": 0,
            "fecha_comprobante": "",
            "observaciones": [],
            "errores_arca": [],
            "eventos": [],
            "status_http": 0,
            "faultcode": "",
            "faultstring": "",
            "errores": [],
        }

        token_texto = str(token or "").strip()
        sign_texto = str(sign or "").strip()
        cuit_texto = str(cuit or "").strip()

        if not token_texto:
            resultado["errores"].append("Token no informado.")
            return resultado
        if not sign_texto:
            resultado["errores"].append("Sign no informado.")
            return resultado
        if not cuit_texto or not cuit_texto.isdigit() or len(cuit_texto) != 11:
            resultado["errores"].append("CUIT inválido.")
            return resultado

        if not isinstance(solicitud, dict):
            resultado["errores"].append("Solicitud inválida.")
            return resultado

        fe_cae_req = solicitud.get("FeCAEReq")
        if not isinstance(fe_cae_req, dict):
            resultado["errores"].append("Solicitud inválida: falta FeCAEReq.")
            return resultado

        fe_cab_req = fe_cae_req.get("FeCabReq")
        fe_det_req = fe_cae_req.get("FeDetReq")
        if not isinstance(fe_cab_req, dict):
            resultado["errores"].append("Solicitud inválida: falta FeCabReq.")
            return resultado
        if not isinstance(fe_det_req, dict):
            resultado["errores"].append("Solicitud inválida: falta FeDetReq.")
            return resultado

        soap_body = WSFEService._construir_soap_cae_solicitar(
            token=token_texto,
            sign=sign_texto,
            cuit=cuit_texto,
            fe_cae_req=fe_cae_req,
        )

        # DEBUG deshabilitado: Descomentar solo si se necesita inspeccionar SOAP
        # try:
        #     import os
        #     carpeta_debug = r"C:\FM_Master_Certificados"
        #     os.makedirs(carpeta_debug, exist_ok=True)
        #     archivo_debug = os.path.join(carpeta_debug, "debug_fecae.xml")
        #     soap_sanitizado = WSFEService.construir_soap_cae_sanitizado(
        #         cuit=cuit_texto,
        #         solicitud=solicitud,
        #     )
        #     with open(archivo_debug, "w", encoding="utf-8") as f:
        #         f.write(soap_sanitizado)
        #     print(f"DEBUG ARCA SOAP - Guardado en: {archivo_debug}")
        # except Exception as e:
        #     print(f"DEBUG ARCA SOAP - Error al guardar: {e}")

        request = urllib.request.Request(
            url=(url or WSFEService.WSFE_HOMOLOGACION_URL),
            data=soap_body.encode("utf-8"),
            method="POST",
            headers={
                "Content-Type": "text/xml; charset=UTF-8",
                "SOAPAction": WSFEService.SOAP_ACTION_FECAE_SOLICITAR,
            },
        )

        try:
            with urllib.request.urlopen(request, timeout=WSFEService.TIMEOUT_SEGUNDOS) as response:
                status_http = getattr(response, "status", getattr(response, "code", 200))
                response_xml = response.read().decode("utf-8", errors="replace")
                resultado["status_http"] = int(status_http or 200)
                if resultado["status_http"] >= 400:
                    resultado["errores"].append(
                        f"HTTP {resultado['status_http']} al invocar FECAESolicitar."
                    )
                    fault = WSFEService._parsear_fault_generico(response_xml)
                    resultado["faultcode"] = fault.get("faultcode", "")
                    resultado["faultstring"] = fault.get("faultstring", "")
                    resultado["errores"].extend(fault.get("errores", []))
                    return resultado
        except urllib.error.HTTPError as error:
            resultado["status_http"] = int(getattr(error, "code", 0) or 0)
            cuerpo = ""
            try:
                cuerpo = error.read().decode("utf-8", errors="replace")
            except Exception:
                cuerpo = ""
            resultado["errores"].append(f"HTTP {error.code} al invocar FECAESolicitar.")
            fault = WSFEService._parsear_fault_generico(cuerpo)
            resultado["faultcode"] = fault.get("faultcode", "")
            resultado["faultstring"] = fault.get("faultstring", "")
            resultado["errores"].extend(fault.get("errores", []))
            return resultado
        except urllib.error.URLError as error:
            resultado["errores"].append(
                f"No se pudo conectar con WSFEv1 de Homologación: {error.reason}"
            )
            return resultado
        except TimeoutError:
            resultado["errores"].append("Tiempo de espera agotado al invocar FECAESolicitar.")
            return resultado
        except Exception as error:
            resultado["errores"].append(f"Error inesperado al invocar FECAESolicitar: {error}")
            return resultado

        parseo = WSFEService._parsear_respuesta_cae_solicitar(response_xml)
        resultado["status_http"] = int(resultado.get("status_http") or 200)
        resultado["resultado"] = parseo.get("resultado", "")
        resultado["cae"] = parseo.get("cae", "")
        resultado["vencimiento_cae"] = parseo.get("vencimiento_cae", "")
        resultado["numero_comprobante"] = parseo.get("numero_comprobante", 0)
        resultado["fecha_comprobante"] = parseo.get("fecha_comprobante", "")
        resultado["observaciones"] = parseo.get("observaciones", [])
        resultado["errores_arca"] = parseo.get("errores_arca", [])
        resultado["eventos"] = parseo.get("eventos", [])
        resultado["faultcode"] = parseo.get("faultcode", "")
        resultado["faultstring"] = parseo.get("faultstring", "")

        if not parseo.get("ok"):
            resultado["errores"].extend(parseo.get("errores", ["WSFEv1 rechazó la solicitud FECAESolicitar."]))
            return resultado

        resultado["ok"] = True
        return resultado

    @staticmethod
    def fe_comp_consultar(token, sign, cuit, punto_venta, tipo_comprobante, numero_comprobante, url=None):
        resultado = {
            "ok": False,
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

        token_texto = str(token or "").strip()
        sign_texto = str(sign or "").strip()
        cuit_texto = str(cuit or "").strip()

        if not token_texto:
            resultado["errores"].append("Token no informado.")
            return resultado
        if not sign_texto:
            resultado["errores"].append("Sign no informado.")
            return resultado
        if not cuit_texto or not cuit_texto.isdigit() or len(cuit_texto) != 11:
            resultado["errores"].append("CUIT inválido.")
            return resultado

        try:
            pto_vta = int(punto_venta)
            if pto_vta <= 0:
                raise ValueError()
        except (TypeError, ValueError):
            resultado["errores"].append("Punto de venta inválido.")
            return resultado

        try:
            cbte_tipo = int(tipo_comprobante)
            if cbte_tipo <= 0:
                raise ValueError()
        except (TypeError, ValueError):
            resultado["errores"].append("Tipo de comprobante inválido.")
            return resultado

        try:
            cbte_nro = int(numero_comprobante)
            if cbte_nro <= 0:
                raise ValueError()
        except (TypeError, ValueError):
            resultado["errores"].append("Número de comprobante inválido.")
            return resultado

        soap_body = WSFEService._construir_soap_comp_consultar(
            token=token_texto,
            sign=sign_texto,
            cuit=cuit_texto,
            punto_venta=pto_vta,
            tipo_comprobante=cbte_tipo,
            numero_comprobante=cbte_nro,
        )
        request = urllib.request.Request(
            url=(url or WSFEService.WSFE_HOMOLOGACION_URL),
            data=soap_body.encode("utf-8"),
            method="POST",
            headers={
                "Content-Type": "text/xml; charset=UTF-8",
                "SOAPAction": WSFEService.SOAP_ACTION_COMP_CONSULTAR,
            },
        )

        try:
            with urllib.request.urlopen(request, timeout=WSFEService.TIMEOUT_SEGUNDOS) as response:
                status_http = getattr(response, "status", getattr(response, "code", 200))
                response_xml = response.read().decode("utf-8", errors="replace")
                resultado["status_http"] = int(status_http or 200)
                if resultado["status_http"] >= 400:
                    resultado["errores"].append(
                        f"HTTP {resultado['status_http']} al invocar FECompConsultar."
                    )
                    fault = WSFEService._parsear_fault_generico(response_xml)
                    resultado["faultcode"] = fault.get("faultcode", "")
                    resultado["faultstring"] = fault.get("faultstring", "")
                    resultado["errores"].extend(fault.get("errores", []))
                    return resultado
        except urllib.error.HTTPError as error:
            resultado["status_http"] = int(getattr(error, "code", 0) or 0)
            cuerpo = ""
            try:
                cuerpo = error.read().decode("utf-8", errors="replace")
            except Exception:
                cuerpo = ""
            resultado["errores"].append(f"HTTP {error.code} al invocar FECompConsultar.")
            fault = WSFEService._parsear_fault_generico(cuerpo)
            resultado["faultcode"] = fault.get("faultcode", "")
            resultado["faultstring"] = fault.get("faultstring", "")
            resultado["errores"].extend(fault.get("errores", []))
            return resultado
        except urllib.error.URLError as error:
            resultado["errores"].append(
                f"No se pudo conectar con WSFEv1 de Homologación: {error.reason}"
            )
            return resultado
        except TimeoutError:
            resultado["errores"].append("Tiempo de espera agotado al invocar FECompConsultar.")
            return resultado
        except Exception as error:
            resultado["errores"].append(f"Error inesperado al invocar FECompConsultar: {error}")
            return resultado

        parseo = WSFEService._parsear_respuesta_comp_consultar(response_xml, cuit_texto)
        resultado["status_http"] = int(resultado.get("status_http") or 200)
        resultado["resultado"] = parseo.get("resultado", "")
        resultado["cuit_emisor"] = parseo.get("cuit_emisor", "")
        resultado["punto_venta"] = parseo.get("punto_venta", 0)
        resultado["tipo_comprobante"] = parseo.get("tipo_comprobante", 0)
        resultado["numero_comprobante"] = parseo.get("numero_comprobante", 0)
        resultado["fecha_comprobante"] = parseo.get("fecha_comprobante", "")
        resultado["doc_tipo"] = parseo.get("doc_tipo", 0)
        resultado["doc_nro"] = parseo.get("doc_nro", 0)
        resultado["importe_total"] = parseo.get("importe_total", 0.0)
        resultado["importe_neto"] = parseo.get("importe_neto", 0.0)
        resultado["importe_iva"] = parseo.get("importe_iva", 0.0)
        resultado["moneda"] = parseo.get("moneda", "")
        resultado["cotizacion"] = parseo.get("cotizacion", 0.0)
        resultado["cae"] = parseo.get("cae", "")
        resultado["vencimiento_cae"] = parseo.get("vencimiento_cae", "")
        resultado["condicion_iva_receptor_id"] = parseo.get("condicion_iva_receptor_id", 0)
        resultado["observaciones"] = parseo.get("observaciones", [])
        resultado["errores_arca"] = parseo.get("errores_arca", [])
        resultado["eventos"] = parseo.get("eventos", [])
        resultado["faultcode"] = parseo.get("faultcode", "")
        resultado["faultstring"] = parseo.get("faultstring", "")

        if not parseo.get("ok"):
            resultado["errores"].extend(parseo.get("errores", ["No se pudo consultar el comprobante."]))
            return resultado

        resultado["ok"] = True
        return resultado

    @staticmethod
    def _construir_soap_fedummy():
        return (
            "<?xml version=\"1.0\" encoding=\"UTF-8\"?>"
            "<soapenv:Envelope xmlns:soapenv=\"http://schemas.xmlsoap.org/soap/envelope/\" "
            "xmlns:ar=\"http://ar.gov.afip.dif.FEV1/\">"
            "<soapenv:Header/>"
            "<soapenv:Body>"
            "<ar:FEDummy/>"
            "</soapenv:Body>"
            "</soapenv:Envelope>"
        )

    @staticmethod
    def _construir_soap_ultimo_autorizado(token, sign, cuit, punto_venta, tipo_comprobante):
        return (
            "<?xml version=\"1.0\" encoding=\"UTF-8\"?>"
            "<soapenv:Envelope xmlns:soapenv=\"http://schemas.xmlsoap.org/soap/envelope/\" "
            "xmlns:ar=\"http://ar.gov.afip.dif.FEV1/\">"
            "<soapenv:Header/>"
            "<soapenv:Body>"
            "<ar:FECompUltimoAutorizado>"
            "<ar:Auth>"
            f"<ar:Token>{WSFEService._escapar_xml(token)}</ar:Token>"
            f"<ar:Sign>{WSFEService._escapar_xml(sign)}</ar:Sign>"
            f"<ar:Cuit>{WSFEService._escapar_xml(cuit)}</ar:Cuit>"
            "</ar:Auth>"
            f"<ar:PtoVta>{punto_venta}</ar:PtoVta>"
            f"<ar:CbteTipo>{tipo_comprobante}</ar:CbteTipo>"
            "</ar:FECompUltimoAutorizado>"
            "</soapenv:Body>"
            "</soapenv:Envelope>"
        )

    @staticmethod
    def _construir_soap_comp_consultar(token, sign, cuit, punto_venta, tipo_comprobante, numero_comprobante):
        return (
            "<?xml version=\"1.0\" encoding=\"UTF-8\"?>"
            "<soapenv:Envelope xmlns:soapenv=\"http://schemas.xmlsoap.org/soap/envelope/\" "
            "xmlns:ar=\"http://ar.gov.afip.dif.FEV1/\">"
            "<soapenv:Header/>"
            "<soapenv:Body>"
            "<ar:FECompConsultar>"
            "<ar:Auth>"
            f"<ar:Token>{WSFEService._escapar_xml(token)}</ar:Token>"
            f"<ar:Sign>{WSFEService._escapar_xml(sign)}</ar:Sign>"
            f"<ar:Cuit>{WSFEService._escapar_xml(cuit)}</ar:Cuit>"
            "</ar:Auth>"
            "<ar:FeCompConsReq>"
            f"<ar:CbteTipo>{tipo_comprobante}</ar:CbteTipo>"
            f"<ar:CbteNro>{numero_comprobante}</ar:CbteNro>"
            f"<ar:PtoVta>{punto_venta}</ar:PtoVta>"
            "</ar:FeCompConsReq>"
            "</ar:FECompConsultar>"
            "</soapenv:Body>"
            "</soapenv:Envelope>"
        )

    @staticmethod
    def _construir_soap_cae_solicitar(token, sign, cuit, fe_cae_req):
        return (
            "<?xml version=\"1.0\" encoding=\"UTF-8\"?>"
            "<soapenv:Envelope xmlns:soapenv=\"http://schemas.xmlsoap.org/soap/envelope/\" "
            "xmlns:ar=\"http://ar.gov.afip.dif.FEV1/\">"
            "<soapenv:Header/>"
            "<soapenv:Body>"
            "<ar:FECAESolicitar>"
            "<ar:Auth>"
            f"<ar:Token>{WSFEService._escapar_xml(token)}</ar:Token>"
            f"<ar:Sign>{WSFEService._escapar_xml(sign)}</ar:Sign>"
            f"<ar:Cuit>{WSFEService._escapar_xml(cuit)}</ar:Cuit>"
            "</ar:Auth>"
            f"{WSFEService._construir_xml_fe_cae_req(fe_cae_req)}"
            "</ar:FECAESolicitar>"
            "</soapenv:Body>"
            "</soapenv:Envelope>"
        )

    @staticmethod
    def construir_soap_cae_sanitizado(cuit, solicitud):
        if isinstance(solicitud, dict) and isinstance(solicitud.get("FeCAEReq"), dict):
            fe_cae_req = solicitud.get("FeCAEReq", {})
        else:
            fe_cae_req = solicitud if isinstance(solicitud, dict) else {}

        return WSFEService._construir_soap_cae_solicitar(
            token="[TOKEN]",
            sign="[SIGN]",
            cuit=str(cuit or "").strip(),
            fe_cae_req=fe_cae_req,
        )

    @staticmethod
    def _construir_xml_fe_cae_req(fe_cae_req):
        fe_cab_req = fe_cae_req.get("FeCabReq", {})
        fe_det_req = fe_cae_req.get("FeDetReq", {})
        detalles = fe_det_req.get("FECAEDetRequest", [])
        if isinstance(detalles, dict):
            detalles = [detalles]

        cant_reg = WSFEService._serializar_entero_xml(fe_cab_req.get("CantReg", 1), default="1")
        pto_vta = WSFEService._serializar_entero_xml(fe_cab_req.get("PtoVta", 0), default="0")
        cbte_tipo = WSFEService._serializar_entero_xml(fe_cab_req.get("CbteTipo", 0), default="0")

        cab = (
            "<ar:FeCabReq>"
            f"<ar:CantReg>{cant_reg}</ar:CantReg>"
            f"<ar:PtoVta>{pto_vta}</ar:PtoVta>"
            f"<ar:CbteTipo>{cbte_tipo}</ar:CbteTipo>"
            "</ar:FeCabReq>"
        )

        detalles_xml = []
        claves_enteras = {
            "Concepto",
            "DocTipo",
            "DocNro",
            "CbteDesde",
            "CbteHasta",
            "CondicionIVAReceptorId",
        }
        claves_decimales = {
            "ImpTotal",
            "ImpTotConc",
            "ImpNeto",
            "ImpOpEx",
            "ImpTrib",
            "ImpIVA",
            "MonCotiz",
        }
        claves_detalle = [
            "Concepto",
            "DocTipo",
            "DocNro",
            "CbteDesde",
            "CbteHasta",
            "CbteFch",
            "FchServDesde",
            "FchServHasta",
            "FchVtoPago",
            "CondicionIVAReceptorId",
            "ImpTotal",
            "ImpTotConc",
            "ImpNeto",
            "ImpOpEx",
            "ImpTrib",
            "ImpIVA",
            "MonId",
            "MonCotiz",
        ]
        for detalle in detalles:
            if not isinstance(detalle, dict):
                continue
            partes = ["<ar:FECAEDetRequest>"]
            for clave in claves_detalle:
                if clave not in detalle:
                    continue
                valor = detalle.get(clave)
                if clave in claves_enteras:
                    valor_xml = WSFEService._serializar_entero_xml(valor)
                elif clave in claves_decimales:
                    valor_xml = WSFEService._serializar_decimal_xml(valor)
                else:
                    valor_xml = WSFEService._escapar_xml(valor)
                partes.append(f"<ar:{clave}>{valor_xml}</ar:{clave}>")

            iva_detalle = detalle.get("Iva") if isinstance(detalle, dict) else None
            if isinstance(iva_detalle, dict):
                alic_list = iva_detalle.get("AlicIva")
                if isinstance(alic_list, dict):
                    alic_list = [alic_list]
                if isinstance(alic_list, list) and alic_list:
                    partes.append("<ar:Iva>")
                    for alic in alic_list:
                        if not isinstance(alic, dict):
                            continue
                        id_xml = WSFEService._serializar_entero_xml(alic.get("Id"), default="0")
                        base_xml = WSFEService._serializar_decimal_xml(alic.get("BaseImp"), default="0")
                        imp_xml = WSFEService._serializar_decimal_xml(alic.get("Importe"), default="0")
                        partes.append("<ar:AlicIva>")
                        partes.append(f"<ar:Id>{id_xml}</ar:Id>")
                        partes.append(f"<ar:BaseImp>{base_xml}</ar:BaseImp>")
                        partes.append(f"<ar:Importe>{imp_xml}</ar:Importe>")
                        partes.append("</ar:AlicIva>")
                    partes.append("</ar:Iva>")
            partes.append("</ar:FECAEDetRequest>")
            detalles_xml.append("".join(partes))

        det = "<ar:FeDetReq>" + "".join(detalles_xml) + "</ar:FeDetReq>"

        return "<ar:FeCAEReq>" + cab + det + "</ar:FeCAEReq>"

    @staticmethod
    def _parsear_respuesta(response_xml):
        resultado = {
            "ok": False,
            "appserver": "",
            "dbserver": "",
            "authserver": "",
            "faultcode": "",
            "faultstring": "",
            "errores": [],
        }

        try:
            root = ET.fromstring(response_xml)
        except ET.ParseError:
            resultado["errores"].append("WSFEv1 devolvió XML inválido.")
            return resultado

        fault = WSFEService._buscar_por_sufijo(root, "Fault")
        if fault is not None:
            faultcode = WSFEService._extraer_texto_por_sufijo(fault, "faultcode")
            faultstring = WSFEService._extraer_texto_por_sufijo(fault, "faultstring")
            detalle = WSFEService._extraer_texto_por_sufijo(fault, "detail")
            resultado["faultcode"] = faultcode
            resultado["faultstring"] = faultstring
            mensaje = "SOAP Fault en WSFEv1."
            if faultcode or faultstring:
                mensaje = f"SOAP Fault en WSFEv1: {faultcode or 'Sin código'} - {faultstring or 'Sin detalle'}"
            resultado["errores"].append(mensaje)
            if detalle:
                resultado["errores"].append(detalle)
            return resultado

        dummy_result = WSFEService._buscar_por_sufijo(root, "FEDummyResult")
        if dummy_result is None:
            resultado["errores"].append("WSFEv1 no devolvió FEDummyResult.")
            return resultado

        resultado["appserver"] = WSFEService._extraer_texto_por_sufijo(dummy_result, "AppServer")
        resultado["dbserver"] = WSFEService._extraer_texto_por_sufijo(dummy_result, "DbServer")
        resultado["authserver"] = WSFEService._extraer_texto_por_sufijo(dummy_result, "AuthServer")

        if not (resultado["appserver"] or resultado["dbserver"] or resultado["authserver"]):
            resultado["errores"].append("WSFEv1 devolvió FEDummyResult vacío.")
            return resultado

        resultado["ok"] = True
        return resultado

    @staticmethod
    def _parsear_respuesta_ultimo_autorizado(response_xml):
        resultado = {
            "ok": False,
            "ultimo_numero": 0,
            "faultcode": "",
            "faultstring": "",
            "errores": [],
        }

        try:
            root = ET.fromstring(response_xml)
        except ET.ParseError:
            resultado["errores"].append("WSFEv1 devolvió XML inválido.")
            return resultado

        fault = WSFEService._buscar_por_sufijo(root, "Fault")
        if fault is not None:
            faultcode = WSFEService._extraer_texto_por_sufijo(fault, "faultcode")
            faultstring = WSFEService._extraer_texto_por_sufijo(fault, "faultstring")
            resultado["faultcode"] = faultcode
            resultado["faultstring"] = faultstring
            mensaje = "SOAP Fault en WSFEv1."
            if faultcode or faultstring:
                mensaje = f"SOAP Fault en WSFEv1: {faultcode or 'Sin código'} - {faultstring or 'Sin detalle'}"
            resultado["errores"].append(mensaje)
            return resultado

        nodo_resultado = WSFEService._buscar_por_sufijo(root, "FECompUltimoAutorizadoResult")
        if nodo_resultado is None:
            resultado["errores"].append("WSFEv1 no devolvió FECompUltimoAutorizadoResult.")
            return resultado

        cbte_nro_texto = WSFEService._extraer_texto_por_sufijo(nodo_resultado, "CbteNro")
        if not cbte_nro_texto:
            resultado["errores"].append("WSFEv1 no devolvió CbteNro.")
            return resultado

        try:
            cbte_nro = int(cbte_nro_texto)
        except (TypeError, ValueError):
            resultado["errores"].append("WSFEv1 devolvió CbteNro inválido.")
            return resultado

        resultado["ok"] = True
        resultado["ultimo_numero"] = cbte_nro
        return resultado

    @staticmethod
    def _parsear_respuesta_cae_solicitar(response_xml):
        resultado = {
            "ok": False,
            "resultado": "",
            "cae": "",
            "vencimiento_cae": "",
            "numero_comprobante": 0,
            "fecha_comprobante": "",
            "observaciones": [],
            "errores_arca": [],
            "eventos": [],
            "faultcode": "",
            "faultstring": "",
            "errores": [],
        }

        try:
            root = ET.fromstring(response_xml)
        except ET.ParseError:
            resultado["errores"].append("WSFEv1 devolvió XML inválido.")
            return resultado

        fault = WSFEService._buscar_por_sufijo(root, "Fault")
        if fault is not None:
            faultcode = WSFEService._extraer_texto_por_sufijo(fault, "faultcode")
            faultstring = WSFEService._extraer_texto_por_sufijo(fault, "faultstring")
            resultado["faultcode"] = faultcode
            resultado["faultstring"] = faultstring
            mensaje = "SOAP Fault en WSFEv1."
            if faultcode or faultstring:
                mensaje = f"SOAP Fault en WSFEv1: {faultcode or 'Sin código'} - {faultstring or 'Sin detalle'}"
            resultado["errores"].append(mensaje)
            return resultado

        nodo_resultado = WSFEService._buscar_por_sufijo(root, "FECAESolicitarResult")
        if nodo_resultado is None:
            resultado["errores"].append("WSFEv1 no devolvió FECAESolicitarResult.")
            return resultado

        resultado_general = WSFEService._extraer_texto_por_sufijo(nodo_resultado, "Resultado")
        if not resultado_general:
            resultado_general = WSFEService._extraer_texto_por_sufijo(nodo_resultado, "Resultado")
        resultado["resultado"] = resultado_general

        det = WSFEService._buscar_por_sufijo(nodo_resultado, "FECAEDetResponse")
        resultado_detalle = WSFEService._extraer_texto_por_sufijo(det, "Resultado") if det is not None else ""
        if not resultado["resultado"] and resultado_detalle:
            resultado["resultado"] = resultado_detalle

        resultado["cae"] = WSFEService._extraer_texto_por_sufijo(det, "CAE") if det is not None else ""
        resultado["vencimiento_cae"] = (
            WSFEService._extraer_texto_por_sufijo(det, "CAEFchVto") if det is not None else ""
        )
        cbte_desde = WSFEService._extraer_texto_por_sufijo(det, "CbteDesde") if det is not None else ""
        resultado["fecha_comprobante"] = WSFEService._extraer_texto_por_sufijo(det, "CbteFch") if det is not None else ""
        try:
            resultado["numero_comprobante"] = int(cbte_desde) if cbte_desde else 0
        except (TypeError, ValueError):
            resultado["numero_comprobante"] = 0

        resultado["observaciones"] = WSFEService._colectar_codigo_mensaje(nodo_resultado, "Obs")
        resultado["errores_arca"] = WSFEService._colectar_codigo_mensaje(nodo_resultado, "Err")
        resultado["eventos"] = WSFEService._colectar_codigo_mensaje(nodo_resultado, "Evt")

        # DEBUG: Imprimir respuesta completa de ARCA para diagnóstico
        if resultado["errores_arca"] or resultado["observaciones"]:
            print("DEBUG ARCA - Respuesta completa de FECAESolicitar:")
            if resultado["errores_arca"]:
                print("  Errors:")
                for error in resultado["errores_arca"]:
                    codigo = str(error.get("codigo") or "").strip()
                    mensaje = str(error.get("mensaje") or "").strip()
                    print(f"    [{codigo}] {mensaje}")
            if resultado["observaciones"]:
                print("  Observaciones:")
                for obs in resultado["observaciones"]:
                    codigo = str(obs.get("codigo") or "").strip()
                    mensaje = str(obs.get("mensaje") or "").strip()
                    print(f"    [{codigo}] {mensaje}")

        aprobado = (resultado["resultado"] == "A" or resultado_detalle == "A") and bool(resultado["cae"])
        if aprobado:
            resultado["ok"] = True
            return resultado

        if resultado["resultado"] == "R" and not resultado["errores_arca"] and not resultado["observaciones"]:
            resultado["errores"].append("ARCA rechazó la solicitud FECAESolicitar.")
        elif not resultado["errores_arca"] and not resultado["observaciones"]:
            resultado["errores"].append("WSFEv1 no aprobó la solicitud FECAESolicitar.")

        return resultado

    @staticmethod
    def _parsear_respuesta_comp_consultar(response_xml, cuit_entrada=""):
        resultado = {
            "ok": False,
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
            "faultcode": "",
            "faultstring": "",
            "errores": [],
        }

        try:
            root = ET.fromstring(response_xml)
        except ET.ParseError:
            resultado["errores"].append("WSFEv1 devolvió XML inválido.")
            return resultado

        fault = WSFEService._buscar_por_sufijo(root, "Fault")
        if fault is not None:
            faultcode = WSFEService._extraer_texto_por_sufijo(fault, "faultcode")
            faultstring = WSFEService._extraer_texto_por_sufijo(fault, "faultstring")
            resultado["faultcode"] = faultcode
            resultado["faultstring"] = faultstring
            mensaje = "SOAP Fault en WSFEv1."
            if faultcode or faultstring:
                mensaje = f"SOAP Fault en WSFEv1: {faultcode or 'Sin código'} - {faultstring or 'Sin detalle'}"
            resultado["errores"].append(mensaje)
            return resultado

        nodo_resultado = WSFEService._buscar_por_sufijo(root, "FECompConsultarResult")
        if nodo_resultado is None:
            resultado["errores"].append("WSFEv1 no devolvió FECompConsultarResult.")
            return resultado

        resultado["observaciones"] = WSFEService._colectar_codigo_mensaje(nodo_resultado, "Obs")
        resultado["errores_arca"] = WSFEService._colectar_codigo_mensaje(nodo_resultado, "Err")
        resultado["eventos"] = WSFEService._colectar_codigo_mensaje(nodo_resultado, "Evt")

        result_get = WSFEService._buscar_por_sufijo(nodo_resultado, "ResultGet")
        if result_get is None:
            if not resultado["errores_arca"] and not resultado["observaciones"]:
                resultado["errores"].append("Comprobante inexistente o no informado por WSFEv1.")
            return resultado

        resultado["resultado"] = WSFEService._extraer_texto_por_sufijo(result_get, "Resultado")
        resultado["cuit_emisor"] = WSFEService._extraer_texto_por_sufijo(result_get, "Cuit")
        if not resultado["cuit_emisor"]:
            resultado["cuit_emisor"] = str(cuit_entrada or "").strip()
        resultado["punto_venta"] = WSFEService._to_int(
            WSFEService._extraer_texto_por_sufijo(result_get, "PtoVta")
        )
        resultado["tipo_comprobante"] = WSFEService._to_int(
            WSFEService._extraer_texto_por_sufijo(result_get, "CbteTipo")
        )
        cbte_nro = WSFEService._to_int(WSFEService._extraer_texto_por_sufijo(result_get, "CbteNro"))
        cbte_desde = WSFEService._to_int(WSFEService._extraer_texto_por_sufijo(result_get, "CbteDesde"))
        cbte_hasta = WSFEService._to_int(WSFEService._extraer_texto_por_sufijo(result_get, "CbteHasta"))
        if cbte_nro > 0:
            resultado["numero_comprobante"] = cbte_nro
        elif cbte_desde > 0:
            resultado["numero_comprobante"] = cbte_desde
        else:
            resultado["numero_comprobante"] = cbte_hasta
        resultado["fecha_comprobante"] = WSFEService._extraer_texto_por_sufijo(result_get, "CbteFch")
        resultado["doc_tipo"] = WSFEService._to_int(
            WSFEService._extraer_texto_por_sufijo(result_get, "DocTipo")
        )
        resultado["doc_nro"] = WSFEService._to_int(
            WSFEService._extraer_texto_por_sufijo(result_get, "DocNro")
        )
        resultado["importe_total"] = WSFEService._to_float(
            WSFEService._extraer_texto_por_sufijo(result_get, "ImpTotal")
        )
        resultado["importe_neto"] = WSFEService._to_float(
            WSFEService._extraer_texto_por_sufijo(result_get, "ImpNeto")
        )
        resultado["importe_iva"] = WSFEService._to_float(
            WSFEService._extraer_texto_por_sufijo(result_get, "ImpIVA")
        )
        resultado["moneda"] = WSFEService._extraer_texto_por_sufijo(result_get, "MonId")
        resultado["cotizacion"] = WSFEService._to_float(
            WSFEService._extraer_texto_por_sufijo(result_get, "MonCotiz")
        )
        resultado["cae"] = WSFEService._extraer_texto_por_sufijo(result_get, "CodAutorizacion")
        resultado["vencimiento_cae"] = WSFEService._extraer_texto_por_sufijo(result_get, "FchVto")
        if not resultado["vencimiento_cae"]:
            resultado["vencimiento_cae"] = WSFEService._extraer_texto_por_sufijo(result_get, "CAEFchVto")
        resultado["condicion_iva_receptor_id"] = WSFEService._to_int(
            WSFEService._extraer_texto_por_sufijo(result_get, "CondicionIVAReceptorId")
        )

        aprobado = resultado["resultado"] == "A" and bool(resultado["cae"]) and resultado["numero_comprobante"] > 0
        if not aprobado and resultado["numero_comprobante"] <= 0:
            if not resultado["errores_arca"] and not resultado["observaciones"]:
                resultado["errores"].append("Comprobante inexistente o no informado por WSFEv1.")
            return resultado

        resultado["ok"] = aprobado
        if not resultado["ok"] and not resultado["errores"] and not resultado["errores_arca"]:
            resultado["errores"].append("WSFEv1 no aprobó la consulta del comprobante.")
        return resultado

    @staticmethod
    def _colectar_codigo_mensaje(root, sufijo_item):
        if root is None:
            return []

        elementos = []
        for nodo in root.iter():
            if not nodo.tag.endswith(sufijo_item):
                continue
            codigo = WSFEService._extraer_texto_por_sufijo(nodo, "Code")
            mensaje = WSFEService._extraer_texto_por_sufijo(nodo, "Msg")
            if codigo or mensaje:
                elementos.append({"codigo": codigo, "mensaje": mensaje})
        return elementos

    @staticmethod
    def _parsear_fault_generico(response_xml):
        resultado = {
            "faultcode": "",
            "faultstring": "",
            "errores": [],
        }

        try:
            root = ET.fromstring(response_xml or "")
        except ET.ParseError:
            if str(response_xml or "").strip():
                resultado["errores"].append("WSFEv1 devolvió XML inválido.")
            return resultado

        fault = WSFEService._buscar_por_sufijo(root, "Fault")
        if fault is None:
            return resultado

        resultado["faultcode"] = WSFEService._extraer_texto_por_sufijo(fault, "faultcode")
        resultado["faultstring"] = WSFEService._extraer_texto_por_sufijo(fault, "faultstring")
        mensaje = "SOAP Fault en WSFEv1."
        if resultado["faultcode"] or resultado["faultstring"]:
            mensaje = (
                "SOAP Fault en WSFEv1: "
                f"{resultado['faultcode'] or 'Sin código'} - {resultado['faultstring'] or 'Sin detalle'}"
            )
        resultado["errores"].append(mensaje)
        return resultado

    @staticmethod
    def _parsear_fault_o_error(response_xml):
        parseo = WSFEService._parsear_respuesta(response_xml)
        if parseo["ok"]:
            return parseo
        if not parseo["errores"]:
            parseo["errores"].append("WSFEv1 devolvió un error SOAP/HTTP.")
        return parseo

    @staticmethod
    def _buscar_por_sufijo(root, sufijo):
        if root.tag.endswith(sufijo):
            return root
        for nodo in root.iter():
            if nodo.tag.endswith(sufijo):
                return nodo
        return None

    @staticmethod
    def _extraer_texto_por_sufijo(root, sufijo):
        nodo = WSFEService._buscar_por_sufijo(root, sufijo)
        if nodo is None:
            return ""
        return (nodo.text or "").strip()

    @staticmethod
    def _escapar_xml(valor):
        texto = str(valor or "")
        return (
            texto.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
            .replace("'", "&apos;")
        )

    @staticmethod
    def _serializar_entero_xml(valor, default="0"):
        if valor is None:
            return WSFEService._escapar_xml(default)

        texto = str(valor).strip()
        if texto == "":
            return WSFEService._escapar_xml(default)

        texto = texto.replace(",", ".")
        try:
            numero = Decimal(texto)
        except (InvalidOperation, ValueError):
            return WSFEService._escapar_xml(default)

        if numero != numero.to_integral_value():
            return WSFEService._escapar_xml(default)

        return WSFEService._escapar_xml(str(int(numero)))

    @staticmethod
    def _serializar_decimal_xml(valor, default="0"):
        if valor is None:
            return WSFEService._escapar_xml(default)

        texto = str(valor).strip()
        if texto == "":
            return WSFEService._escapar_xml(default)

        texto = texto.replace(",", ".")
        try:
            numero = Decimal(texto)
        except (InvalidOperation, ValueError):
            return WSFEService._escapar_xml(default)

        normalizado = format(numero, "f")
        if "." in normalizado:
            normalizado = normalizado.rstrip("0").rstrip(".")
        if normalizado in {"", "-0"}:
            normalizado = "0"

        return WSFEService._escapar_xml(normalizado)

    @staticmethod
    def _to_int(valor):
        try:
            return int(str(valor or "0").strip())
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _to_float(valor):
        try:
            return float(str(valor or "0").strip().replace(",", "."))
        except (TypeError, ValueError):
            return 0.0

    @staticmethod
    def _es_fecha_yyyymmdd(valor):
        texto = str(valor or "").strip()
        if len(texto) != 8 or not texto.isdigit():
            return False
        try:
            datetime.strptime(texto, "%Y%m%d")
        except ValueError:
            return False
        return True
