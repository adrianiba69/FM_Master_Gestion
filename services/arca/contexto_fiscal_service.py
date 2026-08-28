"""Contrato puro para el contexto fiscal preliminar de un intento ARCA."""

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation


CONTEXTO_FISCAL_VERSION = 1
CODIGO_CONTEXTO_VALIDO = "VALIDO"
CODIGO_CONTEXTO_JSON_INVALIDO = "JSON_INVALIDO"
CODIGO_CONTEXTO_VERSION_INVALIDA = "VERSION_INVALIDA"
CODIGO_CONTEXTO_ESTRUCTURA_INVALIDA = "ESTRUCTURA_INVALIDA"
CODIGO_CONTEXTO_HASH_INVALIDO = "HASH_INVALIDO"
CODIGO_CONTEXTO_GUARDADO = "CONTEXTO_GUARDADO"
CODIGO_CONTEXTO_IDEMPOTENTE = "CONTEXTO_IDEMPOTENTE"
CODIGO_CONTEXTO_DIFERENTE = "CONTEXTO_DIFERENTE"
CODIGO_CONTEXTO_CORRUPTO = "CONTEXTO_CORRUPTO"
CODIGO_CONTEXTO_INVALIDO = "CONTEXTO_INVALIDO"

_SECRETOS = {
    "token", "sign", "clave", "clave_privada", "private_key", "certificado",
    "certificate", "password", "contrasena", "contraseña", "secret", "credential",
    "credencial", "ruta_certificado", "ruta_clave", "ruta_clave_privada",
    "certificado_path", "clave_privada_path", "carpeta_trabajo", "carpeta_facturas",
}
_CLAVES_FECHA = re.compile(r"(^fecha($|_)|fecha$|vencimiento|periodo_.*|creado_en$)", re.IGNORECASE)


@dataclass(frozen=True)
class ResultadoIntegridadContextoFiscal:
    valido: bool
    codigo: str
    errores: tuple = ()
    contexto: dict = None
    json_canonico: str = ""
    version: int = None
    hash_calculado: str = ""


@dataclass(frozen=True)
class ResultadoPersistenciaContextoFiscal:
    ok: bool
    codigo: str
    mensaje: str = ""
    actualizado: bool = False
    idempotente: bool = False


class ContextoFiscalError(ValueError):
    pass


