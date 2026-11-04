"""Contrato coordinado, solo :memory:; ejecutar con guardia externa previa.

Complementa test_seguridad_migracion_indices_fiscales con fotos de metadatos,
fallos en operaciones concretas, rollback de grupo y transacciones del llamador.
expectedFailure documenta defectos pendientes, no protecciones implementadas.
"""

import io
import sqlite3
import unittest
from contextlib import redirect_stdout

from tests.test_catalogo_indices_fiscales import ACTUALES, HISTORICAS, database


class SeguridadNoGarantizada(AssertionError):
    """Fallo del contrato, distinguible de errores del fixture o de la guardia."""


class _CursorConFallo:
    def __init__(self, cursor, operacion, nombre, error, modo="error"):
        self.cursor = cursor
        self.operacion = operacion
        self.nombre = nombre
        self.error = error
        self.modo = modo
        self.intervenciones = 0
        self.completadas = []
        self.verificaciones = 0
        self.armado = False

    def execute(self, sql, parametros=()):
        texto = " ".join(sql.split()).upper()
        es_create = texto.startswith("CREATE UNIQUE INDEX")
        es_drop = texto.startswith("DROP INDEX")
        objetivo = f" {self.nombre.upper()} " in f"{texto} "
        if self.armado and self.modo == "verificacion" and (
            ("SQLITE_MASTER" in texto or "SQLITE_SCHEMA" in texto) and texto.startswith("SELECT")
            or texto.startswith("PRAGMA") and "INDEX" in texto
        ):
            self.verificaciones += 1
            self.armado = False
            raise self.error
        coincide = objetivo and (
            self.operacion == "CREATE" and es_create or self.operacion == "DROP" and es_drop
        )
        if coincide:
            self.intervenciones += 1
            if self.modo == "error":
                raise self.error
            if self.modo == "definicion":
                tabla = next(t for n, t, _ in ACTUALES if n == self.nombre)
                self.cursor.execute(
                    f"CREATE UNIQUE INDEX {self.nombre} ON {tabla}(id) WHERE id > 0"
                )
                self.completadas.append(sql)
                return self
        self.cursor.execute(sql, parametros)
        self.completadas.append(sql)
        if coincide and self.modo == "verificacion":
            self.armado = True
        return self

    def __getattr__(self, nombre):
        return getattr(self.cursor, nombre)


def _solicitud(definicion):
    nombre, tabla, sql = definicion
    clave, condicion = sql.split(f"ON {tabla}(", 1)[1].split(") WHERE ", 1)
    return nombre, clave, condicion, tabla


