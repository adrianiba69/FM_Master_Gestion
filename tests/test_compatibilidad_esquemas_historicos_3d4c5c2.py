"""Etapa 3D.4C.5C.2: reconocimiento de esquemas históricos SQLite.

Registra la clasificación OBSERVADA del detector actual
(``database.inspeccionar_estado_base_sqlite``) sobre bases ficticias creadas en
directorios temporales. Cada caso separa tres dimensiones:

* ``estado_observado``: lo que devuelve hoy el detector (fijado para detectar
  cambios de comportamiento; no implica que sea el comportamiento deseado).
* ``compatibilidad``: lo que demuestra el historial Git sobre el origen del
  esquema (``LEGITIMA_DEMOSTRADA`` solo si el DDL fue producido por un
  ``crear_base()`` histórico).
* ``politica_futura``: siempre ``NO_APROBADA``. Ningún estado observado,
  incluido ``HISTORICA_SIN_VERSION``, se traduce aquí en autorización.

Los esquemas históricos están congelados como DDL literal. Se obtuvieron fuera
de esta prueba ejecutando ``crear_base()`` de ``git show <commit>:database.py``
sobre bases ficticias temporales y volcando ``sqlite_master`` (orden rowid).
No se derivan del catálogo del detector.

Esta prueba no ejecuta ``crear_base()`` ni migraciones sobre las bases
inspeccionadas; las inspecciones usan ``mode=ro`` con guardas que fallan ante
cualquier intento de conexión nueva, migración o sentencia de escritura.
"""

import hashlib
import importlib.util
import os
import re
import sqlite3
import sys
import tempfile
import unittest
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from unittest.mock import patch


def _cargar_database_aislado():
    """Carga database.py con runtime_paths falso para evitar preparar rutas reales."""
    nombre_modulo = "_database_compatibilidad_historica_3d4c5c2_test"
    ruta_database = Path(__file__).resolve().parents[1] / "database.py"
    spec = importlib.util.spec_from_file_location(nombre_modulo, ruta_database)
    modulo = importlib.util.module_from_spec(spec)
    runtime_paths_falso = ModuleType("runtime_paths")
    runtime_paths_falso.DATABASE_PATH = Path(":memory:")
    sys.modules[nombre_modulo] = modulo
    try:
        with patch.dict(sys.modules, {"runtime_paths": runtime_paths_falso}):
            spec.loader.exec_module(modulo)
    except Exception:
        sys.modules.pop(nombre_modulo, None)
        raise
    return modulo


database = _cargar_database_aislado()


