import sqlite3
import os

DB_NAME = "database/fm_master.db"

os.makedirs("database", exist_ok=True)


def conectar():
    return sqlite3.connect(DB_NAME)


def agregar_columna_si_falta(cur, tabla, columna, definicion):
    cur.execute(f"PRAGMA table_info({tabla})")
    columnas = {fila[1] for fila in cur.fetchall()}

    if columna not in columnas:
        cur.execute(f"ALTER TABLE {tabla} ADD COLUMN {columna} {definicion}")


def crear_base():

    conn = conectar()
    cur = conn.cursor()

    # ==========================
    # TABLA CLIENTES
    # ==========================

    cur.execute("""
    CREATE TABLE IF NOT EXISTS clientes(

        id INTEGER PRIMARY KEY AUTOINCREMENT,
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
        "activo": "INTEGER DEFAULT 1"
    }

    for columna, definicion in columnas_servicios.items():
        agregar_columna_si_falta(cur, "servicios", columna, definicion)

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
