"""Fase 5C: integracion del snapshot fiscal v1 en el cierre normal.

Cubre construccion (FacturacionService._construir_snapshot_fiscal_cierre_normal),
cierre transaccional (CierreLocalArcaService con snapshot) e inmutabilidad/idempotencia.
Cero red, cero ARCA real: todo se valida con fakes y SQLite temporal.
"""

import json
import os
import re
import sqlite3
import tempfile
import unittest
from decimal import Decimal
from unittest.mock import MagicMock, patch

from services.arca import ambiente_arca
from services.arca.cierre_local_arca_service import CierreLocalArcaService
from services.arca.homologacion_service import HomologacionService
from services.arca.reconciliacion_contracts import ResultadoReconciliacion
from services.arca.snapshot_fiscal_service import (
    CODIGO_VALIDO,
    SNAPSHOT_VERSION,
    calcular_hash_snapshot,
    construir_snapshot_fiscal_v1,
    serializar_snapshot_fiscal,
    validar_integridad_snapshot,
)
from services.facturacion_service import FacturacionService


def _emisor_fiscal(cuit="20206871629", ambiente="Homologación"):
    return (
        30, "FM Master SRL", "FM Master", cuit, "Responsable Inscripto",
        "Factura A", 5, 1, "", ambiente, "Domicilio Fiscal 123",
        "123456", "20200101", "cert.crt", "clave.key", "C:/trabajo",
    )


def _cliente_responsable():
    return (
        20, "", "Cliente Responsable SA", "", "", "Calle Falsa 123", "Springfield",
        "", "", "", "20222222221", "Responsable Inscripto",
    )


def _cliente_consumidor():
    return (
        21, "", "Consumidor Final", "", "", "Otra Calle 456", "Ciudad",
        "", "", "", "", "Consumidor Final",
    )


def _items():
    return [{
        "concepto": "Publicidad", "descripcion": "Publicidad - Agosto",
        "cantidad": 1.0, "precio_unitario": 1000.0, "importe": 1000.0,
    }]


def _snapshot_valido(numero=123, cae="12345678901234"):
    snapshot = construir_snapshot_fiscal_v1(
        fuente="cierre_normal",
        creado_en="2026-08-23T12:00:00",
        ambiente="HOMOLOGACION",
        emisor={
            "emisor_id": 40, "emisor_fiscal_id": 30, "razon_social": "FM Master SRL",
            "nombre_fantasia": "FM Master", "cuit": "20206871629", "condicion_iva": "Responsable Inscripto",
            "domicilio": "Domicilio 123", "ingresos_brutos": "123456",
            "fecha_inicio_actividades": "2020-01-01", "punto_venta_num": 5,
        },
        receptor={
            "cliente_id": 20, "razon_social": "Cliente SA", "documento_visible": "20222222221",
            "condicion_iva": "Responsable Inscripto", "domicilio": "Calle 123",
            "tipo_documento_receptor": 80, "documento_receptor": 20222222221,
        },
        comprobante={
            "fecha": "2026-08-23", "fecha_arca": "20260823", "concepto": 1,
            "concepto_descripcion": "1 - Productos", "punto_venta_num": 5,
            "tipo_comprobante_num": 1, "tipo_comprobante_texto": "Factura A",
            "numero_comprobante_num": numero, "numero_textual": f"00005-{numero:08d}",
            "periodo_servicio_desde": None, "periodo_servicio_hasta": None, "vencimiento_pago": None,
            "moneda": "PES", "cotizacion": Decimal("1"),
        },
        importes={
            "total": Decimal("1210"), "neto": Decimal("1000"), "iva": Decimal("210"),
            "exento": Decimal("0"), "no_gravado": Decimal("0"), "tributos": Decimal("0"),
        },
        iva=[{"id": 5, "base_imponible": Decimal("1000"), "importe": Decimal("210"), "porcentaje": Decimal("21")}],
        items=[{
            "concepto": "Servicio", "descripcion": "Servicio", "cantidad": Decimal("1"),
            "precio_unitario": Decimal("1000"), "subtotal": Decimal("1000"),
        }],
        autorizacion={
            "cae": cae, "vencimiento_cae": "2026-09-02", "vencimiento_cae_arca": "20260902",
            "tipo_cod_aut": "E", "resultado": "AUTORIZADO", "cerrado_en": "2026-08-23T12:00:00",
        },
    )
    json_text = serializar_snapshot_fiscal(snapshot)
    return json_text, SNAPSHOT_VERSION, calcular_hash_snapshot(json_text)