# DDL congelado: nombre -> (commit, descripción, ((tipo, nombre, tabla, sql), ...)).
ESQUEMAS_HISTORICOS = {
    'build_0_2_2_9b6a850': (
        '9b6a850',
        'Build 0.2.2 - Base del proyecto',
        (
            ('table', 'clientes', 'clientes',
             'CREATE TABLE clientes(\n\n        id INTEGER PRIMARY KEY AUTOINCREMENT,\n        codigo TEXT,\n        razon_social TEXT,\n        responsable TEXT,\n        direccion TEXT,\n        localidad TEXT,\n        telefono TEXT,\n        whatsapp TEXT,\n        email TEXT,\n        cuit TEXT,\n        iva TEXT,\n        servicio TEXT,\n        importe REAL,\n        descuento REAL,\n        vencimiento INTEGER,\n        estado TEXT,\n        observaciones TEXT,\n        fecha_alta TEXT\n\n    )'),
        ),
    ),
    'build_0_5_52b0189': (
        '52b0189',
        'Build 0.5 - Clientes y Servicios',
        (
            ('table', 'clientes', 'clientes',
             'CREATE TABLE clientes(\n\n        id INTEGER PRIMARY KEY AUTOINCREMENT,\n        codigo TEXT,\n        razon_social TEXT,\n        nombre_comercial TEXT,\n        responsable TEXT,\n        direccion TEXT,\n        localidad TEXT,\n        telefono TEXT,\n        whatsapp TEXT,\n        email TEXT,\n        cuit TEXT,\n        iva TEXT,\n        vencimiento INTEGER,\n        estado TEXT,\n        observaciones TEXT,\n        fecha_alta TEXT,\n        fecha_modificacion TEXT\n\n    )'),
            ('table', 'servicios', 'servicios',
             'CREATE TABLE servicios(\n\n        id INTEGER PRIMARY KEY AUTOINCREMENT,\n        cliente_id INTEGER NOT NULL,\n        concepto TEXT NOT NULL,\n        descripcion TEXT,\n        cantidad INTEGER DEFAULT 1,\n        importe REAL NOT NULL,\n        descuento REAL DEFAULT 0,\n        activo INTEGER DEFAULT 1,\n\n        FOREIGN KEY(cliente_id)\n        REFERENCES clientes(id)\n\n    )'),
        ),
    ),
    'build_0_7_8c81526': (
        '8c81526',
        'Build 0.7 estable - Clientes, Servicios, Resúmenes y Cobros',
        (
            ('table', 'clientes', 'clientes',
             'CREATE TABLE clientes(\n\n        id INTEGER PRIMARY KEY AUTOINCREMENT,\n        codigo TEXT,\n        razon_social TEXT,\n        nombre_comercial TEXT,\n        responsable TEXT,\n        direccion TEXT,\n        localidad TEXT,\n        telefono TEXT,\n        whatsapp TEXT,\n        email TEXT,\n        cuit TEXT,\n        iva TEXT,\n        vencimiento INTEGER,\n        estado TEXT,\n        observaciones TEXT,\n        fecha_alta TEXT,\n        fecha_modificacion TEXT\n\n    )'),
            ('table', 'servicios', 'servicios',
             'CREATE TABLE servicios(\n\n        id INTEGER PRIMARY KEY AUTOINCREMENT,\n        cliente_id INTEGER NOT NULL,\n        concepto TEXT NOT NULL,\n        descripcion TEXT,\n        cantidad INTEGER DEFAULT 1,\n        importe REAL NOT NULL,\n        descuento REAL DEFAULT 0,\n        activo INTEGER DEFAULT 1,\n\n        FOREIGN KEY(cliente_id)\n        REFERENCES clientes(id)\n\n    )'),
            ('table', 'resumenes', 'resumenes',
             "CREATE TABLE resumenes(\n\n        id INTEGER PRIMARY KEY AUTOINCREMENT,\n        numero INTEGER NOT NULL UNIQUE,\n        cliente_id INTEGER NOT NULL,\n        fecha TEXT NOT NULL,\n        fecha_vencimiento TEXT NOT NULL,\n        total REAL NOT NULL DEFAULT 0,\n        saldo REAL NOT NULL DEFAULT 0,\n        estado TEXT NOT NULL DEFAULT 'Pendiente',\n        pdf_path TEXT,\n        fecha_creacion TEXT,\n\n        FOREIGN KEY(cliente_id)\n        REFERENCES clientes(id)\n\n    )"),
            ('table', 'resumen_conceptos', 'resumen_conceptos',
             'CREATE TABLE resumen_conceptos(\n\n        id INTEGER PRIMARY KEY AUTOINCREMENT,\n        resumen_id INTEGER NOT NULL,\n        servicio_id INTEGER,\n        concepto TEXT NOT NULL,\n        descripcion TEXT,\n        cantidad REAL NOT NULL DEFAULT 1,\n        importe REAL NOT NULL DEFAULT 0,\n        descuento REAL NOT NULL DEFAULT 0,\n        total REAL NOT NULL DEFAULT 0,\n\n        FOREIGN KEY(resumen_id)\n        REFERENCES resumenes(id) ON DELETE CASCADE,\n        FOREIGN KEY(servicio_id)\n        REFERENCES servicios(id)\n\n    )'),
            ('index', 'idx_resumenes_cliente', 'resumenes',
             'CREATE INDEX idx_resumenes_cliente ON resumenes(cliente_id)'),
            ('index', 'idx_resumen_conceptos_resumen', 'resumen_conceptos',
             'CREATE INDEX idx_resumen_conceptos_resumen ON resumen_conceptos(resumen_id)'),
            ('table', 'cobros', 'cobros',
             'CREATE TABLE cobros(\n\n        id INTEGER PRIMARY KEY AUTOINCREMENT,\n        cliente_id INTEGER NOT NULL,\n        fecha TEXT NOT NULL,\n        importe REAL NOT NULL DEFAULT 0,\n        forma_pago TEXT,\n        comprobante TEXT,\n        observaciones TEXT,\n\n        FOREIGN KEY(cliente_id)\n        REFERENCES clientes(id)\n\n    )'),
            ('index', 'idx_cobros_cliente', 'cobros',
             'CREATE INDEX idx_cobros_cliente ON cobros(cliente_id)'),
            ('index', 'idx_cobros_fecha', 'cobros',
             'CREATE INDEX idx_cobros_fecha ON cobros(fecha)'),
        ),
    ),
    'build_1_7_4994dc6': (
        '4994dc6',
        'Build 1.7 - Ejecutable Windows funcionando',
        (
            ('table', 'clientes', 'clientes',
             'CREATE TABLE clientes(\n\n        id INTEGER PRIMARY KEY AUTOINCREMENT,\n        codigo TEXT,\n        razon_social TEXT,\n        nombre_comercial TEXT,\n        responsable TEXT,\n        direccion TEXT,\n        localidad TEXT,\n        telefono TEXT,\n        whatsapp TEXT,\n        email TEXT,\n        cuit TEXT,\n        iva TEXT,\n        vencimiento INTEGER,\n        estado TEXT,\n        observaciones TEXT,\n        fecha_alta TEXT,\n        fecha_modificacion TEXT\n\n    )'),
            ('table', 'servicios', 'servicios',
             "CREATE TABLE servicios(\n\n        id INTEGER PRIMARY KEY AUTOINCREMENT,\n        cliente_id INTEGER NOT NULL,\n        concepto TEXT NOT NULL,\n        descripcion TEXT,\n        cantidad INTEGER DEFAULT 1,\n        importe REAL NOT NULL,\n        descuento REAL DEFAULT 0,\n        activo INTEGER DEFAULT 1,\n        fecha_inicio TEXT,\n        fecha_fin TEXT,\n        renovable INTEGER DEFAULT 1,\n        estado_periodo TEXT DEFAULT 'Activo',\n\n        FOREIGN KEY(cliente_id)\n        REFERENCES clientes(id)\n\n    )"),
            ('table', 'servicio_renovaciones', 'servicio_renovaciones',
             'CREATE TABLE servicio_renovaciones(\n\n        id INTEGER PRIMARY KEY AUTOINCREMENT,\n        servicio_id INTEGER NOT NULL,\n        cliente_id INTEGER NOT NULL,\n        fecha_renovacion TEXT NOT NULL,\n        fecha_inicio_anterior TEXT NOT NULL,\n        fecha_fin_anterior TEXT NOT NULL,\n        fecha_inicio_nueva TEXT NOT NULL,\n        fecha_fin_nueva TEXT NOT NULL,\n        concepto TEXT,\n        descripcion TEXT,\n        cantidad REAL DEFAULT 1,\n        importe REAL DEFAULT 0,\n        descuento REAL DEFAULT 0,\n        resumen_id INTEGER,\n\n        FOREIGN KEY(servicio_id) REFERENCES servicios(id),\n        FOREIGN KEY(cliente_id) REFERENCES clientes(id),\n        FOREIGN KEY(resumen_id) REFERENCES resumenes(id)\n\n    )'),
            ('index', 'idx_renovaciones_servicio', 'servicio_renovaciones',
             'CREATE INDEX idx_renovaciones_servicio ON servicio_renovaciones(servicio_id, fecha_renovacion)'),
            ('index', 'idx_renovaciones_resumen', 'servicio_renovaciones',
             'CREATE INDEX idx_renovaciones_resumen ON servicio_renovaciones(resumen_id)'),
            ('table', 'resumenes', 'resumenes',
             "CREATE TABLE resumenes(\n\n        id INTEGER PRIMARY KEY AUTOINCREMENT,\n        numero INTEGER NOT NULL UNIQUE,\n        cliente_id INTEGER NOT NULL,\n        fecha TEXT NOT NULL,\n        fecha_vencimiento TEXT NOT NULL,\n        total REAL NOT NULL DEFAULT 0,\n        saldo REAL NOT NULL DEFAULT 0,\n        estado TEXT NOT NULL DEFAULT 'Pendiente',\n        pdf_path TEXT,\n        fecha_creacion TEXT,\n\n        FOREIGN KEY(cliente_id)\n        REFERENCES clientes(id)\n\n    )"),
            ('table', 'resumen_conceptos', 'resumen_conceptos',
             'CREATE TABLE resumen_conceptos(\n\n        id INTEGER PRIMARY KEY AUTOINCREMENT,\n        resumen_id INTEGER NOT NULL,\n        servicio_id INTEGER,\n        concepto TEXT NOT NULL,\n        descripcion TEXT,\n        cantidad REAL NOT NULL DEFAULT 1,\n        importe REAL NOT NULL DEFAULT 0,\n        descuento REAL NOT NULL DEFAULT 0,\n        total REAL NOT NULL DEFAULT 0,\n        fecha_inicio TEXT,\n        fecha_fin TEXT,\n\n        FOREIGN KEY(resumen_id)\n        REFERENCES resumenes(id) ON DELETE CASCADE,\n        FOREIGN KEY(servicio_id)\n        REFERENCES servicios(id)\n\n    )'),
            ('index', 'idx_resumenes_cliente', 'resumenes',
             'CREATE INDEX idx_resumenes_cliente ON resumenes(cliente_id)'),
            ('index', 'idx_resumen_conceptos_resumen', 'resumen_conceptos',
             'CREATE INDEX idx_resumen_conceptos_resumen ON resumen_conceptos(resumen_id)'),
            ('index', 'idx_resumen_conceptos_periodo', 'resumen_conceptos',
             'CREATE INDEX idx_resumen_conceptos_periodo ON resumen_conceptos(servicio_id, fecha_inicio, fecha_fin)'),
            ('table', 'cobros', 'cobros',
             'CREATE TABLE cobros(\n\n        id INTEGER PRIMARY KEY AUTOINCREMENT,\n        cliente_id INTEGER NOT NULL,\n        fecha TEXT NOT NULL,\n        importe REAL NOT NULL DEFAULT 0,\n        forma_pago TEXT,\n        comprobante TEXT,\n        observaciones TEXT,\n\n        FOREIGN KEY(cliente_id)\n        REFERENCES clientes(id)\n\n    )'),
            ('index', 'idx_cobros_cliente', 'cobros',
             'CREATE INDEX idx_cobros_cliente ON cobros(cliente_id)'),
            ('index', 'idx_cobros_fecha', 'cobros',
             'CREATE INDEX idx_cobros_fecha ON cobros(fecha)'),
            ('table', 'tareas', 'tareas',
             "CREATE TABLE tareas(\n\n        id INTEGER PRIMARY KEY AUTOINCREMENT,\n        cliente_id INTEGER,\n        fecha TEXT NOT NULL,\n        hora TEXT NOT NULL,\n        tipo TEXT NOT NULL,\n        titulo TEXT NOT NULL,\n        descripcion TEXT,\n        estado TEXT NOT NULL DEFAULT 'Pendiente',\n        prioridad TEXT NOT NULL DEFAULT 'Media',\n        fecha_creacion TEXT,\n\n        FOREIGN KEY(cliente_id) REFERENCES clientes(id)\n\n    )"),
            ('index', 'idx_tareas_fecha', 'tareas',
             'CREATE INDEX idx_tareas_fecha ON tareas(fecha, hora)'),
            ('index', 'idx_tareas_cliente', 'tareas',
             'CREATE INDEX idx_tareas_cliente ON tareas(cliente_id)'),
            ('index', 'idx_tareas_estado', 'tareas',
             'CREATE INDEX idx_tareas_estado ON tareas(estado)'),
        ),
    ),
    'esenciales_16_8a362a5': (
        '8a362a5',
        'Agrega configuracion tecnica ARCA por emisor fiscal (16 tablas esenciales)',
        (
            ('table', 'clientes', 'clientes',
             "CREATE TABLE clientes(\n\n        id INTEGER PRIMARY KEY AUTOINCREMENT,\n        nombre TEXT NOT NULL DEFAULT '',\n        codigo TEXT,\n        razon_social TEXT,\n        nombre_comercial TEXT,\n        responsable TEXT,\n        direccion TEXT,\n        localidad TEXT,\n        telefono TEXT,\n        whatsapp TEXT,\n        email TEXT,\n        cuit TEXT,\n        iva TEXT,\n        tipo_factura TEXT DEFAULT 'No factura',\n        monotributo_facturacion TEXT DEFAULT 'No aplica',\n        emisor_id INTEGER,\n        emisor_recomendado_id INTEGER,\n        vencimiento INTEGER,\n        estado TEXT,\n        observaciones TEXT,\n        fecha_alta TEXT,\n        fecha_modificacion TEXT\n\n    )"),
            ('table', 'servicios', 'servicios',
             "CREATE TABLE servicios(\n\n        id INTEGER PRIMARY KEY AUTOINCREMENT,\n        cliente_id INTEGER NOT NULL,\n        concepto TEXT NOT NULL,\n        descripcion TEXT,\n        cantidad INTEGER DEFAULT 1,\n        importe REAL NOT NULL,\n        descuento REAL DEFAULT 0,\n        activo INTEGER DEFAULT 1,\n        fecha_inicio TEXT,\n        fecha_fin TEXT,\n        renovable INTEGER DEFAULT 1,\n        estado_periodo TEXT DEFAULT 'Activo',\n\n        FOREIGN KEY(cliente_id)\n        REFERENCES clientes(id)\n\n    )"),
            ('table', 'catalogo_servicios', 'catalogo_servicios',
             'CREATE TABLE catalogo_servicios(\n        id INTEGER PRIMARY KEY AUTOINCREMENT,\n        nombre TEXT NOT NULL,\n        descripcion TEXT,\n        precio REAL NOT NULL DEFAULT 0,\n        activo INTEGER DEFAULT 1\n    )'),
            ('table', 'emisores_facturacion', 'emisores_facturacion',
             "CREATE TABLE emisores_facturacion(\n        id INTEGER PRIMARY KEY AUTOINCREMENT,\n        alias TEXT NOT NULL,\n        titular TEXT,\n        nombre TEXT,\n        cuit TEXT,\n        condicion_iva TEXT,\n        punto_venta TEXT,\n        tipo_comprobante_default TEXT,\n        orden_prioridad INTEGER DEFAULT 0,\n        direccion TEXT,\n        localidad TEXT,\n        telefono TEXT,\n        email TEXT,\n        activo INTEGER DEFAULT 1,\n        observaciones TEXT,\n        certificado_path TEXT,\n        clave_privada_path TEXT,\n        arca_modo TEXT DEFAULT 'Homologación',\n        arca_estado TEXT DEFAULT 'Desconocido'\n    )"),
            ('table', 'emisores_fiscales', 'emisores_fiscales',
             "CREATE TABLE emisores_fiscales(\n        id INTEGER PRIMARY KEY AUTOINCREMENT,\n        razon_social TEXT NOT NULL,\n        nombre_fantasia TEXT,\n        cuit TEXT,\n        condicion_iva TEXT,\n        tipo_factura TEXT,\n        punto_venta TEXT,\n        activo INTEGER DEFAULT 1,\n        observaciones TEXT,\n        ambiente_arca TEXT DEFAULT 'Homologación',\n        ruta_certificado TEXT DEFAULT '',\n        ruta_clave_privada TEXT DEFAULT '',\n        carpeta_facturas TEXT DEFAULT '',\n        configuracion_arca_completa INTEGER DEFAULT 0\n    )"),
            ('table', 'arca_config', 'arca_config',
             "CREATE TABLE arca_config(\n        id INTEGER PRIMARY KEY AUTOINCREMENT,\n        modo_trabajo TEXT NOT NULL DEFAULT 'Manual'\n    )"),
            ('table', 'servicio_renovaciones', 'servicio_renovaciones',
             'CREATE TABLE servicio_renovaciones(\n\n        id INTEGER PRIMARY KEY AUTOINCREMENT,\n        servicio_id INTEGER NOT NULL,\n        cliente_id INTEGER NOT NULL,\n        fecha_renovacion TEXT NOT NULL,\n        fecha_inicio_anterior TEXT NOT NULL,\n        fecha_fin_anterior TEXT NOT NULL,\n        fecha_inicio_nueva TEXT NOT NULL,\n        fecha_fin_nueva TEXT NOT NULL,\n        concepto TEXT,\n        descripcion TEXT,\n        cantidad REAL DEFAULT 1,\n        importe REAL DEFAULT 0,\n        descuento REAL DEFAULT 0,\n        resumen_id INTEGER,\n\n        FOREIGN KEY(servicio_id) REFERENCES servicios(id),\n        FOREIGN KEY(cliente_id) REFERENCES clientes(id),\n        FOREIGN KEY(resumen_id) REFERENCES resumenes(id)\n\n    )'),
            ('index', 'idx_renovaciones_servicio', 'servicio_renovaciones',
             'CREATE INDEX idx_renovaciones_servicio ON servicio_renovaciones(servicio_id, fecha_renovacion)'),
            ('index', 'idx_renovaciones_resumen', 'servicio_renovaciones',
             'CREATE INDEX idx_renovaciones_resumen ON servicio_renovaciones(resumen_id)'),
            ('table', 'resumenes', 'resumenes',
             "CREATE TABLE resumenes(\n\n        id INTEGER PRIMARY KEY AUTOINCREMENT,\n        numero INTEGER NOT NULL UNIQUE,\n        cliente_id INTEGER NOT NULL,\n        emisor_fiscal_id INTEGER,\n        fecha TEXT NOT NULL,\n        fecha_vencimiento TEXT NOT NULL,\n        tipo_factura TEXT,\n        punto_venta TEXT,\n        total REAL NOT NULL DEFAULT 0,\n        saldo REAL NOT NULL DEFAULT 0,\n        estado TEXT NOT NULL DEFAULT 'Pendiente',\n        estado_facturacion TEXT NOT NULL DEFAULT 'Pendiente',\n        fecha_facturacion TEXT,\n        cae TEXT,\n        vencimiento_cae TEXT,\n        numero_factura TEXT,\n        pdf_path TEXT,\n        fecha_creacion TEXT,\n\n        FOREIGN KEY(cliente_id)\n        REFERENCES clientes(id),\n        FOREIGN KEY(emisor_fiscal_id)\n        REFERENCES emisores_fiscales(id)\n\n    )"),
            ('table', 'resumen_conceptos', 'resumen_conceptos',
             'CREATE TABLE resumen_conceptos(\n\n        id INTEGER PRIMARY KEY AUTOINCREMENT,\n        resumen_id INTEGER NOT NULL,\n        servicio_id INTEGER,\n        concepto TEXT NOT NULL,\n        descripcion TEXT,\n        cantidad REAL NOT NULL DEFAULT 1,\n        importe REAL NOT NULL DEFAULT 0,\n        descuento REAL NOT NULL DEFAULT 0,\n        total REAL NOT NULL DEFAULT 0,\n        fecha_inicio TEXT,\n        fecha_fin TEXT,\n\n        FOREIGN KEY(resumen_id)\n        REFERENCES resumenes(id) ON DELETE CASCADE,\n        FOREIGN KEY(servicio_id)\n        REFERENCES servicios(id)\n\n    )'),
            ('index', 'idx_resumenes_cliente', 'resumenes',
             'CREATE INDEX idx_resumenes_cliente ON resumenes(cliente_id)'),
            ('index', 'idx_resumen_conceptos_resumen', 'resumen_conceptos',
             'CREATE INDEX idx_resumen_conceptos_resumen ON resumen_conceptos(resumen_id)'),
            ('index', 'idx_resumen_conceptos_periodo', 'resumen_conceptos',
             'CREATE INDEX idx_resumen_conceptos_periodo ON resumen_conceptos(servicio_id, fecha_inicio, fecha_fin)'),
            ('table', 'cobros', 'cobros',
             'CREATE TABLE cobros(\n\n        id INTEGER PRIMARY KEY AUTOINCREMENT,\n        cliente_id INTEGER NOT NULL,\n        fecha TEXT NOT NULL,\n        importe REAL NOT NULL DEFAULT 0,\n        forma_pago TEXT,\n        comprobante TEXT,\n        observaciones TEXT,\n\n        FOREIGN KEY(cliente_id)\n        REFERENCES clientes(id)\n\n    )'),
            ('index', 'idx_cobros_cliente', 'cobros',
             'CREATE INDEX idx_cobros_cliente ON cobros(cliente_id)'),
            ('index', 'idx_cobros_fecha', 'cobros',
             'CREATE INDEX idx_cobros_fecha ON cobros(fecha)'),
            ('table', 'tareas', 'tareas',
             "CREATE TABLE tareas(\n\n        id INTEGER PRIMARY KEY AUTOINCREMENT,\n        cliente_id INTEGER,\n        fecha TEXT NOT NULL,\n        hora TEXT NOT NULL,\n        tipo TEXT NOT NULL,\n        titulo TEXT NOT NULL,\n        descripcion TEXT,\n        estado TEXT NOT NULL DEFAULT 'Pendiente',\n        prioridad TEXT NOT NULL DEFAULT 'Media',\n        fecha_creacion TEXT,\n\n        FOREIGN KEY(cliente_id) REFERENCES clientes(id)\n\n    )"),
            ('index', 'idx_tareas_fecha', 'tareas',
             'CREATE INDEX idx_tareas_fecha ON tareas(fecha, hora)'),
            ('index', 'idx_tareas_cliente', 'tareas',
             'CREATE INDEX idx_tareas_cliente ON tareas(cliente_id)'),
            ('index', 'idx_tareas_estado', 'tareas',
             'CREATE INDEX idx_tareas_estado ON tareas(estado)'),
            ('table', 'contactos', 'contactos',
             "CREATE TABLE contactos(\n        id INTEGER PRIMARY KEY AUTOINCREMENT,\n        cliente_id INTEGER NOT NULL,\n        fecha TEXT NOT NULL,\n        hora TEXT NOT NULL,\n        tipo TEXT NOT NULL,\n        resultado TEXT NOT NULL DEFAULT 'Pendiente',\n        observaciones TEXT,\n        proximo_contacto TEXT,\n        vendedor TEXT,\n        creado TEXT,\n        FOREIGN KEY(cliente_id) REFERENCES clientes(id)\n    )"),
            ('index', 'idx_contactos_cliente', 'contactos',
             'CREATE INDEX idx_contactos_cliente ON contactos(cliente_id)'),
            ('index', 'idx_contactos_fecha', 'contactos',
             'CREATE INDEX idx_contactos_fecha ON contactos(fecha)'),
            ('index', 'idx_contactos_proximo', 'contactos',
             'CREATE INDEX idx_contactos_proximo ON contactos(proximo_contacto)'),
            ('index', 'idx_contactos_tipo', 'contactos',
             'CREATE INDEX idx_contactos_tipo ON contactos(tipo)'),
            ('index', 'idx_contactos_resultado', 'contactos',
             'CREATE INDEX idx_contactos_resultado ON contactos(resultado)'),
            ('table', 'factura_arca', 'factura_arca',
             "CREATE TABLE factura_arca(\n        id INTEGER PRIMARY KEY AUTOINCREMENT,\n        cliente_id INTEGER NOT NULL,\n        emisor_id INTEGER NOT NULL,\n        resumen_id INTEGER NOT NULL,\n        fecha TEXT NOT NULL,\n        punto_venta TEXT,\n        tipo_comprobante TEXT,\n        importe_total REAL NOT NULL DEFAULT 0,\n        estado TEXT NOT NULL DEFAULT 'Pendiente',\n        numero_factura TEXT,\n        cae TEXT,\n        vencimiento_cae TEXT,\n        observaciones TEXT,\n        fecha_creacion TEXT,\n\n        FOREIGN KEY(cliente_id) REFERENCES clientes(id),\n        FOREIGN KEY(emisor_id) REFERENCES emisores_facturacion(id),\n        FOREIGN KEY(resumen_id) REFERENCES resumenes(id)\n    )"),
            ('index', 'idx_factura_arca_cliente', 'factura_arca',
             'CREATE INDEX idx_factura_arca_cliente ON factura_arca(cliente_id)'),
            ('index', 'idx_factura_arca_emisor', 'factura_arca',
             'CREATE INDEX idx_factura_arca_emisor ON factura_arca(emisor_id)'),
            ('index', 'idx_factura_arca_resumen', 'factura_arca',
             'CREATE INDEX idx_factura_arca_resumen ON factura_arca(resumen_id)'),
            ('index', 'idx_factura_arca_estado', 'factura_arca',
             'CREATE INDEX idx_factura_arca_estado ON factura_arca(estado)'),
            ('table', 'oportunidades', 'oportunidades',
             "CREATE TABLE oportunidades(\n        id INTEGER PRIMARY KEY AUTOINCREMENT,\n        cliente_id INTEGER,\n        nombre_potencial TEXT,\n        telefono TEXT,\n        whatsapp TEXT,\n        email TEXT,\n        fecha TEXT NOT NULL,\n        origen TEXT,\n        servicio_interes TEXT,\n        importe_estimado REAL DEFAULT 0,\n        probabilidad REAL DEFAULT 0,\n        estado TEXT NOT NULL DEFAULT 'Nueva',\n        proximo_contacto TEXT,\n        observaciones TEXT,\n        creado TEXT,\n        FOREIGN KEY(cliente_id) REFERENCES clientes(id)\n    )"),
            ('index', 'idx_oportunidades_cliente', 'oportunidades',
             'CREATE INDEX idx_oportunidades_cliente ON oportunidades(cliente_id)'),
            ('index', 'idx_oportunidades_estado', 'oportunidades',
             'CREATE INDEX idx_oportunidades_estado ON oportunidades(estado)'),
            ('index', 'idx_oportunidades_fecha', 'oportunidades',
             'CREATE INDEX idx_oportunidades_fecha ON oportunidades(fecha)'),
            ('index', 'idx_oportunidades_proximo', 'oportunidades',
             'CREATE INDEX idx_oportunidades_proximo ON oportunidades(proximo_contacto)'),
            ('table', 'notificaciones', 'notificaciones',
             "CREATE TABLE notificaciones(\n        id INTEGER PRIMARY KEY AUTOINCREMENT,\n        tipo TEXT NOT NULL,\n        titulo TEXT NOT NULL,\n        mensaje TEXT,\n        prioridad TEXT NOT NULL DEFAULT 'Media',\n        estado TEXT NOT NULL DEFAULT 'Pendiente',\n        fecha TEXT NOT NULL,\n        vencimiento TEXT,\n        referencia_tipo TEXT,\n        referencia_id INTEGER,\n        clave TEXT,\n        automatica INTEGER DEFAULT 0,\n        creado TEXT,\n        actualizado TEXT\n    )"),
            ('index', 'idx_notificaciones_clave', 'notificaciones',
             'CREATE UNIQUE INDEX idx_notificaciones_clave ON notificaciones(clave)'),
            ('index', 'idx_notificaciones_estado', 'notificaciones',
             'CREATE INDEX idx_notificaciones_estado ON notificaciones(estado)'),
            ('index', 'idx_notificaciones_tipo', 'notificaciones',
             'CREATE INDEX idx_notificaciones_tipo ON notificaciones(tipo)'),
            ('index', 'idx_notificaciones_prioridad', 'notificaciones',
             'CREATE INDEX idx_notificaciones_prioridad ON notificaciones(prioridad)'),
            ('index', 'idx_notificaciones_vencimiento', 'notificaciones',
             'CREATE INDEX idx_notificaciones_vencimiento ON notificaciones(vencimiento)'),
            ('table', 'usuarios', 'usuarios',
             "CREATE TABLE usuarios(\n        id INTEGER PRIMARY KEY AUTOINCREMENT,\n        nombre TEXT,\n        usuario TEXT NOT NULL UNIQUE,\n        clave TEXT NOT NULL,\n        rol TEXT NOT NULL DEFAULT 'Consulta',\n        activo INTEGER DEFAULT 1,\n        fecha_creacion TEXT\n    )"),
            ('index', 'idx_usuarios_usuario', 'usuarios',
             'CREATE UNIQUE INDEX idx_usuarios_usuario ON usuarios(usuario)'),
        ),
    ),
    'arca_intentos_af3e31e': (
        'af3e31e',
        'Agrega persistencia de intentos de emision ARCA',
        (
            ('table', 'clientes', 'clientes',
             "CREATE TABLE clientes(\n\n        id INTEGER PRIMARY KEY AUTOINCREMENT,\n        nombre TEXT NOT NULL DEFAULT '',\n        codigo TEXT,\n        razon_social TEXT,\n        nombre_comercial TEXT,\n        responsable TEXT,\n        direccion TEXT,\n        localidad TEXT,\n        telefono TEXT,\n        whatsapp TEXT,\n        email TEXT,\n        cuit TEXT,\n        iva TEXT,\n        tipo_factura TEXT DEFAULT 'No factura',\n        monotributo_facturacion TEXT DEFAULT 'No aplica',\n        emisor_id INTEGER,\n        emisor_recomendado_id INTEGER,\n        vencimiento INTEGER,\n        estado TEXT,\n        observaciones TEXT,\n        fecha_alta TEXT,\n        fecha_modificacion TEXT\n\n    , modalidad_comprobante TEXT DEFAULT 'Solo Resumen', emisor_habitual TEXT DEFAULT 'FM Master 98.3')"),
            ('table', 'servicios', 'servicios',
             "CREATE TABLE servicios(\n\n        id INTEGER PRIMARY KEY AUTOINCREMENT,\n        cliente_id INTEGER NOT NULL,\n        concepto TEXT NOT NULL,\n        descripcion TEXT,\n        cantidad INTEGER DEFAULT 1,\n        importe REAL NOT NULL,\n        descuento REAL DEFAULT 0,\n        activo INTEGER DEFAULT 1,\n        fecha_inicio TEXT,\n        fecha_fin TEXT,\n        renovable INTEGER DEFAULT 1,\n        estado_periodo TEXT DEFAULT 'Activo',\n\n        FOREIGN KEY(cliente_id)\n        REFERENCES clientes(id)\n\n    )"),
            ('table', 'catalogo_servicios', 'catalogo_servicios',
             'CREATE TABLE catalogo_servicios(\n        id INTEGER PRIMARY KEY AUTOINCREMENT,\n        nombre TEXT NOT NULL,\n        descripcion TEXT,\n        precio REAL NOT NULL DEFAULT 0,\n        activo INTEGER DEFAULT 1\n    )'),
            ('table', 'emisores_facturacion', 'emisores_facturacion',
             "CREATE TABLE emisores_facturacion(\n        id INTEGER PRIMARY KEY AUTOINCREMENT,\n        alias TEXT NOT NULL,\n        titular TEXT,\n        nombre TEXT,\n        cuit TEXT,\n        condicion_iva TEXT,\n        punto_venta TEXT,\n        tipo_comprobante_default TEXT,\n        orden_prioridad INTEGER DEFAULT 0,\n        direccion TEXT,\n        localidad TEXT,\n        telefono TEXT,\n        email TEXT,\n        activo INTEGER DEFAULT 1,\n        observaciones TEXT,\n        certificado_path TEXT,\n        clave_privada_path TEXT,\n        arca_modo TEXT DEFAULT 'Homologación',\n        arca_estado TEXT DEFAULT 'Desconocido',\n        emisor_fiscal_id INTEGER\n    )"),
            ('table', 'emisores_fiscales', 'emisores_fiscales',
             "CREATE TABLE emisores_fiscales(\n        id INTEGER PRIMARY KEY AUTOINCREMENT,\n        razon_social TEXT NOT NULL,\n        nombre_fantasia TEXT,\n        cuit TEXT,\n        condicion_iva TEXT,\n        tipo_factura TEXT,\n        punto_venta TEXT,\n        activo INTEGER DEFAULT 1,\n        observaciones TEXT,\n        ambiente_arca TEXT DEFAULT 'Homologación',\n        ruta_certificado TEXT DEFAULT '',\n        ruta_clave_privada TEXT DEFAULT '',\n        carpeta_facturas TEXT DEFAULT '',\n        configuracion_arca_completa INTEGER DEFAULT 0\n    , domicilio TEXT DEFAULT '', ingresos_brutos TEXT DEFAULT '', fecha_inicio_actividades TEXT DEFAULT '')"),
            ('table', 'arca_config', 'arca_config',
             "CREATE TABLE arca_config(\n        id INTEGER PRIMARY KEY AUTOINCREMENT,\n        modo_trabajo TEXT NOT NULL DEFAULT 'Manual'\n    )"),
            ('table', 'servicio_renovaciones', 'servicio_renovaciones',
             'CREATE TABLE servicio_renovaciones(\n\n        id INTEGER PRIMARY KEY AUTOINCREMENT,\n        servicio_id INTEGER NOT NULL,\n        cliente_id INTEGER NOT NULL,\n        fecha_renovacion TEXT NOT NULL,\n        fecha_inicio_anterior TEXT NOT NULL,\n        fecha_fin_anterior TEXT NOT NULL,\n        fecha_inicio_nueva TEXT NOT NULL,\n        fecha_fin_nueva TEXT NOT NULL,\n        concepto TEXT,\n        descripcion TEXT,\n        cantidad REAL DEFAULT 1,\n        importe REAL DEFAULT 0,\n        descuento REAL DEFAULT 0,\n        resumen_id INTEGER,\n\n        FOREIGN KEY(servicio_id) REFERENCES servicios(id),\n        FOREIGN KEY(cliente_id) REFERENCES clientes(id),\n        FOREIGN KEY(resumen_id) REFERENCES resumenes(id)\n\n    )'),
            ('index', 'idx_renovaciones_servicio', 'servicio_renovaciones',
             'CREATE INDEX idx_renovaciones_servicio ON servicio_renovaciones(servicio_id, fecha_renovacion)'),
            ('index', 'idx_renovaciones_resumen', 'servicio_renovaciones',
             'CREATE INDEX idx_renovaciones_resumen ON servicio_renovaciones(resumen_id)'),
            ('table', 'resumenes', 'resumenes',
             "CREATE TABLE resumenes(\n\n        id INTEGER PRIMARY KEY AUTOINCREMENT,\n        numero INTEGER NOT NULL UNIQUE,\n        cliente_id INTEGER NOT NULL,\n        emisor_fiscal_id INTEGER,\n        fecha TEXT NOT NULL,\n        fecha_vencimiento TEXT NOT NULL,\n        tipo_factura TEXT,\n        punto_venta TEXT,\n        total REAL NOT NULL DEFAULT 0,\n        saldo REAL NOT NULL DEFAULT 0,\n        estado TEXT NOT NULL DEFAULT 'Pendiente',\n        estado_facturacion TEXT NOT NULL DEFAULT 'Pendiente',\n        fecha_facturacion TEXT,\n        cae TEXT,\n        vencimiento_cae TEXT,\n        numero_factura TEXT,\n        pdf_path TEXT,\n        fecha_creacion TEXT,\n\n        FOREIGN KEY(cliente_id)\n        REFERENCES clientes(id),\n        FOREIGN KEY(emisor_fiscal_id)\n        REFERENCES emisores_fiscales(id)\n\n    )"),
            ('table', 'resumen_conceptos', 'resumen_conceptos',
             'CREATE TABLE resumen_conceptos(\n\n        id INTEGER PRIMARY KEY AUTOINCREMENT,\n        resumen_id INTEGER NOT NULL,\n        servicio_id INTEGER,\n        concepto TEXT NOT NULL,\n        descripcion TEXT,\n        cantidad REAL NOT NULL DEFAULT 1,\n        importe REAL NOT NULL DEFAULT 0,\n        descuento REAL NOT NULL DEFAULT 0,\n        total REAL NOT NULL DEFAULT 0,\n        fecha_inicio TEXT,\n        fecha_fin TEXT,\n\n        FOREIGN KEY(resumen_id)\n        REFERENCES resumenes(id) ON DELETE CASCADE,\n        FOREIGN KEY(servicio_id)\n        REFERENCES servicios(id)\n\n    )'),
            ('index', 'idx_resumenes_cliente', 'resumenes',
             'CREATE INDEX idx_resumenes_cliente ON resumenes(cliente_id)'),
            ('index', 'idx_resumen_conceptos_resumen', 'resumen_conceptos',
             'CREATE INDEX idx_resumen_conceptos_resumen ON resumen_conceptos(resumen_id)'),
            ('index', 'idx_resumen_conceptos_periodo', 'resumen_conceptos',
             'CREATE INDEX idx_resumen_conceptos_periodo ON resumen_conceptos(servicio_id, fecha_inicio, fecha_fin)'),
            ('table', 'cobros', 'cobros',
             'CREATE TABLE cobros(\n\n        id INTEGER PRIMARY KEY AUTOINCREMENT,\n        cliente_id INTEGER NOT NULL,\n        fecha TEXT NOT NULL,\n        importe REAL NOT NULL DEFAULT 0,\n        forma_pago TEXT,\n        comprobante TEXT,\n        factura_arca_id INTEGER,\n        observaciones TEXT,\n\n        FOREIGN KEY(cliente_id)\n        REFERENCES clientes(id)\n\n    )'),
            ('index', 'idx_cobros_cliente', 'cobros',
             'CREATE INDEX idx_cobros_cliente ON cobros(cliente_id)'),
            ('index', 'idx_cobros_fecha', 'cobros',
             'CREATE INDEX idx_cobros_fecha ON cobros(fecha)'),
            ('table', 'tareas', 'tareas',
             "CREATE TABLE tareas(\n\n        id INTEGER PRIMARY KEY AUTOINCREMENT,\n        cliente_id INTEGER,\n        fecha TEXT NOT NULL,\n        hora TEXT NOT NULL,\n        tipo TEXT NOT NULL,\n        titulo TEXT NOT NULL,\n        descripcion TEXT,\n        estado TEXT NOT NULL DEFAULT 'Pendiente',\n        prioridad TEXT NOT NULL DEFAULT 'Media',\n        fecha_creacion TEXT,\n\n        FOREIGN KEY(cliente_id) REFERENCES clientes(id)\n\n    )"),
            ('index', 'idx_tareas_fecha', 'tareas',
             'CREATE INDEX idx_tareas_fecha ON tareas(fecha, hora)'),
            ('index', 'idx_tareas_cliente', 'tareas',
             'CREATE INDEX idx_tareas_cliente ON tareas(cliente_id)'),
            ('index', 'idx_tareas_estado', 'tareas',
             'CREATE INDEX idx_tareas_estado ON tareas(estado)'),
            ('table', 'contactos', 'contactos',
             "CREATE TABLE contactos(\n        id INTEGER PRIMARY KEY AUTOINCREMENT,\n        cliente_id INTEGER NOT NULL,\n        fecha TEXT NOT NULL,\n        hora TEXT NOT NULL,\n        tipo TEXT NOT NULL,\n        resultado TEXT NOT NULL DEFAULT 'Pendiente',\n        observaciones TEXT,\n        proximo_contacto TEXT,\n        vendedor TEXT,\n        creado TEXT,\n        FOREIGN KEY(cliente_id) REFERENCES clientes(id)\n    )"),
            ('index', 'idx_contactos_cliente', 'contactos',
             'CREATE INDEX idx_contactos_cliente ON contactos(cliente_id)'),
            ('index', 'idx_contactos_fecha', 'contactos',
             'CREATE INDEX idx_contactos_fecha ON contactos(fecha)'),
            ('index', 'idx_contactos_proximo', 'contactos',
             'CREATE INDEX idx_contactos_proximo ON contactos(proximo_contacto)'),
            ('index', 'idx_contactos_tipo', 'contactos',
             'CREATE INDEX idx_contactos_tipo ON contactos(tipo)'),
            ('index', 'idx_contactos_resultado', 'contactos',
             'CREATE INDEX idx_contactos_resultado ON contactos(resultado)'),
            ('table', 'factura_arca', 'factura_arca',
             "CREATE TABLE factura_arca(\n        id INTEGER PRIMARY KEY AUTOINCREMENT,\n        cliente_id INTEGER NOT NULL,\n        emisor_id INTEGER NOT NULL,\n        resumen_id INTEGER NOT NULL,\n        fecha TEXT NOT NULL,\n        punto_venta TEXT,\n        tipo_comprobante TEXT,\n        importe_total REAL NOT NULL DEFAULT 0,\n        estado TEXT NOT NULL DEFAULT 'Pendiente',\n        numero_factura TEXT,\n        cae TEXT,\n        vencimiento_cae TEXT,\n        observaciones TEXT,\n        fecha_creacion TEXT,\n\n        FOREIGN KEY(cliente_id) REFERENCES clientes(id),\n        FOREIGN KEY(emisor_id) REFERENCES emisores_facturacion(id),\n        FOREIGN KEY(resumen_id) REFERENCES resumenes(id)\n    )"),
            ('index', 'idx_factura_arca_cliente', 'factura_arca',
             'CREATE INDEX idx_factura_arca_cliente ON factura_arca(cliente_id)'),
            ('index', 'idx_factura_arca_emisor', 'factura_arca',
             'CREATE INDEX idx_factura_arca_emisor ON factura_arca(emisor_id)'),
            ('index', 'idx_factura_arca_resumen', 'factura_arca',
             'CREATE INDEX idx_factura_arca_resumen ON factura_arca(resumen_id)'),
            ('index', 'idx_factura_arca_estado', 'factura_arca',
             'CREATE INDEX idx_factura_arca_estado ON factura_arca(estado)'),
            ('table', 'intentos_emision_arca', 'intentos_emision_arca',
             "CREATE TABLE intentos_emision_arca(\n        id INTEGER PRIMARY KEY AUTOINCREMENT,\n        resumen_id INTEGER NOT NULL,\n        cliente_id INTEGER NOT NULL,\n        emisor_fiscal_id INTEGER NOT NULL,\n        emisor_id INTEGER NOT NULL,\n        cuit_emisor TEXT NOT NULL,\n        punto_venta INTEGER NOT NULL,\n        tipo_comprobante INTEGER NOT NULL,\n        numero_planificado INTEGER NOT NULL,\n        fecha_comprobante TEXT NOT NULL,\n        concepto INTEGER NOT NULL,\n        tipo_documento INTEGER NOT NULL,\n        documento_receptor INTEGER NOT NULL,\n        condicion_iva_receptor_id INTEGER NOT NULL,\n        importe_total TEXT NOT NULL,\n        importe_neto TEXT NOT NULL,\n        importe_iva TEXT NOT NULL,\n        importe_exento TEXT NOT NULL,\n        importe_no_gravado TEXT NOT NULL,\n        importe_tributos TEXT NOT NULL,\n        moneda TEXT NOT NULL,\n        cotizacion TEXT NOT NULL,\n        alicuotas_iva TEXT NOT NULL DEFAULT '[]',\n        estado TEXT NOT NULL,\n        cae TEXT,\n        vencimiento_cae TEXT,\n        error_codigo TEXT,\n        error_mensaje TEXT,\n        detalle_tecnico TEXT,\n        factura_arca_id INTEGER,\n        creado_en TEXT NOT NULL,\n        actualizado_en TEXT NOT NULL,\n        reconciliado_en TEXT,\n        FOREIGN KEY(resumen_id) REFERENCES resumenes(id),\n        FOREIGN KEY(cliente_id) REFERENCES clientes(id),\n        FOREIGN KEY(emisor_fiscal_id) REFERENCES emisores_fiscales(id),\n        FOREIGN KEY(emisor_id) REFERENCES emisores_facturacion(id),\n        FOREIGN KEY(factura_arca_id) REFERENCES factura_arca(id)\n    )"),
            ('index', 'idx_intentos_emision_arca_estado', 'intentos_emision_arca',
             'CREATE INDEX idx_intentos_emision_arca_estado ON intentos_emision_arca(estado, creado_en)'),
            ('index', 'idx_intentos_emision_arca_resumen', 'intentos_emision_arca',
             'CREATE INDEX idx_intentos_emision_arca_resumen ON intentos_emision_arca(resumen_id)'),
            ('index', 'idx_intentos_emision_arca_clave_fiscal', 'intentos_emision_arca',
             'CREATE INDEX idx_intentos_emision_arca_clave_fiscal ON intentos_emision_arca(cuit_emisor, punto_venta, tipo_comprobante, numero_planificado)'),
            ('index', 'idx_intentos_emision_arca_clave_activa', 'intentos_emision_arca',
             "CREATE UNIQUE INDEX idx_intentos_emision_arca_clave_activa ON intentos_emision_arca(cuit_emisor, punto_venta, tipo_comprobante, numero_planificado) WHERE estado IN ('PENDIENTE_RECONCILIAR', 'ENVIANDO', 'CONFLICTO_MANUAL')"),
            ('table', 'oportunidades', 'oportunidades',
             "CREATE TABLE oportunidades(\n        id INTEGER PRIMARY KEY AUTOINCREMENT,\n        cliente_id INTEGER,\n        nombre_potencial TEXT,\n        telefono TEXT,\n        whatsapp TEXT,\n        email TEXT,\n        fecha TEXT NOT NULL,\n        origen TEXT,\n        servicio_interes TEXT,\n        importe_estimado REAL DEFAULT 0,\n        probabilidad REAL DEFAULT 0,\n        estado TEXT NOT NULL DEFAULT 'Nueva',\n        proximo_contacto TEXT,\n        observaciones TEXT,\n        creado TEXT,\n        FOREIGN KEY(cliente_id) REFERENCES clientes(id)\n    )"),
            ('index', 'idx_oportunidades_cliente', 'oportunidades',
             'CREATE INDEX idx_oportunidades_cliente ON oportunidades(cliente_id)'),
            ('index', 'idx_oportunidades_estado', 'oportunidades',
             'CREATE INDEX idx_oportunidades_estado ON oportunidades(estado)'),
            ('index', 'idx_oportunidades_fecha', 'oportunidades',
             'CREATE INDEX idx_oportunidades_fecha ON oportunidades(fecha)'),
            ('index', 'idx_oportunidades_proximo', 'oportunidades',
             'CREATE INDEX idx_oportunidades_proximo ON oportunidades(proximo_contacto)'),
            ('table', 'notificaciones', 'notificaciones',
             "CREATE TABLE notificaciones(\n        id INTEGER PRIMARY KEY AUTOINCREMENT,\n        tipo TEXT NOT NULL,\n        titulo TEXT NOT NULL,\n        mensaje TEXT,\n        prioridad TEXT NOT NULL DEFAULT 'Media',\n        estado TEXT NOT NULL DEFAULT 'Pendiente',\n        fecha TEXT NOT NULL,\n        vencimiento TEXT,\n        referencia_tipo TEXT,\n        referencia_id INTEGER,\n        clave TEXT,\n        automatica INTEGER DEFAULT 0,\n        creado TEXT,\n        actualizado TEXT\n    )"),
            ('index', 'idx_notificaciones_clave', 'notificaciones',
             'CREATE UNIQUE INDEX idx_notificaciones_clave ON notificaciones(clave)'),
            ('index', 'idx_notificaciones_estado', 'notificaciones',
             'CREATE INDEX idx_notificaciones_estado ON notificaciones(estado)'),
            ('index', 'idx_notificaciones_tipo', 'notificaciones',
             'CREATE INDEX idx_notificaciones_tipo ON notificaciones(tipo)'),
            ('index', 'idx_notificaciones_prioridad', 'notificaciones',
             'CREATE INDEX idx_notificaciones_prioridad ON notificaciones(prioridad)'),
            ('index', 'idx_notificaciones_vencimiento', 'notificaciones',
             'CREATE INDEX idx_notificaciones_vencimiento ON notificaciones(vencimiento)'),
            ('table', 'usuarios', 'usuarios',
             "CREATE TABLE usuarios(\n        id INTEGER PRIMARY KEY AUTOINCREMENT,\n        nombre TEXT,\n        usuario TEXT NOT NULL UNIQUE,\n        clave TEXT NOT NULL,\n        rol TEXT NOT NULL DEFAULT 'Consulta',\n        activo INTEGER DEFAULT 1,\n        fecha_creacion TEXT\n    )"),
            ('index', 'idx_usuarios_usuario', 'usuarios',
             'CREATE UNIQUE INDEX idx_usuarios_usuario ON usuarios(usuario)'),
        ),
    ),
    'arca_indices_unicos_0fe8ac7': (
        '0fe8ac7',
        'Agrega restricciones unicas para facturas ARCA',
        (
            ('table', 'clientes', 'clientes',
             "CREATE TABLE clientes(\n\n        id INTEGER PRIMARY KEY AUTOINCREMENT,\n        nombre TEXT NOT NULL DEFAULT '',\n        codigo TEXT,\n        razon_social TEXT,\n        nombre_comercial TEXT,\n        responsable TEXT,\n        direccion TEXT,\n        localidad TEXT,\n        telefono TEXT,\n        whatsapp TEXT,\n        email TEXT,\n        cuit TEXT,\n        iva TEXT,\n        tipo_factura TEXT DEFAULT 'No factura',\n        monotributo_facturacion TEXT DEFAULT 'No aplica',\n        emisor_id INTEGER,\n        emisor_recomendado_id INTEGER,\n        vencimiento INTEGER,\n        estado TEXT,\n        observaciones TEXT,\n        fecha_alta TEXT,\n        fecha_modificacion TEXT\n\n    , modalidad_comprobante TEXT DEFAULT 'Solo Resumen', emisor_habitual TEXT DEFAULT 'FM Master 98.3')"),
            ('table', 'servicios', 'servicios',
             "CREATE TABLE servicios(\n\n        id INTEGER PRIMARY KEY AUTOINCREMENT,\n        cliente_id INTEGER NOT NULL,\n        concepto TEXT NOT NULL,\n        descripcion TEXT,\n        cantidad INTEGER DEFAULT 1,\n        importe REAL NOT NULL,\n        descuento REAL DEFAULT 0,\n        activo INTEGER DEFAULT 1,\n        fecha_inicio TEXT,\n        fecha_fin TEXT,\n        renovable INTEGER DEFAULT 1,\n        estado_periodo TEXT DEFAULT 'Activo',\n\n        FOREIGN KEY(cliente_id)\n        REFERENCES clientes(id)\n\n    )"),
            ('table', 'catalogo_servicios', 'catalogo_servicios',
             'CREATE TABLE catalogo_servicios(\n        id INTEGER PRIMARY KEY AUTOINCREMENT,\n        nombre TEXT NOT NULL,\n        descripcion TEXT,\n        precio REAL NOT NULL DEFAULT 0,\n        activo INTEGER DEFAULT 1\n    )'),
            ('table', 'emisores_facturacion', 'emisores_facturacion',
             "CREATE TABLE emisores_facturacion(\n        id INTEGER PRIMARY KEY AUTOINCREMENT,\n        alias TEXT NOT NULL,\n        titular TEXT,\n        nombre TEXT,\n        cuit TEXT,\n        condicion_iva TEXT,\n        punto_venta TEXT,\n        tipo_comprobante_default TEXT,\n        orden_prioridad INTEGER DEFAULT 0,\n        direccion TEXT,\n        localidad TEXT,\n        telefono TEXT,\n        email TEXT,\n        activo INTEGER DEFAULT 1,\n        observaciones TEXT,\n        certificado_path TEXT,\n        clave_privada_path TEXT,\n        arca_modo TEXT DEFAULT 'Homologación',\n        arca_estado TEXT DEFAULT 'Desconocido',\n        emisor_fiscal_id INTEGER\n    )"),
            ('table', 'emisores_fiscales', 'emisores_fiscales',
             "CREATE TABLE emisores_fiscales(\n        id INTEGER PRIMARY KEY AUTOINCREMENT,\n        razon_social TEXT NOT NULL,\n        nombre_fantasia TEXT,\n        cuit TEXT,\n        condicion_iva TEXT,\n        tipo_factura TEXT,\n        punto_venta TEXT,\n        activo INTEGER DEFAULT 1,\n        observaciones TEXT,\n        ambiente_arca TEXT DEFAULT 'Homologación',\n        ruta_certificado TEXT DEFAULT '',\n        ruta_clave_privada TEXT DEFAULT '',\n        carpeta_facturas TEXT DEFAULT '',\n        configuracion_arca_completa INTEGER DEFAULT 0\n    , domicilio TEXT DEFAULT '', ingresos_brutos TEXT DEFAULT '', fecha_inicio_actividades TEXT DEFAULT '')"),
            ('table', 'arca_config', 'arca_config',
             "CREATE TABLE arca_config(\n        id INTEGER PRIMARY KEY AUTOINCREMENT,\n        modo_trabajo TEXT NOT NULL DEFAULT 'Manual'\n    )"),
            ('table', 'servicio_renovaciones', 'servicio_renovaciones',
             'CREATE TABLE servicio_renovaciones(\n\n        id INTEGER PRIMARY KEY AUTOINCREMENT,\n        servicio_id INTEGER NOT NULL,\n        cliente_id INTEGER NOT NULL,\n        fecha_renovacion TEXT NOT NULL,\n        fecha_inicio_anterior TEXT NOT NULL,\n        fecha_fin_anterior TEXT NOT NULL,\n        fecha_inicio_nueva TEXT NOT NULL,\n        fecha_fin_nueva TEXT NOT NULL,\n        concepto TEXT,\n        descripcion TEXT,\n        cantidad REAL DEFAULT 1,\n        importe REAL DEFAULT 0,\n        descuento REAL DEFAULT 0,\n        resumen_id INTEGER,\n\n        FOREIGN KEY(servicio_id) REFERENCES servicios(id),\n        FOREIGN KEY(cliente_id) REFERENCES clientes(id),\n        FOREIGN KEY(resumen_id) REFERENCES resumenes(id)\n\n    )'),
            ('index', 'idx_renovaciones_servicio', 'servicio_renovaciones',
             'CREATE INDEX idx_renovaciones_servicio ON servicio_renovaciones(servicio_id, fecha_renovacion)'),
            ('index', 'idx_renovaciones_resumen', 'servicio_renovaciones',
             'CREATE INDEX idx_renovaciones_resumen ON servicio_renovaciones(resumen_id)'),
            ('table', 'resumenes', 'resumenes',
             "CREATE TABLE resumenes(\n\n        id INTEGER PRIMARY KEY AUTOINCREMENT,\n        numero INTEGER NOT NULL UNIQUE,\n        cliente_id INTEGER NOT NULL,\n        emisor_fiscal_id INTEGER,\n        fecha TEXT NOT NULL,\n        fecha_vencimiento TEXT NOT NULL,\n        tipo_factura TEXT,\n        punto_venta TEXT,\n        total REAL NOT NULL DEFAULT 0,\n        saldo REAL NOT NULL DEFAULT 0,\n        estado TEXT NOT NULL DEFAULT 'Pendiente',\n        estado_facturacion TEXT NOT NULL DEFAULT 'Pendiente',\n        fecha_facturacion TEXT,\n        cae TEXT,\n        vencimiento_cae TEXT,\n        numero_factura TEXT,\n        pdf_path TEXT,\n        fecha_creacion TEXT,\n\n        FOREIGN KEY(cliente_id)\n        REFERENCES clientes(id),\n        FOREIGN KEY(emisor_fiscal_id)\n        REFERENCES emisores_fiscales(id)\n\n    )"),
            ('table', 'resumen_conceptos', 'resumen_conceptos',
             'CREATE TABLE resumen_conceptos(\n\n        id INTEGER PRIMARY KEY AUTOINCREMENT,\n        resumen_id INTEGER NOT NULL,\n        servicio_id INTEGER,\n        concepto TEXT NOT NULL,\n        descripcion TEXT,\n        cantidad REAL NOT NULL DEFAULT 1,\n        importe REAL NOT NULL DEFAULT 0,\n        descuento REAL NOT NULL DEFAULT 0,\n        total REAL NOT NULL DEFAULT 0,\n        fecha_inicio TEXT,\n        fecha_fin TEXT,\n\n        FOREIGN KEY(resumen_id)\n        REFERENCES resumenes(id) ON DELETE CASCADE,\n        FOREIGN KEY(servicio_id)\n        REFERENCES servicios(id)\n\n    )'),
            ('index', 'idx_resumenes_cliente', 'resumenes',
             'CREATE INDEX idx_resumenes_cliente ON resumenes(cliente_id)'),
            ('index', 'idx_resumen_conceptos_resumen', 'resumen_conceptos',
             'CREATE INDEX idx_resumen_conceptos_resumen ON resumen_conceptos(resumen_id)'),
            ('index', 'idx_resumen_conceptos_periodo', 'resumen_conceptos',
             'CREATE INDEX idx_resumen_conceptos_periodo ON resumen_conceptos(servicio_id, fecha_inicio, fecha_fin)'),
            ('table', 'cobros', 'cobros',
             'CREATE TABLE cobros(\n\n        id INTEGER PRIMARY KEY AUTOINCREMENT,\n        cliente_id INTEGER NOT NULL,\n        fecha TEXT NOT NULL,\n        importe REAL NOT NULL DEFAULT 0,\n        forma_pago TEXT,\n        comprobante TEXT,\n        factura_arca_id INTEGER,\n        observaciones TEXT,\n\n        FOREIGN KEY(cliente_id)\n        REFERENCES clientes(id)\n\n    )'),
            ('index', 'idx_cobros_cliente', 'cobros',
             'CREATE INDEX idx_cobros_cliente ON cobros(cliente_id)'),
            ('index', 'idx_cobros_fecha', 'cobros',
             'CREATE INDEX idx_cobros_fecha ON cobros(fecha)'),
            ('table', 'tareas', 'tareas',
             "CREATE TABLE tareas(\n\n        id INTEGER PRIMARY KEY AUTOINCREMENT,\n        cliente_id INTEGER,\n        fecha TEXT NOT NULL,\n        hora TEXT NOT NULL,\n        tipo TEXT NOT NULL,\n        titulo TEXT NOT NULL,\n        descripcion TEXT,\n        estado TEXT NOT NULL DEFAULT 'Pendiente',\n        prioridad TEXT NOT NULL DEFAULT 'Media',\n        fecha_creacion TEXT,\n\n        FOREIGN KEY(cliente_id) REFERENCES clientes(id)\n\n    )"),
            ('index', 'idx_tareas_fecha', 'tareas',
             'CREATE INDEX idx_tareas_fecha ON tareas(fecha, hora)'),
            ('index', 'idx_tareas_cliente', 'tareas',
             'CREATE INDEX idx_tareas_cliente ON tareas(cliente_id)'),
            ('index', 'idx_tareas_estado', 'tareas',
             'CREATE INDEX idx_tareas_estado ON tareas(estado)'),
            ('table', 'contactos', 'contactos',
             "CREATE TABLE contactos(\n        id INTEGER PRIMARY KEY AUTOINCREMENT,\n        cliente_id INTEGER NOT NULL,\n        fecha TEXT NOT NULL,\n        hora TEXT NOT NULL,\n        tipo TEXT NOT NULL,\n        resultado TEXT NOT NULL DEFAULT 'Pendiente',\n        observaciones TEXT,\n        proximo_contacto TEXT,\n        vendedor TEXT,\n        creado TEXT,\n        FOREIGN KEY(cliente_id) REFERENCES clientes(id)\n    )"),
            ('index', 'idx_contactos_cliente', 'contactos',
             'CREATE INDEX idx_contactos_cliente ON contactos(cliente_id)'),
            ('index', 'idx_contactos_fecha', 'contactos',
             'CREATE INDEX idx_contactos_fecha ON contactos(fecha)'),
            ('index', 'idx_contactos_proximo', 'contactos',
             'CREATE INDEX idx_contactos_proximo ON contactos(proximo_contacto)'),
            ('index', 'idx_contactos_tipo', 'contactos',
             'CREATE INDEX idx_contactos_tipo ON contactos(tipo)'),
            ('index', 'idx_contactos_resultado', 'contactos',
             'CREATE INDEX idx_contactos_resultado ON contactos(resultado)'),
            ('table', 'factura_arca', 'factura_arca',
             "CREATE TABLE factura_arca(\n        id INTEGER PRIMARY KEY AUTOINCREMENT,\n        cliente_id INTEGER NOT NULL,\n        emisor_id INTEGER NOT NULL,\n        resumen_id INTEGER NOT NULL,\n        fecha TEXT NOT NULL,\n        punto_venta TEXT,\n        tipo_comprobante TEXT,\n        importe_total REAL NOT NULL DEFAULT 0,\n        estado TEXT NOT NULL DEFAULT 'Pendiente',\n        numero_factura TEXT,\n        cae TEXT,\n        vencimiento_cae TEXT,\n        observaciones TEXT,\n        fecha_creacion TEXT, punto_venta_num INTEGER, tipo_comprobante_num INTEGER, numero_comprobante_num INTEGER,\n\n        FOREIGN KEY(cliente_id) REFERENCES clientes(id),\n        FOREIGN KEY(emisor_id) REFERENCES emisores_facturacion(id),\n        FOREIGN KEY(resumen_id) REFERENCES resumenes(id)\n    )"),
            ('index', 'idx_factura_arca_cliente', 'factura_arca',
             'CREATE INDEX idx_factura_arca_cliente ON factura_arca(cliente_id)'),
            ('index', 'idx_factura_arca_emisor', 'factura_arca',
             'CREATE INDEX idx_factura_arca_emisor ON factura_arca(emisor_id)'),
            ('index', 'idx_factura_arca_resumen', 'factura_arca',
             'CREATE INDEX idx_factura_arca_resumen ON factura_arca(resumen_id)'),
            ('index', 'idx_factura_arca_estado', 'factura_arca',
             'CREATE INDEX idx_factura_arca_estado ON factura_arca(estado)'),
            ('index', 'idx_factura_arca_cae_unico', 'factura_arca',
             "CREATE UNIQUE INDEX idx_factura_arca_cae_unico ON factura_arca(cae) WHERE TRIM(COALESCE(cae, '')) <> ''"),
            ('index', 'idx_factura_arca_identidad_unica', 'factura_arca',
             'CREATE UNIQUE INDEX idx_factura_arca_identidad_unica ON factura_arca(emisor_id, punto_venta_num, tipo_comprobante_num, numero_comprobante_num) WHERE numero_comprobante_num IS NOT NULL'),
            ('table', 'intentos_emision_arca', 'intentos_emision_arca',
             "CREATE TABLE intentos_emision_arca(\n        id INTEGER PRIMARY KEY AUTOINCREMENT,\n        resumen_id INTEGER NOT NULL,\n        cliente_id INTEGER NOT NULL,\n        emisor_fiscal_id INTEGER NOT NULL,\n        emisor_id INTEGER NOT NULL,\n        cuit_emisor TEXT NOT NULL,\n        punto_venta INTEGER NOT NULL,\n        tipo_comprobante INTEGER NOT NULL,\n        numero_planificado INTEGER NOT NULL,\n        fecha_comprobante TEXT NOT NULL,\n        concepto INTEGER NOT NULL,\n        tipo_documento INTEGER NOT NULL,\n        documento_receptor INTEGER NOT NULL,\n        condicion_iva_receptor_id INTEGER NOT NULL,\n        importe_total TEXT NOT NULL,\n        importe_neto TEXT NOT NULL,\n        importe_iva TEXT NOT NULL,\n        importe_exento TEXT NOT NULL,\n        importe_no_gravado TEXT NOT NULL,\n        importe_tributos TEXT NOT NULL,\n        moneda TEXT NOT NULL,\n        cotizacion TEXT NOT NULL,\n        alicuotas_iva TEXT NOT NULL DEFAULT '[]',\n        estado TEXT NOT NULL,\n        cae TEXT,\n        vencimiento_cae TEXT,\n        error_codigo TEXT,\n        error_mensaje TEXT,\n        detalle_tecnico TEXT,\n        factura_arca_id INTEGER,\n        creado_en TEXT NOT NULL,\n        actualizado_en TEXT NOT NULL,\n        reconciliado_en TEXT,\n        FOREIGN KEY(resumen_id) REFERENCES resumenes(id),\n        FOREIGN KEY(cliente_id) REFERENCES clientes(id),\n        FOREIGN KEY(emisor_fiscal_id) REFERENCES emisores_fiscales(id),\n        FOREIGN KEY(emisor_id) REFERENCES emisores_facturacion(id),\n        FOREIGN KEY(factura_arca_id) REFERENCES factura_arca(id)\n    )"),
            ('index', 'idx_intentos_emision_arca_estado', 'intentos_emision_arca',
             'CREATE INDEX idx_intentos_emision_arca_estado ON intentos_emision_arca(estado, creado_en)'),
            ('index', 'idx_intentos_emision_arca_resumen', 'intentos_emision_arca',
             'CREATE INDEX idx_intentos_emision_arca_resumen ON intentos_emision_arca(resumen_id)'),
            ('index', 'idx_intentos_emision_arca_clave_fiscal', 'intentos_emision_arca',
             'CREATE INDEX idx_intentos_emision_arca_clave_fiscal ON intentos_emision_arca(cuit_emisor, punto_venta, tipo_comprobante, numero_planificado)'),
            ('index', 'idx_intentos_emision_arca_clave_activa', 'intentos_emision_arca',
             "CREATE UNIQUE INDEX idx_intentos_emision_arca_clave_activa ON intentos_emision_arca(cuit_emisor, punto_venta, tipo_comprobante, numero_planificado) WHERE estado IN ('PENDIENTE_RECONCILIAR', 'ENVIANDO', 'CONFLICTO_MANUAL')"),
            ('table', 'oportunidades', 'oportunidades',
             "CREATE TABLE oportunidades(\n        id INTEGER PRIMARY KEY AUTOINCREMENT,\n        cliente_id INTEGER,\n        nombre_potencial TEXT,\n        telefono TEXT,\n        whatsapp TEXT,\n        email TEXT,\n        fecha TEXT NOT NULL,\n        origen TEXT,\n        servicio_interes TEXT,\n        importe_estimado REAL DEFAULT 0,\n        probabilidad REAL DEFAULT 0,\n        estado TEXT NOT NULL DEFAULT 'Nueva',\n        proximo_contacto TEXT,\n        observaciones TEXT,\n        creado TEXT,\n        FOREIGN KEY(cliente_id) REFERENCES clientes(id)\n    )"),
            ('index', 'idx_oportunidades_cliente', 'oportunidades',
             'CREATE INDEX idx_oportunidades_cliente ON oportunidades(cliente_id)'),
            ('index', 'idx_oportunidades_estado', 'oportunidades',
             'CREATE INDEX idx_oportunidades_estado ON oportunidades(estado)'),
            ('index', 'idx_oportunidades_fecha', 'oportunidades',
             'CREATE INDEX idx_oportunidades_fecha ON oportunidades(fecha)'),
            ('index', 'idx_oportunidades_proximo', 'oportunidades',
             'CREATE INDEX idx_oportunidades_proximo ON oportunidades(proximo_contacto)'),
            ('table', 'notificaciones', 'notificaciones',
             "CREATE TABLE notificaciones(\n        id INTEGER PRIMARY KEY AUTOINCREMENT,\n        tipo TEXT NOT NULL,\n        titulo TEXT NOT NULL,\n        mensaje TEXT,\n        prioridad TEXT NOT NULL DEFAULT 'Media',\n        estado TEXT NOT NULL DEFAULT 'Pendiente',\n        fecha TEXT NOT NULL,\n        vencimiento TEXT,\n        referencia_tipo TEXT,\n        referencia_id INTEGER,\n        clave TEXT,\n        automatica INTEGER DEFAULT 0,\n        creado TEXT,\n        actualizado TEXT\n    )"),
            ('index', 'idx_notificaciones_clave', 'notificaciones',
             'CREATE UNIQUE INDEX idx_notificaciones_clave ON notificaciones(clave)'),
            ('index', 'idx_notificaciones_estado', 'notificaciones',
             'CREATE INDEX idx_notificaciones_estado ON notificaciones(estado)'),
            ('index', 'idx_notificaciones_tipo', 'notificaciones',
             'CREATE INDEX idx_notificaciones_tipo ON notificaciones(tipo)'),
            ('index', 'idx_notificaciones_prioridad', 'notificaciones',
             'CREATE INDEX idx_notificaciones_prioridad ON notificaciones(prioridad)'),
            ('index', 'idx_notificaciones_vencimiento', 'notificaciones',
             'CREATE INDEX idx_notificaciones_vencimiento ON notificaciones(vencimiento)'),
            ('table', 'usuarios', 'usuarios',
             "CREATE TABLE usuarios(\n        id INTEGER PRIMARY KEY AUTOINCREMENT,\n        nombre TEXT,\n        usuario TEXT NOT NULL UNIQUE,\n        clave TEXT NOT NULL,\n        rol TEXT NOT NULL DEFAULT 'Consulta',\n        activo INTEGER DEFAULT 1,\n        fecha_creacion TEXT\n    )"),
            ('index', 'idx_usuarios_usuario', 'usuarios',
             'CREATE UNIQUE INDEX idx_usuarios_usuario ON usuarios(usuario)'),
        ),
    ),
    'arca_config_ambiente_599d0f5': (
        '599d0f5',
        'Agrega configuracion ARCA por ambiente',
        (
            ('table', 'clientes', 'clientes',
             "CREATE TABLE clientes(\n\n        id INTEGER PRIMARY KEY AUTOINCREMENT,\n        nombre TEXT NOT NULL DEFAULT '',\n        codigo TEXT,\n        razon_social TEXT,\n        nombre_comercial TEXT,\n        responsable TEXT,\n        direccion TEXT,\n        localidad TEXT,\n        telefono TEXT,\n        whatsapp TEXT,\n        email TEXT,\n        cuit TEXT,\n        iva TEXT,\n        tipo_factura TEXT DEFAULT 'No factura',\n        monotributo_facturacion TEXT DEFAULT 'No aplica',\n        emisor_id INTEGER,\n        emisor_recomendado_id INTEGER,\n        vencimiento INTEGER,\n        estado TEXT,\n        observaciones TEXT,\n        fecha_alta TEXT,\n        fecha_modificacion TEXT\n\n    , modalidad_comprobante TEXT DEFAULT 'Solo Resumen', emisor_habitual TEXT DEFAULT 'FM Master 98.3')"),
            ('table', 'servicios', 'servicios',
             "CREATE TABLE servicios(\n\n        id INTEGER PRIMARY KEY AUTOINCREMENT,\n        cliente_id INTEGER NOT NULL,\n        concepto TEXT NOT NULL,\n        descripcion TEXT,\n        cantidad INTEGER DEFAULT 1,\n        importe REAL NOT NULL,\n        descuento REAL DEFAULT 0,\n        activo INTEGER DEFAULT 1,\n        fecha_inicio TEXT,\n        fecha_fin TEXT,\n        renovable INTEGER DEFAULT 1,\n        estado_periodo TEXT DEFAULT 'Activo',\n\n        FOREIGN KEY(cliente_id)\n        REFERENCES clientes(id)\n\n    )"),
            ('table', 'catalogo_servicios', 'catalogo_servicios',
             'CREATE TABLE catalogo_servicios(\n        id INTEGER PRIMARY KEY AUTOINCREMENT,\n        nombre TEXT NOT NULL,\n        descripcion TEXT,\n        precio REAL NOT NULL DEFAULT 0,\n        activo INTEGER DEFAULT 1\n    )'),
            ('table', 'emisores_facturacion', 'emisores_facturacion',
             "CREATE TABLE emisores_facturacion(\n        id INTEGER PRIMARY KEY AUTOINCREMENT,\n        alias TEXT NOT NULL,\n        titular TEXT,\n        nombre TEXT,\n        cuit TEXT,\n        condicion_iva TEXT,\n        punto_venta TEXT,\n        tipo_comprobante_default TEXT,\n        orden_prioridad INTEGER DEFAULT 0,\n        direccion TEXT,\n        localidad TEXT,\n        telefono TEXT,\n        email TEXT,\n        activo INTEGER DEFAULT 1,\n        observaciones TEXT,\n        certificado_path TEXT,\n        clave_privada_path TEXT,\n        arca_modo TEXT DEFAULT 'Homologación',\n        arca_estado TEXT DEFAULT 'Desconocido',\n        emisor_fiscal_id INTEGER\n    )"),
            ('table', 'emisores_fiscales', 'emisores_fiscales',
             "CREATE TABLE emisores_fiscales(\n        id INTEGER PRIMARY KEY AUTOINCREMENT,\n        razon_social TEXT NOT NULL,\n        nombre_fantasia TEXT,\n        cuit TEXT,\n        condicion_iva TEXT,\n        tipo_factura TEXT,\n        punto_venta TEXT,\n        activo INTEGER DEFAULT 1,\n        observaciones TEXT,\n        ambiente_arca TEXT DEFAULT 'Homologación',\n        ruta_certificado TEXT DEFAULT '',\n        ruta_clave_privada TEXT DEFAULT '',\n        carpeta_facturas TEXT DEFAULT '',\n        configuracion_arca_completa INTEGER DEFAULT 0\n    , domicilio TEXT DEFAULT '', ingresos_brutos TEXT DEFAULT '', fecha_inicio_actividades TEXT DEFAULT '')"),
            ('table', 'emisor_fiscal_arca_config', 'emisor_fiscal_arca_config',
             "CREATE TABLE emisor_fiscal_arca_config(\n        id INTEGER PRIMARY KEY AUTOINCREMENT,\n        emisor_fiscal_id INTEGER NOT NULL,\n        ambiente_arca TEXT NOT NULL CHECK(ambiente_arca IN ('HOMOLOGACION', 'PRODUCCION')),\n        punto_venta TEXT,\n        ruta_certificado TEXT,\n        ruta_clave_privada TEXT,\n        carpeta_facturas TEXT,\n        UNIQUE(emisor_fiscal_id, ambiente_arca),\n        FOREIGN KEY(emisor_fiscal_id) REFERENCES emisores_fiscales(id)\n    )"),
            ('table', 'arca_config', 'arca_config',
             "CREATE TABLE arca_config(\n        id INTEGER PRIMARY KEY AUTOINCREMENT,\n        modo_trabajo TEXT NOT NULL DEFAULT 'Manual'\n    )"),
            ('table', 'servicio_renovaciones', 'servicio_renovaciones',
             'CREATE TABLE servicio_renovaciones(\n\n        id INTEGER PRIMARY KEY AUTOINCREMENT,\n        servicio_id INTEGER NOT NULL,\n        cliente_id INTEGER NOT NULL,\n        fecha_renovacion TEXT NOT NULL,\n        fecha_inicio_anterior TEXT NOT NULL,\n        fecha_fin_anterior TEXT NOT NULL,\n        fecha_inicio_nueva TEXT NOT NULL,\n        fecha_fin_nueva TEXT NOT NULL,\n        concepto TEXT,\n        descripcion TEXT,\n        cantidad REAL DEFAULT 1,\n        importe REAL DEFAULT 0,\n        descuento REAL DEFAULT 0,\n        resumen_id INTEGER,\n\n        FOREIGN KEY(servicio_id) REFERENCES servicios(id),\n        FOREIGN KEY(cliente_id) REFERENCES clientes(id),\n        FOREIGN KEY(resumen_id) REFERENCES resumenes(id)\n\n    )'),
            ('index', 'idx_renovaciones_servicio', 'servicio_renovaciones',
             'CREATE INDEX idx_renovaciones_servicio ON servicio_renovaciones(servicio_id, fecha_renovacion)'),
            ('index', 'idx_renovaciones_resumen', 'servicio_renovaciones',
             'CREATE INDEX idx_renovaciones_resumen ON servicio_renovaciones(resumen_id)'),
            ('table', 'resumenes', 'resumenes',
             "CREATE TABLE resumenes(\n\n        id INTEGER PRIMARY KEY AUTOINCREMENT,\n        numero INTEGER NOT NULL UNIQUE,\n        cliente_id INTEGER NOT NULL,\n        emisor_fiscal_id INTEGER,\n        fecha TEXT NOT NULL,\n        fecha_vencimiento TEXT NOT NULL,\n        tipo_factura TEXT,\n        punto_venta TEXT,\n        total REAL NOT NULL DEFAULT 0,\n        saldo REAL NOT NULL DEFAULT 0,\n        estado TEXT NOT NULL DEFAULT 'Pendiente',\n        estado_facturacion TEXT NOT NULL DEFAULT 'Pendiente',\n        fecha_facturacion TEXT,\n        cae TEXT,\n        vencimiento_cae TEXT,\n        numero_factura TEXT,\n        pdf_path TEXT,\n        fecha_creacion TEXT,\n\n        FOREIGN KEY(cliente_id)\n        REFERENCES clientes(id),\n        FOREIGN KEY(emisor_fiscal_id)\n        REFERENCES emisores_fiscales(id)\n\n    )"),
            ('table', 'resumen_conceptos', 'resumen_conceptos',
             'CREATE TABLE resumen_conceptos(\n\n        id INTEGER PRIMARY KEY AUTOINCREMENT,\n        resumen_id INTEGER NOT NULL,\n        servicio_id INTEGER,\n        concepto TEXT NOT NULL,\n        descripcion TEXT,\n        cantidad REAL NOT NULL DEFAULT 1,\n        importe REAL NOT NULL DEFAULT 0,\n        descuento REAL NOT NULL DEFAULT 0,\n        total REAL NOT NULL DEFAULT 0,\n        fecha_inicio TEXT,\n        fecha_fin TEXT,\n\n        FOREIGN KEY(resumen_id)\n        REFERENCES resumenes(id) ON DELETE CASCADE,\n        FOREIGN KEY(servicio_id)\n        REFERENCES servicios(id)\n\n    )'),
            ('index', 'idx_resumenes_cliente', 'resumenes',
             'CREATE INDEX idx_resumenes_cliente ON resumenes(cliente_id)'),
            ('index', 'idx_resumen_conceptos_resumen', 'resumen_conceptos',
             'CREATE INDEX idx_resumen_conceptos_resumen ON resumen_conceptos(resumen_id)'),
            ('index', 'idx_resumen_conceptos_periodo', 'resumen_conceptos',
             'CREATE INDEX idx_resumen_conceptos_periodo ON resumen_conceptos(servicio_id, fecha_inicio, fecha_fin)'),
            ('table', 'cobros', 'cobros',
             'CREATE TABLE cobros(\n\n        id INTEGER PRIMARY KEY AUTOINCREMENT,\n        cliente_id INTEGER NOT NULL,\n        fecha TEXT NOT NULL,\n        importe REAL NOT NULL DEFAULT 0,\n        forma_pago TEXT,\n        comprobante TEXT,\n        factura_arca_id INTEGER,\n        observaciones TEXT,\n\n        FOREIGN KEY(cliente_id)\n        REFERENCES clientes(id)\n\n    )'),
            ('index', 'idx_cobros_cliente', 'cobros',
             'CREATE INDEX idx_cobros_cliente ON cobros(cliente_id)'),
            ('index', 'idx_cobros_fecha', 'cobros',
             'CREATE INDEX idx_cobros_fecha ON cobros(fecha)'),
            ('table', 'tareas', 'tareas',
             "CREATE TABLE tareas(\n\n        id INTEGER PRIMARY KEY AUTOINCREMENT,\n        cliente_id INTEGER,\n        fecha TEXT NOT NULL,\n        hora TEXT NOT NULL,\n        tipo TEXT NOT NULL,\n        titulo TEXT NOT NULL,\n        descripcion TEXT,\n        estado TEXT NOT NULL DEFAULT 'Pendiente',\n        prioridad TEXT NOT NULL DEFAULT 'Media',\n        fecha_creacion TEXT,\n\n        FOREIGN KEY(cliente_id) REFERENCES clientes(id)\n\n    )"),
            ('index', 'idx_tareas_fecha', 'tareas',
             'CREATE INDEX idx_tareas_fecha ON tareas(fecha, hora)'),
            ('index', 'idx_tareas_cliente', 'tareas',
             'CREATE INDEX idx_tareas_cliente ON tareas(cliente_id)'),
            ('index', 'idx_tareas_estado', 'tareas',
             'CREATE INDEX idx_tareas_estado ON tareas(estado)'),
            ('table', 'contactos', 'contactos',
             "CREATE TABLE contactos(\n        id INTEGER PRIMARY KEY AUTOINCREMENT,\n        cliente_id INTEGER NOT NULL,\n        fecha TEXT NOT NULL,\n        hora TEXT NOT NULL,\n        tipo TEXT NOT NULL,\n        resultado TEXT NOT NULL DEFAULT 'Pendiente',\n        observaciones TEXT,\n        proximo_contacto TEXT,\n        vendedor TEXT,\n        creado TEXT,\n        FOREIGN KEY(cliente_id) REFERENCES clientes(id)\n    )"),
            ('index', 'idx_contactos_cliente', 'contactos',
             'CREATE INDEX idx_contactos_cliente ON contactos(cliente_id)'),
            ('index', 'idx_contactos_fecha', 'contactos',
             'CREATE INDEX idx_contactos_fecha ON contactos(fecha)'),
            ('index', 'idx_contactos_proximo', 'contactos',
             'CREATE INDEX idx_contactos_proximo ON contactos(proximo_contacto)'),
            ('index', 'idx_contactos_tipo', 'contactos',
             'CREATE INDEX idx_contactos_tipo ON contactos(tipo)'),
            ('index', 'idx_contactos_resultado', 'contactos',
             'CREATE INDEX idx_contactos_resultado ON contactos(resultado)'),
            ('table', 'factura_arca', 'factura_arca',
             "CREATE TABLE factura_arca(\n        id INTEGER PRIMARY KEY AUTOINCREMENT,\n        cliente_id INTEGER NOT NULL,\n        emisor_id INTEGER NOT NULL,\n        resumen_id INTEGER NOT NULL,\n        fecha TEXT NOT NULL,\n        punto_venta TEXT,\n        tipo_comprobante TEXT,\n        importe_total REAL NOT NULL DEFAULT 0,\n        estado TEXT NOT NULL DEFAULT 'Pendiente',\n        numero_factura TEXT,\n        cae TEXT,\n        vencimiento_cae TEXT,\n        observaciones TEXT,\n        fecha_creacion TEXT, punto_venta_num INTEGER, tipo_comprobante_num INTEGER, numero_comprobante_num INTEGER, tipo_documento_receptor INTEGER, documento_receptor INTEGER, snapshot_fiscal_json TEXT, snapshot_version INTEGER, snapshot_hash TEXT, ambiente_arca TEXT, ruta_pdf_relativa TEXT, ruta_pdf_absoluta TEXT,\n\n        FOREIGN KEY(cliente_id) REFERENCES clientes(id),\n        FOREIGN KEY(emisor_id) REFERENCES emisores_facturacion(id),\n        FOREIGN KEY(resumen_id) REFERENCES resumenes(id)\n    )"),
            ('index', 'idx_factura_arca_cliente', 'factura_arca',
             'CREATE INDEX idx_factura_arca_cliente ON factura_arca(cliente_id)'),
            ('index', 'idx_factura_arca_emisor', 'factura_arca',
             'CREATE INDEX idx_factura_arca_emisor ON factura_arca(emisor_id)'),
            ('index', 'idx_factura_arca_resumen', 'factura_arca',
             'CREATE INDEX idx_factura_arca_resumen ON factura_arca(resumen_id)'),
            ('index', 'idx_factura_arca_estado', 'factura_arca',
             'CREATE INDEX idx_factura_arca_estado ON factura_arca(estado)'),
            ('index', 'idx_factura_arca_identidad_unica', 'factura_arca',
             'CREATE UNIQUE INDEX idx_factura_arca_identidad_unica ON factura_arca(ambiente_arca, emisor_id, punto_venta_num, tipo_comprobante_num, numero_comprobante_num) WHERE ambiente_arca IS NOT NULL AND numero_comprobante_num IS NOT NULL AND emisor_id > 0 AND punto_venta_num > 0 AND tipo_comprobante_num > 0 AND numero_comprobante_num > 0'),
            ('index', 'idx_factura_arca_identidad_historica_unica', 'factura_arca',
             'CREATE UNIQUE INDEX idx_factura_arca_identidad_historica_unica ON factura_arca(emisor_id, punto_venta_num, tipo_comprobante_num, numero_comprobante_num) WHERE ambiente_arca IS NULL AND numero_comprobante_num IS NOT NULL AND emisor_id > 0 AND punto_venta_num > 0 AND tipo_comprobante_num > 0 AND numero_comprobante_num > 0'),
            ('index', 'idx_factura_arca_cae_unico', 'factura_arca',
             "CREATE UNIQUE INDEX idx_factura_arca_cae_unico ON factura_arca(ambiente_arca, TRIM(cae)) WHERE ambiente_arca IS NOT NULL AND TRIM(COALESCE(cae, '')) <> ''"),
            ('index', 'idx_factura_arca_cae_historico_unico', 'factura_arca',
             "CREATE UNIQUE INDEX idx_factura_arca_cae_historico_unico ON factura_arca(TRIM(cae)) WHERE ambiente_arca IS NULL AND TRIM(COALESCE(cae, '')) <> ''"),
            ('table', 'intentos_emision_arca', 'intentos_emision_arca',
             "CREATE TABLE intentos_emision_arca(\n        id INTEGER PRIMARY KEY AUTOINCREMENT,\n        resumen_id INTEGER NOT NULL,\n        cliente_id INTEGER NOT NULL,\n        emisor_fiscal_id INTEGER NOT NULL,\n        emisor_id INTEGER NOT NULL,\n        cuit_emisor TEXT NOT NULL,\n        punto_venta INTEGER NOT NULL,\n        tipo_comprobante INTEGER NOT NULL,\n        numero_planificado INTEGER NOT NULL,\n        fecha_comprobante TEXT NOT NULL,\n        concepto INTEGER NOT NULL,\n        tipo_documento INTEGER NOT NULL,\n        documento_receptor INTEGER NOT NULL,\n        condicion_iva_receptor_id INTEGER NOT NULL,\n        importe_total TEXT NOT NULL,\n        importe_neto TEXT NOT NULL,\n        importe_iva TEXT NOT NULL,\n        importe_exento TEXT NOT NULL,\n        importe_no_gravado TEXT NOT NULL,\n        importe_tributos TEXT NOT NULL,\n        moneda TEXT NOT NULL,\n        cotizacion TEXT NOT NULL,\n        alicuotas_iva TEXT NOT NULL DEFAULT '[]',\n        estado TEXT NOT NULL,\n        cae TEXT,\n        vencimiento_cae TEXT,\n        error_codigo TEXT,\n        error_mensaje TEXT,\n        detalle_tecnico TEXT,\n        factura_arca_id INTEGER,\n        creado_en TEXT NOT NULL,\n        actualizado_en TEXT NOT NULL,\n        reconciliado_en TEXT, contexto_fiscal_json TEXT, contexto_fiscal_version INTEGER, contexto_fiscal_hash TEXT, ambiente_arca TEXT,\n        FOREIGN KEY(resumen_id) REFERENCES resumenes(id),\n        FOREIGN KEY(cliente_id) REFERENCES clientes(id),\n        FOREIGN KEY(emisor_fiscal_id) REFERENCES emisores_fiscales(id),\n        FOREIGN KEY(emisor_id) REFERENCES emisores_facturacion(id),\n        FOREIGN KEY(factura_arca_id) REFERENCES factura_arca(id)\n    )"),
            ('index', 'idx_intentos_emision_arca_estado', 'intentos_emision_arca',
             'CREATE INDEX idx_intentos_emision_arca_estado ON intentos_emision_arca(estado, creado_en)'),
            ('index', 'idx_intentos_emision_arca_resumen', 'intentos_emision_arca',
             'CREATE INDEX idx_intentos_emision_arca_resumen ON intentos_emision_arca(resumen_id)'),
            ('index', 'idx_intentos_emision_arca_clave_fiscal', 'intentos_emision_arca',
             'CREATE INDEX idx_intentos_emision_arca_clave_fiscal ON intentos_emision_arca(cuit_emisor, punto_venta, tipo_comprobante, numero_planificado)'),
            ('index', 'idx_intentos_emision_arca_clave_activa_ambiente', 'intentos_emision_arca',
             "CREATE UNIQUE INDEX idx_intentos_emision_arca_clave_activa_ambiente ON intentos_emision_arca(ambiente_arca, cuit_emisor, punto_venta, tipo_comprobante, numero_planificado) WHERE ambiente_arca IS NOT NULL AND TRIM(COALESCE(cuit_emisor, '')) <> '' AND punto_venta > 0 AND tipo_comprobante > 0 AND numero_planificado > 0 AND estado IN ('PENDIENTE_RECONCILIAR', 'ENVIANDO', 'CONFLICTO_MANUAL')"),
            ('index', 'idx_intentos_emision_arca_clave_activa_historica', 'intentos_emision_arca',
             "CREATE UNIQUE INDEX idx_intentos_emision_arca_clave_activa_historica ON intentos_emision_arca(cuit_emisor, punto_venta, tipo_comprobante, numero_planificado) WHERE ambiente_arca IS NULL AND TRIM(COALESCE(cuit_emisor, '')) <> '' AND punto_venta > 0 AND tipo_comprobante > 0 AND numero_planificado > 0 AND estado IN ('PENDIENTE_RECONCILIAR', 'ENVIANDO', 'CONFLICTO_MANUAL')"),
            ('table', 'oportunidades', 'oportunidades',
             "CREATE TABLE oportunidades(\n        id INTEGER PRIMARY KEY AUTOINCREMENT,\n        cliente_id INTEGER,\n        nombre_potencial TEXT,\n        telefono TEXT,\n        whatsapp TEXT,\n        email TEXT,\n        fecha TEXT NOT NULL,\n        origen TEXT,\n        servicio_interes TEXT,\n        importe_estimado REAL DEFAULT 0,\n        probabilidad REAL DEFAULT 0,\n        estado TEXT NOT NULL DEFAULT 'Nueva',\n        proximo_contacto TEXT,\n        observaciones TEXT,\n        creado TEXT,\n        FOREIGN KEY(cliente_id) REFERENCES clientes(id)\n    )"),
            ('index', 'idx_oportunidades_cliente', 'oportunidades',
             'CREATE INDEX idx_oportunidades_cliente ON oportunidades(cliente_id)'),
            ('index', 'idx_oportunidades_estado', 'oportunidades',
             'CREATE INDEX idx_oportunidades_estado ON oportunidades(estado)'),
            ('index', 'idx_oportunidades_fecha', 'oportunidades',
             'CREATE INDEX idx_oportunidades_fecha ON oportunidades(fecha)'),
            ('index', 'idx_oportunidades_proximo', 'oportunidades',
             'CREATE INDEX idx_oportunidades_proximo ON oportunidades(proximo_contacto)'),
            ('table', 'notificaciones', 'notificaciones',
             "CREATE TABLE notificaciones(\n        id INTEGER PRIMARY KEY AUTOINCREMENT,\n        tipo TEXT NOT NULL,\n        titulo TEXT NOT NULL,\n        mensaje TEXT,\n        prioridad TEXT NOT NULL DEFAULT 'Media',\n        estado TEXT NOT NULL DEFAULT 'Pendiente',\n        fecha TEXT NOT NULL,\n        vencimiento TEXT,\n        referencia_tipo TEXT,\n        referencia_id INTEGER,\n        clave TEXT,\n        automatica INTEGER DEFAULT 0,\n        creado TEXT,\n        actualizado TEXT\n    )"),
            ('index', 'idx_notificaciones_clave', 'notificaciones',
             'CREATE UNIQUE INDEX idx_notificaciones_clave ON notificaciones(clave)'),
            ('index', 'idx_notificaciones_estado', 'notificaciones',
             'CREATE INDEX idx_notificaciones_estado ON notificaciones(estado)'),
            ('index', 'idx_notificaciones_tipo', 'notificaciones',
             'CREATE INDEX idx_notificaciones_tipo ON notificaciones(tipo)'),
            ('index', 'idx_notificaciones_prioridad', 'notificaciones',
             'CREATE INDEX idx_notificaciones_prioridad ON notificaciones(prioridad)'),
            ('index', 'idx_notificaciones_vencimiento', 'notificaciones',
             'CREATE INDEX idx_notificaciones_vencimiento ON notificaciones(vencimiento)'),
            ('table', 'usuarios', 'usuarios',
             "CREATE TABLE usuarios(\n        id INTEGER PRIMARY KEY AUTOINCREMENT,\n        nombre TEXT,\n        usuario TEXT NOT NULL UNIQUE,\n        clave TEXT NOT NULL,\n        rol TEXT NOT NULL DEFAULT 'Consulta',\n        activo INTEGER DEFAULT 1,\n        fecha_creacion TEXT\n    )"),
            ('index', 'idx_usuarios_usuario', 'usuarios',
             'CREATE UNIQUE INDEX idx_usuarios_usuario ON usuarios(usuario)'),
        ),
    ),
}

