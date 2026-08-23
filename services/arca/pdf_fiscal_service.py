from datetime import datetime
from pathlib import Path

from reportlab.lib.colors import HexColor, black, white
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas
from reportlab.graphics import renderPDF
from reportlab.graphics.barcode.qr import QrCodeWidget
from reportlab.graphics.shapes import Drawing

from pdf.identidad_emisor import (
    normalizar_cuit as identidad_normalizar_cuit,
    normalizar_nombre_emisor as identidad_normalizar_nombre_emisor,
    resolver_logo_emisor as identidad_resolver_logo_emisor,
    resolver_tipo_identidad_emisor as identidad_resolver_tipo_identidad_emisor,
    obtener_dimensiones_logo_emisor as identidad_obtener_dimensiones_logo_emisor,
    obtener_configuracion_logo_fiscal as identidad_obtener_configuracion_logo_fiscal,
)
from services.arca import ambiente_arca
from services.arca.qr_fiscal_service import QrFiscalService

try:
    from runtime_paths import ASSETS_DIR as _ASSETS_DIR
except Exception:
    _ASSETS_DIR = Path(__file__).resolve().parent.parent.parent / "assets"


class PDFFiscalService:
    COLOR_PRIMARIO = HexColor("#B00020")
    COLOR_TEXTO = HexColor("#1A1A1A")
    COLOR_BORDE = HexColor("#C8C8C8")
    COLOR_SUAVE = HexColor("#F8F8F8")
    COLOR_AGUA = HexColor("#E35D6A")

    LOGO_PATH = _ASSETS_DIR / "logos" / "logo_fm_master.png"
    LOGO_MAX_WIDTH = 120
    LOGO_MAX_HEIGHT = 44

    @staticmethod
    def generar_factura_c(ruta_destino, datos_emisor, datos_receptor, datos_comprobante):
        resultado = {
            "ok": False,
            "ruta_pdf": "",
            "errores": [],
        }

        if not str(ruta_destino or "").strip():
            resultado["errores"].append("Ruta de destino no informada.")
            return resultado

        if not isinstance(datos_emisor, dict):
            resultado["errores"].append("datos_emisor invalido.")
            return resultado

        if not isinstance(datos_receptor, dict):
            resultado["errores"].append("datos_receptor invalido.")
            return resultado

        if not isinstance(datos_comprobante, dict):
            resultado["errores"].append("datos_comprobante invalido.")
            return resultado

        try:
            destino_final = PDFFiscalService._resolver_ruta_destino(ruta_destino)
            destino_final.parent.mkdir(parents=True, exist_ok=True)

            tipo_comprobante = str(PDFFiscalService._pick(datos_comprobante, "tipo", default="Factura C") or "Factura C")

            pdf = canvas.Canvas(str(destino_final), pagesize=A4, pageCompression=1)
            pdf.setTitle(tipo_comprobante)
            pdf.setAuthor(str(PDFFiscalService._pick(datos_emisor, "razon_social", "nombre_fantasia", default="Emisor")))
            pdf.setSubject(f"{tipo_comprobante} - Homologacion")

            PDFFiscalService._dibujar_estructura(pdf, datos_emisor, datos_receptor, datos_comprobante)

            pdf.save()
            resultado["ok"] = True
            resultado["ruta_pdf"] = str(destino_final)
            return resultado
        except Exception as error:
            resultado["errores"].append(f"No se pudo generar el PDF fiscal: {error}")
            return resultado

    @staticmethod
    def _dibujar_estructura(pdf, datos_emisor, datos_receptor, datos_comprobante):
        ancho, alto = A4  # A4: 595.27 x 841.89

        tipo = str(PDFFiscalService._pick(datos_comprobante, "tipo", default="Factura C") or "Factura C")
        numero = PDFFiscalService._pick(datos_comprobante, "numero", "numero_comprobante", default="")
        punto_venta = PDFFiscalService._pick(
            datos_comprobante,
            "punto_venta",
            default=PDFFiscalService._pick(datos_emisor, "punto_venta", default=""),
        )
        codigo = PDFFiscalService._formatear_codigo(punto_venta, numero)

        fecha = str(PDFFiscalService._pick(datos_comprobante, "fecha", "fecha_comprobante", default=""))
        concepto = str(PDFFiscalService._pick(datos_comprobante, "concepto", default=""))
        f_serv_desde = str(PDFFiscalService._pick(datos_comprobante, "periodo_servicio_desde", "fecha_servicio_desde", default=""))
        f_serv_hasta = str(PDFFiscalService._pick(datos_comprobante, "periodo_servicio_hasta", "fecha_servicio_hasta", default=""))
        f_vto_pago = str(PDFFiscalService._pick(datos_comprobante, "vencimiento_pago", "fecha_vencimiento_pago", default=""))
        moneda = str(PDFFiscalService._pick(datos_comprobante, "moneda", default="PES"))
        importe_total = PDFFiscalService._to_float(
            PDFFiscalService._pick(datos_comprobante, "importe_total", default=0.0)
        )
        items = PDFFiscalService._normalizar_items(
            PDFFiscalService._pick(datos_comprobante, "items", default=[])
        )
        cae = str(PDFFiscalService._pick(datos_comprobante, "cae", default=""))
        vto_cae = str(PDFFiscalService._pick(datos_comprobante, "vencimiento_cae", "cae_vencimiento", default=""))
        ambiente = str(PDFFiscalService._pick(datos_comprobante, "ambiente", default="HOMOLOGACION"))
        # Ante ambiente vacio/desconocido, nunca se asume Produccion (se conserva la marca de agua).
        try:
            ambiente_es_produccion = ambiente_arca.normalizar_ambiente_arca(ambiente) == ambiente_arca.AMBIENTE_PRODUCCION
        except ambiente_arca.AmbienteArcaInvalidoError:
            ambiente_es_produccion = False

        # Extraer datos del emisor
        emisor_nombre_fantasia = str(PDFFiscalService._pick(datos_emisor, "nombre_fantasia", default=""))
        emisor_razon_social = str(PDFFiscalService._pick(datos_emisor, "razon_social", default=""))
        emisor_cuit = str(PDFFiscalService._pick(datos_emisor, "cuit", default=""))
        emisor_iva = str(PDFFiscalService._pick(datos_emisor, "condicion_iva", default=""))
        emisor_ingresos_brutos = str(PDFFiscalService._pick(datos_emisor, "ingresos_brutos", default="")).strip() or "-"
        fecha_inicio_actividades_raw = str(
            PDFFiscalService._pick(datos_emisor, "fecha_inicio_actividades", default="")
        ).strip()
        emisor_fecha_inicio_actividades = PDFFiscalService._fmt_fecha(fecha_inicio_actividades_raw) if fecha_inicio_actividades_raw else "-"
        emisor_domicilio = str(PDFFiscalService._pick(datos_emisor, "domicilio", default=""))
        emisor_punto_venta = str(PDFFiscalService._pick(datos_emisor, "punto_venta", default=punto_venta))
        logo_path = PDFFiscalService._resolver_logo_emisor(datos_emisor)
        tipo_identidad_emisor = PDFFiscalService._resolver_tipo_identidad_emisor(datos_emisor)

        # ══════════════════ ENCABEZADO PROFESIONAL ══════════════════
        y = alto - 30

        # Logo (esquina superior izquierda)
        PDFFiscalService._dibujar_logo(
            pdf,
            x=30,
            y_banda_inferior=y - 80,
            altura_banda=80,
            logo_path=logo_path,
            datos_emisor=datos_emisor,
        )

        # Información del emisor (columna central-izquierda)
        pdf.setFillColor(PDFFiscalService.COLOR_TEXTO)
        titulo_emisor_tamano = 14 if tipo_identidad_emisor == "publicidad_servicios_sh" else 16
        x_emisor_texto = 164.0 if tipo_identidad_emisor == "publicidad_servicios_sh" else 170.0
        pdf.setFont("Helvetica-Bold", titulo_emisor_tamano)
        pdf.drawString(x_emisor_texto, y - 5, emisor_nombre_fantasia)

        razon_social_tamano = 10
        if tipo_identidad_emisor == "publicidad_servicios_sh":
            x_caja_objetivo = 350.27559055118115
            margen_visual = 4.0
            ancho_disponible = x_caja_objetivo - x_emisor_texto - margen_visual
            for tam in (10, 9, 8, 7):
                if stringWidth(emisor_razon_social, "Helvetica", tam) <= ancho_disponible:
                    razon_social_tamano = tam
                    break
            else:
                razon_social_tamano = 7

        pdf.setFont("Helvetica", razon_social_tamano)
        pdf.drawString(x_emisor_texto, y - 20, emisor_razon_social)

        pdf.setFont("Helvetica", 9)
        pdf.drawString(x_emisor_texto, y - 32, f"CUIT: {emisor_cuit}  |  Pto. Venta: {emisor_punto_venta}")
        pdf.drawString(x_emisor_texto, y - 42, f"IVA: {emisor_iva}")
        pdf.drawString(x_emisor_texto, y - 52, f"Ingresos Brutos: {emisor_ingresos_brutos}")
        pdf.drawString(x_emisor_texto, y - 62, f"Inicio de Actividades: {emisor_fecha_inicio_actividades}")
        pdf.drawString(x_emisor_texto, y - 72, f"Domicilio: {emisor_domicilio}")

        # Bloque con datos del comprobante (sin fondo rojo, sobre blanco)
        # Alineado al margen derecho del contenido para separar mejor del emisor.
        ancho_bloque_comp = 225
        x_bloque_comp = (ancho - 30) - ancho_bloque_comp
        if tipo_identidad_emisor in {"publicidad_servicios", "publicidad_servicios_sh"}:
            ancho_bloque_comp = 210
            x_bloque_comp = 350.27559055118115
        centro_bloque_comp = x_bloque_comp + (ancho_bloque_comp / 2)
        pdf.setFillColor(white)
        pdf.setStrokeColor(PDFFiscalService.COLOR_BORDE)
        pdf.setLineWidth(0.5)
        pdf.rect(x_bloque_comp, y - 75, ancho_bloque_comp, 75, fill=1, stroke=1)

        pdf.setFillColor(PDFFiscalService.COLOR_TEXTO)
        pdf.setFont("Helvetica-Bold", 13)
        pdf.drawCentredString(centro_bloque_comp, y - 18, tipo.upper())

        pdf.setFont("Helvetica", 11)
        pdf.drawCentredString(centro_bloque_comp, y - 35, f"N° {codigo}")

        pdf.setFont("Helvetica", 8)
        pdf.drawCentredString(centro_bloque_comp, y - 60, ambiente)

        # Línea separadora
        pdf.setStrokeColor(PDFFiscalService.COLOR_BORDE)
        pdf.setLineWidth(1)
        pdf.line(30, y - 80, ancho - 30, y - 80)

        PDFFiscalService._dibujar_marca_homologacion(pdf, ancho, alto, mostrar=not ambiente_es_produccion)

        # Datos del receptor
        y = y - 110
        pdf.setFillColor(PDFFiscalService.COLOR_SUAVE)
        pdf.setStrokeColor(PDFFiscalService.COLOR_BORDE)
        pdf.rect(30, y - 85, ancho - 60, 85, fill=1, stroke=1)
        pdf.setFillColor(PDFFiscalService.COLOR_TEXTO)
        pdf.setFont("Helvetica-Bold", 12)
        pdf.drawString(40, y - 20, "Datos del receptor")

        rec_razon = str(PDFFiscalService._pick(datos_receptor, "razon_social", "nombre", default=""))
        rec_doc = str(PDFFiscalService._pick(datos_receptor, "cuit", "documento", default=""))
        rec_iva = str(PDFFiscalService._pick(datos_receptor, "condicion_iva", default=""))
        rec_dom = str(PDFFiscalService._pick(datos_receptor, "domicilio", default=""))

        pdf.setFont("Helvetica", 10)
        pdf.drawString(40, y - 38, f"Razon social / Nombre: {rec_razon}")
        pdf.drawString(40, y - 53, f"CUIT o documento: {rec_doc}")
        pdf.drawString(300, y - 38, f"Condicion IVA: {rec_iva}")
        pdf.drawString(300, y - 53, f"Domicilio: {rec_dom}")

        # Datos del comprobante
        y = y - 100
        pdf.setStrokeColor(PDFFiscalService.COLOR_BORDE)
        pdf.setFillColor(black)
        pdf.setFont("Helvetica-Bold", 12)
        pdf.drawString(30, y, "Datos del comprobante")

        pdf.setFont("Helvetica", 10)
        pdf.drawString(30, y - 18, f"Fecha comprobante: {PDFFiscalService._fmt_fecha(fecha)}")
        pdf.drawString(250, y - 18, f"Concepto: {concepto}")
        pdf.drawString(430, y - 18, f"Ambiente: {ambiente}")

        pdf.setFont("Helvetica-Bold", 11)
        pdf.drawString(30, y - 40, "Periodo facturado")
        pdf.setFont("Helvetica", 10)
        pdf.drawString(30, y - 58, f"Servicio desde: {PDFFiscalService._fmt_fecha(f_serv_desde)}")
        pdf.drawString(250, y - 58, f"Servicio hasta: {PDFFiscalService._fmt_fecha(f_serv_hasta)}")
        pdf.drawString(430, y - 58, f"Vto. pago: {PDFFiscalService._fmt_fecha(f_vto_pago)}")

        # ══════════════════ TABLA DE DETALLE (AMPLIADA) ══════════════════
        y = y - 80
        pdf.setFillColor(PDFFiscalService.COLOR_SUAVE)
        pdf.setStrokeColor(PDFFiscalService.COLOR_BORDE)
        pdf.setLineWidth(0.5)
        
        # Encabezados de tabla
        pdf.rect(30, y - 20, ancho - 60, 20, fill=1, stroke=1)
        pdf.setFillColor(PDFFiscalService.COLOR_TEXTO)
        pdf.setFont("Helvetica-Bold", 10)
        pdf.drawString(40, y - 12, "Cantidad")
        pdf.drawString(90, y - 12, "Descripcion")
        pdf.drawString(400, y - 12, "Precio unitario")
        pdf.drawString(480, y - 12, "Importe")
        
        filas_disponibles = 8
        filas_detalle = items[:filas_disponibles]
        if not filas_detalle:
            filas_detalle = [
                {
                    "cantidad": 0.0,
                    "descripcion": "Sin detalle de ítems",
                    "precio_unitario": 0.0,
                    "importe": 0.0,
                }
            ]

        for item in filas_detalle:
            y = y - 20
            pdf.setFillColor(white)
            pdf.rect(30, y - 20, ancho - 60, 20, fill=1, stroke=1)
            pdf.setFillColor(PDFFiscalService.COLOR_TEXTO)
            pdf.setFont("Helvetica", 10)
            pdf.drawRightString(80, y - 12, f"{float(item.get('cantidad', 0) or 0):,.2f}")
            pdf.drawString(90, y - 12, str(item.get("descripcion", "") or "-"))
            precio_unit = PDFFiscalService._fmt_moneda(item.get("precio_unitario", 0.0), moneda)
            importe_linea = PDFFiscalService._fmt_moneda(item.get("importe", 0.0), moneda)
            pdf.drawRightString(470, y - 12, precio_unit)
            pdf.drawRightString(555, y - 12, importe_linea)

        for _ in range(max(0, filas_disponibles - len(filas_detalle))):
            y = y - 20
            pdf.setFillColor(white)
            pdf.rect(30, y - 20, ancho - 60, 20, fill=1, stroke=1)
        
        y = y - 20

        # ══════════════════ BLOQUE FISCAL AL PIE ══════════════════
        # Línea separadora antes del bloque fiscal
        pdf.setStrokeColor(PDFFiscalService.COLOR_BORDE)
        pdf.setLineWidth(0.5)
        pdf.line(30, y, ancho - 30, y)
        
        # Se baja el bloque fiscal para acercarlo al pie sin invadir la leyenda inferior.
        y = y - 65
        pdf.setFillColor(PDFFiscalService.COLOR_TEXTO)
        tipo_normalizado = tipo.strip().upper()
        if tipo_normalizado == "FACTURA A":
            importe_neto = PDFFiscalService._to_float(
                PDFFiscalService._pick(datos_comprobante, "importe_neto", "neto_factura", default=0.0)
            )
            importe_iva = PDFFiscalService._to_float(
                PDFFiscalService._pick(datos_comprobante, "importe_iva", "importe_iva_factura", default=0.0)
            )
            alicuota_iva = PDFFiscalService._to_float(
                PDFFiscalService._pick(datos_comprobante, "alicuota_iva", default=21.0)
            )
            importe_total_fiscal = PDFFiscalService._to_float(
                PDFFiscalService._pick(datos_comprobante, "importe_total", default=importe_total)
            )
            etiquetas = [
                ("Importe neto gravado", importe_neto, "Helvetica-Bold", 11),
                (f"IVA {alicuota_iva:.0f} %", importe_iva, "Helvetica-Bold", 11),
                ("IMPORTE TOTAL", importe_total_fiscal, "Helvetica-Bold", 12),
            ]
            for indice, (etiqueta, valor, fuente, tamano) in enumerate(etiquetas):
                posicion_y = y - (indice * 18)
                pdf.setFont(fuente, tamano)
                pdf.drawString(40, posicion_y, etiqueta)
                pdf.drawRightString(ancho - 40, posicion_y, PDFFiscalService._fmt_moneda(valor, moneda))

            y = y - 56
        else:
            pdf.setFont("Helvetica-Bold", 12)
            importe_fmt = PDFFiscalService._fmt_moneda(importe_total, moneda)
            pdf.drawString(40, y, "IMPORTE TOTAL")
            pdf.drawRightString(ancho - 40, y, importe_fmt)

            y = y - 18

        pdf.setFont("Helvetica", 10)
        pdf.drawString(40, y - 18, "CAE")
        pdf.drawRightString(ancho - 40, y - 18, cae or "-")

        pdf.drawString(40, y - 36, "Vencimiento CAE")
        pdf.drawRightString(ancho - 40, y - 36, PDFFiscalService._fmt_fecha(vto_cae))
        
        pdf.line(30, y - 42, ancho - 30, y - 42)

        # ══════════════════ INTENTO DE DIBUJAR QR FISCAL ══════════════════
        # Construir QR desde datos persistidos (no recalcular desde cliente)
        qr_url = None
        try:
            # Extraer datos para QR desde factura_arca persistida
            # Si no están disponibles, el QR simplemente no se dibuja (fail-safe)
            punto_venta_num = PDFFiscalService._to_float(
                PDFFiscalService._pick(datos_comprobante, "punto_venta_num", default=None)
            )
            tipo_comprobante_num = PDFFiscalService._to_float(
                PDFFiscalService._pick(datos_comprobante, "tipo_comprobante_num", default=None)
            )
            numero_comprobante_num = PDFFiscalService._to_float(
                PDFFiscalService._pick(datos_comprobante, "numero_comprobante_num", default=None)
            )
            tipo_documento_receptor = PDFFiscalService._pick(
                datos_comprobante, "tipo_documento_receptor", default=None
            )
            documento_receptor = PDFFiscalService._pick(
                datos_comprobante, "documento_receptor", default=None
            )

            # Obtener CUIT emisor
            cuit_emisor = PDFFiscalService._to_float(
                PDFFiscalService._pick(datos_emisor, "cuit", default=None)
            )

            # Si tenemos datos suficientes, intentar construir QR
            if (
                cuit_emisor
                and punto_venta_num is not None
                and tipo_comprobante_num is not None
                and numero_comprobante_num is not None
                and cae
            ):
                # Normalizar tipos (pueden ser strings)
                try:
                    if tipo_documento_receptor is not None:
                        tipo_documento_receptor = int(tipo_documento_receptor)
                    if documento_receptor is not None:
                        documento_receptor = int(documento_receptor)
                except (TypeError, ValueError):
                    tipo_documento_receptor = None
                    documento_receptor = None

                service_qr = QrFiscalService()
                qr_url, qr_error = service_qr.construir_qr_completo(
                    ver=1,
                    fecha=fecha,  # Será normalizada en el servicio
                    cuit_emisor=int(cuit_emisor),
                    punto_venta_num=int(punto_venta_num),
                    tipo_comprobante_num=int(tipo_comprobante_num),
                    numero_comprobante_num=int(numero_comprobante_num),
                    importe=importe_total,
                    cae=str(cae),
                    tipo_documento_receptor=tipo_documento_receptor,
                    numero_documento_receptor=documento_receptor,
                )
        except Exception as qr_ex:
            # Fail-safe: si algo falla en construcción de QR, simplemente no se dibuja
            # El PDF continúa siendo válido sin QR
            qr_url = None

        # Dibujar QR si se construyó exitosamente
        if qr_url:
            try:
                # Posicionar QR en la esquina inferior derecha
                # Evitar superposición con CAE/vencimiento/pie
                tamaño_qr = 90
                x_qr = ancho - 30 - tamaño_qr
                y_qr = 50  # Posición Y suficientemente baja para evitar conflictos

                PDFFiscalService._dibujar_qr_fiscal(
                    pdf,
                    x_qr,
                    y_qr,
                    qr_url,
                    tamaño_qr_pt=tamaño_qr,
                    datos_comprobante=datos_comprobante,
                )
            except Exception:
                # Fail-safe: QR falla, PDF continúa
                pass

        # ══════════════════ PIE DEL DOCUMENTO ══════════════════
        # Leyenda inferior
        pdf.setFont("Helvetica", 8)
        pdf.setFillColor(HexColor("#666666"))
        pdf.drawString(30, 26, "Documento generado localmente para pruebas de homologacion. Sin validez fiscal.")

    @staticmethod
    def _dibujar_logo(pdf, x, y_banda_inferior, altura_banda, logo_path=None, datos_emisor=None):
        """Dibuja el logo dentro de la banda del encabezado.
        Retorna True si se dibujó, False si el archivo no existe o hay error."""
        try:
            ruta = Path(str(logo_path or "").strip())
            if not ruta.is_file():
                return False
            imagen = ImageReader(str(ruta))
            w_orig, h_orig = imagen.getSize()

            configuracion_logo = identidad_obtener_configuracion_logo_fiscal(datos_emisor)
            max_width = float(configuracion_logo.get("max_width", PDFFiscalService.LOGO_MAX_WIDTH) or PDFFiscalService.LOGO_MAX_WIDTH)
            max_height = float(configuracion_logo.get("max_height", PDFFiscalService.LOGO_MAX_HEIGHT) or PDFFiscalService.LOGO_MAX_HEIGHT)
            x_offset = float(configuracion_logo.get("x_offset", 0.0) or 0.0)
            y_offset = float(configuracion_logo.get("y_offset", 0.0) or 0.0)

            escala = min(
                max_width / float(w_orig),
                max_height / float(h_orig),
            )
            w = w_orig * escala
            h = h_orig * escala
            # Centrar verticalmente dentro de la banda
            x_final = float(x) + x_offset
            y = y_banda_inferior + (altura_banda - h) / 2 + y_offset
            pdf.drawImage(
                imagen,
                x_final,
                y,
                width=w,
                height=h,
                preserveAspectRatio=True,
                mask="auto",
            )
            return True
        except (OSError, ValueError, TypeError):
            return False

    @staticmethod
    def _resolver_logo_emisor(datos_emisor):
        return identidad_resolver_logo_emisor(datos_emisor)

    @staticmethod
    def _normalizar_cuit(cuit):
        return identidad_normalizar_cuit(cuit)

    @staticmethod
    def _normalizar_nombre_emisor(valor):
        return identidad_normalizar_nombre_emisor(valor)

    @staticmethod
    def _resolver_tipo_identidad_emisor(datos_emisor):
        return identidad_resolver_tipo_identidad_emisor(datos_emisor)

    @staticmethod
    def _obtener_dimensiones_logo_emisor(datos_emisor):
        # Se delega en módulo común preservando el tamaño fiscal histórico (120x44).
        tipo_identidad = PDFFiscalService._resolver_tipo_identidad_emisor(datos_emisor)
        base_width = PDFFiscalService.LOGO_MAX_WIDTH
        base_height = PDFFiscalService.LOGO_MAX_HEIGHT
        if tipo_identidad in {"publicidad_servicios", "publicidad_servicios_sh"}:
            base_width = PDFFiscalService.LOGO_MAX_WIDTH / 2.07
            base_height = PDFFiscalService.LOGO_MAX_HEIGHT / 2.07
        return identidad_obtener_dimensiones_logo_emisor(
            datos_emisor,
            base_width,
            base_height,
        )

    @staticmethod
    def _resolver_ruta_destino(ruta_destino):
        destino = Path(ruta_destino)

        if destino.suffix.lower() != ".pdf":
            destino = destino / "factura_c.pdf"

        if not destino.exists():
            return destino

        base = destino.stem
        sello = datetime.now().strftime("%Y%m%d_%H%M%S")
        return destino.with_name(f"{base}_{sello}.pdf")

    @staticmethod
    def _dibujar_qr_fiscal(
        pdf,
        x_posicion,
        y_posicion,
        url_qr,
        tamaño_qr_pt=90,
        datos_comprobante=None,
    ):
        """
        Dibujar código QR fiscal en el PDF.

        Args:
            pdf: Canvas de ReportLab
            x_posicion: Posición X en puntos
            y_posicion: Posición Y en puntos
            url_qr: URL QR completa desde QrFiscalService
            tamaño_qr_pt: Tamaño del QR en puntos (default 90)
            datos_comprobante: Dict con datos (opcional, para logging)

        Nota:
            - Fail-safe: Si falla, LOG y continúa sin QR
            - No modifica datos
            - No llama ARCA
        """
        try:
            if not url_qr or not isinstance(url_qr, str):
                return False

            if "?p=" not in url_qr:
                return False

            qr_widget = QrCodeWidget(url_qr, barBorder=2)
            x_min, y_min, x_max, y_max = qr_widget.getBounds()
            qr_width = x_max - x_min
            qr_height = y_max - y_min
            escala_x = tamaño_qr_pt / qr_width
            escala_y = tamaño_qr_pt / qr_height
            drawing = Drawing(
                tamaño_qr_pt,
                tamaño_qr_pt,
                transform=[escala_x, 0, 0, escala_y, 0, 0],
            )
            drawing.add(qr_widget)
            renderPDF.draw(drawing, pdf, x_posicion, y_posicion)

            return True

        except Exception:
            # Fail-safe: LOG y continúa sin QR
            # No raisea excepción
            return False

    @staticmethod
    def _dibujar_marca_homologacion(pdf, ancho, alto, mostrar=True):
        if not mostrar:
            return
        pdf.saveState()
        pdf.translate(ancho / 2, alto / 2)
        pdf.rotate(28)
        pdf.setFillColor(PDFFiscalService.COLOR_AGUA)
        pdf.setFont("Helvetica-Bold", 34)
        pdf.drawCentredString(0, 0, "HOMOLOGACION - SIN VALIDEZ FISCAL")
        pdf.restoreState()

    @staticmethod
    def _fmt_moneda(valor, moneda):
        moneda_upper = str(moneda or "PES").upper()
        valor_fmt = PDFFiscalService._to_float(valor)
        simbolo = "$" if moneda_upper == "PES" else moneda_upper
        return f"{simbolo} {valor_fmt:,.2f}"

    @staticmethod
    def _fmt_fecha(valor):
        texto = str(valor or "").strip()
        if len(texto) == 8 and texto.isdigit():
            return f"{texto[6:8]}/{texto[4:6]}/{texto[0:4]}"
        return texto

    @staticmethod
    def _pick(origen, *claves, default=""):
        if not isinstance(origen, dict):
            return default
        for clave in claves:
            if clave in origen and origen.get(clave) is not None:
                return origen.get(clave)
        return default

    @staticmethod
    def _to_float(valor):
        try:
            return float(str(valor or "0").replace(",", "."))
        except (TypeError, ValueError):
            return 0.0

    @staticmethod
    def _normalizar_items(items):
        filas = []
        for item in list(items or []):
            if not isinstance(item, dict):
                continue
            filas.append(
                {
                    "cantidad": PDFFiscalService._to_float(item.get("cantidad", 0.0)),
                    "descripcion": str(item.get("descripcion", "") or "").strip(),
                    "precio_unitario": PDFFiscalService._to_float(item.get("precio_unitario", 0.0)),
                    "importe": PDFFiscalService._to_float(item.get("importe", 0.0)),
                }
            )
        return filas

    @staticmethod
    def _formatear_codigo(punto_venta, numero):
        """Formatea punto de venta y número en código de comprobante: 00002-00000003"""
        try:
            pv = int(punto_venta or 0)
            num = int(numero or 0)
            return f"{pv:05d}-{num:08d}"
        except (TypeError, ValueError):
            return "-----"
