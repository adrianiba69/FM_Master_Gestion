"""Etapa 3D.4C.5D.4: control transaccional de claves foráneas (solo bases ficticias).

Bases en memoria o en directorios temporales. ``database.conectar`` queda bloqueado y
no se usa ninguna ruta real. Las tablas funcionales del sistema no se reconstruyen.
"""

import re
import sqlite3
import tempfile
import unittest
from collections import Counter
from pathlib import Path
from unittest.mock import patch

from services import sqlite_control_claves_foraneas as modulo
from services.sqlite_control_claves_foraneas import (
    ErrorAntesDeConfirmar,
    ErrorControlClavesForaneas,
    ErrorDespuesDeConfirmar,
    ErrorEstadoIncierto,
    ejecutar_con_claves_foraneas_controladas as ejecutar,
)
from tests.test_compatibilidad_esquemas_historicos_3d4c5c2 import ESQUEMAS_HISTORICOS, database

ESQUEMA = (
    "CREATE TABLE padre(id INTEGER PRIMARY KEY AUTOINCREMENT, nombre TEXT NOT NULL)",
    "CREATE TABLE hija(id INTEGER PRIMARY KEY AUTOINCREMENT, "
    "padre_id INTEGER NOT NULL REFERENCES padre(id) ON DELETE CASCADE, valor TEXT)",
    "INSERT INTO padre(nombre) VALUES ('p1'), ('p2')",
    "INSERT INTO hija(padre_id, valor) VALUES (1, 'h1'), (2, 'h2')",
)
MODOS = ("DELETE", "WAL")


