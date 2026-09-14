import os
import sqlite3
import tempfile
import unittest
from decimal import Decimal

from database import crear_tabla_intentos_emision_arca
from services.arca.contexto_fiscal_service import ContextoFiscalService
from services.arca.reconciliacion_contracts import (
    EstadoIntentoEmision,
    ResultadoReconciliacion,
    SnapshotFiscalEsperado,
)
from services.arca.reconciliacion_service import ReconciliacionArcaService
from services.intento_emision_arca_service import IntentoEmisionArcaService
from services.arca.recuperacion_local_service import ResultadoRecuperacionLocal


class EmisorFiscalFake:

    def __init__(self, emisor):
        self.emisor = emisor
        self.ids_consultados = []

    def obtener(self, emisor_id):
        self.ids_consultados.append(emisor_id)
        return self.emisor


class ConsultaArcaFake:

    def __init__(self, respuesta=None, error=None):
        self.respuesta = respuesta
        self.error = error
        self.llamadas = []

    def __call__(self, **kwargs):
        self.llamadas.append(kwargs)
        if self.error:
            raise self.error
        return self.respuesta


class RecuperacionLocalFake:

    def __init__(self, resultado=None, error=None, intentos=None):
        self.resultado = resultado or ResultadoRecuperacionLocal(ResultadoReconciliacion.AUTORIZADO, 88, True)
        self.error = error
        self.intentos = intentos
        self.llamadas = []

    def registrar_factura_recuperada(self, intento, snapshot, consulta):
        self.llamadas.append((intento, snapshot, consulta))
        if self.error:
            raise self.error
        if self.intentos and self.resultado.resultado == ResultadoReconciliacion.AUTORIZADO:
            self.intentos.guardar_resultado_reconciliacion(
                intento.id,
                ResultadoReconciliacion.AUTORIZADO,
                cae=consulta.get("cae"),
                vencimiento_cae=consulta.get("vencimiento_cae"),
                factura_arca_id=self.resultado.factura_arca_id,
            )
        return self.resultado


