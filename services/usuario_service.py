import hashlib
from datetime import datetime

from database import conectar


class UsuarioService:
    ROLES = ("Administrador", "Operador", "Consulta")

    @staticmethod
    def _hash_password(password: str) -> str:
        return hashlib.sha256(password.encode("utf-8")).hexdigest()

    @classmethod
    def crear_usuario(cls, nombre, usuario, clave, rol="Consulta", activo=1):
        ahora = datetime.now().isoformat()
        hash_clave = cls._hash_password(clave)
        conn = conectar(); cur = conn.cursor()
        cur.execute("INSERT INTO usuarios(nombre, usuario, clave, rol, activo, fecha_creacion) VALUES(?,?,?,?,?,?)",
                    (nombre, usuario, hash_clave, rol, activo, ahora))
        conn.commit(); conn.close(); return cur.lastrowid

    @classmethod
    def modificar_usuario(cls, usuario_id, nombre=None, usuario=None, rol=None, activo=None):
        campos, params = [], []
        if nombre is not None:
            campos.append("nombre=?"); params.append(nombre)
        if usuario is not None:
            campos.append("usuario=?"); params.append(usuario)
        if rol is not None:
            campos.append("rol=?"); params.append(rol)
        if activo is not None:
            campos.append("activo=?"); params.append(int(bool(activo)))
        if not campos:
            return False
        params.append(usuario_id)
        consulta = f"UPDATE usuarios SET {', '.join(campos)} WHERE id=?"
        conn = conectar(); cur = conn.cursor(); cur.execute(consulta, params)
        actualizado = cur.rowcount > 0
        conn.commit(); conn.close(); return actualizado

    @classmethod
    def cambiar_clave(cls, usuario_id, nueva_clave):
        hash_clave = cls._hash_password(nueva_clave)
        conn = conectar(); cur = conn.cursor()
        cur.execute("UPDATE usuarios SET clave=? WHERE id=?", (hash_clave, usuario_id))
        actualizado = cur.rowcount > 0
        conn.commit(); conn.close(); return actualizado

    @classmethod
    def autenticar(cls, usuario, clave):
        hash_clave = cls._hash_password(clave)
        conn = conectar(); cur = conn.cursor()
        cur.execute("SELECT id, nombre, usuario, rol, activo, fecha_creacion FROM usuarios WHERE usuario=? AND clave=?", (usuario, hash_clave))
        fila = cur.fetchone(); conn.close()
        if not fila:
            return None
        if fila[4] != 1:
            return None
        return {"id": fila[0], "nombre": fila[1], "usuario": fila[2], "rol": fila[3], "activo": fila[4], "fecha_creacion": fila[5]}

    @classmethod
    def listar(cls):
        conn = conectar(); cur = conn.cursor(); cur.execute("SELECT id, nombre, usuario, rol, activo, fecha_creacion FROM usuarios ORDER BY id DESC")
        filas = cur.fetchall(); conn.close(); return filas

    @classmethod
    def obtener(cls, usuario_id):
        conn = conectar(); cur = conn.cursor(); cur.execute("SELECT id, nombre, usuario, rol, activo, fecha_creacion FROM usuarios WHERE id=?", (usuario_id,))
        fila = cur.fetchone(); conn.close(); return fila

    @classmethod
    def init_admin_if_missing(cls):
        conn = conectar(); cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM usuarios"); total = cur.fetchone()[0]
        if total == 0:
            ahora = datetime.now().isoformat()
            hash_clave = cls._hash_password("admin123")
            cur.execute("INSERT INTO usuarios(nombre, usuario, clave, rol, activo, fecha_creacion) VALUES(?,?,?,?,?,?)",
                        ("Administrador", "admin", hash_clave, "Administrador", 1, ahora))
            conn.commit()
        conn.close()
