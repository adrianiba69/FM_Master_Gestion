"""Etapa 3D.4C.5D.5B: reconstrucción segura de ``resumenes`` (solo bases ficticias).

Bases en memoria o en directorios temporales. ``database.conectar`` queda bloqueado. ``crear_base()``
solo se usa para PREPARAR los esquemas ficticios, nunca dentro de la operación de reconstrucción.
"""

import re
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from services import sqlite_reconstruccion_resumenes as modulo
from services.sqlite_control_claves_foraneas import (
    ErrorAntesDeConfirmar,
    ErrorDespuesDeConfirmar,
    ErrorEstadoIncierto,
)
from services.sqlite_huella_estructural import calcular_huella_estructural_sqlite as huella
from services.sqlite_reconstruccion_resumenes import (
    COLUMNAS,
    DEPENDIENTES,
    ErrorReconstruccionResumenes,
    HUELLA_FINAL_ESPERADA,
    HUELLA_ORIGEN_AUTORIZADA,
    reconstruir_resumenes as reconstruir,
)
from tests.test_compatibilidad_esquemas_historicos_3d4c5c2 import ESQUEMAS_HISTORICOS, database
from tests.test_control_claves_foraneas_sqlite_3d4c5d4 import ConexionInstrumentada

ORIGENES = ("build_0_7_8c81526", "build_1_7_4994dc6")
MODOS = ("DELETE", "WAL")
TABLAS = ("resumenes",) + tuple(sorted(DEPENDIENTES))


def _insertar(c, tabla, **datos):
    c.execute(f"INSERT INTO {tabla}({', '.join(datos)}) VALUES ({', '.join('?' * len(datos))})", tuple(datos.values()))


def _sembrar(c, *, vaciar=False, huerfano=False):
    for id_ in (1, 2):
        _insertar(c, "clientes", id=id_, nombre=f"Cliente {id_}")
    for id_ in (9001, 9002):
        _insertar(c, "emisores_fiscales", id=id_, razon_social=f"Emisor {id_}")
    _insertar(c, "emisores_facturacion", id=9001, alias="Alias")
    _insertar(c, "servicios", id=1, cliente_id=1, concepto="Hosting", importe=10)
    base = dict(fecha="2024-02-01", fecha_vencimiento="2024-02-10")
    _insertar(c, "resumenes", id=1, numero=1001, cliente_id=1, emisor_fiscal_id=9001, tipo_factura="B",
              punto_venta="0001", total=1490.5, saldo=490.5, estado="Pendiente", estado_facturacion="Facturado",
              fecha_facturacion="2024-02-02", cae="CAE1", vencimiento_cae="2024-03-01",
              numero_factura="0001-00000001", pdf_path="a.pdf", fecha_creacion="2024-02-01", **base)
    _insertar(c, "resumenes", id=2, numero=1002, cliente_id=2, total=4000, saldo=0, estado="Pagado", **base)
    _insertar(c, "resumenes", id=3, numero=1003, cliente_id=1, emisor_fiscal_id=9002, **base)
    _insertar(c, "resumenes", id=4, numero=2**40, cliente_id=2, saldo="abc", pdf_path=b"\x00\x01", **base)
    if huerfano:
        _insertar(c, "resumenes", id=5, numero=1005, cliente_id=1, emisor_fiscal_id=99999, **base)
    _insertar(c, "resumenes", id=7, numero=1007, cliente_id=1, **base)
    c.execute("DELETE FROM resumenes WHERE id=7")  # deja la secuencia en 7 con max(id) menor
    _insertar(c, "resumen_conceptos", id=1, resumen_id=1, servicio_id=1, concepto="Hosting", importe=10, total=10)
    _insertar(c, "resumen_conceptos", id=2, resumen_id=2, concepto="Ajuste")
    _insertar(c, "servicio_renovaciones", id=1, servicio_id=1, cliente_id=1, fecha_renovacion="2024-12-31",
              fecha_inicio_anterior="2024-01-01", fecha_fin_anterior="2024-12-31",
              fecha_inicio_nueva="2025-01-01", fecha_fin_nueva="2025-12-31", resumen_id=1)
    _insertar(c, "factura_arca", id=1, cliente_id=1, emisor_id=9001, resumen_id=1, fecha="2024-02-02")
    _insertar(c, "intentos_emision_arca", id=1, resumen_id=1, cliente_id=1, emisor_fiscal_id=9001, emisor_id=9001,
              cuit_emisor="20000000001", punto_venta=1, tipo_comprobante=6, numero_planificado=1,
              fecha_comprobante="2024-02-02", concepto=2, tipo_documento=80, documento_receptor=20111111112,
              condicion_iva_receptor_id=5, importe_total="1.00", importe_neto="1.00", importe_iva="0",
              importe_exento="0", importe_no_gravado="0", importe_tributos="0", moneda="PES", cotizacion="1",
              estado="Pendiente", creado_en="2024-02-02", actualizado_en="2024-02-02", factura_arca_id=1)
    if vaciar:
        for tabla in ("intentos_emision_arca", "factura_arca", "servicio_renovaciones", "resumen_conceptos",
                      "resumenes"):
            c.execute(f"DELETE FROM {tabla}")


