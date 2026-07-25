from datetime import datetime
from pathlib import Path

from reportlab.lib.colors import HexColor, black, white
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

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

            pdf = canvas.Canvas(str(destino_final), pagesize=A4, pageCompression=1)
            pdf.setTitle("Factura C")
            pdf.setAuthor(str(PDFFiscalService._pick(datos_emisor, "razon_social", "nombre_fantasia", default="Emisor")))
            pdf.setSubject("Factura C - Homologacion")

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

        # Extraer datos del emisor
        emisor_nombre_fantasia = str(PDFFiscalService._pick(datos_emisor, "nombre_fantasia", default=""))
        emisor_razon_social = str(PDFFiscalService._pick(datos_emisor, "razon_social", default=""))
        emisor_cuit = str(PDFFiscalService._pick(datos_emisor, "cuit", default=""))
        emisor_iva = str(PDFFiscalService._pick(datos_emisor, "condicion_iva", default=""))
        emisor_domicilio = str(PDFFiscalService._pick(datos_emisor, "domicilio", default=""))
        emisor_punto_venta = str(PDFFiscalService._pick(datos_emisor, "punto_venta", default=punto_venta))

        # ══════════════════ ENCABEZADO PROFESIONAL ══════════════════
        y = alto - 30

        # Logo (esquina superior izquierda)
        PDFFiscalService._dibujar_logo(pdf, x=30, y_banda_inferior=y - 80, altura_banda=80)

        # Información del emisor (columna central-izquierda)
        pdf.setFillColor(PDFFiscalService.COLOR_TEXTO)
        pdf.setFont("Helvetica-Bold", 16)
        pdf.drawString(170, y - 5, emisor_nombre_fantasia)

        pdf.setFont("Helvetica", 10)
        pdf.drawString(170, y - 20, emisor_razon_social)

        pdf.setFont("Helvetica", 9)
        pdf.drawString(170, y - 32, f"CUIT: {emisor_cuit}")
        pdf.drawString(170, y - 42, f"IVA: {emisor_iva}")
        pdf.drawString(170, y - 52, f"Domicilio: {emisor_domicilio}")
        pdf.drawString(170, y - 62, f"Pto. Venta: {emisor_punto_venta}")

        # Bloque con datos del comprobante (sin fondo rojo, sobre blanco)
        # Alineado al margen derecho del contenido para separar mejor del emisor.
        ancho_bloque_comp = 225
        x_bloque_comp = (ancho - 30) - ancho_bloque_comp
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

        PDFFiscalService._dibujar_marca_homologacion(pdf, ancho, alto)

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
        pdf.setFont("Helvetica-Bold", 12)
        importe_fmt = PDFFiscalService._fmt_moneda(importe_total, moneda)
        pdf.drawString(40, y, "IMPORTE TOTAL")
        pdf.drawRightString(ancho - 40, y, importe_fmt)
        
        pdf.setFont("Helvetica", 10)
        pdf.drawString(40, y - 18, "CAE")
        pdf.drawRightString(ancho - 40, y - 18, cae or "-")
        
        pdf.drawString(40, y - 36, "Vencimiento CAE")
        pdf.drawRightString(ancho - 40, y - 36, PDFFiscalService._fmt_fecha(vto_cae))
        
        pdf.line(30, y - 42, ancho - 30, y - 42)

        # Leyenda inferior
        pdf.setFont("Helvetica", 8)
        pdf.setFillColor(HexColor("#666666"))
        pdf.drawString(30, 26, "Documento generado localmente para pruebas de homologacion. Sin validez fiscal.")

    @staticmethod
    def _dibujar_logo(pdf, x, y_banda_inferior, altura_banda):
        """Dibuja el logo dentro de la banda del encabezado.
        Retorna True si se dibujó, False si el archivo no existe o hay error."""
        try:
            logo_path = PDFFiscalService.LOGO_PATH
            if not Path(logo_path).exists():
                return False
            imagen = ImageReader(str(logo_path))
            w_orig, h_orig = imagen.getSize()
            escala = min(
                PDFFiscalService.LOGO_MAX_WIDTH / float(w_orig),
                PDFFiscalService.LOGO_MAX_HEIGHT / float(h_orig),
            )
            w = w_orig * escala
            h = h_orig * escala
            # Centrar verticalmente dentro de la banda
            y = y_banda_inferior + (altura_banda - h) / 2
            pdf.drawImage(
                imagen,
                x,
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
    def _dibujar_marca_homologacion(pdf, ancho, alto):
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
