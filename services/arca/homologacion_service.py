from pathlib import Path

from services.arca.wsaa_login_service import WSAALoginService
from services.arca.wsaa_service import WSAAService
from services.arca.wsfe_service import WSFEService


class HomologacionService:

    @staticmethod
    def consultar_ultimo_comprobante(
        ruta_certificado,
        ruta_clave,
        cuit,
        punto_venta,
        tipo_comprobante,
        carpeta_trabajo,
    ):
        resultado = {
            "ok": False,
            "ultimo_numero": 0,
            "punto_venta": punto_venta,
            "tipo_comprobante": tipo_comprobante,
            "expiration": "",
            "errores": [],
        }

        carpeta_texto = str(carpeta_trabajo or "").strip()
        if not carpeta_texto:
            resultado["errores"].append("Carpeta de trabajo no informada.")
            return resultado

        ruta_tra = WSAAService.guardar_tra(
            Path(carpeta_texto) / "tra_wsfe.xml",
            servicio="wsfe",
            duracion_segundos=3600,
        )

        login = WSAALoginService.login_homologacion(
            ruta_tra=ruta_tra,
            ruta_certificado=ruta_certificado,
            ruta_clave=ruta_clave,
        )

        if not login.get("ok"):
            resultado["errores"].extend(login.get("errores") or ["No se pudo autenticar en WSAA."])
            if login.get("faultcode"):
                resultado["errores"].append(f"WSAA faultcode: {login.get('faultcode')}")
            if login.get("faultstring"):
                resultado["errores"].append(f"WSAA faultstring: {login.get('faultstring')}")
            return resultado

        consulta = WSFEService.fe_comp_ultimo_autorizado(
            token=login.get("token", ""),
            sign=login.get("sign", ""),
            cuit=cuit,
            punto_venta=punto_venta,
            tipo_comprobante=tipo_comprobante,
        )

        resultado["ok"] = bool(consulta.get("ok"))
        resultado["ultimo_numero"] = int(consulta.get("ultimo_numero") or 0)
        resultado["expiration"] = login.get("expiration", "")
        if not resultado["ok"]:
            resultado["errores"].extend(consulta.get("errores") or ["No se pudo consultar el último comprobante."])
        return resultado
