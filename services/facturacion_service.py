from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from models.factura_arca import FacturaArca
from pdf.nombre_archivos import nombre_factura_pdf
from services.arca.homologacion_service import HomologacionService
from services.arca.pdf_fiscal_service import PDFFiscalService
from services.cliente_service import ClienteService
from services.emisor_fiscal_service import EmisorFiscalService
from services.factura_arca_service import FacturaArcaService
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
            "cae": "",
            "vencimiento_cae": "",
        }

        fecha_comprobante = datetime.now().strftime("%Y%m%d")
        resultado["fecha_comprobante"] = fecha_comprobante

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
        )
        resultado["emision"] = emision
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
