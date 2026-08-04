import os
from datetime import datetime
from pathlib import Path

from reportlab.lib.colors import HexColor, white
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas

from config import CUIT, DIRECCION, EMAIL, EMPRESA, TELEFONO
from pdf.nombre_archivos import nombre_resumen_pdf
from runtime_paths import APP_DIR, ASSETS_DIR, PDF_DIR
from services.resumen_service import ResumenService


class ResumenPDF:
    ROJO = HexColor("#C00000")
    NEGRO = HexColor("#111111")
    GRIS = HexColor("#EFEFEF")
    GRIS_BORDE = HexColor("#BEBEBE")
    LOGO_WIDTH = 170
    LOGO_HEIGHT = 60
    LOGO_X = 38
    LOGO_Y = 749
    LOGO_FM_MASTER_INSTITUCIONAL = ASSETS_DIR / "logos" / "logo_fm_master.png"
    CUIT_FM_MASTER_NORMALIZADO = "20206871629"

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
        nombre_estandar = nombre_resumen_pdf(resumen.cliente_id, resumen.numero)
        destino = Path(ruta) if ruta else carpeta / nombre_estandar
        if not destino.is_absolute():
            destino = APP_DIR / destino
        destino = destino.resolve()
        destino.parent.mkdir(parents=True, exist_ok=True)

        emisor_nombre = cls._texto_emisor(emisor, "nombre_fantasia", "razon_social")
        emisor_cuit = cls._texto_emisor(emisor, "cuit")
        emisor_domicilio = cls._texto_emisor(emisor, "domicilio")

        if not emisor or not emisor_nombre or not emisor_cuit or not emisor_domicilio:
            raise ValueError(
                "No se puede generar el PDF del resumen porque no se pudo resolver el emisor fiscal "
                "con nombre, CUIT y domicilio. Revise la configuración fiscal del cliente/emisor."
            )

        documento = canvas.Canvas(str(destino), pagesize=A4, pageCompression=1)
        documento.setTitle(f"Resumen {resumen.numero:06d} - {cliente[2]}")
        documento.setAuthor(cls._texto_emisor(emisor, "razon_social", "nombre_fantasia") or EMPRESA)
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

    @staticmethod
    def _normalizar_cuit(cuit):
        return "".join(char for char in str(cuit or "") if char.isdigit())

    @classmethod
    def _ruta_existente(cls, candidato):
        texto = str(candidato or "").strip()
        if not texto:
            return None

        ruta = Path(texto)
        rutas_candidatas = [ruta]
        if not ruta.is_absolute():
            rutas_candidatas.append(APP_DIR / ruta)

        for ruta_candidata in rutas_candidatas:
            try:
                ruta_resuelta = ruta_candidata.resolve()
            except OSError:
                continue
            if ruta_resuelta.is_file():
                return ruta_resuelta
        return None

    @classmethod
    def _ruta_estandar_resumen(cls, resumen):
        return (PDF_DIR / "resumenes" / nombre_resumen_pdf(resumen.cliente_id, resumen.numero)).resolve()

    @classmethod
    def _buscar_pdf_existente(cls, resumen):
        ruta_guardada = cls._ruta_existente(getattr(resumen, "pdf_path", ""))
        if ruta_guardada:
            return ruta_guardada

        ruta_estandar = cls._ruta_estandar_resumen(resumen)
        if ruta_estandar.is_file():
            return ruta_estandar

        carpeta = (PDF_DIR / "resumenes").resolve()
        numero = int(getattr(resumen, "numero", 0) or 0)
        legacy_nombres = [
            f"resumen_{numero:06d}.pdf",
            f"resumen_{numero}.pdf",
        ]
        for nombre in legacy_nombres:
            ruta_legacy_directa = carpeta / nombre
            if ruta_legacy_directa.is_file():
                return ruta_legacy_directa

            coincidencias = list(carpeta.rglob(nombre))
            if coincidencias:
                coincidencias.sort(key=lambda ruta: ruta.stat().st_mtime, reverse=True)
                return coincidencias[0].resolve()

        coincidencias_estandar = list(carpeta.rglob(f"*_Resumen_{numero}.pdf"))
        if coincidencias_estandar:
            coincidencias_estandar.sort(key=lambda ruta: ruta.stat().st_mtime, reverse=True)
            return coincidencias_estandar[0].resolve()

        return None

    @classmethod
    def obtener_ruta_pdf_resumen(cls, resumen_id, regenerar_si_falta=True):
        resumen = ResumenService.obtener(resumen_id)
        if resumen is None:
            raise ValueError("No se encontro el resumen seleccionado.")

        ruta_existente = cls._buscar_pdf_existente(resumen)
        if ruta_existente and ruta_existente.is_file():
            ResumenService.actualizar_pdf_path(resumen.id, os.path.normpath(str(ruta_existente)))
            return str(ruta_existente)

        if not regenerar_si_falta:
            return ""
        return cls.generar(resumen.id)

    @classmethod
    def _dibujar_logo(cls, documento):
        return cls._dibujar_logo_desde_ruta(documento, None)

    @classmethod
    def _dibujar_logo_desde_ruta(cls, documento, logo_path):
        try:
            ruta = Path(str(logo_path or "").strip())
            if not ruta.is_file():
                return False
            imagen = ImageReader(str(ruta))
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

    @staticmethod
    def _texto_emisor(emisor, *claves, default=""):
        if not isinstance(emisor, dict):
            return default
        for clave in claves:
            valor = str(emisor.get(clave) or "").strip()
            if valor:
                return valor
        return default

    @classmethod
    def _resolver_logo_emisor(cls, emisor):
        if not isinstance(emisor, dict):
            return None

        candidatos_explicitos = [
            emisor.get("logo_path"),
            emisor.get("ruta_logo"),
            emisor.get("logo"),
        ]
        for candidato in candidatos_explicitos:
            ruta = cls._ruta_existente(candidato)
            if ruta:
                return ruta

        carpeta = str(emisor.get("carpeta_facturas") or "").strip()
        if carpeta:
            base = Path(carpeta)
            for candidato in (
                base / "logo.png",
                base / "logo.jpg",
                base / "logo.jpeg",
                base / "logo.webp",
                base / "logo_emisor.png",
                base / "logo_emisor.jpg",
            ):
                ruta = cls._ruta_existente(candidato)
                if ruta:
                    return ruta

        emisor_id = int(emisor.get("id") or 0)
        cuit_normalizado = cls._normalizar_cuit(emisor.get("cuit"))
        if emisor_id == 1 or cuit_normalizado == cls.CUIT_FM_MASTER_NORMALIZADO:
            ruta_institucional = cls._ruta_existente(cls.LOGO_FM_MASTER_INSTITUCIONAL)
            if ruta_institucional:
                return ruta_institucional

        return None

    @classmethod
    def _encabezado(cls, documento, resumen, cliente, emisor=None):
        logo_path = cls._resolver_logo_emisor(emisor)
        cls._dibujar_logo_desde_ruta(documento, logo_path)

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
        empresa_nombre = cls._texto_emisor(emisor, "nombre_fantasia", "razon_social")
        empresa_razon_social = cls._texto_emisor(emisor, "razon_social")
        empresa_cuit = cls._texto_emisor(emisor, "cuit")
        empresa_direccion = cls._texto_emisor(emisor, "domicilio")
        empresa_telefono = cls._texto_emisor(emisor, "telefono")
        empresa_email = cls._texto_emisor(emisor, "email")
        documento.drawString(38, 715, cls._ajustar_texto(empresa_nombre or empresa_razon_social or "Emisor fiscal", 285, 11, True))
        documento.setFont("Helvetica", 9)
        if empresa_razon_social and empresa_razon_social != empresa_nombre:
            documento.drawString(38, 700, cls._ajustar_texto(empresa_razon_social, 285, 9))
            texto_cuit_y = 686
        else:
            texto_cuit_y = 698
        documento.drawString(38, texto_cuit_y, f"CUIT: {empresa_cuit or '-'}")
        documento.drawString(38, texto_cuit_y - 15, cls._ajustar_texto(f"Domicilio: {empresa_direccion or '-'}", 285, 9))
        contacto = "  |  ".join(parte for parte in (empresa_telefono, empresa_email) if parte)
        if contacto:
            documento.drawString(38, texto_cuit_y - 30, cls._ajustar_texto(f"Contacto: {contacto}", 285, 9))

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
        tipo_factura = str(getattr(resumen, "tipo_factura", "") or "").strip().upper()
        subtotal_neto = float(getattr(resumen, "total", 0) or 0)
        if tipo_factura == "FACTURA A":
            alicuota_iva = 21.0
            importe_iva = round(subtotal_neto * alicuota_iva / 100.0, 2)
            total_fiscal = round(subtotal_neto + importe_iva, 2)
            saldo_fiscal = total_fiscal

            documento.setFillColor(HexColor("#F7F7F7"))
            documento.setStrokeColor(cls.GRIS_BORDE)
            documento.rect(366, 58, 191, 118, stroke=1, fill=1)

            lineas = [
                ("SUBTOTAL NETO", cls.moneda(subtotal_neto), cls.NEGRO, 11),
                (f"IVA {alicuota_iva:.0f} %", cls.moneda(importe_iva), cls.NEGRO, 11),
                ("TOTAL", cls.moneda(total_fiscal), cls.NEGRO, 12),
                ("SALDO", cls.moneda(saldo_fiscal), cls.ROJO, 13),
            ]
            posiciones_y = [146, 123, 100, 77]
            for (etiqueta, valor, color, tamanio), posicion_y in zip(lineas, posiciones_y):
                documento.setFillColor(color)
                documento.setFont("Helvetica-Bold", tamanio)
                documento.drawString(382, posicion_y, etiqueta)
                documento.drawRightString(542, posicion_y, valor)

            documento.setStrokeColor(cls.ROJO)
            documento.setLineWidth(1.2)
            documento.line(381, 111, 542, 111)
        else:
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
