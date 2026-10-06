import os
import sqlite3
from dataclasses import dataclass, field
from typing import Optional

from database import conectar
from services.arca.ambiente_arca import (
    AMBIENTE_HOMOLOGACION,
    AMBIENTE_PRODUCCION,
    AmbienteArcaInvalidoError,
    normalizar_ambiente_arca,
)
from services.arca_certificados_service import ArcaCertificadosService
from services.emisor_service import EmisorService


@dataclass(frozen=True)
class ConfiguracionArcaEmisor:
    id: int
    emisor_fiscal_id: int
    ambiente_arca: str
    punto_venta: Optional[str]
    ruta_certificado: Optional[str] = field(repr=False)
    ruta_clave_privada: Optional[str] = field(repr=False)
    carpeta_facturas: Optional[str] = field(repr=False)


class ConfiguracionArcaError(ValueError):
    def __init__(self, codigo, mensaje):
        self.codigo = codigo
        super().__init__(mensaje)


@dataclass(frozen=True)
class ResultadoValidacionArcaPorAmbiente:
    ok: bool
    codigo: str
    errores: tuple = ()
    advertencias: tuple = ()
    controles_no_realizados: tuple = ()
    configuracion: Optional[ConfiguracionArcaEmisor] = field(default=None, repr=False)


@dataclass(frozen=True)
class ResultadoGuardadoConfiguracionArca:
    configuracion: ConfiguracionArcaEmisor = field(repr=False)
    espejo_legacy_actualizado: bool


# Valor legacy de emisores_fiscales.ambiente_arca (forma historica visible en UI).
_AMBIENTE_LEGACY = {
    AMBIENTE_HOMOLOGACION: "Homologación",
    AMBIENTE_PRODUCCION: "Producción",
}


