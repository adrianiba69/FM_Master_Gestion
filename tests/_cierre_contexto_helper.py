"""Helper compartido para tests del cierre normal (Bloque 2B.2).

Construye el snapshot fiscal v1 "congelado" que el cierre normal produce y un
resultado compatible con la nueva ruta `_construir_snapshot_desde_contexto_persistido`.

Se usa en los tests de orden/etapa/post-condicion que mockean la nueva ruta para
aislar su proposito (orden cierre/PDF, etapas, post-condiciones), sin depender de
la DB. La cobertura REAL de la nueva ruta (relectura del contexto persistido,
inmutabilidad, errores, A/C) vive en test_cierre_normal_desde_contexto_2b2.py con
SQLite temporal.
"""

from decimal import Decimal

from services.arca.snapshot_fiscal_service import (
    SNAPSHOT_VERSION,
    calcular_hash_snapshot,
    construir_snapshot_fiscal_v1,
    serializar_snapshot_fiscal,
)


def construir_snapshot_cierre_para_test(
    *,
    ambiente="HOMOLOGACION",
    cuit="20206871629",
    emisor_id=40,
    emisor_fiscal_id=30,
    razon_social_emisor="FM Master SRL",
    nombre_fantasia="FM Master",
    condicion_iva_emisor="Responsable Inscripto",
    domicilio_emisor="Domicilio Fiscal 123",
    cliente_id=20,
    razon_social_cliente="Cliente Responsable SA",
    documento_visible="20222222221",
    condicion_iva_cliente="Responsable Inscripto",
    domicilio_cliente="Calle 1 - Ciudad",
    tipo_documento_receptor=80,
    documento_receptor=20222222221,
    punto_venta_num=5,
    tipo_comprobante_num=1,
    tipo_comprobante_texto="Factura A",
    numero_comprobante=123,
    fecha="2026-08-23",
    fecha_arca="20260823",
    total=Decimal("1210"),
    neto=Decimal("1000"),
    iva_importe=Decimal("210"),
    iva_lista=None,
    items=None,
    cae="12345678901234",
    vencimiento_cae="2026-09-02",
    vencimiento_cae_arca="20260902",
):
    """Construye un snapshot fiscal v1 valido y su resultado de cierre compatible."""
    if iva_lista is None:
        iva_lista = [{"id": 5, "base_imponible": neto, "importe": iva_importe, "porcentaje": Decimal("21")}]
    if items is None:
        items = [{
            "concepto": "Servicio", "descripcion": "Servicio",
            "cantidad": Decimal("1"), "precio_unitario": neto, "subtotal": neto,
        }]
    snapshot = construir_snapshot_fiscal_v1(
        fuente="cierre_normal",
        creado_en="2026-08-23T12:00:00",
        ambiente=ambiente,
        emisor={
            "emisor_id": emisor_id, "emisor_fiscal_id": emisor_fiscal_id,
            "razon_social": razon_social_emisor, "nombre_fantasia": nombre_fantasia,
            "cuit": cuit, "condicion_iva": condicion_iva_emisor,
            "domicilio": domicilio_emisor, "ingresos_brutos": "123456",
            "fecha_inicio_actividades": "2020-01-01", "punto_venta_num": punto_venta_num,
        },
        receptor={
            "cliente_id": cliente_id, "razon_social": razon_social_cliente,
            "documento_visible": documento_visible, "condicion_iva": condicion_iva_cliente,
            "domicilio": domicilio_cliente, "tipo_documento_receptor": tipo_documento_receptor,
            "documento_receptor": documento_receptor,
        },
        comprobante={
            "fecha": fecha, "fecha_arca": fecha_arca, "concepto": 1,
            "concepto_descripcion": "1 - Productos", "punto_venta_num": punto_venta_num,
            "tipo_comprobante_num": tipo_comprobante_num,
            "tipo_comprobante_texto": tipo_comprobante_texto,
            "numero_comprobante_num": numero_comprobante,
            "numero_textual": f"{punto_venta_num:05d}-{numero_comprobante:08d}",
            "periodo_servicio_desde": None, "periodo_servicio_hasta": None,
            "vencimiento_pago": None, "moneda": "PES", "cotizacion": Decimal("1"),
        },
        importes={
            "total": total, "neto": neto, "iva": iva_importe,
            "exento": Decimal("0"), "no_gravado": Decimal("0"), "tributos": Decimal("0"),
        },
        iva=iva_lista,
        items=items,
        autorizacion={
            "cae": cae, "vencimiento_cae": vencimiento_cae,
            "vencimiento_cae_arca": vencimiento_cae_arca, "tipo_cod_aut": "E",
            "resultado": "AUTORIZADO", "cerrado_en": "2026-08-23T12:00:00",
        },
    )
    json_text = serializar_snapshot_fiscal(snapshot)
    return {
        "ok": True,
        "snapshot": snapshot,
        "snapshot_json": json_text,
        "snapshot_version": SNAPSHOT_VERSION,
        "snapshot_hash": calcular_hash_snapshot(json_text),
    }


def resultado_snapshot_cierre_para_test(**kwargs):
    """Alias semantico: resultado de la nueva ruta _construir_snapshot_desde_contexto_persistido."""
    return construir_snapshot_cierre_para_test(**kwargs)
