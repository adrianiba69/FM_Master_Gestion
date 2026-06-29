import shutil
from pathlib import Path

import PyInstaller.__main__


RAIZ = Path(__file__).resolve().parent
NOMBRE = "FM_Master_Gestion"
CARPETAS_DATOS = ("assets", "database", "backup", "pdf", "exports")
CARPETAS_ESCRITURA = ("database", "backup", "pdf", "exports")


def buscar_icono():
    return next((ruta for ruta in (RAIZ / "assets").rglob("*.ico")), None)


def construir():
    argumentos = [
        str(RAIZ / "main.py"),
        "--name",
        NOMBRE,
        "--noconfirm",
        "--clean",
        "--windowed",
        "--onedir",
        "--distpath",
        str(RAIZ / "dist"),
        "--workpath",
        str(RAIZ / "build"),
        "--specpath",
        str(RAIZ),
        "--collect-all",
        "customtkinter",
    ]

    for carpeta in CARPETAS_DATOS:
        ruta = RAIZ / carpeta
        ruta.mkdir(parents=True, exist_ok=True)
        argumentos.extend(("--add-data", f"{ruta};{carpeta}"))

    icono = buscar_icono()
    if icono:
        argumentos.extend(("--icon", str(icono)))

    PyInstaller.__main__.run(argumentos)

    destino = RAIZ / "dist" / NOMBRE
    for carpeta in CARPETAS_ESCRITURA:
        origen = RAIZ / carpeta
        salida = destino / carpeta
        if salida.exists():
            shutil.rmtree(salida)
        shutil.copytree(origen, salida)

    ejecutable = destino / f"{NOMBRE}.exe"
    if not ejecutable.is_file():
        raise FileNotFoundError(f"No se genero el ejecutable esperado: {ejecutable}")
    print(f"Ejecutable generado: {ejecutable}")


if __name__ == "__main__":
    construir()