class SnapshotFiscalCierreNormalConstruccionTest(unittest.TestCase):
    """Seccion 18: construccion del snapshot desde el contexto de emision ya resuelto."""

    def _construir_a(self, **overrides):
        base = dict(
            emisor_fiscal=_emisor_fiscal(),
            emisor_facturacion_id=40,
            cuit_emisor_normalizado="20206871629",
            punto_venta_num=5,
            cliente=_cliente_responsable(),
            condicion_iva="Responsable Inscripto",
            documento_normalizado="20222222221",
            tipo_documento=80,
            documento_receptor=20222222221,
            tipo_comprobante=1,
            tipo_factura_normalizado="Factura A",
            numero_comprobante=123,
            numero_factura="00005-00000123",
            fecha_comprobante="20260823",
            periodo_desde="",
            periodo_hasta="",
            vencimiento_pago_arca="",
            moneda="PES",
            cotizacion=1.0,
            neto_factura=1000.0,
            importe_iva_factura=210.0,
            alicuota_iva=21.0,
            total_factura_fiscal=1210.0,
            importe_exento_factura=0.0,
            importe_tot_conc=0.0,
            importe_tributos=0.0,
            alicuotas_iva=[{"id": 5, "base_imponible": 1000.0, "importe": 210.0}],
            items_factura=_items(),
            cae="12345678901234",
            vencimiento_cae="20260902",
            ambiente_normalizado=ambiente_arca.AMBIENTE_HOMOLOGACION,
        )
        base.update(overrides)
        return FacturacionService._construir_snapshot_fiscal_cierre_normal(**base)

    def _construir_c(self, **overrides):
        base = dict(
            emisor_fiscal=_emisor_fiscal(),
            emisor_facturacion_id=40,
            cuit_emisor_normalizado="20206871629",
            punto_venta_num=5,
            cliente=_cliente_consumidor(),
            condicion_iva="Consumidor Final",
            documento_normalizado="",
            tipo_documento=99,
            documento_receptor=0,
            tipo_comprobante=11,
            tipo_factura_normalizado="Factura C",
            numero_comprobante=124,
            numero_factura="00005-00000124",
            fecha_comprobante="20260823",
            periodo_desde="",
            periodo_hasta="",
            vencimiento_pago_arca="",
            moneda="PES",
            cotizacion=1.0,
            neto_factura=1000.0,
            importe_iva_factura=0.0,
            alicuota_iva=0.0,
            total_factura_fiscal=1000.0,
            importe_exento_factura=0.0,
            importe_tot_conc=0.0,
            importe_tributos=0.0,
            alicuotas_iva=[],
            items_factura=_items(),
            cae="12345678901235",
            vencimiento_cae="20260902",
            ambiente_normalizado=ambiente_arca.AMBIENTE_HOMOLOGACION,
        )
        base.update(overrides)
        return FacturacionService._construir_snapshot_fiscal_cierre_normal(**base)

    def test_factura_a_construye_snapshot_completo(self):
        resultado = self._construir_a()
        self.assertTrue(resultado["ok"])
        validado = validar_integridad_snapshot(
            resultado["snapshot_json"], resultado["snapshot_version"], resultado["snapshot_hash"]
        )
        self.assertEqual(validado.codigo, CODIGO_VALIDO)

    def test_factura_c_construye_snapshot_completo(self):
        resultado = self._construir_c()
        self.assertTrue(resultado["ok"])
        validado = validar_integridad_snapshot(
            resultado["snapshot_json"], resultado["snapshot_version"], resultado["snapshot_hash"]
        )
        self.assertEqual(validado.codigo, CODIGO_VALIDO)

    def test_cuit_snapshot_igual_a_cuit_usado_en_wsfe(self):
        resultado = self._construir_a()
        self.assertIn('"cuit":"20206871629"', resultado["snapshot_json"])

    def test_contradiccion_cuit_falla(self):
        resultado = self._construir_a(cuit_emisor_normalizado="20111111117")
        self.assertFalse(resultado["ok"])
        self.assertTrue(any("contradiccion_cuit_emisor" in error for error in resultado["errores"]))

    def test_ambiente_queda_congelado(self):
        resultado = self._construir_a()
        self.assertIn('"ambiente":"HOMOLOGACION"', resultado["snapshot_json"])

    def test_constructor_respeta_ambiente_homologacion_recibido(self):
        resultado = self._construir_a(ambiente_normalizado=ambiente_arca.AMBIENTE_HOMOLOGACION)
        self.assertTrue(resultado["ok"])
        self.assertEqual(json.loads(resultado["snapshot_json"])["ambiente"], ambiente_arca.AMBIENTE_HOMOLOGACION)

    def test_constructor_respeta_ambiente_produccion_recibido(self):
        resultado = self._construir_a(ambiente_normalizado=ambiente_arca.AMBIENTE_PRODUCCION)
        self.assertTrue(resultado["ok"])
        self.assertEqual(json.loads(resultado["snapshot_json"])["ambiente"], ambiente_arca.AMBIENTE_PRODUCCION)

    def test_constructor_rechaza_ambiente_invalido(self):
        resultado = self._construir_a(ambiente_normalizado="QA")
        self.assertFalse(resultado["ok"])
        self.assertTrue(any("ambiente_arca_invalido" in error for error in resultado["errores"]))

    def test_receptor_visible_queda_congelado(self):
        resultado = self._construir_a()
        self.assertIn('"razon_social":"Cliente Responsable SA"', resultado["snapshot_json"])

    def test_doctipo_docnro_iguales_al_request(self):
        resultado = self._construir_a()
        self.assertIn('"tipo_documento_receptor":80', resultado["snapshot_json"])
        self.assertIn('"documento_receptor":20222222221', resultado["snapshot_json"])

    def test_items_quedan_congelados(self):
        resultado = self._construir_a()
        self.assertIn('"descripcion":"Publicidad - Agosto"', resultado["snapshot_json"])

    def test_periodo_y_vencimiento_quedan_congelados(self):
        resultado = self._construir_a(
            periodo_desde="20260801", periodo_hasta="20260831", vencimiento_pago_arca="20260910"
        )
        self.assertIn('"periodo_servicio_desde":"2026-08-01"', resultado["snapshot_json"])
        self.assertIn('"periodo_servicio_hasta":"2026-08-31"', resultado["snapshot_json"])
        self.assertIn('"vencimiento_pago":"2026-09-10"', resultado["snapshot_json"])

    def test_neto_iva_factura_a_coincide_con_calculo_fiscal(self):
        resultado = self._construir_a()
        self.assertIn('"neto":"1000.00"', resultado["snapshot_json"])
        self.assertIn('"iva":"210.00"', resultado["snapshot_json"])

    def test_iva_factura_c_es_cero(self):
        resultado = self._construir_c()
        self.assertIn('"iva":"0.00"', resultado["snapshot_json"])
        self.assertIn('"iva":[]', resultado["snapshot_json"])

    def test_moneda_cotizacion_coinciden_con_request(self):
        resultado = self._construir_a(moneda="PES", cotizacion=1.0)
        self.assertIn('"moneda":"PES"', resultado["snapshot_json"])
        self.assertIn('"cotizacion":"1.000000"', resultado["snapshot_json"])

    def test_cae_vencimiento_coinciden_con_consulta(self):
        resultado = self._construir_a(cae="12345678901234", vencimiento_cae="20260902")
        self.assertIn('"cae":"12345678901234"', resultado["snapshot_json"])
        self.assertIn('"vencimiento_cae":"2026-09-02"', resultado["snapshot_json"])


