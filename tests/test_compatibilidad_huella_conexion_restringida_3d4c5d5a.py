"""Etapa 3D.4C.5D.5A: la huella estructural admite ConexionRestringida (solo bases ficticias).

Bases en memoria o en directorios temporales. ``database.conectar`` queda bloqueado y no se
usa ninguna ruta real. La tabla funcional ``resumenes`` no se modifica en ninguna prueba.
"""

import re
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from services import sqlite_huella_estructural as modulo
from services.sqlite_control_claves_foraneas import (
    ErrorAntesDeConfirmar,
    ejecutar_con_claves_foraneas_controladas as ejecutar,
)
from services.sqlite_huella_estructural import (
    calcular_huella_estructural_sqlite as huella,
    representacion_estructural_sqlite as representacion,
)
from tests.test_compatibilidad_esquemas_historicos_3d4c5c2 import ESQUEMAS_HISTORICOS, database

RAIZ = Path(__file__).resolve().parents[1]
ACTUAL = "650cc300b59db14e5621f922cd77a55d08739ec843729bdb61ccf6e33e4b7fa3"
COMUN_MIGRADA = "b78314c4db609c4c953d4484475e0712695c1a9e5380906b8717e038b36e8a36"
# nombre: (huella del esquema histórico sin migrar, huella tras crear_base())
HISTORICAS = {
    "build_0_2_2_9b6a850": ("36215ac6d972429268edf1f94154305363c6426b927044f02fcd66d8fb0ebf6a",
                            "cceefd20ccfddbe3fee9161e319b9ee9db7d4e1fdef3e105d055b4a588111727"),
    "build_0_5_52b0189": ("2da4b538a04ec5f4a34e72ed7d410a9957d17ae59f8c146c487da95ccee21ae6", ACTUAL),
    "build_0_7_8c81526": ("14b75710351a0b33002c824c2a3cc6df00d4bdae1f6481164117d127b74f03ff", COMUN_MIGRADA),
    "build_1_7_4994dc6": ("33a9eb55f6d073fd7cc688dda060120f364cb808bedb83bdb9f951975b1f9e5a", COMUN_MIGRADA),
    "esenciales_16_8a362a5": ("daf648cd849f1e7253e4e3db39742777ac3248bd07fcc549285e7ce3017dd4c3", ACTUAL),
    "arca_intentos_af3e31e": ("76f87d6e70ae6f8118d90fe1a3f54690796d78c3a2da9b07de7cf1df6eb1e28a", ACTUAL),
    "arca_indices_unicos_0fe8ac7": ("a2bc920a817f817f2925f0d9b79f042fd717a6456e6b5508da522fdf81be0b73", ACTUAL),
    "arca_config_ambiente_599d0f5": (ACTUAL, ACTUAL),
}
ESQUEMA = (
    "CREATE TABLE aux_padre(id INTEGER PRIMARY KEY AUTOINCREMENT, nombre TEXT NOT NULL)",
    "CREATE TABLE aux_hija(id INTEGER PRIMARY KEY AUTOINCREMENT, "
    "padre_id INTEGER NOT NULL REFERENCES aux_padre(id), valor TEXT)",
    "CREATE INDEX idx_aux_hija_padre ON aux_hija(padre_id)",
    "INSERT INTO aux_padre(nombre) VALUES ('p1'), ('p2')",
    "INSERT INTO aux_hija(padre_id, valor) VALUES (1, 'h1'), (2, NULL)",
)
MODOS = ("DELETE", "WAL")


class _Aislada(unittest.TestCase):
    def setUp(self):
        parche = patch.object(database, "conectar", side_effect=AssertionError("acceso a base real bloqueado"))
        parche.start()
        self.addCleanup(parche.stop)

    def memoria(self, historica=None, *, migrar=False):
        conexion = sqlite3.connect(":memory:")
        self.addCleanup(conexion.close)
        if historica:
            for _, _, _, sql in ESQUEMAS_HISTORICOS[historica][2]:
                conexion.execute(sql)
            conexion.commit()
        if migrar:
            conexion.execute("BEGIN IMMEDIATE")
            database.crear_base(conexion=conexion)
            conexion.commit()
        conexion.execute("PRAGMA foreign_keys=ON")
        return conexion

    def auxiliar(self, modo=None):
        if modo is None:
            conexion = sqlite3.connect(":memory:")
        else:
            directorio = tempfile.TemporaryDirectory()
            self.addCleanup(directorio.cleanup)
            self.ruta = str(Path(directorio.name) / "ficticia.db")
            conexion = sqlite3.connect(self.ruta, timeout=0.05)
            self.assertEqual(conexion.execute(f"PRAGMA journal_mode={modo}").fetchone()[0].upper(), modo)
        self.addCleanup(conexion.close)
        for sql in ESQUEMA:
            conexion.execute(sql)
        conexion.commit()
        conexion.execute("PRAGMA foreign_keys=ON")
        return conexion

    def independiente(self):
        conexion = sqlite3.connect(self.ruta, timeout=0.05)
        self.addCleanup(conexion.close)
        return conexion

    @staticmethod
    def dentro(conexion, funcion):
        """Ejecuta ``funcion(interfaz)`` bajo el mecanismo de control y devuelve su resultado."""
        return ejecutar(conexion, funcion).resultado


