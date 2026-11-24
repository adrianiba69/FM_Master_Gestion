"""Huella estructural canónica de una base SQLite (solo lectura).

Etapa 3D.4C.5D.2. Módulo aislado: no abre rutas, no se conecta al arranque, no
participa de la política de autorización y no escribe nada. Recibe una
``sqlite3.Connection`` ya abierta (idealmente ``mode=ro``) y ejecuta únicamente
``SELECT`` sobre ``sqlite_master`` y ``PRAGMA`` de lectura sin asignación.

Representación canónica (formato ``fm-huella-estructural-v1``)
----------------------------------------------------------------
Por cada tabla (ordenadas por nombre, sin distinguir mayúsculas):

* tipo, ``WITHOUT ROWID`` y ``STRICT`` (``PRAGMA table_list``);
* columnas ordenadas POR NOMBRE (``ALTER TABLE ADD COLUMN`` altera la posición, así
  que el orden físico no forma parte de la identidad): tipo declarado, NOT NULL,
  DEFAULT, posición en la clave primaria y columna generada (``table_xinfo``);
* claves foráneas completas, con columnas compuestas en orden, tabla y columnas
  padre (la referencia implícita a la PK se resuelve a sus columnas), ON UPDATE,
  ON DELETE y MATCH (``foreign_key_list``);
* índices (``index_list`` / ``index_xinfo``): los explícitos con su nombre, unicidad,
  parcialidad, columnas con orden y colación, condición WHERE y expresiones; los
  automáticos de UNIQUE/PRIMARY KEY sin nombre (origen, unicidad, columnas);
* restricciones que ningún PRAGMA expone, obtenidas del DDL con un analizador
  léxico propio (no expresiones regulares sobre el texto): CHECK, COLLATE de
  columna, ON CONFLICT, DEFERRABLE/INITIALLY y AUTOINCREMENT.

Además, triggers y vistas con su SQL normalizado.

Normalización: se descartan espacios y comentarios; palabras clave e
identificadores (con o sin comillas) se pasan a minúsculas; los literales de
texto se conservan exactos. Así, diferencias de formato no cambian la huella y
cualquier cambio de significado sí.

Quedan FUERA de la huella: ``application_id``, ``user_version``,
``schema_version``, modo de journal, codificación, tamaño de página, filas,
``sqlite_sequence`` y objetos temporales de la conexión.

Cuando la estructura no puede representarse con fiabilidad (tabla virtual,
columna generada, DDL no analizable, discrepancia entre el DDL y los PRAGMA,
PRAGMA ausente, error de SQLite o cambio de esquema durante la lectura) NO se
devuelve ninguna huella: ``confiable=False`` y ``huella=None``. Nunca hay
coincidencia aproximada.
"""

import hashlib
import json
import re
import sqlite3
from dataclasses import dataclass

FORMATO_HUELLA_ESTRUCTURAL = "fm-huella-estructural-v1"

_PALABRAS_CONSTRAINT_TABLA = frozenset({"constraint", "primary", "unique", "check", "foreign"})
_OPERADORES_DOBLES = frozenset({"||", "<=", ">=", "<>", "!=", "==", "<<", ">>", "->"})


@dataclass(frozen=True)
class ResultadoHuellaEstructuralSQLite:
    confiable: bool
    huella: object = None
    formato: str = FORMATO_HUELLA_ESTRUCTURAL
    razones: tuple = ()
    representacion: object = None
    objetos_temporales: int = 0


class _NoRepresentable(Exception):
    """Estructura que no puede describirse con fiabilidad; lleva un identificador fijo."""


