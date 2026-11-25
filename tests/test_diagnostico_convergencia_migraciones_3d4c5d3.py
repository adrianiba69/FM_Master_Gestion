"""Etapa 3D.4C.5D.3: diagnóstico de convergencia de migraciones históricas SQLite.

Solo bases ficticias en memoria. Se bloquea ``database.conectar`` (y con él cualquier
acceso a DATABASE_PATH) y no se ejecuta main.py. Nada de este módulo corrige
migraciones: documenta, con evidencia reproducible, por qué los esquemas históricos
9b6a850, 8c81526 y 4994dc6 no convergen con la huella actual tras crear_base().
"""

import json
import inspect
import re
import sqlite3
import unittest
from pathlib import Path
from unittest.mock import patch

from services.sqlite_huella_estructural import (
    calcular_huella_estructural_sqlite as huella,
    representacion_estructural_sqlite as representacion,
)
from tests.test_compatibilidad_esquemas_historicos_3d4c5c2 import ESQUEMAS_HISTORICOS, database

RAIZ = Path(__file__).resolve().parents[1]
H_9B = "build_0_2_2_9b6a850"
H_8C = "build_0_7_8c81526"
H_49 = "build_1_7_4994dc6"

# Datos ficticios; solo se insertan las columnas que existen en cada esquema histórico.
DATOS = {
    "clientes": [
        {"id": 1, "codigo": "C001", "razon_social": "Alfa Ficticia SA", "nombre_comercial": "Alfa",
         "responsable": "Ana", "cuit": "30-00000000-1", "iva": "Responsable Inscripto",
         "servicio": "Hosting", "importe": 1500.5, "descuento": 10.0, "vencimiento": 10,
         "estado": "Activo", "observaciones": "ficticio", "fecha_alta": "2024-01-01"},
        {"id": 2, "codigo": "C002", "razon_social": "Beta Ficticia SRL", "nombre_comercial": "Beta",
         "responsable": "Beto", "cuit": "30-00000000-2", "iva": "Monotributo",
         "servicio": "Dominio", "importe": 2000.0, "descuento": 0.0, "vencimiento": 15,
         "estado": "Activo", "observaciones": None, "fecha_alta": "2024-01-02"},
        {"id": 3, "codigo": "C003", "razon_social": "Gamma Ficticia", "nombre_comercial": None,
         "responsable": None, "cuit": None, "iva": None,
         "servicio": None, "importe": None, "descuento": None, "vencimiento": None,
         "estado": "Baja", "observaciones": "", "fecha_alta": "2024-01-03"},
    ],
    "servicios": [
        {"id": 1, "cliente_id": 1, "concepto": "Hosting", "descripcion": "Plan A", "cantidad": 1,
         "importe": 1500.5, "descuento": 10.0, "activo": 1, "fecha_inicio": "2024-01-01",
         "fecha_fin": "2999-12-31", "renovable": 1, "estado_periodo": "Activo"},
        {"id": 2, "cliente_id": 2, "concepto": "Dominio", "descripcion": None, "cantidad": 2,
         "importe": 2000.0, "descuento": 0.0, "activo": 1, "fecha_inicio": "2024-01-01",
         "fecha_fin": "2024-12-31", "renovable": 0, "estado_periodo": "Activo"},
        {"id": 3, "cliente_id": 3, "concepto": "Soporte", "descripcion": None, "cantidad": 1,
         "importe": 300.0, "descuento": 0.0, "activo": 1, "fecha_inicio": "2024-01-01",
         "fecha_fin": "2024-06-30", "renovable": 1, "estado_periodo": "Activo"},
    ],
    "resumenes": [
        {"id": 1, "numero": 1001, "cliente_id": 1, "fecha": "2024-02-01", "fecha_vencimiento": "2024-02-10",
         "total": 1490.5, "saldo": 490.5, "estado": "Pendiente", "pdf_path": None, "fecha_creacion": "2024-02-01"},
        {"id": 2, "numero": 1002, "cliente_id": 2, "fecha": "2024-02-01", "fecha_vencimiento": "2024-02-15",
         "total": 4000.0, "saldo": 0.0, "estado": "Pagado", "pdf_path": "ficticio.pdf", "fecha_creacion": "2024-02-01"},
        {"id": 3, "numero": 1003, "cliente_id": 1, "fecha": "2024-03-01", "fecha_vencimiento": "2024-03-10",
         "total": 1.0, "saldo": 1.0, "estado": "Pendiente", "pdf_path": None, "fecha_creacion": "2024-03-01"},
    ],
    "resumen_conceptos": [
        {"id": 1, "resumen_id": 1, "servicio_id": 1, "concepto": "Hosting", "cantidad": 1.0, "importe": 1500.5,
         "descuento": 10.0, "total": 1490.5, "fecha_inicio": "2024-01-01", "fecha_fin": "2024-01-31"},
        {"id": 2, "resumen_id": 2, "servicio_id": 2, "concepto": "Dominio", "cantidad": 2.0, "importe": 2000.0,
         "descuento": 0.0, "total": 4000.0, "fecha_inicio": "2024-01-01", "fecha_fin": "2024-01-31"},
        {"id": 3, "resumen_id": 2, "servicio_id": None, "concepto": "Ajuste", "cantidad": 1.0, "importe": 0.0,
         "descuento": 0.0, "total": 0.0, "fecha_inicio": None, "fecha_fin": None},
    ],
    "cobros": [
        {"id": 1, "cliente_id": 1, "fecha": "2024-02-05", "importe": 1000.0, "forma_pago": "Efectivo",
         "comprobante": "R-1", "observaciones": None},
        {"id": 2, "cliente_id": 2, "fecha": "2024-02-06", "importe": 4000.0, "forma_pago": "Transferencia",
         "comprobante": "R-2", "observaciones": "ficticio"},
    ],
    "servicio_renovaciones": [
        {"id": 1, "servicio_id": 1, "cliente_id": 1, "fecha_renovacion": "2024-12-31",
         "fecha_inicio_anterior": "2024-01-01", "fecha_fin_anterior": "2024-12-31",
         "fecha_inicio_nueva": "2025-01-01", "fecha_fin_nueva": "2025-12-31",
         "concepto": "Hosting", "descripcion": None, "cantidad": 1.0, "importe": 1500.5,
         "descuento": 10.0, "resumen_id": 1},
    ],
}
ORDEN_SIEMBRA = ("clientes", "servicios", "resumenes", "resumen_conceptos", "cobros", "servicio_renovaciones")
BORRADOS_PARA_SECUENCIA = {"resumenes": 3}


