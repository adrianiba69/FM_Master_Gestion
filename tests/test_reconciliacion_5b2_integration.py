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
from services.arca.recuperacion_local_service import RecuperacionLocalArcaService
from services.arca.snapshot_fiscal_service import CODIGO_VALIDO, validar_integridad_snapshot
from services.intento_emision_arca_service import IntentoEmisionArcaService


class EmisorFiscalFake:

    def __init__(self):
        self.llamadas = []

    def obtener(self, emisor_id):
        self.llamadas.append(emisor_id)
        return (30, "Emisor", "", "20206871629", "", "", 5, 1, "", "Homologacion", "", "", "", "cert.crt", "clave.key", "C:/trabajo", 1)


class ArcaFake:

    def __init__(self, respuesta=None, error=None):
        self.respuesta = respuesta
        self.error = error
        self.consulta_llamadas = []
        self.fecae_llamadas = 0

    def consultar(self, **kwargs):
        self.consulta_llamadas.append(kwargs)
        if self.error:
            raise self.error
        return self.respuesta

    def fe_cae_solicitar(self, *args, **kwargs):
        self.fecae_llamadas += 1
        raise AssertionError("FECAESolicitar no debe ejecutarse durante la reconciliación")


class RecuperacionFake:

    def __init__(self, error=None):
        self.error = error
        self.llamadas = 0

    def registrar_factura_recuperada(self, intento, snapshot, consulta):
        self.llamadas += 1
        if self.error:
            raise self.error
        return type("Resultado", (), {
            "resultado": ResultadoReconciliacion.AUTORIZADO,
            "factura_arca_id": 77,
            "mensaje": "",
        })()