class CommitFallido:
    def __init__(self, conexion):
        self._conexion = conexion

    def cursor(self):
        return self._conexion.cursor()

    def execute(self, *args, **kwargs):
        return self._conexion.execute(*args, **kwargs)

    def commit(self):
        raise sqlite3.OperationalError("commit simulado")

    def rollback(self):
        self._conexion.rollback()

    def close(self):
        self._conexion.close()


class CierreLocalConSnapshotTest(unittest.TestCase):
    """Secciones 19 y 20: cierre transaccional e inmutabilidad/idempotencia."""

    def setUp(self):
        archivo = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        archivo.close()
        self.ruta = archivo.name
        conexion = sqlite3.connect(self.ruta)
        try:
            conexion.executescript(
                """
                CREATE TABLE resumenes(id INTEGER PRIMARY KEY, estado_facturacion TEXT, fecha_facturacion TEXT, cae TEXT, vencimiento_cae TEXT, numero_factura TEXT);
                CREATE TABLE factura_arca(id INTEGER PRIMARY KEY AUTOINCREMENT, cliente_id INTEGER NOT NULL, emisor_id INTEGER NOT NULL, resumen_id INTEGER NOT NULL, fecha TEXT NOT NULL, punto_venta TEXT, tipo_comprobante TEXT, importe_total REAL NOT NULL, estado TEXT NOT NULL, numero_factura TEXT, cae TEXT, vencimiento_cae TEXT, observaciones TEXT, fecha_creacion TEXT, punto_venta_num INTEGER, tipo_comprobante_num INTEGER, numero_comprobante_num INTEGER, tipo_documento_receptor INTEGER, documento_receptor INTEGER, snapshot_fiscal_json TEXT, snapshot_version INTEGER, snapshot_hash TEXT);
                CREATE TABLE intentos_emision_arca(id INTEGER PRIMARY KEY, estado TEXT, cae TEXT, vencimiento_cae TEXT, factura_arca_id INTEGER, error_codigo TEXT, error_mensaje TEXT, actualizado_en TEXT, reconciliado_en TEXT);
                """
            )
            conexion.execute("INSERT INTO resumenes VALUES(10, 'Pendiente', '', '', '', '')")
            conexion.execute("INSERT INTO intentos_emision_arca VALUES(1, 'ENVIANDO', '', '', NULL, '', '', '', NULL)")
            conexion.commit()
        finally:
            conexion.close()
        self.service = CierreLocalArcaService(lambda: sqlite3.connect(self.ruta))

    def tearDown(self):
        if os.path.exists(self.ruta):
            os.remove(self.ruta)

    def filas(self, tabla):
        conexion = sqlite3.connect(self.ruta)
        try:
            return conexion.execute(f"SELECT * FROM {tabla}").fetchall()
        finally:
            conexion.close()

    def datos(self, **overrides):
        base = dict(
            intento_id=1, resumen_id=10, cliente_id=20, emisor_id=40, fecha="20260823",
            punto_venta="5", tipo_comprobante="Factura A", importe_total=1210.0,
            numero_factura="00005-00000123", cae="12345678901234", vencimiento_cae="20260902",
            observaciones="cierre normal 5C",
        )
        base.update(overrides)
        return base

    def _insertar_factura_compatible(self, snapshot_columnas=None):
        conexion = sqlite3.connect(self.ruta)
        if snapshot_columnas:
            conexion.execute(
                "INSERT INTO factura_arca(cliente_id,emisor_id,resumen_id,fecha,punto_venta,tipo_comprobante,importe_total,estado,numero_factura,cae,vencimiento_cae,observaciones,fecha_creacion,snapshot_fiscal_json,snapshot_version,snapshot_hash) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (20, 40, 10, "20260823", "5", "Factura A", 1210.0, "Facturada manualmente",
                 "00005-00000123", "12345678901234", "20260902", "", "", *snapshot_columnas),
            )
        else:
            conexion.execute(
                "INSERT INTO factura_arca(cliente_id,emisor_id,resumen_id,fecha,punto_venta,tipo_comprobante,importe_total,estado,numero_factura,cae,vencimiento_cae,observaciones,fecha_creacion) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (20, 40, 10, "20260823", "5", "Factura A", 1210.0, "Facturada manualmente",
                 "00005-00000123", "12345678901234", "20260902", "", ""),
            )
        conexion.commit()
        conexion.close()

    # --- Seccion 19: cierre transaccional ---

    def test_factura_nueva_persiste_snapshot(self):
        json_text, version, digest = _snapshot_valido()
        resultado = self.service.cerrar_emision_confirmada(
            **self.datos(), snapshot_fiscal_json=json_text, snapshot_version=version, snapshot_hash=digest,
        )
        self.assertTrue(resultado.ok)
        fila = self.filas("factura_arca")[0]
        self.assertEqual(fila[-3:], (json_text, version, digest))

    def test_version_es_1(self):
        _json_text, version, _digest = _snapshot_valido()
        self.assertEqual(version, 1)

    def test_hash_valido(self):
        _json_text, _version, digest = _snapshot_valido()
        self.assertRegex(digest, r"^[0-9a-f]{64}$")

    def test_snapshot_valido_segun_5a(self):
        json_text, version, digest = _snapshot_valido()
        resultado = validar_integridad_snapshot(json_text, version, digest)
        self.assertEqual(resultado.codigo, CODIGO_VALIDO)

    def test_factura_resumen_intento_snapshot_mismo_commit(self):
        json_text, version, digest = _snapshot_valido()
        resultado = self.service.cerrar_emision_confirmada(
            **self.datos(), snapshot_fiscal_json=json_text, snapshot_version=version, snapshot_hash=digest,
        )
        self.assertTrue(resultado.ok)
        self.assertEqual(self.filas("resumenes")[0][1], "Facturado")
        self.assertEqual(self.filas("intentos_emision_arca")[0][1], "RECONCILIADO")
        self.assertIsNotNone(self.filas("factura_arca")[0][-3])

    def test_rollback_por_fallo_insert_factura(self):
        conexion = sqlite3.connect(self.ruta)
        conexion.execute("CREATE TRIGGER falla BEFORE INSERT ON factura_arca BEGIN SELECT RAISE(ABORT, 'insert'); END")
        conexion.commit()
        conexion.close()
        json_text, version, digest = _snapshot_valido()
        with self.assertRaises(sqlite3.DatabaseError):
            self.service.cerrar_emision_confirmada(
                **self.datos(), snapshot_fiscal_json=json_text, snapshot_version=version, snapshot_hash=digest,
            )
        self.assertEqual(len(self.filas("factura_arca")), 0)
        self.assertEqual(self.filas("resumenes")[0][1], "Pendiente")

    def test_rollback_por_fallo_resumen(self):
        conexion = sqlite3.connect(self.ruta)
        conexion.execute("CREATE TRIGGER falla BEFORE UPDATE ON resumenes BEGIN SELECT RAISE(ABORT, 'resumen'); END")
        conexion.commit()
        conexion.close()
        json_text, version, digest = _snapshot_valido()
        with self.assertRaises(sqlite3.DatabaseError):
            self.service.cerrar_emision_confirmada(
                **self.datos(), snapshot_fiscal_json=json_text, snapshot_version=version, snapshot_hash=digest,
            )
        self.assertEqual(len(self.filas("factura_arca")), 0)

    def test_rollback_por_fallo_intento(self):
        conexion = sqlite3.connect(self.ruta)
        conexion.execute("CREATE TRIGGER falla BEFORE UPDATE ON intentos_emision_arca BEGIN SELECT RAISE(ABORT, 'intento'); END")
        conexion.commit()
        conexion.close()
        json_text, version, digest = _snapshot_valido()
        with self.assertRaises(sqlite3.DatabaseError):
            self.service.cerrar_emision_confirmada(
                **self.datos(), snapshot_fiscal_json=json_text, snapshot_version=version, snapshot_hash=digest,
            )
        self.assertEqual(len(self.filas("factura_arca")), 0)
        self.assertEqual(self.filas("resumenes")[0][1], "Pendiente")

    def test_rollback_por_fallo_snapshot_en_factura_existente(self):
        self._insertar_factura_compatible()
        conexion = sqlite3.connect(self.ruta)
        conexion.execute(
            "CREATE TRIGGER falla_snapshot BEFORE UPDATE OF snapshot_fiscal_json ON factura_arca "
            "BEGIN SELECT RAISE(ABORT, 'snapshot'); END"
        )
        conexion.commit()
        conexion.close()
        json_text, version, digest = _snapshot_valido()
        with self.assertRaises(sqlite3.DatabaseError):
            self.service.cerrar_emision_confirmada(
                **self.datos(), snapshot_fiscal_json=json_text, snapshot_version=version, snapshot_hash=digest,
            )
        self.assertEqual(self.filas("resumenes")[0][1], "Pendiente")
        self.assertEqual(self.filas("intentos_emision_arca")[0][1], "ENVIANDO")

    def test_fallo_commit_no_deja_nada_parcial(self):
        service = CierreLocalArcaService(lambda: CommitFallido(sqlite3.connect(self.ruta)))
        json_text, version, digest = _snapshot_valido()
        with self.assertRaises(sqlite3.OperationalError):
            service.cerrar_emision_confirmada(
                **self.datos(), snapshot_fiscal_json=json_text, snapshot_version=version, snapshot_hash=digest,
            )
        self.assertEqual(len(self.filas("factura_arca")), 0)
        self.assertEqual(self.filas("resumenes")[0][1], "Pendiente")
        self.assertEqual(self.filas("intentos_emision_arca")[0][1], "ENVIANDO")

    def test_snapshot_estructuralmente_invalido_no_abre_transaccion(self):
        resultado = self.service.cerrar_emision_confirmada(
            **self.datos(), snapshot_fiscal_json="{mal", snapshot_version=1, snapshot_hash="0" * 64,
        )
        self.assertFalse(resultado.ok)
        self.assertEqual(resultado.resultado, ResultadoReconciliacion.CONFLICTO)
        self.assertEqual(len(self.filas("factura_arca")), 0)
        self.assertEqual(self.filas("resumenes")[0][1], "Pendiente")
        self.assertEqual(self.filas("intentos_emision_arca")[0][1], "ENVIANDO")

    # --- Seccion 20: inmutabilidad/idempotencia ---

    def test_repeticion_mismo_snapshot_no_duplica_factura(self):
        json_text, version, digest = _snapshot_valido()
        primero = self.service.cerrar_emision_confirmada(
            **self.datos(), snapshot_fiscal_json=json_text, snapshot_version=version, snapshot_hash=digest,
        )
        segundo = self.service.cerrar_emision_confirmada(
            **self.datos(), snapshot_fiscal_json=json_text, snapshot_version=version, snapshot_hash=digest,
        )
        self.assertTrue(primero.ok)
        self.assertTrue(segundo.ok)
        self.assertEqual(primero.factura_arca_id, segundo.factura_arca_id)
        self.assertEqual(len(self.filas("factura_arca")), 1)

    def test_factura_existente_snapshot_null_se_completa(self):
        self._insertar_factura_compatible()
        json_text, version, digest = _snapshot_valido()
        resultado = self.service.cerrar_emision_confirmada(
            **self.datos(), snapshot_fiscal_json=json_text, snapshot_version=version, snapshot_hash=digest,
        )
        self.assertTrue(resultado.ok)
        fila = self.filas("factura_arca")[0]
        self.assertEqual(fila[-3:], (json_text, version, digest))

    def test_factura_existente_mismo_snapshot_no_op(self):
        json_text, version, digest = _snapshot_valido()
        self.service.cerrar_emision_confirmada(
            **self.datos(), snapshot_fiscal_json=json_text, snapshot_version=version, snapshot_hash=digest,
        )
        antes = self.filas("factura_arca")[0]
        segundo = self.service.cerrar_emision_confirmada(
            **self.datos(), snapshot_fiscal_json=json_text, snapshot_version=version, snapshot_hash=digest,
        )
        despues = self.filas("factura_arca")[0]
        self.assertTrue(segundo.ok)
        self.assertEqual(antes, despues)

    def test_factura_existente_snapshot_distinto_conflicto(self):
        json_text, version, digest = _snapshot_valido()
        otro_json, otra_version, otro_digest = _snapshot_valido(numero=999, cae="12345678909999")
        self.service.cerrar_emision_confirmada(
            **self.datos(), snapshot_fiscal_json=json_text, snapshot_version=version, snapshot_hash=digest,
        )
        resultado = self.service.cerrar_emision_confirmada(
            **self.datos(), snapshot_fiscal_json=otro_json, snapshot_version=otra_version, snapshot_hash=otro_digest,
        )
        self.assertFalse(resultado.ok)
        self.assertEqual(resultado.resultado, ResultadoReconciliacion.CONFLICTO)
        fila = self.filas("factura_arca")[0]
        self.assertEqual(fila[-3:], (json_text, version, digest))

    def test_factura_existente_snapshot_corrupto_no_overwrite(self):
        self._insertar_factura_compatible(snapshot_columnas=("{mal", 1, "0" * 64))
        json_text, version, digest = _snapshot_valido()
        resultado = self.service.cerrar_emision_confirmada(
            **self.datos(), snapshot_fiscal_json=json_text, snapshot_version=version, snapshot_hash=digest,
        )
        self.assertFalse(resultado.ok)
        self.assertEqual(resultado.resultado, ResultadoReconciliacion.CONFLICTO)
        fila = self.filas("factura_arca")[0]
        self.assertEqual(fila[-3:], ("{mal", 1, "0" * 64))

    def test_mismo_cae_conserva_indices_actuales(self):
        json_text, version, digest = _snapshot_valido()
        self.service.cerrar_emision_confirmada(
            **self.datos(), snapshot_fiscal_json=json_text, snapshot_version=version, snapshot_hash=digest,
        )
        self.service.cerrar_emision_confirmada(
            **self.datos(), snapshot_fiscal_json=json_text, snapshot_version=version, snapshot_hash=digest,
        )
        self.assertEqual(len(self.filas("factura_arca")), 1)
        self.assertEqual(self.filas("factura_arca")[0][10], "12345678901234")

    def test_llamada_legacy_sin_snapshot_sigue_funcionando(self):
        resultado = self.service.cerrar_emision_confirmada(**self.datos())
        self.assertTrue(resultado.ok)
        fila = self.filas("factura_arca")[0]
        self.assertEqual(fila[-3:], (None, None, None))