class ReconciliacionArcaServiceTest(unittest.TestCase):

    def setUp(self):
        archivo_temporal = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        archivo_temporal.close()
        self.ruta_db = archivo_temporal.name
        conexion = sqlite3.connect(self.ruta_db)
        try:
            crear_tabla_intentos_emision_arca(conexion.cursor())
            conexion.commit()
        finally:
            conexion.close()
        self.intentos = IntentoEmisionArcaService(lambda: sqlite3.connect(self.ruta_db))
        self.snapshot = SnapshotFiscalEsperado(
            resumen_id=10, cliente_id=20, emisor_fiscal_id=30, emisor_id=40, cuit_emisor="20206871629",
            punto_venta=5, tipo_comprobante=11, numero_planificado=123, fecha_comprobante="20260816",
            concepto=1, tipo_documento=80, documento_receptor=30712345678, condicion_iva_receptor_id=5,
            importe_total=Decimal("12100.00"), importe_neto=Decimal("12100.00"), importe_iva=Decimal("0.00"),
            importe_exento=Decimal("0.00"), importe_no_gravado=Decimal("0.00"), importe_tributos=Decimal("0.00"),
            moneda="PES", cotizacion=Decimal("1.00"),
        )
        self.emisor = (30, "Emisor", "", "20206871629", "", "", 5, 1, "", "Homologación", "", "", "", "cert.crt", "clave.key", "C:/trabajo", 1)

    def tearDown(self):
        if os.path.exists(self.ruta_db):
            os.remove(self.ruta_db)

    def _consulta_autorizada(self):
        return {
            "ok": True, "resultado": "A", "cuit_emisor": "20206871629", "punto_venta": 5,
            "tipo_comprobante": 11, "numero_comprobante": 123, "fecha_comprobante": "2026-08-16",
            "doc_tipo": 80, "doc_nro": 30712345678, "importe_total": "12100.00",
            "importe_neto": "12100.00", "importe_iva": "0.00", "moneda": "PES", "cotizacion": "1.00",
            "condicion_iva_receptor_id": 5, "cae": "71345678901234", "vencimiento_cae": "20260826",
        }

    def _crear_intento(self, estado=EstadoIntentoEmision.PENDIENTE_RECONCILIAR, con_contexto=True):
        if not con_contexto:
            return self.intentos.crear_intento(self.snapshot, estado)
        contexto = {
            "tipo": "contexto_fiscal_arca", "version": 1, "creado_en": "2026-08-16T10:00:00",
            "ambiente": "HOMOLOGACION",
            "emisor": {
                "emisor_id": 40, "emisor_fiscal_id": 30, "razon_social": "Emisor original",
                "cuit": "20206871629", "condicion_iva": "Monotributo", "punto_venta_num": 5,
            },
            "receptor": {
                "cliente_id": 20, "razon_social": "Cliente original", "documento_visible": "30712345678",
                "condicion_iva": "Consumidor Final", "condicion_iva_receptor_id": 5,
                "tipo_documento_receptor": 80, "documento_receptor": 30712345678,
            },
            "comprobante": {
                "fecha": "2026-08-16", "fecha_arca": "20260816", "concepto": 1,
                "concepto_descripcion": "1 - Productos", "punto_venta_num": 5,
                "tipo_comprobante_num": 11, "tipo_comprobante_texto": "Factura C",
                "numero_comprobante_planificado": 123, "numero_textual_planificado": "00005-00000123",
                "moneda": "PES", "cotizacion": Decimal("1"),
            },
            "importes": {
                "total": Decimal("12100"), "neto": Decimal("12100"), "iva": Decimal("0"),
                "exento": Decimal("0"), "no_gravado": Decimal("0"), "tributos": Decimal("0"),
            },
            "iva": [],
            "items": [{
                "descripcion": "Servicio", "cantidad": Decimal("1"),
                "precio_unitario": Decimal("12100"), "subtotal": Decimal("12100"),
            }],
        }
        validacion = ContextoFiscalService.validar(contexto)
        self.assertTrue(validacion.valido, validacion.errores)
        return self.intentos.crear_intento(
            self.snapshot,
            estado,
            contexto_fiscal_json=validacion.json_canonico,
            contexto_fiscal_version=validacion.version,
            contexto_fiscal_hash=validacion.hash_calculado,
        )

    def _crear_servicio(self, respuesta=None, error=None, emisor=None, recuperacion=None):
        consulta = ConsultaArcaFake(respuesta=respuesta, error=error)
        proveedor = EmisorFiscalFake(self.emisor if emisor is None else emisor)
        recuperacion = recuperacion or RecuperacionLocalFake(intentos=self.intentos)
        servicio = ReconciliacionArcaService(self.intentos, proveedor, consulta, recuperacion)
        return servicio, consulta, proveedor, recuperacion

    def test_reconcilia_coincidencia_y_consulta_con_clave_del_snapshot(self):
        intento_id = self._crear_intento()
        servicio, consulta, _, recuperacion = self._crear_servicio(self._consulta_autorizada())
        resultado = servicio.reconciliar_intento(intento_id)
        intento = self.intentos.obtener(intento_id)
        self.assertTrue(resultado.ok)
        self.assertEqual(resultado.resultado, ResultadoReconciliacion.AUTORIZADO)
        self.assertEqual(intento.estado, EstadoIntentoEmision.RECONCILIADO.value)
        self.assertEqual(intento.cae, "71345678901234")
        self.assertEqual(consulta.llamadas[0]["cuit_emisor"], self.snapshot.cuit_emisor)
        self.assertEqual(consulta.llamadas[0]["numero_comprobante"], self.snapshot.numero_planificado)
        self.assertEqual(len(recuperacion.llamadas), 1)

    def test_conflicto_actualiza_intento_sin_crear_factura(self):
        intento_id = self._crear_intento()
        respuesta = self._consulta_autorizada()
        respuesta["importe_total"] = "12000.00"
        servicio, _, _, recuperacion = self._crear_servicio(respuesta)
        resultado = servicio.reconciliar_intento(intento_id)
        intento = self.intentos.obtener(intento_id)
        self.assertFalse(resultado.ok)
        self.assertEqual(resultado.resultado, ResultadoReconciliacion.CONFLICTO)
        self.assertEqual(intento.estado, EstadoIntentoEmision.CONFLICTO_MANUAL.value)
        self.assertIn("importe_total", intento.error_mensaje)
        self.assertIsNone(intento.factura_arca_id)
        self.assertEqual(recuperacion.llamadas, [])

    def test_respuesta_incompleta_permanece_pendiente(self):
        intento_id = self._crear_intento()
        respuesta = self._consulta_autorizada()
        del respuesta["importe_iva"]
        servicio, _, _, _ = self._crear_servicio(respuesta)
        resultado = servicio.reconciliar_intento(intento_id)
        intento = self.intentos.obtener(intento_id)
        self.assertEqual(resultado.resultado, ResultadoReconciliacion.CONSULTA_INCIERTA)
        self.assertEqual(intento.estado, EstadoIntentoEmision.PENDIENTE_RECONCILIAR.value)
        self.assertIn("Falta importe_iva", intento.error_mensaje)

    def test_falla_de_consulta_permanece_pendiente(self):
        intento_id = self._crear_intento()
        servicio, _, _, _ = self._crear_servicio({"ok": False, "errores": ["Tiempo de espera agotado"]})
        resultado = servicio.reconciliar_intento(intento_id)
        intento = self.intentos.obtener(intento_id)
        self.assertEqual(resultado.resultado, ResultadoReconciliacion.CONSULTA_INCIERTA)
        self.assertEqual(intento.estado, EstadoIntentoEmision.PENDIENTE_RECONCILIAR.value)
        self.assertEqual(intento.error_mensaje, "Tiempo de espera agotado")

    def test_emisor_faltante_no_consulta_y_permanece_pendiente(self):
        intento_id = self._crear_intento()
        consulta = ConsultaArcaFake(respuesta=self._consulta_autorizada())
        servicio = ReconciliacionArcaService(self.intentos, EmisorFiscalFake(None), consulta, RecuperacionLocalFake())
        resultado = servicio.reconciliar_intento(intento_id)
        intento = self.intentos.obtener(intento_id)
        self.assertEqual(resultado.resultado, ResultadoReconciliacion.CONSULTA_INCIERTA)
        self.assertEqual(intento.estado, EstadoIntentoEmision.PENDIENTE_RECONCILIAR.value)
        self.assertEqual(consulta.llamadas, [])

    def test_recuperacion_local_fallida_deja_pendiente(self):
        intento_id = self._crear_intento()
        servicio, _, _, _ = self._crear_servicio(
            self._consulta_autorizada(),
            recuperacion=RecuperacionLocalFake(error=OSError("rollback")),
        )
        resultado = servicio.reconciliar_intento(intento_id)
        intento = self.intentos.obtener(intento_id)
        self.assertEqual(resultado.resultado, ResultadoReconciliacion.CONSULTA_INCIERTA)
        self.assertEqual(intento.estado, EstadoIntentoEmision.PENDIENTE_RECONCILIAR.value)

    def test_intento_reconciliado_no_consulta(self):
        intento_id = self._crear_intento(EstadoIntentoEmision.RECONCILIADO, con_contexto=False)
        conexion = sqlite3.connect(self.ruta_db)
        conexion.execute("UPDATE intentos_emision_arca SET factura_arca_id=88 WHERE id=?", (intento_id,))
        conexion.commit()
        conexion.close()
        servicio, consulta, _, recuperacion = self._crear_servicio(self._consulta_autorizada())
        resultado = servicio.reconciliar_intento(intento_id)
        self.assertTrue(resultado.ok)
        self.assertEqual(consulta.llamadas, [])
        self.assertEqual(recuperacion.llamadas, [])

    def test_conflicto_manual_no_consulta(self):
        intento_id = self._crear_intento(EstadoIntentoEmision.CONFLICTO_MANUAL, con_contexto=False)
        servicio, consulta, _, _ = self._crear_servicio(self._consulta_autorizada())
        resultado = servicio.reconciliar_intento(intento_id)
        self.assertEqual(resultado.resultado, ResultadoReconciliacion.CONFLICTO)
        self.assertEqual(consulta.llamadas, [])

    def test_rechazado_no_consulta(self):
        intento_id = self._crear_intento(EstadoIntentoEmision.RECHAZADO, con_contexto=False)
        servicio, consulta, _, _ = self._crear_servicio(self._consulta_autorizada())
        resultado = servicio.reconciliar_intento(intento_id)
        self.assertEqual(resultado.resultado, ResultadoReconciliacion.CONSULTA_INCIERTA)
        self.assertEqual(consulta.llamadas, [])


if __name__ == "__main__":
    unittest.main()