import io
import sqlite3
import tempfile
import unittest
from contextlib import closing, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from database import crear_tabla_emisor_fiscal_arca_config, migrar_emisor_fiscal_arca_config
from services.arca import ambiente_arca
from services.emisor_fiscal_service import (
    ConfiguracionArcaEmisor,
    ConfiguracionArcaError,
    EmisorFiscalService,
    ResultadoGuardadoConfiguracionArca,
)

COLUMNAS_LEGACY = (
    "id, razon_social, nombre_fantasia, cuit, condicion_iva, tipo_factura, punto_venta, activo, "
    "observaciones, ambiente_arca, domicilio, ingresos_brutos, fecha_inicio_actividades, "
    "ruta_certificado, ruta_clave_privada, carpeta_facturas, configuracion_arca_completa"
)


class EscrituraConfiguracionArcaTest(unittest.TestCase):
    def setUp(self):
        self.temporal = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporal.cleanup)
        self.raiz = Path(self.temporal.name)
        self.base = self.raiz / "config.db"
        # Rutas ficticias inexistentes: la API de escritura no debe tocar el filesystem.
        self.h = ("00002", str(self.raiz / "h" / "cert_h.crt"), str(self.raiz / "h" / "clave_h.key"), str(self.raiz / "h" / "facturas"))
        self.p = ("00009", str(self.raiz / "p" / "cert_p.crt"), str(self.raiz / "p" / "clave_p.key"), str(self.raiz / "p" / "facturas"))
        with closing(sqlite3.connect(self.base)) as conexion:
            conexion.execute(
                "CREATE TABLE emisores_fiscales(id INTEGER PRIMARY KEY, razon_social TEXT NOT NULL DEFAULT '', "
                "nombre_fantasia TEXT, cuit TEXT, condicion_iva TEXT, tipo_factura TEXT, punto_venta TEXT, "
                "activo INTEGER DEFAULT 1, observaciones TEXT, ambiente_arca TEXT DEFAULT 'Homologación', "
                "domicilio TEXT DEFAULT '', ingresos_brutos TEXT DEFAULT '', fecha_inicio_actividades TEXT DEFAULT '', "
                "ruta_certificado TEXT DEFAULT '', ruta_clave_privada TEXT DEFAULT '', carpeta_facturas TEXT DEFAULT '', "
                "configuracion_arca_completa INTEGER DEFAULT 0)"
            )
            conexion.execute(
                f"INSERT INTO emisores_fiscales({COLUMNAS_LEGACY}) VALUES(1,'Emisor Uno','Uno','20-11111111-2',"
                "'Monotributo','Factura C',?,1,'obs','Homologación','Calle 1','IIBB','2020-01-01',?,?,?,1)",
                self.h,
            )
            conexion.execute(
                "INSERT INTO emisores_fiscales(id, razon_social, ambiente_arca) VALUES(2,'Emisor Dos','Homologación')"
            )
            crear_tabla_emisor_fiscal_arca_config(conexion.cursor())
            with redirect_stdout(io.StringIO()):
                migrar_emisor_fiscal_arca_config(conexion.cursor())
            conexion.commit()
        parche = patch("services.emisor_fiscal_service.conectar", side_effect=lambda: sqlite3.connect(self.base))
        self.conectar = parche.start()
        self.addCleanup(parche.stop)
        red = patch("urllib.request.urlopen", side_effect=AssertionError("red prohibida"))
        red.start()
        self.addCleanup(red.stop)

    # -- utilidades --------------------------------------------------------
    def sql(self, consulta, parametros=()):
        with closing(sqlite3.connect(self.base)) as conexion:
            filas = conexion.execute(consulta, parametros).fetchall()
            conexion.commit()
            return filas

    def legacy(self, emisor_id=1):
        return self.sql(f"SELECT {COLUMNAS_LEGACY} FROM emisores_fiscales WHERE id=?", (emisor_id,))[0]

    def espejo(self, emisor_id=1):
        return self.sql(
            "SELECT punto_venta, ruta_certificado, ruta_clave_privada, carpeta_facturas FROM emisores_fiscales WHERE id=?",
            (emisor_id,),
        )[0]

    def hijas(self, emisor_id=None):
        if emisor_id is None:
            return self.sql("SELECT * FROM emisor_fiscal_arca_config ORDER BY id")
        return self.sql("SELECT * FROM emisor_fiscal_arca_config WHERE emisor_fiscal_id=? ORDER BY id", (emisor_id,))

    def hija(self, ambiente, emisor_id=1):
        filas = self.sql(
            "SELECT punto_venta, ruta_certificado, ruta_clave_privada, carpeta_facturas FROM emisor_fiscal_arca_config "
            "WHERE emisor_fiscal_id=? AND ambiente_arca=?",
            (emisor_id, ambiente),
        )
        return filas[0] if filas else None

    def guardar(self, ambiente, valores, emisor_id=1):
        return EmisorFiscalService.guardar_configuracion_arca(emisor_id, ambiente, *valores)

    def assert_codigo(self, codigo, funcion, *argumentos):
        with self.assertRaises(ConfiguracionArcaError) as capturada:
            funcion(*argumentos)
        self.assertEqual(capturada.exception.codigo, codigo)
        self.assertNotIn(str(self.raiz), str(capturada.exception))
        return capturada.exception

    def migrar(self):
        with closing(sqlite3.connect(self.base)) as conexion, redirect_stdout(io.StringIO()) as salida:
            resultado = migrar_emisor_fiscal_arca_config(conexion.cursor())
            conexion.commit()
        return resultado, salida.getvalue()

    # -- creacion / actualizacion -----------------------------------------
    def test_crear_h_y_p_en_emisor_sin_hijas(self):
        self.assertEqual(self.hijas(2), [(2, 2, "HOMOLOGACION", None, "", "", "")])
        self.sql("DELETE FROM emisor_fiscal_arca_config WHERE emisor_fiscal_id=2")
        resultado_h = self.guardar("Homologación", self.h, emisor_id=2)
        resultado_p = self.guardar("produccion", self.p, emisor_id=2)
        self.assertIsInstance(resultado_h, ResultadoGuardadoConfiguracionArca)
        self.assertIsInstance(resultado_h.configuracion, ConfiguracionArcaEmisor)
        self.assertEqual(resultado_h.configuracion.ambiente_arca, "HOMOLOGACION")
        self.assertEqual(resultado_p.configuracion.ambiente_arca, "PRODUCCION")
        self.assertEqual(self.hija("HOMOLOGACION", 2), self.h)
        self.assertEqual(self.hija("PRODUCCION", 2), self.p)
        self.assertEqual(
            EmisorFiscalService.obtener_configuracion_arca(2, "PRODUCCION"), resultado_p.configuracion
        )
        self.assertNotIn(str(self.raiz), repr(resultado_h))

    def test_actualizar_h_no_toca_p_y_viceversa(self):
        self.guardar("PRODUCCION", self.p)
        id_h, id_p = (fila[0] for fila in self.hijas(1))
        nuevo_h = ("00003", "h2.crt", "h2.key", "carpeta_h2")
        self.guardar("HOMOLOGACION", nuevo_h)
        self.assertEqual(self.hija("PRODUCCION"), self.p)
        nuevo_p = ("00010", "p2.crt", "p2.key", "carpeta_p2")
        self.guardar("PRODUCCION", nuevo_p)
        self.assertEqual(self.hija("HOMOLOGACION"), nuevo_h)
        self.assertEqual(self.hija("PRODUCCION"), nuevo_p)
        self.assertEqual([fila[0] for fila in self.hijas(1)], [id_h, id_p])

    # -- espejo legacy -----------------------------------------------------
    def test_h_activo_guardar_h_actualiza_espejo_y_no_toca_otras_columnas(self):
        antes = self.legacy()
        nuevo_h = ("00004", "h3.crt", "h3.key", "carpeta_h3")
        resultado = self.guardar("HOMOLOGACION", nuevo_h)
        self.assertTrue(resultado.espejo_legacy_actualizado)
        despues = self.legacy()
        self.assertEqual(despues[6], "00004")
        self.assertEqual(despues[13:16], nuevo_h[1:])
        self.assertEqual(despues[:6] + despues[7:13] + despues[16:], antes[:6] + antes[7:13] + antes[16:])

    def test_h_activo_guardar_p_no_toca_espejo(self):
        antes = self.legacy()
        resultado = self.guardar("PRODUCCION", self.p)
        self.assertFalse(resultado.espejo_legacy_actualizado)
        self.assertEqual(self.legacy(), antes)

    def test_p_activo_guardar_p_actualiza_espejo_y_guardar_h_no(self):
        self.guardar("PRODUCCION", self.p)
        EmisorFiscalService.cambiar_ambiente_arca_activo(1, "PRODUCCION")
        nuevo_p = ("00011", "p4.crt", "p4.key", "carpeta_p4")
        self.assertTrue(self.guardar("PRODUCCION", nuevo_p).espejo_legacy_actualizado)
        self.assertEqual(self.espejo(), nuevo_p)
        antes = self.legacy()
        resultado = self.guardar("HOMOLOGACION", ("00005", "h5.crt", "h5.key", "carpeta_h5"))
        self.assertFalse(resultado.espejo_legacy_actualizado)
        self.assertEqual(self.legacy(), antes)

    def test_ambiente_legacy_invalido_no_espeja(self):
        self.sql("UPDATE emisores_fiscales SET ambiente_arca='QA' WHERE id=1")
        antes = self.legacy()
        resultado = self.guardar("HOMOLOGACION", ("00006", "x.crt", "x.key", "x"))
        self.assertFalse(resultado.espejo_legacy_actualizado)
        self.assertEqual(self.legacy(), antes)

    # -- cambio de ambiente activo ----------------------------------------
    def test_cambiar_h_a_p_y_p_a_h_copia_exactamente_la_hija(self):
        self.guardar("PRODUCCION", self.p)
        antes = self.legacy()
        configuracion = EmisorFiscalService.cambiar_ambiente_arca_activo(1, "Producción")
        self.assertEqual(configuracion.ambiente_arca, "PRODUCCION")
        despues = self.legacy()
        self.assertEqual(despues[9], "Producción")
        self.assertEqual((despues[6], *despues[13:16]), self.p)
        self.assertEqual(despues[:6] + despues[7:9] + despues[10:13] + despues[16:],
                         antes[:6] + antes[7:9] + antes[10:13] + antes[16:])
        EmisorFiscalService.cambiar_ambiente_arca_activo(1, "HOMOLOGACION")
        despues = self.legacy()
        self.assertEqual(despues[9], "Homologación")
        self.assertEqual((despues[6], *despues[13:16]), self.h)
        self.assertEqual(self.hija("HOMOLOGACION"), self.h)
        self.assertEqual(self.hija("PRODUCCION"), self.p)

    def test_cambiar_a_ambiente_sin_hija_falla_sin_modificar(self):
        antes, hijas_antes = self.legacy(), self.hijas()
        self.assert_codigo("CONFIGURACION_ARCA_NO_ENCONTRADA", EmisorFiscalService.cambiar_ambiente_arca_activo, 1, "PRODUCCION")
        self.assertEqual(self.legacy(), antes)
        self.assertEqual(self.hijas(), hijas_antes)

    # -- entradas invalidas -------------------------------------------------
    def test_ambiente_invalido_falla_sin_conectar(self):
        for ambiente in (None, "", "QA", "H", "secreto.key"):
            with self.subTest(ambiente=ambiente):
                self.conectar.reset_mock()
                self.assert_codigo("AMBIENTE_ARCA_INVALIDO", self.guardar, ambiente, self.h)
                self.assert_codigo("AMBIENTE_ARCA_INVALIDO", EmisorFiscalService.cambiar_ambiente_arca_activo, 1, ambiente)
                self.conectar.assert_not_called()

    def test_emisor_invalido_o_inexistente_falla_sin_escribir(self):
        hijas_antes = self.hijas()
        for emisor_id in (0, -1, True, "x", None, 1.0):
            with self.subTest(emisor_id=emisor_id):
                self.assert_codigo("EMISOR_FISCAL_ID_INVALIDO", self.guardar, "HOMOLOGACION", self.h, emisor_id)
                self.assert_codigo("EMISOR_FISCAL_ID_INVALIDO", EmisorFiscalService.cambiar_ambiente_arca_activo, emisor_id, "HOMOLOGACION")
        self.assert_codigo("EMISOR_FISCAL_NO_ENCONTRADO", self.guardar, "HOMOLOGACION", self.h, 99)
        self.assert_codigo("EMISOR_FISCAL_NO_ENCONTRADO", EmisorFiscalService.cambiar_ambiente_arca_activo, 99, "HOMOLOGACION")
        self.assertEqual(self.hijas(), hijas_antes)

    def test_punto_venta_valido_se_normaliza_a_cinco_digitos(self):
        for entrada, esperado in ((5, "00005"), ("7", "00007"), (" 00012 ", "00012"), (99999, "99999"), ("1", "00001")):
            with self.subTest(entrada=entrada):
                resultado = self.guardar("HOMOLOGACION", (entrada, *self.h[1:]))
                self.assertEqual(resultado.configuracion.punto_venta, esperado)
                self.assertEqual(self.hija("HOMOLOGACION")[0], esperado)
                self.assertEqual(self.espejo()[0], esperado)

    def test_punto_venta_invalido_falla_sin_escribir(self):
        antes, hijas_antes = self.legacy(), self.hijas()
        for entrada in (0, -1, "0", "00000", "-3", "+3", "abc", "1.5", "１２", 100000, 1.0, True, b"5"):
            with self.subTest(entrada=entrada):
                self.assert_codigo("PUNTO_VENTA_INVALIDO", self.guardar, "HOMOLOGACION", (entrada, *self.h[1:]))
        self.assertEqual(self.legacy(), antes)
        self.assertEqual(self.hijas(), hijas_antes)

    def test_punto_venta_vacio_se_guarda_como_incompleto(self):
        for entrada in (None, "", "   "):
            with self.subTest(entrada=entrada):
                resultado = self.guardar("PRODUCCION", (entrada, *self.p[1:]))
                self.assertEqual(resultado.configuracion.punto_venta, "")
                validacion = EmisorFiscalService.validar_configuracion_arca_por_ambiente(1, "PRODUCCION")
                self.assertFalse(validacion.ok)
                self.assertIn("Punto de venta invalido: debe ser un entero positivo.", validacion.errores)

    def test_rutas_incompletas_se_guardan_sin_tocar_filesystem(self):
        resultado = self.guardar("PRODUCCION", ("00009", None, "   ", ""))
        self.assertEqual(self.hija("PRODUCCION"), ("00009", "", "", ""))
        self.assertEqual(resultado.configuracion.ruta_certificado, "")
        resultado = self.guardar("PRODUCCION", ("00009", "  cert.crt  ", Path("clave.key"), "carpeta"))
        self.assertEqual(self.hija("PRODUCCION"), ("00009", "cert.crt", "clave.key", "carpeta"))
        self.assertFalse((self.raiz / "h").exists())
        self.assertFalse((self.raiz / "p").exists())

    def test_ruta_de_tipo_invalido_falla(self):
        for valor in (123, b"cert", "cert\x00.crt"):
            with self.subTest(valor=valor):
                self.assert_codigo("VALOR_CONFIGURACION_INVALIDO", self.guardar, "PRODUCCION", ("00009", valor, "k", "c"))
        self.assertIsNone(self.hija("PRODUCCION"))

    # -- cero fallback -----------------------------------------------------
    def test_cero_fallback_h_p(self):
        self.assert_codigo("CONFIGURACION_ARCA_NO_ENCONTRADA", EmisorFiscalService.obtener_configuracion_arca, 1, "PRODUCCION")
        self.guardar("HOMOLOGACION", ("00003", "h.crt", "h.key", "hc"))
        self.assertIsNone(self.hija("PRODUCCION"))
        self.assert_codigo("CONFIGURACION_ARCA_NO_ENCONTRADA", EmisorFiscalService.obtener_configuracion_arca, 1, "PRODUCCION")
        self.guardar("PRODUCCION", ("", "", "", ""))
        self.assertEqual(self.hija("PRODUCCION"), ("", "", "", ""))
        self.assertEqual(self.hija("HOMOLOGACION"), ("00003", "h.crt", "h.key", "hc"))
        EmisorFiscalService.cambiar_ambiente_arca_activo(1, "PRODUCCION")
        self.assertEqual(self.espejo(), ("", "", "", ""))

    # -- duplicados / corrupcion ------------------------------------------
    def test_duplicado_falla_cerrado_sin_sobrescribir(self):
        self.sql("DROP TABLE emisor_fiscal_arca_config")
        self.sql(
            "CREATE TABLE emisor_fiscal_arca_config(id INTEGER PRIMARY KEY AUTOINCREMENT, emisor_fiscal_id INTEGER, "
            "ambiente_arca TEXT, punto_venta TEXT, ruta_certificado TEXT, ruta_clave_privada TEXT, carpeta_facturas TEXT)"
        )
        for pv in ("00002", "00003"):
            self.sql(
                "INSERT INTO emisor_fiscal_arca_config(emisor_fiscal_id, ambiente_arca, punto_venta, ruta_certificado, "
                "ruta_clave_privada, carpeta_facturas) VALUES(1,'HOMOLOGACION',?,'a','b','c')",
                (pv,),
            )
        antes, hijas_antes = self.legacy(), self.hijas()
        self.assert_codigo("CONFIGURACION_ARCA_AMBIGUA", self.guardar, "HOMOLOGACION", self.h)
        self.assert_codigo("CONFIGURACION_ARCA_AMBIGUA", EmisorFiscalService.cambiar_ambiente_arca_activo, 1, "HOMOLOGACION")
        self.assertEqual(self.legacy(), antes)
        self.assertEqual(self.hijas(), hijas_antes)

    def test_unique_impide_segunda_fila_del_mismo_ambiente(self):
        for _ in range(3):
            self.guardar("PRODUCCION", self.p)
        self.assertEqual(len(self.sql("SELECT id FROM emisor_fiscal_arca_config WHERE emisor_fiscal_id=1 AND ambiente_arca='PRODUCCION'")), 1)

    # -- transaccionalidad -------------------------------------------------
    def test_fallo_en_espejo_legacy_revierte_hija(self):
        self.sql(
            "CREATE TRIGGER falla_legacy BEFORE UPDATE ON emisores_fiscales "
            "BEGIN SELECT RAISE(ABORT, 'fallo simulado C:/secreto'); END"
        )
        antes, hija_antes = self.legacy(), self.hija("HOMOLOGACION")
        error = self.assert_codigo("ESCRITURA_CONFIGURACION_ARCA_FALLIDA", self.guardar, "HOMOLOGACION", ("00008", "n.crt", "n.key", "n"))
        self.assertNotIn("secreto", str(error))
        self.assertEqual(self.hija("HOMOLOGACION"), hija_antes)
        self.assertEqual(self.legacy(), antes)

    def test_fallo_en_hija_no_modifica_legacy(self):
        self.sql(
            "CREATE TRIGGER falla_hija BEFORE UPDATE ON emisor_fiscal_arca_config "
            "BEGIN SELECT RAISE(ABORT, 'fallo simulado'); END"
        )
        antes, hija_antes = self.legacy(), self.hija("HOMOLOGACION")
        self.assert_codigo("ESCRITURA_CONFIGURACION_ARCA_FALLIDA", self.guardar, "HOMOLOGACION", ("00008", "n.crt", "n.key", "n"))
        self.assertEqual(self.legacy(), antes)
        self.assertEqual(self.hija("HOMOLOGACION"), hija_antes)

    def test_fallo_al_cambiar_ambiente_no_modifica_legacy(self):
        self.guardar("PRODUCCION", self.p)
        self.sql(
            "CREATE TRIGGER falla_legacy BEFORE UPDATE ON emisores_fiscales "
            "BEGIN SELECT RAISE(ABORT, 'fallo simulado'); END"
        )
        antes = self.legacy()
        self.assert_codigo("ESCRITURA_CONFIGURACION_ARCA_FALLIDA", EmisorFiscalService.cambiar_ambiente_arca_activo, 1, "PRODUCCION")
        self.assertEqual(self.legacy(), antes)

    # -- migracion de arranque --------------------------------------------
    def test_migracion_posterior_idempotente_y_sin_cruce_h_p(self):
        self.guardar("HOMOLOGACION", ("00003", "h.crt", "h.key", "hc"))
        self.guardar("PRODUCCION", self.p)
        EmisorFiscalService.cambiar_ambiente_arca_activo(1, "PRODUCCION")
        self.guardar("PRODUCCION", ("00012", "p.crt", "p.key", "pc"))
        self.guardar("HOMOLOGACION", ("00004", "h2.crt", "h2.key", "hc2"))
        hijas_antes = self.hijas()
        for _ in range(2):
            resultado, salida = self.migrar()
            self.assertEqual(resultado, {"creadas": 0, "identicas": 2, "invalidas": 0, "conflictos": 0})
            self.assertEqual(salida, "")
            self.assertEqual(self.hijas(), hijas_antes)
        self.assertEqual(self.hija("HOMOLOGACION"), ("00004", "h2.crt", "h2.key", "hc2"))
        self.assertEqual(self.hija("PRODUCCION"), ("00012", "p.crt", "p.key", "pc"))

    def test_migracion_no_crea_hija_del_otro_ambiente(self):
        self.guardar("HOMOLOGACION", ("00003", "h.crt", "h.key", "hc"), emisor_id=2)
        resultado, _salida = self.migrar()
        self.assertEqual(resultado["creadas"], 0)
        self.assertEqual(resultado["conflictos"], 0)
        self.assertIsNone(self.hija("PRODUCCION", 2))
        self.assertIsNone(self.hija("PRODUCCION", 1))

    # -- configuracion_arca_completa / datos fiscales ----------------------
    def test_api_nueva_no_actualiza_configuracion_arca_completa(self):
        self.guardar("PRODUCCION", self.p)
        self.guardar("HOMOLOGACION", ("", "", "", ""))
        EmisorFiscalService.cambiar_ambiente_arca_activo(1, "PRODUCCION")
        self.assertEqual(self.legacy()[16], 1)
        self.assertEqual(self.legacy(2)[16], 0)

    def test_actualizar_datos_fiscales_no_toca_campos_arca(self):
        self.guardar("PRODUCCION", self.p)
        antes, hijas_antes = self.legacy(), self.hijas()
        EmisorFiscalService.actualizar_datos_fiscales(
            1, "Nueva RS", "Nueva NF", "20-22222222-3", "Responsable Inscripto", "Factura A",
            0, "nueva obs", "Calle 2", "IIBB2", "2021-02-02",
        )
        despues = self.legacy()
        self.assertEqual(despues[1:6], ("Nueva RS", "Nueva NF", "20-22222222-3", "Responsable Inscripto", "Factura A"))
        self.assertEqual((despues[7], despues[8], despues[10], despues[11], despues[12]), (0, "nueva obs", "Calle 2", "IIBB2", "2021-02-02"))
        self.assertEqual((despues[6], despues[9], *despues[13:]), (antes[6], antes[9], *antes[13:]))
        self.assertEqual(self.hijas(), hijas_antes)
        self.assert_codigo("EMISOR_FISCAL_NO_ENCONTRADO", EmisorFiscalService.actualizar_datos_fiscales, 99, "X", "", "", "", "")
        self.assert_codigo("EMISOR_FISCAL_ID_INVALIDO", EmisorFiscalService.actualizar_datos_fiscales, 0, "X", "", "", "", "")

    # -- Produccion sigue bloqueada ---------------------------------------
    def test_produccion_activa_no_habilita_emision(self):
        self.guardar("PRODUCCION", self.p)
        EmisorFiscalService.cambiar_ambiente_arca_activo(1, "PRODUCCION")
        ambiente_legacy = self.legacy()[9]
        self.assertEqual(ambiente_arca.normalizar_ambiente_arca(ambiente_legacy), ambiente_arca.AMBIENTE_PRODUCCION)
        with self.assertRaises(ambiente_arca.EmisionProduccionNoHabilitadaError):
            ambiente_arca.asegurar_emision_habilitada(ambiente_legacy)
        self.assertEqual(ambiente_arca.asegurar_emision_habilitada("HOMOLOGACION"), "HOMOLOGACION")


if __name__ == "__main__":
    unittest.main()