class ConexionInstrumentada(sqlite3.Connection):
    """Permite inyectar fallos: ``fallos[patron] = (desde_llamada, accion)``."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fallos = {}
        self.llamadas = Counter()

    def _inyectar(self, clave):
        self.llamadas[clave] += 1
        for patron, (desde, accion) in self.fallos.items():
            if patron == clave and self.llamadas[clave] >= desde:
                return accion
        return None

    def execute(self, sql, *args):
        accion = self._inyectar(sql)
        if accion == "omitir":
            return super().execute("SELECT 1")
        if accion is not None:
            raise accion
        return super().execute(sql, *args)

    def commit(self):
        accion = self._inyectar("commit")
        if accion == "confirmar_y_fallar":
            super().commit()
            raise sqlite3.OperationalError("fallo posterior al commit")
        if accion is not None:
            raise accion
        return super().commit()

    def rollback(self):
        accion = self._inyectar("rollback")
        if accion is not None:
            raise accion
        return super().rollback()


class _Aislada(unittest.TestCase):
    def setUp(self):
        parche = patch.object(database, "conectar", side_effect=AssertionError("acceso a base real bloqueado"))
        parche.start()
        self.addCleanup(parche.stop)

    def conectar(self, destino=":memory:", **kwargs):
        kwargs.setdefault("factory", ConexionInstrumentada)
        conexion = sqlite3.connect(destino, **kwargs)
        self.addCleanup(conexion.close)
        return conexion

    def base(self, *, modo=None, esquema=ESQUEMA, fk=True, timeout=0.05):
        """Base lista: esquema confirmado y foreign_keys=ON (en archivo si se pide un modo)."""
        if modo is None:
            conexion = self.conectar()
        else:
            directorio = tempfile.TemporaryDirectory()
            self.addCleanup(directorio.cleanup)
            self.ruta = str(Path(directorio.name) / "ficticia.db")
            conexion = self.conectar(self.ruta, timeout=timeout)
            self.assertEqual(conexion.execute(f"PRAGMA journal_mode={modo}").fetchone()[0].upper(), modo)
        for sql in esquema:
            conexion.execute(sql)
        conexion.commit()
        if fk:
            conexion.execute("PRAGMA foreign_keys=ON")
        return conexion

    def otra(self, **kwargs):
        return self.conectar(self.ruta, factory=sqlite3.Connection, **kwargs)

    @staticmethod
    def datos(conexion):
        return {
            t: conexion.execute(f"SELECT * FROM {t} ORDER BY id").fetchall() for t in ("padre", "hija")
        }

    def assertRestaurada(self, conexion):
        self.assertEqual(conexion.execute("PRAGMA foreign_keys").fetchone()[0], 1)
        self.assertFalse(conexion.in_transaction)


def _agregar(conexion):
    conexion.execute("INSERT INTO padre(nombre) VALUES ('p3')")
    conexion.execute("INSERT INTO hija(padre_id, valor) VALUES (3, 'h3')")
    return "hecho"


class OperacionExitosaTest(_Aislada):
    def test_confirma_devuelve_el_resultado_y_restaura_claves_foraneas(self):
        conexion = self.base()
        resultado = ejecutar(conexion, _agregar)
        self.assertTrue(resultado.confirmada)
        self.assertEqual(resultado.resultado, "hecho")
        self.assertRestaurada(conexion)
        self.assertEqual(len(self.datos(conexion)["padre"]), 3)
        self.assertEqual(len(self.datos(conexion)["hija"]), 3)

    def test_la_operacion_recibe_una_interfaz_restringida_con_transaccion_y_claves_apagadas(self):
        conexion = self.base()
        vistos = {}

        def operacion(c):
            vistos.update(
                tipo=type(c), es_la_conexion_real=c is conexion, es_conexion=isinstance(c, sqlite3.Connection),
                fk=c.execute("PRAGMA foreign_keys").fetchone()[0],
                reserva=conexion.in_transaction,
            )

        ejecutar(conexion, operacion)
        self.assertEqual(
            vistos,
            {"tipo": modulo.ConexionRestringida, "es_la_conexion_real": False, "es_conexion": False,
             "fk": 0, "reserva": True},
        )

    def test_la_conexion_externa_sigue_abierta_y_utilizable(self):
        conexion = self.base()
        ejecutar(conexion, _agregar)
        self.assertEqual(conexion.execute("SELECT COUNT(*) FROM padre").fetchone()[0], 3)
        conexion.execute("BEGIN")
        conexion.rollback()  # el autorizador fue retirado

    def test_las_claves_foraneas_vuelven_a_proteger_despues(self):
        conexion = self.base()
        ejecutar(conexion, _agregar)
        with self.assertRaises(sqlite3.IntegrityError):
            conexion.execute("INSERT INTO hija(padre_id, valor) VALUES (99, 'huerfana')")

    def test_conserva_registros_relacionados_al_reconstruir_una_tabla_ficticia_padre(self):
        conexion = self.base()
        antes = self.datos(conexion)
        secuencia = conexion.execute("SELECT seq FROM sqlite_sequence WHERE name='padre'").fetchone()[0]

        def reconstruir(c):
            c.execute("CREATE TABLE padre_nueva(id INTEGER PRIMARY KEY AUTOINCREMENT, nombre TEXT NOT NULL, extra TEXT)")
            c.execute("INSERT INTO padre_nueva(id, nombre) SELECT id, nombre FROM padre")
            c.execute("DROP TABLE padre")
            c.execute("ALTER TABLE padre_nueva RENAME TO padre")
            c.execute("UPDATE sqlite_sequence SET seq=? WHERE name='padre'", (secuencia,))

        ejecutar(conexion, reconstruir)
        despues = self.datos(conexion)
        self.assertEqual(despues["hija"], antes["hija"])
        self.assertEqual([f[:2] for f in despues["padre"]], antes["padre"])
        self.assertEqual({f[2] for f in conexion.execute("PRAGMA foreign_key_list(hija)")}, {"padre"})
        self.assertEqual(conexion.execute("PRAGMA foreign_key_check").fetchall(), [])
        self.assertRestaurada(conexion)

    def test_sin_el_mecanismo_el_mismo_drop_con_claves_activas_destruye_las_hijas(self):
        conexion = self.base()
        conexion.execute("BEGIN")
        conexion.execute("DROP TABLE padre")
        self.assertEqual(conexion.execute("SELECT COUNT(*) FROM hija").fetchone()[0], 0)
        conexion.rollback()


class RollbackTest(_Aislada):
    def test_excepcion_de_la_operacion_revierte_y_conserva_la_causa(self):
        conexion = self.base()
        antes = self.datos(conexion)

        def operacion(c):
            _agregar(c)
            raise ValueError("fallo ficticio")

        with self.assertRaises(ErrorAntesDeConfirmar) as contexto:
            ejecutar(conexion, operacion)
        error = contexto.exception
        self.assertIs(error.confirmada, False)
        self.assertTrue(error.conexion_apta)
        self.assertEqual(error.fase, "operacion")
        self.assertIsInstance(error.__cause__, ValueError)
        self.assertEqual(self.datos(conexion), antes)
        self.assertRestaurada(conexion)

    def test_violacion_de_clave_foranea_se_detecta_antes_de_confirmar(self):
        conexion = self.base()
        antes = self.datos(conexion)

        def operacion(c):
            c.execute("INSERT INTO hija(padre_id, valor) VALUES (99, 'huerfana')")

        with self.assertRaises(ErrorAntesDeConfirmar) as contexto:
            ejecutar(conexion, operacion)
        self.assertEqual(contexto.exception.fase, "validacion_final")
        self.assertIs(contexto.exception.confirmada, False)
        self.assertEqual(self.datos(conexion), antes)
        self.assertRestaurada(conexion)

    def test_borrar_un_padre_con_hijas_sin_reconstruirlo_tambien_se_rechaza(self):
        conexion = self.base()
        antes = self.datos(conexion)
        with self.assertRaises(ErrorAntesDeConfirmar):
            ejecutar(conexion, lambda c: c.execute("DELETE FROM padre WHERE id=1"))
        self.assertEqual(self.datos(conexion), antes)

    def test_los_mensajes_no_incluyen_datos_ni_rutas(self):
        conexion = self.base(modo="DELETE")
        with self.assertRaises(ErrorAntesDeConfirmar) as contexto:
            ejecutar(conexion, lambda c: c.execute("INSERT INTO hija(padre_id, valor) VALUES (99, 'secreto-fiscal')"))
        texto = str(contexto.exception) + repr(contexto.exception.__cause__)
        self.assertNotIn("secreto-fiscal", texto)
        self.assertNotIn(self.ruta, texto)
        self.assertNotIn("ficticia.db", str(contexto.exception))

    def test_interrupcion_se_relanza_sin_envolver_tras_revertir_y_restaurar(self):
        conexion = self.base()
        antes = self.datos(conexion)

        def operacion(c):
            _agregar(c)
            raise KeyboardInterrupt

        with self.assertRaises(KeyboardInterrupt):
            ejecutar(conexion, operacion)
        self.assertEqual(self.datos(conexion), antes)
        self.assertRestaurada(conexion)


class PrecondicionesTest(_Aislada):
    def assertRechazo(self, conexion, *, apta=True):
        llamada = []
        with self.assertRaises(ErrorAntesDeConfirmar) as contexto:
            ejecutar(conexion, lambda c: llamada.append(1))
        self.assertEqual(contexto.exception.fase, "precondiciones")
        self.assertIs(contexto.exception.confirmada, False)
        self.assertEqual(contexto.exception.conexion_apta, apta)
        self.assertEqual(llamada, [])
        return contexto.exception

    def test_integridad_previa_incorrecta(self):
        conexion = self.base(fk=False)
        conexion.execute("INSERT INTO hija(padre_id, valor) VALUES (99, 'huerfana')")
        conexion.commit()
        conexion.execute("PRAGMA foreign_keys=ON")
        antes = self.datos(conexion)
        self.assertRechazo(conexion)
        self.assertEqual(self.datos(conexion), antes)
        self.assertRestaurada(conexion)

    def test_quick_check_previo_distinto_de_ok(self):
        conexion = self.base()
        conexion.fallos["PRAGMA quick_check"] = (1, sqlite3.DatabaseError("simulado"))
        self.assertRechazo(conexion)

    def test_transaccion_previamente_abierta_no_se_toca(self):
        conexion = self.base()
        conexion.execute("BEGIN")
        conexion.execute("INSERT INTO padre(nombre) VALUES ('pendiente')")
        self.assertRechazo(conexion)
        self.assertTrue(conexion.in_transaction)
        self.assertEqual(conexion.execute("SELECT COUNT(*) FROM padre").fetchone()[0], 3)
        conexion.rollback()

    def test_estado_inicial_inseguro_de_claves_foraneas(self):
        conexion = self.base(fk=False)
        self.assertRechazo(conexion)
        self.assertEqual(conexion.execute("PRAGMA foreign_keys").fetchone()[0], 0)

    def test_modos_de_autocommit_no_heredados(self):
        for valor in (True, False):
            with self.subTest(autocommit=valor):
                conexion = sqlite3.connect(":memory:", autocommit=valor)
                self.addCleanup(conexion.close)
                if valor:
                    conexion.execute("PRAGMA foreign_keys=ON")
                    self.assertRechazo(conexion)
                else:
                    self.assertRechazo(conexion)

    def test_bases_adjuntas_rechazadas(self):
        conexion = self.base()
        conexion.execute("ATTACH DATABASE ':memory:' AS otra")
        self.addCleanup(lambda: conexion.execute("DETACH DATABASE otra"))
        self.assertRechazo(conexion)

    def test_query_only_activo_rechazado(self):
        conexion = self.base()
        conexion.execute("PRAGMA query_only=ON")
        self.addCleanup(lambda: conexion.execute("PRAGMA query_only=OFF"))
        self.assertRechazo(conexion)

    def test_conexion_cerrada(self):
        conexion = self.base()
        conexion.close()
        self.assertRechazo(conexion, apta=False)

    def test_argumentos_invalidos(self):
        with self.assertRaises(TypeError):
            ejecutar(object(), lambda c: None)
        with self.assertRaises(TypeError):
            ejecutar(self.base(), None)
        with self.assertRaises(TypeError):
            ejecutar(self.base(), lambda c: None, antes_de_operar=3)


class FallosDelProcesoTest(_Aislada):
    def test_la_desactivacion_ineficaz_se_detecta_y_se_restaura(self):
        conexion = self.base()
        conexion.fallos["PRAGMA foreign_keys=OFF"] = (1, "omitir")
        llamada = []
        with self.assertRaises(ErrorAntesDeConfirmar) as contexto:
            ejecutar(conexion, lambda c: llamada.append(1))
        self.assertEqual(contexto.exception.fase, "desactivar_claves_foraneas")
        self.assertEqual(llamada, [])
        self.assertRestaurada(conexion)

    def test_fallo_al_adquirir_la_reserva_de_escritura(self):
        for modo in MODOS:
            with self.subTest(modo=modo):
                conexion = self.base(modo=modo)
                otra = self.otra(timeout=0.05)
                otra.execute("BEGIN IMMEDIATE")
                llamada = []
                with self.assertRaises(ErrorAntesDeConfirmar) as contexto:
                    ejecutar(conexion, lambda c: llamada.append(1))
                self.assertEqual(contexto.exception.fase, "reserva_de_escritura")
                self.assertIsInstance(contexto.exception.__cause__, sqlite3.OperationalError)
                self.assertTrue(contexto.exception.conexion_apta)
                self.assertEqual(llamada, [])
                self.assertRestaurada(conexion)
                otra.rollback()
                ejecutar(conexion, _agregar)

    def test_fallo_en_la_revalidacion_bajo_la_reserva(self):
        conexion = self.base()
        conexion.fallos["PRAGMA foreign_key_check"] = (2, sqlite3.DatabaseError("simulado"))
        llamada = []
        with self.assertRaises(ErrorAntesDeConfirmar) as contexto:
            ejecutar(conexion, lambda c: llamada.append(1))
        self.assertEqual(contexto.exception.fase, "revalidacion_bajo_reserva")
        self.assertEqual(llamada, [])
        self.assertRestaurada(conexion)

    def test_fallo_durante_las_validaciones_finales(self):
        for pragma in ("PRAGMA foreign_key_check", "PRAGMA quick_check"):
            with self.subTest(pragma=pragma):
                conexion = self.base()
                antes = self.datos(conexion)
                conexion.fallos[pragma] = (3, sqlite3.DatabaseError("simulado"))
                with self.assertRaises(ErrorAntesDeConfirmar) as contexto:
                    ejecutar(conexion, _agregar)
                self.assertEqual(contexto.exception.fase, "validacion_final")
                self.assertEqual(self.datos(conexion), antes)
                self.assertRestaurada(conexion)

    def test_fallo_del_commit_con_transaccion_aun_abierta_se_revierte(self):
        conexion = self.base()
        antes = self.datos(conexion)
        conexion.fallos["commit"] = (1, sqlite3.OperationalError("simulado"))
        with self.assertRaises(ErrorAntesDeConfirmar) as contexto:
            ejecutar(conexion, _agregar)
        self.assertEqual(contexto.exception.fase, "commit")
        self.assertIs(contexto.exception.confirmada, False)
        self.assertTrue(contexto.exception.conexion_apta)
        self.assertEqual(self.datos(conexion), antes)
        self.assertRestaurada(conexion)

    def test_fallo_del_commit_con_estado_incierto_no_afirma_la_reversion(self):
        conexion = self.base()
        conexion.fallos["commit"] = (1, "confirmar_y_fallar")
        with self.assertRaises(ErrorEstadoIncierto) as contexto:
            ejecutar(conexion, _agregar)
        error = contexto.exception
        self.assertIsNone(error.confirmada)
        self.assertFalse(error.conexion_apta)
        self.assertNotIn("revert", str(error).casefold())
        self.assertEqual(len(self.datos(conexion)["padre"]), 3)  # sí se había confirmado
        self.assertRestaurada(conexion)

    def test_fallo_al_restaurar_tras_confirmar_no_dice_que_se_revirtio(self):
        for accion in (sqlite3.OperationalError("simulado"), "omitir"):
            with self.subTest(accion=accion):
                conexion = self.base()
                conexion.fallos["PRAGMA foreign_keys=ON"] = (1, accion)
                with self.assertRaises(ErrorDespuesDeConfirmar) as contexto:
                    ejecutar(conexion, _agregar)
                error = contexto.exception
                self.assertIs(error.confirmada, True)
                self.assertFalse(error.conexion_apta)
                self.assertIn("CONFIRMADOS", str(error))
                self.assertIsNotNone(error.__cause__)
                self.assertEqual(len(self.datos(conexion)["padre"]), 3)
                self.assertEqual(conexion.execute("PRAGMA foreign_keys").fetchone()[0], 0)

    def test_fallo_al_restaurar_tras_un_error_previo_conserva_ambos_errores(self):
        conexion = self.base()
        antes = self.datos(conexion)
        conexion.fallos["PRAGMA foreign_keys=ON"] = (1, sqlite3.OperationalError("simulado"))

        def operacion(c):
            _agregar(c)
            raise ValueError("original")

        with self.assertRaises(ErrorAntesDeConfirmar) as contexto:
            ejecutar(conexion, operacion)
        error = contexto.exception
        self.assertIsInstance(error.__cause__, ValueError)
        self.assertFalse(error.conexion_apta)
        self.assertTrue(any("foreign_keys=ON" in n for n in error.__notes__))
        self.assertEqual(self.datos(conexion), antes)

    def test_fallo_del_rollback_se_informa_y_marca_la_conexion_no_apta(self):
        conexion = self.base()
        conexion.fallos["rollback"] = (1, sqlite3.OperationalError("simulado"))

        def operacion(c):
            raise ValueError("original")

        with self.assertRaises(ErrorAntesDeConfirmar) as contexto:
            ejecutar(conexion, operacion)
        error = contexto.exception
        self.assertFalse(error.conexion_apta)
        self.assertTrue(any("revertir" in n for n in error.__notes__))
        self.assertTrue(conexion.in_transaction)
        conexion.fallos.clear()
        conexion.rollback()

    def test_la_operacion_que_cierra_la_conexion_real_se_informa_incierta(self):
        conexion = self.base(modo="DELETE")
        error = None
        try:
            ejecutar(conexion, lambda _c: (_agregar(_c), conexion.close()))
        except ErrorControlClavesForaneas as capturado:
            error = capturado
        self.assertIsInstance(error, ErrorEstadoIncierto)
        self.assertIsNone(error.confirmada)
        self.assertFalse(error.conexion_apta)
        self.assertIn(error.fase, ("operacion", "verificar_transaccion"))
        verificacion = self.otra()
        self.assertEqual(verificacion.execute("SELECT COUNT(*) FROM padre").fetchone()[0], 2)


class PropiedadDeLaTransaccionTest(_Aislada):
    INTENTOS = {
        "execute_commit": lambda c: c.execute("COMMIT"),
        "execute_end": lambda c: c.execute("END"),
        "execute_rollback": lambda c: c.execute("ROLLBACK"),
        "begin": lambda c: c.execute("BEGIN"),
        "begin_immediate": lambda c: c.execute("BEGIN IMMEDIATE"),
        "cursor_execute_commit": lambda c: c.cursor().execute("COMMIT"),
    }

    def test_ningun_intento_de_confirmar_o_revertir_termina_la_transaccion(self):
        for nombre, intento in self.INTENTOS.items():
            with self.subTest(intento=nombre):
                conexion = self.base()
                antes = self.datos(conexion)

                def operacion(c):
                    _agregar(c)
                    intento(c)

                with self.assertRaises(ErrorAntesDeConfirmar) as contexto:
                    ejecutar(conexion, operacion)
                self.assertIsInstance(contexto.exception.__cause__, sqlite3.DatabaseError)
                self.assertEqual(self.datos(conexion), antes)
                self.assertRestaurada(conexion)

    def test_un_commit_anticipado_capturado_no_publica_nada_antes_de_tiempo(self):
        for modo in MODOS:
            with self.subTest(modo=modo):
                conexion = self.base(modo=modo)
                lector = self.otra()
                visto = {}

                def operacion(c):
                    _agregar(c)
                    try:
                        c.execute("COMMIT")
                    except sqlite3.DatabaseError:
                        visto["denegado"] = True
                    if modo == "WAL":
                        visto["lector"] = lector.execute("SELECT COUNT(*) FROM padre").fetchone()[0]
                    visto["en_transaccion"] = conexion.in_transaction

                ejecutar(conexion, operacion)
                self.assertEqual(visto["denegado"], True)
                self.assertTrue(visto["en_transaccion"])
                if modo == "WAL":
                    self.assertEqual(visto["lector"], 2)
                self.assertEqual(lector.execute("SELECT COUNT(*) FROM padre").fetchone()[0], 3)

    def test_savepoints_internos_estan_permitidos(self):
        conexion = self.base()

        def operacion(c):
            c.execute("SAVEPOINT interno")
            c.execute("INSERT INTO padre(nombre) VALUES ('descartado')")
            c.execute("ROLLBACK TO interno")
            c.execute("RELEASE interno")
            _agregar(c)

        ejecutar(conexion, operacion)
        self.assertEqual([f[1] for f in self.datos(conexion)["padre"]], ["p1", "p2", "p3"])

    def test_pragmas_y_attach_protegidos(self):
        sentencias = (
            "PRAGMA foreign_keys=ON", "PRAGMA journal_mode=WAL", "PRAGMA user_version=7",
            "PRAGMA application_id=7", "PRAGMA writable_schema=ON", "PRAGMA query_only=ON", "ATTACH DATABASE ':memory:' AS otra",
        )
        for sql in sentencias:
            with self.subTest(sql=sql):
                conexion = self.base()
                with self.assertRaises(ErrorAntesDeConfirmar) as contexto:
                    ejecutar(conexion, lambda c: c.execute(sql))
                self.assertIsInstance(contexto.exception.__cause__, sqlite3.DatabaseError)
                self.assertEqual(conexion.execute("PRAGMA user_version").fetchone()[0], 0)
                self.assertEqual(conexion.execute("PRAGMA application_id").fetchone()[0], 0)

    def test_las_lecturas_de_pragmas_estan_permitidas(self):
        conexion = self.base()
        ejecutar(conexion, lambda c: [c.execute(f"PRAGMA {p}").fetchall() for p in (
            "foreign_keys", "user_version", "table_info(padre)", "foreign_key_list(hija)")])

    def test_el_autorizador_se_retira_tambien_tras_un_error(self):
        conexion = self.base()
        with self.assertRaises(ErrorAntesDeConfirmar):
            ejecutar(conexion, lambda c: 1 / 0)
        conexion.execute("BEGIN")
        conexion.commit()


class ModosDeJournalYConcurrenciaTest(_Aislada):
    def test_exito_y_rollback_en_delete_y_wal_sin_cambiar_el_modo(self):
        for modo in MODOS:
            with self.subTest(modo=modo):
                conexion = self.base(modo=modo)
                ejecutar(conexion, _agregar)
                self.assertEqual(conexion.execute("PRAGMA journal_mode").fetchone()[0].upper(), modo)
                self.assertEqual(self.otra().execute("SELECT COUNT(*) FROM hija").fetchone()[0], 3)
                antes = self.datos(conexion)
                with self.assertRaises(ErrorAntesDeConfirmar):
                    ejecutar(conexion, lambda c: (c.execute("DELETE FROM hija"), 1 / 0))
                self.assertEqual(self.datos(conexion), antes)
                self.assertEqual(conexion.execute("PRAGMA journal_mode").fetchone()[0].upper(), modo)
                self.assertRestaurada(conexion)

    def test_un_segundo_escritor_queda_bloqueado_durante_la_transaccion(self):
        for modo in MODOS:
            with self.subTest(modo=modo):
                conexion = self.base(modo=modo)
                escritor = self.otra(timeout=0.05)
                resultados = {}

                def operacion(c):
                    _agregar(c)
                    for clave, sql in (
                        ("begin", "BEGIN IMMEDIATE"),
                        ("insert", "INSERT INTO padre(nombre) VALUES ('intruso')"),
                    ):
                        try:
                            escritor.execute(sql)
                            resultados[clave] = "permitido"
                        except sqlite3.OperationalError as error:
                            resultados[clave] = str(error)
                    escritor.rollback()

                ejecutar(conexion, operacion)
                self.assertEqual(resultados, {"begin": "database is locked", "insert": "database is locked"})
                escritor.execute("INSERT INTO padre(nombre) VALUES ('posterior')")
                escritor.commit()
                self.assertEqual(conexion.execute("SELECT COUNT(*) FROM padre").fetchone()[0], 4)

    def test_el_segundo_escritor_no_ve_cambios_parciales_tras_un_rollback(self):
        for modo in MODOS:
            with self.subTest(modo=modo):
                conexion = self.base(modo=modo)
                lector = self.otra()
                with self.assertRaises(ErrorAntesDeConfirmar):
                    ejecutar(conexion, lambda c: (_agregar(c), 1 / 0))
                self.assertEqual(lector.execute("SELECT COUNT(*) FROM padre").fetchone()[0], 2)


class GanchoParaBackupFuturoTest(_Aislada):
    def test_el_gancho_corre_bajo_la_reserva_y_antes_de_cualquier_modificacion(self):
        for modo in MODOS:
            with self.subTest(modo=modo):
                conexion = self.base(modo=modo)
                orden = []
                directorio = tempfile.TemporaryDirectory()
                self.addCleanup(directorio.cleanup)
                copia = str(Path(directorio.name) / "copia.db")

                def gancho():
                    orden.append("gancho")
                    self.assertTrue(conexion.in_transaction)
                    origen = self.otra(timeout=0.05)
                    destino = sqlite3.connect(copia)
                    try:
                        origen.backup(destino)
                        orden.append(destino.execute("PRAGMA quick_check").fetchone()[0])
                        orden.append(destino.execute("SELECT COUNT(*) FROM padre").fetchone()[0])
                    finally:
                        destino.close()

                def operacion(c):
                    orden.append("operacion")
                    _agregar(c)

                ejecutar(conexion, operacion, antes_de_operar=gancho)
                self.assertEqual(orden, ["gancho", "ok", 2, "operacion"])
                self.assertEqual(conexion.execute("SELECT COUNT(*) FROM padre").fetchone()[0], 3)

    def test_un_gancho_fallido_impide_la_operacion_y_revierte(self):
        conexion = self.base()
        llamada = []

        def gancho():
            raise OSError("backup simulado fallido")

        with self.assertRaises(ErrorAntesDeConfirmar) as contexto:
            ejecutar(conexion, lambda c: llamada.append(1), antes_de_operar=gancho)
        self.assertEqual(contexto.exception.fase, "antes_de_operar")
        self.assertEqual(llamada, [])
        self.assertRestaurada(conexion)

    def test_el_gancho_tampoco_puede_confirmar(self):
        conexion = self.base()
        with self.assertRaises(ErrorAntesDeConfirmar):
            ejecutar(conexion, lambda c: None, antes_de_operar=lambda: conexion.commit())


def _historica_con_datos(nombre):
    conexion = sqlite3.connect(":memory:")
    for _, _, _, sql in ESQUEMAS_HISTORICOS[nombre][2]:
        conexion.execute(sql)
    conexion.execute("INSERT INTO clientes(id, razon_social) VALUES (1, 'Ficticio SA')")
    conexion.execute("INSERT INTO servicios(id, cliente_id, concepto, importe) VALUES (1, 1, 'X', 10)")
    conexion.execute(
        "INSERT INTO resumenes(id, numero, cliente_id, fecha, fecha_vencimiento) VALUES (1, 1, 1, '2024-01-01', '2024-01-10')"
    )
    conexion.execute("INSERT INTO resumen_conceptos(resumen_id, servicio_id, concepto) VALUES (1, 1, 'X')")
    conexion.commit()
    return conexion


class CompatibilidadConCrearBaseTest(_Aislada):
    NOMBRES = ("build_0_7_8c81526", "build_1_7_4994dc6")

    def _datos(self, conexion):
        return {
            t: conexion.execute(f"SELECT * FROM {t} ORDER BY id").fetchall()
            for t in ("clientes", "servicios", "resumenes", "resumen_conceptos")
        }

    def test_crear_base_con_conexion_externa_funciona_bajo_el_mecanismo(self):
        from services.sqlite_huella_estructural import calcular_huella_estructural_sqlite as huella

        for nombre in self.NOMBRES:
            with self.subTest(nombre=nombre):
                referencia = _historica_con_datos(nombre)
                self.addCleanup(referencia.close)
                referencia.execute("BEGIN IMMEDIATE")
                database.crear_base(conexion=referencia)
                referencia.commit()

                conexion = _historica_con_datos(nombre)
                self.addCleanup(conexion.close)
                conexion.execute("PRAGMA foreign_keys=ON")
                resultado = ejecutar(conexion, lambda _i: database.crear_base(conexion=conexion))
                self.assertTrue(resultado.confirmada)
                self.assertEqual(huella(conexion).huella, huella(referencia).huella)
                self.assertEqual(self._datos(conexion), self._datos(referencia))
                self.assertRestaurada(conexion)

    def test_un_fallo_de_crear_base_revierte_toda_la_migracion(self):
        conexion = _historica_con_datos("build_1_7_4994dc6")
        self.addCleanup(conexion.close)
        conexion.execute("PRAGMA foreign_keys=ON")
        antes = conexion.execute("SELECT name, sql FROM sqlite_master ORDER BY name").fetchall()
        with patch.object(database, "migrar_emisor_fiscal_arca_config", side_effect=RuntimeError("simulado")):
            with self.assertRaises(ErrorAntesDeConfirmar) as contexto:
                ejecutar(conexion, lambda _i: database.crear_base(conexion=conexion))
        self.assertIsInstance(contexto.exception.__cause__, RuntimeError)
        self.assertEqual(conexion.execute("SELECT name, sql FROM sqlite_master ORDER BY name").fetchall(), antes)
        self.assertRestaurada(conexion)

    def test_el_contrato_de_crear_base_se_satisface_sin_autocommit_y_con_transaccion_activa(self):
        conexion = self.base()
        vistos = {}

        def operacion(_i):
            vistos["in_transaction"] = conexion.in_transaction
            vistos["autocommit"] = conexion.autocommit

        ejecutar(conexion, operacion)
        self.assertEqual(vistos, {"in_transaction": True, "autocommit": sqlite3.LEGACY_TRANSACTION_CONTROL})

    def test_incompatibilidad_documentada_crear_base_rechaza_la_interfaz_restringida(self):
        conexion = _historica_con_datos("build_1_7_4994dc6")
        self.addCleanup(conexion.close)
        conexion.execute("PRAGMA foreign_keys=ON")
        antes = conexion.execute("SELECT name, sql FROM sqlite_master ORDER BY name").fetchall()
        with self.assertRaises(ErrorAntesDeConfirmar) as contexto:
            ejecutar(conexion, lambda interfaz: database.crear_base(conexion=interfaz))
        self.assertIs(contexto.exception.confirmada, False)
        self.assertEqual(conexion.execute("SELECT name, sql FROM sqlite_master ORDER BY name").fetchall(), antes)
        self.assertRestaurada(conexion)


class AislamientoDelModuloTest(_Aislada):
    def test_el_modulo_no_conoce_rutas_database_ni_backup_ni_marcadores(self):
        fuente = Path(modulo.__file__).read_text(encoding="utf-8")
        codigo = re.sub(r'"""[\s\S]*?"""', "", fuente)
        for patron in (r"runtime_paths", r"import database|from database", r"backup_service", r"sqlite3\.connect",
                       r"DATABASE_PATH", r"application_id\s*=", r"user_version\s*="):
            with self.subTest(patron=patron):
                self.assertIsNone(re.search(patron, codigo), patron)

    def test_conectar_esta_bloqueado(self):
        with self.assertRaises(AssertionError):
            database.conectar()

    def test_las_excepciones_comparten_una_base_comun(self):
        for clase in (ErrorAntesDeConfirmar, ErrorDespuesDeConfirmar, ErrorEstadoIncierto):
            self.assertTrue(issubclass(clase, ErrorControlClavesForaneas))


class RevisionComplementariaTest(_Aislada):
    """Regresión de los cinco defectos de la revisión previa al commit.

    Dos grupos: (1) lo que la operación puede hacer con la interfaz restringida, y
    (2) lo que ocurre si código con acceso a la conexión REAL (capturada por clausura, algo que la
    interfaz no puede impedir) intenta eludir el control: el mecanismo no puede impedirlo,
    pero debe informar ``confirmada=None`` y no apta, nunca un valor de persistencia
    falso. Todo se verifica desde una segunda conexión independiente.
    """

    def ids(self):
        return [f[0] for f in self.otra().execute("SELECT id FROM padre ORDER BY id")]

    def ejecutar_y_capturar(self, conexion, operacion, **kwargs):
        try:
            ejecutar(conexion, operacion, **kwargs)
        except ErrorControlClavesForaneas as error:
            return error
        return None

    @staticmethod
    def padre(conexion, identificador=5):
        conexion.execute("INSERT INTO padre(id, nombre) VALUES (?, 'x')", (identificador,))

    @staticmethod
    def hija_huerfana(conexion):
        conexion.execute("INSERT INTO hija(padre_id, valor) VALUES (999, 'huerfana')")

    # --- Pruebas de contención: lo que SÍ está impedido ---------------------------------

    def test_commit_denegado_y_capturado_no_confirma_antes_de_tiempo(self):
        conexion = self.base(modo="DELETE")
        visto = {}

        def operacion(c):
            self.padre(c)
            for sql in ("COMMIT", "END", "ROLLBACK", "BEGIN", "BEGIN IMMEDIATE"):
                try:
                    c.execute(sql)
                    visto[sql] = "permitido"
                except sqlite3.DatabaseError:
                    pass
            visto["otra_conexion"] = self.ids()
            self.padre(c, 6)

        ejecutar(conexion, operacion)
        self.assertNotIn("COMMIT", visto)
        self.assertEqual({k for k in visto if k != "otra_conexion"}, set())
        self.assertEqual(visto["otra_conexion"], [1, 2])
        self.assertEqual(self.ids(), [1, 2, 5, 6])

    def test_commit_denegado_capturado_y_fallo_final_revierte_todo(self):
        conexion = self.base(modo="DELETE")

        def operacion(c):
            self.padre(c)
            try:
                c.execute("COMMIT")
            except sqlite3.DatabaseError:
                pass
            self.hija_huerfana(c)

        error = self.ejecutar_y_capturar(conexion, operacion)
        self.assertIsInstance(error, ErrorAntesDeConfirmar)
        self.assertIs(error.confirmada, False)
        self.assertEqual(self.ids(), [1, 2])

    def test_la_interfaz_no_permite_cambiar_autocommit_isolation_level_ni_ejecutar_scripts(self):
        intentos = {
            "autocommit": lambda c: setattr(c, "autocommit", True),
            "isolation_level": lambda c: setattr(c, "isolation_level", None),
            "executescript": lambda c: c.executescript("COMMIT;"),
            "set_authorizer": lambda c: c.set_authorizer(None),
            "commit": lambda c: c.commit(),
            "rollback": lambda c: c.rollback(),
            "close": lambda c: c.close(),
            "connection": lambda c: c.connection,
            "in_transaction": lambda c: c.in_transaction,
            "enable_load_extension": lambda c: c.enable_load_extension(True),
            "backup": lambda c: c.backup(None),
        }
        for nombre, intento in intentos.items():
            with self.subTest(nombre):
                conexion = self.base(modo="DELETE")
                capturado = []

                def operacion(c, intento=intento):
                    self.padre(c)
                    try:
                        intento(c)
                    except AttributeError as error:
                        capturado.append(type(error).__name__)

                ejecutar(conexion, operacion)
                self.assertEqual(capturado, ["AttributeError"])
                self.assertEqual(self.ids(), [1, 2, 5])
                self.assertEqual(conexion.isolation_level, "")
                self.assertEqual(conexion.autocommit, sqlite3.LEGACY_TRANSACTION_CONTROL)

    def test_los_cursores_no_permiten_recuperar_la_conexion_real(self):
        conexion = self.base(modo="DELETE")
        resultados = {}

        def operacion(c):
            for nombre, cursor in (("execute", c.execute("SELECT 1")), ("cursor", c.cursor()),
                                   ("executemany", c.executemany("INSERT INTO padre(id, nombre) VALUES (?, 'x')", [(5,), (6,)])),
                                   ("encadenado", c.cursor().execute("SELECT 1"))):
                resultados[nombre] = [hasattr(cursor, atributo) for atributo in ("connection", "_cursor_real", "commit")]
                with self.assertRaises(AttributeError):
                    cursor.connection.commit()
            resultados["lectura"] = c.execute("SELECT COUNT(*) FROM padre").fetchone()[0]

        ejecutar(conexion, operacion)
        for valor in resultados.values():
            if isinstance(valor, list):
                self.assertEqual(valor, [False, False, False])
        self.assertEqual(resultados["lectura"], 4)
        self.assertEqual(self.ids(), [1, 2, 5, 6])

    def test_la_interfaz_y_sus_cursores_dejan_de_funcionar_al_terminar(self):
        conexion = self.base(modo="DELETE")
        guardados = {}

        def operacion(c):
            guardados["interfaz"] = c
            guardados["cursor"] = c.cursor()

        ejecutar(conexion, operacion)
        with self.assertRaises(sqlite3.ProgrammingError):
            guardados["interfaz"].execute("DELETE FROM padre")
        with self.assertRaises(sqlite3.ProgrammingError):
            guardados["cursor"].execute("DELETE FROM padre")
        self.assertEqual(self.ids(), [1, 2])

    def test_los_savepoints_reservados_del_mecanismo_estan_denegados(self):
        for sql in ("SAVEPOINT _fm_ctl_x", "RELEASE _fm_ctl_x", "ROLLBACK TO _FM_CTL_x"):
            with self.subTest(sql):
                conexion = self.base(modo="DELETE")
                with self.assertRaises(ErrorAntesDeConfirmar) as contexto:
                    ejecutar(conexion, lambda c: (self.padre(c), c.execute(sql)))
                self.assertIsInstance(contexto.exception.__cause__, sqlite3.DatabaseError)
                self.assertEqual(self.ids(), [1, 2])

    def test_or_rollback_y_raise_rollback_terminan_la_transaccion_y_se_informa_incierto(self):
        accion_conflicto = lambda c: c.execute("INSERT OR ROLLBACK INTO padre(id, nombre) VALUES (1, 'dup')")
        accion_trigger = lambda c: (
            c.execute("CREATE TRIGGER t BEFORE INSERT ON padre WHEN NEW.id = 50 BEGIN SELECT RAISE(ROLLBACK, 'x'); END"),
            c.execute("INSERT INTO padre(id, nombre) VALUES (50, 'z')"),
        )
        for nombre, accion in (("or_rollback", accion_conflicto), ("raise_rollback", accion_trigger)):
            with self.subTest(nombre):
                conexion = self.base(modo="DELETE")

                def operacion(c, accion=accion):
                    self.padre(c)
                    try:
                        accion(c)
                    except sqlite3.DatabaseError:
                        pass

                error = self.ejecutar_y_capturar(conexion, operacion)
                self.assertIsInstance(error, ErrorEstadoIncierto)
                self.assertIsNone(error.confirmada)
                self.assertFalse(error.conexion_apta)
                self.assertEqual(self.ids(), [1, 2])

    def test_tras_or_rollback_el_inicio_implicito_de_transaccion_esta_denegado(self):
        conexion = self.base(modo="DELETE")
        resultados = {}

        def operacion(c):
            self.padre(c)
            try:
                c.execute("INSERT OR ROLLBACK INTO padre(id, nombre) VALUES (1, 'dup')")
            except sqlite3.DatabaseError:
                pass
            try:
                self.padre(c, 6)
                resultados["continuo"] = True
            except sqlite3.DatabaseError:
                resultados["continuo"] = False

        error = self.ejecutar_y_capturar(conexion, operacion)
        self.assertFalse(resultados["continuo"])
        self.assertIsInstance(error, ErrorEstadoIncierto)
        self.assertEqual(self.ids(), [1, 2])

    def test_attach_y_detach_estan_denegados_aunque_se_capture_el_error(self):
        conexion = self.base(modo="DELETE")
        capturado = {}

        def operacion(c):
            self.padre(c)
            try:
                c.execute("ATTACH DATABASE ':memory:' AS otra")
            except sqlite3.DatabaseError as error:
                capturado["error"] = str(error)
            self.assertNotIn("otra", [f[1] for f in c.execute("PRAGMA database_list")])

        ejecutar(conexion, operacion)
        self.assertEqual(capturado["error"], "not authorized")

    def test_vacuum_into_no_puede_ejecutarse_dentro_de_la_transaccion(self):
        conexion = self.base(modo="DELETE")
        error = self.ejecutar_y_capturar(conexion, lambda c: c.execute("VACUUM INTO ':memory:'"))
        self.assertIsInstance(error, ErrorAntesDeConfirmar)
        self.assertEqual(self.ids(), [1, 2])

    # --- Código con acceso a la conexión REAL (clausura): no se puede impedir, sí informar bien ---

    def real(self, conexion, operacion):
        """Operación que usa la conexión real capturada, no la interfaz restringida."""
        return lambda _interfaz: operacion(conexion)

    def test_retirar_el_autorizador_y_confirmar_con_la_conexion_real_se_informa_incierto(self):
        conexion = self.base(modo="DELETE")
        error = self.ejecutar_y_capturar(
            conexion, self.real(conexion, lambda c: (self.padre(c), c.set_authorizer(None), c.commit()))
        )
        self.assertIsInstance(error, ErrorEstadoIncierto)
        self.assertIsNone(error.confirmada)
        self.assertFalse(error.conexion_apta)
        self.assertEqual(self.ids(), [1, 2, 5])  # persistió: confirmada=None es la única respuesta honesta

    def test_reemplazar_el_autorizador_por_uno_permisivo_y_confirmar_se_informa_incierto(self):
        conexion = self.base(modo="DELETE")
        error = self.ejecutar_y_capturar(
            conexion,
            self.real(
                conexion,
                lambda c: (self.padre(c), c.set_authorizer(lambda *a: sqlite3.SQLITE_OK), c.commit()),
            ),
        )
        self.assertIsInstance(error, ErrorEstadoIncierto)
        self.assertIsNone(error.confirmada)
        self.assertEqual(self.ids(), [1, 2, 5])

    def test_el_autorizador_previo_se_reemplaza_y_se_elimina(self):
        conexion = self.base(modo="DELETE")
        llamadas = []
        conexion.set_authorizer(lambda accion, *resto: (llamadas.append(accion), sqlite3.SQLITE_OK)[1])
        ejecutar(conexion, self.padre)
        antes = len(llamadas)
        conexion.execute("SELECT 1 FROM padre").fetchall()
        self.assertEqual(len(llamadas), antes)  # el autorizador previo ya no se consulta

    def test_un_autorizador_previo_restrictivo_queda_eludido(self):
        conexion = self.base(modo="DELETE")
        conexion.set_authorizer(lambda accion, *r: sqlite3.SQLITE_DENY if accion == sqlite3.SQLITE_INSERT else sqlite3.SQLITE_OK)
        ejecutar(conexion, self.padre)
        self.assertEqual(self.ids(), [1, 2, 5])

    # --- Los cinco defectos confirmados (antes expectedFailure) ----------------------------

    def test_defecto_1_commit_anticipado_con_nueva_transaccion_se_informa_incierto(self):
        for modo in MODOS:
            with self.subTest(modo):
                conexion = self.base(modo=modo)

                def operacion(c):
                    self.padre(c)
                    c.set_authorizer(None)
                    c.commit()
                    c.execute("BEGIN")
                    self.hija_huerfana(c)

                error = self.ejecutar_y_capturar(conexion, self.real(conexion, operacion))
                self.assertEqual(self.ids(), [1, 2, 5])  # persistió el cambio anticipado
                self.assertIsInstance(error, ErrorEstadoIncierto)
                self.assertIsNone(error.confirmada)
                self.assertFalse(error.conexion_apta)

    def test_defecto_1b_commit_anticipado_y_nueva_transaccion_exitosa_tampoco_se_confirma_como_prevista(self):
        conexion = self.base(modo="DELETE")

        def operacion(c):
            self.padre(c)
            c.set_authorizer(None)
            c.commit()
            c.execute("BEGIN")
            self.padre(c, 6)

        error = self.ejecutar_y_capturar(conexion, self.real(conexion, operacion))
        self.assertIsInstance(error, ErrorEstadoIncierto)
        self.assertEqual(self.ids(), [1, 2, 5])  # 5 quedó persistido; 6 se revirtió
        self.assertFalse(conexion.in_transaction)

    def test_defecto_2_commit_anticipado_y_cierre_de_la_conexion_se_informa_incierto(self):
        conexion = self.base(modo="DELETE")

        def operacion(c):
            self.padre(c)
            c.set_authorizer(None)
            c.commit()
            c.close()

        error = self.ejecutar_y_capturar(conexion, self.real(conexion, operacion))
        self.assertEqual(self.ids(), [1, 2, 5])
        self.assertIsInstance(error, ErrorEstadoIncierto)
        self.assertIsNone(error.confirmada)
        self.assertFalse(error.conexion_apta)

    def test_defecto_3_escritura_en_otra_base_adjuntada_sin_autorizador_se_informa_incierto(self):
        conexion = self.base(modo="DELETE")
        directorio = tempfile.TemporaryDirectory()
        self.addCleanup(directorio.cleanup)
        ruta_otra = str(Path(directorio.name) / "otra_ficticia.db")
        preparada = sqlite3.connect(ruta_otra)
        preparada.execute("CREATE TABLE t(a)")
        preparada.commit()
        preparada.close()

        def operacion(c):
            c.set_authorizer(None)
            c.commit()
            c.execute("ATTACH DATABASE ? AS otra", (ruta_otra,))
            self.addCleanup(lambda: conexion.execute("DETACH DATABASE otra"))
            c.execute("INSERT INTO otra.t VALUES (1)")
            c.commit()
            c.execute("BEGIN")
            self.hija_huerfana(c)

        error = self.ejecutar_y_capturar(conexion, self.real(conexion, operacion))
        verificacion = sqlite3.connect(ruta_otra)
        try:
            self.assertEqual(verificacion.execute("SELECT COUNT(*) FROM t").fetchone()[0], 1)
        finally:
            verificacion.close()
        self.assertIsInstance(error, ErrorEstadoIncierto)
        self.assertIsNone(error.confirmada)
        self.assertFalse(error.conexion_apta)

    def test_defecto_4_autocommit_true_no_se_informa_como_confirmado_ni_como_revertido(self):
        conexion = self.base(modo="DELETE")

        def operacion(c):
            self.padre(c)
            try:
                c.autocommit = True  # el setter falla (denegado) pero deja el atributo modificado
            except sqlite3.DatabaseError:
                pass

        error = self.ejecutar_y_capturar(conexion, self.real(conexion, operacion))
        self.assertEqual(self.ids(), [1, 2])  # nada persistió
        self.assertIsInstance(error, ErrorEstadoIncierto)
        self.assertIsNone(error.confirmada)
        self.assertFalse(error.conexion_apta)

    def test_defecto_4b_autocommit_false_y_aislamiento_alterado_no_confirman_ni_se_informan_como_revertidos(self):
        for nombre, accion in (
            ("autocommit_false", lambda c: setattr(c, "autocommit", False)),
            ("isolation_level", lambda c: setattr(c, "isolation_level", "EXCLUSIVE")),
        ):
            with self.subTest(nombre):
                conexion = self.base(modo="DELETE")
                error = self.ejecutar_y_capturar(conexion, self.real(conexion, lambda c: (self.padre(c), accion(c))))
                self.assertEqual(self.ids(), [1, 2])
                self.assertIsInstance(error, ErrorEstadoIncierto)
                self.assertIsNone(error.confirmada)
                self.assertFalse(error.conexion_apta)

    def test_defecto_5_el_gancho_previo_no_recibe_conexion_y_sus_escrituras_quedan_bloqueadas(self):
        escrituras = {
            "insert": lambda c: c.execute("INSERT INTO padre(id, nombre) VALUES (77, 'h')"),
            "update": lambda c: c.execute("UPDATE padre SET nombre = 'h'"),
            "delete": lambda c: c.execute("DELETE FROM hija"),
            "ddl": lambda c: c.execute("CREATE TABLE z(a)"),
            "alter": lambda c: c.execute("ALTER TABLE padre ADD COLUMN q"),
            "pragma": lambda c: c.execute("PRAGMA user_version=9"),
            "commit": lambda c: c.commit(),
            "rollback": lambda c: c.rollback(),
            "begin": lambda c: c.execute("BEGIN"),
        }
        for nombre, escritura in escrituras.items():
            for modo in MODOS:
                with self.subTest(nombre, modo=modo):
                    conexion = self.base(modo=modo)
                    llamada = []
                    error = self.ejecutar_y_capturar(
                        conexion,
                        lambda c: llamada.append(1),
                        antes_de_operar=lambda: escritura(conexion),  # el gancho captura la conexión real
                    )
                    self.assertIsInstance(error, ErrorAntesDeConfirmar)
                    self.assertEqual(error.fase, "antes_de_operar")
                    self.assertIs(error.confirmada, False)
                    self.assertTrue(error.conexion_apta)
                    self.assertEqual(llamada, [])
                    self.assertEqual(self.ids(), [1, 2])
                    self.assertEqual(
                        [f[0] for f in self.otra().execute("SELECT name FROM sqlite_master WHERE name='z'")], [])
                    self.assertEqual(conexion.execute("PRAGMA query_only").fetchone()[0], 0)
                    self.assertRestaurada(conexion)

    def test_el_gancho_no_recibe_argumentos_y_un_gancho_con_parametro_falla_antes_de_operar(self):
        conexion = self.base(modo="DELETE")
        llamada = []
        error = self.ejecutar_y_capturar(conexion, lambda c: llamada.append(1), antes_de_operar=lambda conexion_: None)
        self.assertIsInstance(error, ErrorAntesDeConfirmar)
        self.assertIsInstance(error.__cause__, TypeError)
        self.assertEqual(llamada, [])

    def test_query_only_y_el_autorizador_de_lectura_se_retiran_tras_el_gancho(self):
        conexion = self.base(modo="DELETE")
        estados = {}

        def gancho():
            with self.assertRaises(sqlite3.DatabaseError):
                conexion.execute("INSERT INTO padre(id, nombre) VALUES (78, 'h')")
            estados["gancho"] = "escritura bloqueada"

        def operacion(c):
            estados["operacion"] = c.execute("PRAGMA query_only").fetchone()[0]
            self.padre(c)

        ejecutar(conexion, operacion, antes_de_operar=gancho)
        self.assertEqual(estados, {"gancho": "escritura bloqueada", "operacion": 0})
        self.assertEqual(conexion.execute("PRAGMA query_only").fetchone()[0], 0)
        self.assertEqual(self.ids(), [1, 2, 5])

    def test_la_operacion_no_puede_activar_query_only(self):
        conexion = self.base(modo="DELETE")
        with self.assertRaises(ErrorAntesDeConfirmar) as contexto:
            ejecutar(conexion, lambda c: c.execute("PRAGMA query_only=ON"))
        self.assertIsInstance(contexto.exception.__cause__, sqlite3.DatabaseError)

    def test_un_backup_desde_otra_conexion_de_solo_lectura_bajo_la_reserva_ve_el_estado_previo(self):
        for modo in MODOS:
            with self.subTest(modo):
                conexion = self.base(modo=modo)
                vistos = {}

                def gancho():
                    origen = sqlite3.connect(f"file:{Path(self.ruta).as_posix()}?mode=ro", uri=True, timeout=0.5)
                    destino = sqlite3.connect(":memory:")
                    try:
                        origen.backup(destino)
                        vistos["filas"] = destino.execute("SELECT COUNT(*) FROM padre").fetchone()[0]
                        vistos["quick_check"] = destino.execute("PRAGMA quick_check").fetchone()[0]
                    finally:
                        destino.close()
                        origen.close()

                ejecutar(conexion, self.padre, antes_de_operar=gancho)
                self.assertEqual(vistos, {"filas": 2, "quick_check": "ok"})
                self.assertEqual(self.ids(), [1, 2, 5])

    def test_un_fallo_del_backup_impide_la_operacion_y_no_modifica_nada(self):
        for modo in MODOS:
            with self.subTest(modo):
                conexion = self.base(modo=modo)
                llamada = []

                def gancho():
                    raise OSError("backup simulado fallido")

                error = self.ejecutar_y_capturar(conexion, lambda c: llamada.append(1), antes_de_operar=gancho)
                self.assertIsInstance(error, ErrorAntesDeConfirmar)
                self.assertIs(error.confirmada, False)
                self.assertEqual(error.fase, "antes_de_operar")
                self.assertIsInstance(error.__cause__, OSError)
                self.assertEqual(llamada, [])
                self.assertEqual(self.ids(), [1, 2])
                self.assertRestaurada(conexion)
                self.assertEqual(conexion.execute("PRAGMA query_only").fetchone()[0], 0)


if __name__ == "__main__":
    unittest.main()