class EmisorFiscalService:

    @staticmethod
    def _canonizar_ambiente(ambiente):
        try:
            return normalizar_ambiente_arca(ambiente)
        except AmbienteArcaInvalidoError:
            raise ConfiguracionArcaError("AMBIENTE_ARCA_INVALIDO", "Ambiente ARCA no reconocido.") from None

    @staticmethod
    def _canonizar_emisor_id(emisor_fiscal_id):
        if isinstance(emisor_fiscal_id, bool) or not isinstance(emisor_fiscal_id, (int, str)):
            raise ConfiguracionArcaError("EMISOR_FISCAL_ID_INVALIDO", "Identificador del emisor fiscal invalido.")
        try:
            emisor_id = int(emisor_fiscal_id)
        except ValueError:
            raise ConfiguracionArcaError("EMISOR_FISCAL_ID_INVALIDO", "Identificador del emisor fiscal invalido.") from None
        if emisor_id <= 0:
            raise ConfiguracionArcaError("EMISOR_FISCAL_ID_INVALIDO", "Identificador del emisor fiscal invalido.")
        return emisor_id

    @staticmethod
    def _normalizar_punto_venta_configuracion(punto_venta):
        """Vacio/None => '' (configuracion incompleta); valido => texto de 5 digitos."""
        error = ConfiguracionArcaError(
            "PUNTO_VENTA_INVALIDO", "Punto de venta invalido: debe ser un entero entre 1 y 99999."
        )
        if punto_venta is None:
            return ""
        if isinstance(punto_venta, bool):
            raise error
        if isinstance(punto_venta, int):
            numero = punto_venta
        elif isinstance(punto_venta, str):
            texto = punto_venta.strip()
            if not texto:
                return ""
            if not (texto.isascii() and texto.isdigit()):
                raise error
            numero = int(texto)
        else:
            raise error
        if not 1 <= numero <= 99999:
            raise error
        return f"{numero:05d}"

    @staticmethod
    def _normalizar_ruta_configuracion(valor):
        """Normaliza sin tocar el filesystem; la existencia la comprueba el validador."""
        if valor is None:
            return ""
        if isinstance(valor, os.PathLike):
            valor = os.fspath(valor)
        if not isinstance(valor, str) or "\x00" in valor:
            raise ConfiguracionArcaError("VALOR_CONFIGURACION_INVALIDO", "Valor de ruta de configuracion ARCA invalido.")
        return valor.strip()

    @staticmethod
    def _ambiente_activo_legacy(valor):
        try:
            return normalizar_ambiente_arca(valor)
        except AmbienteArcaInvalidoError:
            return None

    @staticmethod
    def guardar_configuracion_arca(
        emisor_fiscal_id, ambiente, punto_venta, ruta_certificado, ruta_clave_privada, carpeta_facturas,
    ):
        """Crea/actualiza solo la hija del ambiente indicado; espeja al legacy solo si es el ambiente activo."""
        ambiente_canonico = EmisorFiscalService._canonizar_ambiente(ambiente)
        emisor_id = EmisorFiscalService._canonizar_emisor_id(emisor_fiscal_id)
        valores = (
            EmisorFiscalService._normalizar_punto_venta_configuracion(punto_venta),
            EmisorFiscalService._normalizar_ruta_configuracion(ruta_certificado),
            EmisorFiscalService._normalizar_ruta_configuracion(ruta_clave_privada),
            EmisorFiscalService._normalizar_ruta_configuracion(carpeta_facturas),
        )

        conexion = None
        try:
            conexion = conectar()
            cursor = conexion.cursor()
            cursor.execute("BEGIN IMMEDIATE")
            cursor.execute("SELECT ambiente_arca FROM emisores_fiscales WHERE id=?", (emisor_id,))
            fila_emisor = cursor.fetchone()
            if fila_emisor is None:
                raise ConfiguracionArcaError("EMISOR_FISCAL_NO_ENCONTRADO", "El emisor fiscal solicitado no existe.")
            cursor.execute(
                "SELECT id FROM emisor_fiscal_arca_config WHERE emisor_fiscal_id=? AND ambiente_arca=? ORDER BY id",
                (emisor_id, ambiente_canonico),
            )
            ids = [fila[0] for fila in cursor.fetchall()]
            if len(ids) > 1:
                raise ConfiguracionArcaError("CONFIGURACION_ARCA_AMBIGUA", "Hay varias configuraciones ARCA para el mismo emisor y ambiente.")
            if ids:
                configuracion_id = ids[0]
                if not isinstance(configuracion_id, int) or configuracion_id <= 0:
                    raise ConfiguracionArcaError("CONFIGURACION_ARCA_INCOHERENTE", "La configuracion ARCA no es coherente con la solicitud.")
                cursor.execute(
                    "UPDATE emisor_fiscal_arca_config SET punto_venta=?, ruta_certificado=?, "
                    "ruta_clave_privada=?, carpeta_facturas=? WHERE id=? AND emisor_fiscal_id=? AND ambiente_arca=?",
                    (*valores, configuracion_id, emisor_id, ambiente_canonico),
                )
                if cursor.rowcount != 1:
                    raise ConfiguracionArcaError("CONFIGURACION_ARCA_INCOHERENTE", "La configuracion ARCA no es coherente con la solicitud.")
            else:
                cursor.execute(
                    "INSERT INTO emisor_fiscal_arca_config(emisor_fiscal_id, ambiente_arca, punto_venta, "
                    "ruta_certificado, ruta_clave_privada, carpeta_facturas) VALUES(?,?,?,?,?,?)",
                    (emisor_id, ambiente_canonico, *valores),
                )
                configuracion_id = cursor.lastrowid

            espejo = EmisorFiscalService._ambiente_activo_legacy(fila_emisor[0]) == ambiente_canonico
            if espejo:
                cursor.execute(
                    "UPDATE emisores_fiscales SET punto_venta=?, ruta_certificado=?, ruta_clave_privada=?, "
                    "carpeta_facturas=? WHERE id=?",
                    (*valores, emisor_id),
                )
                if cursor.rowcount != 1:
                    raise ConfiguracionArcaError("CONFIGURACION_ARCA_INCOHERENTE", "La configuracion ARCA no es coherente con la solicitud.")
            conexion.commit()
        except ConfiguracionArcaError:
            if conexion is not None:
                conexion.rollback()
            raise
        except (sqlite3.Error, OSError):
            if conexion is not None:
                conexion.rollback()
            raise ConfiguracionArcaError("ESCRITURA_CONFIGURACION_ARCA_FALLIDA", "No se pudo guardar la configuracion ARCA del emisor.") from None
        finally:
            if conexion is not None:
                conexion.close()
        return ResultadoGuardadoConfiguracionArca(
            ConfiguracionArcaEmisor(configuracion_id, emisor_id, ambiente_canonico, *valores), espejo,
        )

    @staticmethod
    def cambiar_ambiente_arca_activo(emisor_fiscal_id, ambiente):
        """Copia atomicamente la hija exacta al legacy; no habilita emision (ver asegurar_emision_habilitada)."""
        ambiente_canonico = EmisorFiscalService._canonizar_ambiente(ambiente)
        emisor_id = EmisorFiscalService._canonizar_emisor_id(emisor_fiscal_id)

        conexion = None
        try:
            conexion = conectar()
            cursor = conexion.cursor()
            cursor.execute("BEGIN IMMEDIATE")
            cursor.execute("SELECT id FROM emisores_fiscales WHERE id=?", (emisor_id,))
            if cursor.fetchone() is None:
                raise ConfiguracionArcaError("EMISOR_FISCAL_NO_ENCONTRADO", "El emisor fiscal solicitado no existe.")
            cursor.execute(
                "SELECT id, emisor_fiscal_id, ambiente_arca, punto_venta, ruta_certificado, "
                "ruta_clave_privada, carpeta_facturas FROM emisor_fiscal_arca_config "
                "WHERE emisor_fiscal_id=? AND ambiente_arca=? ORDER BY id",
                (emisor_id, ambiente_canonico),
            )
            filas = cursor.fetchall()
            if not filas:
                raise ConfiguracionArcaError("CONFIGURACION_ARCA_NO_ENCONTRADA", "Falta configuracion ARCA para el ambiente solicitado.")
            if len(filas) != 1:
                raise ConfiguracionArcaError("CONFIGURACION_ARCA_AMBIGUA", "Hay varias configuraciones ARCA para el mismo emisor y ambiente.")
            fila = filas[0]
            if (
                not isinstance(fila[0], int) or fila[0] <= 0 or fila[1] != emisor_id
                or fila[2] != ambiente_canonico
                or any(valor is not None and not isinstance(valor, str) for valor in fila[3:])
            ):
                raise ConfiguracionArcaError("CONFIGURACION_ARCA_INCOHERENTE", "La configuracion ARCA no es coherente con la solicitud.")
            cursor.execute(
                "UPDATE emisores_fiscales SET ambiente_arca=?, punto_venta=?, ruta_certificado=?, "
                "ruta_clave_privada=?, carpeta_facturas=? WHERE id=?",
                (_AMBIENTE_LEGACY[ambiente_canonico], *fila[3:], emisor_id),
            )
            if cursor.rowcount != 1:
                raise ConfiguracionArcaError("CONFIGURACION_ARCA_INCOHERENTE", "La configuracion ARCA no es coherente con la solicitud.")
            conexion.commit()
        except ConfiguracionArcaError:
            if conexion is not None:
                conexion.rollback()
            raise
        except (sqlite3.Error, OSError):
            if conexion is not None:
                conexion.rollback()
            raise ConfiguracionArcaError("ESCRITURA_CONFIGURACION_ARCA_FALLIDA", "No se pudo cambiar el ambiente ARCA activo.") from None
        finally:
            if conexion is not None:
                conexion.close()
        return ConfiguracionArcaEmisor(*fila)

    @staticmethod
    def actualizar_datos_fiscales(
        id_,
        razon_social,
        nombre_fantasia,
        cuit,
        condicion_iva,
        tipo_factura,
        activo=1,
        observaciones="",
        domicilio="",
        ingresos_brutos="",
        fecha_inicio_actividades="",
    ):
        """Actualiza solo la identidad fiscal comun; nunca columnas ARCA legacy."""
        emisor_id = EmisorFiscalService._canonizar_emisor_id(id_)
        conexion = conectar()
        try:
            cursor = conexion.cursor()
            cursor.execute(
                """
                UPDATE emisores_fiscales
                SET razon_social=?,
                    nombre_fantasia=?,
                    cuit=?,
                    condicion_iva=?,
                    tipo_factura=?,
                    activo=?,
                    observaciones=?,
                    domicilio=?,
                    ingresos_brutos=?,
                    fecha_inicio_actividades=?
                WHERE id=?
                """,
                (
                    razon_social,
                    nombre_fantasia,
                    cuit,
                    condicion_iva,
                    tipo_factura,
                    1 if activo else 0,
                    observaciones,
                    domicilio,
                    ingresos_brutos,
                    fecha_inicio_actividades,
                    emisor_id,
                ),
            )
            if cursor.rowcount != 1:
                conexion.rollback()
                raise ConfiguracionArcaError("EMISOR_FISCAL_NO_ENCONTRADO", "El emisor fiscal solicitado no existe.")
            conexion.commit()
        finally:
            conexion.close()

    @staticmethod
    def obtener_configuracion_arca(emisor_fiscal_id, ambiente):
        """Lee la tabla hija por ambiente; nunca usa la configuracion legacy."""
        ambiente_canonico = EmisorFiscalService._canonizar_ambiente(ambiente)
        emisor_id = EmisorFiscalService._canonizar_emisor_id(emisor_fiscal_id)

        conexion = None
        try:
            conexion = conectar()
            cursor = conexion.cursor()
            cursor.execute("SELECT id FROM emisores_fiscales WHERE id=?", (emisor_id,))
            if cursor.fetchone() is None:
                raise ConfiguracionArcaError("EMISOR_FISCAL_NO_ENCONTRADO", "El emisor fiscal solicitado no existe.")
            cursor.execute(
                "SELECT id, emisor_fiscal_id, ambiente_arca, punto_venta, ruta_certificado, "
                "ruta_clave_privada, carpeta_facturas FROM emisor_fiscal_arca_config "
                "WHERE emisor_fiscal_id=? AND ambiente_arca=? ORDER BY id",
                (emisor_id, ambiente_canonico),
            )
            filas = cursor.fetchall()
            if not filas:
                raise ConfiguracionArcaError("CONFIGURACION_ARCA_NO_ENCONTRADA", "Falta configuracion ARCA para el ambiente solicitado.")
            if len(filas) != 1:
                raise ConfiguracionArcaError("CONFIGURACION_ARCA_AMBIGUA", "Hay varias configuraciones ARCA para el mismo emisor y ambiente.")
            fila = filas[0]
            if (
                not isinstance(fila[0], int) or fila[0] <= 0 or fila[1] != emisor_id
                or fila[2] != ambiente_canonico
                or any(valor is not None and not isinstance(valor, str) for valor in fila[3:])
            ):
                raise ConfiguracionArcaError("CONFIGURACION_ARCA_INCOHERENTE", "La configuracion ARCA no es coherente con la solicitud.")
            return ConfiguracionArcaEmisor(*fila)
        except (sqlite3.Error, OSError):
            raise ConfiguracionArcaError("LECTURA_CONFIGURACION_ARCA_FALLIDA", "No se pudo leer la configuracion ARCA del emisor.") from None
        finally:
            if conexion is not None:
                conexion.close()

    @staticmethod
    def validar_configuracion_arca_por_ambiente(emisor_fiscal_id, ambiente):
        """Valida recursos locales, sin acreditar validez criptografica ni habilitacion ARCA."""
        controles = (
            "vigencia_certificado: no verificada",
            "cuit_certificado: no verificado",
            "correspondencia_certificado_clave: no verificada",
            "autorizacion_arca: no verificada",
            "escritura_carpeta: no demostrada; solo se comprueban permisos",
        )
        try:
            configuracion = EmisorFiscalService.obtener_configuracion_arca(emisor_fiscal_id, ambiente)
        except ConfiguracionArcaError as error:
            return ResultadoValidacionArcaPorAmbiente(
                False, error.codigo, errores=(str(error),), controles_no_realizados=controles,
            )
        errores = []
        try:
            punto_venta = int(configuracion.punto_venta)
            if punto_venta <= 0:
                raise ValueError()
        except (TypeError, ValueError):
            errores.append("Punto de venta invalido: debe ser un entero positivo.")
        for etiqueta, ruta in (
            ("certificado", configuracion.ruta_certificado),
            ("clave privada", configuracion.ruta_clave_privada),
        ):
            if not ruta or not ruta.strip():
                errores.append(f"Falta ruta del archivo de {etiqueta}.")
                continue
            try:
                if not ArcaCertificadosService.validar_archivo(ruta):
                    errores.append(f"No existe un archivo de {etiqueta} utilizable.")
                    continue
                with open(ruta, "rb") as archivo:
                    archivo.read(1)
            except (OSError, ValueError):
                errores.append(f"El archivo de {etiqueta} no es legible.")
        carpeta = configuracion.carpeta_facturas
        if not carpeta or not carpeta.strip():
            errores.append("Falta carpeta de facturas.")
        else:
            try:
                if not os.path.isdir(carpeta):
                    errores.append("La carpeta de facturas no existe.")
                elif not os.access(carpeta, os.W_OK | os.X_OK):
                    errores.append("La carpeta de facturas no tiene permisos de escritura y acceso.")
            except (OSError, ValueError):
                errores.append("No se pudo comprobar la carpeta de facturas.")
        return ResultadoValidacionArcaPorAmbiente(
            not errores, "VALIDACION_OFFLINE_OK" if not errores else "CONFIGURACION_ARCA_INVALIDA",
            errores=tuple(errores),
            advertencias=("La validacion offline basica no demuestra habilitacion ARCA ni validez criptografica.",),
            controles_no_realizados=controles, configuracion=configuracion,
        )

    @staticmethod
    def _normalizar_cuit(valor):
        digitos = "".join(caracter for caracter in str(valor or "") if caracter.isdigit())
        return digitos if len(digitos) == 11 else ""

    @staticmethod
    def resolver_desde_emisor_facturacion(emisor_id, cuit_snapshot=None):
        resultado = {
            "ok": False,
            "emisor_fiscal": None,
            "codigo": "",
            "mensaje": "",
        }

        emisor_interno = EmisorService.obtener(emisor_id)
        if not emisor_interno:
            resultado["codigo"] = "EMISOR_INTERNO_NO_ENCONTRADO"
            resultado["mensaje"] = "No se encontro el emisor interno asociado a la factura."
            return resultado

        cuit_interno = EmisorFiscalService._normalizar_cuit(
            emisor_interno[4] if len(emisor_interno) > 4 else ""
        )
        cuit_interno_raw = str(emisor_interno[4] if len(emisor_interno) > 4 else "" or "").strip()
        if cuit_interno_raw and not cuit_interno:
            resultado["codigo"] = "CUIT_INTERNO_INVALIDO"
            resultado["mensaje"] = "El CUIT configurado en el emisor interno es invalido."
            return resultado
        cuit_historico = EmisorFiscalService._normalizar_cuit(cuit_snapshot)
        if cuit_interno and cuit_historico and cuit_interno != cuit_historico:
            resultado["codigo"] = "CUIT_INTERNO_CONTRADICE_SNAPSHOT"
            resultado["mensaje"] = "El CUIT actual del emisor interno contradice el snapshot fiscal."
            return resultado

        emisor_fiscal_id = emisor_interno[19] if len(emisor_interno) > 19 else None
        if emisor_fiscal_id:
            emisor_fiscal = EmisorFiscalService.obtener(emisor_fiscal_id)
            if not emisor_fiscal:
                resultado["codigo"] = "VINCULO_FISCAL_NO_ENCONTRADO"
                resultado["mensaje"] = "El emisor fiscal vinculado no existe."
                return resultado

            cuit_fiscal = EmisorFiscalService._normalizar_cuit(
                emisor_fiscal[3] if len(emisor_fiscal) > 3 else ""
            )
            cuit_fiscal_raw = str(emisor_fiscal[3] if len(emisor_fiscal) > 3 else "" or "").strip()
            if cuit_fiscal_raw and not cuit_fiscal:
                resultado["codigo"] = "CUIT_FISCAL_INVALIDO"
                resultado["mensaje"] = "El CUIT configurado en el emisor fiscal vinculado es invalido."
                return resultado
            if cuit_interno and cuit_fiscal and cuit_interno != cuit_fiscal:
                resultado["codigo"] = "CUIT_VINCULO_INCONSISTENTE"
                resultado["mensaje"] = "El CUIT del emisor fiscal vinculado no coincide con el emisor interno."
                return resultado
            if cuit_historico and cuit_fiscal and cuit_historico != cuit_fiscal:
                resultado["codigo"] = "CUIT_SNAPSHOT_INCONSISTENTE"
                resultado["mensaje"] = "El CUIT del emisor fiscal vinculado contradice el snapshot fiscal."
                return resultado

            resultado.update(ok=True, emisor_fiscal=emisor_fiscal, codigo="VINCULO_EXPLICITO")
            return resultado

        cuit_referencia = cuit_historico or cuit_interno
        if not cuit_referencia:
            resultado["codigo"] = "CUIT_NO_DISPONIBLE"
            resultado["mensaje"] = "No hay un CUIT valido para resolver el emisor fiscal."
            return resultado

        coincidencias = [
            emisor
            for emisor in EmisorFiscalService.listar()
            if EmisorFiscalService._normalizar_cuit(emisor[3] if len(emisor) > 3 else "") == cuit_referencia
        ]
        if not coincidencias:
            resultado["codigo"] = "EMISOR_FISCAL_NO_ENCONTRADO"
            resultado["mensaje"] = "No existe un emisor fiscal con el CUIT del emisor interno."
            return resultado
        if len(coincidencias) > 1:
            resultado["codigo"] = "EMISOR_FISCAL_AMBIGUO"
            resultado["mensaje"] = "Hay mas de un emisor fiscal con el mismo CUIT."
            return resultado

        resultado.update(ok=True, emisor_fiscal=coincidencias[0], codigo="FALLBACK_CUIT_UNICO")
        return resultado

    @staticmethod
    def etiqueta_visible(emisor):
        if not emisor:
            return "No aplica"
        nombre_fantasia = (emisor[2] or "").strip()
        razon_social = (emisor[1] or "").strip()
        return nombre_fantasia or razon_social or "No aplica"

    @staticmethod
    def listar_activos_ordenados_por_id():
        emisores = EmisorFiscalService.listar_activos()
        return sorted(emisores, key=lambda fila: fila[0] or 0)

    @staticmethod
    def resolver_etiqueta(valor):
        texto = (valor or "").strip()
        if not texto or texto == "No aplica":
            return "No aplica"

        if texto.startswith("EMISOR:"):
            try:
                emisor_id = int(texto.split(":", 1)[1])
            except ValueError:
                return texto
            emisor = EmisorFiscalService.obtener(emisor_id)
            return EmisorFiscalService.etiqueta_visible(emisor)

        if texto in ("Monotributo 1", "Monotributo 2"):
            indice = 0 if texto.endswith("1") else 1
            emisores = EmisorFiscalService.listar_activos_ordenados_por_id()
            if len(emisores) > indice:
                return EmisorFiscalService.etiqueta_visible(emisores[indice])
            return "No aplica"

        emisores = EmisorFiscalService.listar()
        for emisor in emisores:
            if texto == EmisorFiscalService.etiqueta_visible(emisor):
                return texto
        return texto

    @staticmethod
    def codificar_seleccion(valor):
        texto = (valor or "").strip()
        if not texto or texto == "No aplica":
            return "No aplica"

        if texto.startswith("EMISOR:"):
            return texto

        emisores = EmisorFiscalService.listar()
        for emisor in emisores:
            if texto == EmisorFiscalService.etiqueta_visible(emisor):
                return f"EMISOR:{emisor[0]}"

        return texto

    @staticmethod
    def listar():
        conn = conectar()
        cur = conn.cursor()
        cur.execute(
            """
            SELECT
                id,
                razon_social,
                nombre_fantasia,
                cuit,
                condicion_iva,
                tipo_factura,
                punto_venta,
                activo,
                observaciones,
                ambiente_arca,
                domicilio,
                ingresos_brutos,
                fecha_inicio_actividades,
                ruta_certificado,
                ruta_clave_privada,
                carpeta_facturas,
                configuracion_arca_completa
            FROM emisores_fiscales
            ORDER BY
                CASE WHEN activo=1 THEN 0 ELSE 1 END,
                COALESCE(NULLIF(nombre_fantasia, ''), razon_social)
            """
        )
        filas = cur.fetchall()
        conn.close()
        return filas

    @staticmethod
    def listar_activos():
        conn = conectar()
        cur = conn.cursor()
        cur.execute(
            """
            SELECT
                id,
                razon_social,
                nombre_fantasia,
                cuit,
                condicion_iva,
                tipo_factura,
                punto_venta,
                activo,
                observaciones,
                ambiente_arca,
                domicilio,
                ingresos_brutos,
                fecha_inicio_actividades,
                ruta_certificado,
                ruta_clave_privada,
                carpeta_facturas,
                configuracion_arca_completa
            FROM emisores_fiscales
            WHERE activo=1
            ORDER BY COALESCE(NULLIF(nombre_fantasia, ''), razon_social)
            """
        )
        filas = cur.fetchall()
        conn.close()
        return filas

    @staticmethod
    def obtener(id_):
        conn = conectar()
        cur = conn.cursor()
        cur.execute(
            """
            SELECT
                id,
                razon_social,
                nombre_fantasia,
                cuit,
                condicion_iva,
                tipo_factura,
                punto_venta,
                activo,
                observaciones,
                ambiente_arca,
                domicilio,
                ingresos_brutos,
                fecha_inicio_actividades,
                ruta_certificado,
                ruta_clave_privada,
                carpeta_facturas,
                configuracion_arca_completa
            FROM emisores_fiscales
            WHERE id=?
            """,
            (id_,),
        )
        fila = cur.fetchone()
        conn.close()
        return fila

    @staticmethod
    def guardar(
        razon_social,
        nombre_fantasia,
        cuit,
        condicion_iva,
        tipo_factura,
        punto_venta,
        activo=1,
        observaciones="",
        ambiente_arca="Homologación",
        domicilio="",
        ingresos_brutos="",
        fecha_inicio_actividades="",
        ruta_certificado="",
        ruta_clave_privada="",
        carpeta_facturas="",
        configuracion_arca_completa=0,
    ):
        conn = conectar()
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO emisores_fiscales(
                razon_social,
                nombre_fantasia,
                cuit,
                condicion_iva,
                tipo_factura,
                punto_venta,
                activo,
                observaciones,
                ambiente_arca,
                domicilio,
                ingresos_brutos,
                fecha_inicio_actividades,
                ruta_certificado,
                ruta_clave_privada,
                carpeta_facturas,
                configuracion_arca_completa
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                razon_social,
                nombre_fantasia,
                cuit,
                condicion_iva,
                tipo_factura,
                punto_venta,
                activo,
                observaciones,
                ambiente_arca,
                domicilio,
                ingresos_brutos,
                fecha_inicio_actividades,
                ruta_certificado,
                ruta_clave_privada,
                carpeta_facturas,
                int(bool(configuracion_arca_completa)),
            ),
        )
        emisor_id = cur.lastrowid
        conn.commit()
        conn.close()
        return emisor_id

    @staticmethod
    def actualizar(
        id_,
        razon_social,
        nombre_fantasia,
        cuit,
        condicion_iva,
        tipo_factura,
        punto_venta,
        activo=1,
        observaciones="",
        ambiente_arca="Homologación",
        domicilio="",
        ingresos_brutos="",
        fecha_inicio_actividades="",
        ruta_certificado="",
        ruta_clave_privada="",
        carpeta_facturas="",
        configuracion_arca_completa=0,
    ):
        conn = conectar()
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE emisores_fiscales
            SET razon_social=?,
                nombre_fantasia=?,
                cuit=?,
                condicion_iva=?,
                tipo_factura=?,
                punto_venta=?,
                activo=?,
                observaciones=?,
                ambiente_arca=?,
                domicilio=?,
                ingresos_brutos=?,
                fecha_inicio_actividades=?,
                ruta_certificado=?,
                ruta_clave_privada=?,
                carpeta_facturas=?,
                configuracion_arca_completa=?
            WHERE id=?
            """,
            (
                razon_social,
                nombre_fantasia,
                cuit,
                condicion_iva,
                tipo_factura,
                punto_venta,
                activo,
                observaciones,
                ambiente_arca,
                domicilio,
                ingresos_brutos,
                fecha_inicio_actividades,
                ruta_certificado,
                ruta_clave_privada,
                carpeta_facturas,
                int(bool(configuracion_arca_completa)),
                id_,
            ),
        )
        conn.commit()
        conn.close()

    @staticmethod
    def cambiar_estado(id_, activo):
        conn = conectar()
        cur = conn.cursor()
        cur.execute(
            "UPDATE emisores_fiscales SET activo=? WHERE id=?",
            (1 if activo else 0, id_),
        )
        conn.commit()
        conn.close()

    @staticmethod
    def validar_configuracion_arca(emisor_id, ruta_certificado=None, ruta_clave_privada=None, carpeta_facturas=None, ambiente_arca=None):
        resultado = {
            "completa": False,
            "faltantes": [],
            "errores": [],
        }

        emisor = EmisorFiscalService.obtener(emisor_id)
        if not emisor:
            resultado["errores"].append("Emisor fiscal no encontrado.")
            return resultado

        cuit = str(emisor[3] or "").strip() if len(emisor) > 3 else ""
        punto_venta = str(emisor[6] or "").strip() if len(emisor) > 6 else ""
        
        # Si se proporciona el ambiente actualmente visible, usar ése; sino, usar el de la BD
        if ambiente_arca is None:
            ambiente_arca = str(emisor[9] or "").strip() if len(emisor) > 9 else ""
        else:
            ambiente_arca = str(ambiente_arca or "").strip()
        
        # Si se proporcionan las rutas actualmente visibles, usar esas; sino, usar las de la BD
        if ruta_certificado is None:
            ruta_certificado = str(emisor[13] or "").strip() if len(emisor) > 13 else ""
        else:
            ruta_certificado = str(ruta_certificado or "").strip()
            
        if ruta_clave_privada is None:
            ruta_clave_privada = str(emisor[14] or "").strip() if len(emisor) > 14 else ""
        else:
            ruta_clave_privada = str(ruta_clave_privada or "").strip()
            
        if carpeta_facturas is None:
            carpeta_facturas = str(emisor[15] or "").strip() if len(emisor) > 15 else ""
        else:
            carpeta_facturas = str(carpeta_facturas or "").strip()

        if not cuit:
            resultado["faltantes"].append("Falta CUIT")
        if not punto_venta:
            resultado["faltantes"].append("Falta punto de venta")
        if ambiente_arca not in {"Homologación", "Producción"}:
            resultado["faltantes"].append("Falta ambiente ARCA")

        if not ruta_certificado:
            resultado["faltantes"].append("Falta ruta del certificado digital")
        elif not os.path.isfile(ruta_certificado):
            resultado["errores"].append("No existe el archivo del certificado digital.")

        if not ruta_clave_privada:
            resultado["faltantes"].append("Falta ruta de la clave privada")
        elif not os.path.isfile(ruta_clave_privada):
            resultado["errores"].append("No existe el archivo de la clave privada.")

        if not carpeta_facturas:
            resultado["faltantes"].append("Falta carpeta de facturas")
        elif not os.path.isdir(carpeta_facturas):
            resultado["errores"].append("No existe la carpeta de facturas.")

        resultado["completa"] = not resultado["faltantes"] and not resultado["errores"]
        return resultado
