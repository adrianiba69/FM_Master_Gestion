from database import conectar


class CatalogoService:

    @staticmethod
    def listar(activos_solo=True):
        conn = conectar()
        cur = conn.cursor()
        if activos_solo:
            cur.execute("SELECT id, nombre, descripcion, precio, activo FROM catalogo_servicios WHERE activo=1 ORDER BY nombre")
        else:
            cur.execute("SELECT id, nombre, descripcion, precio, activo FROM catalogo_servicios ORDER BY nombre")
        filas = cur.fetchall()
        conn.close()
        return filas

    @staticmethod
    def buscar(texto):
        conn = conectar()
        cur = conn.cursor()
        cur.execute("SELECT id, nombre, descripcion, precio, activo FROM catalogo_servicios WHERE nombre LIKE ? ORDER BY nombre", ('%'+texto+'%',))
        filas = cur.fetchall()
        conn.close()
        return filas

    @staticmethod
    def obtener(id_):
        conn = conectar()
        cur = conn.cursor()
        cur.execute("SELECT id, nombre, descripcion, precio, activo FROM catalogo_servicios WHERE id=?", (id_,))
        fila = cur.fetchone()
        conn.close()
        return fila

    @staticmethod
    def guardar(nombre, descripcion, precio, activo=1):
        conn = conectar()
        cur = conn.cursor()
        cur.execute("INSERT INTO catalogo_servicios(nombre, descripcion, precio, activo) VALUES(?,?,?,?)",
                    (nombre, descripcion, precio, activo))
        id_ = cur.lastrowid
        conn.commit()
        conn.close()
        return id_

    @staticmethod
    def asegurar_servicios_iniciales():
        filas = CatalogoService.listar(False)
        if filas:
            return
        servicios = [
            ("Publicidad rotativa", "Servicio de publicidad rotativa", 1500.0, 1),
            ("Auspicio", "Auspicio de eventos o programas", 2500.0, 1),
            ("Programa radial", "Publicidad en programa radial", 1800.0, 1),
            ("Streaming", "Publicidad o contenido en streaming", 2200.0, 1),
            ("Facebook", "Campaña publicitaria en Facebook", 1600.0, 1),
            ("Instagram", "Campaña publicitaria en Instagram", 1700.0, 1),
            ("Cobertura de eventos", "Cobertura y producción de eventos", 3000.0, 1),
            ("Producción comercial", "Producción comercial y edición", 3500.0, 1),
            ("Publicidad política", "Campaña política y difusión", 4000.0, 1),
            ("Banner web", "Diseño y publicación de banner web", 1200.0, 1),
            ("Publicidad especial", "Campaña publicitaria especial", 2800.0, 1),
            ("Otro", "Otro tipo de servicio", 1000.0, 1),
        ]
        for nombre, descripcion, precio, activo in servicios:
            CatalogoService.guardar(nombre, descripcion, precio, activo)

    @staticmethod
    def actualizar(id_, nombre, descripcion, precio, activo=1):
        conn = conectar()
        cur = conn.cursor()
        cur.execute("UPDATE catalogo_servicios SET nombre=?, descripcion=?, precio=?, activo=? WHERE id=?",
                    (nombre, descripcion, precio, activo, id_))
        conn.commit()
        conn.close()

    @staticmethod
    def eliminar(id_):
        conn = conectar()
        cur = conn.cursor()
        cur.execute("DELETE FROM catalogo_servicios WHERE id=?", (id_,))
        conn.commit()
        conn.close()
