import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from services.arca.reconciliacion_contracts import EstadoIntentoEmision, ResultadoReconciliacion
from services.arca.reconciliacion_pendientes_service import ReconciliacionPendientesService
from services.facturacion_service import FacturacionService
from services.intento_emision_arca_service import IntentoEmisionArcaService


class ResultadoFake:
    def __init__(self, resultado, recuperado=False):
        self.resultado = resultado
        self.recuperado = recuperado


class ReconciliacionFake:
    def __init__(self, resultados):
        self.resultados = iter(resultados)
        self.llamadas = []

    def reconciliar_intento(self, intento_id):
        self.llamadas.append(intento_id)
        return next(self.resultados)


class ReconciliacionPendientesServiceTest(unittest.TestCase):

    def setUp(self):
        archivo = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        archivo.close()
        self.ruta = archivo.name
        conexion = sqlite3.connect(self.ruta)
        conexion.execute("CREATE TABLE intentos_emision_arca(id INTEGER PRIMARY KEY, resumen_id INTEGER, estado TEXT)")
        conexion.executemany(
            "INSERT INTO intentos_emision_arca VALUES(?,?,?)",
            [(1, 10, "PENDIENTE_RECONCILIAR"), (2, 10, "ENVIANDO"), (3, 11, "CONFLICTO_MANUAL")],
        )
        conexion.commit()
        conexion.close()

    def tearDown(self):
        import os
        if os.path.exists(self.ruta):
            os.remove(self.ruta)

    def test_reconciliar_todos_continua_y_resume_resultados(self):
        intentos = IntentosFake([1, 2, 3])
        reconciliacion = ReconciliacionFake([
            ResultadoFake(ResultadoReconciliacion.AUTORIZADO, True),
            ResultadoFake(ResultadoReconciliacion.CONFLICTO),
            ResultadoFake(ResultadoReconciliacion.CONSULTA_INCIERTA),
        ])
        servicio = ReconciliacionPendientesService(intentos, reconciliacion)
        lote = servicio.reconciliar_todos()
        self.assertEqual((lote.total, lote.reconciliados, lote.conflictos, lote.inciertos, lote.errores), (3, 1, 1, 1, 0))
        self.assertEqual(reconciliacion.llamadas, [1, 2, 3])

    def test_reconciliar_uno_delega_por_id(self):
        intentos = IntentosFake([])
        reconciliacion = ReconciliacionFake([ResultadoFake(ResultadoReconciliacion.AUTORIZADO, True)])
        servicio = ReconciliacionPendientesService(intentos, reconciliacion)
        resultado = servicio.reconciliar_uno(44)
        self.assertEqual(resultado.resultado, ResultadoReconciliacion.AUTORIZADO)
        self.assertEqual(reconciliacion.llamadas, [44])

    def test_sin_pendientes_devuelve_vacio(self):
        servicio = ReconciliacionPendientesService(IntentosFake([]), ReconciliacionFake([]))
        lote = servicio.reconciliar_todos()
        self.assertEqual(lote.total, 0)
        self.assertEqual(lote.detalle, ())

    def test_bloqueo_previene_emitir_antes_de_arca(self):
        resumen = type("Resumen", (), {"id": 10, "estado_facturacion": "Pendiente"})()
        for estado in (
            EstadoIntentoEmision.PENDIENTE_RECONCILIAR.value,
            EstadoIntentoEmision.ENVIANDO.value,
            EstadoIntentoEmision.CONFLICTO_MANUAL.value,
        ):
            with self.subTest(estado=estado):
                intento = type("Intento", (), {"id": 7, "estado": estado})()
                with (
                    patch("services.facturacion_service.ResumenService.obtener", return_value=resumen),
                    patch("services.facturacion_service.IntentoEmisionArcaService.listar_activos_por_resumen", return_value=[intento]),
                    patch("services.facturacion_service.FacturaArcaService.listar_por_resumen") as facturas,
                    patch.object(FacturacionService, "emitir_en_arca") as emitir,
                ):
                    resultado = FacturacionService.emitir_desde_resumen(10)
                self.assertEqual(resultado["etapa"], "resumen_bloqueado")
                self.assertEqual(resultado["datos_modal"]["estado_intento"], estado)
                facturas.assert_not_called()
                emitir.assert_not_called()


class IntentosFake:
    def __init__(self, ids):
        self.ids = ids

    def listar_pendientes_reconciliacion(self):
        return [type("Intento", (), {"id": intento_id})() for intento_id in self.ids]


if __name__ == "__main__":
    unittest.main()