class CompatibilidadDeInterfacesTest(_Aislada):
    def test_representacion_y_huella_son_identicas_en_ambas_interfaces(self):
        conexion = self.auxiliar()
        real_rep, real_huella = representacion(conexion), huella(conexion)
        rep, resultado = self.dentro(conexion, lambda i: (representacion(i), huella(i)))
        self.assertEqual(rep, real_rep)
        self.assertEqual(resultado.huella, real_huella.huella)
        self.assertEqual(resultado.representacion, real_huella.representacion)
        self.assertTrue(resultado.confiable)
        self.assertEqual(resultado.formato, "fm-huella-estructural-v1")

    def test_huellas_historicas_conocidas_se_conservan_en_ambas_interfaces(self):
        for nombre, (sin_migrar, migrada) in HISTORICAS.items():
            for migrar, esperada in ((False, sin_migrar), (True, migrada)):
                with self.subTest(nombre=nombre, migrar=migrar):
                    conexion = self.memoria(nombre, migrar=migrar)
                    self.assertEqual(huella(conexion).huella, esperada)
                    restringida = self.dentro(conexion, lambda i: huella(i))
                    self.assertEqual(restringida.huella, esperada)
                    self.assertEqual(restringida.representacion, huella(conexion).representacion)

    def test_huella_actual_y_comun_de_los_dos_origenes_migrados(self):
        actual = self.memoria(migrar=True)
        self.assertEqual(self.dentro(actual, lambda i: huella(i)).huella, ACTUAL)
        for nombre in ("build_0_7_8c81526", "build_1_7_4994dc6"):
            with self.subTest(nombre=nombre):
                conexion = self.memoria(nombre, migrar=True)
                self.assertEqual(self.dentro(conexion, lambda i: huella(i)).huella, COMUN_MIGRADA)
        self.assertNotEqual(COMUN_MIGRADA, ACTUAL)

    def test_objetos_incompatibles_son_rechazados(self):
        conexion = self.auxiliar()

        class ConExecute:
            def execute(self, *args):
                raise AssertionError("no debe usarse")

            def cursor(self):
                raise AssertionError("no debe usarse")

        for objeto in (None, "x", 1, ConExecute(), SimpleNamespace(execute=conexion.execute, cursor=conexion.cursor)):
            for funcion in (huella, representacion):
                with self.subTest(objeto=type(objeto).__name__, funcion=funcion.__name__):
                    with self.assertRaises(TypeError):
                        funcion(objeto)

    def test_interfaz_invalidada_es_rechazada(self):
        conexion = self.auxiliar()
        interfaz = self.dentro(conexion, lambda i: i)
        resultado = huella(interfaz)
        self.assertFalse(resultado.confiable)
        self.assertIsNone(resultado.huella)
        self.assertEqual(resultado.razones, ("error_sqlite",))
        with self.assertRaises(sqlite3.ProgrammingError):
            representacion(interfaz)

    def test_conexion_cerrada_no_produce_huella(self):
        conexion = self.auxiliar()
        conexion.close()
        resultado = huella(conexion)
        self.assertFalse(resultado.confiable)
        self.assertEqual(resultado.razones, ("error_sqlite",))

    def test_estructura_no_representable_se_trata_igual_en_ambas(self):
        conexion = self.auxiliar()
        conexion.execute("CREATE TABLE aux_generada(a INTEGER, b INTEGER GENERATED ALWAYS AS (a + 1) VIRTUAL)")
        conexion.commit()
        real = huella(conexion)
        restringida = self.dentro(conexion, lambda i: huella(i))
        self.assertFalse(real.confiable)
        self.assertEqual((restringida.confiable, restringida.huella, restringida.razones),
                         (real.confiable, real.huella, real.razones))

    def test_el_cambio_estructural_durante_la_lectura_se_detecta_en_ambas(self):
        original = modulo.representacion_estructural_sqlite
        conexion = self.auxiliar()

        def intrusa(destino):
            representacion_leida = original(destino)
            destino.execute("CREATE TABLE aux_intrusa(a INTEGER)")
            return representacion_leida

        with patch.object(modulo, "representacion_estructural_sqlite", intrusa):
            real = huella(conexion)
        self.assertEqual((real.confiable, real.razones), (False, ("esquema_cambio_durante_lectura",)))
        conexion.execute("DROP TABLE aux_intrusa")
        conexion.commit()
        with patch.object(modulo, "representacion_estructural_sqlite", intrusa):
            restringida = self.dentro(conexion, lambda i: huella(i))
        self.assertEqual((restringida.confiable, restringida.razones), (False, ("esquema_cambio_durante_lectura",)))


