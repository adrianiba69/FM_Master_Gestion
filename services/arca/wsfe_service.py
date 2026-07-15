import urllib.error
import urllib.request
import xml.etree.ElementTree as ET


class WSFEService:
    WSFE_HOMOLOGACION_URL = "https://wswhomo.afip.gov.ar/wsfev1/service.asmx"
    SOAP_ACTION_FEDUMMY = "http://ar.gov.afip.dif.FEV1/FEDummy"
    SOAP_ACTION_ULTIMO_AUTORIZADO = "http://ar.gov.afip.dif.FEV1/FECompUltimoAutorizado"
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
    ):
        errores = []

        cuit_texto = str(cuit or "").strip()
        documento_raw = documento_receptor
        documento_texto = "" if documento_raw is None else str(documento_raw).strip()
        fecha_texto = str(fecha_comprobante or "").strip()
        moneda_texto = str(moneda or "").strip()

        if not cuit_texto:
            errores.append("CUIT obligatorio.")
        if not fecha_texto:
            errores.append("Fecha comprobante obligatoria.")
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
            mon_cotiz = round(float(cotizacion), 6)
            if mon_cotiz <= 0:
                raise ValueError()
        except (TypeError, ValueError):
            errores.append("Cotización inválida.")
            mon_cotiz = 0.0

        if imp_total <= 0:
            errores.append("El importe total debe ser mayor a cero.")
        if imp_neto < 0 or imp_iva < 0 or imp_exento < 0:
            errores.append("Importes neto, IVA y exento no pueden ser negativos.")

        suma_componentes = round(imp_neto + imp_iva + imp_exento, 2)
        if round(imp_total, 2) != suma_componentes:
            errores.append("Los totales no cierran: importe total debe igualar neto + IVA + exento.")

        if imp_iva > 0 and imp_neto <= 0:
            errores.append("IVA inválido: si hay IVA, el importe neto debe ser mayor a cero.")

        if concepto_val in {2, 3}:
            errores.append("Concepto 2/3 requiere fechas de servicio, no incluidas en este constructor.")

        if errores:
            return {
                "ok": False,
                "solicitud": {},
                "errores": errores,
            }

        solicitud = {
            "FeCAEReq": {
                "FeCabReq": {
                    "CantReg": 1,
                    "PtoVta": pto_vta,
                    "CbteTipo": cbte_tipo,
                },
                "FeDetReq": {
                    "FECAEDetRequest": [
                        {
                            "Concepto": concepto_val,
                            "DocTipo": doc_tipo,
                            "DocNro": doc_nro,
                            "CbteDesde": cbte_numero,
                            "CbteHasta": cbte_numero,
                            "CbteFch": fecha_texto,
                            "CondicionIVAReceptorId": cond_iva_receptor,
                            "ImpTotal": imp_total,
                            "ImpTotConc": 0.0,
                            "ImpNeto": imp_neto,
                            "ImpOpEx": imp_exento,
                            "ImpTrib": 0.0,
                            "ImpIVA": imp_iva,
                            "MonId": moneda_texto,
                            "MonCotiz": mon_cotiz,
                        }
                    ]
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
    def fe_comp_ultimo_autorizado(token, sign, cuit, punto_venta, tipo_comprobante):
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
        cuit_texto = str(cuit or "").strip()

        if not token_texto:
            resultado["errores"].append("Token no informado.")
            return resultado
        if not sign_texto:
            resultado["errores"].append("Sign no informado.")
            return resultado
        if not cuit_texto:
            resultado["errores"].append("CUIT no informado.")
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
            url=WSFEService.WSFE_HOMOLOGACION_URL,
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
    def fe_cae_solicitar(token, sign, cuit, solicitud):
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

        request = urllib.request.Request(
            url=WSFEService.WSFE_HOMOLOGACION_URL,
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
    def _construir_xml_fe_cae_req(fe_cae_req):
        fe_cab_req = fe_cae_req.get("FeCabReq", {})
        fe_det_req = fe_cae_req.get("FeDetReq", {})
        detalles = fe_det_req.get("FECAEDetRequest", [])
        if isinstance(detalles, dict):
            detalles = [detalles]

        cab = (
            "<ar:FeCabReq>"
            f"<ar:CantReg>{int(fe_cab_req.get('CantReg', 1))}</ar:CantReg>"
            f"<ar:PtoVta>{int(fe_cab_req.get('PtoVta', 0))}</ar:PtoVta>"
            f"<ar:CbteTipo>{int(fe_cab_req.get('CbteTipo', 0))}</ar:CbteTipo>"
            "</ar:FeCabReq>"
        )

        detalles_xml = []
        claves_detalle = [
            "Concepto",
            "DocTipo",
            "DocNro",
            "CbteDesde",
            "CbteHasta",
            "CbteFch",
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
                partes.append(f"<ar:{clave}>{WSFEService._escapar_xml(valor)}</ar:{clave}>")
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
