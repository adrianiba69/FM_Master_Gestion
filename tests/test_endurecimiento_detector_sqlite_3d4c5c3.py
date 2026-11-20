"""Etapa 3D.4C.5C.3: endurecimiento del detector SQLite (integridad y compatibilidad).

Pruebas aisladas: solo bases ficticias temporales o en memoria. No se abren bases
reales, no se ejecuta main.py ni se conecta el detector al arranque. Reutiliza los
DDL históricos congelados de la etapa 3D.4C.5C.2 como referencia independiente del
detector.
"""

import sqlite3
import unittest
from pathlib import Path

from tests.test_compatibilidad_esquemas_historicos_3d4c5c2 import (
    ESQUEMAS_HISTORICOS,
    _BaseFicticia,
    _auxiliares_existentes,
    _estado_fisico,
    _insertar_minimo,
    _sentencias_esquema,
    _sentencias_referencia,
    database,
)

_REFERENCIA = "arca_config_ambiente_599d0f5"
_IDX_CAE = "idx_factura_arca_cae_unico"
_IDX_IDENTIDAD = "idx_factura_arca_identidad_unica"


def _motivos(resultado):
    return " | ".join(resultado.motivos)


class _ConexionFalsa:
    """Conexión ficticia cuyo cursor responde con filas fijas o lanza errores."""

    def __init__(self, respuestas, errores=()):
        self.respuestas = respuestas
        self.errores = tuple(errores)
        self.consultas = []

    def cursor(self):
        return self

    def execute(self, sql, *args):
        self.consultas.append(sql)
        for fragmento in self.errores:
            if fragmento in sql:
                raise sqlite3.OperationalError("fallo ficticio en C:\\ruta\\secreta\\fm_master.db")
        self._filas = self.respuestas.get(sql, [])
        return self

    def fetchone(self):
        return self._filas[0] if self._filas else None

    def fetchall(self):
        return list(self._filas)


class EsquemasHistoricosLegitimosTest(_BaseFicticia):

    def test_ningun_esquema_historico_presenta_incompatibilidades_estructurales(self):
        for nombre in ESQUEMAS_HISTORICOS:
            with self.subTest(esquema=nombre):
                ruta = self.construir(nombre, _sentencias_esquema(nombre))
                resultado = self.inspeccionar(ruta)
                self.assertNotIn("estructura_incompatible", _motivos(resultado))
                self.assertNotIn("integridad_sqlite_fallida", _motivos(resultado))
                self.assertNotIn(resultado.estado, {"ACTUAL", "NUEVA", "VERSION_INCOMPATIBLE"})

    def test_esquema_de_referencia_sigue_siendo_historico_sin_version(self):
        ruta = self.construir("referencia", _sentencias_esquema(_REFERENCIA))
        self.assertEqual(self.inspeccionar(ruta).estado, "HISTORICA_SIN_VERSION")