class EstadoPreservadoTest(_Aislada):
    def test_el_calculo_no_altera_transaccion_claves_foraneas_datos_ni_estructura(self):
        conexion = self.auxiliar()
        vistos = {}

        def instantanea(i):
            return (
                i.execute("SELECT type, name, sql FROM sqlite_master ORDER BY name").fetchall(),
                i.execute("SELECT * FROM aux_padre ORDER BY id").fetchall(),
                i.execute("SELECT * FROM aux_hija ORDER BY id").fetchall(),
                i.execute("SELECT name, seq FROM sqlite_sequence ORDER BY name").fetchall(),
            )

        def operacion(i):
            vistos["antes"] = (instantanea(i), conexion.in_transaction, conexion.isolation_level,
                               i.execute("PRAGMA foreign_keys").fetchone()[0],
                               i.execute("PRAGMA schema_version").fetchone()[0])
            huella(i)
            representacion(i)
            vistos["despues"] = (instantanea(i), conexion.in_transaction, conexion.isolation_level,
                                 i.execute("PRAGMA foreign_keys").fetchone()[0],
                                 i.execute("PRAGMA schema_version").fetchone()[0])

        ejecutar(conexion, operacion)
        self.assertEqual(vistos["antes"], vistos["despues"])
        self.assertTrue(vistos["antes"][1])
        self.assertEqual(vistos["antes"][3], 0)
        self.assertEqual(conexion.execute("PRAGMA foreign_keys").fetchone()[0], 1)
        self.assertFalse(conexion.in_transaction)

    def test_el_autorizador_sigue_denegando_escrituras_protegidas_tras_calcular(self):
        conexion = self.auxiliar()

        def operacion(i):
            huella(i)
            with self.assertRaises(sqlite3.DatabaseError):
                i.execute("PRAGMA foreign_keys=ON")
            with self.assertRaises(sqlite3.DatabaseError):
                i.execute("COMMIT")
            with self.assertRaises(sqlite3.DatabaseError):
                i.execute("ATTACH DATABASE ':memory:' AS otra")
            return huella(i).huella

        self.assertEqual(self.dentro(conexion, operacion), huella(conexion).huella)

    def test_calcular_con_conexion_real_no_abre_transaccion_ni_cambia_claves_foraneas(self):
        conexion = self.auxiliar()
        huella(conexion)
        representacion(conexion)
        self.assertFalse(conexion.in_transaction)
        self.assertEqual(conexion.execute("PRAGMA foreign_keys").fetchone()[0], 1)