LEGITIMA_DEMOSTRADA = "LEGITIMA_DEMOSTRADA"
LEGITIMA_ALTERADA = "LEGITIMA_ALTERADA_NO_DEMOSTRADA"
AJENA_O_IMITACION = "AJENA_O_IMITACION"
SIN_ESQUEMA = "SIN_ESQUEMA"
NO_SQLITE_O_CORRUPTA = "NO_SQLITE_O_CORRUPTA"

POLITICA_NO_APROBADA = "NO_APROBADA"

COHERENTE = "COHERENTE"
FALSO_NEGATIVO = "FALSO_NEGATIVO"
FALSO_POSITIVO = "FALSO_POSITIVO"
TOLERANCIA_A_REVISAR = "TOLERANCIA_A_REVISAR"

_FUNCIONES_PROHIBIDAS_EXACTAS = frozenset(
    {"crear_base", "conectar", "_inicializar_base", "agregar_columna_si_falta"}
)
_PREFIJOS_FUNCIONES_PROHIBIDAS = ("migrar_", "crear_tabla_", "completar_")
_PREFIJOS_LECTURA = ("SELECT", "PRAGMA", "WITH")
_PRAGMA_ASIGNACION = re.compile(r"^\s*PRAGMA\s+[\w.]+\s*=", re.IGNORECASE)
_SUFIJOS_AUXILIARES = ("-journal", "-wal", "-shm")


