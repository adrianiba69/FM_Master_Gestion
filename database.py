import sqlite3
import os

DB_NAME = "database/fm_master.db"

os.makedirs("database", exist_ok=True)


def conectar():
    return sqlite3.connect(DB_NAME)


def crear_base():

    conn = conectar()
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS clientes(

        id INTEGER PRIMARY KEY AUTOINCREMENT,
        codigo TEXT,
        razon_social TEXT,
        responsable TEXT,
        direccion TEXT,
        localidad TEXT,
        telefono TEXT,
        whatsapp TEXT,
        email TEXT,
        cuit TEXT,
        iva TEXT,
        servicio TEXT,
        importe REAL,
        descuento REAL,
        vencimiento INTEGER,
        estado TEXT,
        observaciones TEXT,
        fecha_alta TEXT

    )
    """)

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
        servicio,
        importe,
        estado
        FROM clientes
        ORDER BY razon_social
    """)

    datos = cur.fetchall()

    conn.close()

    return datos