def _tokenizar(sql):
    """Devuelve [(tipo, texto)] con tipo word|id|str|num|punct; descarta espacios y comentarios."""
    texto = str(sql)
    tokens = []
    i, n = 0, len(texto)
    while i < n:
        c = texto[i]
        if c.isspace():
            i += 1
        elif texto.startswith("--", i):
            fin = texto.find("\n", i)
            i = n if fin == -1 else fin + 1
        elif texto.startswith("/*", i):
            fin = texto.find("*/", i + 2)
            if fin == -1:
                raise _NoRepresentable("sql_no_analizable")
            i = fin + 2
        elif c == "'":
            j = i + 1
            while True:
                if j >= n:
                    raise _NoRepresentable("sql_no_analizable")
                if texto[j] == "'":
                    if j + 1 < n and texto[j + 1] == "'":
                        j += 2
                        continue
                    break
                j += 1
            tokens.append(("str", texto[i:j + 1]))
            i = j + 1
        elif c in "\"`[":
            cierre = "]" if c == "[" else c
            j = i + 1
            partes = []
            while True:
                if j >= n:
                    raise _NoRepresentable("sql_no_analizable")
                if texto[j] == cierre:
                    if cierre != "]" and j + 1 < n and texto[j + 1] == cierre:
                        partes.append(cierre)
                        j += 2
                        continue
                    break
                partes.append(texto[j])
                j += 1
            tokens.append(("id", "".join(partes).casefold()))
            i = j + 1
        elif c.isdigit() or (c == "." and i + 1 < n and texto[i + 1].isdigit()):
            m = re.compile(r"0[xX][0-9a-fA-F]+|(\d+\.?\d*|\.\d+)([eE][+-]?\d+)?").match(texto, i)
            tokens.append(("num", m.group(0).casefold()))
            i = m.end()
        elif c.isalpha() or c == "_" or ord(c) > 127:
            j = i + 1
            while j < n and (texto[j].isalnum() or texto[j] in "_$" or ord(texto[j]) > 127):
                j += 1
            tokens.append(("word", texto[i:j].casefold()))
            i = j
        elif texto[i:i + 2] in _OPERADORES_DOBLES:
            tokens.append(("punct", texto[i:i + 2]))
            i += 2
        else:
            tokens.append(("punct", c))
            i += 1
    return tokens


def _texto_normalizado(tokens):
    texto = " ".join(valor for _, valor in tokens)
    return re.sub(r"\s*([(),])\s*", r"\1", texto)


def _normalizar_sql(sql):
    return _texto_normalizado(_tokenizar(sql))


def _grupo_entre_parentesis(tokens, inicio):
    """tokens[inicio] es '('. Devuelve (tokens_internos, indice_posterior_al_cierre)."""
    profundidad = 0
    for i in range(inicio, len(tokens)):
        if tokens[i] == ("punct", "("):
            profundidad += 1
        elif tokens[i] == ("punct", ")"):
            profundidad -= 1
            if profundidad == 0:
                return tokens[inicio + 1:i], i + 1
    raise _NoRepresentable("sql_no_analizable")


def _items_de_tabla(sql):
    """Parte el cuerpo de CREATE TABLE en elementos de nivel superior."""
    tokens = _tokenizar(sql)
    try:
        inicio = tokens.index(("punct", "("))
    except ValueError:
        raise _NoRepresentable("sql_no_analizable") from None
    cuerpo, _ = _grupo_entre_parentesis(tokens, inicio)
    items, actual, profundidad = [], [], 0
    for token in cuerpo:
        if token == ("punct", "("):
            profundidad += 1
        elif token == ("punct", ")"):
            profundidad -= 1
        if token == ("punct", ",") and profundidad == 0:
            items.append(actual)
            actual = []
        else:
            actual.append(token)
    items.append(actual)
    if any(not item for item in items):
        raise _NoRepresentable("sql_no_analizable")
    return items


def _clausulas_no_expuestas(sql, columnas_pragma):
    """CHECK, COLLATE, ON CONFLICT, DEFERRABLE y AUTOINCREMENT del DDL de una tabla."""
    checks, colaciones, conflictos, diferibles = [], [], [], []
    autoincrement = False
    for item in _items_de_tabla(sql):
        es_constraint = item[0][0] == "word" and item[0][1] in _PALABRAS_CONSTRAINT_TABLA
        if es_constraint:
            propietario = "*tabla*"
        else:
            if item[0][0] not in ("word", "id") or item[0][1] not in columnas_pragma:
                raise _NoRepresentable("ddl_no_coincide_con_pragma")
            propietario = item[0][1]
        for i, token in enumerate(item):
            if token[0] != "word":
                continue
            palabra = token[1]
            if palabra == "autoincrement":
                autoincrement = True
            elif palabra == "check" and i + 1 < len(item) and item[i + 1] == ("punct", "("):
                interno, _ = _grupo_entre_parentesis(item, i + 1)
                checks.append(_texto_normalizado(interno))
            elif palabra == "collate" and not es_constraint and i + 1 < len(item):
                colaciones.append([propietario, item[i + 1][1]])
            elif palabra == "on" and i + 2 < len(item) and item[i + 1] == ("word", "conflict"):
                conflictos.append([propietario, item[i + 2][1]])
            elif palabra == "deferrable":
                partes = (["not"] if i > 0 and item[i - 1] == ("word", "not") else []) + ["deferrable"]
                if i + 2 < len(item) and item[i + 1] == ("word", "initially"):
                    partes += ["initially", item[i + 2][1]]
                diferibles.append([propietario, " ".join(partes)])
            elif palabra == "generated" or (
                palabra == "as" and not es_constraint and i + 1 < len(item) and item[i + 1] == ("punct", "(")
            ):
                raise _NoRepresentable("columna_generada")
    return {
        "autoincrement": autoincrement,
        "checks": sorted(checks),
        "colaciones": sorted(colaciones),
        "on_conflict": sorted(conflictos),
        "diferibles": sorted(diferibles),
    }