def _sentencias_esquema(nombre):
    return tuple(sql for _, _, _, sql in ESQUEMAS_HISTORICOS[nombre][2])


def _sentencias_referencia(*, omitir=(), reemplazos=()):
    sentencias = []
    for _, nombre, _, sql in ESQUEMAS_HISTORICOS["arca_config_ambiente_599d0f5"][2]:
        if nombre in omitir:
            continue
        for tabla, original, nuevo in reemplazos:
            if nombre == tabla:
                if original not in sql:
                    raise AssertionError(f"Fragmento ausente en {tabla}: {original}")
                sql = sql.replace(original, nuevo, 1)
        sentencias.append(sql)
    return tuple(sentencias)


def _columnas_obligatorias(conexion, tabla):
    return [
        (fila[1], (fila[2] or "").upper())
        for fila in conexion.execute(f'PRAGMA table_info("{tabla}")')
        if fila[3] and fila[4] is None and not fila[5]
    ]


def _insertar_minimo(conexion, tabla, valores):
    """Inserta completando columnas NOT NULL sin default con valores ficticios."""
    datos = dict(valores)
    for columna, tipo in _columnas_obligatorias(conexion, tabla):
        if columna not in datos:
            datos[columna] = 1 if ("INT" in tipo or "REAL" in tipo) else "ficticio"
    columnas = ", ".join(f'"{c}"' for c in datos)
    marcadores = ", ".join("?" for _ in datos)
    conexion.execute(f'INSERT INTO "{tabla}" ({columnas}) VALUES ({marcadores})', tuple(datos.values()))


