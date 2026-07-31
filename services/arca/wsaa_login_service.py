from base64 import b64encode
import hashlib
from pathlib import Path
import json
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

from services.arca.certificado_service import CertificadoService


class WSAALoginService:
    WSAA_HOMOLOGACION_URL = "https://wsaahomo.afip.gov.ar/ws/services/LoginCms"
    TIMEOUT_SEGUNDOS = 20
    
    # Cache de TA en memoria (por sesión), segmentado por identidad de emisor.
    _ta_cache = {}
    
    # Archivo de caché en disco (persiste entre ejecuciones)
    _TA_CACHE_FILENAME_PREFIX = "ta_cache_homologacion"

    @staticmethod
    def _cache_key(ruta_certificado, ruta_clave):
        cert = str(Path(str(ruta_certificado or "")).resolve()) if str(ruta_certificado or "").strip() else ""
        clave = str(Path(str(ruta_clave or "")).resolve()) if str(ruta_clave or "").strip() else ""
        base = f"{cert}|{clave}|{WSAALoginService.WSAA_HOMOLOGACION_URL}"
        return hashlib.sha1(base.encode("utf-8", errors="ignore")).hexdigest()[:16]

    @staticmethod
    def _ruta_cache_disco(ruta_tra, cache_key):
        """Devuelve la ruta del archivo de caché junto al TRA."""
        try:
            carpeta = Path(str(ruta_tra)).parent
            nombre = f"{WSAALoginService._TA_CACHE_FILENAME_PREFIX}_{cache_key}.json"
            return carpeta / nombre
        except Exception:
            return None

    @staticmethod
    def _leer_cache_disco(ruta_tra, cache_key):
        """Lee el TA guardado en disco. Devuelve dict o None."""
        try:
            ruta = WSAALoginService._ruta_cache_disco(ruta_tra, cache_key)
            if ruta and ruta.exists():
                datos = json.loads(ruta.read_text(encoding="utf-8"))
                return datos
        except Exception:
            pass
        return None

    @staticmethod
    def _guardar_cache_disco(ruta_tra, cache_key, token, sign, expiration):
        """Guarda el TA en disco para persistir entre ejecuciones."""
        try:
            ruta = WSAALoginService._ruta_cache_disco(ruta_tra, cache_key)
            if ruta:
                datos = {"token": token, "sign": sign, "expiration": expiration}
                ruta.write_text(json.dumps(datos, indent=2), encoding="utf-8")
        except Exception as e:
            print(f"DEBUG WSAA - No se pudo guardar TA en disco: {e}")

    @staticmethod
    def _validar_ta(token, sign, expiration):
        """Valida que el TA exista y no esté expirado. Devuelve True/False."""
        if not token or not sign or not expiration:
            return False
        try:
            ahora_utc = datetime.now(timezone.utc)
            exp_text = expiration.replace("Z", "+00:00")
            exp_dt = datetime.fromisoformat(exp_text)
            if exp_dt.tzinfo is None:
                exp_dt = exp_dt.replace(tzinfo=timezone.utc)
            exp_utc = exp_dt.astimezone(timezone.utc)
            return exp_utc > ahora_utc
        except Exception:
            return False

    @staticmethod
    def login_homologacion(ruta_tra, ruta_certificado, ruta_clave):
        resultado = {
            "ok": False,
            "token": "",
            "sign": "",
            "expiration": "",
            "faultcode": "",
            "faultstring": "",
            "detail": "",
            "status_http": 0,
            "cuerpo_respuesta_sanitizado": "",
            "errores": [],
        }

        cache_key = WSAALoginService._cache_key(ruta_certificado, ruta_clave)
        cache_memoria = WSAALoginService._ta_cache.get(cache_key, {})
        
        # DEBUG: Verificar si existe TA en caché válido
        # 1. Verificar caché en memoria (misma sesión)
        if WSAALoginService._validar_ta(
            cache_memoria.get("token", ""),
            cache_memoria.get("sign", ""),
            cache_memoria.get("expiration", ""),
        ):
            ahora_utc = datetime.now(timezone.utc)
            exp_text = str(cache_memoria.get("expiration", "")).replace("Z", "+00:00")
            exp_dt = datetime.fromisoformat(exp_text)
            if exp_dt.tzinfo is None:
                exp_dt = exp_dt.replace(tzinfo=timezone.utc)
            exp_utc = exp_dt.astimezone(timezone.utc)
            print("DEBUG WSAA - TA válido en caché (memoria):")
            print(f"  Ahora (UTC): {ahora_utc.isoformat()}")
            print(f"  Expira (UTC): {exp_utc.isoformat()}")
            print("  TA reutilizado: SÍ (memoria)")
            resultado["ok"] = True
            resultado["token"] = cache_memoria.get("token", "")
            resultado["sign"] = cache_memoria.get("sign", "")
            resultado["expiration"] = cache_memoria.get("expiration", "")
            return resultado
        
        # 2. Verificar caché en disco (entre ejecuciones)
        cache_disco = WSAALoginService._leer_cache_disco(ruta_tra, cache_key)
        if cache_disco:
            token_d = cache_disco.get("token", "")
            sign_d = cache_disco.get("sign", "")
            exp_d = cache_disco.get("expiration", "")
            if WSAALoginService._validar_ta(token_d, sign_d, exp_d):
                ahora_utc = datetime.now(timezone.utc)
                exp_text = exp_d.replace("Z", "+00:00")
                exp_dt = datetime.fromisoformat(exp_text)
                if exp_dt.tzinfo is None:
                    exp_dt = exp_dt.replace(tzinfo=timezone.utc)
                exp_utc = exp_dt.astimezone(timezone.utc)
                print("DEBUG WSAA - TA válido en caché (disco):")
                print(f"  Ahora (UTC): {ahora_utc.isoformat()}")
                print(f"  Expira (UTC): {exp_utc.isoformat()}")
                print("  TA reutilizado: SÍ (disco)")
                # Cargar también en memoria
                WSAALoginService._ta_cache[cache_key] = {
                    "token": token_d,
                    "sign": sign_d,
                    "expiration": exp_d,
                }
                resultado["ok"] = True
                resultado["token"] = token_d
                resultado["sign"] = sign_d
                resultado["expiration"] = exp_d
                return resultado
            else:
                print("DEBUG WSAA - TA en disco expirado o inválido")
        
        print("DEBUG WSAA - TA no existe o expiró, solicitando uno nuevo")

        firma = CertificadoService.firmar_tra_cms(
            ruta_tra=ruta_tra,
            ruta_certificado=ruta_certificado,
            ruta_clave_privada=ruta_clave,
            ruta_salida=None,
        )
        if not firma.get("firmado"):
            resultado["errores"].extend(firma.get("errores") or ["No se pudo generar el CMS del TRA."])
            return resultado

        ruta_cms = Path(str(firma.get("ruta_cms") or "").strip())
        if not ruta_cms.exists() or not ruta_cms.is_file():
            resultado["errores"].append("No se encontró el archivo CMS generado.")
            return resultado

        try:
            cms_base64 = WSAALoginService._leer_cms_base64(ruta_cms)
        except OSError:
            resultado["errores"].append("No se pudo leer el archivo CMS para preparar el login WSAA.")
            return resultado

        soap_body = WSAALoginService._construir_sobre_soap(cms_base64)

        request = urllib.request.Request(
            url=WSAALoginService.WSAA_HOMOLOGACION_URL,
            data=soap_body.encode("utf-8"),
            method="POST",
            headers={
                "Content-Type": "text/xml; charset=UTF-8",
                "SOAPAction": "urn:LoginCms",
            },
        )

        try:
            with urllib.request.urlopen(request, timeout=WSAALoginService.TIMEOUT_SEGUNDOS) as response:
                status_http = getattr(response, "status", getattr(response, "code", 200))
                response_xml = response.read().decode("utf-8", errors="replace")
                resultado["status_http"] = int(status_http or 200)
        except urllib.error.HTTPError as error:
            resultado["status_http"] = int(getattr(error, "code", 0) or 0)
            detalle = ""
            try:
                detalle = error.read().decode("utf-8", errors="replace").strip()
            except Exception:
                detalle = ""
            resultado["cuerpo_respuesta_sanitizado"] = WSAALoginService._sanitizar_respuesta(detalle)
            parseo = WSAALoginService._parsear_respuesta_login(detalle)
            resultado["faultcode"] = parseo.get("faultcode", "")
            resultado["faultstring"] = parseo.get("faultstring", "")
            resultado["detail"] = parseo.get("detail", "")

            faultcode_str = str(parseo.get("faultcode", "")).lower()
            if "alreadyauthenticated" in faultcode_str:
                print("DEBUG WSAA - SOAP Fault alreadyAuthenticated recibido en HTTPError")
                cache_memoria = WSAALoginService._ta_cache.get(cache_key, {})
                if WSAALoginService._validar_ta(
                    cache_memoria.get("token", ""),
                    cache_memoria.get("sign", ""),
                    cache_memoria.get("expiration", ""),
                ):
                    print("DEBUG WSAA - Reutilizando TA valido de memoria tras alreadyAuthenticated")
                    resultado["ok"] = True
                    resultado["token"] = cache_memoria.get("token", "")
                    resultado["sign"] = cache_memoria.get("sign", "")
                    resultado["expiration"] = cache_memoria.get("expiration", "")
                    return resultado

                cache_disco = WSAALoginService._leer_cache_disco(ruta_tra, cache_key)
                if cache_disco and WSAALoginService._validar_ta(
                    cache_disco.get("token", ""),
                    cache_disco.get("sign", ""),
                    cache_disco.get("expiration", ""),
                ):
                    print("DEBUG WSAA - Reutilizando TA valido de disco tras alreadyAuthenticated")
                    resultado["ok"] = True
                    resultado["token"] = cache_disco.get("token", "")
                    resultado["sign"] = cache_disco.get("sign", "")
                    resultado["expiration"] = cache_disco.get("expiration", "")
                    WSAALoginService._ta_cache[cache_key] = {
                        "token": resultado["token"],
                        "sign": resultado["sign"],
                        "expiration": resultado["expiration"],
                    }
                    return resultado

            if parseo.get("errores"):
                resultado["errores"].extend(parseo.get("errores"))
            else:
                resultado["errores"].append(f"Error HTTP al invocar WSAA: {error.code} {error.reason}")
            return resultado
        except urllib.error.URLError as error:
            resultado["errores"].append(f"No se pudo conectar con WSAA de Homologación: {error.reason}")
            return resultado
        except TimeoutError:
            resultado["errores"].append("Tiempo de espera agotado al invocar WSAA de Homologación.")
            return resultado
        except Exception as error:
            resultado["errores"].append(f"Error inesperado al invocar WSAA de Homologación: {error}")
            return resultado

        parseo = WSAALoginService._parsear_respuesta_login(response_xml)
        resultado["cuerpo_respuesta_sanitizado"] = WSAALoginService._sanitizar_respuesta(response_xml)
        resultado["status_http"] = int(resultado.get("status_http") or 200)
        
        # DEBUG: Chequear si es "alreadyAuthenticated"
        faultcode_str = str(parseo.get("faultcode", "")).lower()
        if "alreadyauthenticated" in faultcode_str:
            print("DEBUG WSAA - AFIP reportó 'alreadyAuthenticated'")
            print(f"  FaultCode original: {parseo.get('faultcode', '')}")
            # Intentar reutilizar TA del caché en memoria
            cache_memoria = WSAALoginService._ta_cache.get(cache_key, {})
            if cache_memoria.get("token"):
                print("  Reutilizando TA del caché (memoria)")
                resultado["ok"] = True
                resultado["token"] = cache_memoria.get("token", "")
                resultado["sign"] = cache_memoria.get("sign", "")
                resultado["expiration"] = cache_memoria.get("expiration", "")
                return resultado
            # Intentar reutilizar TA del caché en disco
            cache_disco = WSAALoginService._leer_cache_disco(ruta_tra, cache_key)
            if cache_disco and cache_disco.get("token"):
                print("  Reutilizando TA del caché (disco)")
                resultado["ok"] = True
                resultado["token"] = cache_disco["token"]
                resultado["sign"] = cache_disco["sign"]
                resultado["expiration"] = cache_disco.get("expiration", "")
                return resultado
            # No hay TA en ningún caché - caso inusual
            print("  AVISO: alreadyAuthenticated pero no hay TA disponible en caché")
            resultado["ok"] = False
            resultado["faultcode"] = parseo.get("faultcode", "")
            resultado["faultstring"] = parseo.get("faultstring", "")
            resultado["detail"] = parseo.get("detail", "")
            resultado["errores"].append("AFIP respondió alreadyAuthenticated pero no hay TA disponible en caché")
            return resultado
        
        if not parseo.get("ok"):
            resultado["faultcode"] = parseo.get("faultcode", "")
            resultado["faultstring"] = parseo.get("faultstring", "")
            resultado["detail"] = parseo.get("detail", "")
            resultado["errores"].extend(parseo.get("errores") or ["Respuesta inválida de WSAA."])
            return resultado

        resultado["ok"] = True
        resultado["token"] = parseo.get("token", "")
        resultado["sign"] = parseo.get("sign", "")
        resultado["expiration"] = parseo.get("expiration", "")
        
        # DEBUG: Guardar TA en caché para reutilización
        print("DEBUG WSAA - TA obtenido exitosamente, guardando en caché")
        print(f"  Token: {resultado['token'][:30]}..." if len(resultado['token']) > 30 else f"  Token: {resultado['token']}")
        print(f"  Expira (original): {resultado['expiration']}")
        
        # Normalizar fecha de expiración para caché
        expiration_text = resultado["expiration"]
        if expiration_text:
            try:
                expiration_text = expiration_text.replace("Z", "+00:00")
                expiration_dt = datetime.fromisoformat(expiration_text)
                if expiration_dt.tzinfo is None:
                    expiration_dt = expiration_dt.replace(tzinfo=timezone.utc)
                expiration_utc = expiration_dt.astimezone(timezone.utc)
                print(f"  Expira (UTC): {expiration_utc.isoformat()}")
                # Guardar en formato ISO con timezone explícito
                resultado["expiration"] = expiration_utc.isoformat()
            except Exception as e:
                print(f"  AVISO: No se pudo normalizar fecha: {e}")
        
        # Guardar en caché en memoria
        WSAALoginService._ta_cache[cache_key] = {
            "token": resultado["token"],
            "sign": resultado["sign"],
            "expiration": resultado["expiration"],
        }
        
        # Guardar en caché en disco (persiste entre ejecuciones)
        WSAALoginService._guardar_cache_disco(
            ruta_tra,
            cache_key,
            resultado["token"],
            resultado["sign"],
            resultado["expiration"],
        )
        
        return resultado

    @staticmethod
    def _leer_cms_base64(ruta_cms):
        contenido = ruta_cms.read_text(encoding="utf-8", errors="replace")
        lineas = []
        for linea in contenido.splitlines():
            texto = linea.strip()
            if not texto:
                continue
            if texto.startswith("-----BEGIN") or texto.startswith("-----END"):
                continue
            lineas.append(texto)
        return "".join(lineas)

    @staticmethod
    def _construir_sobre_soap(cms_base64):
        return (
            "<?xml version=\"1.0\" encoding=\"UTF-8\"?>"
            "<soapenv:Envelope xmlns:soapenv=\"http://schemas.xmlsoap.org/soap/envelope/\" "
            "xmlns:wsaa=\"http://wsaa.view.sua.dvadac.desein.afip.gov\">"
            "<soapenv:Header/>"
            "<soapenv:Body>"
            "<wsaa:loginCms>"
            f"<wsaa:in0>{cms_base64}</wsaa:in0>"
            "</wsaa:loginCms>"
            "</soapenv:Body>"
            "</soapenv:Envelope>"
        )

    @staticmethod
    def _parsear_respuesta_login(response_xml):
        resultado = {
            "ok": False,
            "token": "",
            "sign": "",
            "expiration": "",
            "faultcode": "",
            "faultstring": "",
            "detail": "",
            "errores": [],
        }

        try:
            root = ET.fromstring(response_xml)
        except ET.ParseError:
            resultado["errores"].append("WSAA devolvió XML SOAP inválido.")
            return resultado

        fault = WSAALoginService._buscar_por_sufijo(root, "Fault")
        if fault is not None:
            faultstring = WSAALoginService._extraer_texto_por_sufijo(fault, "faultstring")
            faultcode = WSAALoginService._extraer_texto_por_sufijo(fault, "faultcode")
            detail = WSAALoginService._extraer_texto_por_sufijo(fault, "detail")
            resultado["faultcode"] = faultcode
            resultado["faultstring"] = faultstring
            resultado["detail"] = detail
            # DEBUG: Mostrar SOAP Fault recibido
            print(f"DEBUG WSAA - SOAP Fault recibido: faultcode='{faultcode}'")
            if faultstring or faultcode:
                resultado["errores"].append(f"WSAA respondió SOAP Fault: {faultcode or 'Sin código'} - {faultstring or 'Sin detalle'}")
            else:
                resultado["errores"].append("WSAA respondió con SOAP Fault.")
            return resultado

        login_return = WSAALoginService._buscar_por_sufijo(root, "loginCmsReturn")
        if login_return is None or not (login_return.text or "").strip():
            resultado["errores"].append("WSAA no devolvió loginCmsReturn.")
            return resultado

        inner_xml = (login_return.text or "").strip()
        try:
            login_ticket = ET.fromstring(inner_xml)
        except ET.ParseError:
            resultado["errores"].append("WSAA devolvió loginCmsReturn inválido.")
            return resultado

        token = WSAALoginService._extraer_texto_por_sufijo(login_ticket, "token")
        sign = WSAALoginService._extraer_texto_por_sufijo(login_ticket, "sign")
        expiration = WSAALoginService._extraer_texto_por_sufijo(login_ticket, "expirationTime")

        if not token or not sign:
            resultado["errores"].append("No se encontraron token/sign en la respuesta de WSAA.")
            return resultado

        resultado["ok"] = True
        resultado["token"] = token
        resultado["sign"] = sign
        resultado["expiration"] = expiration or ""
        return resultado

    @staticmethod
    def _sanitizar_respuesta(response_xml):
        texto = str(response_xml or "")
        if not texto:
            return ""

        reemplazos = [
            ("token", "token"),
            ("sign", "sign"),
            ("cms", "cms"),
        ]

        try:
            root = ET.fromstring(texto)
        except ET.ParseError:
            sanitizado = texto
        else:
            for nodo in root.iter():
                nombre = nodo.tag.split("}")[-1].lower()
                if nombre in {"token", "sign", "cms", "in0"} and (nodo.text or "").strip():
                    nodo.text = "[OCULTO]"
            sanitizado = ET.tostring(root, encoding="unicode")

        for clave, marcador in reemplazos:
            sanitizado = sanitizado.replace(clave, marcador)
        return sanitizado.strip()

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
        nodo = WSAALoginService._buscar_por_sufijo(root, sufijo)
        if nodo is None:
            return ""
        return (nodo.text or "").strip()
