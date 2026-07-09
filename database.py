import sqlite3
import calendar
from datetime import date, datetime

from runtime_paths import DATABASE_PATH

DB_NAME = str(DATABASE_PATH)


def conectar():
    return sqlite3.connect(DB_NAME)


def agregar_columna_si_falta(cur, tabla, columna, definicion):
    cur.execute(f"PRAGMA table_info({tabla})")
    columnas = {fila[1] for fila in cur.fetchall()}

    if columna not in columnas:
        cur.execute(f"ALTER TABLE {tabla} ADD COLUMN {columna} {definicion}")


def sumar_un_mes(fecha):
    anio = fecha.year + (1 if fecha.month == 12 else 0)
    mes = 1 if fecha.month == 12 else fecha.month + 1
    dia = min(fecha.day, calendar.monthrange(anio, mes)[1])
    return date(anio, mes, dia)


def crear_base():

    conn = conectar()
    cur = conn.cursor()

    # ==========================
    # TABLA CLIENTES
    # ==========================

    cur.execute("""
    CREATE TABLE IF NOT EXISTS clientes(

        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nombre TEXT NOT NULL DEFAULT '',
        codigo TEXT,
        razon_social TEXT,
        nombre_comercial TEXT,
        responsable TEXT,
        direccion TEXT,
        localidad TEXT,
        telefono TEXT,
        whatsapp TEXT,
        email TEXT,
        cuit TEXT,
        iva TEXT,
        tipo_factura TEXT DEFAULT 'No factura',
        monotributo_facturacion TEXT DEFAULT 'No aplica',
        emisor_id INTEGER,
        emisor_recomendado_id INTEGER,
        vencimiento INTEGER,
        estado TEXT,
        observaciones TEXT,
        fecha_alta TEXT,
        fecha_modificacion TEXT

    )
    """)

    columnas_clientes = {
        "nombre": "TEXT NOT NULL DEFAULT ''",
        "codigo": "TEXT",
        "razon_social": "TEXT",
        "nombre_comercial": "TEXT",
        "responsable": "TEXT",
        "direccion": "TEXT",
        "localidad": "TEXT",
        "telefono": "TEXT",
        "whatsapp": "TEXT",
        "email": "TEXT",
        "cuit": "TEXT",
        "iva": "TEXT",
        "tipo_factura": "TEXT DEFAULT 'No factura'",
        "monotributo_facturacion": "TEXT DEFAULT 'No aplica'",
        "vencimiento": "INTEGER",
        "estado": "TEXT",
        "observaciones": "TEXT",
        "fecha_alta": "TEXT",
        "fecha_modificacion": "TEXT"
    }

    for columna, definicion in columnas_clientes.items():
        agregar_columna_si_falta(cur, "clientes", columna, definicion)
    # Añadir columnas para emisores en clientes si no existen
    agregar_columna_si_falta(cur, "clientes", "emisor_id", "INTEGER")
    agregar_columna_si_falta(cur, "clientes", "emisor_recomendado_id", "INTEGER")

    # ==========================
    # TABLA SERVICIOS
    # ==========================

    cur.execute("""
    CREATE TABLE IF NOT EXISTS servicios(

        id INTEGER PRIMARY KEY AUTOINCREMENT,
        cliente_id INTEGER NOT NULL,
        concepto TEXT NOT NULL,
        descripcion TEXT,
        cantidad INTEGER DEFAULT 1,
        importe REAL NOT NULL,
        descuento REAL DEFAULT 0,
        activo INTEGER DEFAULT 1,
        fecha_inicio TEXT,
        fecha_fin TEXT,
        renovable INTEGER DEFAULT 1,
        estado_periodo TEXT DEFAULT 'Activo',

        FOREIGN KEY(cliente_id)
        REFERENCES clientes(id)

    )
    """)

    columnas_servicios = {
        "cliente_id": "INTEGER",
        "concepto": "TEXT",
        "descripcion": "TEXT",
        "cantidad": "REAL DEFAULT 1",
        "importe": "REAL DEFAULT 0",
        "descuento": "REAL DEFAULT 0",
        "activo": "INTEGER DEFAULT 1",
        "fecha_inicio": "TEXT",
        "fecha_fin": "TEXT",
        "renovable": "INTEGER DEFAULT 1",
        "estado_periodo": "TEXT DEFAULT 'Activo'"
    }

    for columna, definicion in columnas_servicios.items():
        agregar_columna_si_falta(cur, "servicios", columna, definicion)

    # ==========================
    # CATALOGO DE SERVICIOS
    # ==========================
    cur.execute("""
    CREATE TABLE IF NOT EXISTS catalogo_servicios(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nombre TEXT NOT NULL,
        descripcion TEXT,
        precio REAL NOT NULL DEFAULT 0,
        activo INTEGER DEFAULT 1
    )
    """)

    columnas_catalogo = {
        "nombre": "TEXT",
        "descripcion": "TEXT",
        "precio": "REAL DEFAULT 0",
        "activo": "INTEGER DEFAULT 1",
    }
    for columna, definicion in columnas_catalogo.items():
        agregar_columna_si_falta(cur, "catalogo_servicios", columna, definicion)

    # ==========================
    # EMISORES DE FACTURACION
    # ==========================
    cur.execute("""
    CREATE TABLE IF NOT EXISTS emisores_facturacion(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        alias TEXT NOT NULL,
        titular TEXT,
        nombre TEXT,
        cuit TEXT,
        condicion_iva TEXT,
        punto_venta TEXT,
        tipo_comprobante_default TEXT,
        orden_prioridad INTEGER DEFAULT 0,
        direccion TEXT,
        localidad TEXT,
        telefono TEXT,
        email TEXT,
        activo INTEGER DEFAULT 1,
        observaciones TEXT,
        certificado_path TEXT,
        clave_privada_path TEXT,
        arca_modo TEXT DEFAULT 'Homologación',
        arca_estado TEXT DEFAULT 'Desconocido'
    )
    """)

    columnas_emisores = {
        "alias": "TEXT",
        "titular": "TEXT",
        "nombre": "TEXT",
        "cuit": "TEXT",
        "condicion_iva": "TEXT",
        "punto_venta": "TEXT",
        "tipo_comprobante_default": "TEXT",
        "orden_prioridad": "INTEGER DEFAULT 0",
        "direccion": "TEXT",
        "localidad": "TEXT",
        "telefono": "TEXT",
        "email": "TEXT",
        "activo": "INTEGER DEFAULT 1",
        "observaciones": "TEXT",
        "certificado_path": "TEXT",
        "clave_privada_path": "TEXT",
        "arca_modo": "TEXT DEFAULT 'Homologación'",
        "arca_estado": "TEXT DEFAULT 'Desconocido'",
    }
    for columna, definicion in columnas_emisores.items():
        agregar_columna_si_falta(cur, "emisores_facturacion", columna, definicion)

    # ==========================
    # EMISORES FISCALES (PRE-ARCA)
    # ==========================
    cur.execute("""
    CREATE TABLE IF NOT EXISTS emisores_fiscales(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        razon_social TEXT NOT NULL,
        nombre_fantasia TEXT,
        cuit TEXT,
        condicion_iva TEXT,
        tipo_factura TEXT,
        punto_venta TEXT,
        activo INTEGER DEFAULT 1,
        observaciones TEXT
    )
    """)

    columnas_emisores_fiscales = {
        "razon_social": "TEXT NOT NULL DEFAULT ''",
        "nombre_fantasia": "TEXT",
        "cuit": "TEXT",
        "condicion_iva": "TEXT",
        "tipo_factura": "TEXT",
        "punto_venta": "TEXT",
        "activo": "INTEGER DEFAULT 1",
        "observaciones": "TEXT",
    }
    for columna, definicion in columnas_emisores_fiscales.items():
        agregar_columna_si_falta(cur, "emisores_fiscales", columna, definicion)

    emisores_iniciales = [
        (
            "Ibarrondo Adrian Oscar",
            "F.M. Master 98.3",
            "20-20687162-9",
            "Monotributo",
            "Factura C",
            "00002",
            1,
            "",
        ),
        (
            "Ibarrondo Luis Angel",
            "Publicidad & Servicios",
            "20-26385888-4",
            "Monotributo",
            "Factura C",
            "00002",
            1,
            "",
        ),
        (
            "Ibarrondo Adrian Oscar e Ibarrondo Luis Angel S.H.",
            "Publicidad & Servicios S.H.",
            "30-71217861-9",
            "Responsable Inscripto",
            "Factura A",
            "00002",
            1,
            "",
        ),
    ]
    for emisor in emisores_iniciales:
        cur.execute("SELECT id FROM emisores_fiscales WHERE cuit=?", (emisor[2],))
        if cur.fetchone() is None:
            cur.execute(
                """
                INSERT INTO emisores_fiscales(
                    razon_social,
                    nombre_fantasia,
                    cuit,
                    condicion_iva,
                    tipo_factura,
                    punto_venta,
                    activo,
                    observaciones
                ) VALUES(?,?,?,?,?,?,?,?)
                """,
                emisor,
            )

    cur.execute("""
    CREATE TABLE IF NOT EXISTS arca_config(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        modo_trabajo TEXT NOT NULL DEFAULT 'Manual'
    )
    """)
    cur.execute("INSERT INTO arca_config(modo_trabajo) SELECT 'Manual' WHERE NOT EXISTS(SELECT 1 FROM arca_config)")

    hoy = date.today()
    cur.execute("SELECT id, fecha_inicio, fecha_fin, renovable FROM servicios")
    for servicio_id, inicio_guardado, fin_guardado, renovable in cur.fetchall():
        try:
            inicio = datetime.strptime(inicio_guardado, "%Y-%m-%d").date()
        except (TypeError, ValueError):
            inicio = hoy
        try:
            fin = datetime.strptime(fin_guardado, "%Y-%m-%d").date()
        except (TypeError, ValueError):
            fin = sumar_un_mes(inicio)
        es_renovable = 1 if renovable is None else int(bool(renovable))
        if fin < hoy:
            estado = "Vencido" if es_renovable else "Finalizado"
        else:
            estado = "Activo"
        cur.execute("""
            UPDATE servicios
            SET fecha_inicio=?, fecha_fin=?, renovable=?, estado_periodo=?
            WHERE id=?
        """, (inicio.isoformat(), fin.isoformat(), es_renovable, estado, servicio_id))

    # ==========================
    # HISTORIAL DE RENOVACIONES
    # ==========================

    cur.execute("""
    CREATE TABLE IF NOT EXISTS servicio_renovaciones(

        id INTEGER PRIMARY KEY AUTOINCREMENT,
        servicio_id INTEGER NOT NULL,
        cliente_id INTEGER NOT NULL,
        fecha_renovacion TEXT NOT NULL,
        fecha_inicio_anterior TEXT NOT NULL,
        fecha_fin_anterior TEXT NOT NULL,
        fecha_inicio_nueva TEXT NOT NULL,
        fecha_fin_nueva TEXT NOT NULL,
        concepto TEXT,
        descripcion TEXT,
        cantidad REAL DEFAULT 1,
        importe REAL DEFAULT 0,
        descuento REAL DEFAULT 0,
        resumen_id INTEGER,

        FOREIGN KEY(servicio_id) REFERENCES servicios(id),
        FOREIGN KEY(cliente_id) REFERENCES clientes(id),
        FOREIGN KEY(resumen_id) REFERENCES resumenes(id)

    )
    """)
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_renovaciones_servicio "
        "ON servicio_renovaciones(servicio_id, fecha_renovacion)"
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_renovaciones_resumen "
        "ON servicio_renovaciones(resumen_id)"
    )

    # ==========================
    # TABLAS RESUMENES
    # ==========================

    cur.execute("""
    CREATE TABLE IF NOT EXISTS resumenes(

        id INTEGER PRIMARY KEY AUTOINCREMENT,
        numero INTEGER NOT NULL UNIQUE,
        cliente_id INTEGER NOT NULL,
        emisor_fiscal_id INTEGER,
        fecha TEXT NOT NULL,
        fecha_vencimiento TEXT NOT NULL,
        tipo_factura TEXT,
        punto_venta TEXT,
        total REAL NOT NULL DEFAULT 0,
        saldo REAL NOT NULL DEFAULT 0,
        estado TEXT NOT NULL DEFAULT 'Pendiente',
        estado_facturacion TEXT NOT NULL DEFAULT 'Pendiente',
        fecha_facturacion TEXT,
        cae TEXT,
        vencimiento_cae TEXT,
        numero_factura TEXT,
        pdf_path TEXT,
        fecha_creacion TEXT,

        FOREIGN KEY(cliente_id)
        REFERENCES clientes(id),
        FOREIGN KEY(emisor_fiscal_id)
        REFERENCES emisores_fiscales(id)

    )
    """)

    columnas_resumenes = {
        "emisor_fiscal_id": "INTEGER",
        "tipo_factura": "TEXT",
        "punto_venta": "TEXT",
        "estado_facturacion": "TEXT NOT NULL DEFAULT 'Pendiente'",
        "fecha_facturacion": "TEXT",
        "cae": "TEXT",
        "vencimiento_cae": "TEXT",
        "numero_factura": "TEXT",
    }
    for columna, definicion in columnas_resumenes.items():
        agregar_columna_si_falta(cur, "resumenes", columna, definicion)
    cur.execute(
        "UPDATE resumenes SET estado_facturacion='Pendiente' WHERE estado_facturacion IS NULL OR TRIM(estado_facturacion)=''"
    )

    cur.execute("""
    CREATE TABLE IF NOT EXISTS resumen_conceptos(

        id INTEGER PRIMARY KEY AUTOINCREMENT,
        resumen_id INTEGER NOT NULL,
        servicio_id INTEGER,
        concepto TEXT NOT NULL,
        descripcion TEXT,
        cantidad REAL NOT NULL DEFAULT 1,
        importe REAL NOT NULL DEFAULT 0,
        descuento REAL NOT NULL DEFAULT 0,
        total REAL NOT NULL DEFAULT 0,
        fecha_inicio TEXT,
        fecha_fin TEXT,

        FOREIGN KEY(resumen_id)
        REFERENCES resumenes(id) ON DELETE CASCADE,
        FOREIGN KEY(servicio_id)
        REFERENCES servicios(id)

    )
    """)

    columnas_resumen_conceptos = {
        "fecha_inicio": "TEXT",
        "fecha_fin": "TEXT"
    }
    for columna, definicion in columnas_resumen_conceptos.items():
        agregar_columna_si_falta(
            cur,
            "resumen_conceptos",
            columna,
            definicion,
        )

    cur.execute("""
        UPDATE resumen_conceptos
        SET fecha_inicio = (
                SELECT s.fecha_inicio FROM servicios s
                WHERE s.id=resumen_conceptos.servicio_id
            )
        WHERE fecha_inicio IS NULL AND servicio_id IS NOT NULL
    """)
    cur.execute("""
        UPDATE resumen_conceptos
        SET fecha_fin = (
                SELECT s.fecha_fin FROM servicios s
                WHERE s.id=resumen_conceptos.servicio_id
            )
        WHERE fecha_fin IS NULL AND servicio_id IS NOT NULL
    """)

    cur.execute("CREATE INDEX IF NOT EXISTS idx_resumenes_cliente ON resumenes(cliente_id)")
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_resumen_conceptos_resumen "
        "ON resumen_conceptos(resumen_id)"
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_resumen_conceptos_periodo "
        "ON resumen_conceptos(servicio_id, fecha_inicio, fecha_fin)"
    )

    # ==========================
    # TABLA COBROS
    # ==========================

    cur.execute("""
    CREATE TABLE IF NOT EXISTS cobros(

        id INTEGER PRIMARY KEY AUTOINCREMENT,
        cliente_id INTEGER NOT NULL,
        fecha TEXT NOT NULL,
        importe REAL NOT NULL DEFAULT 0,
        forma_pago TEXT,
        comprobante TEXT,
        observaciones TEXT,

        FOREIGN KEY(cliente_id)
        REFERENCES clientes(id)

    )
    """)

    columnas_cobros = {
        "cliente_id": "INTEGER",
        "fecha": "TEXT",
        "importe": "REAL DEFAULT 0",
        "forma_pago": "TEXT",
        "comprobante": "TEXT",
        "observaciones": "TEXT"
    }

    for columna, definicion in columnas_cobros.items():
        agregar_columna_si_falta(cur, "cobros", columna, definicion)

    cur.execute("CREATE INDEX IF NOT EXISTS idx_cobros_cliente ON cobros(cliente_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_cobros_fecha ON cobros(fecha)")

    # ==========================
    # TABLA TAREAS
    # ==========================

    cur.execute("""
    CREATE TABLE IF NOT EXISTS tareas(

        id INTEGER PRIMARY KEY AUTOINCREMENT,
        cliente_id INTEGER,
        fecha TEXT NOT NULL,
        hora TEXT NOT NULL,
        tipo TEXT NOT NULL,
        titulo TEXT NOT NULL,
        descripcion TEXT,
        estado TEXT NOT NULL DEFAULT 'Pendiente',
        prioridad TEXT NOT NULL DEFAULT 'Media',
        fecha_creacion TEXT,

        FOREIGN KEY(cliente_id) REFERENCES clientes(id)

    )
    """)

    columnas_tareas = {
        "cliente_id": "INTEGER",
        "fecha": "TEXT",
        "hora": "TEXT",
        "tipo": "TEXT",
        "titulo": "TEXT",
        "descripcion": "TEXT",
        "estado": "TEXT DEFAULT 'Pendiente'",
        "prioridad": "TEXT DEFAULT 'Media'",
        "fecha_creacion": "TEXT"
    }
    for columna, definicion in columnas_tareas.items():
        agregar_columna_si_falta(cur, "tareas", columna, definicion)

    cur.execute("CREATE INDEX IF NOT EXISTS idx_tareas_fecha ON tareas(fecha, hora)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_tareas_cliente ON tareas(cliente_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_tareas_estado ON tareas(estado)")

    # ==========================
    # TABLA CONTACTOS CRM
    # ==========================

    cur.execute("""
    CREATE TABLE IF NOT EXISTS contactos(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        cliente_id INTEGER NOT NULL,
        fecha TEXT NOT NULL,
        hora TEXT NOT NULL,
        tipo TEXT NOT NULL,
        resultado TEXT NOT NULL DEFAULT 'Pendiente',
        observaciones TEXT,
        proximo_contacto TEXT,
        vendedor TEXT,
        creado TEXT,
        FOREIGN KEY(cliente_id) REFERENCES clientes(id)
    )
    """)
    columnas_contactos = {
        "cliente_id": "INTEGER", "fecha": "TEXT", "hora": "TEXT",
        "tipo": "TEXT", "resultado": "TEXT DEFAULT 'Pendiente'",
        "observaciones": "TEXT", "proximo_contacto": "TEXT",
        "vendedor": "TEXT", "creado": "TEXT",
    }
    for columna, definicion in columnas_contactos.items():
        agregar_columna_si_falta(cur, "contactos", columna, definicion)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_contactos_cliente ON contactos(cliente_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_contactos_fecha ON contactos(fecha)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_contactos_proximo ON contactos(proximo_contacto)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_contactos_tipo ON contactos(tipo)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_contactos_resultado ON contactos(resultado)")

    # ==========================
    # TABLA FACTURA ARCA
    # ==========================

    cur.execute("""
    CREATE TABLE IF NOT EXISTS factura_arca(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        cliente_id INTEGER NOT NULL,
        emisor_id INTEGER NOT NULL,
        resumen_id INTEGER NOT NULL,
        fecha TEXT NOT NULL,
        punto_venta TEXT,
        tipo_comprobante TEXT,
        importe_total REAL NOT NULL DEFAULT 0,
        estado TEXT NOT NULL DEFAULT 'Pendiente',
        numero_factura TEXT,
        cae TEXT,
        vencimiento_cae TEXT,
        observaciones TEXT,
        fecha_creacion TEXT,

        FOREIGN KEY(cliente_id) REFERENCES clientes(id),
        FOREIGN KEY(emisor_id) REFERENCES emisores_facturacion(id),
        FOREIGN KEY(resumen_id) REFERENCES resumenes(id)
    )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_factura_arca_cliente ON factura_arca(cliente_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_factura_arca_emisor ON factura_arca(emisor_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_factura_arca_resumen ON factura_arca(resumen_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_factura_arca_estado ON factura_arca(estado)")

    # ==========================
    # MIGRACIÓN TABLA FACTURA ARCA
    # ==========================
    cur.execute("PRAGMA table_info(factura_arca)")
    if not cur.fetchall():
        cur.execute("CREATE TABLE IF NOT EXISTS factura_arca(\n"
                    "    id INTEGER PRIMARY KEY AUTOINCREMENT,\n"
                    "    cliente_id INTEGER NOT NULL,\n"
                    "    emisor_id INTEGER NOT NULL,\n"
                    "    resumen_id INTEGER NOT NULL,\n"
                    "    fecha TEXT NOT NULL,\n"
                    "    punto_venta TEXT,\n"
                    "    tipo_comprobante TEXT,\n"
                    "    importe_total REAL NOT NULL DEFAULT 0,\n"
                    "    estado TEXT NOT NULL DEFAULT 'Pendiente',\n"
                    "    numero_factura TEXT,\n"
                    "    cae TEXT,\n"
                    "    vencimiento_cae TEXT,\n"
                    "    observaciones TEXT,\n"
                    "    fecha_creacion TEXT,\n"
                    "    FOREIGN KEY(cliente_id) REFERENCES clientes(id),\n"
                    "    FOREIGN KEY(emisor_id) REFERENCES emisores_facturacion(id),\n"
                    "    FOREIGN KEY(resumen_id) REFERENCES resumenes(id)\n"
                    ")")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_factura_arca_cliente ON factura_arca(cliente_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_factura_arca_emisor ON factura_arca(emisor_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_factura_arca_resumen ON factura_arca(resumen_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_factura_arca_estado ON factura_arca(estado)")

    # ==========================
    # TABLA OPORTUNIDADES
    # ==========================

    cur.execute("""
    CREATE TABLE IF NOT EXISTS oportunidades(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        cliente_id INTEGER,
        nombre_potencial TEXT,
        telefono TEXT,
        whatsapp TEXT,
        email TEXT,
        fecha TEXT NOT NULL,
        origen TEXT,
        servicio_interes TEXT,
        importe_estimado REAL DEFAULT 0,
        probabilidad REAL DEFAULT 0,
        estado TEXT NOT NULL DEFAULT 'Nueva',
        proximo_contacto TEXT,
        observaciones TEXT,
        creado TEXT,
        FOREIGN KEY(cliente_id) REFERENCES clientes(id)
    )
    """)
    columnas_oportunidades = {
        "cliente_id": "INTEGER", "nombre_potencial": "TEXT",
        "telefono": "TEXT", "whatsapp": "TEXT", "email": "TEXT",
        "fecha": "TEXT", "origen": "TEXT", "servicio_interes": "TEXT",
        "importe_estimado": "REAL DEFAULT 0", "probabilidad": "REAL DEFAULT 0",
        "estado": "TEXT DEFAULT 'Nueva'", "proximo_contacto": "TEXT",
        "observaciones": "TEXT", "creado": "TEXT",
    }
    for columna, definicion in columnas_oportunidades.items():
        agregar_columna_si_falta(cur, "oportunidades", columna, definicion)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_oportunidades_cliente ON oportunidades(cliente_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_oportunidades_estado ON oportunidades(estado)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_oportunidades_fecha ON oportunidades(fecha)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_oportunidades_proximo ON oportunidades(proximo_contacto)")

    # ==========================
    # TABLA NOTIFICACIONES
    # ==========================

    cur.execute("""
    CREATE TABLE IF NOT EXISTS notificaciones(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        tipo TEXT NOT NULL,
        titulo TEXT NOT NULL,
        mensaje TEXT,
        prioridad TEXT NOT NULL DEFAULT 'Media',
        estado TEXT NOT NULL DEFAULT 'Pendiente',
        fecha TEXT NOT NULL,
        vencimiento TEXT,
        referencia_tipo TEXT,
        referencia_id INTEGER,
        clave TEXT,
        automatica INTEGER DEFAULT 0,
        creado TEXT,
        actualizado TEXT
    )
    """)
    columnas_notificaciones = {
        "tipo": "TEXT", "titulo": "TEXT", "mensaje": "TEXT",
        "prioridad": "TEXT DEFAULT 'Media'", "estado": "TEXT DEFAULT 'Pendiente'",
        "fecha": "TEXT", "vencimiento": "TEXT", "referencia_tipo": "TEXT",
        "referencia_id": "INTEGER", "clave": "TEXT", "automatica": "INTEGER DEFAULT 0",
        "creado": "TEXT", "actualizado": "TEXT",
    }
    for columna, definicion in columnas_notificaciones.items():
        agregar_columna_si_falta(cur, "notificaciones", columna, definicion)
    cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_notificaciones_clave ON notificaciones(clave)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_notificaciones_estado ON notificaciones(estado)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_notificaciones_tipo ON notificaciones(tipo)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_notificaciones_prioridad ON notificaciones(prioridad)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_notificaciones_vencimiento ON notificaciones(vencimiento)")
    # ==========================
    # TABLA USUARIOS
    # ==========================

    cur.execute("""
    CREATE TABLE IF NOT EXISTS usuarios(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nombre TEXT,
        usuario TEXT NOT NULL UNIQUE,
        clave TEXT NOT NULL,
        rol TEXT NOT NULL DEFAULT 'Consulta',
        activo INTEGER DEFAULT 1,
        fecha_creacion TEXT
    )
    """)
    columnas_usuarios = {
        "nombre": "TEXT", "usuario": "TEXT", "clave": "TEXT",
        "rol": "TEXT DEFAULT 'Consulta'", "activo": "INTEGER DEFAULT 1",
        "fecha_creacion": "TEXT",
    }
    for columna, definicion in columnas_usuarios.items():
        agregar_columna_si_falta(cur, "usuarios", columna, definicion)
    cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_usuarios_usuario ON usuarios(usuario)")

    conn.commit()
    conn.close()


def obtener_clientes():

    conn = conectar()
    cur = conn.cursor()

    cur.execute("""
        SELECT
            id,
            codigo,
            razon_social,
            telefono,
            estado
        FROM clientes
        ORDER BY razon_social
    """)

    datos = cur.fetchall()

    conn.close()

    return datos
