import os
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

from runtime_paths import APP_DIR


class PDFService:
    MANUALES_DIR = APP_DIR / "manuales"

    @classmethod
    def exportar_manual(cls, ruta=None):
        cls.MANUALES_DIR.mkdir(parents=True, exist_ok=True)
        destino = Path(ruta) if ruta else cls.MANUALES_DIR / "manual_fm_master_gestion.pdf"
        documento = SimpleDocTemplate(
            str(destino),
            pagesize=A4,
            title="Manual FM Master Gestión",
            leftMargin=20 * mm,
            rightMargin=20 * mm,
            topMargin=20 * mm,
            bottomMargin=20 * mm,
        )
        estilos = getSampleStyleSheet()
        titulo = ParagraphStyle(
            "Titulo",
            parent=estilos["Title"],
            fontSize=18,
            leading=22,
            textColor=colors.HexColor("#C00000"),
            spaceAfter=10,
        )
        encabezado = ParagraphStyle(
            "Encabezado",
            parent=estilos["Heading2"],
            fontSize=13,
            leading=16,
            textColor=colors.HexColor("#333333"),
            spaceAfter=4,
        )
        cuerpo = ParagraphStyle(
            "Cuerpo",
            parent=estilos["BodyText"],
            fontSize=11,
            leading=14,
            spaceAfter=8,
        )

        contenido = [Paragraph("Manual FM Master Gestión", titulo), Spacer(1, 6 * mm)]
        secciones = [
            (
                "1. Cómo cargar un cliente",
                "Abra la sección Clientes, haga clic en Nuevo Cliente, complete los campos obligatorios y guarde.",
            ),
            (
                "2. Cómo cargar servicios",
                "Desde Clientes o Servicios, agregue un servicio con concepto, fecha de inicio, fecha de fin y estado. Guarde el servicio para que se vincule al cliente.",
            ),
            (
                "3. Cómo generar un resumen",
                "Vaya a Resúmenes, seleccione el cliente o los servicios correspondientes y genere el resumen. Verifique los datos antes de guardar.",
            ),
            (
                "4. Cómo registrar un cobro",
                "Abra Cobros, elija el cliente o resumen, ingrese el importe, la fecha y confirme el registro del cobro.",
            ),
            (
                "5. Cómo usar cuenta corriente",
                "Revise los movimientos de cada cliente en Cuenta Corriente y consulte saldo, resúmenes pendientes y pagos registrados.",
            ),
            (
                "6. Cómo hacer backup",
                "En Configuración, utilice Crear backup ahora. El sistema también realiza copias automáticas diarias.",
            ),
            (
                "7. Cómo usar WhatsApp",
                "Desde el cliente o el resumen, utilice el botón de WhatsApp para enviar información de manera rápida y directa.",
            ),
            (
                "8. Cómo hacer cierre mensual",
                "Acceda a Cierre del Mes, siga los pasos de análisis, generación de resúmenes y respaldo para completar el cierre.",
            ),
            (
                "9. Cómo usar oportunidades",
                "Abra Oportunidades, cree nuevos registros, establezca fechas de seguimiento y actualice el estado a medida que avance el proceso.",
            ),
            (
                "10. Cómo usar notificaciones",
                "Abra Notificaciones para ver alertas automáticas de servicios, cobros, contactos, backups y oportunidades que requieren atención.",
            ),
        ]

        for titulo_seccion, texto in secciones:
            contenido.append(Paragraph(titulo_seccion, encabezado))
            contenido.append(Paragraph(texto, cuerpo))
            contenido.append(Spacer(1, 2 * mm))

        documento.build(contenido)
        return str(destino.resolve())

    @classmethod
    def abrir_manuales(cls):
        cls.MANUALES_DIR.mkdir(parents=True, exist_ok=True)
        try:
            os.startfile(str(cls.MANUALES_DIR.resolve()))
        except (AttributeError, OSError) as error:
            raise OSError("No se pudo abrir la carpeta de manuales.") from error
