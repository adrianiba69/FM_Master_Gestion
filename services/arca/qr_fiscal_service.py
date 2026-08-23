"""
QR Fiscal ARCA Service

Construcción del payload QR para comprobantes electrónicos según
especificación ARCA vigente.

No llama ARCA. No toca SQLite. No emite.
Solo construye payload, valida, serializa y codifica.
"""

import json
import base64
import re
from typing import Dict, Optional, Tuple
from datetime import datetime


class QRFiscalError(Exception):
    """Error en construcción/validación de QR fiscal"""
    pass


class QrFiscalService:
    """
    Servicio de construcción de QR fiscal ARCA.
    
    Responsabilidades:
    - construir_payload(...)
    - validar_payload(...)
    - serializar_json(...)
    - codificar_base64(...)
    - construir_url(...)
    
    No toca base de datos ni ReportLab.
    """

    QR_VERIFICATION_URL = "https://www.arca.gob.ar/fe/qr/"

    # Tipos de código de autorización
    TIPO_COD_AUT_ELECTRONICOS = "E"  # Comprobante Electrónico (CAE)

    # Moneda predeterminada
    MONEDA_PESOS = "PES"

    # Cotización predeterminada
    COTIZACION_PESOS = 1

    def __init__(self):
        """Inicializar servicio QR fiscal"""
        pass

    def construir_payload(
        self,
        ver: int,
        fecha: str,
        cuit_emisor: int,
        punto_venta_num: int,
        tipo_comprobante_num: int,
        numero_comprobante_num: int,
        importe: float,
        cae: str,
        tipo_documento_receptor: Optional[int] = None,
        numero_documento_receptor: Optional[int] = None,
        moneda: str = None,
        cotizacion: float = None,
    ) -> Dict:
        """
        Construir payload QR fiscal.

        Args:
            ver: Versión de formato (típicamente 1)
            fecha: Fecha en formato YYYYMMDD o YYYY-MM-DD
            cuit_emisor: CUIT del emisor (11 dígitos)
            punto_venta_num: Punto de venta (normalizado)
            tipo_comprobante_num: Tipo de comprobante (normalizado)
            numero_comprobante_num: Número de comprobante (normalizado)
            importe: Importe total
            cae: Código de Autorización Electrónica
            tipo_documento_receptor: Tipo de documento receptor (80=CUIT, 96=DNI, 99=sin doc)
            numero_documento_receptor: Número de documento receptor
            moneda: Código de moneda (default: PES)
            cotizacion: Cotización (default: 1)

        Returns:
            Dict con estructura de payload QR

        Raises:
            QRFiscalError: Si datos inválidos
        """
        # Valores por defecto
        if moneda is None:
            moneda = self.MONEDA_PESOS
        if cotizacion is None:
            cotizacion = self.COTIZACION_PESOS

        # Validar inputs
        self._validar_inputs(
            ver=ver,
            fecha=fecha,
            cuit_emisor=cuit_emisor,
            punto_venta_num=punto_venta_num,
            tipo_comprobante_num=tipo_comprobante_num,
            numero_comprobante_num=numero_comprobante_num,
            importe=importe,
            cae=cae,
            tipo_documento_receptor=tipo_documento_receptor,
            numero_documento_receptor=numero_documento_receptor,
            moneda=moneda,
            cotizacion=cotizacion,
        )

        # Normalizar fecha al formato YYYY-MM-DD
        fecha_normalizada = self._normalizar_fecha(fecha)

        # Construir payload base
        payload = {
            "ver": ver,
            "fecha": fecha_normalizada,
            "cuit": cuit_emisor,
            "ptoVta": punto_venta_num,
            "tipoCmp": tipo_comprobante_num,
            "nroCmp": numero_comprobante_num,
            "importe": round(importe, 2),
            "moneda": moneda,
            "ctz": cotizacion,
            "tipoCodAut": self.TIPO_COD_AUT_ELECTRONICOS,
            "codAut": int(cae),
        }

        # Agregar receptor si ambos campos son válidos
        if (
            tipo_documento_receptor is not None
            and numero_documento_receptor is not None
        ):
            payload["tipoDocRec"] = tipo_documento_receptor
            payload["nroDocRec"] = numero_documento_receptor

        return payload

    def validar_payload(self, payload: Dict) -> Tuple[bool, Optional[str]]:
        """
        Validar estructura y contenido del payload QR.

        Args:
            payload: Diccionario de payload

        Returns:
            Tupla (válido, mensaje_error)
        """
        try:
            # Campos obligatorios
            campos_obligatorios = [
                "ver",
                "fecha",
                "cuit",
                "ptoVta",
                "tipoCmp",
                "nroCmp",
                "importe",
                "moneda",
                "ctz",
                "tipoCodAut",
                "codAut",
            ]

            for campo in campos_obligatorios:
                if campo not in payload:
                    return False, f"Campo obligatorio faltante: {campo}"

            # Validar tipos
            if not isinstance(payload["ver"], int):
                return False, "ver debe ser entero"
            if not isinstance(payload["fecha"], str) or not re.match(
                r"^\d{4}-\d{2}-\d{2}$", payload["fecha"]
            ):
                return False, "fecha debe estar en formato YYYY-MM-DD"
            if not isinstance(payload["cuit"], int) or payload["cuit"] < 0:
                return False, "cuit debe ser entero positivo"
            if not isinstance(payload["ptoVta"], int) or payload["ptoVta"] < 0:
                return False, "ptoVta debe ser entero positivo"
            if not isinstance(payload["tipoCmp"], int) or payload["tipoCmp"] < 0:
                return False, "tipoCmp debe ser entero positivo"
            if not isinstance(payload["nroCmp"], int) or payload["nroCmp"] < 0:
                return False, "nroCmp debe ser entero positivo"
            if not isinstance(payload["importe"], (int, float)) or payload["importe"] < 0:
                return False, "importe debe ser numérico positivo"
            if not isinstance(payload["moneda"], str):
                return False, "moneda debe ser string"
            if not isinstance(payload["ctz"], (int, float)) or payload["ctz"] <= 0:
                return False, "ctz debe ser numérico positivo"
            if payload["tipoCodAut"] != "E":
                return False, "tipoCodAut debe ser 'E'"
            if not isinstance(payload["codAut"], int) or payload["codAut"] <= 0:
                return False, "codAut (CAE) debe ser entero positivo"

            # Validar receptor si está presente
            if "tipoDocRec" in payload or "nroDocRec" in payload:
                if "tipoDocRec" not in payload or "nroDocRec" not in payload:
                    return (
                        False,
                        "Si se incluye receptor, ambos tipoDocRec y nroDocRec son obligatorios",
                    )
                if not isinstance(payload["tipoDocRec"], int):
                    return False, "tipoDocRec debe ser entero"
                if not isinstance(payload["nroDocRec"], int):
                    return False, "nroDocRec debe ser entero"

            return True, None

        except Exception as e:
            return False, f"Error validación: {str(e)}"

    def serializar_json(self, payload: Dict) -> str:
        """
        Serializar payload a JSON compacto y determinista.

        Args:
            payload: Diccionario de payload

        Returns:
            String JSON compacto (sin espacios, sorted keys)

        Raises:
            QRFiscalError: Si no es serializable
        """
        try:
            # JSON compacto con keys ordenadas para determinismo
            return json.dumps(
                payload, separators=(",", ":"), sort_keys=True, ensure_ascii=False
            )
        except Exception as e:
            raise QRFiscalError(f"Error serializando JSON: {str(e)}")

    def codificar_base64(self, json_str: str) -> str:
        """
        Codificar JSON en Base64 estándar.

        Args:
            json_str: String JSON

        Returns:
            String Base64 (UTF-8)

        Raises:
            QRFiscalError: Si no es codificable
        """
        try:
            # Codificar UTF-8 y luego Base64
            json_bytes = json_str.encode("utf-8")
            base64_bytes = base64.b64encode(json_bytes)
            return base64_bytes.decode("ascii")
        except Exception as e:
            raise QRFiscalError(f"Error codificando Base64: {str(e)}")

    def construir_url(self, base64_payload: str) -> str:
        """
        Construir URL final del QR.

        Args:
            base64_payload: Payload codificado en Base64

        Returns:
            URL completa para verificador QR ARCA

        Raises:
            QRFiscalError: Si URL inválida
        """
        try:
            if not base64_payload or not isinstance(base64_payload, str):
                raise QRFiscalError("base64_payload debe ser un string no vacío")

            return f"{self.QR_VERIFICATION_URL}?p={base64_payload}"
        except Exception as e:
            raise QRFiscalError(f"Error construyendo URL: {str(e)}")

    def construir_qr_completo(
        self,
        ver: int,
        fecha: str,
        cuit_emisor: int,
        punto_venta_num: int,
        tipo_comprobante_num: int,
        numero_comprobante_num: int,
        importe: float,
        cae: str,
        tipo_documento_receptor: Optional[int] = None,
        numero_documento_receptor: Optional[int] = None,
        moneda: str = None,
        cotizacion: float = None,
    ) -> Tuple[Optional[str], Optional[str]]:
        """
        Construir QR completamente desde parámetros.

        Encadena: construir_payload -> validar -> serializar -> codificar -> url

        Args:
            (mismos que construir_payload)

        Returns:
            Tupla (url_qr, error_mensaje)
            - Si éxito: (url, None)
            - Si fallo: (None, mensaje_error)

        Nota: Fail-safe. NUNCA levanta excepción. NUNCA modifica datos.
        """
        try:
            # 1. Construir payload
            payload = self.construir_payload(
                ver=ver,
                fecha=fecha,
                cuit_emisor=cuit_emisor,
                punto_venta_num=punto_venta_num,
                tipo_comprobante_num=tipo_comprobante_num,
                numero_comprobante_num=numero_comprobante_num,
                importe=importe,
                cae=cae,
                tipo_documento_receptor=tipo_documento_receptor,
                numero_documento_receptor=numero_documento_receptor,
                moneda=moneda,
                cotizacion=cotizacion,
            )

            # 2. Validar payload
            valido, error = self.validar_payload(payload)
            if not valido:
                return None, f"Payload inválido: {error}"

            # 3. Serializar a JSON
            json_str = self.serializar_json(payload)

            # 4. Codificar Base64
            base64_payload = self.codificar_base64(json_str)

            # 5. Construir URL
            url_qr = self.construir_url(base64_payload)

            return url_qr, None

        except QRFiscalError as e:
            return None, str(e)
        except Exception as e:
            return None, f"Error inesperado construyendo QR: {str(e)}"

    def decodificar_url_qr(self, url_qr: str) -> Tuple[Optional[Dict], Optional[str]]:
        """
        Decodificar URL QR para validación/test.

        Args:
            url_qr: URL QR completa

        Returns:
            Tupla (payload_dict, error_mensaje)

        Nota: Solo para tests/validación. Utilidad para verificar reversibilidad.
        """
        try:
            if not url_qr.startswith(self.QR_VERIFICATION_URL):
                return None, "URL no comienza con QR_VERIFICATION_URL"

            # Extraer parámetro 'p'
            if "?p=" not in url_qr:
                return None, "URL no contiene parámetro ?p="

            base64_payload = url_qr.split("?p=", 1)[1]

            # Decodificar Base64
            try:
                json_bytes = base64.b64decode(base64_payload)
            except Exception as e:
                return None, f"Base64 inválido: {str(e)}"

            # Decodificar UTF-8 a JSON
            try:
                json_str = json_bytes.decode("utf-8")
            except Exception as e:
                return None, f"UTF-8 inválido: {str(e)}"

            # Parsear JSON
            try:
                payload = json.loads(json_str)
            except Exception as e:
                return None, f"JSON inválido: {str(e)}"

            return payload, None

        except Exception as e:
            return None, f"Error decodificando URL: {str(e)}"

    # =========================================================================
    # MÉTODOS PRIVADOS
    # =========================================================================

    def _validar_inputs(
        self,
        ver: int,
        fecha: str,
        cuit_emisor: int,
        punto_venta_num: int,
        tipo_comprobante_num: int,
        numero_comprobante_num: int,
        importe: float,
        cae: str,
        tipo_documento_receptor: Optional[int],
        numero_documento_receptor: Optional[int],
        moneda: str,
        cotizacion: float,
    ) -> None:
        """Validar inputs de construir_payload"""
        if not isinstance(ver, int) or ver < 1:
            raise QRFiscalError("ver debe ser entero >= 1")

        if not isinstance(fecha, str) or len(fecha) == 0:
            raise QRFiscalError("fecha debe ser string no vacío")

        if not isinstance(cuit_emisor, int) or cuit_emisor <= 0:
            raise QRFiscalError("cuit_emisor debe ser entero positivo")

        if not isinstance(punto_venta_num, int) or punto_venta_num < 1:
            raise QRFiscalError("punto_venta_num debe ser entero >= 1")

        if not isinstance(tipo_comprobante_num, int) or tipo_comprobante_num < 0:
            raise QRFiscalError("tipo_comprobante_num debe ser entero >= 0")

        if not isinstance(numero_comprobante_num, int) or numero_comprobante_num < 0:
            raise QRFiscalError("numero_comprobante_num debe ser entero >= 0")

        if not isinstance(importe, (int, float)) or importe < 0:
            raise QRFiscalError("importe debe ser numérico >= 0")

        if not isinstance(cae, str) or len(cae) == 0:
            raise QRFiscalError("cae debe ser string no vacío")

        # CAE debe ser numérico
        if not cae.isdigit():
            raise QRFiscalError("cae debe contener solo dígitos")

        # CAE longitud típica es 14 dígitos
        if len(cae) != 14:
            raise QRFiscalError(f"cae debe tener 14 dígitos, recibido {len(cae)}")

        # Validar receptor: si uno está presente, ambos deben estarlo
        if (tipo_documento_receptor is None) != (numero_documento_receptor is None):
            raise QRFiscalError(
                "tipo_documento_receptor y numero_documento_receptor deben ser ambos None o ambos presentes"
            )

        if tipo_documento_receptor is not None:
            if not isinstance(tipo_documento_receptor, int):
                raise QRFiscalError("tipo_documento_receptor debe ser entero")
            if not isinstance(numero_documento_receptor, int):
                raise QRFiscalError("numero_documento_receptor debe ser entero")

        if not isinstance(moneda, str) or len(moneda) == 0:
            raise QRFiscalError("moneda debe ser string no vacío")

        if not isinstance(cotizacion, (int, float)) or cotizacion <= 0:
            raise QRFiscalError("cotizacion debe ser numérico positivo")

    def _normalizar_fecha(self, fecha: str) -> str:
        """
        Normalizar fecha a formato YYYY-MM-DD.

        Acepta:
        - YYYYMMDD
        - YYYY-MM-DD
        - Otros formatos conocidos

        Raises:
            QRFiscalError: Si fecha inválida
        """
        if not isinstance(fecha, str):
            raise QRFiscalError("fecha debe ser string")

        # Si ya está en formato correcto
        if re.match(r"^\d{4}-\d{2}-\d{2}$", fecha):
            # Validar que sea fecha válida
            try:
                datetime.strptime(fecha, "%Y-%m-%d")
                return fecha
            except ValueError:
                raise QRFiscalError(f"Fecha inválida: {fecha}")

        # Si está en formato YYYYMMDD
        if re.match(r"^\d{8}$", fecha):
            try:
                dt = datetime.strptime(fecha, "%Y%m%d")
                return dt.strftime("%Y-%m-%d")
            except ValueError:
                raise QRFiscalError(f"Fecha YYYYMMDD inválida: {fecha}")

        raise QRFiscalError(
            f"Formato de fecha no reconocido: {fecha} (esperado YYYYMMDD o YYYY-MM-DD)"
        )