class ImitacionesYEstructurasTest(_BaseFicticia):

    def _imitacion(self, con_indices):
        referencia = sqlite3.connect(":memory:")
        self.addCleanup(referencia.close)
        for sql in _sentencias_referencia():
            referencia.execute(sql)
        sentencias = []
        for (tabla,) in referencia.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY rowid"
        ).fetchall():
            columnas = [fila[1] for fila in referencia.execute(f'PRAGMA table_info("{tabla}")')]
            sentencias.append(
                f'CREATE TABLE "{tabla}" ('
                + ", ".join('"id" INTEGER PRIMARY KEY' if c == "id" else f'"{c}"' for c in columnas)
                + ")"
            )
        if con_indices:
            sentencias += [s for tipo, _, _, s in ESQUEMAS_HISTORICOS[_REFERENCIA][2] if tipo == "index"]
        return self.construir("imitacion_" + str(con_indices), sentencias)

    def test_imitacion_de_nombres_no_se_acepta_con_ni_sin_indices(self):
        for con_indices in (False, True):
            with self.subTest(con_indices=con_indices):
                resultado = self.inspeccionar(self._imitacion(con_indices))
                self.assertEqual(resultado.estado, "BLOQUEADA")
                self.assertIn("estructura_incompatible:", _motivos(resultado))

    def test_tipos_y_restricciones_incorrectos_bloquean(self):
        casos = (
            ("tipo_cae", (("factura_arca", "cae TEXT", "cae BLOB"),), "columna_tipo_incompatible:factura_arca.cae"),
            (
                "sin_unique",
                (("resumenes", "numero INTEGER NOT NULL UNIQUE", "numero INTEGER NOT NULL"),),
                "restriccion_unica_ausente:resumenes(numero)",
            ),
            (
                "sin_not_null",
                (("resumenes", "numero INTEGER NOT NULL UNIQUE", "numero INTEGER UNIQUE"),),
                "columna_not_null_ausente:resumenes.numero",
            ),
        )
        for nombre, reemplazos, esperado in casos:
            with self.subTest(caso=nombre):
                ruta = self.construir(nombre, _sentencias_referencia(reemplazos=reemplazos))
                resultado = self.inspeccionar(ruta)
                self.assertEqual(resultado.estado, "BLOQUEADA")
                self.assertIn("estructura_incompatible:" + esperado, resultado.motivos)

    def test_indices_fiscales_incorrectos_bloquean(self):
        casos = (
            ("sin_where", f"CREATE UNIQUE INDEX {_IDX_CAE} ON factura_arca(cae)", _IDX_CAE),
            (
                "no_unico",
                f"CREATE INDEX {_IDX_CAE} ON factura_arca(cae) WHERE cae IS NOT NULL",
                _IDX_CAE,
            ),
            ("columnas_ajenas", f"CREATE UNIQUE INDEX {_IDX_IDENTIDAD} ON factura_arca(id)", _IDX_IDENTIDAD),
        )
        for nombre, sql, indice in casos:
            with self.subTest(caso=nombre):
                ruta = self.construir(
                    nombre, _sentencias_referencia(omitir=(indice,)) + (sql,)
                )
                resultado = self.inspeccionar(ruta)
                self.assertEqual(resultado.estado, "BLOQUEADA")
                self.assertIn("estructura_incompatible:indice_fiscal_incompatible:" + indice, resultado.motivos)

    def test_esquema_parcialmente_migrado_sigue_incompleto_sin_autorizar(self):
        ruta = self.construir("parcial", _sentencias_referencia(omitir=(_IDX_CAE,)))
        resultado = self.inspeccionar(ruta)
        self.assertEqual(resultado.estado, "INCOMPLETA")
        self.assertIn("indice:" + _IDX_CAE, resultado.estructuras_pendientes)

    def test_parcialmente_migrado_con_pieza_contradictoria_bloquea(self):
        sentencias = _sentencias_referencia(omitir=("emisor_fiscal_arca_config", _IDX_CAE))
        ruta = self.construir(
            "parcial_contradictorio",
            sentencias + (f"CREATE UNIQUE INDEX {_IDX_CAE} ON factura_arca(cae)",),
        )
        self.assertEqual(self.inspeccionar(ruta).estado, "BLOQUEADA")

    def test_clave_foranea_huerfana_bloquea_sin_exponer_datos(self):
        def datos(conexion):
            _insertar_minimo(conexion, "servicios", {"id": 1, "cliente_id": 987654})

        ruta = self.construir("huerfana", _sentencias_referencia(), datos=datos)
        resultado = self.inspeccionar(ruta)
        self.assertEqual(resultado.estado, "BLOQUEADA")
        self.assertIn("clave_foranea_huerfana:servicios", _motivos(resultado))
        self.assertNotIn("987654", repr(resultado))