def datos(c):
    """Registros con tipo de almacenamiento y secuencias, en orden estable de columnas."""
    resultado = {}
    for tabla in TABLAS:
        columnas = list(COLUMNAS) if tabla == "resumenes" else [f[1] for f in c.execute(f'PRAGMA table_info("{tabla}")')]
        filas = c.execute(f'SELECT {", ".join(columnas)} FROM {tabla} ORDER BY id').fetchall()
        resultado[tabla] = [(tuple(f), tuple(type(v) for v in f)) for f in filas]
    resultado["sqlite_sequence"] = c.execute("SELECT name, seq FROM sqlite_sequence ORDER BY name").fetchall()
    return resultado


def foto(c):
    if hasattr(c, "fallos"):
        c.fallos.clear()
    return (
        c.execute("SELECT type, name, tbl_name, sql FROM sqlite_master ORDER BY type, name").fetchall(),
        datos(c),
        huella(c).huella,
    )


class _Aislada(unittest.TestCase):
    def setUp(self):
        parche = patch.object(database, "conectar", side_effect=AssertionError("acceso a base real bloqueado"))
        parche.start()
        self.addCleanup(parche.stop)

    def base(self, origen=ORIGENES[1], *, modo=None, con_datos=True, vaciar=False, huerfano=False):
        """Base ficticia con ``crear_base()`` ya aplicado (origen=None: esquema final) y foreign_keys=ON."""
        if modo is None:
            c = sqlite3.connect(":memory:", factory=ConexionInstrumentada)
        else:
            directorio = tempfile.TemporaryDirectory()
            self.addCleanup(directorio.cleanup)
            self.ruta = str(Path(directorio.name) / "ficticia.db")
            c = sqlite3.connect(self.ruta, factory=ConexionInstrumentada, timeout=0.05)
            self.assertEqual(c.execute(f"PRAGMA journal_mode={modo}").fetchone()[0].upper(), modo)
        self.addCleanup(c.close)
        if origen:
            for _, _, _, sql in ESQUEMAS_HISTORICOS[origen][2]:
                c.execute(sql)
            c.commit()
        c.execute("BEGIN IMMEDIATE")
        database.crear_base(conexion=c)
        c.commit()
        c.execute("PRAGMA foreign_keys=ON")
        if con_datos:
            _sembrar(c, vaciar=vaciar, huerfano=huerfano)
            c.commit()
        return c

    def otra(self):
        c = sqlite3.connect(self.ruta, timeout=0.05)
        self.addCleanup(c.close)
        return c

    def assertRestaurada(self, c):
        self.assertEqual(c.execute("PRAGMA foreign_keys").fetchone()[0], 1)
        self.assertFalse(c.in_transaction)

    def assertRechazo(self, c, razon):
        antes = foto(c)
        with self.assertRaises(ErrorAntesDeConfirmar) as contexto:
            reconstruir(c)
        self.assertIs(contexto.exception.confirmada, False)
        self.assertIsInstance(contexto.exception.__cause__, ErrorReconstruccionResumenes)
        self.assertEqual(contexto.exception.__cause__.razon, razon)
        self.assertEqual(foto(c), antes)
        self.assertRestaurada(c)