def _memoria():
    conexion = sqlite3.connect(":memory:")
    unittest.addModuleCleanup(conexion.close)
    return conexion


def _historica(nombre, *, con_datos=False):
    conexion = _memoria()
    for _, _, _, sql in ESQUEMAS_HISTORICOS[nombre][2]:
        conexion.execute(sql)
    if con_datos:
        existentes = {f[0] for f in conexion.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        for tabla in ORDEN_SIEMBRA:
            if tabla not in existentes:
                continue
            columnas = {f[1] for f in conexion.execute(f'PRAGMA table_info("{tabla}")')}
            for fila in DATOS[tabla]:
                datos = {k: v for k, v in fila.items() if k in columnas}
                marcadores = ",".join("?" * len(datos))
                conexion.execute(
                    f'INSERT INTO "{tabla}"({",".join(datos)}) VALUES ({marcadores})', tuple(datos.values())
                )
        for tabla, id_borrado in BORRADOS_PARA_SECUENCIA.items():
            if tabla in existentes:
                conexion.execute(f'DELETE FROM "{tabla}" WHERE id=?', (id_borrado,))
    conexion.commit()
    return conexion


def _crear_base(conexion):
    conexion.execute("BEGIN IMMEDIATE")
    database.crear_base(conexion=conexion)
    conexion.commit()


def _actual():
    conexion = _memoria()
    _crear_base(conexion)
    return conexion


def _migrada(nombre, *, con_datos=False):
    conexion = _historica(nombre, con_datos=con_datos)
    _crear_base(conexion)
    return conexion


def _tablas(conexion):
    return {t["nombre"]: t for t in representacion(conexion)["tablas"]}


def _diferencias_por_tabla(a, b):
    """Devuelve {tabla: {clave: (valor_a, valor_b)}} entre dos representaciones."""
    ta, tb = _tablas(a), _tablas(b)
    resultado = {}
    for nombre in sorted(set(ta) | set(tb)):
        if nombre not in ta or nombre not in tb:
            resultado[nombre] = {"presencia": (nombre in ta, nombre in tb)}
            continue
        claves = {k for k in set(ta[nombre]) | set(tb[nombre]) if ta[nombre].get(k) != tb[nombre].get(k)}
        if claves:
            resultado[nombre] = {k: (ta[nombre].get(k), tb[nombre].get(k)) for k in sorted(claves)}
    return resultado


def _columnas_por_nombre(tabla):
    return {c["nombre"]: c for c in tabla["columnas"]}


def _instantanea(conexion):
    nombres = [
        f[0] for f in conexion.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        )
    ]
    tablas = {}
    for nombre in nombres:
        columnas = [f[1] for f in conexion.execute(f'PRAGMA table_info("{nombre}")')]
        seleccion = ", ".join(f'"{c}"' for c in columnas)
        filas = conexion.execute(f'SELECT {seleccion} FROM "{nombre}" ORDER BY rowid').fetchall()
        tablas[nombre] = [dict(zip(columnas, f)) for f in filas]
    secuencias = (
        dict(conexion.execute("SELECT name, seq FROM sqlite_sequence").fetchall())
        if "sqlite_sequence" in {f[0] for f in conexion.execute("SELECT name FROM sqlite_master")}
        else {}
    )
    indices = {
        f[0]: (f[1], f[2])
        for f in conexion.execute("SELECT name, tbl_name, sql FROM sqlite_master WHERE type='index' AND sql IS NOT NULL")
    }
    return {
        "tablas": tablas,
        "secuencias": secuencias,
        "indices": indices,
        "quick_check": conexion.execute("PRAGMA quick_check").fetchall(),
        "foreign_key_check": conexion.execute("PRAGMA foreign_key_check").fetchall(),
        "huella": huella(conexion).huella,
    }