class CorrupcionYMarcadoresTest(_BaseFicticia):

    def test_archivos_no_sqlite_o_corruptos_bloquean(self):
        base = self.construir("base", _sentencias_referencia())
        contenido = base.read_bytes()
        rota = bytearray(contenido)
        rota[0:16] = b"NO ES SQLITE !!!"
        paginas = bytearray(contenido)
        for desplazamiento in range(4096, len(paginas), 4096):
            paginas[desplazamiento + 8:desplazamiento + 60] = b"\xa5" * 52
        for nombre, datos in (("texto", b"no es sqlite " * 400), ("cabecera", bytes(rota)), ("paginas", bytes(paginas))):
            with self.subTest(caso=nombre):
                resultado = self.inspeccionar(self.escribir_bytes(nombre, datos))
                self.assertEqual(resultado.estado, "BLOQUEADA")

    def test_corrupcion_sutil_en_pagina_no_leida_la_detecta_quick_check(self):
        ruta = self.construir("sutil", _sentencias_referencia())
        conexion = sqlite3.connect(ruta.as_uri() + "?mode=ro", uri=True)
        try:
            raiz = conexion.execute("SELECT rootpage FROM sqlite_master WHERE name='tareas'").fetchone()[0]
            tamano = conexion.execute("PRAGMA page_size").fetchone()[0]
        finally:
            conexion.close()
        contenido = bytearray(ruta.read_bytes())
        desplazamiento = (raiz - 1) * tamano
        contenido[desplazamiento:desplazamiento + 8] = b"\x0d\x00\x00\x00\x05\xff\xff\x00"
        ruta.write_bytes(bytes(contenido))

        resultado = self.inspeccionar(ruta)

        self.assertEqual(resultado.estado, "BLOQUEADA")
        self.assertIn("integridad_sqlite_fallida", _motivos(resultado))

    def test_marcadores_desconocidos_son_version_incompatible(self):
        casos = {
            "user_version": "PRAGMA user_version=3",
            "application_id": "PRAGMA application_id=1179468372",
            "alembic": "CREATE TABLE alembic_version(v)",
            "mayusculas": "CREATE TABLE SCHEMA_MIGRATIONS(v)",
            "flyway": "CREATE TABLE flyway_schema_history(v)",
            "django": "CREATE TABLE django_migrations(v)",
        }
        for nombre, sql in casos.items():
            with self.subTest(marcador=nombre):
                ruta = self.construir("marcador_" + nombre, _sentencias_referencia() + (sql,))
                self.assertEqual(self.inspeccionar(ruta).estado, "VERSION_INCOMPATIBLE")

    def test_base_vacia_con_application_id_no_es_nueva(self):
        ruta = self.construir("vacia_appid", ("PRAGMA application_id=1234",))
        resultado = self.inspeccionar(ruta, instalacion_nueva_confirmada=True)
        self.assertEqual(resultado.estado, "VERSION_INCOMPATIBLE")


class LecturaYRespuestasInesperadasTest(unittest.TestCase):

    def _inspeccionar(self, respuestas, errores=()):
        conexion = _ConexionFalsa(respuestas, errores)
        resultado = database.inspeccionar_estado_base_sqlite(conexion)
        self.assertFalse(database.evaluar_autorizacion_arranque_sqlite(resultado).autorizado)
        return resultado, conexion

    def test_quick_check_inesperado_bloquea_en_modo_cerrado(self):
        for respuesta in ([], [("ok",), ("ok",)], [("error",)], [(None,)], [("OK ",)], [(1,)]):
            with self.subTest(respuesta=respuesta):
                resultado, _ = self._inspeccionar(
                    {"PRAGMA user_version": [(0,)], "PRAGMA quick_check": respuesta}
                )
                self.assertEqual(resultado.estado, "BLOQUEADA")
                self.assertIn("integridad_sqlite_fallida", _motivos(resultado))

    def test_application_id_inesperado_bloquea(self):
        for respuesta in ([], [("1",)], [(True,)], [(None,)]):
            with self.subTest(respuesta=respuesta):
                resultado, _ = self._inspeccionar({
                    "PRAGMA user_version": [(0,)],
                    "PRAGMA quick_check": [("ok",)],
                    "PRAGMA application_id": respuesta,
                })
                self.assertEqual(resultado.estado, "BLOQUEADA")

    def test_user_version_booleano_o_ausente_bloquea(self):
        for respuesta in ([], [(True,)], [("0",)]):
            with self.subTest(respuesta=respuesta):
                resultado, _ = self._inspeccionar({"PRAGMA user_version": respuesta})
                self.assertEqual(resultado.estado, "BLOQUEADA")

    def test_errores_de_lectura_se_sanitizan(self):
        for pragma in ("PRAGMA user_version", "PRAGMA quick_check", "PRAGMA application_id", "sqlite_master"):
            with self.subTest(fallo=pragma):
                resultado, _ = self._inspeccionar(
                    {
                        "PRAGMA user_version": [(0,)],
                        "PRAGMA quick_check": [("ok",)],
                        "PRAGMA application_id": [(0,)],
                    },
                    errores=(pragma,),
                )
                self.assertEqual(resultado.estado, "BLOQUEADA")
                texto = repr(resultado)
                self.assertNotIn("secreta", texto)
                self.assertNotIn("fm_master.db", texto)
                self.assertNotIn("C:\\", texto)

    def test_error_de_foreign_key_check_no_se_trata_como_limpio(self):
        resultado, conexion = self._inspeccionar(
            {
                "PRAGMA user_version": [(0,)],
                "PRAGMA quick_check": [("ok",)],
                "PRAGMA application_id": [(0,)],
            },
            errores=("foreign_key_check",),
        )
        self.assertEqual(resultado.estado, "BLOQUEADA")
        self.assertTrue(any("foreign_key_check" in c for c in conexion.consultas))

    def test_inspeccion_solo_emite_consultas_de_lectura(self):
        _, conexion = self._inspeccionar({"PRAGMA user_version": [(0,)], "PRAGMA quick_check": [("x",)]})
        for consulta in conexion.consultas:
            self.assertTrue(consulta.lstrip().upper().startswith(("SELECT", "PRAGMA")), consulta)
            self.assertNotIn("=", consulta.split("PRAGMA", 1)[-1] if consulta.upper().startswith("PRAGMA") else "")


