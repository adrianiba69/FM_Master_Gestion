import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import database
from views import servicios


class CatalogoSQLiteExistenteTest(unittest.TestCase):
    def setUp(self):
        temporal = tempfile.TemporaryDirectory()
        self.addCleanup(temporal.cleanup)
        self.raiz = Path(temporal.name)
        self.base = self.raiz / "catalogo con espacios # %.db"
        self.enterContext(patch.object(database, "DB_NAME", str(self.base)))
        # Incluso una regresion a la conexion directa queda confinada al temporal.
        self.enterContext(patch.object(servicios, "DATABASE_PATH", self.base, create=True))
        with closing(sqlite3.connect(self.base)):
            pass
        self.vista = SimpleNamespace(
            _crear_tabla_catalogo_si_falta=lambda: servicios.ServiciosWindow._crear_tabla_catalogo_si_falta(self.vista),
            _seed_catalogo_inicial=lambda: servicios.ServiciosWindow._seed_catalogo_inicial(self.vista),
            formatear_moneda=servicios.ServiciosWindow.formatear_moneda,
            catalogo_cb=Mock(),
            _catalogo_map={},
        )

    def consultar(self, sql):
        with closing(database.conectar()) as conexion:
            return conexion.execute(sql).fetchall()

    def test_crea_tabla_idempotente_con_columnas_y_valores_predeterminados(self):
        self.vista._crear_tabla_catalogo_si_falta()
        self.vista._crear_tabla_catalogo_si_falta()
        columnas = self.consultar("PRAGMA table_info(catalogo_servicios)")
        self.assertEqual(
            [(fila[1], fila[2], fila[3], fila[4], fila[5]) for fila in columnas],
            [
                ("id", "INTEGER", 0, None, 1),
                ("nombre", "TEXT", 1, None, 0),
                ("descripcion", "TEXT", 0, None, 0),
                ("precio", "REAL", 1, "0", 0),
                ("activo", "INTEGER", 0, "1", 0),
            ],
        )

    def test_seed_persiste_los_doce_servicios_sin_duplicarlos(self):
        self.vista._crear_tabla_catalogo_si_falta()
        self.vista._seed_catalogo_inicial()
        antes = self.consultar("SELECT * FROM catalogo_servicios ORDER BY id")
        self.assertEqual(len(antes), 12)
        self.assertEqual(
            [(fila[1], fila[3], fila[4]) for fila in antes],
            [
                ("Publicidad rotativa", 1500.0, 1), ("Auspicio", 2500.0, 1),
                ("Programa radial", 1800.0, 1), ("Streaming", 2200.0, 1),
                ("Facebook", 1600.0, 1), ("Instagram", 1700.0, 1),
                ("Cobertura de eventos", 3000.0, 1),
                ("Producción comercial", 3500.0, 1),
                ("Publicidad política", 4000.0, 1), ("Banner web", 1200.0, 1),
                ("Publicidad especial", 2800.0, 1), ("Otro", 1000.0, 1),
            ],
        )
        self.vista._seed_catalogo_inicial()
        self.assertEqual(self.consultar("SELECT * FROM catalogo_servicios ORDER BY id"), antes)

    def test_catalogo_personalizado_no_se_reemplaza_y_selector_filtra_y_ordena(self):
        self.vista._crear_tabla_catalogo_si_falta()
        with closing(database.conectar()) as conexion:
            conexion.executemany(
                "INSERT INTO catalogo_servicios(nombre, descripcion, precio, activo) VALUES(?,?,?,?)",
                [("Zeta", "Ultimo", 25, 1), ("Alfa", "Primero", 10, 1),
                 ("Oculto", "Inactivo", 99, 0)],
            )
            conexion.commit()
        antes = self.consultar("SELECT * FROM catalogo_servicios ORDER BY id")
        servicios.ServiciosWindow.cargar_catalogo_values(self.vista)
        self.assertEqual(self.consultar("SELECT * FROM catalogo_servicios ORDER BY id"), antes)
        filas = [antes[1], antes[0]]
        valores = [f"{fila[1]} - {self.vista.formatear_moneda(fila[3])}" for fila in filas]
        self.assertEqual(self.vista._catalogo_map, dict(zip(valores, filas)))
        self.vista.catalogo_cb.configure.assert_called_once_with(values=valores)
        self.vista.catalogo_cb.set.assert_called_once_with("")

    def test_cada_apertura_con_base_ausente_falla_sin_crear_archivos(self):
        self.base.unlink()
        for metodo in (
            servicios.ServiciosWindow._crear_tabla_catalogo_si_falta,
            servicios.ServiciosWindow._seed_catalogo_inicial,
            servicios.ServiciosWindow.cargar_catalogo_values,
        ):
            with self.subTest(metodo=metodo.__name__):
                with patch.object(self.vista, "_crear_tabla_catalogo_si_falta"), patch.object(
                    self.vista, "_seed_catalogo_inicial"
                ):
                    with self.assertRaises(sqlite3.OperationalError):
                        metodo(self.vista)
                self.assertEqual(list(self.raiz.iterdir()), [])
        self.vista.catalogo_cb.configure.assert_not_called()

    def test_desaparicion_entre_operaciones_no_recrea_base_ni_actualiza_selector(self):
        for etapa in ("_crear_tabla_catalogo_si_falta", "_seed_catalogo_inicial"):
            with self.subTest(etapa=etapa):
                with closing(sqlite3.connect(self.base)):
                    pass
                original = getattr(self.vista, etapa)

                def ejecutar_y_borrar():
                    original()
                    self.base.unlink()

                with patch.object(self.vista, etapa, side_effect=ejecutar_y_borrar):
                    with self.assertRaises(sqlite3.OperationalError):
                        servicios.ServiciosWindow.cargar_catalogo_values(self.vista)
                self.assertEqual(list(self.raiz.iterdir()), [])
                self.assertEqual(self.vista._catalogo_map, {})
                self.vista.catalogo_cb.configure.assert_not_called()

    def test_commits_y_cierres_incluido_retorno_anticipado(self):
        for metodo, cuenta, commits in (
            ("_crear_tabla_catalogo_si_falta", 0, 1),
            ("_seed_catalogo_inicial", 0, 1),
            ("_seed_catalogo_inicial", 1, 0),
            ("cargar_catalogo_values", 0, 0),
        ):
            with self.subTest(metodo=metodo, cuenta=cuenta):
                conexion = Mock()
                conexion.cursor.return_value.fetchone.return_value = (cuenta,)
                conexion.cursor.return_value.fetchall.return_value = []
                with patch.object(servicios, "conectar", return_value=conexion), patch.object(
                    self.vista, "_crear_tabla_catalogo_si_falta"
                ), patch.object(self.vista, "_seed_catalogo_inicial"):
                    getattr(servicios.ServiciosWindow, metodo)(self.vista)
                self.assertEqual(conexion.commit.call_count, commits)
                conexion.close.assert_called_once_with()
                conexion.rollback.assert_not_called()


