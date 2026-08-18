import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

from main import programar_aviso_pendientes_inicio
from services.intento_emision_arca_service import IntentoEmisionArcaService


class AppFake:

    def __init__(self):
        self.callbacks = []

    def after(self, _delay, callback):
        self.callbacks.append(callback)


class AvisoPendientesInicioTest(unittest.TestCase):

    def setUp(self):
        archivo = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        archivo.close()
        self.ruta = Path(archivo.name)
        conexion = sqlite3.connect(self.ruta)
        conexion.execute("CREATE TABLE intentos_emision_arca(estado TEXT NOT NULL)")
        conexion.commit()
        conexion.close()
        self.servicio = IntentoEmisionArcaService(lambda: sqlite3.connect(self.ruta))

    def tearDown(self):
        self.ruta.unlink(missing_ok=True)

    def _ejecutar(self, estados):
        conexion = sqlite3.connect(self.ruta)
        conexion.executemany("INSERT INTO intentos_emision_arca(estado) VALUES(?)", [(estado,) for estado in estados])
        conexion.commit()
        conexion.close()
        app = AppFake()
        dialogo = MagicMock()
        programar_aviso_pendientes_inicio(app, self.servicio, dialogo)
        app.callbacks[0]()
        return app, dialogo

    def test_cero_pendientes_no_avisa(self):
        _, dialogo = self._ejecutar([])
        dialogo.showwarning.assert_not_called()

    def test_pendiente_avisa(self):
        _, dialogo = self._ejecutar(["PENDIENTE_RECONCILIAR"])
        dialogo.showwarning.assert_called_once()
        self.assertIn("Hay 1 emisión", dialogo.showwarning.call_args.args[1])

    def test_enviando_avisa(self):
        _, dialogo = self._ejecutar(["ENVIANDO"])
        dialogo.showwarning.assert_called_once()

    def test_conflicto_avisa_con_advertencia(self):
        _, dialogo = self._ejecutar(["CONFLICTO_MANUAL"])
        mensaje = dialogo.showwarning.call_args.args[1]
        self.assertIn("conflicto", mensaje)

    def test_combinacion_conserva_conteo_total(self):
        _, dialogo = self._ejecutar(["ENVIANDO", "PENDIENTE_RECONCILIAR", "CONFLICTO_MANUAL"])
        mensaje = dialogo.showwarning.call_args.args[1]
        self.assertIn("Hay 3 emisiones", mensaje)
        self.assertIn("conflicto", mensaje)

    def test_error_de_lectura_no_interrumpe(self):
        app = AppFake()
        dialogo = MagicMock()
        servicio = MagicMock()
        servicio.contar_pendientes_reconciliacion.side_effect = OSError("db")
        self.assertTrue(programar_aviso_pendientes_inicio(app, servicio, dialogo))
        app.callbacks[0]()
        dialogo.showwarning.assert_not_called()

    def test_aviso_programado_una_sola_vez(self):
        app = AppFake()
        dialogo = MagicMock()
        servicio = MagicMock()
        servicio.contar_pendientes_reconciliacion.return_value = {"total": 1, "CONFLICTO_MANUAL": 0}
        self.assertTrue(programar_aviso_pendientes_inicio(app, servicio, dialogo))
        self.assertFalse(programar_aviso_pendientes_inicio(app, servicio, dialogo))
        self.assertEqual(len(app.callbacks), 1)
        app.callbacks[0]()
        dialogo.showwarning.assert_called_once()
        servicio.contar_pendientes_reconciliacion.assert_called_once()


if __name__ == "__main__":
    unittest.main()