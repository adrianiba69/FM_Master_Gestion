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
        "vencimiento": "INTEGER",
        "estado": "TEXT",
        "observaciones": "TEXT",
        "fecha_alta": "TEXT",
        "fecha_modificacion": "TEXT"
    }

    for columna, definicion in columnas_clientes.items():
        agregar_columna_si_falta(cur, "clientes", columna, definicion)

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
        fecha TEXT NOT NULL,
        fecha_vencimiento TEXT NOT NULL,
        total REAL NOT NULL DEFAULT 0,
        saldo REAL NOT NULL DEFAULT 0,
        estado TEXT NOT NULL DEFAULT 'Pendiente',
        pdf_path TEXT,
        fecha_creacion TEXT,

        FOREIGN KEY(cliente_id)
        REFERENCES clientes(id)

    )
    """)

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
