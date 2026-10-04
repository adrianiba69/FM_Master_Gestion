import json
import sqlite3
from datetime import datetime
from decimal import Decimal

from database import conectar
from models.intento_emision_arca import IntentoEmisionArca
from services.arca.reconciliacion_contracts import (
    EstadoIntentoEmision,
    ResultadoReconciliacion,
    SnapshotFiscalEsperado,
    normalizar_importe,
)
from services.arca.contexto_fiscal_service import (
    CODIGO_CONTEXTO_CORRUPTO,
    CODIGO_CONTEXTO_DIFERENTE,
    CODIGO_CONTEXTO_GUARDADO,
    CODIGO_CONTEXTO_IDEMPOTENTE,
    CODIGO_CONTEXTO_INVALIDO,
    ContextoFiscalService,
    ResultadoPersistenciaContextoFiscal,
)


AMBIENTES_CANONICOS = ("HOMOLOGACION", "PRODUCCION")


class ConflictoIntentoAmbiguoError(ValueError):
    """Existe un intento activo de ambiente desconocido para la misma clave fiscal."""


class IntentoEmisionArcaService:

    _COLUMNAS = (
        "id, resumen_id, cliente_id, emisor_fiscal_id, emisor_id, cuit_emisor, "
        "punto_venta, tipo_comprobante, numero_planificado, fecha_comprobante, concepto, "
        "tipo_documento, documento_receptor, condicion_iva_receptor_id, importe_total, "
        "importe_neto, importe_iva, importe_exento, importe_no_gravado, importe_tributos, "
        "moneda, cotizacion, alicuotas_iva, estado, cae, vencimiento_cae, error_codigo, "
        "error_mensaje, detalle_tecnico, factura_arca_id, creado_en, actualizado_en, reconciliado_en"
        ", contexto_fiscal_json, contexto_fiscal_version, contexto_fiscal_hash"
    )
    _ESTADOS_ACTIVOS = (
        EstadoIntentoEmision.PENDIENTE_RECONCILIAR.value,
        EstadoIntentoEmision.ENVIANDO.value,
        EstadoIntentoEmision.CONFLICTO_MANUAL.value,
    )

    def __init__(self, conexion_factory=conectar):
        self._conexion_factory = conexion_factory

    @staticmethod
    def _ahora():
        return datetime.now().isoformat(timespec="seconds")

    @staticmethod
    def _serializar_alicuotas(alicuotas):
        def convertir(valor):
            if isinstance(valor, Decimal):
                return format(normalizar_importe(valor), "f")
            if isinstance(valor, dict):
                return {str(clave): convertir(contenido) for clave, contenido in valor.items()}
            if isinstance(valor, (tuple, list)):
                return [convertir(contenido) for contenido in valor]
            return valor

        return json.dumps(convertir(tuple(alicuotas or ())), ensure_ascii=True, sort_keys=True, separators=(",", ":"))

    @staticmethod
    def _deserializar_alicuotas(valor):
        try:
            datos = json.loads(str(valor or "[]"))
        except (TypeError, ValueError, json.JSONDecodeError) as error:
            raise ValueError("Alicuotas IVA persistidas inválidas.") from error
        if not isinstance(datos, list):
            raise ValueError("Alicuotas IVA persistidas inválidas.")
        return tuple(datos)

    @staticmethod
    def _validar_estado(estado):
        try:
            valor = estado.value if isinstance(estado, EstadoIntentoEmision) else str(estado)
            return EstadoIntentoEmision(valor).value
        except ValueError as error:
            raise ValueError(f"Estado de intento inválido: {estado!r}") from error

    @staticmethod
    def _normalizar_cuit(cuit):
        return "".join(caracter for caracter in str(cuit or "") if caracter.isdigit())

    @staticmethod
    def _tiene_columna_ambiente(cursor):
        cursor.execute("PRAGMA table_info(intentos_emision_arca)")
        return any(fila[1] == "ambiente_arca" for fila in cursor.fetchall())

    @classmethod
    def _select_columnas(cls, cursor):
        # Esquema fisicamente antiguo (sin columna): se lee como NULL, nunca como un ambiente.
        return cls._COLUMNAS + (", ambiente_arca" if cls._tiene_columna_ambiente(cursor) else ", NULL")

    @classmethod
    def evaluar_coherencia_contexto(
        cls, contexto, cuit_emisor, punto_venta, tipo_comprobante, numero_planificado, ambiente_columna=None,
    ):
        """Devuelve (ambiente_contexto, codigo, errores); codigo None si contexto, columna e identidad concuerdan."""
        ambiente = contexto.get("ambiente") if isinstance(contexto, dict) else None
        if ambiente not in AMBIENTES_CANONICOS:
            return None, "AMBIENTE_CONTEXTO_INVALIDO", (f"ambiente del contexto no canonico: {ambiente!r}",)
        try:
            emisor = contexto["emisor"]
            comprobante = contexto["comprobante"]
            puntos = {
                int(valor) for valor in (comprobante.get("punto_venta_num"), emisor.get("punto_venta_num"))
                if valor is not None
            }
            if not puntos:
                raise KeyError("punto_venta_num")
            contexto_cuit = cls._normalizar_cuit(emisor["cuit"])
            contexto_tipo = int(comprobante["tipo_comprobante_num"])
            contexto_numero = int(comprobante["numero_comprobante_planificado"])
            esperado = (cls._normalizar_cuit(cuit_emisor), int(punto_venta), int(tipo_comprobante), int(numero_planificado))
        except (AttributeError, KeyError, TypeError, ValueError) as error:
            return ambiente, "CONTEXTO_INCOMPLETO", (f"identidad del contexto incompleta: {error!r}",)
        if ambiente_columna is not None and ambiente_columna != ambiente:
            return ambiente, "CONFLICTO_AMBIENTE", (
                f"ambiente_arca {ambiente_columna!r} contradice el contexto {ambiente!r}",
            )
        if len(puntos) != 1 or (contexto_cuit, next(iter(puntos)), contexto_tipo, contexto_numero) != esperado:
            return ambiente, "CONFLICTO_IDENTIDAD", (
                "identidad escalar del intento contradice el contexto fiscal",
            )
        return ambiente, None, ()

    @classmethod
    def _desde_fila(cls, fila):
        if not fila:
            return None
        datos = list(fila)
        for indice in (14, 15, 16, 17, 18, 19, 21):
            datos[indice] = normalizar_importe(datos[indice])
        datos[22] = cls._deserializar_alicuotas(datos[22])
        return IntentoEmisionArca(*datos)

    @classmethod
    def _parametros_snapshot(cls, snapshot, estado, ahora):
        if not isinstance(snapshot, SnapshotFiscalEsperado):
            raise TypeError("snapshot debe ser SnapshotFiscalEsperado.")
        return (
            snapshot.resumen_id, snapshot.cliente_id, snapshot.emisor_fiscal_id, snapshot.emisor_id,
            cls._normalizar_cuit(snapshot.cuit_emisor), snapshot.punto_venta, snapshot.tipo_comprobante,
            snapshot.numero_planificado, snapshot.fecha_comprobante, snapshot.concepto, snapshot.tipo_documento,
            snapshot.documento_receptor, snapshot.condicion_iva_receptor_id,
            format(normalizar_importe(snapshot.importe_total), "f"),
            format(normalizar_importe(snapshot.importe_neto), "f"),
            format(normalizar_importe(snapshot.importe_iva), "f"),
            format(normalizar_importe(snapshot.importe_exento), "f"),
            format(normalizar_importe(snapshot.importe_no_gravado), "f"),
            format(normalizar_importe(snapshot.importe_tributos), "f"),
            str(snapshot.moneda or "").strip(), format(normalizar_importe(snapshot.cotizacion), "f"),
            cls._serializar_alicuotas(snapshot.alicuotas_iva), estado, ahora, ahora,
        )

    @staticmethod
    def _parametros_contexto_fiscal(contexto_fiscal_json, contexto_fiscal_version, contexto_fiscal_hash):
        valores = (contexto_fiscal_json, contexto_fiscal_version, contexto_fiscal_hash)
        if all(valor is None for valor in valores):
            return (None, None, None)
        if any(valor is None for valor in valores):
            raise ValueError("El contexto fiscal del intento debe informarse completo.")

        integridad = ContextoFiscalService.validar_integridad(
            contexto_fiscal_json,
            contexto_fiscal_version,
            contexto_fiscal_hash,
        )
        if not integridad.valido:
            raise ValueError("Contexto fiscal inválido para crear intento: " + "; ".join(integridad.errores))
        return (integridad.json_canonico, integridad.version, integridad.hash_calculado)

    @classmethod
    def _resolver_ambiente_nuevo(cls, snapshot, contexto_valores, ambiente_arca):
        if ambiente_arca is not None and ambiente_arca not in AMBIENTES_CANONICOS:
            raise ValueError(f"ambiente_arca no canonico: {ambiente_arca!r}")
        if contexto_valores[0] is None:
            return ambiente_arca
        ambiente, codigo, errores = cls.evaluar_coherencia_contexto(
            json.loads(contexto_valores[0]), snapshot.cuit_emisor, snapshot.punto_venta,
            snapshot.tipo_comprobante, snapshot.numero_planificado, ambiente_arca,
        )
        if codigo:
            raise ValueError(f"Contexto fiscal incoherente con el intento ({codigo}): " + "; ".join(errores))
        return ambiente

    def crear_intento(
        self,
        snapshot,
        estado=EstadoIntentoEmision.PENDIENTE_RECONCILIAR,
        contexto_fiscal_json=None,
        contexto_fiscal_version=None,
        contexto_fiscal_hash=None,
        ambiente_arca=None,
    ):
        estado_normalizado = self._validar_estado(estado)
        contexto_fiscal_valores = self._parametros_contexto_fiscal(
            contexto_fiscal_json,
            contexto_fiscal_version,
            contexto_fiscal_hash,
        )
        ambiente = self._resolver_ambiente_nuevo(snapshot, contexto_fiscal_valores, ambiente_arca)
        parametros = self._parametros_snapshot(snapshot, estado_normalizado, self._ahora()) + contexto_fiscal_valores
        conexion = self._conexion_factory()
        try:
            cursor = conexion.cursor()
            cursor.execute("BEGIN IMMEDIATE")
            tiene_ambiente = self._tiene_columna_ambiente(cursor)
            if ambiente is not None and not tiene_ambiente:
                raise ValueError("El esquema de intentos no tiene ambiente_arca para persistir el ambiente.")
            if ambiente is not None and estado_normalizado in self._ESTADOS_ACTIVOS:
                cursor.execute(
                    "SELECT id FROM intentos_emision_arca WHERE ambiente_arca IS NULL AND cuit_emisor=? "
                    f"AND punto_venta=? AND tipo_comprobante=? AND numero_planificado=? AND estado IN ({','.join('?' for _ in self._ESTADOS_ACTIVOS)}) ORDER BY id",
                    (parametros[4], parametros[5], parametros[6], parametros[7], *self._ESTADOS_ACTIVOS),
                )
                ambiguos = [fila[0] for fila in cursor.fetchall()]
                if ambiguos:
                    raise ConflictoIntentoAmbiguoError(
                        f"Intento activo de ambiente desconocido para la misma clave fiscal: ids {ambiguos}."
                    )
            cursor.execute(
                f"""
                INSERT INTO intentos_emision_arca(
                    resumen_id, cliente_id, emisor_fiscal_id, emisor_id, cuit_emisor,
                    punto_venta, tipo_comprobante, numero_planificado, fecha_comprobante,
                    concepto, tipo_documento, documento_receptor, condicion_iva_receptor_id,
                    importe_total, importe_neto, importe_iva, importe_exento,
                    importe_no_gravado, importe_tributos, moneda, cotizacion, alicuotas_iva,
                    estado, creado_en, actualizado_en,
                    contexto_fiscal_json, contexto_fiscal_version, contexto_fiscal_hash{', ambiente_arca' if tiene_ambiente else ''}
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?{',?' if tiene_ambiente else ''})
                """,
                parametros + ((ambiente,) if tiene_ambiente else ()),
            )
            intento_id = cursor.lastrowid
            conexion.commit()
            return intento_id
        except Exception:
            conexion.rollback()
            raise
        finally:
            conexion.close()

    def obtener(self, intento_id):
        conexion = self._conexion_factory()
        try:
            cursor = conexion.cursor()
            cursor.execute(
                f"SELECT {self._select_columnas(cursor)} FROM intentos_emision_arca WHERE id=?", (int(intento_id),)
            )
            return self._desde_fila(cursor.fetchone())
        finally:
            conexion.close()

    def guardar_contexto_fiscal_si_ausente(
        self,
        intento_id,
        contexto_fiscal_json,
        contexto_fiscal_version,
        contexto_fiscal_hash,
    ):
        integridad = ContextoFiscalService.validar_integridad(
            contexto_fiscal_json,
            contexto_fiscal_version,
            contexto_fiscal_hash,
        )
        if not integridad.valido:
            return ResultadoPersistenciaContextoFiscal(
                False,
                CODIGO_CONTEXTO_INVALIDO,
                "; ".join(integridad.errores),
            )

        conexion = self._conexion_factory()
        try:
            conexion.execute("BEGIN IMMEDIATE")
            columna_ambiente = (
                "ambiente_arca" if self._tiene_columna_ambiente(conexion.cursor()) else "NULL"
            )
            fila = conexion.execute(
                "SELECT contexto_fiscal_json, contexto_fiscal_version, contexto_fiscal_hash, "
                f"cuit_emisor, punto_venta, tipo_comprobante, numero_planificado, {columna_ambiente} "
                "FROM intentos_emision_arca WHERE id=?",
                (int(intento_id),),
            ).fetchone()
            if fila is None:
                return ResultadoPersistenciaContextoFiscal(
                    False, CODIGO_CONTEXTO_INVALIDO, "intento de emisión inexistente"
                )

            actual_json, actual_version, actual_hash, *identidad_y_ambiente = fila
            campos_vacios = (actual_json is None, actual_version is None, actual_hash is None)
            if all(campos_vacios):
                _, codigo, errores = self.evaluar_coherencia_contexto(
                    integridad.contexto, *identidad_y_ambiente
                )
                if codigo:
                    conexion.rollback()
                    return ResultadoPersistenciaContextoFiscal(
                        False, CODIGO_CONTEXTO_INVALIDO, f"{codigo}: " + "; ".join(errores)
                    )
                conexion.execute(
                    "UPDATE intentos_emision_arca SET contexto_fiscal_json=?, "
                    "contexto_fiscal_version=?, contexto_fiscal_hash=? WHERE id=?",
                    (
                        integridad.json_canonico,
                        integridad.version,
                        integridad.hash_calculado,
                        int(intento_id),
                    ),
                )
                conexion.commit()
                return ResultadoPersistenciaContextoFiscal(
                    True, CODIGO_CONTEXTO_GUARDADO, actualizado=True
                )

            if any(campos_vacios):
                conexion.rollback()
                return ResultadoPersistenciaContextoFiscal(
                    False, CODIGO_CONTEXTO_CORRUPTO, "contexto fiscal almacenado incompleto"
                )

            actual = ContextoFiscalService.validar_integridad(actual_json, actual_version, actual_hash)
            if not actual.valido:
                conexion.rollback()
                return ResultadoPersistenciaContextoFiscal(
                    False, CODIGO_CONTEXTO_CORRUPTO, "; ".join(actual.errores)
                )

            if actual.hash_calculado == integridad.hash_calculado:
                conexion.commit()
                return ResultadoPersistenciaContextoFiscal(
                    True, CODIGO_CONTEXTO_IDEMPOTENTE, idempotente=True
                )

            conexion.rollback()
            return ResultadoPersistenciaContextoFiscal(
                False, CODIGO_CONTEXTO_DIFERENTE, "contexto fiscal existente diferente"
            )
        except Exception:
            conexion.rollback()
            raise
        finally:
            conexion.close()

    def actualizar_estado(self, intento_id, estado, error_codigo=None, error_mensaje=None, detalle_tecnico=None):
        estado_normalizado = self._validar_estado(estado)
        conexion = self._conexion_factory()
        try:
            cursor = conexion.cursor()
            cursor.execute(
                "UPDATE intentos_emision_arca SET estado=?, error_codigo=?, error_mensaje=?, detalle_tecnico=?, actualizado_en=? WHERE id=?",
                (estado_normalizado, error_codigo, error_mensaje, detalle_tecnico, self._ahora(), int(intento_id)),
            )
            if cursor.rowcount != 1:
                raise LookupError(f"Intento de emisión ARCA inexistente: {intento_id}")
            conexion.commit()
        except Exception:
            conexion.rollback()
            raise
        finally:
            conexion.close()

    def guardar_resultado_reconciliacion(
        self, intento_id, resultado, cae="", vencimiento_cae="", factura_arca_id=None,
        error_codigo=None, error_mensaje=None, detalle_tecnico=None,
    ):
        try:
            valor = resultado.value if isinstance(resultado, ResultadoReconciliacion) else str(resultado)
            resultado_normalizado = ResultadoReconciliacion(valor).value
        except ValueError as error:
            raise ValueError(f"Resultado de reconciliación inválido: {resultado!r}") from error
        estado = {
            ResultadoReconciliacion.AUTORIZADO.value: EstadoIntentoEmision.RECONCILIADO.value,
            ResultadoReconciliacion.NO_AUTORIZADO.value: EstadoIntentoEmision.NO_AUTORIZADO.value,
            ResultadoReconciliacion.CONFLICTO.value: EstadoIntentoEmision.CONFLICTO_MANUAL.value,
            ResultadoReconciliacion.CONSULTA_INCIERTA.value: EstadoIntentoEmision.PENDIENTE_RECONCILIAR.value,
        }[resultado_normalizado]
        ahora = self._ahora()
        reconciliado_en = ahora if estado != EstadoIntentoEmision.PENDIENTE_RECONCILIAR.value else None
        conexion = self._conexion_factory()
        try:
            cursor = conexion.cursor()
            cursor.execute(
                """
                UPDATE intentos_emision_arca
                SET estado=?, cae=?, vencimiento_cae=?, error_codigo=?, error_mensaje=?, detalle_tecnico=?,
                    factura_arca_id=?, actualizado_en=?, reconciliado_en=?
                WHERE id=?
                """,
                (estado, str(cae or ""), str(vencimiento_cae or ""), error_codigo, error_mensaje,
                 detalle_tecnico, factura_arca_id, ahora, reconciliado_en, int(intento_id)),
            )
            if cursor.rowcount != 1:
                raise LookupError(f"Intento de emisión ARCA inexistente: {intento_id}")
            conexion.commit()
        except Exception:
            conexion.rollback()
            raise
        finally:
            conexion.close()

    def listar_pendientes_reconciliacion(self):
        marcadores = ",".join("?" for _ in self._ESTADOS_ACTIVOS)
        conexion = self._conexion_factory()
        try:
            cursor = conexion.cursor()
            cursor.execute(
                f"SELECT {self._select_columnas(cursor)} FROM intentos_emision_arca WHERE estado IN ({marcadores}) ORDER BY creado_en, id",
                self._ESTADOS_ACTIVOS,
            )
            return [self._desde_fila(fila) for fila in cursor.fetchall()]
        finally:
            conexion.close()

    def contar_pendientes_reconciliacion(self):
        conexion = self._conexion_factory()
        try:
            cursor = conexion.cursor()
            cursor.execute(
                "SELECT estado, COUNT(*) FROM intentos_emision_arca "
                "WHERE estado IN (?,?,?) GROUP BY estado",
                self._ESTADOS_ACTIVOS,
            )
            conteos = {estado: 0 for estado in self._ESTADOS_ACTIVOS}
            for estado, cantidad in cursor.fetchall():
                conteos[estado] = int(cantidad or 0)
            return {
                "total": sum(conteos.values()),
                "ENVIANDO": conteos[EstadoIntentoEmision.ENVIANDO.value],
                "PENDIENTE_RECONCILIAR": conteos[EstadoIntentoEmision.PENDIENTE_RECONCILIAR.value],
                "CONFLICTO_MANUAL": conteos[EstadoIntentoEmision.CONFLICTO_MANUAL.value],
            }
        finally:
            conexion.close()

    def listar_activos_por_resumen(self, resumen_id):
        marcadores = ",".join("?" for _ in self._ESTADOS_ACTIVOS)
        conexion = self._conexion_factory()
        try:
            cursor = conexion.cursor()
            cursor.execute(
                f"SELECT {self._select_columnas(cursor)} FROM intentos_emision_arca "
                f"WHERE resumen_id=? AND estado IN ({marcadores}) ORDER BY id DESC",
                (int(resumen_id), *self._ESTADOS_ACTIVOS),
            )
            return [self._desde_fila(fila) for fila in cursor.fetchall()]
        finally:
            conexion.close()

    def obtener_por_clave_fiscal(
        self, cuit_emisor, punto_venta, tipo_comprobante, numero_planificado, ambiente_arca=None,
    ):
        """Con ambiente_arca solo devuelve ese ambiente exacto; sin el, todos (listado legacy)."""
        conexion = self._conexion_factory()
        try:
            cursor = conexion.cursor()
            consulta = (
                f"SELECT {self._select_columnas(cursor)} FROM intentos_emision_arca "
                "WHERE cuit_emisor=? AND punto_venta=? AND tipo_comprobante=? AND numero_planificado=?"
            )
            parametros = [
                self._normalizar_cuit(cuit_emisor), int(punto_venta), int(tipo_comprobante), int(numero_planificado),
            ]
            if ambiente_arca is not None and self._tiene_columna_ambiente(cursor):
                consulta += " AND ambiente_arca=?"
                parametros.append(ambiente_arca)
            cursor.execute(consulta + " ORDER BY id DESC", tuple(parametros))
            return [self._desde_fila(fila) for fila in cursor.fetchall()]
        finally:
            conexion.close()

    def buscar_activos_por_clave_fiscal(
        self, cuit_emisor, punto_venta, tipo_comprobante, numero_planificado, ambiente_arca,
    ):
        """Para una operacion nueva con ambiente conocido: (activos del mismo ambiente, activos NULL ambiguos).

        El ambiente opuesto nunca es candidato.
        """
        if ambiente_arca not in AMBIENTES_CANONICOS:
            raise ValueError(f"ambiente_arca no canonico: {ambiente_arca!r}")
        activos = [
            intento for intento in self.obtener_por_clave_fiscal(
                cuit_emisor, punto_venta, tipo_comprobante, numero_planificado
            )
            if intento.estado in self._ESTADOS_ACTIVOS
        ]
        return (
            [intento for intento in activos if intento.ambiente_arca == ambiente_arca],
            [intento for intento in activos if intento.ambiente_arca is None],
        )

    def obtener_factura_para_validacion(self, factura_arca_id):
        """Lectura local de la factura vinculada; None si no existe. Sin red ni escrituras."""
        conexion = self._conexion_factory()
        try:
            cursor = conexion.cursor()
            cursor.execute("PRAGMA table_info(factura_arca)")
            disponibles = {fila[1] for fila in cursor.fetchall()}
            if not disponibles:
                return None
            nombres = [
                nombre for nombre in (
                    "id", "cliente_id", "emisor_id", "resumen_id", "numero_factura", "cae",
                    "punto_venta_num", "tipo_comprobante_num", "numero_comprobante_num", "ambiente_arca",
                ) if nombre in disponibles
            ]
            cursor.execute(f"SELECT {', '.join(nombres)} FROM factura_arca WHERE id=?", (int(factura_arca_id),))
            fila = cursor.fetchone()
            if fila is None:
                return None
            datos = dict(zip(nombres, fila))
            datos["_esquema_con_ambiente"] = "ambiente_arca" in disponibles
            return datos
        finally:
            conexion.close()