def _sha256(ruta):
    return hashlib.sha256(Path(ruta).read_bytes()).hexdigest()


def _estado_fisico(ruta, *, leer_shm=False):
    ruta = Path(ruta)
    estado = {"principal": (ruta.stat().st_size, ruta.stat().st_mtime_ns, _sha256(ruta))}
    for sufijo in _SUFIJOS_AUXILIARES:
        auxiliar = Path(str(ruta) + sufijo)
        if not auxiliar.exists():
            estado[sufijo] = None
        elif sufijo == "-shm" and not leer_shm:
            # SQLite mantiene bloqueos de rango sobre -shm; solo se compara existencia y tamaño.
            estado[sufijo] = (auxiliar.stat().st_size,)
        else:
            estado[sufijo] = (auxiliar.stat().st_size, _sha256(auxiliar))
    return estado


def _auxiliares_existentes(ruta):
    return {s for s in _SUFIJOS_AUXILIARES if Path(str(ruta) + s).exists()}


@dataclass(frozen=True)
class Caso:
    nombre: str
    construir: object
    estado_observado: str
    compatibilidad: str
    hallazgo: str
    motivos_contienen: tuple = ()
    pendientes_contienen: tuple = ()
    instalacion_nueva_confirmada: bool = False
    politica_futura: str = POLITICA_NO_APROBADA


