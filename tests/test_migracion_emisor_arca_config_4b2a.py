import io
import sqlite3
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

import database
from database import crear_tabla_emisor_fiscal_arca_config, migrar_emisor_fiscal_arca_config


class MigracionEmisorArcaConfigTest(unittest.TestCase):
    def setUp(self):
        self.conexion = sqlite3.connect(":memory:")
        self.addCleanup(self.conexion.close)
        self.conexion.execute(
            "CREATE TABLE emisores_fiscales(id INTEGER PRIMARY KEY, razon_social TEXT, "
            "ambiente_arca TEXT, punto_venta TEXT, ruta_certificado TEXT, "
            "ruta_clave_privada TEXT, carpeta_facturas TEXT)"
        )

    def legacy(self, ambiente="Homologación", emisor_id=1, configuracion=None):
        valores = configuracion if configuracion is not None else (
            "00002", "  certificado.crt  ", "clave.key", "C:/carpeta legacy"
        )
        self.conexion.execute(
            "INSERT INTO emisores_fiscales VALUES(?, 'Emisor', ?, ?, ?, ?, ?)",
            (emisor_id, ambiente, *valores),
        )
        return valores

    def migrar(self):
        salida = io.StringIO()
        with redirect_stdout(salida):
            resultado = migrar_emisor_fiscal_arca_config(self.conexion.cursor())
        return resultado, salida.getvalue()

    def hijas(self):
        return self.conexion.execute("SELECT * FROM emisor_fiscal_arca_config ORDER BY id").fetchall()

    def test_creacion_tabla_idempotente_y_fk_declarada(self):
        for _repeticion in range(2):
            crear_tabla_emisor_fiscal_arca_config(self.conexion.cursor())
        columnas = self.conexion.execute("PRAGMA table_info(emisor_fiscal_arca_config)").fetchall()
        self.assertEqual([fila[1] for fila in columnas], [
            "id", "emisor_fiscal_id", "ambiente_arca", "punto_venta", "ruta_certificado",
            "ruta_clave_privada", "carpeta_facturas",
        ])
        self.assertTrue(all(fila[4] is None for fila in columnas))
        fk = self.conexion.execute("PRAGMA foreign_key_list(emisor_fiscal_arca_config)").fetchone()
        self.assertEqual(fk[2:5], ("emisores_fiscales", "emisor_fiscal_id", "id"))

    def test_unique_emisor_ambiente_y_coexistencia_h_p(self):
        self.legacy()
        self.migrar()
        self.conexion.execute(
            "INSERT INTO emisor_fiscal_arca_config(emisor_fiscal_id, ambiente_arca) VALUES(1, 'PRODUCCION')"
        )
        for ambiente in ("HOMOLOGACION", "PRODUCCION"):
            with self.subTest(ambiente=ambiente), self.assertRaises(sqlite3.IntegrityError):
                self.conexion.execute(
                    "INSERT INTO emisor_fiscal_arca_config(emisor_fiscal_id, ambiente_arca) VALUES(1, ?)",
                    (ambiente,),
                )
        self.assertEqual(len(self.hijas()), 2)

    def test_check_solo_canonicos_y_sin_null(self):
        self.legacy()
        self.migrar()
        for invalido in (None, "", "Homologación", "Producción", "QA", "homologacion"):
            with self.subTest(ambiente=invalido), self.assertRaises(sqlite3.IntegrityError):
                self.conexion.execute(
                    "INSERT INTO emisor_fiscal_arca_config(emisor_fiscal_id, ambiente_arca) VALUES(1, ?)",
                    (invalido,),
                )

    def test_migracion_h_solo_crea_h(self):
        valores = self.legacy("Homologación")
        self.migrar()
        self.assertEqual(self.hijas()[0][1:], (1, "HOMOLOGACION", *valores))
        self.assertEqual(len(self.hijas()), 1)

    def test_migracion_p_solo_crea_p(self):
        valores = self.legacy("Producción")
        self.migrar()
        self.assertEqual(self.hijas()[0][1:], (1, "PRODUCCION", *valores))
        self.assertEqual(len(self.hijas()), 1)

    def test_canonicalizacion_alias_sin_cambiar_legacy(self):
        casos = (
            ("Homologación", "HOMOLOGACION"), ("homologacion", "HOMOLOGACION"),
            ("  HOMOLOGACION  ", "HOMOLOGACION"), ("Producción", "PRODUCCION"),
            ("produccion", "PRODUCCION"), (" PRODUCCION ", "PRODUCCION"),
        )
        for emisor_id, (legacy, _canonico) in enumerate(casos, 1):
            self.legacy(legacy, emisor_id)
        antes = self.conexion.execute("SELECT * FROM emisores_fiscales ORDER BY id").fetchall()
        self.migrar()
        self.assertEqual([fila[2] for fila in self.hijas()], [canonico for _, canonico in casos])
        self.assertEqual(self.conexion.execute("SELECT * FROM emisores_fiscales ORDER BY id").fetchall(), antes)

    def test_ambiente_invalido_no_crea_hija_e_informa_sin_datos_sensibles(self):
        casos = (None, "", " ", "QA", "H/P", "secreto.key")
        for emisor_id, invalido in enumerate(casos, 1):
            self.legacy(invalido, emisor_id)
        antes = self.conexion.execute("SELECT * FROM emisores_fiscales ORDER BY id").fetchall()
        resultado, salida = self.migrar()
        self.assertEqual(resultado["invalidas"], len(casos))
        self.assertEqual(self.hijas(), [])
        self.assertIn("ADVERTENCIA", salida)
        self.assertNotIn("secreto.key", salida)
        self.assertNotIn("certificado.crt", salida)
        self.assertEqual(self.conexion.execute("SELECT * FROM emisores_fiscales ORDER BY id").fetchall(), antes)

    def test_repeticion_no_duplica_ni_modifica_hija(self):
        self.legacy()
        primero, _salida = self.migrar()
        antes = self.hijas()
        for _repeticion in range(2):
            resultado, salida = self.migrar()
            self.assertEqual(resultado["identicas"], 1)
            self.assertEqual(resultado["creadas"], 0)
            self.assertEqual(salida, "")
            self.assertEqual(self.hijas(), antes)
        self.assertEqual(primero["creadas"], 1)

    def test_hija_identica_preexistente_no_se_reescribe(self):
        valores = self.legacy()
        crear_tabla_emisor_fiscal_arca_config(self.conexion.cursor())
        self.conexion.execute(
            "INSERT INTO emisor_fiscal_arca_config VALUES(99, 1, 'HOMOLOGACION', ?, ?, ?, ?)", valores
        )
        antes = self.hijas()
        resultado, salida = self.migrar()
        self.assertEqual(resultado["identicas"], 1)
        self.assertEqual(self.hijas(), antes)
        self.assertEqual(salida, "")

    def test_hija_diferente_se_conserva_y_reporta_conflicto_por_cada_campo(self):
        valores = self.legacy()
        crear_tabla_emisor_fiscal_arca_config(self.conexion.cursor())
        legacy_antes = self.conexion.execute("SELECT * FROM emisores_fiscales").fetchall()
        for indice in range(4):
            with self.subTest(campo=indice):
                self.conexion.execute("DELETE FROM emisor_fiscal_arca_config")
                distintos = list(valores)
                distintos[indice] = "valor diferente sensible"
                self.conexion.execute(
                    "INSERT INTO emisor_fiscal_arca_config VALUES(99, 1, 'HOMOLOGACION', ?, ?, ?, ?)", distintos
                )
                antes = self.hijas()
                for _repeticion in range(2):
                    resultado, salida = self.migrar()
                    self.assertEqual(resultado["conflictos"], 1)
                    self.assertIn("conflicto", salida)
                    self.assertIn("emisor fiscal 1, HOMOLOGACION", salida)
                    self.assertNotIn("sensible", salida)
                    self.assertEqual(self.hijas(), antes)
                self.assertEqual(self.conexion.execute("SELECT * FROM emisores_fiscales").fetchall(), legacy_antes)

    def test_tabla_hija_vacia_preexistente_y_valores_null_se_preservan(self):
        self.legacy("PRODUCCION", configuracion=(None, "", None, "  C:/raiz  "))
        crear_tabla_emisor_fiscal_arca_config(self.conexion.cursor())
        self.migrar()
        self.assertEqual(self.hijas()[0][3:], (None, "", None, "  C:/raiz  "))

    def test_no_modifica_otras_tablas_fiscales_ni_legacy(self):
        self.legacy()
        tablas = ("factura_arca", "intentos_emision_arca", "resumenes")
        for tabla in tablas:
            self.conexion.execute(f"CREATE TABLE {tabla}(id INTEGER PRIMARY KEY, evidencia TEXT)")
            self.conexion.execute(f"INSERT INTO {tabla} VALUES(1, 'contexto/snapshot original')")
        antes = {tabla: self.conexion.execute(f"SELECT * FROM {tabla}").fetchall()
                 for tabla in (*tablas, "emisores_fiscales")}
        self.migrar()
        self.migrar()
        for tabla, datos in antes.items():
            self.assertEqual(self.conexion.execute(f"SELECT * FROM {tabla}").fetchall(), datos)

    def test_migracion_no_depende_de_foreign_keys_para_seleccionar_padres(self):
        self.assertEqual(self.conexion.execute("PRAGMA foreign_keys").fetchone()[0], 0)
        self.legacy(emisor_id=7)
        self.migrar()
        self.assertEqual([fila[1] for fila in self.hijas()], [7])

    def test_savepoint_revierte_inserciones_parciales_y_conserva_transaccion_externa(self):
        self.legacy(emisor_id=1)
        self.legacy("Producción", emisor_id=2)
        self.conexion.commit()
        crear_tabla_emisor_fiscal_arca_config(self.conexion.cursor())
        self.conexion.execute(
            "CREATE TRIGGER falla BEFORE INSERT ON emisor_fiscal_arca_config "
            "WHEN NEW.emisor_fiscal_id=2 BEGIN SELECT RAISE(ABORT, 'fallo simulado'); END"
        )
        self.conexion.commit()
        self.conexion.execute("UPDATE emisores_fiscales SET razon_social='Cambio externo' WHERE id=1")
        with self.assertRaises(sqlite3.IntegrityError):
            self.migrar()
        self.assertEqual(self.hijas(), [])
        self.assertTrue(self.conexion.in_transaction)
        self.assertEqual(self.conexion.execute("SELECT razon_social FROM emisores_fiscales WHERE id=1").fetchone()[0], "Cambio externo")
        self.conexion.rollback()
        self.assertEqual(self.conexion.execute("SELECT razon_social FROM emisores_fiscales WHERE id=1").fetchone()[0], "Emisor")

    def test_crear_base_nueva_y_reabrir_preserva_legacy_y_configuracion(self):
        with tempfile.TemporaryDirectory() as carpeta:
            ruta = Path(carpeta) / "nueva.db"
            with patch.object(database, "DB_NAME", str(ruta)):
                database.crear_base()
                conexion = sqlite3.connect(ruta)
                try:
                    padres = conexion.execute("SELECT * FROM emisores_fiscales ORDER BY id").fetchall()
                    hijas = conexion.execute("SELECT * FROM emisor_fiscal_arca_config ORDER BY id").fetchall()
                    self.assertEqual(len(hijas), len(padres))
                    self.assertGreater(len(hijas), 0)
                    self.assertEqual({fila[2] for fila in hijas}, {"HOMOLOGACION"})
                    columnas = {fila[1] for fila in conexion.execute("PRAGMA table_info(emisores_fiscales)")}
                    self.assertTrue({"ambiente_arca", "punto_venta", "ruta_certificado",
                                     "ruta_clave_privada", "carpeta_facturas"}.issubset(columnas))
                finally:
                    conexion.close()
                database.crear_base()
                conexion = sqlite3.connect(ruta)
                try:
                    self.assertEqual(conexion.execute("SELECT * FROM emisores_fiscales ORDER BY id").fetchall(), padres)
                    self.assertEqual(conexion.execute("SELECT * FROM emisor_fiscal_arca_config ORDER BY id").fetchall(), hijas)
                finally:
                    conexion.close()

    def test_emisores_distintos_pueden_tener_el_mismo_ambiente(self):
        self.legacy(emisor_id=1)
        self.legacy(emisor_id=2)
        self.migrar()
        self.assertEqual([fila[1:3] for fila in self.hijas()], [(1, "HOMOLOGACION"), (2, "HOMOLOGACION")])

    def test_hija_opuesta_preexistente_no_se_modifica(self):
        valores = self.legacy()
        crear_tabla_emisor_fiscal_arca_config(self.conexion.cursor())
        self.conexion.execute(
            "INSERT INTO emisor_fiscal_arca_config VALUES(99, 1, 'PRODUCCION', '00009', 'p.crt', 'p.key', 'C:/p')"
        )
        antes = self.hijas()[0]
        resultado, _salida = self.migrar()
        self.assertEqual(resultado["creadas"], 1)
        self.assertEqual(self.hijas()[0], antes)
        self.assertEqual(self.hijas()[1][1:], (1, "HOMOLOGACION", *valores))

    def test_error_revierte_tambien_creacion_de_tabla(self):
        self.conexion.execute("DROP TABLE emisores_fiscales")
        with self.assertRaises(sqlite3.OperationalError):
            self.migrar()
        self.assertIsNone(self.conexion.execute(
            "SELECT name FROM sqlite_master WHERE name='emisor_fiscal_arca_config'"
        ).fetchone())


if __name__ == "__main__":
    unittest.main()