class ReconstruccionTest(_Aislada):
    def test_las_huellas_de_referencia_se_confirman_con_bases_ficticias(self):
        for origen in ORIGENES:
            self.assertEqual(huella(self.base(origen, con_datos=False)).huella, HUELLA_ORIGEN_AUTORIZADA)
        self.assertEqual(huella(self.base(None, con_datos=False)).huella, HUELLA_FINAL_ESPERADA)

    def test_reconstruye_ambos_origenes_conservando_todo(self):
        for origen in ORIGENES:
            with self.subTest(origen=origen):
                c = self.base(origen)
                antes = datos(c)
                relaciones = c.execute("SELECT * FROM factura_arca").fetchall()
                resultado = reconstruir(c)
                self.assertTrue(resultado.reconstruida)
                self.assertEqual((resultado.huella_origen, resultado.huella_final, resultado.registros),
                                 (HUELLA_ORIGEN_AUTORIZADA, HUELLA_FINAL_ESPERADA, 4))
                self.assertEqual(huella(c).huella, HUELLA_FINAL_ESPERADA)
                self.assertEqual(datos(c), antes)
                self.assertEqual(c.execute("SELECT * FROM factura_arca").fetchall(), relaciones)
                self.assertEqual(c.execute("PRAGMA foreign_key_check").fetchall(), [])
                self.assertEqual(c.execute("PRAGMA quick_check").fetchall(), [("ok",)])
                self.assertRestaurada(c)

    def test_tipos_de_almacenamiento_nulos_y_emisores(self):
        c = self.base()
        reconstruir(c)
        self.assertEqual(c.execute("SELECT typeof(saldo), typeof(pdf_path), typeof(numero) FROM resumenes WHERE id=4")
                         .fetchone(), ("text", "blob", "integer"))
        self.assertEqual(c.execute("SELECT id, emisor_fiscal_id FROM resumenes ORDER BY id").fetchall(),
                         [(1, 9001), (2, None), (3, 9002), (4, None)])

    def test_bases_vacias_y_tabla_vacia_con_secuencia_historica(self):
        c = self.base(con_datos=False)
        self.assertTrue(reconstruir(c).reconstruida)
        self.assertEqual(c.execute("SELECT COUNT(*) FROM sqlite_sequence WHERE name='resumenes'").fetchone()[0], 0)
        self.assertEqual(huella(c).huella, HUELLA_FINAL_ESPERADA)
        c = self.base(vaciar=True)
        self.assertEqual(c.execute("SELECT seq FROM sqlite_sequence WHERE name='resumenes'").fetchone()[0], 7)
        self.assertEqual(c.execute("SELECT COUNT(*) FROM resumenes").fetchone()[0], 0)
        antes = datos(c)
        self.assertTrue(reconstruir(c).reconstruida)
        self.assertEqual(datos(c), antes)
        _insertar(c, "resumenes", numero=1, cliente_id=1, fecha="x", fecha_vencimiento="y")
        self.assertEqual(c.execute("SELECT MAX(id) FROM resumenes").fetchone()[0], 8)

    def test_identificadores_altos_eliminados_no_se_reutilizan(self):
        c = self.base()
        self.assertEqual(c.execute("SELECT MAX(id) FROM resumenes").fetchone()[0], 4)
        reconstruir(c)
        self.assertEqual(c.execute("SELECT seq FROM sqlite_sequence WHERE name='resumenes'").fetchone()[0], 7)
        _insertar(c, "resumenes", numero=5000, cliente_id=1, fecha="x", fecha_vencimiento="y")
        self.assertEqual(c.execute("SELECT MAX(id) FROM resumenes").fetchone()[0], 8)

    def test_indices_dependientes_y_ausencia_de_cascadas(self):
        c = self.base()
        antes = {t: c.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in TABLAS}
        reconstruir(c)
        self.assertEqual({t: c.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in TABLAS}, antes)
        self.assertEqual(
            sorted(f[0] for f in c.execute("SELECT name FROM sqlite_master WHERE tbl_name='resumenes'")),
            ["idx_resumenes_cliente", "resumenes", "sqlite_autoindex_resumenes_1"])
        for tabla in DEPENDIENTES:
            padres = {f[2] for f in c.execute(f"PRAGMA foreign_key_list({tabla})")}
            self.assertIn("resumenes", padres, tabla)
        self.assertEqual(c.execute("SELECT COUNT(*) FROM sqlite_master WHERE name LIKE '%reconstruccion%'")
                         .fetchone()[0], 0)

    def test_la_nueva_clave_foranea_valida_y_rechaza_referencias_fiscales(self):
        c = self.base()
        reconstruir(c)
        padres = {f[2]: f[3] for f in c.execute("PRAGMA foreign_key_list(resumenes)")}
        self.assertEqual(padres, {"clientes": "cliente_id", "emisores_fiscales": "emisor_fiscal_id"})
        nuevo = dict(numero=7000, cliente_id=1, fecha="x", fecha_vencimiento="y")
        with self.assertRaises(sqlite3.IntegrityError):
            _insertar(c, "resumenes", emisor_fiscal_id=99999, **nuevo)
        _insertar(c, "resumenes", emisor_fiscal_id=9001, **nuevo)
        with self.assertRaises(sqlite3.IntegrityError):
            c.execute("DELETE FROM emisores_fiscales WHERE id=9002")

    def test_emisor_fiscal_huerfano_es_rechazado_sin_corregir(self):
        for origen in ORIGENES:
            with self.subTest(origen=origen):
                c = self.base(origen, huerfano=True)
                self.assertRechazo(c, "emisor_fiscal_huerfano")
                self.assertEqual(c.execute("SELECT emisor_fiscal_id FROM resumenes WHERE id=5").fetchone()[0], 99999)

    def test_estructuras_no_contempladas_son_rechazadas(self):
        casos = {
            "indice": ("CREATE INDEX idx_extra ON resumenes(fecha)", "huella_de_origen_no_autorizada"),
            "trigger": ("CREATE TRIGGER trg_extra AFTER INSERT ON resumenes BEGIN SELECT 1; END",
                        "huella_de_origen_no_autorizada"),
            "vista": ("CREATE VIEW v_extra AS SELECT id FROM resumenes", "huella_de_origen_no_autorizada"),
            "tabla_extra": ("CREATE TABLE extra(id INTEGER)", "huella_de_origen_no_autorizada"),
            "auxiliar": (f"CREATE TABLE {modulo.TABLA_AUXILIAR}(a INTEGER)", "tabla_auxiliar_preexistente"),
            "no_confiable": ("CREATE TABLE gen(a INTEGER, b INTEGER GENERATED ALWAYS AS (a + 1) VIRTUAL)",
                             "huella_de_origen_no_confiable"),
        }
        for nombre, (sql, razon) in casos.items():
            with self.subTest(caso=nombre):
                c = self.base()
                c.execute(sql)
                c.commit()
                self.assertRechazo(c, razon)

    def test_huellas_desconocidas_son_rechazadas(self):
        for historico in ("build_0_2_2_9b6a850", "build_0_5_52b0189"):
            with self.subTest(historico=historico):
                c = self.base(historico, con_datos=False)
                if huella(c).huella == HUELLA_FINAL_ESPERADA:
                    continue
                self.assertRechazo(c, "huella_de_origen_no_autorizada")

    def test_esquema_ya_corregido_y_segunda_ejecucion_no_modifican_nada(self):
        for preparar in (lambda: self.base(None), lambda: (lambda c: (reconstruir(c), c)[1])(self.base())):
            c = preparar()
            antes, version = foto(c), c.execute("PRAGMA schema_version").fetchone()[0]
            resultado = reconstruir(c)
            self.assertFalse(resultado.reconstruida)
            self.assertEqual(resultado.huella_origen, HUELLA_FINAL_ESPERADA)
            self.assertEqual(foto(c), antes)
            self.assertEqual(c.execute("PRAGMA schema_version").fetchone()[0], version)
            self.assertRestaurada(c)

    def test_el_modulo_respeta_las_prohibiciones(self):
        codigo = re.sub(r'"""[\s\S]*?"""', "", Path(modulo.__file__).read_text(encoding="utf-8"))
        for patron in (r"writable_schema", r"SELECT \*", r"sqlite3\.connect", r"_conexion\b", r"\.commit\(",
                       r"\.rollback\(", r"set_authorizer", r"crear_base", r"import database|from database",
                       r"backup_service", r"user_version|application_id", r"runtime_paths"):
            with self.subTest(patron=patron):
                self.assertIsNone(re.search(patron, codigo), patron)
        self.assertEqual(len(COLUMNAS), 18)
        for columna in COLUMNAS:
            self.assertIn(columna, modulo.SQL_COPIAR)
        self.assertNotIn("SELECT *", modulo.SQL_COPIAR)
        self.assertTrue(modulo.SQL_RENOMBRAR.startswith(f"ALTER TABLE {modulo.TABLA_AUXILIAR} RENAME TO resumenes"))
        self.assertEqual(modulo.SQL_ELIMINAR_ORIGINAL, "DROP TABLE resumenes")