class _BaseFicticia(unittest.TestCase):

    def setUp(self):
        directorio = tempfile.TemporaryDirectory(prefix="fm_3d4c5c2_")
        self.addCleanup(directorio.cleanup)
        self.raiz = Path(directorio.name).resolve()

    def ruta(self, nombre):
        return self.raiz / f"{nombre}.db"

    def _verificar_ruta_temporal(self, ruta):
        ruta = Path(ruta).resolve()
        self.assertIn(self.raiz, ruta.parents, "Ruta SQLite fuera del directorio temporal")
        self.assertNotEqual(ruta.name.lower(), "fm_master.db")

    def construir(self, nombre, sentencias=(), *, journal="DELETE", datos=None, mantener_abierta=False):
        ruta = self.ruta(nombre)
        self._verificar_ruta_temporal(ruta)
        conexion = sqlite3.connect(ruta)
        try:
            modo = conexion.execute(f"PRAGMA journal_mode={journal}").fetchone()[0]
            self.assertEqual(modo.upper(), journal)
            if journal == "WAL":
                conexion.execute("PRAGMA wal_autocheckpoint=0")
            for sql in sentencias:
                conexion.execute(sql)
            if datos is not None:
                datos(conexion)
            conexion.commit()
        except BaseException:
            conexion.close()
            raise
        if mantener_abierta:
            self.addCleanup(conexion.close)
            return ruta, conexion
        conexion.close()
        return ruta

    def escribir_bytes(self, nombre, contenido):
        ruta = self.ruta(nombre)
        self._verificar_ruta_temporal(ruta)
        ruta.write_bytes(contenido)
        return ruta

    @contextmanager
    def _guardas(self):
        with ExitStack() as pila:
            simulados = {}
            for nombre in dir(database):
                if nombre in _FUNCIONES_PROHIBIDAS_EXACTAS or nombre.startswith(
                    _PREFIJOS_FUNCIONES_PROHIBIDAS
                ):
                    if callable(getattr(database, nombre)):
                        simulados[nombre] = pila.enter_context(
                            patch.object(
                                database, nombre, side_effect=AssertionError(f"Prohibido: {nombre}")
                            )
                        )
            simulados["sqlite3.connect"] = pila.enter_context(
                patch.object(
                    sqlite3, "connect", side_effect=AssertionError("Conexión nueva prohibida")
                )
            )
            yield simulados
        llamados = sorted(nombre for nombre, simulado in simulados.items() if simulado.called)
        self.assertEqual(llamados, [], "Se invocaron funciones prohibidas durante la inspección")

    def inspeccionar(self, ruta, **kwargs):
        """Inspección de solo lectura: mode=ro, sin conexiones nuevas ni escrituras."""
        self._verificar_ruta_temporal(ruta)
        conexion = sqlite3.connect(Path(ruta).as_uri() + "?mode=ro", uri=True)
        sentencias = []
        try:
            conexion.set_trace_callback(sentencias.append)
            cambios = conexion.total_changes
            with self._guardas() as simulados:
                resultado = database.inspeccionar_estado_base_sqlite(conexion, **kwargs)
            conexion.set_trace_callback(None)
            self.assertGreater(len(simulados), 4)
            self.assertEqual(conexion.total_changes, cambios)
            self.assertFalse(conexion.in_transaction)
        finally:
            conexion.close()
        for sentencia in sentencias:
            texto = sentencia.lstrip().upper()
            self.assertTrue(texto.startswith(_PREFIJOS_LECTURA), f"Sentencia no lectora: {sentencia[:80]}")
            self.assertIsNone(_PRAGMA_ASIGNACION.match(sentencia), f"PRAGMA de escritura: {sentencia[:80]}")
        decision = database.evaluar_autorizacion_arranque_sqlite(resultado)
        self.assertFalse(decision.autorizado)
        self.assertEqual(decision.estado, resultado.estado)
        return resultado


