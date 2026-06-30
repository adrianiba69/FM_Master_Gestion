from pathlib import Path
import shutil

import PyInstaller.__main__
from PIL import Image


RAIZ = Path(__file__).resolve().parent
NOMBRE = "FM_Master_Gestion"
CARPETAS_DATOS = ("database",)
CARPETAS_ESCRITURA = ("database", "backup", "pdf", "exports", "cierres")
LOGO = RAIZ / "assets" / "logos" / "logo_fm_master.png"
ICONO = RAIZ / "assets" / "iconos" / "fm_master.ico"


def generar_icono():
    if not LOGO.is_file():
        return None

    ICONO.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(LOGO) as imagen:
        imagen = imagen.convert("RGBA")
        limite = min(imagen.width, imagen.height + 24)
        isotipo = imagen.crop((0, 0, limite, imagen.height))
        contenido = isotipo.getbbox()
        if contenido:
            isotipo = isotipo.crop(contenido)

        isotipo.thumbnail((460, 460), Image.Resampling.LANCZOS)
        lienzo = Image.new("RGBA", (512, 512), (0, 0, 0, 0))
        posicion = ((512 - isotipo.width) // 2, (512 - isotipo.height) // 2)
        lienzo.alpha_composite(isotipo, posicion)
        lienzo.save(
            ICONO,
            format="ICO",
            sizes=((16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)),
        )
    return ICONO


def construir():
    icono = generar_icono()
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

    if icono:
        argumentos.extend(("--icon", str(icono)))

    PyInstaller.__main__.run(argumentos)

    destino = RAIZ / "dist" / NOMBRE
    assets_destino = destino / "assets"
    if assets_destino.exists():
        shutil.rmtree(assets_destino)
    shutil.copytree(RAIZ / "assets", assets_destino)

    for carpeta in CARPETAS_ESCRITURA:
        salida = destino / carpeta
        salida.mkdir(parents=True, exist_ok=True)

    ejecutable = destino / f"{NOMBRE}.exe"
    if not ejecutable.is_file():
        raise FileNotFoundError(f"No se genero el ejecutable esperado: {ejecutable}")
    print(f"Ejecutable generado: {ejecutable}")


if __name__ == "__main__":
    construir()
