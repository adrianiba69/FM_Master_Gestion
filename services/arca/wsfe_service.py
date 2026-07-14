import urllib.error
import urllib.request
import xml.etree.ElementTree as ET


class WSFEService:
    WSFE_HOMOLOGACION_URL = "https://wswhomo.afip.gov.ar/wsfev1/service.asmx"
    SOAP_ACTION_FEDUMMY = "http://ar.gov.afip.dif.FEV1/FEDummy"
    SOAP_ACTION_ULTIMO_AUTORIZADO = "http://ar.gov.afip.dif.FEV1/FECompUltimoAutorizado"
    TIMEOUT_SEGUNDOS = 20

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
