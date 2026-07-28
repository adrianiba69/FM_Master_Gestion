import re
import os
import subprocess
import webbrowser
from pathlib import Path
from urllib.parse import quote, urlencode

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

    @classmethod
    def abrir_whatsapp_factura(cls, numero, mensaje, pdf_path):
        numero_normalizado = cls.normalizar_numero(numero)
        ruta_pdf_abs = os.path.abspath(os.path.normpath(str(pdf_path or "")))
        existe = os.path.exists(ruta_pdf_abs)
        es_archivo = os.path.isfile(ruta_pdf_abs)
        print(f"[WhatsAppFactura][Diag] Ruta absoluta PDF: {ruta_pdf_abs}")
        print(f"[WhatsAppFactura][Diag] os.path.exists(pdf): {existe}")
        print(f"[WhatsAppFactura][Diag] os.path.isfile(pdf): {es_archivo}")
        if not existe or not es_archivo:
            raise ValueError("No se encontró el archivo PDF para adjuntar.")

        resultado_chat = cls.abrir_chat_con_fallback(numero_normalizado, mensaje)
        resultado_explorador = cls.mostrar_pdf_en_explorador(ruta_pdf_abs)
        comando_explorer = str(resultado_explorador.get("comando", ""))
        url_usada = str(resultado_chat["url"])
        print(f"[WhatsAppFactura][Diag] Comando Explorer enviado: {comando_explorer}")
        print(f"[WhatsAppFactura][Diag] URL WhatsApp usada: {url_usada}")
        return {
            "numero": numero_normalizado,
            "canal": resultado_chat["canal"],
            "url": url_usada,
            "url_desktop": resultado_chat.get("url_desktop", ""),
            "pdf_path": ruta_pdf_abs,
            "pdf_exists": existe,
            "pdf_isfile": es_archivo,
            "explorer_command": comando_explorer,
            "explorador_seleccion_ok": bool(resultado_explorador.get("seleccion_ok")),
            "explorador_advertencia": resultado_explorador.get("advertencia", ""),
        }

    @staticmethod
    def abrir_chat_con_fallback(numero_normalizado, mensaje):
        numero = str(numero_normalizado or "").strip()
        if not numero:
            raise ValueError("No se pudo preparar el número de WhatsApp.")

        texto = str(mensaje or "").strip()
        mensaje_codificado = quote(texto, safe="")
        url_desktop = f"whatsapp://send?phone={numero}&text={mensaje_codificado}"

        print(f"[WhatsAppFactura] URL desktop generada: {url_desktop}")

        try:
            if hasattr(os, "startfile"):
                os.startfile(url_desktop)
                print(f"[WhatsAppFactura] URL usada: {url_desktop}")
                return {"canal": "desktop", "url": url_desktop, "url_desktop": url_desktop}
            else:
                desktop_abierto = bool(webbrowser.open(url_desktop, new=0, autoraise=True))
                if desktop_abierto:
                    print(f"[WhatsAppFactura] URL usada: {url_desktop}")
                    return {"canal": "desktop", "url": url_desktop, "url_desktop": url_desktop}
        except (OSError, webbrowser.Error):
            pass

        raise OSError("No fue posible iniciar WhatsApp Desktop.")

    @staticmethod
    def mostrar_pdf_en_explorador(pdf_path):
        ruta_pdf = os.path.abspath(os.path.normpath(str(pdf_path or "")))
        if not os.path.exists(ruta_pdf) or not os.path.isfile(ruta_pdf):
            raise ValueError("No se encontro el archivo PDF para mostrar.")

        comando_select = f'explorer /select,"{os.path.normpath(ruta_pdf)}"'
        print(f"[WhatsAppFactura] Comando Explorer: {comando_select}")

        try:
            subprocess.Popen(
                comando_select,
                shell=True,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            return {
                "seleccion_ok": True,
                "advertencia": "",
                "comando": str(comando_select),
            }
        except OSError:
            carpeta = os.path.dirname(ruta_pdf) or ruta_pdf
            comando_carpeta = ["explorer", os.path.normpath(carpeta)]
            print(f"[WhatsAppFactura] Fallback Explorer carpeta: {comando_carpeta}")
            try:
                subprocess.Popen(
                    comando_carpeta,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
                return {
                    "seleccion_ok": False,
                    "advertencia": (
                        "No se pudo seleccionar el PDF automáticamente en Explorer.\n"
                        f"Ruta del archivo: {ruta_pdf}"
                    ),
                    "comando": str(comando_select),
                }
            except (AttributeError, OSError) as error:
                raise OSError(
                    "No se pudo abrir Explorer para el PDF.\n"
                    f"Ruta del archivo: {ruta_pdf}"
                ) from error

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