def _identificador(nombre):
    return '"' + str(nombre).replace('"', '""') + '"'


def _tipo_normalizado(tipo):
    return _normalizar_sql(tipo or "").upper()


def _defecto_normalizado(valor):
    return None if valor is None else _normalizar_sql(valor)


def _estructura_tabla(cursor, nombre, sql, info_lista):
    ident = _identificador(nombre)
    if info_lista is None:
        raise _NoRepresentable("table_list_sin_tabla")
    tipo_objeto, sin_rowid, estricta = info_lista
    if tipo_objeto != "table":
        raise _NoRepresentable("tabla_virtual")
    if sql is None:
        raise _NoRepresentable("sql_ausente")

    cursor.execute(f"PRAGMA main.table_xinfo({ident})")
    filas = cursor.fetchall()
    if not filas:
        raise _NoRepresentable("sin_columnas")
    columnas = []
    for _cid, col, tipo, no_nulo, defecto, pk, oculta in filas:
        if oculta != 0:
            raise _NoRepresentable("columna_generada_o_oculta")
        columnas.append({
            "nombre": str(col).casefold(),
            "tipo": _tipo_normalizado(tipo),
            "no_nulo": int(no_nulo),
            "defecto": _defecto_normalizado(defecto),
            "pk": int(pk),
        })
    nombres = {c["nombre"] for c in columnas}
    if len(nombres) != len(columnas):
        raise _NoRepresentable("columnas_duplicadas")
    columnas.sort(key=lambda c: c["nombre"])
    extras = _clausulas_no_expuestas(sql, nombres)

    cursor.execute(f"PRAGMA main.foreign_key_list({ident})")
    grupos = {}
    for fila in cursor.fetchall():
        id_fk, secuencia, padre, desde, hacia, al_actualizar, al_borrar, coincidencia = fila
        grupos.setdefault(id_fk, []).append(
            (secuencia, str(padre).casefold(), str(desde).casefold(), hacia, al_actualizar, al_borrar, coincidencia)
        )
    claves_foraneas = []
    for partes in grupos.values():
        partes.sort()
        padre = partes[0][1]
        hacia = [p[3] for p in partes]
        if any(valor is None for valor in hacia):
            cursor.execute(f"PRAGMA main.table_xinfo({_identificador(padre)})")
            pk_padre = [str(f[1]).casefold() for f in sorted(cursor.fetchall(), key=lambda f: f[5]) if f[5] > 0]
            if len(pk_padre) != len(partes):
                # Padre ausente o con PK incompatible: se conserva como referencia no resuelta.
                hacia = ["?"] * len(partes)
            else:
                hacia = pk_padre
        else:
            hacia = [str(valor).casefold() for valor in hacia]
        claves_foraneas.append({
            "desde": [p[2] for p in partes],
            "padre": padre,
            "hacia": hacia,
            "al_actualizar": str(partes[0][4]).upper(),
            "al_borrar": str(partes[0][5]).upper(),
            "coincidencia": str(partes[0][6]).upper(),
        })
    claves_foraneas.sort(key=lambda fk: json.dumps(fk, sort_keys=True))

    cursor.execute(f"PRAGMA main.index_list({ident})")
    indices = []
    for fila in cursor.fetchall():
        nombre_indice, unico, origen, parcial = fila[1], int(fila[2]), fila[3], int(fila[4])
        cursor.execute(f"PRAGMA main.index_xinfo({_identificador(nombre_indice)})")
        columnas_indice = [
            [None if f[2] is None else str(f[2]).casefold(), int(f[3]), str(f[4]).casefold()]
            for f in sorted(cursor.fetchall(), key=lambda f: f[0]) if f[5]
        ]
        indice = {"origen": origen, "unico": unico, "parcial": parcial, "columnas": columnas_indice}
        if origen == "c":
            cursor.execute(
                "SELECT sql FROM main.sqlite_master WHERE type='index' AND name=?", (nombre_indice,)
            )
            fila_sql = cursor.fetchone()
            if not fila_sql or fila_sql[0] is None:
                raise _NoRepresentable("sql_indice_ausente")
            tokens = _tokenizar(fila_sql[0])
            indice["nombre"] = str(nombre_indice).casefold()
            if any(columna[0] is None for columna in columnas_indice):
                inicio = tokens.index(("punct", "("))
                interno, _ = _grupo_entre_parentesis(tokens, inicio)
                indice["expresiones"] = _texto_normalizado(interno)
            if parcial:
                posiciones = [i for i, t in enumerate(tokens) if t == ("word", "where")]
                if not posiciones:
                    raise _NoRepresentable("sql_indice_no_analizable")
                indice["donde"] = _texto_normalizado(tokens[posiciones[-1] + 1:])
        elif origen not in ("u", "pk"):
            raise _NoRepresentable("origen_indice_desconocido")
        indices.append(indice)
    indices.sort(key=lambda i: json.dumps(i, sort_keys=True))

    return {
        "nombre": str(nombre).casefold(),
        "sin_rowid": int(sin_rowid),
        "estricta": int(estricta),
        "columnas": columnas,
        "claves_foraneas": claves_foraneas,
        "indices": indices,
        **extras,
    }


