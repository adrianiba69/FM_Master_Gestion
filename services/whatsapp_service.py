import re
import os
import subprocess
import webbrowser
from pathlib import Path
from urllib.parse import urlencode

from database import conectar
from runtime_paths import APP_DIR


class WhatsAppService:
    MENSAJE = (
        "Hola, te enviamos el resumen de FM Master 98.3. "
        "Adjunto el comprobante correspondiente."
    )
    RAIZ_PROYECTO = APP_DIR

    @classmethod
    def preparar_envio_resumen(cls, resumen_id):
        conn = conectar()
        cur = conn.cursor()
        cur.execute("""
            SELECT
                COALESCE(c.whatsapp, ''),
                COALESCE(r.pdf_path, ''),
                COALESCE(NULLIF(c.razon_social, ''), c.nombre),
                r.numero
            FROM resumenes r
            JOIN clientes c ON c.id=r.cliente_id
            WHERE r.id=?
        """, (resumen_id,))
        fila = cur.fetchone()
        conn.close()

        if fila is None:
            raise ValueError("No se encontro el resumen seleccionado.")

        whatsapp, pdf_path, cliente, numero_resumen = fila
        if not whatsapp.strip():
            raise ValueError("El cliente no tiene un numero de WhatsApp cargado.")
        if not pdf_path.strip():
            raise ValueError("El resumen no tiene un PDF generado.")

        ruta_pdf = Path(pdf_path)
        if not ruta_pdf.is_absolute():
            ruta_pdf = cls.RAIZ_PROYECTO / ruta_pdf
        ruta_pdf = ruta_pdf.resolve()
        if not ruta_pdf.is_file():
            raise ValueError("No se encontro el archivo PDF generado para este resumen.")

        numero = cls.normalizar_numero(whatsapp)
        parametros = urlencode({"phone": numero, "text": cls.MENSAJE})
        return {
            "url": f"https://web.whatsapp.com/send?{parametros}",
            "numero": numero,
            "pdf_path": str(ruta_pdf),
            "cliente": cliente,
            "numero_resumen": numero_resumen,
        }

    @classmethod
    def abrir_whatsapp_resumen(cls, resumen_id):
        datos = cls.preparar_envio_resumen(resumen_id)
        webbrowser.open(datos["url"], new=0)
        cls.mostrar_pdf_en_explorador(datos["pdf_path"])
        return datos

    @staticmethod
    def mostrar_pdf_en_explorador(pdf_path):
        ruta_pdf = Path(pdf_path).resolve()
        if not ruta_pdf.is_file():
            raise ValueError("No se encontro el archivo PDF para mostrar.")

        try:
            subprocess.Popen(
                ["explorer.exe", "/select,", str(ruta_pdf)],
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except OSError:
            try:
                os.startfile(str(ruta_pdf.parent))
            except (AttributeError, OSError) as error:
                raise OSError("No se pudo abrir la carpeta del PDF.") from error

    @staticmethod
    def normalizar_numero(numero):
        digitos = re.sub(r"\D", "", str(numero or ""))
        if digitos.startswith("00"):
            digitos = digitos[2:]
        if len(digitos) < 8:
            raise ValueError("El numero de WhatsApp cargado no es valido.")

        formato_local = re.fullmatch(r"0?(\d{2,4})15(\d{6,8})", digitos)
        if formato_local:
            return f"549{formato_local.group(1)}{formato_local.group(2)}"
        if digitos.startswith("549"):
            return digitos
        if digitos.startswith("54"):
            return f"549{digitos[2:]}"
        if digitos.startswith("0"):
            digitos = digitos[1:]
        if len(digitos) == 10:
            return f"549{digitos}"
        return digitos
