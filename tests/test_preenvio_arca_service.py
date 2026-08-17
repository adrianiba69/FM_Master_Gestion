import unittest
from decimal import Decimal

from services.arca.preenvio_arca_service import PreenvioArcaService
from services.arca.reconciliacion_contracts import EstadoIntentoEmision, SnapshotFiscalEsperado


class IntentosFake:

    def __init__(self, error_crear=None):
        self.error_crear = error_crear
        self.eventos = []
        self.siguiente_id = 1

    def crear_intento(self, snapshot, estado):
        self.eventos.append(("crear", snapshot, estado))
        if self.error_crear:
            raise self.error_crear
        intento_id = self.siguiente_id
        self.siguiente_id += 1
        return intento_id

    def actualizar_estado(self, intento_id, estado, **kwargs):
        self.eventos.append(("estado", intento_id, estado, kwargs))


class PreenvioArcaServiceTest(unittest.TestCase):

    def _snapshot(self, tipo_comprobante=11):
        return SnapshotFiscalEsperado(
            resumen_id=10, cliente_id=20, emisor_fiscal_id=30, emisor_id=40, cuit_emisor="20206871629",
            punto_venta=5, tipo_comprobante=tipo_comprobante, numero_planificado=123, fecha_comprobante="20260816",
            concepto=1, tipo_documento=80, documento_receptor=30712345678, condicion_iva_receptor_id=5,
            importe_total=Decimal("12100.00"), importe_neto=Decimal("12100.00"), importe_iva=Decimal("0.00"),
            importe_exento=Decimal("0.00"), importe_no_gravado=Decimal("0.00"), importe_tributos=Decimal("0.00"),
            moneda="PES", cotizacion=Decimal("1.00"),
        )

    def test_confirma_intento_antes_de_enviar(self):
        intentos = IntentosFake()
        servicio = PreenvioArcaService(intentos)
        orden = []

        def enviar():
            orden.append("enviar")
            self.assertEqual(intentos.eventos[0][0], "crear")
            self.assertEqual(intentos.eventos[1][2], EstadoIntentoEmision.ENVIANDO)
            return {"ok": True, "resultado": "A"}

        resultado = servicio.enviar_una_vez(self._snapshot(), enviar)
        self.assertTrue(resultado.ok)
        self.assertEqual(orden, ["enviar"])
        self.assertEqual(intentos.eventos[2][2], EstadoIntentoEmision.PENDIENTE_RECONCILIAR)

    def test_fallo_al_crear_impide_envio(self):
        intentos = IntentosFake(error_crear=RuntimeError("sqlite sin espacio"))
        servicio = PreenvioArcaService(intentos)
        llamado = []
        resultado = servicio.enviar_una_vez(self._snapshot(), lambda: llamado.append(True))
        self.assertFalse(resultado.ok)
        self.assertEqual(llamado, [])

    def test_timeout_deja_pendiente_y_no_reintenta(self):
        intentos = IntentosFake()
        servicio = PreenvioArcaService(intentos)
        llamadas = []

        def enviar():
            llamadas.append(True)
            raise TimeoutError("timeout")

        resultado = servicio.enviar_una_vez(self._snapshot(), enviar)
        self.assertFalse(resultado.ok)
        self.assertEqual(llamadas, [True])
        self.assertEqual(intentos.eventos[-1][2], EstadoIntentoEmision.PENDIENTE_RECONCILIAR)

    def test_rechazo_explicito_deja_rechazado(self):
        intentos = IntentosFake()
        resultado = PreenvioArcaService(intentos).enviar_una_vez(
            self._snapshot(),
            lambda: {"ok": False, "resultado": "R", "errores": ["Datos inválidos"]},
        )
        self.assertFalse(resultado.ok)
        self.assertEqual(intentos.eventos[-1][2], EstadoIntentoEmision.RECHAZADO)

    def test_factura_a_y_c_comparten_proteccion(self):
        for tipo in (1, 11):
            with self.subTest(tipo_comprobante=tipo):
                intentos = IntentosFake()
                resultado = PreenvioArcaService(intentos).enviar_una_vez(
                    self._snapshot(tipo),
                    lambda: {"ok": True, "resultado": "A"},
                )
                self.assertTrue(resultado.ok)
                self.assertEqual(intentos.eventos[0][1].tipo_comprobante, tipo)


if __name__ == "__main__":
    unittest.main()