# ---------------------------------------------------------------------------
# Catálogo de casos. ``construir`` recibe la prueba y devuelve la ruta ficticia.
# ---------------------------------------------------------------------------

def _historico(nombre, journal="DELETE"):
    return lambda prueba: prueba.construir(nombre, _sentencias_esquema(nombre), journal=journal)


def _referencia(nombre, *, omitir=(), reemplazos=(), posteriores=(), datos=None):
    return lambda prueba: prueba.construir(
        nombre, _sentencias_referencia(omitir=omitir, reemplazos=reemplazos) + tuple(posteriores), datos=datos
    )


def _imitacion(con_indices):
    def construir(prueba):
        referencia = sqlite3.connect(":memory:")
        try:
            for sql in _sentencias_referencia():
                referencia.execute(sql)
            tablas = [
                fila[0]
                for fila in referencia.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY rowid"
                )
            ]
            sentencias = []
            for tabla in tablas:
                columnas = [fila[1] for fila in referencia.execute(f'PRAGMA table_info("{tabla}")')]
                definicion = ", ".join(
                    '"id" INTEGER PRIMARY KEY' if c == "id" else f'"{c}"' for c in columnas
                )
                sentencias.append(f'CREATE TABLE "{tabla}" ({definicion})')
        finally:
            referencia.close()
        if con_indices:
            sentencias += [
                sql for tipo, _, _, sql in ESQUEMAS_HISTORICOS["arca_config_ambiente_599d0f5"][2] if tipo == "index"
            ]
        return prueba.construir("imitacion_" + ("con" if con_indices else "sin") + "_indices", sentencias)

    return construir


def _cae_duplicado(conexion):
    for identificador in (1, 2):
        _insertar_minimo(
            conexion,
            "factura_arca",
            {"id": identificador, "cae": "70000000000001", "ambiente_arca": "homologacion"},
        )


def _corrupcion_en_todas_las_paginas(prueba):
    ruta = prueba.construir("corrupta_todas", _sentencias_referencia())
    contenido = bytearray(ruta.read_bytes())
    for desplazamiento in range(4096, len(contenido), 4096):
        contenido[desplazamiento + 8:desplazamiento + 60] = b"\xa5" * 52
    ruta.write_bytes(bytes(contenido))
    return ruta


def _cabecera_rota(prueba):
    ruta = prueba.construir("cabecera_rota", _sentencias_referencia())
    contenido = bytearray(ruta.read_bytes())
    contenido[0:16] = b"NO ES SQLITE !!!"
    ruta.write_bytes(bytes(contenido))
    return ruta


def _corrupcion_sutil_tareas(prueba):
    ruta = prueba.construir("corrupcion_sutil", _sentencias_referencia())
    conexion = sqlite3.connect(Path(ruta).as_uri() + "?mode=ro", uri=True)
    try:
        raiz = conexion.execute("SELECT rootpage FROM sqlite_master WHERE name='tareas'").fetchone()[0]
        tamano = conexion.execute("PRAGMA page_size").fetchone()[0]
    finally:
        conexion.close()
    contenido = bytearray(ruta.read_bytes())
    desplazamiento = (raiz - 1) * tamano
    # Hoja de tabla que declara 5 celdas inexistentes; solo afecta a "tareas".
    contenido[desplazamiento:desplazamiento + 8] = b"\x0d\x00\x00\x00\x05\xff\xff\x00"
    ruta.write_bytes(bytes(contenido))
    return ruta


def _fk_huerfana(conexion):
    _insertar_minimo(conexion, "servicios", {"id": 1, "cliente_id": 999})


_IDX_CAE = "idx_factura_arca_cae_unico"
_IDX_CAE_HIST = "idx_factura_arca_cae_historico_unico"
_IDX_IDENTIDAD = "idx_factura_arca_identidad_unica"

CASOS_HISTORICOS = (
    Caso("build_0_2_2_9b6a850", _historico("build_0_2_2_9b6a850"), "BLOQUEADA", LEGITIMA_DEMOSTRADA,
         FALSO_NEGATIVO, motivos_contienen=("tabla_esencial_ausente:servicios",)),
    Caso("build_0_5_52b0189", _historico("build_0_5_52b0189"), "BLOQUEADA", LEGITIMA_DEMOSTRADA,
         FALSO_NEGATIVO, motivos_contienen=("tabla_esencial_ausente:catalogo_servicios",)),
    Caso("build_0_7_8c81526", _historico("build_0_7_8c81526"), "BLOQUEADA", LEGITIMA_DEMOSTRADA,
         FALSO_NEGATIVO, motivos_contienen=("tabla_esencial_ausente:catalogo_servicios",)),
    Caso("build_1_7_4994dc6", _historico("build_1_7_4994dc6"), "BLOQUEADA", LEGITIMA_DEMOSTRADA,
         FALSO_NEGATIVO, motivos_contienen=("tabla_esencial_ausente:emisores_fiscales",)),
    Caso("esenciales_16_8a362a5", _historico("esenciales_16_8a362a5"), "INCOMPLETA", LEGITIMA_DEMOSTRADA,
         COHERENTE, pendientes_contienen=("tabla:emisor_fiscal_arca_config", "columna:factura_arca.punto_venta_num")),
    Caso("arca_intentos_af3e31e", _historico("arca_intentos_af3e31e"), "INCOMPLETA", LEGITIMA_DEMOSTRADA,
         COHERENTE, pendientes_contienen=("tabla:emisor_fiscal_arca_config", "columna:factura_arca.punto_venta_num")),
    Caso("arca_indices_unicos_0fe8ac7", _historico("arca_indices_unicos_0fe8ac7"), "INCOMPLETA",
         LEGITIMA_DEMOSTRADA, COHERENTE,
         pendientes_contienen=("tabla:emisor_fiscal_arca_config", "columna:factura_arca.ambiente_arca")),
    Caso("arca_config_ambiente_599d0f5", _historico("arca_config_ambiente_599d0f5"), "HISTORICA_SIN_VERSION",
         LEGITIMA_DEMOSTRADA, COHERENTE),
)