class ModosYHuellaPrevia(_Aislada):
    def test_delete_y_wal_con_huella_final_calculada_antes_del_commit(self):
        for modo in MODOS:
            with self.subTest(modo=modo):
                c = self.base(modo=modo)
                antes = datos(c)
                observado = {}
                original = modulo._calcular_huella_final

                def calcular(i):
                    observado["previa"] = original(i)
                    observado["lector"] = huella(self.otra()).huella
                    return observado["previa"]

                with patch.object(modulo, "_calcular_huella_final", calcular):
                    resultado = reconstruir(c)
                self.assertEqual(observado["lector"], HUELLA_ORIGEN_AUTORIZADA)
                self.assertEqual(huella(self.otra()).huella, observado["previa"])
                self.assertEqual(resultado.huella_final, observado["previa"])
                self.assertEqual(datos(self.otra()), antes)
                self.assertRestaurada(c)
                self.assertEqual(c.execute("PRAGMA journal_mode").fetchone()[0].upper(), modo)


class BackupSimuladoTest(_Aislada):
    def _gancho(self, destino, eventos, *, fallar=False):
        def gancho():
            eventos.append("backup")
            if fallar:
                raise RuntimeError("fallo simulado del backup")
            lectura = sqlite3.connect(f"file:{Path(self.ruta).as_posix()}?mode=ro", uri=True, timeout=0.05)
            copia = sqlite3.connect(destino)
            try:
                lectura.backup(copia)
            finally:
                copia.close()
                lectura.close()
            escritor = self.otra()
            with self.assertRaises(sqlite3.OperationalError):
                escritor.execute("BEGIN IMMEDIATE")
        return gancho

    def test_backup_consistente_previo_con_reserva_de_escritura(self):
        for modo in MODOS:
            with self.subTest(modo=modo):
                c = self.base(modo=modo)
                antes = datos(c)
                destino = str(Path(self.ruta).with_name("copia.db"))
                eventos = []
                original = modulo._crear_tabla_auxiliar

                def crear(i):
                    eventos.append("crear_auxiliar")
                    original(i)

                with patch.object(modulo, "_crear_tabla_auxiliar", crear):
                    self.assertTrue(reconstruir(c, antes_de_operar=self._gancho(destino, eventos)).reconstruida)
                self.assertEqual(eventos, ["backup", "crear_auxiliar"])
                copia = sqlite3.connect(destino)
                self.addCleanup(copia.close)
                self.assertEqual(huella(copia).huella, HUELLA_ORIGEN_AUTORIZADA)
                self.assertEqual(datos(copia), antes)
                self.assertEqual(huella(c).huella, HUELLA_FINAL_ESPERADA)

    def test_un_fallo_del_backup_impide_la_reconstruccion(self):
        for modo in MODOS:
            with self.subTest(modo=modo):
                c = self.base(modo=modo)
                antes, eventos = foto(c), []
                with patch.object(modulo, "_crear_tabla_auxiliar", side_effect=AssertionError("no debía iniciar")):
                    with self.assertRaises(ErrorAntesDeConfirmar) as contexto:
                        reconstruir(c, antes_de_operar=self._gancho("", eventos, fallar=True))
                self.assertEqual((contexto.exception.fase, contexto.exception.confirmada), ("antes_de_operar", False))
                self.assertEqual(eventos, ["backup"])
                self.assertEqual(foto(self.otra()), antes)
                self.assertRestaurada(c)

    def test_un_segundo_escritor_no_puede_modificar_durante_la_operacion(self):
        for modo in MODOS:
            with self.subTest(modo=modo):
                c = self.base(modo=modo)
                intentos = []
                original = modulo._verificar_copia

                def verificar(i, captura):
                    escritor = self.otra()
                    try:
                        escritor.execute("INSERT INTO clientes(id, nombre) VALUES (500, 'intruso')")
                        intentos.append("escribio")
                    except sqlite3.OperationalError:
                        intentos.append("bloqueado")
                    original(i, captura)

                with patch.object(modulo, "_verificar_copia", verificar):
                    reconstruir(c)
                self.assertEqual(intentos, ["bloqueado"])
                self.assertEqual(c.execute("SELECT COUNT(*) FROM clientes WHERE id=500").fetchone()[0], 0)
                _insertar(self.otra(), "clientes", id=501, nombre="posterior")  # liberado tras la operación