def _comparar_preservacion(antes, despues):
    """Lista de problemas: filas, ids, valores, secuencias o índices que cambiaron."""
    problemas = []
    for tabla, filas in antes["tablas"].items():
        posteriores = despues["tablas"].get(tabla)
        if posteriores is None:
            problemas.append(f"tabla_perdida:{tabla}")
            continue
        if len(posteriores) != len(filas):
            problemas.append(f"cantidad:{tabla}")
            continue
        for previa, posterior in zip(filas, posteriores):
            for columna, valor in previa.items():
                if posterior.get(columna) != valor:
                    problemas.append(f"valor:{tabla}.{columna}:{valor!r}->{posterior.get(columna)!r}")
    for tabla, valor in antes["secuencias"].items():
        if despues["secuencias"].get(tabla) != valor:
            problemas.append(f"secuencia:{tabla}:{valor}->{despues['secuencias'].get(tabla)}")
    for nombre, definicion in antes["indices"].items():
        if despues["indices"].get(nombre) != definicion:
            problemas.append(f"indice:{nombre}")
    return problemas


class _Aislada(unittest.TestCase):
    def setUp(self):
        parche = patch.object(database, "conectar", side_effect=AssertionError("acceso a base real bloqueado"))
        parche.start()
        self.addCleanup(parche.stop)