class ErrorCatalogoConstructorTest(unittest.TestCase):
    def ejecutar_constructor(self, error=None):
        clase = servicios.ServiciosWindow
        self.enterContext(patch.object(servicios.ctk.CTkToplevel, "__init__", return_value=None))
        self.enterContext(patch.object(servicios.ctk, "IntVar"))
        for nombre in ("title", "geometry", "minsize", "configure", "transient", "grab_set"):
            self.enterContext(patch.object(clase, nombre))
        self.cargar = self.enterContext(patch.object(clase, "cargar_servicios"))
        self.limpiar = self.enterContext(patch.object(clase, "limpiar_formulario"))
        self.enterContext(patch.object(clase, "cargar_catalogo_values", side_effect=error))

        def interfaz(vista):
            for nombre in ("aviso_label", "catalogo_cb", "boton_usar_catalogo", "boton_admin_catalogo"):
                setattr(vista, nombre, Mock())

        self.enterContext(patch.object(clase, "crear_interfaz", autospec=True, side_effect=interfaz))
        return clase(Mock(), 1, "Cliente temporal")

    def test_error_sqlite_visible_sin_dialogos_ni_continuacion_exitosa(self):
        with patch.object(servicios.messagebox, "showerror") as dialogo:
            vista = self.ejecutar_constructor(sqlite3.OperationalError("unable to open database file"))
        aviso = vista.aviso_label.configure.call_args.kwargs
        self.assertIn("No se pudo cargar el catalogo", aviso["text"])
        self.assertIn("unable to open database file", aviso["text"])
        for control in (vista.catalogo_cb, vista.boton_usar_catalogo, vista.boton_admin_catalogo):
            control.configure.assert_called_once_with(state="disabled")
        self.cargar.assert_not_called()
        self.limpiar.assert_not_called()
        dialogo.assert_not_called()

    def test_constructor_sin_error_conserva_carga_normal(self):
        vista = self.ejecutar_constructor()
        self.cargar.assert_called_once_with()
        self.limpiar.assert_called_once_with()
        vista.aviso_label.configure.assert_not_called()

    def test_error_no_sqlite_no_se_oculta(self):
        with self.assertRaisesRegex(ValueError, "fallo no SQLite"):
            self.ejecutar_constructor(ValueError("fallo no SQLite"))
        self.cargar.assert_not_called()
        self.limpiar.assert_not_called()


if __name__ == "__main__":
    unittest.main()