class AtomicidadIndicesFiscalesTest(unittest.TestCase):
    def setUp(self):
        self.conexion = sqlite3.connect(":memory:")
        self.addCleanup(self.conexion.close)
        self.tablas()

    def tablas(self, ambiente=True):
        columna = "ambiente_arca TEXT, " if ambiente else ""
        self.conexion.execute(
            f"CREATE TABLE main.factura_arca(id INTEGER PRIMARY KEY, {columna}"
            "emisor_id INTEGER, punto_venta_num INTEGER, tipo_comprobante_num INTEGER, "
            "numero_comprobante_num INTEGER, cae TEXT)"
        )
        self.conexion.execute(
            f"CREATE TABLE main.intentos_emision_arca(id INTEGER PRIMARY KEY, {columna}"
            "cuit_emisor TEXT, punto_venta INTEGER, tipo_comprobante INTEGER, "
            "numero_planificado INTEGER, estado TEXT)"
        )
        self.conexion.execute("CREATE TABLE main.resumenes(id INTEGER PRIMARY KEY, cae TEXT)")
        self.conexion.execute(
            "CREATE INDEX main.idx_resumenes_control ON resumenes(cae)"
        )
        self.conexion.execute("INSERT INTO resumenes VALUES(1, 'control')")
        self.conexion.commit()

    def factura(self, numero=1, cae="111", ambiente="HOMOLOGACION"):
        self.conexion.execute(
            "INSERT INTO factura_arca(ambiente_arca, emisor_id, punto_venta_num, "
            "tipo_comprobante_num, numero_comprobante_num, cae) VALUES(?,1,2,11,?,?)",
            (ambiente, numero, cae),
        )

    def historicos(self):
        self.factura()
        self.factura(2, "222", None)
        self.conexion.execute(HISTORICAS[0][2])
        self.conexion.execute(HISTORICAS[1][2])
        self.conexion.commit()

    def global_intentos(self):
        self.conexion.execute(
            "INSERT INTO intentos_emision_arca(ambiente_arca,cuit_emisor,punto_venta,"
            "tipo_comprobante,numero_planificado,estado) "
            "VALUES(NULL,'20123456789',2,11,1,'ENVIANDO')"
        )
        self.conexion.execute(HISTORICAS[2][2])
        self.conexion.commit()

    def foto(self):
        tablas = ("factura_arca", "intentos_emision_arca", "resumenes")
        indices = self.conexion.execute(
            "SELECT name,tbl_name,sql FROM main.sqlite_master WHERE type='index' ORDER BY name"
        ).fetchall()
        return {
            "objetos": self.conexion.execute(
                "SELECT type,name,tbl_name,sql FROM main.sqlite_master ORDER BY type,name"
            ).fetchall(),
            "indices": indices,
            "index_list": {
                tabla: sorted(self.conexion.execute(f"PRAGMA main.index_list({tabla})").fetchall())
                for tabla in tablas
            },
            "index_xinfo": {
                nombre: self.conexion.execute(f"PRAGMA main.index_xinfo({nombre})").fetchall()
                for nombre, _tabla, _sql in indices
            },
            "columnas": {
                tabla: self.conexion.execute(f"PRAGMA main.table_info({tabla})").fetchall()
                for tabla in tablas
            },
            "filas": {
                tabla: self.conexion.execute(f"SELECT * FROM main.{tabla} ORDER BY id").fetchall()
                for tabla in tablas
            },
            "user_version": self.conexion.execute("PRAGMA main.user_version").fetchone()[0],
            "total_changes": self.conexion.total_changes,
        }

    def ejecutar(self, funcion, *args, cursor=None):
        # No commit/rollback: la transaccion y los savepoints pertenecen al caso.
        error = None
        salida = io.StringIO()
        with redirect_stdout(salida):
            try:
                funcion(cursor if cursor is not None else self.conexion.cursor(), *args)
            except (sqlite3.Error, ValueError) as fallo:
                error = fallo
        return error, salida.getvalue()

    def exigir(self, condicion, motivo):
        if not condicion:
            raise SeguridadNoGarantizada(motivo)

    def restaurada(self, antes, error, error_esperado=None):
        despues = self.foto()
        diferencias = [clave for clave in antes if antes[clave] != despues[clave]]
        motivos = []
        if error is None:
            motivos.append("la migracion no propago el bloqueo")
        if error_esperado is not None and error is not error_esperado:
            motivos.append("no se propago la excepcion inyectada")
        if diferencias:
            motivos.append("no se restauro: " + ", ".join(diferencias))
        self.exigir(not motivos, "; ".join(motivos))

    def fallo_factura(self, operacion, posicion, error_tipo, individual=False, exterior=False):
        self.historicos()
        if exterior:
            self.conexion.execute("BEGIN")
            self.conexion.execute("INSERT INTO resumenes VALUES(2,'pendiente')")
            self.conexion.execute("SAVEPOINT punto_llamador")
        antes = self.foto()
        error_simulado = error_tipo(f"inyectado {operacion} {ACTUALES[posicion][0]}")
        cursor = _CursorConFallo(
            self.conexion.cursor(), operacion, ACTUALES[posicion][0], error_simulado
        )
        funcion = (
            database._migrar_indice_factura_arca if individual
            else database.migrar_indices_unicos_factura_arca
        )
        args = _solicitud(ACTUALES[posicion]) if individual else ()
        error, _ = self.ejecutar(funcion, *args, cursor=cursor)
        self.assertEqual(cursor.intervenciones, 1, "No se alcanzo el fallo programado")
        if operacion == "CREATE" and posicion == 2:
            self.assertTrue(any(
                sql.startswith("DROP INDEX") and ACTUALES[2][0] in sql
                for sql in cursor.completadas
            ), "CREATE no fue precedido por el DROP del historico")
        if not individual and posicion > 0:
            self.assertTrue(any(
                sql.startswith("CREATE UNIQUE INDEX") and ACTUALES[0][0] in sql
                for sql in cursor.completadas
            ), "No hubo reemplazos exitosos anteriores al fallo")
        if exterior:
            self.assertTrue(self.conexion.in_transaction)
            self.conexion.execute("ROLLBACK TO punto_llamador")
            self.conexion.execute("RELEASE punto_llamador")
            # Se comprueba la foto ANTES del rollback del llamador en otro caso.
            self.assertEqual(self.foto(), antes)
        else:
            self.restaurada(antes, error, error_simulado)
        return error

    @unittest.expectedFailure
    def test_create_operational_individual_restaura_sql_y_metadatos(self):
        # El helper propaga OperationalError, pero ya perdio el indice historico.
        self.fallo_factura("CREATE", 2, sqlite3.OperationalError, individual=True)

    @unittest.expectedFailure
    def test_create_integrity_individual_restaura_y_propaga(self):
        # IntegrityError se convierte en advertencia tras eliminar el historico.
        self.fallo_factura("CREATE", 2, sqlite3.IntegrityError, individual=True)

    @unittest.expectedFailure
    def test_ultimo_create_factura_revierte_todos_los_reemplazos(self):
        # Falta SAVEPOINT de grupo: quedan los tres indices anteriores aplicados.
        self.fallo_factura("CREATE", 3, sqlite3.OperationalError)

    @unittest.expectedFailure
    def test_drop_tardio_factura_revierte_reemplazos_anteriores(self):
        # El DROP falla, pero los dos indices de identidad ya fueron modificados.
        self.fallo_factura("DROP", 2, sqlite3.OperationalError)

    def test_drop_individual_fallido_conserva_indice_y_propaga(self):
        self.fallo_factura("DROP", 2, sqlite3.OperationalError, individual=True)

    @unittest.expectedFailure
    def test_trim_historico_null_no_deja_grupo_parcial(self):
        # El duplicado NULL aparece en el ultimo destino y el grupo continua.
        self.factura(1, "111", None)
        self.factura(2, " 111 ", None)
        self.conexion.execute(HISTORICAS[1][2])
        self.conexion.commit()
        antes = self.foto()
        clave = self.conexion.execute(
            "SELECT TRIM(cae),COUNT(*) FROM factura_arca "
            "WHERE ambiente_arca IS NULL GROUP BY TRIM(cae) HAVING COUNT(*)>1"
        ).fetchall()
        self.assertEqual(clave, [("111", 2)])
        error, salida = self.ejecutar(database.migrar_indices_unicos_factura_arca)
        if error is None:
            self.assertIn(ACTUALES[3][0] + " NO se creo por duplicados", salida)
        self.restaurada(antes, error)

    def bloqueo_tardio(self, otra_tabla=False):
        self.factura()
        tabla = "resumenes" if otra_tabla else "factura_arca"
        self.conexion.execute(f"CREATE UNIQUE INDEX {ACTUALES[3][0]} ON {tabla}(cae)")
        self.conexion.commit()
        antes = self.foto()
        sql_existente = self.conexion.execute(
            "SELECT sql FROM main.sqlite_master WHERE name=?", (ACTUALES[3][0],)
        ).fetchone()[0]
        self.assertEqual(
            database._reconocer_definicion_indice_fiscal(
                ACTUALES[3][0], tabla, sql_existente
            ), "DESCONOCIDA"
        )
        error, _ = self.ejecutar(database.migrar_indices_unicos_factura_arca)
        self.restaurada(antes, error)

    @unittest.expectedFailure
    def test_desconocido_tardio_preserva_grupo_completo(self):
        # Se elimina la definicion desconocida y quedan cambios previos de grupo.
        self.bloqueo_tardio()

    @unittest.expectedFailure
    def test_homonimo_tardio_en_otra_tabla_preserva_grupo_completo(self):
        # Se elimina una proteccion de resumenes para crear otra en factura_arca.
        self.bloqueo_tardio(otra_tabla=True)

    def fallo_global(self, posicion, operacion="CREATE"):
        self.global_intentos()
        antes = self.foto()
        nombre = ACTUALES[posicion][0] if operacion == "CREATE" else HISTORICAS[2][0]
        simulado = sqlite3.OperationalError(f"inyectado {operacion} {nombre}")
        cursor = _CursorConFallo(self.conexion.cursor(), operacion, nombre, simulado)
        error, _ = self.ejecutar(
            database.migrar_indices_activos_intentos_emision_arca, cursor=cursor
        )
        self.assertEqual(cursor.intervenciones, 1)
        if posicion == 5 and operacion == "CREATE":
            self.assertTrue(any(ACTUALES[4][0] in s and s.startswith("CREATE")
                                for s in cursor.completadas))
        self.restaurada(antes, error, simulado)

    @unittest.expectedFailure
    def test_primer_create_intentos_conserva_global(self):
        # El global se elimina antes del primer reemplazo.
        self.fallo_global(4)

    @unittest.expectedFailure
    def test_ultimo_create_intentos_conserva_global_sin_reemplazo_parcial(self):
        # El global desaparece y queda solo el reemplazo por ambiente.
        self.fallo_global(5)

    def test_drop_global_fallido_preserva_filas_indices_y_error(self):
        self.fallo_global(4, operacion="DROP")

    def fallo_verificacion(self, modo):
        self.historicos()
        antes = self.foto()
        simulado = sqlite3.OperationalError("inyectado verificacion posterior")
        cursor = _CursorConFallo(
            self.conexion.cursor(), "CREATE", ACTUALES[2][0], simulado, modo=modo
        )
        error, _ = self.ejecutar(
            database._migrar_indice_factura_arca, *_solicitud(ACTUALES[2]), cursor=cursor
        )
        self.assertEqual(cursor.intervenciones, 1, "CREATE objetivo no ejecutado")
        if modo == "verificacion":
            self.exigir(cursor.verificaciones == 1,
                        "CREATE exitoso no fue seguido de una consulta de verificacion")
            self.restaurada(antes, error, simulado)
        else:
            self.restaurada(antes, error)

    @unittest.expectedFailure
    def test_create_exitoso_con_definicion_incorrecta_debe_revertirse(self):
        # CREATE devuelve exito pero la definicion creada no se verifica.
        self.fallo_verificacion("definicion")

    @unittest.expectedFailure
    def test_error_de_consulta_de_verificacion_debe_restaurar(self):
        # Hoy no existe verificacion posterior: el fallo queda armado sin ejecutar.
        self.fallo_verificacion("verificacion")

    @unittest.expectedFailure
    def test_fallo_grupo_preserva_transaccion_y_savepoint_sin_rollback_del_llamador(self):
        # Preservar la transaccion no basta: el grupo debe deshacer sus propios DDL.
        self.historicos()
        self.conexion.execute("BEGIN")
        self.conexion.execute("INSERT INTO resumenes VALUES(2,'pendiente')")
        self.conexion.execute("SAVEPOINT punto_llamador")
        antes = self.foto()
        simulado = sqlite3.OperationalError("ultimo CREATE")
        cursor = _CursorConFallo(self.conexion.cursor(), "CREATE", ACTUALES[3][0], simulado)
        error, _ = self.ejecutar(database.migrar_indices_unicos_factura_arca, cursor=cursor)
        self.assertEqual(cursor.intervenciones, 1)
        despues = self.foto()
        self.assertTrue(self.conexion.in_transaction)
        self.conexion.execute("ROLLBACK TO punto_llamador")
        self.conexion.execute("RELEASE punto_llamador")
        self.assertEqual(self.foto(), antes, "El savepoint del llamador se perdio")
        self.exigir(despues == antes and error is simulado,
                    "El grupo dejo DDL parciales antes del rollback del llamador")

    def test_rollback_savepoint_del_llamador_restaura_grupo_y_filas_pendientes(self):
        self.fallo_factura("CREATE", 3, sqlite3.OperationalError, exterior=True)
        self.conexion.rollback()
        self.assertEqual(self.conexion.execute("SELECT id FROM resumenes").fetchall(), [(1,)])

    def sin_transaccion(self, funcion):
        self.historicos()
        self.global_intentos()
        antes = self.foto()
        self.assertFalse(self.conexion.in_transaction)
        error, _ = self.ejecutar(funcion)
        self.assertIsNone(error)
        abierta = self.conexion.in_transaction
        self.conexion.rollback()
        self.exigir(abierta and self.foto() == antes,
                    "Sin BEGIN previo, los DDL se confirman y rollback no restaura")

    @unittest.expectedFailure
    def test_factura_sin_transaccion_permanece_reversible_por_el_llamador(self):
        # No se abre transaccion exterior y cada DDL queda confirmado.
        self.sin_transaccion(database.migrar_indices_unicos_factura_arca)

    @unittest.expectedFailure
    def test_intentos_sin_transaccion_permanece_reversible_por_el_llamador(self):
        # El DROP global y los CREATE quedan confirmados sin BEGIN previo.
        self.sin_transaccion(database.migrar_indices_activos_intentos_emision_arca)

    def test_indices_actuales_idempotentes_con_metadatos_y_transaccion_intactos(self):
        self.factura()
        self.global_intentos()
        self.conexion.execute(f"DROP INDEX {HISTORICAS[2][0]}")
        for _nombre, _tabla, sql in ACTUALES:
            self.conexion.execute(sql)
        for nombre, tabla, _sql in ACTUALES:
            self.assertEqual(
                database._validar_indice_fiscal_sqlite(self.conexion.cursor(), nombre, tabla),
                "ACTUAL",
            )
        self.conexion.commit()
        self.conexion.execute("BEGIN")
        self.conexion.execute("SAVEPOINT punto_llamador")
        antes = self.foto()
        trazas = []
        self.conexion.set_trace_callback(trazas.append)
        try:
            for funcion in (
                database.migrar_indices_unicos_factura_arca,
                database.migrar_indices_activos_intentos_emision_arca,
            ):
                for _ in range(2):
                    error, salida = self.ejecutar(funcion)
                    self.assertIsNone(error)
                    self.assertEqual(salida, "")
        finally:
            self.conexion.set_trace_callback(None)
        self.assertEqual(self.foto(), antes)
        self.assertTrue(self.conexion.in_transaction)
        self.assertFalse(any(s.lstrip().upper().startswith(
            ("COMMIT", "END", "ROLLBACK", "ALTER", "CREATE", "INSERT", "UPDATE", "DELETE")
        ) for s in trazas))
        self.conexion.execute("ROLLBACK TO punto_llamador")
        self.conexion.execute("RELEASE punto_llamador")

    def sin_ambiente(self):
        self.conexion.close()
        self.conexion = sqlite3.connect(":memory:")
        self.addCleanup(self.conexion.close)
        self.tablas(ambiente=False)
        self.conexion.execute("INSERT INTO factura_arca VALUES(1,1,2,11,1,'111')")
        self.conexion.execute(
            "INSERT INTO intentos_emision_arca VALUES(1,'20123456789',2,11,1,'ENVIANDO')"
        )
        for _nombre, _tabla, sql in HISTORICAS:
            self.conexion.execute(sql)
        self.conexion.commit()

    def test_ambiente_ausente_se_agrega_null_y_rollback_exterior_restaura(self):
        self.sin_ambiente()
        antes = self.foto()
        self.conexion.execute("BEGIN")
        self.conexion.execute("SAVEPOINT punto_llamador")
        for funcion in (
            database.migrar_indices_unicos_factura_arca,
            database.migrar_indices_activos_intentos_emision_arca,
        ):
            error, _ = self.ejecutar(funcion)
            self.assertIsNone(error)
        for tabla in ("factura_arca", "intentos_emision_arca"):
            self.assertEqual(
                self.conexion.execute(f"SELECT ambiente_arca FROM {tabla}").fetchall(), [(None,)]
            )
            columnas_originales = ", ".join(fila[1] for fila in antes["columnas"][tabla])
            self.assertEqual(
                self.conexion.execute(
                    f"SELECT {columnas_originales} FROM {tabla} ORDER BY id"
                ).fetchall(), antes["filas"][tabla],
            )
        self.assertEqual(self.foto()["user_version"], antes["user_version"])
        self.conexion.execute("ROLLBACK TO punto_llamador")
        self.conexion.execute("RELEASE punto_llamador")
        self.assertEqual(self.foto(), antes)
        self.conexion.rollback()

    @unittest.expectedFailure
    def test_fallo_intentos_revierte_columna_ambiente_y_global(self):
        # ALTER y DROP quedan fuera de una proteccion de grupo incluso con BEGIN.
        self.sin_ambiente()
        self.conexion.execute("BEGIN")
        antes = self.foto()
        simulado = sqlite3.OperationalError("CREATE tras ALTER")
        cursor = _CursorConFallo(self.conexion.cursor(), "CREATE", ACTUALES[5][0], simulado)
        error, _ = self.ejecutar(
            database.migrar_indices_activos_intentos_emision_arca, cursor=cursor
        )
        self.assertEqual(cursor.intervenciones, 1)
        self.assertTrue(self.conexion.in_transaction)
        self.restaurada(antes, error, simulado)

    @unittest.expectedFailure
    def test_ambiente_sin_transaccion_previa_es_reversible(self):
        # ALTER sin BEGIN se confirma; rollback del llamador no devuelve el esquema.
        self.sin_ambiente()
        antes = self.foto()
        for funcion in (
            database.migrar_indices_unicos_factura_arca,
            database.migrar_indices_activos_intentos_emision_arca,
        ):
            error, _ = self.ejecutar(funcion)
            self.assertIsNone(error)
        abierta = self.conexion.in_transaction
        self.conexion.rollback()
        self.exigir(abierta and self.foto() == antes,
                    "ambiente_arca y los indices no son reversibles sin BEGIN exterior")


if __name__ == "__main__":
    unittest.main()