class AislamientoDelModuloTest(_Aislada):
    def test_el_modulo_de_huella_no_toca_la_conexion_real_ni_el_control_transaccional(self):
        codigo = re.sub(r'"""[\s\S]*?"""', "", Path(modulo.__file__).read_text(encoding="utf-8"))
        for patron in (r"_conexion\b", r"\.commit\(", r"\.rollback\(", r"conexion\.close\(",
                       r"set_authorizer", r"sqlite3\.connect", r"BEGIN", r"INSERT|UPDATE|DELETE|CREATE|DROP|ALTER",
                       r"foreign_keys\s*=", r"import database|from database", r"backup_service"):
            with self.subTest(patron=patron):
                self.assertIsNone(re.search(patron, codigo, re.MULTILINE), patron)

    def test_no_hay_importacion_circular(self):
        for primero, segundo in (("sqlite_control_claves_foraneas", "sqlite_huella_estructural"),
                                 ("sqlite_huella_estructural", "sqlite_control_claves_foraneas")):
            with self.subTest(primero=primero):
                programa = (
                    f"import sys, services.{primero}, services.{segundo}; "
                    "print('services.sqlite_control_claves_foraneas' in sys.modules)"
                )
                salida = subprocess.run([sys.executable, "-c", programa], cwd=RAIZ, capture_output=True, text=True)
                self.assertEqual(salida.returncode, 0, salida.stderr)
        # El módulo de control no depende del de huella: importarlo solo no carga la huella.
        programa = "import sys, services.sqlite_control_claves_foraneas; print('services.sqlite_huella_estructural' in sys.modules)"
        salida = subprocess.run([sys.executable, "-c", programa], cwd=RAIZ, capture_output=True, text=True)
        self.assertEqual((salida.returncode, salida.stdout.strip()), (0, "False"), salida.stderr)


class HuellaDentroDeLaTransaccionTest(_Aislada):
    """Cálculo previo al commit con la interfaz restringida, en DELETE y WAL (tabla auxiliar ficticia)."""

    @staticmethod
    def _modificar(interfaz):
        interfaz.execute("ALTER TABLE aux_hija ADD COLUMN nota TEXT")
        interfaz.execute("CREATE INDEX idx_aux_hija_valor ON aux_hija(valor)")

    def test_huella_previa_al_commit_coincide_con_la_persistida(self):
        for modo in MODOS:
            with self.subTest(modo=modo):
                conexion = self.auxiliar(modo)
                inicial = huella(conexion).huella
                observado = {}

                def operacion(interfaz):
                    self._modificar(interfaz)
                    observado["nueva"] = huella(interfaz).huella
                    observado["lector"] = huella(self.independiente()).huella
                    return observado["nueva"]

                resultado = ejecutar(conexion, operacion)
                self.assertTrue(resultado.confirmada)
                self.assertNotEqual(observado["nueva"], inicial)
                self.assertEqual(observado["lector"], inicial)
                self.assertEqual(resultado.resultado, observado["nueva"])
                self.assertEqual(huella(self.independiente()).huella, observado["nueva"])
                self.assertEqual(huella(conexion).huella, observado["nueva"])
                self.assertEqual(conexion.execute("PRAGMA foreign_keys").fetchone()[0], 1)
                self.assertFalse(conexion.in_transaction)

    def test_un_fallo_posterior_al_calculo_conserva_la_huella_original(self):
        for modo in MODOS:
            with self.subTest(modo=modo):
                conexion = self.auxiliar(modo)
                inicial = huella(conexion).huella
                datos = conexion.execute("SELECT * FROM aux_hija ORDER BY id").fetchall()
                observado = {}

                def operacion(interfaz):
                    self._modificar(interfaz)
                    observado["nueva"] = huella(interfaz).huella
                    raise RuntimeError("fallo simulado posterior al cálculo")

                with self.assertRaises(ErrorAntesDeConfirmar) as contexto:
                    ejecutar(conexion, operacion)
                self.assertIs(contexto.exception.confirmada, False)
                self.assertNotEqual(observado["nueva"], inicial)
                self.assertEqual(huella(conexion).huella, inicial)
                self.assertEqual(huella(self.independiente()).huella, inicial)
                self.assertEqual(conexion.execute("SELECT * FROM aux_hija ORDER BY id").fetchall(), datos)
                self.assertEqual(conexion.execute("PRAGMA foreign_keys").fetchone()[0], 1)
                self.assertFalse(conexion.in_transaction)

    def test_un_error_de_lectura_de_la_huella_no_impide_el_rollback(self):
        conexion = self.auxiliar()
        inicial = huella(conexion).huella

        def operacion(interfaz):
            self._modificar(interfaz)
            interfaz.execute("CREATE TABLE aux_generada(a INTEGER, b INTEGER GENERATED ALWAYS AS (a + 1) VIRTUAL)")
            if huella(interfaz).confiable:
                return "inesperado"
            raise RuntimeError("huella no confiable")

        with self.assertRaises(ErrorAntesDeConfirmar):
            ejecutar(conexion, operacion)
        self.assertEqual(huella(conexion).huella, inicial)


if __name__ == "__main__":
    unittest.main()