class FallosInyectadosTest(_Aislada):
    SQL = (modulo.SQL_CREAR_AUXILIAR, modulo.SQL_COPIAR, modulo.SQL_ELIMINAR_ORIGINAL, modulo.SQL_RENOMBRAR,
           modulo.SQL_CREAR_INDICE_CLIENTE, modulo.SQL_SECUENCIA_ACTUALIZAR)

    def _caso(self, modo, inyectar):
        c = self.base(modo=modo)
        antes = foto(c)
        with inyectar(c):
            with self.assertRaises(ErrorAntesDeConfirmar) as contexto:
                reconstruir(c)
        self.assertIs(contexto.exception.confirmada, False)
        self.assertTrue(contexto.exception.conexion_apta)
        self.assertEqual(foto(self.otra()), antes)
        self.assertEqual(foto(c), antes)
        self.assertEqual(huella(self.otra()).huella, HUELLA_ORIGEN_AUTORIZADA)
        self.assertRestaurada(c)
        return contexto.exception

    @staticmethod
    def _sql(sentencia, desde=1):
        def inyectar(c):
            c.fallos[sentencia] = (desde, sqlite3.OperationalError("inyectado"))
            return patch.object(modulo, "_ident", modulo._ident)  # contexto neutro
        return inyectar

    def test_fallos_de_cada_sentencia_se_revierten_con_evidencia(self):
        for modo in MODOS:
            for sentencia in self.SQL:
                with self.subTest(modo=modo, sentencia=sentencia[:40]):
                    self._caso(modo, self._sql(sentencia))

    def test_fallos_de_verificacion_huella_e_integridad_se_revierten(self):
        casos = {
            "verificar_copia": lambda c: patch.object(modulo, "_verificar_copia", side_effect=RuntimeError("x")),
            "verificar_relaciones": lambda c: patch.object(modulo, "_verificar_relaciones", side_effect=RuntimeError("x")),
            "huella_final_error": lambda c: patch.object(
                modulo, "calcular_huella_estructural_sqlite",
                side_effect=[huella(c), sqlite3.OperationalError("inyectado")]),
            "huella_final_incorrecta": lambda c: patch.object(modulo, "HUELLA_FINAL_ESPERADA", "0" * 64),
            "integridad_final": lambda c: self._sql("PRAGMA foreign_key_check", 3)(c),
            "commit": lambda c: self._sql("commit")(c),
        }
        for modo in MODOS:
            for nombre, inyectar in casos.items():
                with self.subTest(modo=modo, fase=nombre):
                    if nombre == "huella_final_error":
                        # La primera llamada (origen) usa la huella real; la segunda falla.
                        def preparar(c):
                            real = modulo.calcular_huella_estructural_sqlite
                            llamadas = []

                            def calcular(i):
                                llamadas.append(1)
                                if len(llamadas) == 2:
                                    raise sqlite3.OperationalError("inyectado")
                                return real(i)
                            return patch.object(modulo, "calcular_huella_estructural_sqlite", calcular)
                        self._caso(modo, preparar)
                    else:
                        self._caso(modo, inyectar)

    def test_la_huella_final_incorrecta_deja_razon_fija_en_la_causa(self):
        c = self.base()
        with patch.object(modulo, "HUELLA_FINAL_ESPERADA", "0" * 64):
            with self.assertRaises(ErrorAntesDeConfirmar) as contexto:
                reconstruir(c)
        self.assertEqual(contexto.exception.__cause__.razon, "huella_final_inesperada")

    def test_estado_incierto_se_distingue_del_rollback_y_no_se_reintenta(self):
        c = self.base(modo="DELETE")
        c.llamadas.clear()
        c.fallos["commit"] = (1, "confirmar_y_fallar")
        with self.assertRaises(ErrorEstadoIncierto) as contexto:
            reconstruir(c)
        self.assertIsNone(contexto.exception.confirmada)
        self.assertFalse(contexto.exception.conexion_apta)
        self.assertEqual(c.llamadas["commit"], 1)
        self.assertEqual(c.llamadas[modulo.SQL_CREAR_AUXILIAR], 1)
        # Evidencia independiente de lo ocurrido (el mecanismo no la afirmaba): sí se persistió.
        self.assertEqual(huella(self.otra()).huella, HUELLA_FINAL_ESPERADA)

    def test_fallo_posterior_al_commit_se_informa_como_confirmado(self):
        c = self.base(modo="WAL")
        c.fallos["PRAGMA foreign_keys=ON"] = (1, sqlite3.OperationalError("inyectado"))
        with self.assertRaises(ErrorDespuesDeConfirmar) as contexto:
            reconstruir(c)
        self.assertIs(contexto.exception.confirmada, True)
        self.assertFalse(contexto.exception.conexion_apta)
        self.assertEqual(huella(self.otra()).huella, HUELLA_FINAL_ESPERADA)


if __name__ == "__main__":
    unittest.main()
