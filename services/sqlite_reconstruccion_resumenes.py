"""Reconstrucción segura de la tabla ``resumenes`` (etapa 3D.4C.5D.5B).

Módulo independiente: no se integra al arranque, no abre rutas, no importa ``database`` ni el
servicio de backup, no escribe marcadores de versión y no usa ``crear_base()``.

Objetivo
========
Los esquemas derivados de 8c81526 y 4994dc6 (tras ``crear_base()``) tienen la columna
``resumenes.emisor_fiscal_id`` sin la clave foránea ``REFERENCES emisores_fiscales(id)``.
Este módulo reconstruye la tabla con la definición actual preservando todos los datos.

Seguridad
=========
* Toda la operación corre dentro de ``ejecutar_con_claves_foraneas_controladas`` y solo usa la
  ``ConexionRestringida`` que éste entrega. No hay commit, rollback ni reintentos propios: los
  contratos de confirmación (``confirmada`` True/False/None) son los del mecanismo, cuyas
  excepciones se propagan sin envolver.
* Solo se reconoce la huella estructural oficial de origen ``HUELLA_ORIGEN_AUTORIZADA``,
  calculada DENTRO de la transacción y bajo la reserva de escritura. La huella final
  ``HUELLA_FINAL_ESPERADA`` (esquema ya corregido) se trata como "nada que hacer". Cualquier
  otra huella, o una no confiable, se rechaza. Estas huellas no autorizan arranque ni migración
  de bases reales.
* Referencias huérfanas de ``emisor_fiscal_id`` se rechazan con una consulta explícita (sin la
  clave foránea ``foreign_key_check`` no puede detectarlas); no se corrigen ni se anulan.
* No se usa ``writable_schema`` ni se renombra primero la tabla original; las columnas se copian siempre por nombre.

Secuencia (procedimiento de reconstrucción de SQLite)
=====================================================
1. Colisión con la tabla auxiliar -> rechazo. 2. Huella de origen (rechazo / ya corregida / ok).
3. Dependientes e índice contemplados. 4. Huérfanos. 5. Captura de registros (con tipo de
almacenamiento), dependientes, relaciones, objetos ajenos y ``sqlite_sequence``.
6. ``CREATE TABLE`` auxiliar. 7. ``INSERT ... SELECT`` con las 18 columnas por nombre.
8. Verificación de la copia. 9. ``DROP TABLE`` original. 10. ``RENAME`` de la auxiliar.
11. ``CREATE INDEX``. 12. Restauración de ``sqlite_sequence``. 13. Verificación de dependientes,
relaciones, objetos y ausencia de residuos. 14. Huella final oficial, confiable e igual a la
esperada. Después, el mecanismo valida ``foreign_key_check``/``quick_check`` y confirma.
"""

from dataclasses import dataclass

from services.sqlite_control_claves_foraneas import ejecutar_con_claves_foraneas_controladas
from services.sqlite_huella_estructural import calcular_huella_estructural_sqlite

HUELLA_ORIGEN_AUTORIZADA = "b78314c4db609c4c953d4484475e0712695c1a9e5380906b8717e038b36e8a36"
HUELLA_FINAL_ESPERADA = "650cc300b59db14e5621f922cd77a55d08739ec843729bdb61ccf6e33e4b7fa3"
TABLA_AUXILIAR = "resumenes_reconstruccion_3d4c5d5b"
COLUMNAS = (
    "id", "numero", "cliente_id", "emisor_fiscal_id", "fecha", "fecha_vencimiento", "tipo_factura",
    "punto_venta", "total", "saldo", "estado", "estado_facturacion", "fecha_facturacion", "cae",
    "vencimiento_cae", "numero_factura", "pdf_path", "fecha_creacion",
)
DEPENDIENTES = frozenset({"resumen_conceptos", "servicio_renovaciones", "factura_arca", "intentos_emision_arca"})
_LISTA = ", ".join(COLUMNAS)

SQL_CREAR_AUXILIAR = f"""CREATE TABLE {TABLA_AUXILIAR}(
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
    FOREIGN KEY(cliente_id) REFERENCES clientes(id),
    FOREIGN KEY(emisor_fiscal_id) REFERENCES emisores_fiscales(id)
)"""
SQL_COPIAR = f"INSERT INTO {TABLA_AUXILIAR}({_LISTA}) SELECT {_LISTA} FROM resumenes ORDER BY id"
SQL_ELIMINAR_ORIGINAL = "DROP TABLE resumenes"
SQL_RENOMBRAR = f"ALTER TABLE {TABLA_AUXILIAR} RENAME TO resumenes"
SQL_CREAR_INDICE_CLIENTE = "CREATE INDEX idx_resumenes_cliente ON resumenes(cliente_id)"
SQL_SECUENCIA_ACTUALIZAR = "UPDATE sqlite_sequence SET seq=? WHERE name='resumenes'"
SQL_SECUENCIA_INSERTAR = "INSERT INTO sqlite_sequence(name, seq) VALUES ('resumenes', ?)"
SQL_SECUENCIA_ELIMINAR = "DELETE FROM sqlite_sequence WHERE name='resumenes'"
_SQL_HUERFANOS = (
    "SELECT COUNT(*) FROM resumenes r WHERE r.emisor_fiscal_id IS NOT NULL "
    "AND NOT EXISTS (SELECT 1 FROM emisores_fiscales e WHERE e.id = r.emisor_fiscal_id)"
)


