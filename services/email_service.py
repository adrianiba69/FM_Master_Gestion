import os
import re
import subprocess
import webbrowser
from pathlib import Path
from urllib.parse import quote, urlencode


class EmailService:
    OUTLOOK_COMPOSE_URL = "https://outlook.live.com/mail/0/deeplink/compose"

    @staticmethod
    def validar_email_basico(email):
        texto = str(email or "").strip()
        if not texto:
            return False
        return bool(re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", texto))

    @staticmethod
    def _resolver_ruta_absoluta(ruta):
        valor = str(ruta or "").strip()
        if not valor:
            return None
        ruta_path = Path(valor)
        if not ruta_path.is_absolute():
            return None
        try:
            return ruta_path.resolve()
        except OSError:
            return None

    @staticmethod
    def _construir_url_outlook_compose(destinatario, asunto, cuerpo):
        params = {
            "to": str(destinatario or "").strip(),
            "subject": str(asunto or ""),
            "body": str(cuerpo or ""),
        }
        query = urlencode(params, quote_via=quote, safe="")
        return f"{EmailService.OUTLOOK_COMPOSE_URL}?{query}"

    @staticmethod
    def _abrir_outlook_web(destinatario, asunto, cuerpo):
        url = EmailService._construir_url_outlook_compose(destinatario, asunto, cuerpo)
        abierto = webbrowser.open(url, new=0, autoraise=True)
        if not abierto:
            raise OSError(
                "No fue posible abrir Outlook.com en el navegador predeterminado. "
                "Podés reintentar con fallback por cliente local (mailto)."
            )
        return url

    @staticmethod
    def _abrir_cliente_correo_mailto(destinatario, asunto, cuerpo):
        asunto_cod = quote(str(asunto or ""), safe="")
        cuerpo_cod = quote(str(cuerpo or ""), safe="")
        url = f"mailto:{destinatario}?subject={asunto_cod}&body={cuerpo_cod}"
        try:
            if hasattr(os, "startfile"):
                os.startfile(url)
                return url
        except OSError:
            pass

        abierto = webbrowser.open(url, new=0, autoraise=True)
        if not abierto:
            raise OSError("No fue posible abrir el cliente de correo predeterminado (mailto).")
        return url

    @staticmethod
    def _abrir_explorador_para_adjuntos(ruta_factura, ruta_resumen=None):
        ruta_factura_abs = os.path.abspath(os.path.normpath(str(ruta_factura)))
        comando_factura = f'explorer /select,"{ruta_factura_abs}"'
        subprocess.Popen(
            comando_factura,
            shell=True,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )

        if not ruta_resumen:
            return

        ruta_resumen_abs = os.path.abspath(os.path.normpath(str(ruta_resumen)))
        if os.path.exists(ruta_resumen_abs) and os.path.isfile(ruta_resumen_abs):
            comando_resumen = f'explorer /select,"{ruta_resumen_abs}"'
            subprocess.Popen(
                comando_resumen,
                shell=True,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            return

        carpeta_resumen = os.path.dirname(ruta_resumen_abs)
        if carpeta_resumen:
            subprocess.Popen(
                ["explorer", os.path.normpath(carpeta_resumen)],
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )

    @classmethod
    def preparar_y_abrir_correo_factura(
        cls,
        destinatario,
        nombre_cliente,
        emisor,
        tipo_comprobante,
        codigo_comprobante,
        importe_total,
        ruta_pdf_factura,
        ruta_pdf_resumen=None,
        usar_fallback_mailto=False,
    ):
        email = str(destinatario or "").strip()
        if not email:
            raise ValueError("El cliente no tiene e-mail cargado.")
        if not cls.validar_email_basico(email):
            raise ValueError("El e-mail del cliente no tiene un formato válido.")

        factura_path = cls._resolver_ruta_absoluta(ruta_pdf_factura)
        if factura_path is None:
            raise ValueError("La ruta del PDF de factura debe ser absoluta.")
        if not factura_path.is_file():
            raise ValueError("No se encontró el PDF de factura para adjuntar.")

        resumen_path = None
        if str(ruta_pdf_resumen or "").strip():
            resumen_path = cls._resolver_ruta_absoluta(ruta_pdf_resumen)
            if resumen_path is None:
                raise ValueError("La ruta del PDF de resumen debe ser absoluta.")

        asunto = f"{tipo_comprobante} {codigo_comprobante} - {emisor}"
        cuerpo = (
            f"Hola {nombre_cliente}.\n\n"
            f"Te enviamos la factura {tipo_comprobante} {codigo_comprobante} correspondiente.\n\n"
            f"Importe total: {importe_total}\n\n"
            "Adjuntamos también el resumen relacionado.\n\n"
            "Muchas gracias.\n\n"
            f"{emisor}"
        )

        canal = "outlook_web"
        compose_url = ""
        if usar_fallback_mailto:
            canal = "mailto"
            compose_url = cls._abrir_cliente_correo_mailto(email, asunto, cuerpo)
        else:
            compose_url = cls._abrir_outlook_web(email, asunto, cuerpo)

        cls._abrir_explorador_para_adjuntos(factura_path, resumen_path)
        return {
            "ok": True,
            "canal": canal,
            "compose_url": compose_url,
            "outlook_compose_base": cls.OUTLOOK_COMPOSE_URL,
            "ruta_factura": str(factura_path),
            "ruta_resumen": str(resumen_path) if resumen_path else "",
        }