import re

from database import conectar


def sanitizar_nombre_archivo(texto):
    valor = str(texto or "").strip()
    if not valor:
        return ""
    valor = re.sub(r'[\\/:*?"<>|]+', "_", valor)
    valor = re.sub(r"\s+", "_", valor)
    valor = re.sub(r"_+", "_", valor)
    return valor.strip("_")


def nombre_cliente_archivo(cliente_id):
    try:
        cliente_id = int(cliente_id)
    except (TypeError, ValueError):
        return "Cliente"

    conn = conectar()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT
            id,
            COALESCE(NULLIF(razon_social, ''), ''),
            COALESCE(NULLIF(nombre_comercial, ''), '')
        FROM clientes
        WHERE id=?
        """,
        (cliente_id,),
    )
    fila = cur.fetchone()
    conn.close()

    if not fila:
        return f"Cliente_{cliente_id}"

    razon_social = str(fila[1] or "").strip()
    nombre_comercial = str(fila[2] or "").strip()
    base = razon_social or nombre_comercial or f"Cliente_{fila[0]}"
    nombre = sanitizar_nombre_archivo(base)
    return nombre or f"Cliente_{fila[0]}"


def nombre_factura_pdf(cliente_id, tipo_factura, codigo_factura):
    cliente = nombre_cliente_archivo(cliente_id)
    tipo = sanitizar_nombre_archivo(tipo_factura or "Factura") or "Factura"
    codigo = str(codigo_factura or "").strip()
    return f"{cliente}_{tipo}_{codigo}.pdf"


def nombre_resumen_pdf(cliente_id, numero_resumen):
    cliente = nombre_cliente_archivo(cliente_id)
    try:
        numero_texto = str(int(numero_resumen))
    except (TypeError, ValueError):
        numero_texto = str(numero_resumen or "").strip()
    return f"{cliente}_Resumen_{numero_texto}.pdf"