class SnapshotFiscalFlujoCompletoTest(unittest.TestCase):
    """PDF sigue fuera de la transaccion y no afecta el snapshot ya persistido."""

    def _emitir(self, pdf_ok=True, cliente=None, cierre_side_effect=None, ambiente="Homologación"):
        orden = []
        self.snapshot_cierre = None
        self.emitir_en_arca_mock = None
        resultado_arca = {
            "ok": True, "intento_id": 77, "consulta": {"moneda": "PES", "cotizacion": 1.0},
            "fecha_comprobante": "20260823", "numero_comprobante": 123, "punto_venta_num": 5,
            "cae": "12345678901234", "vencimiento_cae": "20260902",
        }
        cliente_final = cliente or (
            20, "", "Cliente Responsable SA", "", "", "Calle 1", "Ciudad",
            "", "", "", "20222222221", "Responsable Inscripto",
        )
        emisor = _emisor_fiscal(ambiente=ambiente)
        ambiente_esperado = ambiente_arca.normalizar_ambiente_arca(ambiente)
        fiscal = {
            "ok": True, "tipo_comprobante": 1, "neto_factura": 1000.0, "alicuota_iva": 21.0,
            "importe_iva_factura": 210.0, "total_factura_fiscal": 1210.0, "importe_exento_factura": 0.0,
            "importe_tot_conc": 0.0, "importe_tributos": 0.0,
            "alicuotas_iva": [{"id": 5, "base_imponible": 1000.0, "importe": 210.0}],
            "condicion_iva_receptor_id": 1,
        }
        resumen = type(
            "Resumen", (), {
                "id": 10, "estado_facturacion": "Pendiente", "cliente_id": 20,
                "total": 1000.0, "conceptos": [object()], "fecha_vencimiento": "",
            },
        )()

        def cierre_default(*_args, **kwargs):
            orden.append("cierre")
            self.assertIsNotNone(kwargs.get("snapshot_fiscal_json"))
            self.assertEqual(kwargs.get("snapshot_version"), 1)
            self.assertIsNotNone(kwargs.get("snapshot_hash"))
            self.snapshot_cierre = json.loads(kwargs["snapshot_fiscal_json"])
            self.assertEqual(self.snapshot_cierre["ambiente"], ambiente_esperado)
            return type("Cierre", (), {"ok": True, "factura_arca_id": 99})()

        cierre_mock = MagicMock(side_effect=cierre_side_effect or cierre_default)
        pdf_resultado = {"ok": True, "ruta_pdf": "ruta.pdf"} if pdf_ok else {"ok": False, "errores": ["pdf"]}

        with (
            patch("services.facturacion_service.ResumenService.obtener", return_value=resumen),
            patch("services.facturacion_service.FacturaArcaService.listar_por_resumen", return_value=[]),
            patch("services.facturacion_service.IntentoEmisionArcaService.listar_activos_por_resumen", return_value=[]),
            patch.object(FacturacionService, "validar_resumen_para_facturar", return_value={"ok": True}),
            patch.object(FacturacionService, "resolver_cliente", return_value={"ok": True, "cliente": cliente_final}),
            patch.object(FacturacionService, "resolver_conceptos", return_value={"ok": True, "resumen": resumen, "conceptos": [object()]}),
            patch.object(FacturacionService, "resolver_emisor", return_value={"ok": True, "emisor_fiscal": emisor}),
            patch.object(FacturacionService, "_resolver_emisor_facturacion_id", return_value=(40, "id")),
            patch.object(
                FacturacionService, "_armar_items_factura_desde_resumen",
                return_value=[{"importe": 1000.0, "cantidad": 1.0, "precio_unitario": 1000.0, "descripcion": "Servicio", "concepto": "Servicio"}],
            ),
            patch.object(FacturacionService, "calcular_importes_fiscales", return_value=fiscal),
            patch("services.facturacion_service.FacturaArcaService.validar_pre_guardado", return_value={"ok": True}),
            patch.object(FacturacionService, "_sumar_importes_items", return_value=1000.0),
            patch.object(FacturacionService, "emitir_en_arca", return_value=resultado_arca) as emitir_en_arca_mock,
            patch("services.facturacion_service.CierreLocalArcaService") as cierre_cls,
            patch.object(FacturacionService, "generar_pdf_fiscal", side_effect=lambda **kwargs: orden.append("pdf") or pdf_resultado),
        ):
            self.emitir_en_arca_mock = emitir_en_arca_mock
            cierre_cls.return_value.cerrar_emision_confirmada.side_effect = cierre_mock
            resultado = FacturacionService.emitir_desde_resumen(
                10, {"tipo_factura": "Factura A", "condicion_iva": "Responsable Inscripto"}
            )
        return resultado, orden, cierre_cls

    def _emitir_real_hasta_bloqueo_arca(self, ambiente):
        self.snapshot_cierre = None
        resumen = type(
            "Resumen", (), {
                "id": 10, "estado_facturacion": "Pendiente", "cliente_id": 20,
                "total": 1000.0, "conceptos": [object()], "fecha_vencimiento": "",
            },
        )()
        cliente = (
            20, "", "Cliente Responsable SA", "", "", "Calle 1", "Ciudad",
            "", "", "", "20222222221", "Responsable Inscripto",
        )
        fiscal = {
            "ok": True, "tipo_comprobante": 1, "neto_factura": 1000.0, "alicuota_iva": 21.0,
            "importe_iva_factura": 210.0, "total_factura_fiscal": 1210.0, "importe_exento_factura": 0.0,
            "importe_tot_conc": 0.0, "importe_tributos": 0.0,
            "alicuotas_iva": [{"id": 5, "base_imponible": 1000.0, "importe": 210.0}],
            "condicion_iva_receptor_id": 1,
        }

        with (
            patch("services.facturacion_service.ResumenService.obtener", return_value=resumen),
            patch("services.facturacion_service.FacturaArcaService.listar_por_resumen", return_value=[]),
            patch("services.facturacion_service.IntentoEmisionArcaService.listar_activos_por_resumen", return_value=[]),
            patch.object(FacturacionService, "validar_resumen_para_facturar", return_value={"ok": True}),
            patch.object(FacturacionService, "resolver_cliente", return_value={"ok": True, "cliente": cliente}),
            patch.object(FacturacionService, "resolver_conceptos", return_value={"ok": True, "resumen": resumen, "conceptos": [object()]}),
            patch.object(FacturacionService, "resolver_emisor", return_value={"ok": True, "emisor_fiscal": _emisor_fiscal(ambiente=ambiente)}),
            patch.object(FacturacionService, "_resolver_emisor_facturacion_id", return_value=(40, "id")),
            patch.object(
                FacturacionService, "_armar_items_factura_desde_resumen",
                return_value=[{"importe": 1000.0, "cantidad": 1.0, "precio_unitario": 1000.0, "descripcion": "Servicio", "concepto": "Servicio"}],
            ),
            patch.object(FacturacionService, "calcular_importes_fiscales", return_value=fiscal),
            patch("services.facturacion_service.FacturaArcaService.validar_pre_guardado", return_value={"ok": True}),
            patch.object(FacturacionService, "_sumar_importes_items", return_value=1000.0),
            patch("services.facturacion_service.HomologacionService.emitir_comprobante_prueba", wraps=HomologacionService.emitir_comprobante_prueba) as emitir_comprobante,
            patch("services.arca.homologacion_service.WSAAService.guardar_tra") as guardar_tra,
            patch("services.arca.homologacion_service.WSAALoginService.login_homologacion") as login,
            patch("services.arca.homologacion_service.WSFEService.fe_comp_ultimo_autorizado") as ultimo,
            patch("services.arca.homologacion_service.WSFEService.fe_cae_solicitar") as solicitar,
            patch("services.arca.homologacion_service.PreenvioArcaService") as preenvio_cls,
            patch("services.facturacion_service.CierreLocalArcaService") as cierre_cls,
            patch.object(FacturacionService, "generar_pdf_fiscal") as pdf,
        ):
            resultado = FacturacionService.emitir_desde_resumen(
                10, {"tipo_factura": "Factura A", "condicion_iva": "Responsable Inscripto"}
            )
        return resultado, cierre_cls, pdf, emitir_comprobante, guardar_tra, login, ultimo, solicitar, preenvio_cls

    def test_pdf_ocurre_despues_del_commit_con_snapshot(self):
        resultado, orden, cierre_cls = self._emitir(pdf_ok=True)
        self.assertEqual(orden, ["cierre", "pdf"])
        self.assertTrue(resultado["ok"])
        cierre_cls.return_value.cerrar_emision_confirmada.assert_called_once()

    def test_emisor_homologacion_propaga_mismo_ambiente_a_emision_y_snapshot(self):
        resultado, _orden, _cierre_cls = self._emitir(ambiente="Homologación")
        self.assertTrue(resultado["ok"])
        ambiente_emitir = self.emitir_en_arca_mock.call_args.kwargs["ambiente"]
        self.assertEqual(ambiente_emitir, ambiente_arca.AMBIENTE_HOMOLOGACION)
        self.assertEqual(self.snapshot_cierre["ambiente"], ambiente_emitir)

    def test_emisor_produccion_bloquea_antes_de_red_intento_y_cierre(self):
        resultado, cierre_cls, pdf, emitir_comprobante, guardar_tra, login, ultimo, solicitar, preenvio_cls = self._emitir_real_hasta_bloqueo_arca("Producción")
        self.assertFalse(resultado["ok"])
        self.assertEqual(resultado["etapa"], "arca")
        self.assertTrue(any("Producción" in error or "Produccion" in error for error in resultado["errores"]))
        self.assertEqual(emitir_comprobante.call_args.kwargs["ambiente"], ambiente_arca.AMBIENTE_PRODUCCION)
        guardar_tra.assert_not_called()
        login.assert_not_called()
        ultimo.assert_not_called()
        solicitar.assert_not_called()
        preenvio_cls.assert_not_called()
        cierre_cls.return_value.cerrar_emision_confirmada.assert_not_called()
        pdf.assert_not_called()
        self.assertIsNone(self.snapshot_cierre)

    def test_ambiente_invalido_bloquea_antes_de_arca_y_cierre(self):
        resultado, cierre_cls, pdf, emitir_comprobante, guardar_tra, login, ultimo, solicitar, preenvio_cls = self._emitir_real_hasta_bloqueo_arca("QA")
        self.assertFalse(resultado["ok"])
        self.assertEqual(resultado["etapa"], "ambiente_arca")
        self.assertTrue(any("Ambiente ARCA inválido" in error for error in resultado["errores"]))
        emitir_comprobante.assert_not_called()
        guardar_tra.assert_not_called()
        login.assert_not_called()
        ultimo.assert_not_called()
        solicitar.assert_not_called()
        preenvio_cls.assert_not_called()
        cierre_cls.return_value.cerrar_emision_confirmada.assert_not_called()
        pdf.assert_not_called()
        self.assertIsNone(self.snapshot_cierre)

    def test_pdf_fallido_no_elimina_snapshot(self):
        resultado, orden, cierre_cls = self._emitir(pdf_ok=False)
        self.assertEqual(resultado["etapa"], "pdf")
        self.assertEqual(orden, ["cierre", "pdf"])
        cierre_cls.return_value.cerrar_emision_confirmada.assert_called_once()
        self.assertEqual(resultado["factura_id"], 99)

    def test_snapshot_invalido_bloquea_cierre_sin_llamar_cierre_local(self):
        cliente_sin_razon_social = (
            20, "", "", "", "", "Calle 1", "Ciudad", "", "", "", "20222222221", "Responsable Inscripto",
        )
        resultado, orden, cierre_cls = self._emitir(cliente=cliente_sin_razon_social)
        self.assertEqual(resultado["etapa"], "snapshot_fiscal")
        self.assertEqual(orden, [])
        cierre_cls.return_value.cerrar_emision_confirmada.assert_not_called()


if __name__ == "__main__":
    unittest.main()