class ErrorReconstruccionResumenes(RuntimeError):
    """Rechazo o fallo propio; ``razon`` es un identificador fijo sin rutas ni datos."""

    def __init__(self, razon):
        super().__init__(f"Reconstrucción de resumenes rechazada: {razon}.")
        self.razon = razon


@dataclass(frozen=True)
class ResultadoReconstruccionResumenes:
    reconstruida: bool
    huella_origen: str
    huella_final: str
    registros: int


def _ident(nombre):
    return '"' + str(nombre).replace('"', '""') + '"'


def _columnas(i, tabla):
    return [f[1] for f in i.execute(f"PRAGMA table_info({_ident(tabla)})").fetchall()]


def _filas(i, tabla, columnas):
    seleccion = ", ".join(_ident(c) for c in columnas)
    filas = i.execute(f"SELECT {seleccion} FROM {_ident(tabla)} ORDER BY id").fetchall()
    # Se conserva el tipo de almacenamiento: 1 == 1.0 en Python pero no en SQLite.
    return [(tuple(f), tuple(type(v) for v in f)) for f in filas]


def _rechazar_colision(i):
    for catalogo in ("sqlite_master", "sqlite_temp_master"):
        if i.execute(f"SELECT 1 FROM {catalogo} WHERE lower(name)=lower(?)", (TABLA_AUXILIAR,)).fetchone():
            raise ErrorReconstruccionResumenes("tabla_auxiliar_preexistente")