class DeleteWalYNoModificacionTest(_BaseFicticia):

    def _datos(self, conexion):
        _insertar_minimo(conexion, "clientes", {"id": 1, "nombre": "Cliente ficticio"})

    def test_delete_no_modifica_archivos_ni_crea_auxiliares(self):
        ruta = self.construir("delete", _sentencias_referencia(), journal="DELETE", datos=self._datos)
        antes = _estado_fisico(ruta)
        resultado = self.inspeccionar(ruta)
        self.assertEqual(_estado_fisico(ruta), antes)
        self.assertEqual(_auxiliares_existentes(ruta), set())
        self.assertEqual(resultado.estado, "HISTORICA_SIN_VERSION")

    def test_wal_cerrada_conserva_el_archivo_principal(self):
        ruta = self.construir("wal", _sentencias_referencia(), journal="WAL", datos=self._datos)
        antes = _estado_fisico(ruta)["principal"]
        resultado = self.inspeccionar(ruta)
        self.assertEqual(_estado_fisico(ruta)["principal"], antes)
        self.assertEqual(resultado.estado, "HISTORICA_SIN_VERSION")

    def test_wal_con_escritor_activo_no_se_altera_y_sigue_siendo_legible(self):
        ruta, escritor = self.construir(
            "wal_activa", _sentencias_referencia(), journal="WAL", datos=self._datos, mantener_abierta=True
        )
        escritor.execute("INSERT INTO clientes (id, nombre) VALUES (2, 'Pendiente en WAL')")
        escritor.commit()
        antes = _estado_fisico(ruta)
        resultado = self.inspeccionar(ruta)
        despues = _estado_fisico(ruta)
        self.assertEqual(despues["principal"], antes["principal"])
        self.assertEqual(despues["-wal"], antes["-wal"])
        self.assertEqual(resultado.estado, "HISTORICA_SIN_VERSION")
        self.assertEqual(escritor.execute("SELECT COUNT(*) FROM clientes").fetchone()[0], 2)

    def test_inspeccion_no_cambia_esquema_ni_datos(self):
        ruta = self.construir("logica", _sentencias_referencia(), datos=self._datos)
        conexion = sqlite3.connect(ruta.as_uri() + "?mode=ro", uri=True)
        self.addCleanup(conexion.close)
        volcado = tuple(conexion.iterdump())
        maestro = conexion.execute("SELECT type, name, sql FROM sqlite_master ORDER BY name").fetchall()
        version = conexion.execute("PRAGMA user_version").fetchone()
        aplicacion = conexion.execute("PRAGMA application_id").fetchone()

        database.inspeccionar_estado_base_sqlite(conexion)

        self.assertEqual(tuple(conexion.iterdump()), volcado)
        self.assertEqual(
            conexion.execute("SELECT type, name, sql FROM sqlite_master ORDER BY name").fetchall(), maestro
        )
        self.assertEqual(conexion.execute("PRAGMA user_version").fetchone(), version)
        self.assertEqual(conexion.execute("PRAGMA application_id").fetchone(), aplicacion)
        self.assertEqual(conexion.total_changes, 0)


class PoliticaSigueRechazandoTodoTest(_BaseFicticia):

    def test_ningun_estado_endurecido_autoriza(self):
        ruta = self.construir("ref", _sentencias_referencia())
        resultados = [
            self.inspeccionar(ruta),
            self.inspeccionar(self.construir("uv", _sentencias_referencia() + ("PRAGMA user_version=9",))),
            self.inspeccionar(self.escribir_bytes("basura", b"x" * 2048)),
            self.inspeccionar(self.construir("nueva"), instalacion_nueva_confirmada=True),
        ]
        self.assertEqual(resultados[-1].estado, "NUEVA")
        for resultado in resultados:
            decision = database.evaluar_autorizacion_arranque_sqlite(resultado)
            self.assertFalse(decision.autorizado)


if __name__ == "__main__":
    unittest.main()
