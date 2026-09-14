import os
import json
import sqlite3
import tempfile
import unittest
from dataclasses import replace
from decimal import Decimal

from database import crear_tabla_intentos_emision_arca
from services.arca.contexto_fiscal_service import ContextoFiscalService
from services.arca.recuperacion_local_service import RecuperacionLocalArcaService
from services.arca.reconciliacion_contracts import ResultadoReconciliacion, SnapshotFiscalEsperado
from services.arca.snapshot_fiscal_service import (
    CODIGO_VALIDO,
    calcular_hash_snapshot,
    serializar_snapshot_fiscal,
    validar_integridad_snapshot,
)
from services.intento_emision_arca_service import IntentoEmisionArcaService


class RecuperacionLocalArcaServiceTest(unittest.TestCase):

    def setUp(self):
        archivo = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        archivo.close()
        self.ruta = archivo.name
        conexion = sqlite3.connect(self.ruta)
        try:
            cursor = conexion.cursor()
            cursor.executescript("""
                CREATE TABLE resumenes(id INTEGER PRIMARY KEY, estado_facturacion TEXT, fecha_facturacion TEXT, cae TEXT, vencimiento_cae TEXT, numero_factura TEXT);
                CREATE TABLE factura_arca(id INTEGER PRIMARY KEY AUTOINCREMENT, cliente_id INTEGER NOT NULL, emisor_id INTEGER NOT NULL, resumen_id INTEGER NOT NULL, fecha TEXT NOT NULL, punto_venta TEXT, tipo_comprobante TEXT, importe_total REAL NOT NULL, estado TEXT NOT NULL, numero_factura TEXT, cae TEXT, vencimiento_cae TEXT, observaciones TEXT, fecha_creacion TEXT, punto_venta_num INTEGER, tipo_comprobante_num INTEGER, numero_comprobante_num INTEGER, tipo_documento_receptor INTEGER, documento_receptor INTEGER, snapshot_fiscal_json TEXT, snapshot_version INTEGER, snapshot_hash TEXT);
            """)
            crear_tabla_intentos_emision_arca(cursor)
            cursor.execute("INSERT INTO resumenes VALUES(10, 'Pendiente', '', '', '', '')")
            conexion.commit()
        finally:
            conexion.close()
        self.conexion_factory = lambda: sqlite3.connect(self.ruta)
        self.intentos = IntentoEmisionArcaService(self.conexion_factory)
        self.snapshot = SnapshotFiscalEsperado(
            resumen_id=10, cliente_id=20, emisor_fiscal_id=30, emisor_id=40, cuit_emisor="20206871629",
            punto_venta=5, tipo_comprobante=11, numero_planificado=123, fecha_comprobante="20260817",
            concepto=1, tipo_documento=80, documento_receptor=30712345678, condicion_iva_receptor_id=5,
            importe_total=Decimal("100.00"), importe_neto=Decimal("100.00"), importe_iva=Decimal("0.00"),
            importe_exento=Decimal("0.00"), importe_no_gravado=Decimal("0.00"), importe_tributos=Decimal("0.00"),
            moneda="PES", cotizacion=Decimal("1.00"),
        )
        validacion = ContextoFiscalService.validar(self._contexto())
        self.assertTrue(validacion.valido, validacion.errores)
        self.intento_id = self.intentos.crear_intento(
            self.snapshot,
            estado="PENDIENTE_RECONCILIAR",
            contexto_fiscal_json=validacion.json_canonico,
            contexto_fiscal_version=validacion.version,
            contexto_fiscal_hash=validacion.hash_calculado,
        )
        self.service = RecuperacionLocalArcaService(self.conexion_factory, self.intentos)

    def tearDown(self):
        if os.path.exists(self.ruta):
            os.remove(self.ruta)

    def _contexto(self):
        return {
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

    def _intento(self, estado=None, factura_arca_id=None):
        intento = self.intentos.obtener(self.intento_id)
        cambios = {}
        if estado is not None:
            cambios["estado"] = estado
        if factura_arca_id is not None:
            cambios["factura_arca_id"] = factura_arca_id
        return replace(intento, **cambios)

    def _consulta(self):
        return {"resultado": "A", "cuit_emisor": "20206871629", "punto_venta": 5, "tipo_comprobante": 11, "numero_comprobante": 123, "fecha_comprobante": "20260817", "doc_tipo": 80, "doc_nro": 30712345678, "importe_total": "100.00", "importe_neto": "100.00", "importe_iva": "0.00", "moneda": "PES", "cotizacion": "1.00", "condicion_iva_receptor_id": 5, "cae": "86330766550000", "vencimiento_cae": "20260827"}

    def _filas(self, tabla):
        conexion = sqlite3.connect(self.ruta)
        try:
            return conexion.execute(f"SELECT * FROM {tabla}").fetchall()
        finally:
            conexion.close()

    def _assert_sin_cierre(self):
        self.assertEqual(self._filas("factura_arca"), [])
        self.assertEqual(self._filas("resumenes")[0][1], "Pendiente")
        intento = self.intentos.obtener(self.intento_id)
        self.assertEqual(intento.estado, "PENDIENTE_RECONCILIAR")
        self.assertIsNone(intento.factura_arca_id)

    def test_recuperacion_nueva_exitosa_y_persistente(self):
        resultado = self.service.registrar_factura_recuperada(self._intento(), self.snapshot, self._consulta())
        self.assertEqual(resultado.resultado, ResultadoReconciliacion.AUTORIZADO)
        self.assertTrue(resultado.insertada)
        factura = self._filas("factura_arca")[0]
        intento = self.intentos.obtener(self.intento_id)
        self.assertEqual(factura[9], "00005-00000123")
        self.assertEqual(intento.estado, "RECONCILIADO")
        self.assertEqual(intento.factura_arca_id, resultado.factura_arca_id)
        self.assertTrue(intento.reconciliado_en)
        integridad = validar_integridad_snapshot(factura[-3], factura[-2], factura[-1])
        self.assertEqual(integridad.codigo, CODIGO_VALIDO)
        self.assertEqual(integridad.snapshot["fuente"], "recuperacion")
        self.assertEqual(integridad.snapshot["emisor"]["razon_social"], "Emisor congelado")
        self.assertEqual(integridad.snapshot["receptor"]["razon_social"], "Cliente congelado")
        self.assertEqual(integridad.snapshot["items"][0]["descripcion"], "Servicio congelado")
        self.assertEqual(integridad.snapshot["comprobante"]["tipo_comprobante_texto"], "Factura C")
        self.assertEqual(integridad.snapshot["receptor"]["condicion_iva"], "Consumidor Final")
        self.assertEqual(integridad.snapshot["importes"]["neto"], "100.00")
        self.assertEqual(integridad.snapshot["importes"]["iva"], "0.00")
        self.assertEqual(integridad.snapshot["importes"]["total"], "100.00")
        self.assertEqual(integridad.snapshot["iva"], [])
        self.assertEqual(integridad.snapshot["autorizacion"]["cae"], "86330766550000")

    def test_relee_contexto_persistido_y_no_el_objeto_intento_en_memoria(self):
        intento_memoria = replace(
            self._intento(),
            contexto_fiscal_json="{contexto vivo falso}",
            contexto_fiscal_version=99,
            contexto_fiscal_hash="0" * 64,
        )
        resultado = self.service.registrar_factura_recuperada(
            intento_memoria,
            self.snapshot,
            self._consulta(),
        )
        self.assertEqual(resultado.resultado, ResultadoReconciliacion.AUTORIZADO)
        factura = self._filas("factura_arca")[0]
        integridad = validar_integridad_snapshot(factura[-3], factura[-2], factura[-1])
        self.assertEqual(integridad.codigo, CODIGO_VALIDO)
        self.assertEqual(integridad.snapshot["receptor"]["razon_social"], "Cliente congelado")

    def test_recuperacion_factura_a_persiste_neto_iva_total_alicuota_y_cae(self):
        contexto = self._contexto()
        contexto["emisor"]["condicion_iva"] = "Responsable Inscripto"
        contexto["receptor"]["condicion_iva"] = "Responsable Inscripto"
        contexto["receptor"]["condicion_iva_receptor_id"] = 1
        contexto["comprobante"]["tipo_comprobante_num"] = 1
        contexto["comprobante"]["tipo_comprobante_texto"] = "Factura A"
        contexto["importes"].update(total=Decimal("121"), neto=Decimal("100"), iva=Decimal("21"))
        contexto["iva"] = [{
            "id": 5, "base_imponible": Decimal("100"), "importe": Decimal("21"),
            "porcentaje": Decimal("21"),
        }]
        validacion = ContextoFiscalService.validar(contexto)
        self.assertTrue(validacion.valido, validacion.errores)
        conexion = sqlite3.connect(self.ruta)
        conexion.execute(
            "UPDATE intentos_emision_arca SET tipo_comprobante=1, condicion_iva_receptor_id=1, importe_total='121', importe_neto='100', importe_iva='21', contexto_fiscal_json=?, contexto_fiscal_version=?, contexto_fiscal_hash=? WHERE id=?",
            (validacion.json_canonico, validacion.version, validacion.hash_calculado, self.intento_id),
        )
        conexion.commit()
        conexion.close()
        snapshot_a = replace(
            self.snapshot,
            tipo_comprobante=1,
            condicion_iva_receptor_id=1,
            importe_total=Decimal("121"),
            importe_neto=Decimal("100"),
            importe_iva=Decimal("21"),
            alicuotas_iva=({"Id": 5, "BaseImp": "100", "Importe": "21"},),
        )
        consulta = self._consulta()
        consulta.update(
            tipo_comprobante=1,
            condicion_iva_receptor_id=1,
            importe_total="121",
            importe_neto="100",
            importe_iva="21",
        )

        resultado = self.service.registrar_factura_recuperada(self._intento(), snapshot_a, consulta)
        self.assertEqual(resultado.resultado, ResultadoReconciliacion.AUTORIZADO)
        factura = self._filas("factura_arca")[0]
        integridad = validar_integridad_snapshot(factura[-3], factura[-2], factura[-1])
        self.assertEqual(integridad.codigo, CODIGO_VALIDO)
        final = integridad.snapshot
        self.assertEqual(final["comprobante"]["tipo_comprobante_texto"], "Factura A")
        self.assertEqual(final["receptor"]["condicion_iva"], "Responsable Inscripto")
        self.assertEqual(final["importes"]["neto"], "100.00")
        self.assertEqual(final["importes"]["iva"], "21.00")
        self.assertEqual(final["importes"]["total"], "121.00")
        self.assertEqual(final["iva"][0]["porcentaje"], "21.00")
        self.assertEqual(final["autorizacion"]["cae"], "86330766550000")

    def test_repetir_recuperacion_es_idempotente(self):
        primero = self.service.registrar_factura_recuperada(self._intento(), self.snapshot, self._consulta())
        hash_primero = self._filas("factura_arca")[0][-1]
        segundo = self.service.registrar_factura_recuperada(self._intento("RECONCILIADO", primero.factura_arca_id), self.snapshot, self._consulta())
        self.assertEqual(primero.factura_arca_id, segundo.factura_arca_id)
        self.assertEqual(len(self._filas("factura_arca")), 1)
        self.assertEqual(self._filas("factura_arca")[0][-1], hash_primero)

    def test_snapshot_existente_diferente_no_se_sobrescribe(self):
        primero = self.service.registrar_factura_recuperada(self._intento(), self.snapshot, self._consulta())
        factura = self._filas("factura_arca")[0]
        snapshot_distinto = json.loads(factura[-3])
        snapshot_distinto["creado_en"] = "2026-08-17T11:00:00"
        json_distinto = serializar_snapshot_fiscal(snapshot_distinto)
        hash_distinto = calcular_hash_snapshot(json_distinto)
        conexion = sqlite3.connect(self.ruta)
        conexion.execute(
            "UPDATE factura_arca SET snapshot_fiscal_json=?, snapshot_hash=? WHERE id=?",
            (json_distinto, hash_distinto, primero.factura_arca_id),
        )
        conexion.execute("UPDATE resumenes SET estado_facturacion='Pendiente' WHERE id=10")
        conexion.execute("UPDATE intentos_emision_arca SET estado='PENDIENTE_RECONCILIAR' WHERE id=?", (self.intento_id,))
        conexion.commit()
        conexion.close()

        resultado = self.service.registrar_factura_recuperada(self._intento(), self.snapshot, self._consulta())
        self.assertEqual(resultado.resultado, ResultadoReconciliacion.CONFLICTO)
        self.assertEqual(self._filas("factura_arca")[0][-1], hash_distinto)
        self.assertEqual(self._filas("resumenes")[0][1], "Pendiente")
        self.assertEqual(self.intentos.obtener(self.intento_id).estado, "PENDIENTE_RECONCILIAR")

    def test_intento_sin_contexto_no_hace_fallback(self):
        conexion = sqlite3.connect(self.ruta)
        conexion.execute(
            "UPDATE intentos_emision_arca SET contexto_fiscal_json=NULL, contexto_fiscal_version=NULL, contexto_fiscal_hash=NULL WHERE id=?",
            (self.intento_id,),
        )
        conexion.commit()
        conexion.close()
        resultado = self.service.registrar_factura_recuperada(self._intento(), self.snapshot, self._consulta())
        self.assertEqual(resultado.resultado, ResultadoReconciliacion.CONSULTA_INCIERTA)
        self._assert_sin_cierre()

    def test_contexto_corrupto_version_y_hash_invalidos_no_cierran(self):
        casos = (
            ("{mal", 1, "0" * 64),
            (self._intento().contexto_fiscal_json, 99, self._intento().contexto_fiscal_hash),
            (self._intento().contexto_fiscal_json, 1, "0" * 64),
        )
        for json_contexto, version, hash_contexto in casos:
            with self.subTest(version=version, hash=hash_contexto[:4]):
                conexion = sqlite3.connect(self.ruta)
                conexion.execute(
                    "UPDATE intentos_emision_arca SET contexto_fiscal_json=?, contexto_fiscal_version=?, contexto_fiscal_hash=? WHERE id=?",
                    (json_contexto, version, hash_contexto, self.intento_id),
                )
                conexion.commit()
                conexion.close()
                resultado = self.service.registrar_factura_recuperada(self._intento(), self.snapshot, self._consulta())
                self.assertEqual(resultado.resultado, ResultadoReconciliacion.CONSULTA_INCIERTA)
                self._assert_sin_cierre()

    def test_respuestas_arca_invalidas_no_cierran(self):
        casos = {
            "sin_cae": ("cae", None),
            "sin_vencimiento": ("vencimiento_cae", None),
            "resultado_rechazado": ("resultado", "R"),
            "campo_obligatorio_ausente": ("importe_total", None),
            "cuit": ("cuit_emisor", "20999999999"),
            "pv": ("punto_venta", 6),
            "tipo": ("tipo_comprobante", 1),
            "numero": ("numero_comprobante", 124),
            "fecha": ("fecha_comprobante", "20260818"),
            "doc_tipo": ("doc_tipo", 96),
            "doc_nro": ("doc_nro", 99999999),
            "total": ("importe_total", "101.00"),
            "neto": ("importe_neto", "99.00"),
            "iva": ("importe_iva", "1.00"),
            "moneda": ("moneda", "USD"),
            "cotizacion": ("cotizacion", "2.00"),
            "condicion_iva": ("condicion_iva_receptor_id", 1),
        }
        for nombre, (campo, valor) in casos.items():
            with self.subTest(caso=nombre):
                consulta = self._consulta()
                if valor is None:
                    consulta.pop(campo)
                else:
                    consulta[campo] = valor
                resultado = self.service.registrar_factura_recuperada(self._intento(), self.snapshot, consulta)
                self.assertNotEqual(resultado.resultado, ResultadoReconciliacion.AUTORIZADO)
                self._assert_sin_cierre()

    def test_fallo_persistir_snapshot_hace_rollback(self):
        primero = self.service.registrar_factura_recuperada(self._intento(), self.snapshot, self._consulta())
        conexion = sqlite3.connect(self.ruta)
        conexion.execute("UPDATE factura_arca SET snapshot_fiscal_json=NULL, snapshot_version=NULL, snapshot_hash=NULL WHERE id=?", (primero.factura_arca_id,))
        conexion.execute("UPDATE resumenes SET estado_facturacion='Pendiente', cae='', numero_factura='' WHERE id=10")
        conexion.execute("UPDATE intentos_emision_arca SET estado='PENDIENTE_RECONCILIAR', factura_arca_id=NULL WHERE id=?", (self.intento_id,))
        conexion.execute("CREATE TRIGGER falla_snapshot BEFORE UPDATE OF snapshot_fiscal_json ON factura_arca BEGIN SELECT RAISE(ABORT, 'snapshot'); END")
        conexion.commit()
        conexion.close()

        with self.assertRaises(sqlite3.DatabaseError):
            self.service.registrar_factura_recuperada(self._intento(), self.snapshot, self._consulta())
        factura = self._filas("factura_arca")[0]
        self.assertIsNone(factura[-3])
        self.assertEqual(self._filas("resumenes")[0][1], "Pendiente")
        self.assertEqual(self.intentos.obtener(self.intento_id).estado, "PENDIENTE_RECONCILIAR")

    def test_fallo_actualizar_factura_existente_hace_rollback(self):
        primero = self.service.registrar_factura_recuperada(self._intento(), self.snapshot, self._consulta())
        conexion = sqlite3.connect(self.ruta)
        conexion.execute("UPDATE factura_arca SET estado='Estado previo' WHERE id=?", (primero.factura_arca_id,))
        conexion.execute("UPDATE resumenes SET estado_facturacion='Pendiente', cae='', numero_factura='' WHERE id=10")
        conexion.execute("UPDATE intentos_emision_arca SET estado='PENDIENTE_RECONCILIAR', factura_arca_id=NULL WHERE id=?", (self.intento_id,))
        conexion.execute("CREATE TRIGGER falla_update_factura BEFORE UPDATE OF estado ON factura_arca BEGIN SELECT RAISE(ABORT, 'update factura'); END")
        conexion.commit()
        conexion.close()

        with self.assertRaises(sqlite3.DatabaseError):
            self.service.registrar_factura_recuperada(self._intento(), self.snapshot, self._consulta())
        self.assertEqual(self._filas("factura_arca")[0][8], "Estado previo")
        self.assertEqual(self._filas("resumenes")[0][1], "Pendiente")
        self.assertEqual(self.intentos.obtener(self.intento_id).estado, "PENDIENTE_RECONCILIAR")

    def test_factura_existe_y_resumen_pendiente(self):
        self.service.registrar_factura_recuperada(self._intento(), self.snapshot, self._consulta())
        conexion = sqlite3.connect(self.ruta)
        conexion.execute("UPDATE resumenes SET estado_facturacion='Pendiente', cae='', numero_factura='' WHERE id=10")
        conexion.execute("UPDATE intentos_emision_arca SET estado='PENDIENTE_RECONCILIAR', factura_arca_id=NULL WHERE id=1")
        conexion.commit(); conexion.close()
        resultado = self.service.registrar_factura_recuperada(self._intento(), self.snapshot, self._consulta())
        self.assertFalse(resultado.insertada)
        self.assertEqual(len(self._filas("factura_arca")), 1)

    def test_resumen_facturado_y_factura_falta(self):
        conexion = sqlite3.connect(self.ruta)
        conexion.execute("UPDATE resumenes SET estado_facturacion='Facturado', cae='86330766550000', numero_factura='00005-00000123' WHERE id=10")
        conexion.commit(); conexion.close()
        resultado = self.service.registrar_factura_recuperada(self._intento(), self.snapshot, self._consulta())
        self.assertEqual(resultado.resultado, ResultadoReconciliacion.AUTORIZADO)
        self.assertEqual(len(self._filas("factura_arca")), 1)

    def test_intento_ya_reconciliado_con_factura_enlazada_es_idempotente(self):
        primero = self.service.registrar_factura_recuperada(self._intento(), self.snapshot, self._consulta())
        resultado = self.service.registrar_factura_recuperada(
            self._intento("RECONCILIADO", primero.factura_arca_id),
            self.snapshot,
            self._consulta(),
        )
        self.assertEqual(resultado.resultado, ResultadoReconciliacion.AUTORIZADO)
        self.assertEqual(resultado.factura_arca_id, primero.factura_arca_id)
        self.assertEqual(len(self._filas("factura_arca")), 1)

    def test_cerrar_y_reabrir_conexion_conserva_recuperacion(self):
        resultado = self.service.registrar_factura_recuperada(self._intento(), self.snapshot, self._consulta())
        conexion = sqlite3.connect(self.ruta)
        try:
            intento = conexion.execute("SELECT estado, factura_arca_id, reconciliado_en FROM intentos_emision_arca WHERE id=1").fetchone()
            resumen = conexion.execute("SELECT estado_facturacion, cae, numero_factura FROM resumenes WHERE id=10").fetchone()
        finally:
            conexion.close()
        self.assertEqual(intento[0], "RECONCILIADO")
        self.assertEqual(intento[1], resultado.factura_arca_id)
        self.assertTrue(intento[2])
        self.assertEqual(resumen[0], "Facturado")

    def test_conflicto_por_identidad_local(self):
        conexion = sqlite3.connect(self.ruta)
        conexion.execute("INSERT INTO factura_arca(id,cliente_id,emisor_id,resumen_id,fecha,punto_venta,tipo_comprobante,importe_total,estado,numero_factura,cae,vencimiento_cae,observaciones,fecha_creacion) VALUES(NULL,99,40,10,'20260817','5','Factura C',100,'Facturada manualmente','00005-00000123','86330766550000','20260827','','')")
        conexion.commit(); conexion.close()
        resultado = self.service.registrar_factura_recuperada(self._intento(), self.snapshot, self._consulta())
        self.assertEqual(resultado.resultado, ResultadoReconciliacion.CONFLICTO)
        self.assertEqual(self.intentos.obtener(self.intento_id).estado, "PENDIENTE_RECONCILIAR")

    def test_conflicto_por_cae_local(self):
        conexion = sqlite3.connect(self.ruta)
        conexion.execute("INSERT INTO factura_arca(id,cliente_id,emisor_id,resumen_id,fecha,punto_venta,tipo_comprobante,importe_total,estado,numero_factura,cae,vencimiento_cae,observaciones,fecha_creacion) VALUES(NULL,20,40,99,'20260817','5','Factura C',100,'Facturada manualmente','00005-00000123','86330766550000','20260827','','')")
        conexion.commit(); conexion.close()
        resultado = self.service.registrar_factura_recuperada(self._intento(), self.snapshot, self._consulta())
        self.assertEqual(resultado.resultado, ResultadoReconciliacion.CONFLICTO)

    def test_fallo_insertar_hace_rollback(self):
        conexion = sqlite3.connect(self.ruta)
        conexion.execute("CREATE TRIGGER falla_insert BEFORE INSERT ON factura_arca BEGIN SELECT RAISE(ABORT, 'insert'); END")
        conexion.commit(); conexion.close()
        with self.assertRaises(sqlite3.DatabaseError):
            self.service.registrar_factura_recuperada(self._intento(), self.snapshot, self._consulta())
        self.assertEqual(len(self._filas("factura_arca")), 0)
        self.assertEqual(self.intentos.obtener(self.intento_id).estado, "PENDIENTE_RECONCILIAR")

    def test_fallo_marcar_resumen_hace_rollback(self):
        conexion = sqlite3.connect(self.ruta)
        conexion.execute("CREATE TRIGGER falla_resumen BEFORE UPDATE ON resumenes BEGIN SELECT RAISE(ABORT, 'resumen'); END")
        conexion.commit(); conexion.close()
        with self.assertRaises(sqlite3.DatabaseError):
            self.service.registrar_factura_recuperada(self._intento(), self.snapshot, self._consulta())
        self.assertEqual(len(self._filas("factura_arca")), 0)

    def test_fallo_enlazar_intento_hace_rollback(self):
        conexion = sqlite3.connect(self.ruta)
        conexion.execute("CREATE TRIGGER falla_intento BEFORE UPDATE ON intentos_emision_arca BEGIN SELECT RAISE(ABORT, 'intento'); END")
        conexion.commit(); conexion.close()
        with self.assertRaises(sqlite3.DatabaseError):
            self.service.registrar_factura_recuperada(self._intento(), self.snapshot, self._consulta())
        self.assertEqual(len(self._filas("factura_arca")), 0)


if __name__ == "__main__":
    unittest.main()