def representacion_estructural_sqlite(conexion):
    """Devuelve la representación canónica (dict serializable) o lanza _NoRepresentable."""
    if not isinstance(conexion, sqlite3.Connection):
        raise TypeError("Se requiere una sqlite3.Connection.")
    cursor = conexion.cursor()
    try:
        cursor.execute("PRAGMA main.table_list")
        lista = {
            str(f[1]): (f[2], f[4], f[5])
            for f in cursor.fetchall() if f[0] == "main" and not str(f[1]).startswith("sqlite_")
        }
        cursor.execute(
            "SELECT type, name, tbl_name, sql FROM main.sqlite_master "
            "WHERE name NOT LIKE 'sqlite_%' ORDER BY type, name"
        )
        objetos = cursor.fetchall()
        tablas = [
            _estructura_tabla(cursor, nombre, sql, lista.get(nombre))
            for tipo, nombre, _tbl, sql in objetos if tipo == "table"
        ]
        derivados = []
        for tipo, nombre, tabla, sql in objetos:
            if tipo in ("trigger", "view"):
                if sql is None:
                    raise _NoRepresentable("sql_ausente")
                derivados.append({
                    "tipo": tipo, "nombre": str(nombre).casefold(),
                    "tabla": str(tabla).casefold(), "sql": _normalizar_sql(sql),
                })
        # Un índice sin tabla propia o cualquier otro tipo es desconocido: no se descarta en silencio.
        conocidos = {nombre for tipo, nombre, _t, _s in objetos if tipo == "table"}
        for tipo, nombre, tabla, _sql in objetos:
            if tipo == "index" and str(tabla) not in conocidos:
                raise _NoRepresentable("indice_sin_tabla")
            if tipo not in ("table", "index", "trigger", "view"):
                raise _NoRepresentable("objeto_desconocido")
        return {
            "formato": FORMATO_HUELLA_ESTRUCTURAL,
            "tablas": sorted(tablas, key=lambda t: t["nombre"]),
            "triggers_y_vistas": sorted(derivados, key=lambda d: (d["tipo"], d["nombre"])),
        }
    finally:
        cursor.close()


def calcular_huella_estructural_sqlite(conexion):
    """Calcula la huella SHA-256 de la estructura. Solo lectura; no lanza por datos de la base."""
    if not isinstance(conexion, sqlite3.Connection):
        raise TypeError("Se requiere una sqlite3.Connection.")
    try:
        cursor = conexion.cursor()
        try:
            cursor.execute("PRAGMA schema_version")
            antes = cursor.fetchone()
            representacion = representacion_estructural_sqlite(conexion)
            cursor.execute("PRAGMA schema_version")
            despues = cursor.fetchone()
            cursor.execute("SELECT COUNT(*) FROM sqlite_temp_master")
            temporales = int(cursor.fetchone()[0])
        finally:
            cursor.close()
        if antes is None or antes != despues:
            return ResultadoHuellaEstructuralSQLite(False, razones=("esquema_cambio_durante_lectura",))
    except _NoRepresentable as error:
        return ResultadoHuellaEstructuralSQLite(False, razones=(str(error),))
    except sqlite3.Error:
        # Sin detalle: el mensaje de SQLite podría incluir nombres de la base.
        return ResultadoHuellaEstructuralSQLite(False, razones=("error_sqlite",))
    serializado = json.dumps(representacion, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    huella = hashlib.sha256(serializado.encode("ascii")).hexdigest()
    return ResultadoHuellaEstructuralSQLite(
        True, huella=huella, representacion=representacion, objetos_temporales=temporales
    )