class DiferenciasDeEstructuraTest(_Aislada):
    def test_historicos_sin_migrar_difieren_del_actual_y_solo_599d0f5_coincide(self):
        actual = huella(_actual()).huella
        for nombre in ESQUEMAS_HISTORICOS:
            with self.subTest(nombre=nombre):
                coincide = huella(_historica(nombre)).huella == actual
                self.assertEqual(coincide, nombre.endswith("599d0f5"))

    def test_9b6a850_solo_difiere_en_clientes_por_tres_columnas_heredadas(self):
        diferencias = _diferencias_por_tabla(_actual(), _migrada(H_9B))
        self.assertEqual(list(diferencias), ["clientes"])
        self.assertEqual(list(diferencias["clientes"]), ["columnas"])
        actuales = _columnas_por_nombre(_tablas(_actual())["clientes"])
        migradas = _columnas_por_nombre(_tablas(_migrada(H_9B))["clientes"])
        self.assertEqual(set(actuales), set(migradas) - {"servicio", "importe", "descuento"})
        self.assertEqual(
            {n: migradas[n] for n in ("servicio", "importe", "descuento")},
            {
                "servicio": {"nombre": "servicio", "tipo": "TEXT", "no_nulo": 0, "defecto": None, "pk": 0},
                "importe": {"nombre": "importe", "tipo": "REAL", "no_nulo": 0, "defecto": None, "pk": 0},
                "descuento": {"nombre": "descuento", "tipo": "REAL", "no_nulo": 0, "defecto": None, "pk": 0},
            },
        )
        for nombre, columna in actuales.items():
            with self.subTest(columna=nombre):
                self.assertEqual(migradas[nombre], columna)

    def test_9b6a850_origen_de_cada_columna_de_clientes(self):
        historica = {f[1] for f in _historica(H_9B).execute("PRAGMA table_info(clientes)")}
        migrada = {f[1] for f in _migrada(H_9B).execute("PRAGMA table_info(clientes)")}
        agregadas = migrada - historica
        self.assertEqual(
            agregadas,
            {"nombre", "nombre_comercial", "tipo_factura", "monotributo_facturacion",
             "modalidad_comprobante", "emisor_habitual", "fecha_modificacion", "emisor_id",
             "emisor_recomendado_id"},
        )
        # servicio/importe/descuento existen desde 9b6a850; ningún CREATE ni ALTER actual los define.
        fuente = (RAIZ / "database.py").read_text(encoding="utf-8")
        inicio = fuente.index("def _inicializar_base")
        for columna in ("servicio", "importe", "descuento"):
            self.assertIn(columna, historica)
            bloque_clientes = fuente[inicio:fuente.index("# TABLA SERVICIOS", inicio)]
            self.assertIsNone(re.search(rf"\b{columna}\b", bloque_clientes), columna)

    def test_8c81526_y_4994dc6_solo_difieren_en_la_clave_foranea_de_resumenes(self):
        for nombre in (H_8C, H_49):
            with self.subTest(nombre=nombre):
                diferencias = _diferencias_por_tabla(_actual(), _migrada(nombre))
                self.assertEqual(list(diferencias), ["resumenes"])
                self.assertEqual(list(diferencias["resumenes"]), ["claves_foraneas"])
                actual_fk, migrada_fk = diferencias["resumenes"]["claves_foraneas"]
                self.assertEqual(len(actual_fk), len(migrada_fk) + 1)
                self.assertIn("emisores_fiscales", json.dumps(actual_fk))
                self.assertNotIn("emisores_fiscales", json.dumps(migrada_fk))

    def test_la_columna_emisor_fiscal_id_existe_pero_se_agrega_sin_references(self):
        for nombre in (H_8C, H_49):
            with self.subTest(nombre=nombre):
                conexion = _migrada(nombre)
                sql = conexion.execute("SELECT sql FROM sqlite_master WHERE name='resumenes'").fetchone()[0]
                self.assertNotIn("emisores_fiscales", sql)
                self.assertIn("emisor_fiscal_id INTEGER", sql)
                columnas = [f[1] for f in conexion.execute("PRAGMA table_info(resumenes)")]
                self.assertEqual(columnas[-8:][0], "emisor_fiscal_id")
        origen = database.agregar_columna_si_falta
        self.assertIn("ADD COLUMN", inspect.getsource(origen))
        self.assertIn('"emisor_fiscal_id": "INTEGER"', (RAIZ / "database.py").read_text(encoding="utf-8"))

    def test_el_orden_fisico_de_columnas_difiere_pero_la_huella_lo_ignora(self):
        actual = [f[1] for f in _actual().execute("PRAGMA table_info(resumenes)")]
        migrada = [f[1] for f in _migrada(H_8C).execute("PRAGMA table_info(resumenes)")]
        self.assertNotEqual(actual, migrada)
        self.assertEqual(sorted(actual), sorted(migrada))


class ConvergenciaDeLosCincoRestantesTest(_Aislada):
    def test_los_demas_historicos_convergen_con_el_actual(self):
        actual = huella(_actual()).huella
        divergentes = {H_9B, H_8C, H_49}
        for nombre in ESQUEMAS_HISTORICOS:
            if nombre in divergentes:
                continue
            with self.subTest(nombre=nombre):
                self.assertEqual(huella(_migrada(nombre)).huella, actual)

    def test_las_huellas_divergentes_no_se_registran_como_equivalentes(self):
        actual = huella(_actual()).huella
        for nombre in (H_9B, H_8C, H_49):
            with self.subTest(nombre=nombre):
                self.assertNotEqual(huella(_migrada(nombre)).huella, actual)
        self.assertEqual(huella(_migrada(H_8C)).huella, huella(_migrada(H_8C)).huella)


