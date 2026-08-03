import argparse
import sys
from pathlib import Path

import customtkinter as ctk

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from views.resumenes import ResumenesFrame


def main():
    parser = argparse.ArgumentParser(
        description="Abre el modal de factura emitida usando una factura ya existente (sin emitir)."
    )
    parser.add_argument("factura_id", type=int, help="ID de factura_arca existente")
    args = parser.parse_args()

    ctk.set_appearance_mode("light")
    ctk.set_default_color_theme("blue")

    app = ctk.CTk()
    app.title("Prueba local modal FACTURA EMITIDA CORRECTAMENTE")
    app.geometry("1280x760")

    frame = ResumenesFrame(app, origen_creacion="script_probar_modal_factura")
    frame.pack(fill="both", expand=True)

    def abrir_modal_prueba():
        frame._abrir_modal_factura_existente(args.factura_id)

    app.after(250, abrir_modal_prueba)
    app.mainloop()


if __name__ == "__main__":
    main()
