import os
from datetime import datetime
from pathlib import Path

from reportlab.lib.colors import HexColor, white
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas

from config import CUIT, DIRECCION, EMAIL, EMPRESA, TELEFONO
from runtime_paths import ASSETS_DIR, PDF_DIR
from services.resumen_service import ResumenService


class ResumenPDF:
    ROJO = HexColor("#C00000")
    NEGRO = HexColor("#111111")
    GRIS = HexColor("#EFEFEF")
    GRIS_BORDE = HexColor("#BEBEBE")

    LOGO_PATH = ASSETS_DIR / "logos" / "logo_fm_master.png"
    LOGO_WIDTH = 170
    LOGO_HEIGHT = 60
    LOGO_X = 38
    LOGO_Y = 749

    @staticmethod
    def moneda(valor):
        numero = f"{float(valor or 0):,.2f}"
        return "$ " + numero.replace(",", "X").replace(".", ",").replace("X", ".")

    @staticmethod
    def fecha(valor):
        return datetime.strptime(valor, "%Y-%m-%d").strftime("%d/%m/%Y")

    @classmethod
    def generar(cls, resumen_id, ruta=None):
        resumen = ResumenService.obtener(resumen_id)
        cliente = ResumenService.obtener_cliente(resumen_id)
        emisor = ResumenService.obtener_emisor_de_cliente(resumen_id)
        if resumen is None or cliente is None:
            raise ValueError("No se encontro la informacion del resumen.")

        carpeta = PDF_DIR / "resumenes"
        carpeta.mkdir(parents=True, exist_ok=True)
        destino = Path(ruta) if ruta else carpeta / f"resumen_{resumen.numero:06d}.pdf"
        destino.parent.mkdir(parents=True, exist_ok=True)

        documento = canvas.Canvas(str(destino), pagesize=A4, pageCompression=1)
        documento.setTitle(f"Resumen {resumen.numero:06d} - {cliente[2]}")
        documento.setAuthor(emisor[1] if emisor else EMPRESA)
        documento.setSubject("Resumen de servicios")

        conceptos = resumen.conceptos or []
        por_pagina = 18
        paginas = [
            conceptos[indice:indice + por_pagina]
            for indice in range(0, len(conceptos), por_pagina)
        ] or [[]]

        for indice, conceptos_pagina in enumerate(paginas):
            cls._encabezado(documento, resumen, cliente, emisor)
            cls._dibujar_conceptos(documento, conceptos_pagina)

            if indice == len(paginas) - 1:
                cls._dibujar_totales(documento, resumen)

            documento.setFont("Helvetica", 8)
            documento.setFillColor(HexColor("#595959"))
            documento.drawString(38, 38, "Gracias por confiar en FM Master.")
            documento.drawRightString(557, 38, f"Pagina {indice + 1}/{len(paginas)}")
            documento.showPage()

        documento.save()
        ruta_guardada = os.path.normpath(str(destino))
        ResumenService.actualizar_pdf_path(resumen.id, ruta_guardada)
        return str(destino.resolve())

    @classmethod
    def _dibujar_logo(cls, documento):
        try:
            imagen = ImageReader(str(cls.LOGO_PATH))
            ancho_original, alto_original = imagen.getSize()
            escala = min(
                cls.LOGO_WIDTH / float(ancho_original),
                cls.LOGO_HEIGHT / float(alto_original),
            )
            ancho = ancho_original * escala
            alto = alto_original * escala
            y = cls.LOGO_Y + (cls.LOGO_HEIGHT - alto) / 2
            documento.drawImage(
                imagen,
                cls.LOGO_X,
                y,
                width=ancho,
                height=alto,
                preserveAspectRatio=True,
                mask="auto",
            )
            return True
        except (OSError, ValueError, TypeError):
            return False

    @classmethod
    def _encabezado(cls, documento, resumen, cliente, emisor=None):
        if not cls._dibujar_logo(documento):
            documento.setFillColor(cls.ROJO)
            documento.rect(cls.LOGO_X, 752, cls.LOGO_WIDTH, 55, stroke=0, fill=1)
            documento.setFillColor(white)
            documento.setFont("Helvetica-Bold", 19)
            documento.drawString(cls.LOGO_X + 14, 773, "FM MASTER 98.3")

        documento.setFillColor(cls.ROJO)
        documento.setFont("Helvetica-Bold", 25)
        documento.drawRightString(557, 782, "RESUMEN")
        documento.setFillColor(cls.NEGRO)
        documento.setFont("Helvetica-Bold", 11)
        documento.drawRightString(557, 758, f"Nro. {resumen.numero:06d}")

        documento.setStrokeColor(cls.ROJO)
        documento.setLineWidth(2)
        documento.line(38, 735, 557, 735)

        documento.setFillColor(cls.NEGRO)
        documento.setFont("Helvetica-Bold", 11)
        empresa_nombre = emisor[1] if emisor else EMPRESA
        empresa_cuit = emisor[2] if emisor else CUIT
        empresa_direccion = emisor[4] if emisor else DIRECCION
        empresa_telefono = emisor[6] if emisor else TELEFONO
        empresa_email = emisor[7] if emisor else EMAIL
        documento.drawString(38, 715, empresa_nombre)
        documento.setFont("Helvetica", 9)
        documento.drawString(38, 698, f"CUIT: {empresa_cuit}")
        documento.drawString(38, 683, f"Direccion: {empresa_direccion}")
        documento.drawString(38, 668, f"Telefono: {empresa_telefono}  |  {empresa_email}")

        documento.setFillColor(cls.GRIS)
        documento.setStrokeColor(cls.GRIS_BORDE)
        documento.setLineWidth(0.7)
        documento.rect(365, 665, 192, 61, stroke=1, fill=1)
        documento.setFillColor(cls.ROJO)
        documento.setFont("Helvetica-Bold", 8)
        documento.drawString(380, 706, "FECHA")
        documento.drawString(380, 683, "VENCIMIENTO")
        documento.setFillColor(cls.NEGRO)
        documento.setFont("Helvetica-Bold", 9)
        documento.drawString(465, 706, cls.fecha(resumen.fecha))
        documento.drawString(465, 683, cls.fecha(resumen.fecha_vencimiento))

        documento.setFillColor(HexColor("#FAFAFA"))
        documento.setStrokeColor(cls.GRIS_BORDE)
        documento.rect(38, 584, 519, 66, stroke=1, fill=1)
        documento.setFillColor(cls.ROJO)
        documento.rect(38, 584, 6, 66, stroke=0, fill=1)
        documento.setFont("Helvetica-Bold", 9)
        documento.drawString(52, 635, "CLIENTE")
        documento.setFillColor(cls.NEGRO)
        documento.setFont("Helvetica-Bold", 13)
        documento.drawString(52, 614, cls._ajustar_texto(cliente[2], 285, 13, True))
        documento.setFont("Helvetica", 9)
        domicilio = " - ".join(parte for parte in (cliente[5], cliente[6]) if parte)
        documento.drawString(52, 594, cls._ajustar_texto(domicilio, 285, 9))
        documento.drawString(365, 635, f"CUIT: {cliente[9] or '-'}")
        documento.drawString(365, 614, f"IVA: {cliente[10] or '-'}")

        documento.setFillColor(cls.ROJO)
        documento.rect(38, 540, 519, 28, stroke=0, fill=1)
        documento.setFillColor(white)
        documento.setFont("Helvetica-Bold", 8)
        documento.drawString(48, 550, "CANT.")
        documento.drawString(102, 550, "DESCRIPCION")
        documento.drawString(307, 550, "PRECIO UNIT.")
        documento.drawString(394, 550, "DESCUENTO")
        documento.drawString(492, 550, "TOTAL")

    @classmethod
    def _dibujar_conceptos(cls, documento, conceptos):
        y = 520
        documento.setFillColor(cls.NEGRO)
        documento.setFont("Helvetica", 9)

        for concepto in conceptos:
            descripcion = concepto.concepto
            if concepto.descripcion:
                descripcion = f"{descripcion} - {concepto.descripcion}"

            documento.drawCentredString(65, y, f"{concepto.cantidad:g}")
            documento.drawString(102, y, cls._ajustar_texto(descripcion, 194, 9))
            documento.drawRightString(382, y, cls.moneda(concepto.importe))
            documento.drawRightString(466, y, cls.moneda(concepto.descuento))
            documento.setFont("Helvetica-Bold", 9)
            documento.drawRightString(550, y, cls.moneda(concepto.total))
            documento.setFont("Helvetica", 9)

            documento.setStrokeColor(HexColor("#D9D9D9"))
            documento.setLineWidth(0.5)
            documento.line(38, y - 8, 557, y - 8)
            y -= 25

    @classmethod
    def _dibujar_totales(cls, documento, resumen):
        documento.setFillColor(HexColor("#F7F7F7"))
        documento.setStrokeColor(cls.GRIS_BORDE)
        documento.rect(366, 72, 191, 78, stroke=1, fill=1)

        documento.setFillColor(cls.NEGRO)
        documento.setFont("Helvetica-Bold", 11)
        documento.drawString(382, 124, "TOTAL")
        documento.drawRightString(542, 124, cls.moneda(resumen.total))
        documento.setStrokeColor(cls.ROJO)
        documento.setLineWidth(1.2)
        documento.line(381, 111, 542, 111)
        documento.setFillColor(cls.ROJO)
        documento.setFont("Helvetica-Bold", 13)
        documento.drawString(382, 88, "SALDO")
        documento.drawRightString(542, 88, cls.moneda(resumen.saldo))

    @staticmethod
    def _ajustar_texto(texto, ancho_maximo, tamano, negrita=False):
        valor = str(texto or "")
        fuente = "Helvetica-Bold" if negrita else "Helvetica"
        if stringWidth(valor, fuente, tamano) <= ancho_maximo:
            return valor

        sufijo = "..."
        while valor and stringWidth(valor + sufijo, fuente, tamano) > ancho_maximo:
            valor = valor[:-1]
        return valor.rstrip() + sufijo
