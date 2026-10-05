import sqlite3
import tempfile
import unittest
from contextlib import closing
from dataclasses import FrozenInstanceError
from pathlib import Path
from unittest.mock import patch

from database import crear_tabla_emisor_fiscal_arca_config
from services.emisor_fiscal_service import (
    ConfiguracionArcaEmisor, ConfiguracionArcaError, EmisorFiscalService,
)


class ResolverEmisorArcaTest(unittest.TestCase):
    def setUp(self):
        self.temporal = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporal.cleanup)
        self.raiz = Path(self.temporal.name)
        self.base = self.raiz / "config.db"
        self.certificado = self.raiz / "certificado.crt"
        self.clave = self.raiz / "clave.key"
        self.certificado.write_bytes(b"CERTIFICADO FICTICIO SECRETO")
        self.clave.write_bytes(b"CLAVE FICTICIA SECRETA")
        with closing(sqlite3.connect(self.base)) as conexion:
            conexion.execute(
                "CREATE TABLE emisores_fiscales(id INTEGER PRIMARY KEY, ambiente_arca TEXT, "
                "punto_venta TEXT, ruta_certificado TEXT, ruta_clave_privada TEXT, carpeta_facturas TEXT)"
            )
            conexion.execute(
                "INSERT INTO emisores_fiscales VALUES(1,'Homologación','999',?,?,?)",
                (str(self.certificado), str(self.clave), str(self.raiz)),
            )
            crear_tabla_emisor_fiscal_arca_config(conexion.cursor())
            conexion.commit()
        parche = patch("services.emisor_fiscal_service.conectar", side_effect=lambda: sqlite3.connect(self.base))
        parche.start()
        self.addCleanup(parche.stop)
        red = patch("urllib.request.urlopen", side_effect=AssertionError("red prohibida"))
        self.red = red.start()
        self.addCleanup(red.stop)

    def sql(self, consulta, parametros=()):
        with closing(sqlite3.connect(self.base)) as conexion:
            filas = conexion.execute(consulta, parametros).fetchall()
            conexion.commit()
            return filas

    def hija(self, ambiente="HOMOLOGACION", emisor_id=1, pv="00005"):
        self.sql(
            "INSERT INTO emisor_fiscal_arca_config(emisor_fiscal_id,ambiente_arca,punto_venta,"
            "ruta_certificado,ruta_clave_privada,carpeta_facturas) VALUES(?,?,?,?,?,?)",
            (emisor_id, ambiente, pv, str(self.certificado), str(self.clave), str(self.raiz)),
        )

    def assert_codigo(self, codigo, emisor_id=1, ambiente="HOMOLOGACION"):
        with self.assertRaises(ConfiguracionArcaError) as capturada:
            EmisorFiscalService.obtener_configuracion_arca(emisor_id, ambiente)
        self.assertEqual(capturada.exception.codigo, codigo)
        return capturada.exception

    def test_h_y_p_devuelven_solo_la_configuracion_exacta(self):
        self.hija("HOMOLOGACION", pv="00005")
        self.hija("PRODUCCION", pv="00009")
        for ambiente, pv in (("HOMOLOGACION", "00005"), ("PRODUCCION", "00009")):
            with self.subTest(ambiente=ambiente):
                config = EmisorFiscalService.obtener_configuracion_arca(1, ambiente)
                self.assertIsInstance(config, ConfiguracionArcaEmisor)
                self.assertEqual((config.emisor_fiscal_id, config.ambiente_arca, config.punto_venta), (1, ambiente, pv))
                self.assertEqual(config.ruta_certificado, str(self.certificado))

    def test_alias_se_canonicalizan(self):
        self.hija("HOMOLOGACION")
        self.hija("PRODUCCION")
        for entrada, esperado in ((" Homologación ", "HOMOLOGACION"), ("homologacion", "HOMOLOGACION"),
                                  ("Producción", "PRODUCCION"), (" produccion ", "PRODUCCION")):
            with self.subTest(ambiente=entrada):
                self.assertEqual(EmisorFiscalService.obtener_configuracion_arca(1, entrada).ambiente_arca, esperado)

    def test_estructura_inmutable_y_repr_no_revela_rutas(self):
        self.hija()
        config = EmisorFiscalService.obtener_configuracion_arca(1, "HOMOLOGACION")
        with self.assertRaises(FrozenInstanceError):
            config.punto_venta = "9"
        self.assertNotIn(str(self.raiz), repr(config))

    def test_ambiente_ausente_o_invalido_falla_sin_conectar(self):
        for ambiente in (None, "", "QA", "H/P", "secreto.key"):
            with self.subTest(ambiente=ambiente), patch("services.emisor_fiscal_service.conectar") as conectar:
                error = self.assert_codigo("AMBIENTE_ARCA_INVALIDO", ambiente=ambiente)
                self.assertNotIn("secreto.key", str(error))
                conectar.assert_not_called()

    def test_ambiente_e_id_son_argumentos_obligatorios(self):
        with self.assertRaises(TypeError):
            EmisorFiscalService.obtener_configuracion_arca(1)
        with self.assertRaises(TypeError):
            EmisorFiscalService.validar_configuracion_arca_por_ambiente(1)

    def test_id_invalido_o_emisor_inexistente_falla(self):
        for emisor_id in (None, 0, -1, "x", True, 1.5):
            with self.subTest(emisor_id=emisor_id):
                self.assert_codigo("EMISOR_FISCAL_ID_INVALIDO", emisor_id=emisor_id)
        self.assert_codigo("EMISOR_FISCAL_NO_ENCONTRADO", emisor_id=99)

    def test_h_ausente_no_usa_p_ni_legacy(self):
        self.hija("PRODUCCION")
        self.assert_codigo("CONFIGURACION_ARCA_NO_ENCONTRADA", ambiente="HOMOLOGACION")

    def test_p_ausente_no_usa_h_ni_legacy(self):
        self.hija("HOMOLOGACION")
        self.assert_codigo("CONFIGURACION_ARCA_NO_ENCONTRADA", ambiente="PRODUCCION")

    def test_sin_hijas_no_hay_fallback_a_configuracion_legacy_completa(self):
        for ambiente in ("HOMOLOGACION", "PRODUCCION"):
            with self.subTest(ambiente=ambiente):
                self.assert_codigo("CONFIGURACION_ARCA_NO_ENCONTRADA", ambiente=ambiente)
                resultado = EmisorFiscalService.validar_configuracion_arca_por_ambiente(1, ambiente)
                self.assertFalse(resultado.ok)
                self.assertEqual(resultado.codigo, "CONFIGURACION_ARCA_NO_ENCONTRADA")

    def test_hija_huerfana_no_se_acepta_aunque_fk_este_desactivada(self):
        self.hija(emisor_id=99)
        self.assert_codigo("EMISOR_FISCAL_NO_ENCONTRADO", emisor_id=99)

    def test_tabla_hija_ausente_falla_cerrado_sin_detalles_sql(self):
        self.sql("DROP TABLE emisor_fiscal_arca_config")
        self.assert_codigo("LECTURA_CONFIGURACION_ARCA_FALLIDA")

    def test_duplicados_por_corrupcion_fallan_cerrado(self):
        self.sql("DROP TABLE emisor_fiscal_arca_config")
        self.sql("CREATE TABLE emisor_fiscal_arca_config(id INTEGER PRIMARY KEY,emisor_fiscal_id INTEGER,"
                 "ambiente_arca TEXT,punto_venta TEXT,ruta_certificado TEXT,ruta_clave_privada TEXT,carpeta_facturas TEXT)")
        self.hija()
        self.hija()
        self.assert_codigo("CONFIGURACION_ARCA_AMBIGUA")
        self.assertFalse(EmisorFiscalService.validar_configuracion_arca_por_ambiente(1, "HOMOLOGACION").ok)

    def test_configuracion_valida_offline_y_controles_no_realizados_explicitos(self):
        self.hija()
        self.hija("PRODUCCION")
        for ambiente in ("HOMOLOGACION", "PRODUCCION"):
            resultado = EmisorFiscalService.validar_configuracion_arca_por_ambiente(1, ambiente)
            self.assertTrue(resultado.ok)
            self.assertEqual(resultado.codigo, "VALIDACION_OFFLINE_OK")
            self.assertEqual(resultado.errores, ())
            self.assertTrue(resultado.advertencias)
            self.assertTrue(any("vigencia_certificado" in control for control in resultado.controles_no_realizados))
            self.assertTrue(any("cuit_certificado" in control for control in resultado.controles_no_realizados))
            self.assertTrue(any("correspondencia_certificado_clave" in control for control in resultado.controles_no_realizados))
            self.assertTrue(any("escritura_carpeta" in control for control in resultado.controles_no_realizados))
            self.assertNotIn(str(self.raiz), repr(resultado))

    def test_pv_vacio_cero_negativo_o_no_entero_falla(self):
        self.hija()
        for pv in (None, "", "0", "-1", "abc", "1.5"):
            with self.subTest(pv=pv):
                self.sql("UPDATE emisor_fiscal_arca_config SET punto_venta=?", (pv,))
                resultado = EmisorFiscalService.validar_configuracion_arca_por_ambiente(1, "HOMOLOGACION")
                self.assertFalse(resultado.ok)
                self.assertTrue(any("Punto de venta" in error for error in resultado.errores))

    def test_rutas_certificado_clave_y_carpeta_ausentes_fallan(self):
        self.hija()
        for campo in ("ruta_certificado", "ruta_clave_privada", "carpeta_facturas"):
            for valor in (None, "", " ", str(self.raiz / "no-existe")):
                with self.subTest(campo=campo, valor=valor):
                    self.sql("UPDATE emisor_fiscal_arca_config SET ruta_certificado=?,ruta_clave_privada=?,carpeta_facturas=?",
                             (str(self.certificado), str(self.clave), str(self.raiz)))
                    self.sql(f"UPDATE emisor_fiscal_arca_config SET {campo}=?", (valor,))
                    resultado = EmisorFiscalService.validar_configuracion_arca_por_ambiente(1, "HOMOLOGACION")
                    self.assertFalse(resultado.ok)
                    self.assertTrue(resultado.errores)
                    self.assertNotIn(str(self.raiz), " ".join(resultado.errores))

    def test_archivos_no_legibles_fallan_sin_revelar_excepcion(self):
        self.hija()
        for ruta in (self.certificado, self.clave):
            with self.subTest(archivo=ruta.name):
                abrir_real = open

                def abrir(nombre, *args, **kwargs):
                    if nombre == str(ruta):
                        raise PermissionError("contenido sensible " + str(ruta))
                    return abrir_real(nombre, *args, **kwargs)

                with patch("builtins.open", side_effect=abrir):
                    resultado = EmisorFiscalService.validar_configuracion_arca_por_ambiente(1, "HOMOLOGACION")
                self.assertFalse(resultado.ok)
                self.assertTrue(any("no es legible" in error for error in resultado.errores))
                self.assertNotIn("sensible", " ".join(resultado.errores))

    def test_carpeta_sin_permisos_falla(self):
        self.hija()
        with patch("services.emisor_fiscal_service.os.access", return_value=False):
            resultado = EmisorFiscalService.validar_configuracion_arca_por_ambiente(1, "HOMOLOGACION")
        self.assertFalse(resultado.ok)
        self.assertTrue(any("permisos" in error for error in resultado.errores))

    def test_resolver_y_validador_no_escriben_no_hacen_red_ni_modifican_archivos(self):
        self.hija()
        antes = self.sql("SELECT * FROM emisor_fiscal_arca_config")
        legacy = self.sql("SELECT * FROM emisores_fiscales")
        archivos = {ruta.name: ruta.read_bytes() for ruta in (self.certificado, self.clave)}
        nombres = sorted(ruta.name for ruta in self.raiz.iterdir())
        EmisorFiscalService.obtener_configuracion_arca(1, "HOMOLOGACION")
        EmisorFiscalService.validar_configuracion_arca_por_ambiente(1, "HOMOLOGACION")
        self.red.assert_not_called()
        self.assertEqual(self.sql("SELECT * FROM emisor_fiscal_arca_config"), antes)
        self.assertEqual(self.sql("SELECT * FROM emisores_fiscales"), legacy)
        self.assertEqual({ruta.name: ruta.read_bytes() for ruta in (self.certificado, self.clave)}, archivos)
        self.assertEqual(sorted(ruta.name for ruta in self.raiz.iterdir()), nombres)

    def test_ambiente_corrupto_que_sql_coincide_no_se_acepta_como_canonico(self):
        self.sql("DROP TABLE emisor_fiscal_arca_config")
        self.sql("CREATE TABLE emisor_fiscal_arca_config(id INTEGER PRIMARY KEY,emisor_fiscal_id INTEGER,"
                 "ambiente_arca TEXT COLLATE NOCASE,punto_venta TEXT,ruta_certificado TEXT,"
                 "ruta_clave_privada TEXT,carpeta_facturas TEXT)")
        self.hija("homologacion")
        self.assert_codigo("CONFIGURACION_ARCA_INCOHERENTE")

    def test_ruta_corrupta_tipo_blob_no_se_acepta(self):
        self.hija()
        self.sql("UPDATE emisor_fiscal_arca_config SET ruta_certificado=?", (b"contenido secreto",))
        error = self.assert_codigo("CONFIGURACION_ARCA_INCOHERENTE")
        self.assertNotIn("secreto", str(error))

    def test_validador_informa_id_emisor_y_ambiente_invalidos(self):
        for emisor_id, ambiente, codigo in (
            (99, "HOMOLOGACION", "EMISOR_FISCAL_NO_ENCONTRADO"),
            (1, None, "AMBIENTE_ARCA_INVALIDO"),
            (1, "QA", "AMBIENTE_ARCA_INVALIDO"),
            (None, "HOMOLOGACION", "EMISOR_FISCAL_ID_INVALIDO"),
        ):
            with self.subTest(codigo=codigo):
                resultado = EmisorFiscalService.validar_configuracion_arca_por_ambiente(emisor_id, ambiente)
                self.assertFalse(resultado.ok)
                self.assertEqual(resultado.codigo, codigo)
                self.assertIsNone(resultado.configuracion)

    def test_errores_db_no_revelan_rutas_ni_contenido(self):
        with patch("services.emisor_fiscal_service.conectar",
                   side_effect=sqlite3.OperationalError("detalle secreto " + str(self.raiz))):
            error = self.assert_codigo("LECTURA_CONFIGURACION_ARCA_FALLIDA")
            resultado = EmisorFiscalService.validar_configuracion_arca_por_ambiente(1, "HOMOLOGACION")
        self.assertNotIn("secreto", str(error))
        self.assertNotIn(str(self.raiz), str(error))
        self.assertFalse(resultado.ok)
        self.assertNotIn("secreto", " ".join(resultado.errores))

    def test_configuracion_de_otro_emisor_no_se_utiliza(self):
        self.sql("INSERT INTO emisores_fiscales(id) VALUES(2)")
        self.hija(emisor_id=2)
        self.assert_codigo("CONFIGURACION_ARCA_NO_ENCONTRADA")


if __name__ == "__main__":
    unittest.main()