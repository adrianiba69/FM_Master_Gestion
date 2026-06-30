import customtkinter as ctk
from tkinter import messagebox

from services.pdf_service import PDFService


class AyudaFrame(ctk.CTkFrame):
    def __init__(self, master):
        super().__init__(master, fg_color="white", corner_radius=0)
        self._crear_interfaz()

    def _crear_interfaz(self):
        self.grid_rowconfigure(2, weight=1)
        self.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            self,
            text="AYUDA",
            font=("Arial", 26, "bold"),
            text_color="#C00000",
        ).grid(row=0, column=0, sticky="w", padx=20, pady=(20, 10))

        acciones = ctk.CTkFrame(self, fg_color="white")
        acciones.grid(row=1, column=0, sticky="ew", padx=20)
        acciones.grid_columnconfigure((0, 1), weight=1)

        ctk.CTkButton(
            acciones,
            text="Abrir carpeta de manuales",
            width=210,
            fg_color="#333333",
            hover_color="#111111",
            command=self.abrir_carpeta_manual,
        ).grid(row=0, column=0, sticky="w", padx=(0, 8), pady=(0, 10))

        ctk.CTkButton(
            acciones,
            text="Exportar manual en PDF",
            width=210,
            fg_color="#C00000",
            hover_color="#990000",
            command=self.exportar_manual_pdf,
        ).grid(row=0, column=1, sticky="w", pady=(0, 10))

        contenido = ctk.CTkScrollableFrame(self, fg_color="white")
        contenido.grid(row=2, column=0, sticky="nsew", padx=20, pady=(0, 20))
        contenido.grid_columnconfigure(0, weight=1)

        secciones = [
            (
                "1. Cómo cargar un cliente",
                "Abra Clientes, haga clic en Nuevo Cliente, complete los datos y guarde.",
            ),
            (
                "2. Cómo cargar servicios",
                "Desde Clientes o Servicios, agregue un servicio con concepto, fechas y estado, luego guarde.",
            ),
            (
                "3. Cómo generar un resumen",
                "Vaya a Resúmenes, seleccione el cliente o servicios y genere el resumen revisando los datos antes de guardar.",
            ),
            (
                "4. Cómo registrar un cobro",
                "Abra Cobros, seleccione el cliente o resumen, ingrese importe y fecha, y confirme el cobro.",
            ),
            (
                "5. Cómo usar cuenta corriente",
                "Consulte saldos, movimientos y resúmenes pendientes para cada cliente dentro de la cuenta corriente.",
            ),
            (
                "6. Cómo hacer backup",
                "En Configuración, utilice Crear backup ahora. El sistema también ejecuta backups automáticos diarios.",
            ),
            (
                "7. Cómo usar WhatsApp",
                "Use la función de WhatsApp desde el cliente o el resumen para enviar información directamente al contactado.",
            ),
            (
                "8. Cómo hacer cierre mensual",
                "Abra Cierre del Mes y siga los pasos de análisis, generación de resúmenes y respaldo para cerrar el mes.",
            ),
            (
                "9. Cómo usar oportunidades",
                "Abra Oportunidades, cree registros nuevos, programe seguimientos y actualice el estado de cada oportunidad.",
            ),
            (
                "10. Cómo usar notificaciones",
                "Abra Notificaciones para revisar alertas automáticas de servicios, cobros, contactos, backups y oportunidades.",
            ),
        ]

        for indice, (titulo, descripcion) in enumerate(secciones):
            ctk.CTkLabel(
                contenido,
                text=titulo,
                font=("Arial", 13, "bold"),
                text_color="#222222",
                anchor="w",
                justify="left",
            ).grid(row=indice * 2, column=0, sticky="w", pady=(10, 2), padx=10)
            ctk.CTkLabel(
                contenido,
                text=descripcion,
                font=("Arial", 11),
                text_color="#444444",
                wraplength=1000,
                justify="left",
                anchor="w",
            ).grid(row=indice * 2 + 1, column=0, sticky="w", padx=10)

    def abrir_carpeta_manual(self):
        try:
            PDFService.abrir_manuales()
        except OSError as error:
            messagebox.showerror("Ayuda", str(error), parent=self)

    def exportar_manual_pdf(self):
        try:
            ruta = PDFService.exportar_manual()
        except Exception as error:
            messagebox.showerror("Ayuda", f"No se pudo exportar el manual.\n{error}", parent=self)
            return
        messagebox.showinfo("Ayuda", f"Manual exportado correctamente.\n{ruta}", parent=self)