CASOS_NEGATIVOS = (
    Caso("archivo_vacio", lambda p: p.escribir_bytes("vacio", b""), "BLOQUEADA", SIN_ESQUEMA, COHERENTE,
         motivos_contienen=("confirmación explícita",)),
    Caso("archivo_vacio_confirmado", lambda p: p.escribir_bytes("vacio_confirmado", b""), "NUEVA", SIN_ESQUEMA,
         TOLERANCIA_A_REVISAR, instalacion_nueva_confirmada=True),
    Caso("sqlite_sin_tablas", lambda p: p.construir("sin_tablas"), "BLOQUEADA", SIN_ESQUEMA, COHERENTE,
         motivos_contienen=("confirmación explícita",)),
    Caso("sqlite_sin_tablas_confirmado", lambda p: p.construir("sin_tablas_confirmado"), "NUEVA", SIN_ESQUEMA,
         COHERENTE, instalacion_nueva_confirmada=True),
    Caso("archivo_texto", lambda p: p.escribir_bytes("texto", b"no es sqlite " * 400), "BLOQUEADA",
         NO_SQLITE_O_CORRUPTA, COHERENTE, motivos_contienen=("DatabaseError",)),
    Caso("cabecera_rota", _cabecera_rota, "BLOQUEADA", NO_SQLITE_O_CORRUPTA, COHERENTE,
         motivos_contienen=("DatabaseError",)),
    Caso("corrupcion_todas_las_paginas", _corrupcion_en_todas_las_paginas, "BLOQUEADA", NO_SQLITE_O_CORRUPTA,
         COHERENTE, motivos_contienen=("DatabaseError",)),
    Caso("corrupcion_sutil_tabla_no_leida", _corrupcion_sutil_tareas, "HISTORICA_SIN_VERSION",
         NO_SQLITE_O_CORRUPTA, FALSO_POSITIVO),
    Caso("otra_aplicacion", lambda p: p.construir("ajena", (
        "CREATE TABLE users(id INTEGER PRIMARY KEY, email TEXT)",
        "CREATE TABLE orders(id INTEGER PRIMARY KEY, user_id INTEGER)")),
         "BLOQUEADA", AJENA_O_IMITACION, COHERENTE, motivos_contienen=("tabla_esencial_ausente:clientes",)),
    Caso("otra_aplicacion_con_tabla_clientes", lambda p: p.construir("ajena_clientes", (
        "CREATE TABLE clientes(id INTEGER PRIMARY KEY, nombre TEXT)",)),
         "BLOQUEADA", AJENA_O_IMITACION, COHERENTE, motivos_contienen=("tabla_esencial_ausente:servicios",)),
    Caso("imitacion_nombres_sin_indices", _imitacion(False), "INCOMPLETA", AJENA_O_IMITACION, FALSO_POSITIVO,
         pendientes_contienen=("indice:" + _IDX_IDENTIDAD,)),
    Caso("imitacion_nombres_con_indices", _imitacion(True), "HISTORICA_SIN_VERSION", AJENA_O_IMITACION,
         FALSO_POSITIVO),
    Caso("parcial_sin_tabla_config_ambiente",
         _referencia("parcial_config", omitir=("emisor_fiscal_arca_config",)),
         "INCOMPLETA", LEGITIMA_ALTERADA, COHERENTE, pendientes_contienen=("tabla:emisor_fiscal_arca_config",)),
    Caso("parcial_sin_indice_cae", _referencia("parcial_cae", omitir=(_IDX_CAE,)), "INCOMPLETA",
         LEGITIMA_ALTERADA, COHERENTE, pendientes_contienen=("indice:" + _IDX_CAE,)),
    Caso("contradiccion_trigger", _referencia("trigger", posteriores=(
        "CREATE TRIGGER tr_ficticio AFTER INSERT ON clientes BEGIN SELECT 1; END",)),
         "BLOQUEADA", LEGITIMA_ALTERADA, COHERENTE, motivos_contienen=("trigger_no_reconocido:tr_ficticio",)),
    Caso("contradiccion_pk_texto", _referencia("pk_texto", reemplazos=(
        ("clientes", "id INTEGER PRIMARY KEY AUTOINCREMENT", "id TEXT PRIMARY KEY"),)),
         "BLOQUEADA", LEGITIMA_ALTERADA, COHERENTE, motivos_contienen=("clave_primaria_incompatible:clientes",)),
    Caso("contradiccion_cae_duplicado", _referencia("cae_duplicado", omitir=(_IDX_CAE, _IDX_CAE_HIST),
                                                    datos=_cae_duplicado),
         "BLOQUEADA", LEGITIMA_ALTERADA, COHERENTE, motivos_contienen=("duplicados:factura_arca.cae",)),
    Caso("marcador_user_version_7", _referencia("uv7", posteriores=("PRAGMA user_version=7",)),
         "VERSION_INCOMPATIBLE", LEGITIMA_ALTERADA, COHERENTE, motivos_contienen=("user_version=7",)),
    Caso("marcador_user_version_negativo", _referencia("uvneg", posteriores=("PRAGMA user_version=-1",)),
         "VERSION_INCOMPATIBLE", LEGITIMA_ALTERADA, COHERENTE, motivos_contienen=("user_version=-1",)),
    Caso("marcador_schema_migrations", _referencia("sm", posteriores=("CREATE TABLE schema_migrations(v)",)),
         "VERSION_INCOMPATIBLE", LEGITIMA_ALTERADA, COHERENTE, motivos_contienen=("schema_migrations",)),
    Caso("marcador_database_migrations", _referencia("dm", posteriores=("CREATE TABLE database_migrations(v)",)),
         "VERSION_INCOMPATIBLE", LEGITIMA_ALTERADA, COHERENTE, motivos_contienen=("database_migrations",)),
    Caso("marcador_migraciones_esquema", _referencia("me", posteriores=("CREATE TABLE migraciones_esquema(v)",)),
         "VERSION_INCOMPATIBLE", LEGITIMA_ALTERADA, COHERENTE, motivos_contienen=("migraciones_esquema",)),
    Caso("marcador_application_id_ignorado", _referencia("appid", posteriores=("PRAGMA application_id=1179468372",)),
         "HISTORICA_SIN_VERSION", LEGITIMA_ALTERADA, FALSO_POSITIVO),
    Caso("marcador_alembic_version_ignorado", _referencia("alembic", posteriores=("CREATE TABLE alembic_version(v)",)),
         "HISTORICA_SIN_VERSION", LEGITIMA_ALTERADA, FALSO_POSITIVO),
    Caso("tabla_ajena_adicional", _referencia("tabla_extra", posteriores=("CREATE TABLE users(id INTEGER PRIMARY KEY)",)),
         "HISTORICA_SIN_VERSION", LEGITIMA_ALTERADA, TOLERANCIA_A_REVISAR),
    Caso("vista_adicional", _referencia("vista", posteriores=("CREATE VIEW v_ficticia AS SELECT * FROM clientes",)),
         "HISTORICA_SIN_VERSION", LEGITIMA_ALTERADA, TOLERANCIA_A_REVISAR),
    Caso("indice_cae_sin_where", _referencia("cae_sin_where", omitir=(_IDX_CAE,), posteriores=(
        f"CREATE UNIQUE INDEX {_IDX_CAE} ON factura_arca(cae)",)),
         "INCOMPLETA", LEGITIMA_ALTERADA, TOLERANCIA_A_REVISAR, pendientes_contienen=("indice_incompatible:" + _IDX_CAE,)),
    Caso("indice_cae_no_unico", _referencia("cae_no_unico", omitir=(_IDX_CAE,), posteriores=(
        f"CREATE INDEX {_IDX_CAE} ON factura_arca(cae) WHERE cae IS NOT NULL",)),
         "INCOMPLETA", LEGITIMA_ALTERADA, TOLERANCIA_A_REVISAR, pendientes_contienen=("indice_incompatible:" + _IDX_CAE,)),
    Caso("indice_identidad_columnas_ajenas", _referencia("identidad_ajena", omitir=(_IDX_IDENTIDAD,), posteriores=(
        f"CREATE UNIQUE INDEX {_IDX_IDENTIDAD} ON factura_arca(id)",)),
         "INCOMPLETA", LEGITIMA_ALTERADA, TOLERANCIA_A_REVISAR,
         pendientes_contienen=("indice_incompatible:" + _IDX_IDENTIDAD,)),
    Caso("restriccion_unique_resumenes_ausente", _referencia("resumenes_sin_unique", reemplazos=(
        ("resumenes", "numero INTEGER NOT NULL UNIQUE", "numero INTEGER"),)),
         "HISTORICA_SIN_VERSION", LEGITIMA_ALTERADA, FALSO_POSITIVO),
    Caso("tipo_columna_cae_blob", _referencia("cae_blob", reemplazos=(("factura_arca", "cae TEXT", "cae BLOB"),)),
         "HISTORICA_SIN_VERSION", LEGITIMA_ALTERADA, FALSO_POSITIVO),
    Caso("clave_foranea_huerfana", _referencia("fk_huerfana", datos=_fk_huerfana),
         "HISTORICA_SIN_VERSION", LEGITIMA_ALTERADA, FALSO_POSITIVO),
)


class EsquemasHistoricosCongeladosTest(unittest.TestCase):
    """Comprueba la coherencia interna del DDL congelado (no consulta el detector)."""

    TABLAS_ESPERADAS = {
        "build_0_2_2_9b6a850": {"clientes"},
        "build_0_5_52b0189": {"clientes", "servicios"},
        "build_0_7_8c81526": {"clientes", "servicios", "resumenes", "resumen_conceptos", "cobros"},
        "build_1_7_4994dc6": {"clientes", "servicios", "servicio_renovaciones", "resumenes",
                              "resumen_conceptos", "cobros", "tareas"},
    }
    ESENCIALES_16 = {
        "clientes", "servicios", "catalogo_servicios", "emisores_facturacion", "emisores_fiscales",
        "arca_config", "servicio_renovaciones", "resumenes", "resumen_conceptos", "cobros", "tareas",
        "contactos", "factura_arca", "oportunidades", "notificaciones", "usuarios",
    }

    def _tablas(self, nombre):
        return {n for tipo, n, _, _ in ESQUEMAS_HISTORICOS[nombre][2] if tipo == "table"}

    def test_tablas_de_cada_build_historico(self):
        for nombre, tablas in self.TABLAS_ESPERADAS.items():
            with self.subTest(nombre=nombre):
                self.assertEqual(self._tablas(nombre), tablas)
        self.assertEqual(self._tablas("esenciales_16_8a362a5"), self.ESENCIALES_16)
        self.assertEqual(self._tablas("arca_intentos_af3e31e"), self.ESENCIALES_16 | {"intentos_emision_arca"})
        self.assertEqual(self._tablas("arca_indices_unicos_0fe8ac7"), self.ESENCIALES_16 | {"intentos_emision_arca"})
        self.assertEqual(
            self._tablas("arca_config_ambiente_599d0f5"),
            self.ESENCIALES_16 | {"intentos_emision_arca", "emisor_fiscal_arca_config"},
        )

    def test_ningun_esquema_historico_declara_triggers_ni_marcadores_de_version(self):
        for nombre, (commit, _, objetos) in ESQUEMAS_HISTORICOS.items():
            with self.subTest(nombre=nombre, commit=commit):
                self.assertTrue(nombre.endswith(commit))
                self.assertNotIn("trigger", {tipo for tipo, _, _, _ in objetos})
                texto = " ".join(sql for _, _, _, sql in objetos).lower()
                for marcador in ("user_version", "application_id", "schema_migrations"):
                    self.assertNotIn(marcador, texto)

    def test_ddl_congelado_es_reproducible_en_memoria(self):
        for nombre in ESQUEMAS_HISTORICOS:
            with self.subTest(nombre=nombre):
                conexion = sqlite3.connect(":memory:")
                try:
                    for sql in _sentencias_esquema(nombre):
                        conexion.execute(sql)
                    self.assertEqual(conexion.execute("PRAGMA user_version").fetchone()[0], 0)
                    self.assertEqual(conexion.execute("PRAGMA integrity_check").fetchone()[0], "ok")
                finally:
                    conexion.close()


class ClasificacionObservadaTest(_BaseFicticia):
    """Fija la clasificación real del detector actual; no constituye política."""

    def _ejecutar(self, caso):
        ruta = caso.construir(self)
        antes = _estado_fisico(ruta)
        auxiliares_antes = _auxiliares_existentes(ruta)
        resultado = self.inspeccionar(ruta, instalacion_nueva_confirmada=caso.instalacion_nueva_confirmada)
        self.assertEqual(_estado_fisico(ruta), antes, "La inspección alteró el archivo o sus auxiliares")
        self.assertEqual(_auxiliares_existentes(ruta), auxiliares_antes)
        return resultado

    def _verificar(self, caso, resultado):
        self.assertEqual(caso.politica_futura, POLITICA_NO_APROBADA)
        self.assertEqual(resultado.estado, caso.estado_observado, resultado.motivos)
        self.assertNotEqual(resultado.estado, "ACTUAL")
        motivos = " ".join(resultado.motivos)
        for fragmento in caso.motivos_contienen:
            self.assertIn(fragmento, motivos)
        for estructura in caso.pendientes_contienen:
            self.assertIn(estructura, resultado.estructuras_pendientes)

    def test_esquemas_historicos_legitimos(self):
        for caso in CASOS_HISTORICOS:
            with self.subTest(caso=caso.nombre):
                self.assertEqual(caso.compatibilidad, LEGITIMA_DEMOSTRADA)
                self._verificar(caso, self._ejecutar(caso))

    def test_casos_negativos_e_incompatibles(self):
        for caso in CASOS_NEGATIVOS:
            with self.subTest(caso=caso.nombre):
                self.assertNotEqual(caso.compatibilidad, LEGITIMA_DEMOSTRADA)
                self._verificar(caso, self._ejecutar(caso))

    def test_ningun_esquema_historico_legitimo_es_reconocido_como_bloqueado_por_version(self):
        for caso in CASOS_HISTORICOS:
            with self.subTest(caso=caso.nombre):
                resultado = self._ejecutar(caso)
                self.assertNotEqual(resultado.estado, "VERSION_INCOMPATIBLE")
                self.assertIsNone(resultado.version_registrada)

    def test_historica_sin_version_no_se_convierte_en_autorizacion(self):
        caso = CASOS_HISTORICOS[-1]
        resultado = self._ejecutar(caso)
        self.assertEqual(resultado.estado, "HISTORICA_SIN_VERSION")
        decision = database.evaluar_autorizacion_arranque_sqlite(resultado)
        self.assertFalse(decision.autorizado)
        self.assertTrue(decision.motivo_denegacion)

    def test_catalogo_de_casos_es_consistente(self):
        nombres = [c.nombre for c in CASOS_HISTORICOS + CASOS_NEGATIVOS]
        self.assertEqual(len(nombres), len(set(nombres)))
        for caso in CASOS_HISTORICOS + CASOS_NEGATIVOS:
            self.assertEqual(caso.politica_futura, POLITICA_NO_APROBADA)
            self.assertIn(caso.hallazgo, {COHERENTE, FALSO_NEGATIVO, FALSO_POSITIVO, TOLERANCIA_A_REVISAR})


class GuardasDeSoloLecturaTest(_BaseFicticia):

    def test_guardas_detectan_crear_base_y_migraciones(self):
        with self.assertRaises(AssertionError):
            with self._guardas():
                database.crear_base()
        with self.assertRaises(AssertionError):
            with self._guardas():
                database.migrar_indices_unicos_factura_arca(None)

    def test_guardas_detectan_conexiones_nuevas(self):
        with self.assertRaises(AssertionError):
            with self._guardas():
                sqlite3.connect(":memory:")

    def test_inspeccion_no_altera_sqlite_master_ni_datos(self):
        ruta = self.construir("esquema_estable", _sentencias_referencia(), datos=_fk_huerfana)
        consulta = "SELECT type, name, tbl_name, sql FROM sqlite_master ORDER BY rowid"

        def instantanea():
            conexion = sqlite3.connect(ruta.as_uri() + "?mode=ro", uri=True)
            try:
                return conexion.execute(consulta).fetchall(), conexion.execute("SELECT * FROM servicios").fetchall()
            finally:
                conexion.close()

        antes = instantanea()
        self.inspeccionar(ruta)
        self.assertEqual(instantanea(), antes)


class SeguridadFisicaDeLecturaTest(_BaseFicticia):
    """DELETE y WAL separados; compara hashes y archivos auxiliares."""

    def test_delete_no_crea_auxiliares_ni_modifica_principal(self):
        for nombre in ESQUEMAS_HISTORICOS:
            with self.subTest(nombre=nombre):
                ruta = self.construir("del_" + nombre, _sentencias_esquema(nombre), journal="DELETE")
                antes = _estado_fisico(ruta)
                self.inspeccionar(ruta)
                self.assertEqual(_estado_fisico(ruta), antes)
                self.assertEqual(_auxiliares_existentes(ruta), set())

    def test_wal_con_escritor_activo_conserva_principal_y_wal(self):
        for nombre in ESQUEMAS_HISTORICOS:
            with self.subTest(nombre=nombre):
                ruta, creador = self.construir(
                    "wal_" + nombre, _sentencias_esquema(nombre), journal="WAL", mantener_abierta=True
                )
                self.assertEqual(_auxiliares_existentes(ruta), {"-wal", "-shm"})
                antes = _estado_fisico(ruta)
                resultado = self.inspeccionar(ruta)
                self.assertEqual(_estado_fisico(ruta), antes)
                creador.close()
                caso = next(c for c in CASOS_HISTORICOS if c.nombre == nombre)
                self.assertEqual(resultado.estado, caso.estado_observado)

    def test_wal_cerrada_conserva_principal_pero_crea_auxiliares(self):
        """Limitación observada: mode=ro sobre WAL sin -wal/-shm los crea en disco."""
        ruta = self.construir("wal_cerrada", _sentencias_referencia(), journal="WAL")
        self.assertEqual(_auxiliares_existentes(ruta), set())
        principal = _estado_fisico(ruta)["principal"]
        resultado = self.inspeccionar(ruta)
        self.assertEqual(resultado.estado, "HISTORICA_SIN_VERSION")
        self.assertEqual(_estado_fisico(ruta)["principal"], principal)
        self.assertEqual(_auxiliares_existentes(ruta), {"-wal", "-shm"})
        self.assertEqual(Path(str(ruta) + "-wal").stat().st_size, 0)


if __name__ == "__main__":
    unittest.main()
