from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

from models.factura_arca import FacturaArca
from pdf.nombre_archivos import nombre_factura_pdf
from services.arca import ambiente_arca
from services.arca.homologacion_service import HomologacionService
from services.arca.cierre_local_arca_service import CierreLocalArcaService
from services.arca.contexto_fiscal_service import CONTEXTO_FISCAL_VERSION
from services.arca.pdf_fiscal_service import PDFFiscalService
from services.arca.reconciliacion_contracts import ResultadoReconciliacion, SnapshotFiscalEsperado
from services.arca.snapshot_fiscal_pdf_adapter import construir_datos_pdf_desde_snapshot
from services.arca.snapshot_fiscal_service import (
    SnapshotFiscalError,
    calcular_hash_snapshot,
    construir_snapshot_fiscal_v1,
    serializar_snapshot_fiscal,
)
from services.cliente_service import ClienteService
from services.emisor_fiscal_service import EmisorFiscalService
from services.emisor_service import EmisorService
from services.factura_arca_service import FacturaArcaService
from services.intento_emision_arca_service import IntentoEmisionArcaService
from services.resumen_service import ResumenService


@dataclass
class ResultadoFacturacion:
    ok: bool
    datos: dict
    errores: list


class FacturacionService:

    @staticmethod
    def _a_fecha_arca_yyyymmdd(valor):
        texto = str(valor or "").strip()
        if len(texto) == 8 and texto.isdigit():
            return texto
        if len(texto) == 10 and texto[4] == "-" and texto[7] == "-":
            return texto.replace("-", "")
        return texto

    @staticmethod
    def _combinar_domicilio_cliente(cliente_fila):
        direccion = str(cliente_fila[5] if len(cliente_fila) > 5 else "" or "").strip()
        localidad = str(cliente_fila[6] if len(cliente_fila) > 6 else "" or "").strip()
        if direccion and localidad:
            return f"{direccion} - {localidad}"
        return direccion or localidad

    @staticmethod
    def _a_fecha_iso_snapshot(valor):
        """Convierte YYYYMMDD, YYYY-MM-DD o DD/MM/YYYY a YYYY-MM-DD; None si no reconocible (ausencia valida)."""
        texto = str(valor or "").strip()
        if len(texto) == 8 and texto.isdigit():
            return f"{texto[0:4]}-{texto[4:6]}-{texto[6:8]}"
        if len(texto) == 10 and texto[4] == "-" and texto[7] == "-":
            return texto
        if len(texto) == 10 and texto[2] == "/" and texto[5] == "/":
            partes = texto.split("/")
            if len(partes) == 3 and len(partes[0]) == 2 and len(partes[1]) == 2 and len(partes[2]) == 4:
                if partes[0].isdigit() and partes[1].isdigit() and partes[2].isdigit():
                    return f"{partes[2]}-{partes[1]}-{partes[0]}"
        return None

    @classmethod
    def _construir_contexto_fiscal_base(
        cls,
        ambiente_normalizado,
        emisor_fiscal,
        emisor_facturacion_id,
        cuit_emisor_normalizado,
        punto_venta_num,
        cliente,
        condicion_iva,
        documento_normalizado,
        tipo_documento,
        documento_receptor,
        tipo_comprobante,
        tipo_factura_normalizado,
        fecha_comprobante,
        periodo_desde,
        periodo_hasta,
        vencimiento_pago_arca,
        moneda,
        cotizacion,
        neto_factura,
        importe_iva_factura,
        alicuota_iva,
        total_factura_fiscal,
        importe_exento_factura,
        importe_tot_conc,
        importe_tributos,
        alicuotas_iva,
        items_factura,
    ):
        """Construye el contexto fiscal BASE (sin numero planificado ni CAE/sin secretos)
        con todos los datos ya resueltos, antes de invocar a HomologacionService."""
        cuit_emisor_fiscal_normalizado = cls._normalizar_cuit(
            emisor_fiscal[3] if len(emisor_fiscal) > 3 else ""
        )
        if cuit_emisor_fiscal_normalizado != cuit_emisor_normalizado:
            return {
                "ok": False,
                "errores": [
                    "contradiccion_cuit_emisor: el CUIT del emisor fiscal seleccionado no coincide "
                    "con el CUIT utilizado en la operacion ARCA."
                ],
            }

        ahora_iso = datetime.now().isoformat(timespec="seconds")
        cuit_o_doc = str(documento_normalizado or "").strip() or "0"

        emisor_contexto = {
            "emisor_id": int(emisor_facturacion_id),
            "emisor_fiscal_id": int(emisor_fiscal[0]),
            "razon_social": str(emisor_fiscal[1] if len(emisor_fiscal) > 1 else "" or ""),
            "nombre_fantasia": str(emisor_fiscal[2]).strip() if len(emisor_fiscal) > 2 and str(emisor_fiscal[2] or "").strip() else None,
            "cuit": cuit_emisor_normalizado,
            "condicion_iva": str(emisor_fiscal[4] if len(emisor_fiscal) > 4 else "" or ""),
            "domicilio": str(emisor_fiscal[10]).strip() if len(emisor_fiscal) > 10 and str(emisor_fiscal[10] or "").strip() else None,
            "ingresos_brutos": str(emisor_fiscal[11]).strip() if len(emisor_fiscal) > 11 and str(emisor_fiscal[11] or "").strip() else None,
            "fecha_inicio_actividades": cls._a_fecha_iso_snapshot(emisor_fiscal[12] if len(emisor_fiscal) > 12 else ""),
            "punto_venta_num": int(punto_venta_num),
        }

        receptor_contexto = {
            "cliente_id": int(cliente[0]),
            "razon_social": str(cliente[2] if len(cliente) > 2 else "" or ""),
            "documento_visible": cuit_o_doc,
            "condicion_iva": str(condicion_iva or ""),
            "domicilio": cls._combinar_domicilio_cliente(cliente) or None,
            "tipo_documento_receptor": int(tipo_documento),
            "documento_receptor": int(documento_receptor),
        }

        comprobante_contexto = {
            "fecha": cls._a_fecha_iso_snapshot(fecha_comprobante),
            "fecha_arca": str(fecha_comprobante or ""),
            "concepto": 1,
            "concepto_descripcion": "Productos",
            "punto_venta_num": int(punto_venta_num),
            "tipo_comprobante_num": int(tipo_comprobante),
            "tipo_comprobante_texto": str(tipo_factura_normalizado or ""),
            "numero_comprobante_planificado": None,
            "numero_textual_planificado": None,
            "moneda": str(moneda or "PES"),
            "cotizacion": Decimal(str(cotizacion or 1)),
            "periodo_servicio_desde": cls._a_fecha_iso_snapshot(periodo_desde),
            "periodo_servicio_hasta": cls._a_fecha_iso_snapshot(periodo_hasta),
            "vencimiento_pago": cls._a_fecha_iso_snapshot(vencimiento_pago_arca),
        }

        importes_contexto = {
            "total": Decimal(str(total_factura_fiscal)),
            "neto": Decimal(str(neto_factura)),
            "iva": Decimal(str(importe_iva_factura)),
            "exento": Decimal(str(importe_exento_factura)),
            "no_gravado": Decimal(str(importe_tot_conc)),
            "tributos": Decimal(str(importe_tributos)),
        }

        iva_contexto = [
            {
                "id": int(item.get("id")),
                "base_imponible": Decimal(str(item.get("base_imponible"))),
                "importe": Decimal(str(item.get("importe"))),
                "porcentaje": Decimal(str(alicuota_iva)),
            }
            for item in (alicuotas_iva or [])
        ]

        items_contexto = [
            {
                "concepto": (str(item.get("concepto")).strip() or None) if item.get("concepto") is not None else None,
                "descripcion": str(item.get("descripcion") or ""),
                "cantidad": Decimal(str(item.get("cantidad"))),
                "precio_unitario": Decimal(str(item.get("precio_unitario"))),
                "subtotal": Decimal(str(item.get("importe"))),
            }
            for item in (items_factura or [])
        ]

        contexto = {
            "tipo": "contexto_fiscal_arca",
            "version": CONTEXTO_FISCAL_VERSION,
            "creado_en": ahora_iso,
            "ambiente": ambiente_normalizado,
            "emisor": emisor_contexto,
            "receptor": receptor_contexto,
            "comprobante": comprobante_contexto,
            "importes": importes_contexto,
            "iva": iva_contexto,
            "items": items_contexto,
        }
        return {"ok": True, "contexto": contexto, "errores": []}

    @classmethod
    def _construir_snapshot_fiscal_cierre_normal(
        cls,
        emisor_fiscal,
        emisor_facturacion_id,
        cuit_emisor_normalizado,
        punto_venta_num,
        cliente,
        condicion_iva,
        documento_normalizado,
        tipo_documento,
        documento_receptor,
        tipo_comprobante,
        tipo_factura_normalizado,
        numero_comprobante,
        numero_factura,
        fecha_comprobante,
        periodo_desde,
        periodo_hasta,
        vencimiento_pago_arca,
        moneda,
        cotizacion,
        neto_factura,
        importe_iva_factura,
        alicuota_iva,
        total_factura_fiscal,
        importe_exento_factura,
        importe_tot_conc,
        importe_tributos,
        alicuotas_iva,
        items_factura,
        cae,
        vencimiento_cae,
        ambiente_normalizado,
    ):
        """Congela el snapshot fiscal v1 desde el contexto de emision ya resuelto (sin
        volver a consultar ClienteService/EmisorFiscalService/ResumenService)."""
        try:
            ambiente_snapshot = ambiente_arca.normalizar_ambiente_arca(ambiente_normalizado)
        except ambiente_arca.AmbienteArcaInvalidoError as error:
            return {"ok": False, "errores": [f"ambiente_arca_invalido: {error}"]}

        cuit_emisor_fiscal_normalizado = cls._normalizar_cuit(
            emisor_fiscal[3] if len(emisor_fiscal) > 3 else ""
        )
        if cuit_emisor_fiscal_normalizado != cuit_emisor_normalizado:
            return {
                "ok": False,
                "errores": [
                    "contradiccion_cuit_emisor: el CUIT del emisor fiscal seleccionado no coincide "
                    "con el CUIT utilizado en la operacion ARCA."
                ],
            }

        ahora_iso = datetime.now().isoformat(timespec="seconds")
        cuit_o_doc = str(documento_normalizado or "").strip() or "0"

        emisor_snapshot = {
            "emisor_id": int(emisor_facturacion_id),
            "emisor_fiscal_id": int(emisor_fiscal[0]),
            "razon_social": str(emisor_fiscal[1] if len(emisor_fiscal) > 1 else "" or ""),
            "nombre_fantasia": str(emisor_fiscal[2]).strip() if len(emisor_fiscal) > 2 and str(emisor_fiscal[2] or "").strip() else None,
            "cuit": cuit_emisor_normalizado,
            "condicion_iva": str(emisor_fiscal[4] if len(emisor_fiscal) > 4 else "" or ""),
            "domicilio": str(emisor_fiscal[10]).strip() if len(emisor_fiscal) > 10 and str(emisor_fiscal[10] or "").strip() else None,
            "ingresos_brutos": str(emisor_fiscal[11]).strip() if len(emisor_fiscal) > 11 and str(emisor_fiscal[11] or "").strip() else None,
            "fecha_inicio_actividades": cls._a_fecha_iso_snapshot(emisor_fiscal[12] if len(emisor_fiscal) > 12 else ""),
            "punto_venta_num": int(punto_venta_num),
        }

        receptor_snapshot = {
            "cliente_id": int(cliente[0]),
            "razon_social": str(cliente[2] if len(cliente) > 2 else "" or ""),
            "documento_visible": cuit_o_doc,
            "condicion_iva": str(condicion_iva or ""),
            "domicilio": cls._combinar_domicilio_cliente(cliente) or None,
            "tipo_documento_receptor": int(tipo_documento),
            "documento_receptor": int(documento_receptor),
        }

        comprobante_snapshot = {
            "fecha": cls._a_fecha_iso_snapshot(fecha_comprobante),
            "fecha_arca": str(fecha_comprobante or ""),
            "concepto": 1,
            "concepto_descripcion": "Productos",
            "punto_venta_num": int(punto_venta_num),
            "tipo_comprobante_num": int(tipo_comprobante),
            "tipo_comprobante_texto": str(tipo_factura_normalizado or ""),
            "numero_comprobante_num": int(numero_comprobante),
            "numero_textual": str(numero_factura or ""),
            "periodo_servicio_desde": cls._a_fecha_iso_snapshot(periodo_desde),
            "periodo_servicio_hasta": cls._a_fecha_iso_snapshot(periodo_hasta),
            "vencimiento_pago": cls._a_fecha_iso_snapshot(vencimiento_pago_arca),
            "moneda": str(moneda or "PES"),
            "cotizacion": Decimal(str(cotizacion or 1)),
        }

        importes_snapshot = {
            "total": Decimal(str(total_factura_fiscal)),
            "neto": Decimal(str(neto_factura)),
            "iva": Decimal(str(importe_iva_factura)),
            "exento": Decimal(str(importe_exento_factura)),
            "no_gravado": Decimal(str(importe_tot_conc)),
            "tributos": Decimal(str(importe_tributos)),
        }

        iva_snapshot = [
            {
                "id": int(item.get("id")),
                "base_imponible": Decimal(str(item.get("base_imponible"))),
                "importe": Decimal(str(item.get("importe"))),
                "porcentaje": Decimal(str(alicuota_iva)),
            }
            for item in (alicuotas_iva or [])
        ]

        items_snapshot = [
            {
                "concepto": (str(item.get("concepto")).strip() or None) if item.get("concepto") is not None else None,
                "descripcion": str(item.get("descripcion") or ""),
                "cantidad": Decimal(str(item.get("cantidad"))),
                "precio_unitario": Decimal(str(item.get("precio_unitario"))),
                "subtotal": Decimal(str(item.get("importe"))),
            }
            for item in (items_factura or [])
        ]

        autorizacion_snapshot = {
            "cae": str(cae or ""),
            "vencimiento_cae": cls._a_fecha_iso_snapshot(vencimiento_cae),
            "vencimiento_cae_arca": str(vencimiento_cae or ""),
            "tipo_cod_aut": "E",
            "resultado": "AUTORIZADO",
            "cerrado_en": ahora_iso,
        }

        try:
            snapshot = construir_snapshot_fiscal_v1(
                fuente="cierre_normal",
                creado_en=ahora_iso,
                ambiente=ambiente_snapshot,
                emisor=emisor_snapshot,
                receptor=receptor_snapshot,
                comprobante=comprobante_snapshot,
                importes=importes_snapshot,
                iva=iva_snapshot,
                items=items_snapshot,
                autorizacion=autorizacion_snapshot,
            )
            json_text = serializar_snapshot_fiscal(snapshot)
            snapshot_hash = calcular_hash_snapshot(json_text)
        except SnapshotFiscalError as error:
            return {"ok": False, "errores": [f"snapshot_fiscal_invalido: {error}"]}

        return {
            "ok": True,
            "snapshot": snapshot,
            "snapshot_json": json_text,
            "snapshot_version": snapshot["version"],
            "snapshot_hash": snapshot_hash,
        }

    @staticmethod
    def _sumar_importes_conceptos(conceptos):
        total = 0.0
        for concepto in list(conceptos or []):
            cantidad = float(getattr(concepto, "cantidad", 0) or 0)
            precio_unitario = float(getattr(concepto, "importe", 0) or 0)
            importe = float(getattr(concepto, "total", 0) or 0)
            if abs(importe) <= 0.0 and cantidad > 0:
                importe = cantidad * precio_unitario
            total += float(round(importe, 2))
        return float(round(total, 2))

    @staticmethod
    def _sumar_importes_items(items):
        return float(round(sum(float(item.get("importe", 0) or 0) for item in list(items or [])), 2))

    @staticmethod
    def _normalizar_etiqueta_emisor(valor):
        texto = str(valor or "").strip().lower()
        return "".join(caracter for caracter in texto if caracter.isalnum())

    @staticmethod
    def _normalizar_cuit(cuit):
        texto = str(cuit or "").strip()
        digitos = "".join(char for char in texto if char.isdigit())
        if len(digitos) != 11:
            return None
        return digitos

    @staticmethod
    def _normalizar_punto_venta(punto_venta):
        try:
            valor = int(punto_venta or 0)
        except (TypeError, ValueError):
            return None
        return valor if valor > 0 else None

    @staticmethod
    def _formatear_codigo_factura(punto_venta, numero):
        try:
            pv = int(punto_venta)
        except (TypeError, ValueError):
            pv = 0
        try:
            nro = int(numero)
        except (TypeError, ValueError):
            nro = 0
        return f"{pv:05d}-{nro:08d}"

    @staticmethod
    def _armar_items_factura_desde_resumen(resumen):
        items = []
        for concepto in list(getattr(resumen, "conceptos", []) or []):
            cantidad = float(getattr(concepto, "cantidad", 0) or 0)
            precio_unitario = float(getattr(concepto, "importe", 0) or 0)
            importe = float(getattr(concepto, "total", 0) or 0)
            if abs(importe) <= 0.0 and cantidad > 0:
                importe = cantidad * precio_unitario
            texto_concepto = str(getattr(concepto, "concepto", "") or "").strip()
            texto_descripcion = str(getattr(concepto, "descripcion", "") or "").strip()
            descripcion = texto_concepto
            if texto_descripcion:
                descripcion = f"{texto_concepto} - {texto_descripcion}" if texto_concepto else texto_descripcion

            items.append(
                {
                    "concepto": texto_concepto,
                    "descripcion": descripcion or "(Sin descripción)",
                    "cantidad": cantidad,
                    "precio_unitario": precio_unitario,
                    "importe": float(round(importe, 2)),
                }
            )
        return items

    @classmethod
    def _obtener_periodo_facturado(cls, resumen):
        fechas_inicio = []
        fechas_fin = []
        for concepto in list(getattr(resumen, "conceptos", []) or []):
            inicio = cls._a_fecha_arca_yyyymmdd(getattr(concepto, "fecha_inicio", ""))
            fin = cls._a_fecha_arca_yyyymmdd(getattr(concepto, "fecha_fin", ""))
            if len(inicio) == 8 and inicio.isdigit():
                fechas_inicio.append(inicio)
            if len(fin) == 8 and fin.isdigit():
                fechas_fin.append(fin)

        if not fechas_inicio and not fechas_fin:
            return "", ""

        periodo_desde = min(fechas_inicio) if fechas_inicio else ""
        periodo_hasta = max(fechas_fin) if fechas_fin else ""
        return periodo_desde, periodo_hasta

    @classmethod
    def _resolver_emisor_facturacion_id(cls, emisor_fiscal):
        emisor_fiscal_id = emisor_fiscal[0] if emisor_fiscal and len(emisor_fiscal) > 0 else None
        cuit_fiscal = cls._normalizar_cuit(emisor_fiscal[3] if len(emisor_fiscal) > 3 else "")
        nombre_fiscal = EmisorFiscalService.etiqueta_visible(emisor_fiscal)
        nombre_fiscal_normalizado = cls._normalizar_etiqueta_emisor(nombre_fiscal)

        emisores_internos = EmisorService.listar(False)

        if emisor_fiscal_id:
            emisor_vinculado = EmisorService.obtener_por_emisor_fiscal_id(emisor_fiscal_id)
            if emisor_vinculado:
                return emisor_vinculado[0], "emisor_fiscal_id"

        if emisor_fiscal_id and EmisorService.obtener(emisor_fiscal_id):
            return emisor_fiscal_id, "id_directo_legacy"

        if cuit_fiscal:
            for emisor in emisores_internos:
                cuit_interno = cls._normalizar_cuit(emisor[4] if len(emisor) > 4 else "")
                if cuit_interno and cuit_interno == cuit_fiscal:
                    return emisor[0], "cuit"

        if nombre_fiscal_normalizado:
            for emisor in emisores_internos:
                alias_normalizado = cls._normalizar_etiqueta_emisor(emisor[1] if len(emisor) > 1 else "")
                if alias_normalizado and alias_normalizado == nombre_fiscal_normalizado:
                    return emisor[0], "alias"

        if nombre_fiscal_normalizado:
            for emisor in emisores_internos:
                nombre_normalizado = cls._normalizar_etiqueta_emisor(emisor[3] if len(emisor) > 3 else "")
                titular_normalizado = cls._normalizar_etiqueta_emisor(emisor[2] if len(emisor) > 2 else "")
                if nombre_normalizado == nombre_fiscal_normalizado or titular_normalizado == nombre_fiscal_normalizado:
                    return emisor[0], "nombre_exacto_normalizado"

        return None, "sin_vinculo"

    @classmethod
    def emitir_desde_resumen(cls, resumen_id, contexto=None):
        resultado = {
            "ok": False,
            "etapa": "inicio",
            "factura_id": None,
            "resumen_id": resumen_id,
            "numero_factura": "",
            "cae": "",
            "vencimiento_cae": "",
            "ruta_pdf": "",
            "errores": [],
            "observaciones": "",
            "detalle_arca": None,
            "tipo_mensaje": "error",
            "mensaje": "",
            "datos_modal": {},
            "ruta_pdf_resumen_recomendada": "",
        }

        if resumen_id is None:
            resultado["etapa"] = "resumen_no_encontrado"
            resultado["mensaje"] = "No se encontró el resumen recién generado."
            return resultado

        resumen = ResumenService.obtener(resumen_id)
        if not resumen:
            resultado["etapa"] = "resumen_no_encontrado"
            resultado["mensaje"] = "No se encontró el resumen recién generado."
            return resultado

        intentos_activos = IntentoEmisionArcaService().listar_activos_por_resumen(resumen.id)
        if intentos_activos:
            intento = intentos_activos[0]
            resultado["etapa"] = "resumen_bloqueado"
            resultado["tipo_mensaje"] = "warning"
            resultado["errores"] = ["El resumen tiene una emisión pendiente de verificar con ARCA."]
            resultado["datos_modal"] = {
                "intento_id": intento.id,
                "estado_intento": intento.estado,
            }
            resultado["mensaje"] = (
                "Hay una emisión pendiente de verificar con ARCA.\n\n"
                f"Intento: {intento.id}\n"
                f"Estado: {intento.estado}\n\n"
                "Debe reconciliarla antes de intentar emitir nuevamente."
            )
            return resultado

        facturas_existentes = FacturaArcaService.listar_por_resumen(resumen.id)
        if facturas_existentes:
            factura_existente = facturas_existentes[0]
            numero_factura = str(factura_existente[9] if len(factura_existente) > 9 else "" or "-").strip()
            cae = str(factura_existente[10] if len(factura_existente) > 10 else "" or "-").strip()
            resultado["etapa"] = "resumen_ya_con_factura"
            resultado["tipo_mensaje"] = "warning"
            resultado["numero_factura"] = numero_factura
            resultado["cae"] = cae
            resultado["mensaje"] = (
                "El resumen ya tiene una factura asociada. No se realizará una nueva emisión.\n\n"
                f"Comprobante: {numero_factura}\n"
                f"CAE: {cae}"
            )
            return resultado

        if str(resumen.estado_facturacion or "").strip().lower() == "facturado":
            numero_factura = str(getattr(resumen, "numero_factura", "") or "-").strip()
            cae = str(getattr(resumen, "cae", "") or "-").strip()
            resultado["etapa"] = "resumen_ya_facturado"
            resultado["tipo_mensaje"] = "warning"
            resultado["numero_factura"] = numero_factura
            resultado["cae"] = cae
            resultado["mensaje"] = (
                "El resumen ya figura como facturado. No se realizará una nueva emisión.\n\n"
                f"Comprobante: {numero_factura}\n"
                f"CAE: {cae}"
            )
            return resultado

        validacion_resumen = cls.validar_resumen_para_facturar(resumen.id)
        if not validacion_resumen.get("ok"):
            errores_validacion = validacion_resumen.get("errores") or ["El resumen no cumple las validaciones previas para facturar."]
            resultado["etapa"] = "validacion_resumen"
            resultado["errores"] = list(errores_validacion)
            resultado["mensaje"] = (
                "No se puede facturar porque el resumen no cumple las validaciones previas:\n- "
                + "\n- ".join(str(error) for error in errores_validacion)
            )
            return resultado

        resolucion_cliente = cls.resolver_cliente(resumen.id)
        if not resolucion_cliente.get("ok"):
            errores_cliente = resolucion_cliente.get("errores") or ["cliente_no_encontrado"]
            resultado["etapa"] = "cliente"
            resultado["errores"] = list(errores_cliente)
            resultado["mensaje"] = (
                "No se encontraron los datos del cliente para facturar:\n- "
                + "\n- ".join(str(error) for error in errores_cliente)
            )
            return resultado
        cliente = resolucion_cliente.get("cliente")

        datos_contexto = contexto if isinstance(contexto, dict) else {}
        modalidad = str(datos_contexto.get("modalidad_comprobante") or "Solo Resumen").strip()
        emisor_habitual = str(datos_contexto.get("emisor_habitual") or "").strip()
        tipo_factura = str(datos_contexto.get("tipo_factura") or "").strip()
        condicion_iva = str(datos_contexto.get("condicion_iva") or "").strip()

        faltantes = []
        if not tipo_factura:
            faltantes.append("Tipo de factura")
        if not condicion_iva:
            faltantes.append("Condición de IVA")

        resolucion_conceptos = cls.resolver_conceptos(resumen.id)
        if not resolucion_conceptos.get("ok"):
            errores_conceptos = resolucion_conceptos.get("errores") or ["resumen_sin_conceptos"]
            resultado["etapa"] = "conceptos"
            resultado["errores"] = list(errores_conceptos)
            resultado["mensaje"] = (
                "No se puede facturar porque faltan datos obligatorios:\n- "
                + "\n- ".join(str(error) for error in errores_conceptos)
            )
            return resultado
        resumen_actual = resolucion_conceptos.get("resumen")
        conceptos_resumen = resolucion_conceptos.get("conceptos") or []
        if not conceptos_resumen:
            faltantes.append("Ítems del resumen")

        if faltantes:
            resultado["etapa"] = "faltantes"
            resultado["errores"] = list(faltantes)
            resultado["mensaje"] = "No se puede facturar porque faltan datos obligatorios:\n- " + "\n- ".join(faltantes)
            return resultado

        tipo_factura_normalizado = str(tipo_factura or "").strip()
        if tipo_factura_normalizado not in {"Factura C", "Factura A"}:
            resultado["etapa"] = "tipo_factura"
            resultado["mensaje"] = "El tipo de factura configurado no es compatible con este flujo automático (solo Factura C / Factura A)."
            return resultado

        resolucion_emisor = cls.resolver_emisor(resumen.id)
        if not resolucion_emisor.get("ok"):
            errores_emisor = resolucion_emisor.get("errores") or ["emisor_fiscal_no_encontrado"]
            resultado["etapa"] = "emisor"
            resultado["errores"] = list(errores_emisor)
            resultado["mensaje"] = (
                "No se encontró el emisor configurado para iniciar la emisión:\n- "
                + "\n- ".join(str(error) for error in errores_emisor)
            )
            return resultado
        emisor_fiscal = resolucion_emisor.get("emisor_fiscal")

        emisor_facturacion_id, campo_vinculo = cls._resolver_emisor_facturacion_id(emisor_fiscal)
        if emisor_facturacion_id is None:
            resultado["etapa"] = "vinculo_emisor"
            resultado["observaciones"] = f"campo_usado_vinculo={campo_vinculo}"
            resultado["mensaje"] = "No se pudo vincular el emisor interno de facturación para registrar la factura."
            return resultado

        cuit_emisor = str(emisor_fiscal[3] if len(emisor_fiscal) > 3 else "" or "").strip()
        punto_venta = emisor_fiscal[6] if len(emisor_fiscal) > 6 else ""
        ambiente_emisor = emisor_fiscal[9] if len(emisor_fiscal) > 9 else ""
        ruta_certificado = str(emisor_fiscal[13] if len(emisor_fiscal) > 13 else "" or "").strip()
        ruta_clave = str(emisor_fiscal[14] if len(emisor_fiscal) > 14 else "" or "").strip()
        carpeta_facturas = str(emisor_fiscal[15] if len(emisor_fiscal) > 15 else "" or "").strip()

        try:
            ambiente_normalizado = ambiente_arca.normalizar_ambiente_arca(ambiente_emisor)
        except ambiente_arca.AmbienteArcaInvalidoError as error:
            resultado["etapa"] = "ambiente_arca"
            resultado["errores"] = [str(error)]
            resultado["mensaje"] = str(error)
            return resultado

        cuit_emisor_normalizado = cls._normalizar_cuit(cuit_emisor)
        punto_venta_normalizado = cls._normalizar_punto_venta(punto_venta)
        if not cuit_emisor_normalizado:
            resultado["etapa"] = "cuit_emisor"
            resultado["mensaje"] = "El CUIT del emisor habitual es inválido."
            return resultado
        if punto_venta_normalizado is None:
            resultado["etapa"] = "punto_venta"
            resultado["mensaje"] = "El punto de venta del emisor habitual es inválido."
            return resultado

        condicion_iva_emisor = str(emisor_fiscal[4] if len(emisor_fiscal) > 4 else "" or "").strip().lower()
        if tipo_factura_normalizado == "Factura A" and "responsable" not in condicion_iva_emisor:
            resultado["etapa"] = "condicion_emisor"
            resultado["mensaje"] = "No se puede emitir Factura A: el emisor no está configurado como Responsable Inscripto."
            return resultado

        if not resumen_actual:
            resultado["etapa"] = "resumen_recarga"
            resultado["mensaje"] = "No se pudo recargar el resumen recién guardado para emitir."
            return resultado

        items_factura = cls._armar_items_factura_desde_resumen(resumen_actual)
        if not items_factura:
            resultado["etapa"] = "items"
            resultado["mensaje"] = "El resumen no tiene ítems válidos para facturación."
            return resultado

        suma_items = cls._sumar_importes_items(items_factura)
        total_resumen = float(getattr(resumen_actual, "total", 0) or 0)
        diferencia = round(suma_items - total_resumen, 2)
        if abs(diferencia) > 0.01:
            resultado["etapa"] = "diferencia_totales"
            resultado["errores"] = ["diferencia_totales"]
            resultado["datos_modal"] = {
                "suma_items": float(suma_items),
                "total_resumen": float(total_resumen),
                "diferencia": float(diferencia),
                "items_factura": list(items_factura or []),
            }
            return resultado

        total_factura = float(round(suma_items, 2))
        if total_factura <= 0:
            resultado["etapa"] = "total_factura"
            resultado["mensaje"] = "El total del resumen es inválido para facturación."
            return resultado

        documento_cliente = str(cliente[10] if len(cliente) > 10 else "" or "").strip()
        documento_normalizado = "".join(char for char in documento_cliente if char.isdigit())
        condicion_iva_normalizada = condicion_iva.lower()
        if not documento_normalizado and condicion_iva_normalizada != "consumidor final":
            resultado["etapa"] = "documento_cliente"
            resultado["mensaje"] = "No se puede facturar porque falta CUIT o documento del cliente."
            return resultado

        if tipo_factura_normalizado == "Factura A":
            if "responsable" not in condicion_iva_normalizada:
                resultado["etapa"] = "condicion_cliente"
                resultado["mensaje"] = "No se puede emitir Factura A: el cliente debe ser Responsable Inscripto."
                return resultado
            if len(documento_normalizado) != 11:
                resultado["etapa"] = "cuit_cliente"
                resultado["mensaje"] = "No se puede emitir Factura A: el cliente debe tener CUIT válido de 11 dígitos."
                return resultado
            tipo_documento = 80
            documento_receptor = int(documento_normalizado)
        elif documento_normalizado and len(documento_normalizado) == 11:
            if condicion_iva_normalizada == "consumidor final":
                tipo_documento = 96
                documento_receptor = int(documento_normalizado[2:-1])
            else:
                tipo_documento = 80
                documento_receptor = int(documento_normalizado)
        else:
            tipo_documento = 99
            documento_receptor = 0

        fiscal = cls.calcular_importes_fiscales(resumen.id, tipo_factura=tipo_factura_normalizado)
        if not fiscal.get("ok"):
            errores_fiscales = list(fiscal.get("errores") or ["Cálculo fiscal inválido."])
            resultado["etapa"] = "calculo_fiscal"
            resultado["errores"] = errores_fiscales
            return resultado

        tipo_comprobante = int(fiscal.get("tipo_comprobante") or 0)
        neto_factura = float(fiscal.get("neto_factura") or 0.0)
        alicuota_iva = float(fiscal.get("alicuota_iva") or 0.0)
        importe_iva_factura = float(fiscal.get("importe_iva_factura") or 0.0)
        total_factura_fiscal = float(fiscal.get("total_factura_fiscal") or 0.0)
        importe_exento_factura = float(fiscal.get("importe_exento_factura") or 0.0)
        importe_tot_conc = float(fiscal.get("importe_tot_conc") or 0.0)
        importe_tributos = float(fiscal.get("importe_tributos") or 0.0)
        alicuotas_iva = list(fiscal.get("alicuotas_iva") or [])
        condicion_iva_receptor_id = int(fiscal.get("condicion_iva_receptor_id") or 0)

        pre_guardado = FacturaArcaService.validar_pre_guardado(
            cliente_id=cliente[0],
            emisor_id=emisor_facturacion_id,
            resumen_id=resumen.id,
            fecha=date.today().isoformat(),
            punto_venta=str(punto_venta_normalizado),
            tipo_comprobante=tipo_factura_normalizado,
            importe_total=total_factura_fiscal,
            estado="Facturada manualmente",
        )
        if not pre_guardado.get("ok"):
            resultado["etapa"] = "pre_guardado"
            resultado["errores"] = list(pre_guardado.get("errores") or ["Validación local fallida."])
            return resultado

        fecha_comprobante_arca = datetime.now().strftime("%Y%m%d")
        periodo_desde, periodo_hasta = cls._obtener_periodo_facturado(resumen_actual)
        vencimiento_pago_arca = cls._a_fecha_arca_yyyymmdd(getattr(resumen_actual, "fecha_vencimiento", ""))

        contexto_base_resultado = cls._construir_contexto_fiscal_base(
            ambiente_normalizado=ambiente_normalizado,
            emisor_fiscal=emisor_fiscal,
            emisor_facturacion_id=emisor_facturacion_id,
            cuit_emisor_normalizado=cuit_emisor_normalizado,
            punto_venta_num=punto_venta_normalizado,
            cliente=cliente,
            condicion_iva=condicion_iva,
            documento_normalizado=documento_normalizado,
            tipo_documento=tipo_documento,
            documento_receptor=documento_receptor,
            tipo_comprobante=tipo_comprobante,
            tipo_factura_normalizado=tipo_factura_normalizado,
            fecha_comprobante=fecha_comprobante_arca,
            periodo_desde=periodo_desde,
            periodo_hasta=periodo_hasta,
            vencimiento_pago_arca=vencimiento_pago_arca,
            moneda="PES",
            cotizacion=1,
            neto_factura=neto_factura,
            importe_iva_factura=importe_iva_factura,
            alicuota_iva=alicuota_iva,
            total_factura_fiscal=total_factura_fiscal,
            importe_exento_factura=importe_exento_factura,
            importe_tot_conc=importe_tot_conc,
            importe_tributos=importe_tributos,
            alicuotas_iva=alicuotas_iva,
            items_factura=items_factura,
        )
        if not contexto_base_resultado.get("ok"):
            resultado["etapa"] = "contexto_fiscal_base"
            resultado["errores"] = list(
                contexto_base_resultado.get("errores") or ["No se pudo construir el contexto fiscal base."]
            )
            return resultado
        contexto_fiscal_base = contexto_base_resultado["contexto"]

        try:
            resultado_arca = cls.emitir_en_arca(
                ruta_certificado=ruta_certificado,
                ruta_clave=ruta_clave,
                cuit_emisor=cuit_emisor_normalizado,
                punto_venta=punto_venta_normalizado,
                tipo_comprobante=tipo_comprobante,
                condicion_iva_receptor_id=condicion_iva_receptor_id,
                tipo_documento=tipo_documento,
                documento_receptor=documento_receptor,
                importe_total=total_factura_fiscal,
                importe_neto=neto_factura,
                importe_iva=importe_iva_factura,
                importe_exento=importe_exento_factura,
                carpeta_trabajo=carpeta_facturas,
                importe_tot_conc=importe_tot_conc,
                importe_tributos=importe_tributos,
                alicuotas_iva=alicuotas_iva,
                concepto=1,
                datos_intento={
                    "resumen_id": resumen.id,
                    "cliente_id": cliente[0],
                    "emisor_fiscal_id": emisor_fiscal[0],
                    "emisor_id": emisor_facturacion_id,
                },
                contexto_fiscal_base=contexto_fiscal_base,
                fecha_comprobante=fecha_comprobante_arca,
                ambiente=ambiente_normalizado,
            )
            if not resultado_arca.get("ok"):
                detalle_arca = resultado_arca.get("emision") if resultado_arca.get("etapa") != "consulta" else resultado_arca.get("consulta")
                resultado["etapa"] = "arca"
                resultado["detalle_arca"] = detalle_arca or {}
                resultado["errores"] = list(resultado_arca.get("errores") or [])
                return resultado

            consulta = resultado_arca.get("consulta") or {}
            fecha_comprobante = str(resultado_arca.get("fecha_comprobante") or "")
            numero_comprobante = int(resultado_arca.get("numero_comprobante") or 0)
            punto_venta_num = int(resultado_arca.get("punto_venta_num") or punto_venta_normalizado)
            numero_factura = cls._formatear_codigo_factura(punto_venta_num, numero_comprobante)
            cae = str(resultado_arca.get("cae") or "")
            vencimiento_cae = str(resultado_arca.get("vencimiento_cae") or "")

            observaciones_factura = (
                f"Emitida desde Resúmenes ({modalidad}). Emisor habitual: {emisor_habitual}. "
                f"Fiscal: neto={neto_factura:.2f}; iva_alicuota={alicuota_iva:.2f}%; "
                f"iva_importe={importe_iva_factura:.2f}; total={total_factura_fiscal:.2f}"
            )
            intento_id = resultado_arca.get("intento_id")
            if intento_id is None:
                resultado["etapa"] = "cierre_local"
                resultado["errores"] = ["La emisión aprobada no tiene intento ARCA asociado."]
                return resultado

            snapshot_resultado = cls._construir_snapshot_fiscal_cierre_normal(
                emisor_fiscal=emisor_fiscal,
                emisor_facturacion_id=emisor_facturacion_id,
                cuit_emisor_normalizado=cuit_emisor_normalizado,
                punto_venta_num=punto_venta_num,
                cliente=cliente,
                condicion_iva=condicion_iva,
                documento_normalizado=documento_normalizado,
                tipo_documento=tipo_documento,
                documento_receptor=documento_receptor,
                tipo_comprobante=tipo_comprobante,
                tipo_factura_normalizado=tipo_factura_normalizado,
                numero_comprobante=numero_comprobante,
                numero_factura=numero_factura,
                fecha_comprobante=fecha_comprobante,
                periodo_desde=periodo_desde,
                periodo_hasta=periodo_hasta,
                vencimiento_pago_arca=vencimiento_pago_arca,
                moneda=str(consulta.get("moneda") or "PES"),
                cotizacion=consulta.get("cotizacion") or 1,
                neto_factura=neto_factura,
                importe_iva_factura=importe_iva_factura,
                alicuota_iva=alicuota_iva,
                total_factura_fiscal=total_factura_fiscal,
                importe_exento_factura=importe_exento_factura,
                importe_tot_conc=importe_tot_conc,
                importe_tributos=importe_tributos,
                alicuotas_iva=alicuotas_iva,
                items_factura=items_factura,
                cae=cae,
                vencimiento_cae=vencimiento_cae,
                ambiente_normalizado=ambiente_normalizado,
            )
            if not snapshot_resultado.get("ok"):
                resultado["etapa"] = "snapshot_fiscal"
                resultado["tipo_mensaje"] = "warning"
                resultado["errores"] = list(snapshot_resultado.get("errores") or ["No se pudo construir el snapshot fiscal."])
                return resultado

            try:
                cierre_local = CierreLocalArcaService().cerrar_emision_confirmada(
                    intento_id=intento_id,
                    resumen_id=resumen.id,
                    cliente_id=cliente[0],
                    emisor_id=emisor_facturacion_id,
                    fecha=date.today().isoformat(),
                    punto_venta=str(punto_venta_num),
                    tipo_comprobante=tipo_factura_normalizado,
                    importe_total=total_factura_fiscal,
                    numero_factura=numero_factura,
                    cae=cae,
                    vencimiento_cae=vencimiento_cae,
                    observaciones=observaciones_factura,
                    tipo_documento_receptor=tipo_documento,
                    documento_receptor=documento_receptor,
                    snapshot_fiscal_json=snapshot_resultado["snapshot_json"],
                    snapshot_version=snapshot_resultado["snapshot_version"],
                    snapshot_hash=snapshot_resultado["snapshot_hash"],
                )
            except Exception as error:
                resultado["etapa"] = "cierre_local"
                resultado["tipo_mensaje"] = "warning"
                resultado["errores"] = [str(error)]
                resultado["numero_factura"] = numero_factura
                resultado["cae"] = cae
                resultado["vencimiento_cae"] = vencimiento_cae
                resultado["observaciones"] = observaciones_factura
                return resultado

            if not cierre_local.ok:
                resultado["etapa"] = "cierre_local"
                resultado["tipo_mensaje"] = "warning"
                resultado["errores"] = [cierre_local.mensaje or "No se pudo cerrar localmente la emisión."]
                resultado["numero_factura"] = numero_factura
                resultado["cae"] = cae
                resultado["vencimiento_cae"] = vencimiento_cae
                resultado["observaciones"] = observaciones_factura
                return resultado

            factura_id = cierre_local.factura_arca_id

            codigo_factura = cls._formatear_codigo_factura(punto_venta_num, numero_comprobante)

            pdf = cls.generar_pdf_fiscal(
                cliente_id=cliente[0],
                tipo_factura=tipo_factura,
                tipo_factura_comprobante=tipo_factura_normalizado,
                numero_comprobante=numero_comprobante,
                codigo_factura=codigo_factura,
                carpeta_facturas=carpeta_facturas,
                emisor_fiscal=emisor_fiscal,
                cuit_emisor=cuit_emisor_normalizado,
                punto_venta_num=punto_venta_num,
                cliente=cliente,
                condicion_iva=condicion_iva,
                documento_normalizado=documento_normalizado,
                consulta=consulta,
                fecha_comprobante=fecha_comprobante,
                resumen_actual=resumen_actual,
                periodo_desde=periodo_desde,
                periodo_hasta=periodo_hasta,
                neto_factura=neto_factura,
                importe_iva_factura=importe_iva_factura,
                alicuota_iva=alicuota_iva,
                total_factura_fiscal=total_factura_fiscal,
                items_factura=items_factura,
                cae=cae,
                vencimiento_cae=vencimiento_cae,
                snapshot=snapshot_resultado.get("snapshot"),
            )
            if not pdf.get("ok"):
                resultado["etapa"] = "pdf"
                resultado["tipo_mensaje"] = "warning"
                resultado["errores"] = list(pdf.get("errores") or ["No se pudo generar el PDF fiscal."])
                resultado["factura_id"] = factura_id
                resultado["numero_factura"] = numero_factura
                resultado["cae"] = cae
                resultado["vencimiento_cae"] = vencimiento_cae
                resultado["observaciones"] = observaciones_factura
                resultado["datos_modal"] = {
                    "cliente_fila": cliente,
                    "emisor_fiscal": emisor_fiscal,
                    "tipo_factura": tipo_factura_normalizado,
                    "punto_venta_num": punto_venta_num,
                    "numero_comprobante": numero_comprobante,
                    "codigo_factura": codigo_factura,
                    "neto_factura": neto_factura,
                    "importe_iva_factura": importe_iva_factura,
                    "total_factura_fiscal": total_factura_fiscal,
                }
                return resultado

            ruta_pdf = str(pdf.get("ruta_pdf") or "").strip()

            resultado["ok"] = True
            resultado["etapa"] = "ok"
            resultado["factura_id"] = factura_id
            resultado["resumen_id"] = resumen.id
            resultado["numero_factura"] = numero_factura
            resultado["cae"] = cae
            resultado["vencimiento_cae"] = vencimiento_cae
            resultado["ruta_pdf"] = ruta_pdf
            resultado["observaciones"] = observaciones_factura
            resultado["datos_modal"] = {
                "cliente_fila": cliente,
                "emisor_fiscal": emisor_fiscal,
                "tipo_factura": tipo_factura_normalizado,
                "punto_venta_num": punto_venta_num,
                "numero_comprobante": numero_comprobante,
                "codigo_factura": codigo_factura,
                "neto_factura": neto_factura,
                "importe_iva_factura": importe_iva_factura,
                "total_factura_fiscal": total_factura_fiscal,
            }
            return resultado
        except Exception as error:
            resultado["etapa"] = "excepcion"
            resultado["errores"] = [str(error)]
            return resultado

    @classmethod
    def validar_resumen_para_facturar(cls, resumen_id):
        resultado = {
            "ok": False,
            "resumen": None,
            "errores": [],
        }

        resumen = ResumenService.obtener(resumen_id)
        if not resumen:
            resultado["errores"].append("resumen_no_encontrado")
            return resultado

        errores = []
        if not getattr(resumen, "cliente_id", None):
            errores.append("resumen_sin_cliente")
        if not getattr(resumen, "conceptos", None):
            errores.append("resumen_sin_conceptos")
        if float(getattr(resumen, "total", 0) or 0) <= 0:
            errores.append("resumen_sin_importe_valido")

        if errores:
            resultado["errores"].extend(errores)
            resultado["resumen"] = resumen
            return resultado

        resultado["ok"] = True
        resultado["resumen"] = resumen
        return resultado

    @classmethod
    def resolver_cliente(cls, resumen_id):
        resultado = {
            "ok": False,
            "cliente": None,
            "errores": [],
        }

        resumen = ResumenService.obtener(resumen_id)
        if not resumen:
            resultado["errores"].append("resumen_no_encontrado")
            return resultado

        cliente = ClienteService.obtener(resumen.cliente_id)
        if not cliente:
            resultado["errores"].append("cliente_no_encontrado")
            return resultado

        resultado["ok"] = True
        resultado["cliente"] = cliente
        return resultado

    @classmethod
    def resolver_conceptos(cls, resumen_id):
        resultado = {
            "ok": False,
            "resumen": None,
            "conceptos": [],
            "errores": [],
        }

        resumen = ResumenService.obtener(resumen_id)
        if not resumen:
            resultado["errores"].append("resumen_no_encontrado")
            return resultado

        conceptos = list(getattr(resumen, "conceptos", []) or [])
        if not conceptos:
            resultado["errores"].append("resumen_sin_conceptos")
            resultado["resumen"] = resumen
            return resultado

        resultado["ok"] = True
        resultado["resumen"] = resumen
        resultado["conceptos"] = conceptos
        return resultado

    @classmethod
    def calcular_importes_fiscales(cls, resumen_id, tipo_factura=None):
        resultado = {
            "ok": False,
            "errores": [],
            "neto_factura": 0.0,
            "alicuota_iva": 0.0,
            "importe_iva_factura": 0.0,
            "total_factura_fiscal": 0.0,
            "importe_exento_factura": 0.0,
            "importe_tot_conc": 0.0,
            "importe_tributos": 0.0,
            "alicuotas_iva": [],
            "condicion_iva_receptor_id": 0,
            "tipo_comprobante": 0,
            "importe_neto": 0.0,
            "importe_iva": 0.0,
            "importe_total": 0.0,
            "importe_exento": 0.0,
            "resumen": None,
        }

        resumen = ResumenService.obtener(resumen_id)
        if not resumen:
            resultado["errores"].append("resumen_no_encontrado")
            resultado["resumen"] = resumen
            return resultado

        tipo_factura_normalizado = str(tipo_factura if tipo_factura is not None else getattr(resumen, "tipo_factura", "") or "").strip()
        if tipo_factura_normalizado not in {"Factura C", "Factura A"}:
            resultado["errores"].append("Tipo de factura no compatible (solo Factura C / Factura A).")
            resultado["resumen"] = resumen
            return resultado

        conceptos = list(getattr(resumen, "conceptos", []) or [])
        total_factura = cls._sumar_importes_conceptos(conceptos)
        if total_factura <= 0:
            resultado["errores"].append("El total del resumen es inválido para facturación.")
            resultado["resumen"] = resumen
            return resultado

        if tipo_factura_normalizado == "Factura A":
            alicuota_iva = 21.0
            neto_factura = round(total_factura, 2)
            importe_iva_factura = round(neto_factura * (alicuota_iva / 100.0), 2)
            total_factura_fiscal = round(neto_factura + importe_iva_factura, 2)
            alicuotas_iva = [
                {
                    "id": 5,
                    "base_imponible": neto_factura,
                    "importe": importe_iva_factura,
                }
            ]
            condicion_iva_receptor_id = 1
            tipo_comprobante = 1
        else:
            neto_factura = round(total_factura, 2)
            alicuota_iva = 0.0
            importe_iva_factura = 0.0
            total_factura_fiscal = round(total_factura, 2)
            alicuotas_iva = []
            condicion_iva_receptor_id = 5
            tipo_comprobante = 11

        importe_exento_factura = 0.0
        importe_tot_conc = 0.0
        importe_tributos = 0.0

        total_componentes = round(
            neto_factura + importe_iva_factura + importe_exento_factura + importe_tot_conc + importe_tributos,
            2,
        )
        if round(total_factura_fiscal, 2) != total_componentes:
            resultado["errores"].append(
                "Los importes fiscales no cierran (neto + IVA + exento + no gravado + tributos != total)."
            )
            resultado["resumen"] = resumen
            return resultado

        resultado["ok"] = True
        resultado["resumen"] = resumen
        resultado["neto_factura"] = neto_factura
        resultado["alicuota_iva"] = alicuota_iva
        resultado["importe_iva_factura"] = importe_iva_factura
        resultado["total_factura_fiscal"] = total_factura_fiscal
        resultado["importe_exento_factura"] = importe_exento_factura
        resultado["importe_tot_conc"] = importe_tot_conc
        resultado["importe_tributos"] = importe_tributos
        resultado["alicuotas_iva"] = alicuotas_iva
        resultado["condicion_iva_receptor_id"] = condicion_iva_receptor_id
        resultado["tipo_comprobante"] = tipo_comprobante
        resultado["importe_neto"] = neto_factura
        resultado["importe_iva"] = importe_iva_factura
        resultado["importe_total"] = total_factura_fiscal
        resultado["importe_exento"] = importe_exento_factura
        return resultado

    @classmethod
    def resolver_emisor(cls, resumen_id):
        resultado = {
            "ok": False,
            "resumen": None,
            "emisor_fiscal": None,
            "errores": [],
        }

        resumen = ResumenService.obtener(resumen_id)
        if not resumen:
            resultado["errores"].append("resumen_no_encontrado")
            return resultado

        emisor_id = getattr(resumen, "emisor_fiscal_id", None)
        if not emisor_id:
            resultado["errores"].append("resumen_sin_emisor_fiscal")
            return resultado

        emisor_fiscal = EmisorFiscalService.obtener(emisor_id)
        if not emisor_fiscal:
            resultado["errores"].append("emisor_fiscal_no_encontrado")
            return resultado

        resultado["ok"] = True
        resultado["resumen"] = resumen
        resultado["emisor_fiscal"] = emisor_fiscal
        return resultado

    @classmethod
    def emitir_en_arca(
        cls,
        ruta_certificado,
        ruta_clave,
        cuit_emisor,
        punto_venta,
        tipo_comprobante,
        condicion_iva_receptor_id,
        tipo_documento,
        documento_receptor,
        importe_total,
        importe_neto,
        importe_iva,
        importe_exento,
        carpeta_trabajo,
        importe_tot_conc,
        importe_tributos,
        alicuotas_iva,
        concepto=1,
        datos_intento=None,
        contexto_fiscal_base=None,
        fecha_comprobante=None,
        ambiente=ambiente_arca.AMBIENTE_HOMOLOGACION,
    ):
        resultado = {
            "ok": False,
            "errores": [],
            "etapa": "emision",
            "fecha_comprobante": "",
            "emision": None,
            "consulta": None,
            "numero_emitido": 0,
            "numero_comprobante": 0,
            "punto_venta_num": 0,
            "intento_id": None,
            "cae": "",
            "vencimiento_cae": "",
            "ambiente": "",
        }

        try:
            ambiente_normalizado = ambiente_arca.normalizar_ambiente_arca(ambiente)
        except ambiente_arca.AmbienteArcaInvalidoError as error:
            resultado["errores"] = [str(error)]
            return resultado
        resultado["ambiente"] = ambiente_normalizado

        fecha_comprobante = str(fecha_comprobante or "").strip() or datetime.now().strftime("%Y%m%d")
        resultado["fecha_comprobante"] = fecha_comprobante

        if contexto_fiscal_base is None:
            resultado["errores"] = ["Contexto fiscal base obligatorio antes de emitir en ARCA."]
            return resultado

        emision = HomologacionService.emitir_comprobante_prueba(
            ruta_certificado=ruta_certificado,
            ruta_clave=ruta_clave,
            cuit_emisor=cuit_emisor,
            punto_venta=punto_venta,
            tipo_comprobante=tipo_comprobante,
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
            importe_tot_conc=importe_tot_conc,
            importe_tributos=importe_tributos,
            alicuotas_iva=alicuotas_iva,
            datos_intento=datos_intento,
            contexto_fiscal_base=contexto_fiscal_base,
            exigir_contexto_fiscal=True,
            ambiente=ambiente_normalizado,
        )
        resultado["emision"] = emision
        resultado["intento_id"] = emision.get("intento_id")
        if not emision.get("ok"):
            resultado["errores"] = list(emision.get("errores") or [])
            return resultado

        numero_emitido = int(emision.get("numero_comprobante") or 0)
        resultado["numero_emitido"] = numero_emitido

        consulta = HomologacionService.consultar_comprobante_emitido(
            ruta_certificado=ruta_certificado,
            ruta_clave=ruta_clave,
            cuit_emisor=cuit_emisor,
            punto_venta=punto_venta,
            tipo_comprobante=tipo_comprobante,
            numero_comprobante=numero_emitido,
            carpeta_trabajo=carpeta_trabajo,
            token=emision.get("token"),
            sign=emision.get("sign"),
            ambiente=ambiente_normalizado,
        )
        resultado["consulta"] = consulta
        if not consulta.get("ok"):
            resultado["etapa"] = "consulta"
            resultado["errores"] = list(consulta.get("errores") or [])
            return resultado

        numero_comprobante = int(consulta.get("numero_comprobante") or numero_emitido)
        punto_venta_num = int(consulta.get("punto_venta") or punto_venta)
        cae = str(consulta.get("cae") or emision.get("cae") or "")
        vencimiento_cae = str(consulta.get("vencimiento_cae") or emision.get("vencimiento_cae") or "")

        resultado["ok"] = True
        resultado["etapa"] = "ok"
        resultado["numero_comprobante"] = numero_comprobante
        resultado["punto_venta_num"] = punto_venta_num
        resultado["cae"] = cae
        resultado["vencimiento_cae"] = vencimiento_cae
        return resultado

    @classmethod
    def registrar_emision_aprobada(
        cls,
        cliente_id,
        emisor_id,
        resumen_id,
        fecha,
        punto_venta,
        tipo_comprobante,
        importe_total,
        numero_factura,
        cae,
        vencimiento_cae,
        observaciones,
    ):
        resultado = {
            "ok": False,
            "factura_id": None,
            "resumen_id": resumen_id,
            "numero_factura": str(numero_factura or ""),
            "cae": str(cae or ""),
            "vencimiento_cae": str(vencimiento_cae or ""),
            "errores": [],
        }

        try:
            factura_id = FacturaArcaService.guardar(
                FacturaArca(
                    cliente_id=cliente_id,
                    emisor_id=emisor_id,
                    resumen_id=resumen_id,
                    fecha=fecha,
                    punto_venta=str(punto_venta),
                    tipo_comprobante=tipo_comprobante,
                    importe_total=importe_total,
                    estado="Facturada manualmente",
                    numero_factura=str(numero_factura or ""),
                    cae=str(cae or ""),
                    vencimiento_cae=str(vencimiento_cae or ""),
                    observaciones=str(observaciones or ""),
                    fecha_creacion=datetime.now().isoformat(timespec="seconds"),
                )
            )

            ResumenService.marcar_facturado(
                resumen_id,
                numero_factura=str(numero_factura or ""),
                cae=str(cae or ""),
                vencimiento_cae=str(vencimiento_cae or ""),
            )
        except Exception as error:
            resultado["errores"].append(str(error))
            return resultado

        resultado["ok"] = True
        resultado["factura_id"] = factura_id
        return resultado

    @classmethod
    def generar_pdf_fiscal(
        cls,
        cliente_id,
        tipo_factura,
        tipo_factura_comprobante,
        numero_comprobante,
        codigo_factura,
        carpeta_facturas,
        emisor_fiscal,
        cuit_emisor,
        punto_venta_num,
        cliente,
        condicion_iva,
        documento_normalizado,
        consulta,
        fecha_comprobante,
        resumen_actual,
        periodo_desde,
        periodo_hasta,
        neto_factura,
        importe_iva_factura,
        alicuota_iva,
        total_factura_fiscal,
        items_factura,
        cae,
        vencimiento_cae,
        snapshot=None,
    ):
        resultado = {
            "ok": False,
            "ruta_pdf": "",
            "errores": [],
        }

        try:
            ruta_sugerida_pdf = str(
                Path(str(carpeta_facturas or "").strip())
                / nombre_factura_pdf(int(cliente_id), str(tipo_factura or ""), str(codigo_factura or ""))
            )

            if snapshot:
                # FASE 5E: el PDF inicial usa el mismo snapshot recien construido/persistido,
                # sin reconsultar cliente/emisor/resumen (misma fuente que la regeneracion 5D).
                datos_pdf = construir_datos_pdf_desde_snapshot(snapshot)
                datos_pdf["datos_emisor"]["carpeta_facturas"] = str(carpeta_facturas or "")
                datos_emisor = datos_pdf["datos_emisor"]
                datos_receptor = datos_pdf["datos_receptor"]
                datos_comprobante = datos_pdf["datos_comprobante"]
            else:
                # MODO LEGACY: sin snapshot disponible, se reconstruye desde el contexto de emision.
                datos_emisor = {
                    "razon_social": str(emisor_fiscal[1] if len(emisor_fiscal) > 1 else "" or ""),
                    "nombre_fantasia": str(emisor_fiscal[2] if len(emisor_fiscal) > 2 else "" or ""),
                    "cuit": str(cuit_emisor or ""),
                    "condicion_iva": str(emisor_fiscal[4] if len(emisor_fiscal) > 4 else "" or ""),
                    "domicilio": str(emisor_fiscal[10] if len(emisor_fiscal) > 10 else "" or ""),
                    "ingresos_brutos": str(emisor_fiscal[11] if len(emisor_fiscal) > 11 else "" or ""),
                    "fecha_inicio_actividades": str(emisor_fiscal[12] if len(emisor_fiscal) > 12 else "" or ""),
                    "punto_venta": punto_venta_num,
                    "carpeta_facturas": str(carpeta_facturas or ""),
                }

                cuit_o_doc = str(documento_normalizado or "").strip() or "0"
                datos_receptor = {
                    "razon_social": str(cliente[2] if len(cliente) > 2 else "" or ""),
                    "cuit": cuit_o_doc,
                    "documento": cuit_o_doc,
                    "condicion_iva": str(condicion_iva or ""),
                    "domicilio": cls._combinar_domicilio_cliente(cliente),
                }

                datos_comprobante = {
                    "tipo": str(tipo_factura_comprobante or ""),
                    "numero": numero_comprobante,
                    "fecha": str((consulta or {}).get("fecha_comprobante") or fecha_comprobante or ""),
                    "concepto": "1 - Productos",
                    "periodo_servicio_desde": str(periodo_desde or ""),
                    "periodo_servicio_hasta": str(periodo_hasta or ""),
                    "vencimiento_pago": cls._a_fecha_arca_yyyymmdd(getattr(resumen_actual, "fecha_vencimiento", "")),
                    "importe_neto": neto_factura,
                    "importe_iva": importe_iva_factura,
                    "alicuota_iva": alicuota_iva,
                    "importe_total": total_factura_fiscal,
                    "items": list(items_factura or []),
                    "moneda": str((consulta or {}).get("moneda") or "PES"),
                    "cae": str(cae or ""),
                    "vencimiento_cae": str(vencimiento_cae or ""),
                    "ambiente": str(emisor_fiscal[9] if len(emisor_fiscal) > 9 else "Homologación"),
                    "punto_venta": punto_venta_num,
                }

            pdf = PDFFiscalService.generar_factura_c(
                ruta_destino=ruta_sugerida_pdf,
                datos_emisor=datos_emisor,
                datos_receptor=datos_receptor,
                datos_comprobante=datos_comprobante,
            )

            if not pdf.get("ok"):
                resultado["errores"] = list(pdf.get("errores") or ["No se pudo generar el PDF fiscal."])
                return resultado

            resultado["ok"] = True
            resultado["ruta_pdf"] = str(pdf.get("ruta_pdf") or "").strip()
            return resultado
        except Exception as error:
            resultado["errores"].append(str(error))
            return resultado