class Reconciliacion5B2IntegrationTest(unittest.TestCase):

    def setUp(self):
        archivo = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        archivo.close()
        self.ruta_db = archivo.name
        conexion = sqlite3.connect(self.ruta_db)
        try:
            cursor = conexion.cursor()
            cursor.executescript(
                """
                CREATE TABLE resumenes(
                    id INTEGER PRIMARY KEY,
                    estado_facturacion TEXT,
                    fecha_facturacion TEXT,
                    cae TEXT,
                    vencimiento_cae TEXT,
                    numero_factura TEXT
                );
                CREATE TABLE factura_arca(
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    cliente_id INTEGER NOT NULL,
                    emisor_id INTEGER NOT NULL,
                    resumen_id INTEGER NOT NULL,
                    fecha TEXT NOT NULL,
                    punto_venta TEXT,
                    tipo_comprobante TEXT,
                    importe_total REAL NOT NULL,
                    estado TEXT NOT NULL,
                    numero_factura TEXT,
                    cae TEXT,
                    vencimiento_cae TEXT,
                    observaciones TEXT,
                    fecha_creacion TEXT,
                    punto_venta_num INTEGER,
                    tipo_comprobante_num INTEGER,
                    numero_comprobante_num INTEGER,
                    tipo_documento_receptor INTEGER,
                    documento_receptor INTEGER,
                    snapshot_fiscal_json TEXT,
                    snapshot_version INTEGER,
                    snapshot_hash TEXT
                );
                """
            )
            crear_tabla_intentos_emision_arca(cursor)
            cursor.execute("INSERT INTO resumenes VALUES(10, 'Pendiente', '', '', '', '')")
            conexion.commit()
        finally:
            conexion.close()

        self.conexion_factory = lambda: sqlite3.connect(self.ruta_db)
        self.intentos = IntentoEmisionArcaService(self.conexion_factory)
        self.recuperacion = RecuperacionLocalArcaService(self.conexion_factory)
        self.snapshot = SnapshotFiscalEsperado(
            resumen_id=10,
            cliente_id=20,
            emisor_fiscal_id=30,
            emisor_id=40,
            cuit_emisor="20206871629",
            punto_venta=5,
            tipo_comprobante=11,
            numero_planificado=123,
            fecha_comprobante="20260817",
            concepto=1,
            tipo_documento=80,
            documento_receptor=30712345678,
            condicion_iva_receptor_id=5,
            importe_total=Decimal("100.00"),
            importe_neto=Decimal("100.00"),
            importe_iva=Decimal("0.00"),
            importe_exento=Decimal("0.00"),
            importe_no_gravado=Decimal("0.00"),
            importe_tributos=Decimal("0.00"),
            moneda="PES",
            cotizacion=Decimal("1.00"),
        )

    def tearDown(self):
        if os.path.exists(self.ruta_db):
            os.remove(self.ruta_db)

    def _consulta_autorizada(self):
        return {
            "ok": True,
            "resultado": "A",
            "cuit_emisor": "20206871629",
            "punto_venta": 5,
            "tipo_comprobante": 11,
            "numero_comprobante": 123,
            "fecha_comprobante": "2026-08-17",
            "doc_tipo": 80,
            "doc_nro": 30712345678,
            "importe_total": "100.00",
            "importe_neto": "100.00",
            "importe_iva": "0.00",
            "moneda": "PES",
            "cotizacion": "1.00",
            "condicion_iva_receptor_id": 5,
            "cae": "86330766550000",
            "vencimiento_cae": "20260827",
        }

    def _crear_intento(self, estado=EstadoIntentoEmision.PENDIENTE_RECONCILIAR):
        contexto = {
            "tipo": "contexto_fiscal_arca", "version": 1, "creado_en": "2026-08-17T10:00:00",
            "ambiente": "HOMOLOGACION",
            "emisor": {
                "emisor_id": 40, "emisor_fiscal_id": 30, "razon_social": "Emisor congelado",
                "nombre_fantasia": "Emisor", "cuit": "20206871629", "condicion_iva": "Monotributo",
                "domicilio": "Domicilio emisor", "ingresos_brutos": "123", "fecha_inicio_actividades": "2020-01-01",
                "punto_venta_num": 5,
            },
            "receptor": {
                "cliente_id": 20, "razon_social": "Cliente congelado", "documento_visible": "30712345678",
                "condicion_iva": "Consumidor Final", "condicion_iva_receptor_id": 5,
                "domicilio": "Domicilio receptor", "tipo_documento_receptor": 80,
                "documento_receptor": 30712345678,
            },
            "comprobante": {
                "fecha": "2026-08-17", "fecha_arca": "20260817", "concepto": 1,
                "concepto_descripcion": "1 - Productos", "punto_venta_num": 5,
                "tipo_comprobante_num": 11, "tipo_comprobante_texto": "Factura C",
                "numero_comprobante_planificado": 123, "numero_textual_planificado": "00005-00000123",
                "periodo_servicio_desde": None, "periodo_servicio_hasta": None, "vencimiento_pago": None,
                "moneda": "PES", "cotizacion": Decimal("1"),
            },
            "importes": {
                "total": Decimal("100"), "neto": Decimal("100"), "iva": Decimal("0"),
                "exento": Decimal("0"), "no_gravado": Decimal("0"), "tributos": Decimal("0"),
            },
            "iva": [],
            "items": [{
                "concepto": "Servicio", "descripcion": "Servicio congelado", "cantidad": Decimal("1"),
                "precio_unitario": Decimal("100"), "subtotal": Decimal("100"),
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

    def _servicio(self, arca, recuperacion=None):
        return ReconciliacionArcaService(
            self.intentos,
            EmisorFiscalFake(),
            arca.consultar,
            self.recuperacion if recuperacion is None else recuperacion,
        )

    def _estado_intento(self, intento_id):
        return self.intentos.obtener(intento_id)

    def _cantidad_facturas(self):
        conexion = sqlite3.connect(self.ruta_db)
        try:
            return conexion.execute("SELECT COUNT(*) FROM factura_arca").fetchone()[0]
        finally:
            conexion.close()

    def test_pendiente_coincide_recupera_y_reconcilia(self):
        intento_id = self._crear_intento()
        arca = ArcaFake(self._consulta_autorizada())
        resultado = self._servicio(arca).reconciliar_intento(intento_id)
        intento = self._estado_intento(intento_id)
        self.assertTrue(resultado.ok)
        self.assertEqual(resultado.resultado, ResultadoReconciliacion.AUTORIZADO)
        self.assertEqual(intento.estado, EstadoIntentoEmision.RECONCILIADO.value)
        self.assertIsNotNone(intento.factura_arca_id)
        self.assertEqual(resultado.factura_arca_id, intento.factura_arca_id)
        conexion = sqlite3.connect(self.ruta_db)
        try:
            factura = conexion.execute(
                "SELECT snapshot_fiscal_json, snapshot_version, snapshot_hash FROM factura_arca WHERE id=?",
                (intento.factura_arca_id,),
            ).fetchone()
            resumen = conexion.execute(
                "SELECT estado_facturacion FROM resumenes WHERE id=10"
            ).fetchone()
        finally:
            conexion.close()
        integridad = validar_integridad_snapshot(*factura)
        self.assertEqual(integridad.codigo, CODIGO_VALIDO)
        self.assertEqual(integridad.snapshot["fuente"], "recuperacion")
        self.assertEqual(integridad.snapshot["receptor"]["razon_social"], "Cliente congelado")
        self.assertEqual(resumen[0], "Facturado")

    def test_contexto_persistido_prevalece_sobre_columnas_parciales_mutadas(self):
        intento_id = self._crear_intento()
        conexion = sqlite3.connect(self.ruta_db)
        conexion.execute(
            "UPDATE intentos_emision_arca SET importe_total='999.00' WHERE id=?",
            (intento_id,),
        )
        conexion.commit()
        conexion.close()

        resultado = self._servicio(ArcaFake(self._consulta_autorizada())).reconciliar_intento(intento_id)

        self.assertTrue(resultado.ok)
        self.assertEqual(resultado.resultado, ResultadoReconciliacion.AUTORIZADO)
        self.assertEqual(self._estado_intento(intento_id).estado, EstadoIntentoEmision.RECONCILIADO.value)

    def test_recuperacion_lanza_excepcion_deja_pendiente(self):
        intento_id = self._crear_intento()
        arca = ArcaFake(self._consulta_autorizada())
        resultado = self._servicio(arca, RecuperacionFake(error=OSError("rollback"))).reconciliar_intento(intento_id)
        self.assertEqual(resultado.resultado, ResultadoReconciliacion.CONSULTA_INCIERTA)
        self.assertEqual(self._estado_intento(intento_id).estado, EstadoIntentoEmision.PENDIENTE_RECONCILIAR.value)

    def test_conflicto_importe_no_llama_recuperacion(self):
        intento_id = self._crear_intento()
        consulta = self._consulta_autorizada()
        consulta["importe_total"] = "101.00"
        arca = ArcaFake(consulta)
        recuperacion = RecuperacionFake()
        resultado = self._servicio(arca, recuperacion).reconciliar_intento(intento_id)
        self.assertEqual(resultado.resultado, ResultadoReconciliacion.CONFLICTO)
        self.assertEqual(self._estado_intento(intento_id).estado, EstadoIntentoEmision.CONFLICTO_MANUAL.value)
        self.assertEqual(recuperacion.llamadas, 0)

    def test_consulta_incompleta_no_llama_recuperacion(self):
        intento_id = self._crear_intento()
        consulta = self._consulta_autorizada()
        del consulta["importe_iva"]
        arca = ArcaFake(consulta)
        recuperacion = RecuperacionFake()
        resultado = self._servicio(arca, recuperacion).reconciliar_intento(intento_id)
        self.assertEqual(resultado.resultado, ResultadoReconciliacion.CONSULTA_INCIERTA)
        self.assertEqual(self._estado_intento(intento_id).estado, EstadoIntentoEmision.PENDIENTE_RECONCILIAR.value)
        self.assertEqual(recuperacion.llamadas, 0)

    def test_intento_reconciliado_no_consulta_ni_recupera(self):
        intento_id = self._crear_intento()
        self.recuperacion.registrar_factura_recuperada(self._estado_intento(intento_id), self.snapshot, self._consulta_autorizada())
        arca = ArcaFake(self._consulta_autorizada())
        recuperacion = RecuperacionFake()
        resultado = self._servicio(arca, recuperacion).reconciliar_intento(intento_id)
        self.assertTrue(resultado.ok)
        self.assertEqual(arca.consulta_llamadas, [])
        self.assertEqual(recuperacion.llamadas, 0)

    def test_dos_reconciliaciones_conservan_una_factura(self):
        intento_id = self._crear_intento()
        arca = ArcaFake(self._consulta_autorizada())
        servicio = self._servicio(arca)
        primero = servicio.reconciliar_intento(intento_id)
        segundo = servicio.reconciliar_intento(intento_id)
        self.assertEqual(primero.factura_arca_id, segundo.factura_arca_id)
        self.assertEqual(self._cantidad_facturas(), 1)
        self.assertGreaterEqual(len(arca.consulta_llamadas), 1)

    def test_reconciliacion_no_tiene_llamada_fecae(self):
        intento_id = self._crear_intento()
        arca = ArcaFake(self._consulta_autorizada())
        resultado = self._servicio(arca).reconciliar_intento(intento_id)
        self.assertTrue(resultado.ok)
        self.assertEqual(arca.fecae_llamadas, 0)
        self.assertEqual(len(arca.consulta_llamadas), 1)


if __name__ == "__main__":
    unittest.main()
