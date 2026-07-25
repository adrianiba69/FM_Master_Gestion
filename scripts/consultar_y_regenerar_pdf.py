#!/usr/bin/env python3
"""
Prueba local para generar un PDF fiscal sin consultar ARCA ni emitir comprobantes.
Usa exclusivamente datos almacenados en la base local.
"""

import sys
from datetime import datetime
from pathlib import Path

from database import conectar
from pdf.nombre_archivos import nombre_factura_pdf
from services.arca.pdf_fiscal_service import PDFFiscalService


def consultar_y_regenerar():
    print("\n" + "="*70)
    print("GENERAR PDF FISCAL LOCAL (SIN ARCA)")
    print("="*70)

    try:
        conn = conectar()
        conn.row_factory = None
        cur = conn.cursor()
    except Exception as e:
        print(f"ERROR: No se pudo conectar a la BD: {e}")
        return False

    emisor = None
    try:
        # Buscar estrictamente el emisor fiscal solicitado: FM Master 98.3 (normalizando puntos/espacios)
        etiqueta_objetivo = "FM Master 98.3"
        cur.execute(
            """
            SELECT
                id,
                razon_social,
                nombre_fantasia,
                cuit,
                condicion_iva,
                punto_venta,
                domicilio,
                carpeta_facturas
            FROM emisores_fiscales
            WHERE LOWER(REPLACE(REPLACE(COALESCE(nombre_fantasia, ''), '.', ''), ' ', '')) =
                  LOWER(REPLACE(REPLACE(?, '.', ''), ' ', ''))
               OR LOWER(REPLACE(REPLACE(COALESCE(razon_social, ''), '.', ''), ' ', '')) =
                  LOWER(REPLACE(REPLACE(?, '.', ''), ' ', ''))
            ORDER BY id
            LIMIT 1
            """,
            (etiqueta_objetivo, etiqueta_objetivo),
        )
        emisor = cur.fetchone()

        if not emisor:
            cur.execute(
                "SELECT id, razon_social, nombre_fantasia FROM emisores_fiscales ORDER BY id"
            )
            disponibles = cur.fetchall()
            print("ERROR: No se encontró emisor fiscal FM Master 98.3 en la base local.")
            print(f"Emisores disponibles: {disponibles}")
            return False

        emisor_id = int(emisor[0] or 0)
        emisor_razon = str(emisor[1] or "").strip()
        emisor_fantasia = str(emisor[2] or "").strip()
        cuit_emisor = str(emisor[3] or "").strip().replace("-", "")
        emisor_iva = str(emisor[4] or "").strip()
        punto_venta = int(str(emisor[5] or "0").strip() or 0)
        emisor_domicilio = str(emisor[6] or "").strip()
        carpeta_facturas = str(emisor[7] or "").strip()

        print("\nOrigen del domicilio del emisor:")
        print("  Tabla: emisores_fiscales")
        print("  Campo: domicilio")
        print(f"  Emisor ID: {emisor_id}")
        print(f"  Emisor: {emisor_fantasia or emisor_razon}")
        print(f"  Valor actual en BD: {repr(emisor_domicilio)}")

        # Receptor de prueba local: cliente conocido si existe, sin dependencias externas.
        cur.execute(
            """
            SELECT id, nombre, cuit, iva, direccion
            FROM clientes
            WHERE nombre LIKE '%IBARRONDO%'
            ORDER BY id DESC
            LIMIT 1
            """
        )
        cliente = cur.fetchone()
        if cliente:
            receptor_razon = str(cliente[1] or "").strip() or "IBARRONDO LOLA"
            receptor_documento = str(cliente[2] or "").strip() or "50265343"
            receptor_iva = str(cliente[3] or "").strip() or "Consumidor Final"
            receptor_domicilio = str(cliente[4] or "").strip()
        else:
            cliente = (0,)
            receptor_razon = "IBARRONDO LOLA"
            receptor_documento = "50265343"
            receptor_iva = "Consumidor Final"
            receptor_domicilio = ""
    except Exception as e:
        print(f"ERROR: No se pudieron obtener datos locales para la prueba: {e}")
        return False
    finally:
        conn.close()

    print(f"\nDatos del emisor local:")
    print(f"  CUIT: {cuit_emisor}")
    print(f"  Punto de Venta: {punto_venta}")

    datos_emisor = {
        "cuit": cuit_emisor,
        "razon_social": emisor_razon,
        "nombre_fantasia": emisor_fantasia,
        "condicion_iva": emisor_iva,
        # Sin fallback fijo: se usa el valor exacto almacenado en BD.
        "domicilio": emisor_domicilio,
        "punto_venta": punto_venta,
    }

    datos_receptor = {
        "nombre": receptor_razon,
        "cuit": receptor_documento,
        "condicion_iva": receptor_iva,
        "domicilio": receptor_domicilio,
    }

    hoy = datetime.now().strftime("%Y%m%d")
    numero_prueba = 6
    datos_pdf_comprobante = {
        "tipo": "Factura C",
        "numero": numero_prueba,
        "punto_venta": punto_venta,
        "fecha": hoy,
        "numero_comprobante": numero_prueba,
        "concepto": "Servicios",
        "periodo_servicio_desde": hoy,
        "periodo_servicio_hasta": hoy,
        "vencimiento_pago": hoy,
        "moneda": "PES",
        "importe_total": 50000.0,
        "cae": "00000000000000",
        "cae_vencimiento": hoy,
        "ambiente": "HOMOLOGACION",
    }

    carpeta_destino = Path(carpeta_facturas) if carpeta_facturas else (Path("pdf") / "resumenes" / "2026-07")
    carpeta_destino.mkdir(parents=True, exist_ok=True)

    codigo_factura = f"{punto_venta:05d}-{numero_prueba:08d}"
    nombre_pdf = nombre_factura_pdf(cliente[0] if cliente else 0, "Factura C", codigo_factura)
    ruta_pdf = str(carpeta_destino / nombre_pdf)

    print(f"\nGenerando PDF local (sin ARCA)...")
    print(f"  Ruta destino: {ruta_pdf}")

    resultado_pdf = PDFFiscalService.generar_factura_c(
        ruta_destino=ruta_pdf,
        datos_emisor=datos_emisor,
        datos_receptor=datos_receptor,
        datos_comprobante=datos_pdf_comprobante,
    )

    if not resultado_pdf.get("ok"):
        print(f"❌ Error al generar PDF: {', '.join(resultado_pdf.get('errores', ['Error desconocido']))}")
        return False

    print("✓ PDF local generado exitosamente")
    print(f"  Ruta final: {resultado_pdf.get('ruta_pdf')}")
    print("\nValidación aplicada:")
    print("  - No se emitieron comprobantes")
    print("  - No se consultó ARCA")
    print("  - Domicilio del emisor tomado desde emisores_fiscales.domicilio")

    return True


if __name__ == "__main__":
    try:
        exito = consultar_y_regenerar()
        sys.exit(0 if exito else 1)
    except Exception as e:
        print(f"ERROR FATAL: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
