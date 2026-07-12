from pathlib import Path
import shutil
import subprocess


class CertificadoService:

    @staticmethod
    def _localizar_openssl():
        candidatos = []

        openssl_en_path = shutil.which("openssl")
        if openssl_en_path:
            candidatos.append(Path(openssl_en_path))

        candidatos.append(Path(r"C:\Program Files\Git\usr\bin\openssl.exe"))
        candidatos.append(Path(r"C:\Program Files\Git\mingw64\bin\openssl.exe"))

        for candidato in candidatos:
            if candidato and candidato.exists() and candidato.is_file():
                return str(candidato)

        return None

    @staticmethod
    def _ejecutar_openssl(openssl_path, argumentos, timeout=8):
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        comando = [openssl_path] + list(argumentos)
        return subprocess.run(
            comando,
            capture_output=True,
            text=True,
            timeout=timeout,
            creationflags=creationflags,
        )

    @staticmethod
    def validar_clave_privada(ruta_clave):
        resultado = {
            "valida": False,
            "errores": [],
            "openssl_disponible": False,
        }

        ruta_texto = str(ruta_clave or "").strip()
        if not ruta_texto:
            resultado["errores"].append("Ruta de clave privada no informada.")
            return resultado

        ruta = Path(ruta_texto)
        if not ruta.exists() or not ruta.is_file():
            resultado["errores"].append("El archivo de clave privada no existe.")
            return resultado

        extension = ruta.suffix.lower()
        if extension not in {".key", ".pem", ".p12", ".pfx"}:
            resultado["errores"].append("La extensión de la clave privada no es válida.")
            return resultado

        openssl_path = CertificadoService._localizar_openssl()
        if not openssl_path:
            resultado["errores"].append("OpenSSL no está disponible en el equipo.")
            return resultado

        resultado["openssl_disponible"] = True

        if extension in {".key", ".pem"}:
            comando = ["pkey", "-in", str(ruta), "-check", "-noout"]
            mensaje_ok = "Key is valid"
        else:
            comando = ["pkcs12", "-in", str(ruta), "-noout", "-info", "-passin", "pass:"]
            mensaje_ok = "MAC verified OK"

        try:
            proceso = CertificadoService._ejecutar_openssl(openssl_path, comando)
        except subprocess.TimeoutExpired:
            resultado["errores"].append("OpenSSL excedió el tiempo de validación de la clave.")
            return resultado
        except Exception:
            resultado["errores"].append("No se pudo ejecutar OpenSSL para validar la clave.")
            return resultado

        salida = (proceso.stdout or "") + "\n" + (proceso.stderr or "")
        if proceso.returncode != 0:
            resultado["errores"].append("OpenSSL no pudo validar la clave privada.")
            return resultado

        if extension in {".p12", ".pfx"} and mensaje_ok not in salida:
            resultado["errores"].append("OpenSSL no confirmó integridad del archivo PKCS12.")
            return resultado

        resultado["valida"] = True
        return resultado

    @staticmethod
    def validar_csr(ruta_csr):
        resultado = {
            "valido": False,
            "subject": "",
            "errores": [],
            "openssl_disponible": False,
        }

        ruta_texto = str(ruta_csr or "").strip()
        if not ruta_texto:
            resultado["errores"].append("Ruta de CSR no informada.")
            return resultado

        ruta = Path(ruta_texto)
        if not ruta.exists() or not ruta.is_file():
            resultado["errores"].append("El archivo CSR no existe.")
            return resultado

        if ruta.suffix.lower() != ".csr":
            resultado["errores"].append("La extensión del CSR debe ser .csr.")
            return resultado

        openssl_path = CertificadoService._localizar_openssl()
        if not openssl_path:
            resultado["errores"].append("OpenSSL no está disponible en el equipo.")
            return resultado

        resultado["openssl_disponible"] = True

        try:
            verificacion = CertificadoService._ejecutar_openssl(
                openssl_path,
                ["req", "-in", str(ruta), "-noout", "-verify"],
            )
        except subprocess.TimeoutExpired:
            resultado["errores"].append("OpenSSL excedió el tiempo de verificación del CSR.")
            return resultado
        except Exception:
            resultado["errores"].append("No se pudo ejecutar OpenSSL para verificar el CSR.")
            return resultado

        if verificacion.returncode != 0:
            resultado["errores"].append("OpenSSL no pudo verificar criptográficamente el CSR.")
            return resultado

        try:
            subject_cmd = CertificadoService._ejecutar_openssl(
                openssl_path,
                ["req", "-in", str(ruta), "-noout", "-subject"],
            )
        except subprocess.TimeoutExpired:
            resultado["errores"].append("OpenSSL excedió el tiempo de lectura del subject del CSR.")
            return resultado
        except Exception:
            resultado["errores"].append("No se pudo leer el subject del CSR con OpenSSL.")
            return resultado

        if subject_cmd.returncode != 0:
            resultado["errores"].append("OpenSSL no pudo obtener el subject del CSR.")
            return resultado

        subject = (subject_cmd.stdout or "").strip()
        if not subject:
            resultado["errores"].append("El CSR no contiene subject legible.")
            return resultado

        resultado["subject"] = subject
        resultado["valido"] = True
        return resultado

    @staticmethod
    def validar_cuit_en_csr(ruta_csr, cuit):
        resultado = {
            "valido": False,
            "subject": "",
            "errores": [],
            "openssl_disponible": False,
        }

        validacion_csr = CertificadoService.validar_csr(ruta_csr)
        resultado["openssl_disponible"] = bool(validacion_csr.get("openssl_disponible"))
        resultado["subject"] = validacion_csr.get("subject", "")

        if not validacion_csr.get("valido"):
            resultado["errores"].extend(validacion_csr.get("errores", []))
            return resultado

        cuit_texto = str(cuit or "").strip()
        cuit_normalizado = cuit_texto.replace("-", "").replace(" ", "")
        if not cuit_normalizado or not cuit_normalizado.isdigit() or len(cuit_normalizado) != 11:
            resultado["errores"].append("CUIT inválido para validación en CSR.")
            return resultado

        subject = validacion_csr.get("subject", "")
        subject_normalizado = subject.replace(" ", "")
        patron = f"serialNumber=CUIT{cuit_normalizado}"

        if patron not in subject_normalizado:
            resultado["errores"].append("El serialNumber del CSR no coincide con el CUIT informado.")
            return resultado

        resultado["valido"] = True
        return resultado