def _relaciones_hacia_resumenes(i):
    tablas = [f[0] for f in i.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name").fetchall()]
    relaciones = {}
    for tabla in tablas:
        filas = [tuple(f) for f in i.execute(f"PRAGMA foreign_key_list({_ident(tabla)})").fetchall()
                 if str(f[2]).casefold() == "resumenes"]
        if filas:
            relaciones[tabla] = filas
    return relaciones


def _objetos_ajenos(i):
    return [tuple(f) for f in i.execute(
        "SELECT type, name, tbl_name, sql FROM sqlite_master "
        "WHERE tbl_name <> 'resumenes' AND name NOT LIKE 'sqlite_%' ORDER BY type, name").fetchall()]


def _secuencias(i):
    filas = [tuple(f) for f in i.execute("SELECT name, seq FROM sqlite_sequence ORDER BY name, seq").fetchall()]
    nombres = [f[0] for f in filas]
    if len(nombres) != len(set(nombres)):
        raise ErrorReconstruccionResumenes("sqlite_sequence_duplicada")
    return dict(filas)


def _estado_dependientes(i, tablas):
    return {t: (lambda cols: (cols, _filas(i, t, cols)))(_columnas(i, t)) for t in sorted(tablas)}


def _capturar(i):
    relaciones = _relaciones_hacia_resumenes(i)
    if set(relaciones) != DEPENDIENTES:
        raise ErrorReconstruccionResumenes("dependientes_no_contemplados")
    indices = i.execute(
        "SELECT name, sql FROM sqlite_master WHERE type='index' AND tbl_name='resumenes' "
        "AND name NOT LIKE 'sqlite_autoindex_%'").fetchall()
    if [tuple(f) for f in indices] != [("idx_resumenes_cliente", SQL_CREAR_INDICE_CLIENTE)]:
        raise ErrorReconstruccionResumenes("indices_no_contemplados")
    if _columnas(i, "resumenes") and set(_columnas(i, "resumenes")) != set(COLUMNAS):
        raise ErrorReconstruccionResumenes("columnas_no_contempladas")
    if i.execute(_SQL_HUERFANOS).fetchone()[0]:
        raise ErrorReconstruccionResumenes("emisor_fiscal_huerfano")
    secuencias = _secuencias(i)
    return {
        "filas": _filas(i, "resumenes", COLUMNAS),
        "relaciones": relaciones,
        "dependientes": _estado_dependientes(i, DEPENDIENTES),
        "ajenos": _objetos_ajenos(i),
        "secuencia": secuencias.pop("resumenes", None),
        "otras_secuencias": secuencias,
    }


def _crear_tabla_auxiliar(i):
    i.execute(SQL_CREAR_AUXILIAR)


def _copiar_registros(i):
    i.execute(SQL_COPIAR)


def _verificar_copia(i, captura):
    if _filas(i, TABLA_AUXILIAR, COLUMNAS) != captura["filas"]:
        raise ErrorReconstruccionResumenes("copia_no_equivalente")


def _eliminar_original(i):
    i.execute(SQL_ELIMINAR_ORIGINAL)


def _renombrar_auxiliar(i):
    i.execute(SQL_RENOMBRAR)


def _recrear_indices(i):
    i.execute(SQL_CREAR_INDICE_CLIENTE)


def _restaurar_secuencia(i, captura):
    secuencia = captura["secuencia"]
    if secuencia is None:
        i.execute(SQL_SECUENCIA_ELIMINAR)
    elif i.execute(SQL_SECUENCIA_ACTUALIZAR, (secuencia,)).rowcount == 0:
        i.execute(SQL_SECUENCIA_INSERTAR, (secuencia,))


def _verificar_relaciones(i, captura):
    def exigir(condicion, razon):
        if not condicion:
            raise ErrorReconstruccionResumenes(razon)

    exigir(_filas(i, "resumenes", COLUMNAS) == captura["filas"], "registros_no_conservados")
    exigir(_estado_dependientes(i, DEPENDIENTES) == captura["dependientes"], "dependientes_no_conservados")
    exigir(_relaciones_hacia_resumenes(i) == captura["relaciones"], "relaciones_no_conservadas")
    exigir(_objetos_ajenos(i) == captura["ajenos"], "objetos_ajenos_alterados")
    secuencias = _secuencias(i)
    exigir(secuencias.pop("resumenes", None) == captura["secuencia"], "secuencia_no_conservada")
    exigir(secuencias == captura["otras_secuencias"], "secuencias_ajenas_alteradas")
    exigir(not i.execute(
        "SELECT 1 FROM sqlite_master WHERE lower(name) LIKE ?", (TABLA_AUXILIAR.lower() + "%",)).fetchall(),
        "residuos_de_reconstruccion")
    propios = {f[0] for f in i.execute("SELECT name FROM sqlite_master WHERE tbl_name='resumenes'").fetchall()}
    exigir(propios == {"resumenes", "idx_resumenes_cliente", "sqlite_autoindex_resumenes_1"}, "objetos_propios_inesperados")
    padres = {str(f[2]).casefold(): str(f[3]).casefold() for f in i.execute("PRAGMA foreign_key_list(resumenes)")}
    exigir(padres == {"clientes": "cliente_id", "emisores_fiscales": "emisor_fiscal_id"}, "clave_foranea_ausente")


def _calcular_huella_final(i):
    resultado = calcular_huella_estructural_sqlite(i)
    if not resultado.confiable:
        raise ErrorReconstruccionResumenes("huella_final_no_confiable")
    if resultado.huella != HUELLA_FINAL_ESPERADA:
        raise ErrorReconstruccionResumenes("huella_final_inesperada")
    return resultado.huella


def _operacion(i):
    _rechazar_colision(i)
    origen = calcular_huella_estructural_sqlite(i)
    if not origen.confiable:
        raise ErrorReconstruccionResumenes("huella_de_origen_no_confiable")
    if origen.huella not in (HUELLA_ORIGEN_AUTORIZADA, HUELLA_FINAL_ESPERADA):
        raise ErrorReconstruccionResumenes("huella_de_origen_no_autorizada")
    registros = i.execute("SELECT COUNT(*) FROM resumenes").fetchone()[0]
    if origen.huella == HUELLA_FINAL_ESPERADA:
        return ResultadoReconstruccionResumenes(False, origen.huella, origen.huella, registros)
    captura = _capturar(i)
    _crear_tabla_auxiliar(i)
    _copiar_registros(i)
    _verificar_copia(i, captura)
    _eliminar_original(i)
    _renombrar_auxiliar(i)
    _recrear_indices(i)
    _restaurar_secuencia(i, captura)
    _verificar_relaciones(i, captura)
    final = _calcular_huella_final(i)
    return ResultadoReconstruccionResumenes(True, origen.huella, final, registros)


def reconstruir_resumenes(conexion, *, antes_de_operar=None):
    """Reconstruye ``resumenes`` bajo el control transaccional de claves foráneas.

    Devuelve ``ResultadoReconstruccionResumenes``. Las excepciones del mecanismo
    (``ErrorAntesDeConfirmar``, ``ErrorEstadoIncierto``, ``ErrorDespuesDeConfirmar``) se propagan
    sin modificar; el rechazo propio queda en ``__cause__`` como ``ErrorReconstruccionResumenes``.
    No hay reintentos. ``antes_de_operar`` es el gancho de backup del mecanismo (sin argumentos).
    """
    return ejecutar_con_claves_foraneas_controladas(
        conexion, _operacion, antes_de_operar=antes_de_operar
    ).resultado