class ContextoFiscalService:
    @staticmethod
    def normalizar(contexto):
        if not isinstance(contexto, dict):
            raise ContextoFiscalError("contexto debe ser un objeto")
        return ContextoFiscalService._normalizar_valor(contexto, "contexto")

    @staticmethod
    def validar(contexto):
        try:
            normalizado = ContextoFiscalService.normalizar(contexto)
        except ContextoFiscalError as error:
            return ResultadoIntegridadContextoFiscal(
                False, CODIGO_CONTEXTO_ESTRUCTURA_INVALIDA, (str(error),)
            )
        if normalizado.get("version") != CONTEXTO_FISCAL_VERSION:
            return ResultadoIntegridadContextoFiscal(
                False, CODIGO_CONTEXTO_VERSION_INVALIDA, ("version invalida",)
            )
        if normalizado.get("tipo") != "contexto_fiscal_arca":
            return ResultadoIntegridadContextoFiscal(
                False, CODIGO_CONTEXTO_ESTRUCTURA_INVALIDA, ("tipo invalido",)
            )
        try:
            serializado = ContextoFiscalService.serializar(normalizado)
        except ContextoFiscalError as error:
            return ResultadoIntegridadContextoFiscal(
                False, CODIGO_CONTEXTO_ESTRUCTURA_INVALIDA, (str(error),)
            )
        return ResultadoIntegridadContextoFiscal(
            True,
            CODIGO_CONTEXTO_VALIDO,
            contexto=normalizado,
            json_canonico=serializado,
            version=CONTEXTO_FISCAL_VERSION,
            hash_calculado=ContextoFiscalService.calcular_hash(serializado),
        )

    @staticmethod
    def serializar(contexto):
        normalizado = ContextoFiscalService.normalizar(contexto)
        if normalizado.get("version") != CONTEXTO_FISCAL_VERSION:
            raise ContextoFiscalError("version invalida")
        if normalizado.get("tipo") != "contexto_fiscal_arca":
            raise ContextoFiscalError("tipo invalido")
        return json.dumps(normalizado, ensure_ascii=False, sort_keys=True, separators=(",", ":"))

    @staticmethod
    def calcular_hash(json_canonico):
        if not isinstance(json_canonico, str) or not json_canonico:
            raise ContextoFiscalError("JSON canonico vacio")
        return hashlib.sha256(json_canonico.encode("utf-8")).hexdigest()

    @staticmethod
    def validar_integridad(json_texto, version, hash_texto):
        try:
            contexto = json.loads(json_texto)
        except (TypeError, json.JSONDecodeError):
            return ResultadoIntegridadContextoFiscal(False, CODIGO_CONTEXTO_JSON_INVALIDO, ("JSON invalido",))
        if version != CONTEXTO_FISCAL_VERSION:
            return ResultadoIntegridadContextoFiscal(False, CODIGO_CONTEXTO_VERSION_INVALIDA, ("version invalida",))
        validacion = ContextoFiscalService.validar(contexto)
        if not validacion.valido:
            return validacion
        if not isinstance(hash_texto, str) or not re.fullmatch(r"[0-9a-f]{64}", hash_texto):
            return ResultadoIntegridadContextoFiscal(False, CODIGO_CONTEXTO_HASH_INVALIDO, ("hash invalido",))
        if validacion.hash_calculado != hash_texto:
            return ResultadoIntegridadContextoFiscal(False, CODIGO_CONTEXTO_HASH_INVALIDO, ("hash no coincide",))
        return validacion

    @staticmethod
    def _normalizar_valor(valor, ruta):
        if isinstance(valor, float):
            raise ContextoFiscalError(f"{ruta} no acepta float")
        if isinstance(valor, Decimal):
            try:
                decimal = valor.normalize()
            except (InvalidOperation, ValueError) as error:
                raise ContextoFiscalError(f"{ruta} decimal invalido") from error
            return format(decimal, "f")
        if isinstance(valor, (datetime, date)):
            return valor.isoformat()
        if isinstance(valor, dict):
            resultado = {}
            for clave, contenido in valor.items():
                clave_texto = str(clave)
                if clave_texto.lower() in _SECRETOS:
                    raise ContextoFiscalError(f"campo secreto prohibido: {ruta}.{clave_texto}")
                valor_normalizado = ContextoFiscalService._normalizar_valor(contenido, f"{ruta}.{clave_texto}")
                if isinstance(valor_normalizado, str) and _CLAVES_FECHA.search(clave_texto):
                    valor_normalizado = ContextoFiscalService._normalizar_fecha(valor_normalizado, f"{ruta}.{clave_texto}")
                resultado[clave_texto] = valor_normalizado
            return resultado
        if isinstance(valor, (list, tuple)):
            return [ContextoFiscalService._normalizar_valor(item, f"{ruta}[]") for item in valor]
        if isinstance(valor, (str, int, bool)) or valor is None:
            return valor
        raise ContextoFiscalError(f"{ruta} contiene un tipo no permitido")

    @staticmethod
    def _normalizar_fecha(valor, ruta):
        texto = valor.strip()
        try:
            if len(texto) == 8 and texto.isdigit():
                return datetime.strptime(texto, "%Y%m%d").date().isoformat()
            if len(texto) == 10:
                return date.fromisoformat(texto).isoformat()
            if "T" in texto:
                return datetime.fromisoformat(texto).isoformat()
        except ValueError as error:
            raise ContextoFiscalError(f"{ruta} fecha invalida") from error
        raise ContextoFiscalError(f"{ruta} debe estar en formato ISO")