class MigracionConDatosFicticiosTest(_Aislada):
    def _verificar(self, nombre, cambios_esperados=()):
        conexion = _historica(nombre, con_datos=True)
        antes = _instantanea(conexion)
        self.assertGreater(sum(len(f) for f in antes["tablas"].values()), 0)
        _crear_base(conexion)
        despues = _instantanea(conexion)
        self.assertEqual(_comparar_preservacion(antes, despues), list(cambios_esperados))
        self.assertEqual(despues["quick_check"], [("ok",)])
        self.assertEqual(despues["foreign_key_check"], [])
        self.assertNotEqual(despues["huella"], antes["huella"])
        return antes, despues

    def test_9b6a850_preserva_filas_ids_valores_secuencias_e_indices(self):
        antes, despues = self._verificar(H_9B)
        self.assertEqual(len(despues["tablas"]["clientes"]), 3)
        self.assertEqual([f["nombre"] for f in despues["tablas"]["clientes"]], ["", "", ""])
        self.assertEqual(
            [(f["servicio"], f["importe"], f["descuento"]) for f in despues["tablas"]["clientes"]],
            [("Hosting", 1500.5, 10.0), ("Dominio", 2000.0, 0.0), (None, None, None)],
        )
        self.assertEqual(despues["secuencias"]["clientes"], 3)

    def test_8c81526_preserva_datos_y_deja_emisor_fiscal_id_nulo(self):
        antes, despues = self._verificar(H_8C)
        self.assertEqual({k: len(v) for k, v in antes["tablas"].items()},
                         {k: len(despues["tablas"][k]) for k in antes["tablas"]})
        self.assertEqual(antes["secuencias"]["resumenes"], 3)
        self.assertEqual(despues["secuencias"]["resumenes"], 3)
        self.assertEqual([f["id"] for f in despues["tablas"]["resumenes"]], [1, 2])
        self.assertEqual([f["emisor_fiscal_id"] for f in despues["tablas"]["resumenes"]], [None, None])
        self.assertEqual([f["estado_facturacion"] for f in despues["tablas"]["resumenes"]], ["Pendiente"] * 2)

    def test_8c81526_asigna_periodos_a_servicios_a_partir_de_la_fecha_actual(self):
        conexion = _migrada(H_8C, con_datos=True)
        filas = conexion.execute(
            "SELECT fecha_inicio, fecha_fin, renovable, estado_periodo FROM servicios ORDER BY id"
        ).fetchall()
        for inicio, fin, renovable, estado in filas:
            self.assertEqual((renovable, estado), (1, "Activo"))
            self.assertGreater(fin, inicio)

    def test_4994dc6_preserva_datos_incluidas_renovaciones(self):
        # crear_base recalcula servicios.estado_periodo según date.today(): cambio intencional del código actual.
        antes, despues = self._verificar(H_49, (
            "valor:servicios.estado_periodo:'Activo'->'Finalizado'",
            "valor:servicios.estado_periodo:'Activo'->'Vencido'",
        ))
        self.assertEqual([s["estado_periodo"] for s in despues["tablas"]["servicios"]],
                         ["Activo", "Finalizado", "Vencido"])
        self.assertEqual(len(despues["tablas"]["servicio_renovaciones"]), 1)
        self.assertEqual(despues["tablas"]["servicio_renovaciones"][0]["resumen_id"], 1)
        self.assertEqual(despues["tablas"]["resumen_conceptos"][0]["total"], 1490.5)
        self.assertEqual(despues["tablas"]["cobros"][1]["importe"], 4000.0)

    def test_las_tablas_nuevas_quedan_vacias_salvo_siembras_conocidas(self):
        for nombre in (H_9B, H_8C, H_49):
            with self.subTest(nombre=nombre):
                conexion = _historica(nombre, con_datos=True)
                previas = {f[0] for f in conexion.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                _crear_base(conexion)
                despues = _instantanea(conexion)
                sembradas = {
                    t: len(f) for t, f in despues["tablas"].items() if t not in previas and f
                }
                actual = _instantanea(_actual())
                esperadas = {t: len(f) for t, f in actual["tablas"].items() if t not in previas and f}
                self.assertEqual(sembradas, esperadas)

    def test_la_migracion_es_idempotente_y_no_cambia_la_huella(self):
        for nombre in (H_9B, H_8C, H_49):
            with self.subTest(nombre=nombre):
                conexion = _migrada(nombre, con_datos=True)
                primera = _instantanea(conexion)
                _crear_base(conexion)
                segunda = _instantanea(conexion)
                self.assertEqual(primera, segunda)


class ConsecuenciasParaLaIntegridadFiscalTest(_Aislada):
    def _huerfano(self, conexion):
        conexion.commit()  # PRAGMA foreign_keys no tiene efecto dentro de una transacción abierta
        conexion.execute("PRAGMA foreign_keys=ON")
        conexion.execute(
            "INSERT INTO resumenes(numero, cliente_id, fecha, fecha_vencimiento, emisor_fiscal_id) "
            "VALUES (9001, 1, '2024-05-01', '2024-05-10', 99999)"
        )

    def test_en_el_esquema_actual_un_emisor_fiscal_inexistente_es_rechazado(self):
        conexion = _actual()
        conexion.execute("INSERT INTO clientes(id, nombre) VALUES (1, 'X')")
        with self.assertRaises(sqlite3.IntegrityError):
            self._huerfano(conexion)

    def test_en_la_migrada_un_emisor_fiscal_inexistente_es_aceptado_y_no_se_detecta(self):
        for nombre in (H_8C, H_49):
            with self.subTest(nombre=nombre):
                conexion = _migrada(nombre, con_datos=True)
                self._huerfano(conexion)
                self.assertEqual(conexion.execute("PRAGMA foreign_key_check").fetchall(), [])
                self.assertEqual(
                    conexion.execute("SELECT COUNT(*) FROM resumenes WHERE emisor_fiscal_id=99999").fetchone()[0], 1
                )

    def test_el_detector_bloquea_las_migradas_por_la_clave_foranea_ausente(self):
        for nombre in (H_8C, H_49):
            with self.subTest(nombre=nombre):
                resultado = database.inspeccionar_estado_base_sqlite(_migrada(nombre))
                self.assertEqual(resultado.estado, "BLOQUEADA")
                self.assertIn(
                    "estructura_incompatible:clave_foranea_incompatible:resumenes.emisor_fiscal_id",
                    resultado.motivos,
                )

    def test_la_migrada_9b6a850_no_queda_bloqueada_por_las_columnas_heredadas(self):
        resultado = database.inspeccionar_estado_base_sqlite(_migrada(H_9B))
        self.assertEqual(resultado.estado, "HISTORICA_SIN_VERSION")

    def test_la_politica_sigue_rechazando_todos_los_estados(self):
        for nombre in (H_9B, H_8C, H_49):
            with self.subTest(nombre=nombre):
                inspeccion = database.inspeccionar_estado_base_sqlite(_migrada(nombre))
                decision = database.evaluar_autorizacion_arranque_sqlite(inspeccion)
                self.assertIs(decision.autorizado, False)
                self.assertEqual(decision.estado, inspeccion.estado)


class AlternativasDeCorreccionTest(_Aislada):
    """Experimentos en memoria; no modifican crear_base ni se aplican a bases reales."""

    def _con_resumenes_y_dependientes(self, nombre=H_49):
        conexion = _migrada(nombre, con_datos=True)
        return conexion

    def test_alter_add_column_con_references_solo_sirve_antes_de_crear_base(self):
        conexion = _historica(H_8C, con_datos=True)
        conexion.execute(
            "ALTER TABLE resumenes ADD COLUMN emisor_fiscal_id INTEGER REFERENCES emisores_fiscales(id)"
        )
        _crear_base(conexion)
        diferencias = _diferencias_por_tabla(_actual(), conexion)
        self.assertEqual(diferencias, {})
        self.assertEqual(huella(conexion).huella, huella(_actual()).huella)
        # En una base ya migrada la columna existe: ALTER no puede añadir la clave foránea.
        migrada = _migrada(H_8C)
        with self.assertRaises(sqlite3.OperationalError):
            migrada.execute(
                "ALTER TABLE resumenes ADD COLUMN emisor_fiscal_id INTEGER REFERENCES emisores_fiscales(id)"
            )

    def test_drop_table_con_foreign_keys_activas_borra_en_cascada_los_conceptos(self):
        conexion = self._con_resumenes_y_dependientes()
        conexion.execute("PRAGMA foreign_keys=ON")
        conexion.execute("BEGIN")
        # Las hijas sin ON DELETE (servicio_renovaciones) hacen fallar el DROP...
        with self.assertRaises(sqlite3.IntegrityError):
            conexion.execute("DROP TABLE resumenes")
        conexion.rollback()
        # ...pero si esas referencias se difieren, la cascada de resumen_conceptos sí se ejecuta.
        conexion.execute("BEGIN")
        conexion.execute("PRAGMA defer_foreign_keys=ON")
        conexion.execute("DROP TABLE resumenes")
        perdidos = conexion.execute("SELECT COUNT(*) FROM resumen_conceptos").fetchone()[0]
        conexion.rollback()
        self.assertEqual(perdidos, 0)
        self.assertEqual(conexion.execute("SELECT COUNT(*) FROM resumen_conceptos").fetchone()[0], 3)

    def test_pragma_foreign_keys_no_se_puede_desactivar_dentro_de_una_transaccion(self):
        conexion = self._con_resumenes_y_dependientes()
        conexion.execute("PRAGMA foreign_keys=ON")
        conexion.execute("BEGIN IMMEDIATE")
        conexion.execute("PRAGMA foreign_keys=OFF")
        self.assertEqual(conexion.execute("PRAGMA foreign_keys").fetchone()[0], 1)
        conexion.rollback()

    def test_renombrar_la_tabla_vieja_reapunta_las_claves_foraneas_hijas(self):
        conexion = self._con_resumenes_y_dependientes()
        conexion.execute("PRAGMA foreign_keys=OFF")
        conexion.execute("ALTER TABLE resumenes RENAME TO resumenes_vieja")
        padres = {
            tabla: {f[2] for f in conexion.execute(f'PRAGMA foreign_key_list("{tabla}")')}
            for tabla in ("resumen_conceptos", "servicio_renovaciones", "factura_arca", "intentos_emision_arca")
        }
        for tabla, referenciados in padres.items():
            with self.subTest(tabla=tabla):
                self.assertIn("resumenes_vieja", referenciados)
                self.assertNotIn("resumenes", referenciados)

    def test_reconstruccion_segura_con_foreign_keys_off_preserva_todo_y_converge(self):
        conexion = self._con_resumenes_y_dependientes(H_8C)
        actual = _actual()
        sql_nueva = actual.execute("SELECT sql FROM sqlite_master WHERE name='resumenes'").fetchone()[0]
        indices = [
            f[0] for f in actual.execute(
                "SELECT sql FROM sqlite_master WHERE type='index' AND tbl_name='resumenes' AND sql IS NOT NULL"
            )
        ]
        antes = _instantanea(conexion)
        secuencia = conexion.execute("SELECT seq FROM sqlite_sequence WHERE name='resumenes'").fetchone()[0]
        columnas = [f[1] for f in conexion.execute("PRAGMA table_info(resumenes)")]
        lista = ", ".join(columnas)

        conexion.execute("PRAGMA foreign_keys=OFF")
        conexion.execute("BEGIN IMMEDIATE")
        conexion.execute(sql_nueva.replace("CREATE TABLE resumenes", "CREATE TABLE resumenes_nueva", 1))
        conexion.execute(f"INSERT INTO resumenes_nueva({lista}) SELECT {lista} FROM resumenes")
        conexion.execute("DROP TABLE resumenes")
        conexion.execute("ALTER TABLE resumenes_nueva RENAME TO resumenes")
        for sql in indices:
            conexion.execute(sql)
        conexion.execute("UPDATE sqlite_sequence SET seq=? WHERE name='resumenes'", (secuencia,))
        self.assertEqual(conexion.execute("PRAGMA foreign_key_check").fetchall(), [])
        conexion.commit()

        despues = _instantanea(conexion)
        self.assertEqual(_comparar_preservacion(antes, despues), [])
        self.assertEqual(despues["quick_check"], [("ok",)])
        self.assertEqual(despues["foreign_key_check"], [])
        hijas = {f[2] for f in conexion.execute("PRAGMA foreign_key_list(resumen_conceptos)")}
        self.assertEqual(hijas, {"resumenes", "servicios"})
        _crear_base(conexion)
        self.assertEqual(_diferencias_por_tabla(_actual(), conexion), {})

    def test_sin_restaurar_sqlite_sequence_la_secuencia_retrocede(self):
        conexion = self._con_resumenes_y_dependientes(H_8C)
        actual = _actual()
        sql_nueva = actual.execute("SELECT sql FROM sqlite_master WHERE name='resumenes'").fetchone()[0]
        columnas = ", ".join(f[1] for f in conexion.execute("PRAGMA table_info(resumenes)"))
        conexion.execute("PRAGMA foreign_keys=OFF")
        conexion.execute("BEGIN IMMEDIATE")
        conexion.execute(sql_nueva.replace("CREATE TABLE resumenes", "CREATE TABLE resumenes_nueva", 1))
        conexion.execute(f"INSERT INTO resumenes_nueva({columnas}) SELECT {columnas} FROM resumenes")
        conexion.execute("DROP TABLE resumenes")
        conexion.execute("ALTER TABLE resumenes_nueva RENAME TO resumenes")
        secuencia = conexion.execute("SELECT seq FROM sqlite_sequence WHERE name='resumenes'").fetchone()[0]
        conexion.rollback()
        self.assertEqual(secuencia, 2)  # antes era 3: se reutilizaría el id 3 de un resumen borrado

    def test_la_reconstruccion_no_puede_ejecutarse_dentro_de_crear_base_con_conexion_externa(self):
        conexion = _historica(H_8C)
        conexion.execute("PRAGMA foreign_keys=ON")
        conexion.execute("BEGIN IMMEDIATE")
        conexion.execute("PRAGMA foreign_keys=OFF")
        self.assertEqual(conexion.execute("PRAGMA foreign_keys").fetchone()[0], 1)
        conexion.rollback()


class OrdenDeColumnasYAccesoPosicionalTest(_Aislada):
    ARCHIVOS = tuple(
        p for carpeta in ("services", "views") for p in (RAIZ / carpeta).rglob("*.py")
    ) + (RAIZ / "database.py",)

    def test_el_codigo_de_produccion_no_usa_select_estrella_sobre_tablas_de_negocio(self):
        patron = re.compile(r"select\s+(\w+\.)?\*", re.IGNORECASE)
        hallazgos = [
            f"{p.name}:{n}"
            for p in self.ARCHIVOS
            for n, linea in enumerate(p.read_text(encoding="utf-8").splitlines(), 1)
            if patron.search(linea)
        ]
        self.assertEqual(hallazgos, ["database.py:%d" % int(hallazgos[0].split(":")[1])])
        self.assertIn("SELECT *, NULL AS ambiente_arca FROM main.", (RAIZ / "database.py").read_text(encoding="utf-8"))

    def test_no_hay_insert_posicional_sin_lista_de_columnas(self):
        patron = re.compile(r"insert\s+(or\s+\w+\s+)?into\s+\w+\s+values", re.IGNORECASE)
        for p in self.ARCHIVOS:
            with self.subTest(archivo=p.name):
                self.assertIsNone(patron.search(p.read_text(encoding="utf-8")))

    def test_la_consulta_de_clientes_es_independiente_del_orden_fisico(self):
        consulta = (
            "SELECT id, codigo, COALESCE(NULLIF(razon_social, ''), nombre) AS razon_social, "
            "cuit, iva, estado FROM clientes ORDER BY id"
        )
        migrada = _migrada(H_9B, con_datos=True).execute(consulta).fetchall()
        actual = _actual()
        actual.execute(
            "INSERT INTO clientes(nombre, codigo, razon_social, cuit, iva, estado) "
            "VALUES ('Alfa Ficticia SA','C001','Alfa Ficticia SA','30-00000000-1','Responsable Inscripto','Activo')"
        )
        self.assertEqual(migrada[0][1:], actual.execute(consulta).fetchall()[0][1:])
        self.assertEqual(len(migrada), 3)


class AislamientoDelDiagnosticoTest(_Aislada):
    def test_conectar_esta_bloqueado_y_no_se_usa_la_ruta_real(self):
        with self.assertRaises(AssertionError):
            database.conectar()
        self.assertEqual(database.DB_NAME, ":memory:")

    def test_la_inspeccion_y_la_huella_no_modifican_datos_ni_esquema(self):
        for nombre in (H_9B, H_8C, H_49):
            with self.subTest(nombre=nombre):
                conexion = _migrada(nombre, con_datos=True)
                antes = _instantanea(conexion)
                database.inspeccionar_estado_base_sqlite(conexion)
                huella(conexion)
                self.assertEqual(_instantanea(conexion), antes)


if __name__ == "__main__":
    unittest.main()
