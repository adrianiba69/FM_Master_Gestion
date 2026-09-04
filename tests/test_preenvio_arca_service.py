import unittest
from decimal import Decimal

from services.arca.contexto_fiscal_service import ContextoFiscalService
from services.arca.preenvio_arca_service import PreenvioArcaService
from services.arca.reconciliacion_contracts import EstadoIntentoEmision, SnapshotFiscalEsperado


class IntentoObtenidoFake:
    def __init__(self, contexto_fiscal_json, contexto_fiscal_version, contexto_fiscal_hash):
        self.contexto_fiscal_json = contexto_fiscal_json
        self.contexto_fiscal_version = contexto_fiscal_version
        self.contexto_fiscal_hash = contexto_fiscal_hash


class IntentosFake:

    def __init__(self, error_crear=None, obtener_forzado="__sin_forzar__", orden=None):
        self.error_crear = error_crear
        self.eventos = []
        self.orden = orden if orden is not None else []
        self.siguiente_id = 1
        self.obtener_forzado = obtener_forzado
        self._contextos_guardados = {}

    def crear_intento(
        self,
        snapshot,
        estado,
        contexto_fiscal_json=None,
        contexto_fiscal_version=None,
        contexto_fiscal_hash=None,
    ):
        self.eventos.append(("crear", snapshot, estado, contexto_fiscal_json, contexto_fiscal_version, contexto_fiscal_hash))
        if self.error_crear:
            raise self.error_crear
        intento_id = self.siguiente_id
        self.siguiente_id += 1
        if contexto_fiscal_json is not None or contexto_fiscal_version is not None or contexto_fiscal_hash is not None:
            self.orden.append("CREAR_INTENTO_CON_CONTEXTO")
            self._contextos_guardados[intento_id] = (
                contexto_fiscal_json,
                contexto_fiscal_version,
                contexto_fiscal_hash,
            )
        else:
            self.orden.append("CREAR_INTENTO")
        return intento_id

    def actualizar_estado(self, intento_id, estado, **kwargs):
        self.eventos.append(("estado", intento_id, estado, kwargs))
        if estado == EstadoIntentoEmision.ENVIANDO:
            self.orden.append("ENVIANDO")

    def guardar_contexto_fiscal_si_ausente(self, intento_id, contexto_fiscal_json, contexto_fiscal_version, contexto_fiscal_hash):
        self.eventos.append(("persistir_contexto", intento_id, contexto_fiscal_json, contexto_fiscal_version, contexto_fiscal_hash))
        self.orden.append("PERSISTIR_CONTEXTO")
        raise AssertionError("La ruta nueva no debe llamar guardar_contexto_fiscal_si_ausente.")

    def obtener(self, intento_id):
        if self.obtener_forzado != "__sin_forzar__":
            return self.obtener_forzado
        datos = self._contextos_guardados.get(intento_id)
        if datos is None:
            return None
        self.orden.append("VERIFICAR_CONTEXTO")
        return IntentoObtenidoFake(*datos)


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

    def _contexto_fiscal(self):
        return {
            "tipo": "contexto_fiscal_arca",
            "version": 1,
            "creado_en": "2026-08-28T12:30:00",
            "ambiente": "HOMOLOGACION",
            "emisor": {"emisor_id": 40, "emisor_fiscal_id": 30, "razon_social": "Emisor SA", "cuit": "20206871629", "punto_venta_num": 5},
            "receptor": {"cliente_id": 20, "razon_social": "Cliente SA", "documento_visible": "30712345678", "tipo_documento_receptor": 80, "documento_receptor": 30712345678},
            "comprobante": {"fecha": "20260816", "fecha_arca": "20260816", "tipo_comprobante_num": 11, "numero_comprobante_planificado": 123},
            "importes": {"total": Decimal("12100.00"), "neto": Decimal("12100.00")},
            "iva": [],
            "items": [{"descripcion": "Servicio", "subtotal": Decimal("12100.00")}],
        }

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

    # --- Orden crítico exigido: VALIDAR_CONTEXTO -> CREAR_INTENTO_CON_CONTEXTO -> VERIFICAR_CONTEXTO -> ENVIANDO -> CALLBACK ---

    def test_orden_critico_validar_crear_verificar_enviando_callback(self):
        orden = ["VALIDAR_CONTEXTO"]
        intentos = IntentosFake(orden=orden)
        servicio = PreenvioArcaService(intentos)

        def enviar_fecae():
            orden.append("CALLBACK")
            return {"ok": True, "resultado": "A"}

        resultado = servicio.enviar_una_vez_con_contexto(self._snapshot(), self._contexto_fiscal(), enviar_fecae)

        self.assertTrue(resultado.ok)
        self.assertEqual(orden, ["VALIDAR_CONTEXTO", "CREAR_INTENTO_CON_CONTEXTO", "VERIFICAR_CONTEXTO", "ENVIANDO", "CALLBACK"])

    def test_ruta_nueva_no_llama_guardar_contexto_fiscal_si_ausente(self):
        orden = []
        intentos = IntentosFake(orden=orden)
        servicio = PreenvioArcaService(intentos)

        resultado = servicio.enviar_una_vez_con_contexto(
            self._snapshot(), self._contexto_fiscal(), lambda: {"ok": True, "resultado": "A"}
        )

        self.assertTrue(resultado.ok)
        self.assertNotIn("PERSISTIR_CONTEXTO", orden)
        self.assertFalse(any(evento[0] == "persistir_contexto" for evento in intentos.eventos))

    def test_contexto_invalido_bloquea_antes_de_crear_intento(self):
        intentos = IntentosFake()
        servicio = PreenvioArcaService(intentos)
        llamado = []

        contexto_invalido = self._contexto_fiscal()
        contexto_invalido["version"] = 99

        resultado = servicio.enviar_una_vez_con_contexto(
            self._snapshot(), contexto_invalido, lambda: llamado.append(True)
        )

        self.assertFalse(resultado.ok)
        self.assertEqual(llamado, [])
        self.assertEqual(intentos.eventos, [])
        self.assertNotIn("ENVIANDO", intentos.orden)

    def test_crear_intento_con_contexto_fallido_no_ejecuta_callback(self):
        intentos = IntentosFake(error_crear=RuntimeError("sqlite sin espacio"))
        servicio = PreenvioArcaService(intentos)
        llamado = []

        resultado = servicio.enviar_una_vez_con_contexto(
            self._snapshot(), self._contexto_fiscal(), lambda: llamado.append(True)
        )

        self.assertFalse(resultado.ok)
        self.assertEqual(llamado, [])
        self.assertNotIn("ENVIANDO", intentos.orden)

    def test_hash_invalido_al_verificar_no_ejecuta_callback(self):
        intentos = IntentosFake(
            obtener_forzado=IntentoObtenidoFake('{"tipo":"contexto_fiscal_arca"}', 1, "0" * 64)
        )
        servicio = PreenvioArcaService(intentos)
        llamado = []

        resultado = servicio.enviar_una_vez_con_contexto(
            self._snapshot(), self._contexto_fiscal(), lambda: llamado.append(True)
        )

        self.assertFalse(resultado.ok)
        self.assertEqual(llamado, [])
        self.assertNotIn("ENVIANDO", intentos.orden)

    def test_contexto_corrupto_al_verificar_no_ejecuta_callback(self):
        intentos = IntentosFake(obtener_forzado=IntentoObtenidoFake(None, None, None))
        servicio = PreenvioArcaService(intentos)
        llamado = []

        resultado = servicio.enviar_una_vez_con_contexto(
            self._snapshot(), self._contexto_fiscal(), lambda: llamado.append(True)
        )

        self.assertFalse(resultado.ok)
        self.assertEqual(llamado, [])
        self.assertNotIn("ENVIANDO", intentos.orden)

    def test_enviando_nunca_aparece_antes_de_contexto_valido(self):
        intentos = IntentosFake()
        servicio = PreenvioArcaService(intentos)
        contexto_invalido = self._contexto_fiscal()
        del contexto_invalido["tipo"]

        def callback_no_debe_llamarse():
            raise AssertionError("El callback FECAESolicitar no debe ejecutarse sin contexto valido.")

        resultado = servicio.enviar_una_vez_con_contexto(self._snapshot(), contexto_invalido, callback_no_debe_llamarse)

        self.assertFalse(resultado.ok)
        self.assertNotIn("ENVIANDO", intentos.orden)
        self.assertEqual(intentos.orden, [])


if __name__ == "__main__":
    unittest.main()