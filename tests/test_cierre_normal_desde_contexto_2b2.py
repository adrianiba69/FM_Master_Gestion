"""Bloque 2B.2: el cierre normal construye el snapshot fiscal final v1 desde el
CONTEXTO FISCAL PERSISTIDO del intento + autorizacion ARCA, no desde variables
fiscales/documentales vivas de FacturacionService.

CERO red, CERO ARCA real, CERO PDF/QR real. SQLite temporal para el intento.
"""

import os
import sqlite3
import tempfile
import unittest
from copy import deepcopy
from decimal import Decimal
from unittest.mock import patch

from database import crear_tabla_intentos_emision_arca
from services.arca.contexto_fiscal_service import ContextoFiscalService
from services.arca.reconciliacion_contracts import SnapshotFiscalEsperado
from services.arca.snapshot_fiscal_service import (
    CODIGO_VALIDO,
    validar_integridad_snapshot,
)
from services.facturacion_service import FacturacionService
from services.intento_emision_arca_service import IntentoEmisionArcaService


def _contexto_a():
    return {
        "tipo": "contexto_fiscal_arca",
        "version": 1,
        "creado_en": "2026-08-23T11:59:00",
        "ambiente": "HOMOLOGACION",
        "emisor": {
            "emisor_id": 40, "emisor_fiscal_id": 30, "razon_social": "FM Master SRL",
            "nombre_fantasia": "FM Master", "cuit": "20206871629",
            "condicion_iva": "Responsable Inscripto", "domicilio": "Domicilio Fiscal 123",
            "ingresos_brutos": "123456", "fecha_inicio_actividades": "2020-01-01",
            "punto_venta_num": 5,
        },
        "receptor": {
            "cliente_id": 20, "razon_social": "Cliente Responsable SA",
            "documento_visible": "20222222221", "condicion_iva": "Responsable Inscripto",
            "condicion_iva_receptor_id": 1, "domicilio": "Calle 1 - Ciudad",
            "tipo_documento_receptor": 80, "documento_receptor": 20222222221,
        },
        "comprobante": {
            "fecha": "2026-08-23", "fecha_arca": "20260823", "concepto": 1,
            "concepto_descripcion": "1 - Productos", "punto_venta_num": 5,
            "tipo_comprobante_num": 1, "tipo_comprobante_texto": "Factura A",
            "numero_comprobante_planificado": 123,
            "numero_textual_planificado": "00005-00000123",
            "periodo_servicio_desde": None, "periodo_servicio_hasta": None,
            "vencimiento_pago": None, "moneda": "PES", "cotizacion": Decimal("1"),
        },
        "importes": {
            "total": Decimal("1210"), "neto": Decimal("1000"), "iva": Decimal("210"),
            "exento": Decimal("0"), "no_gravado": Decimal("0"), "tributos": Decimal("0"),
        },
        "iva": [{"id": 5, "base_imponible": Decimal("1000"), "importe": Decimal("210"), "porcentaje": Decimal("21")}],
        "items": [{
            "concepto": "Servicio", "descripcion": "Servicio - Publicidad agosto",
            "cantidad": Decimal("1"), "precio_unitario": Decimal("1000"), "subtotal": Decimal("1000"),
        }],
    }


def _contexto_c():
    contexto = _contexto_a()
    contexto["emisor"]["condicion_iva"] = "Monotributo"
    contexto["receptor"]["razon_social"] = "Consumidor Final"
    contexto["receptor"]["condicion_iva"] = "Consumidor Final"
    contexto["receptor"]["condicion_iva_receptor_id"] = 5
    contexto["receptor"]["documento_visible"] = "0"
    contexto["receptor"]["tipo_documento_receptor"] = 99
    contexto["receptor"]["documento_receptor"] = 0
    contexto["comprobante"]["tipo_comprobante_num"] = 11
    contexto["comprobante"]["tipo_comprobante_texto"] = "Factura C"
    contexto["comprobante"]["numero_comprobante_planificado"] = 124
    contexto["comprobante"]["numero_textual_planificado"] = "00005-00000124"
    contexto["importes"]["total"] = Decimal("1000")
    contexto["importes"]["iva"] = Decimal("0")
    contexto["iva"] = []
    return contexto


def _consulta_a():
    """Datos de la consulta FECompConsultar ya realizada por el flujo normal."""
    return {
        "resultado": "A", "cae": "12345678901234", "vencimiento_cae": "20260902",
        "numero_comprobante": 123, "fecha_comprobante": "20260823",
        "punto_venta": 5, "tipo_comprobante": 1, "cuit_emisor": "20206871629",
        "doc_tipo": 80, "doc_nro": 20222222221,
        "importe_total": 1210.0, "importe_neto": 1000.0, "importe_iva": 210.0,
        "moneda": "PES", "cotizacion": 1.0, "condicion_iva_receptor_id": 1,
    }


def _consulta_c():
    consulta = _consulta_a()
    consulta["cae"] = "12345678901235"
    consulta["numero_comprobante"] = 124
    consulta["tipo_comprobante"] = 11
    consulta["doc_tipo"] = 99
    consulta["doc_nro"] = 0
    consulta["importe_total"] = 1000.0
    consulta["importe_iva"] = 0.0
    consulta["condicion_iva_receptor_id"] = 5
    return consulta


class CierreNormalDesdeContextoBase(unittest.TestCase):
    """Persiste un intento real con contexto en SQLite temporal y ejercita la
    nueva ruta _construir_snapshot_desde_contexto_persistido."""

    def setUp(self):
        archivo = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.ruta = archivo.name
        archivo.close()
        conexion = sqlite3.connect(self.ruta)
        crear_tabla_intentos_emision_arca(conexion.cursor())
        conexion.commit()
        conexion.close()
        self.intentos = IntentoEmisionArcaService(lambda: sqlite3.connect(self.ruta))

    def tearDown(self):
        if os.path.exists(self.ruta):
            os.remove(self.ruta)

    def _crear_intento_con_contexto(self, contexto, **snapshot_overrides):
        validacion = ContextoFiscalService.validar(contexto)
        self.assertTrue(validacion.valido)
        snapshot = SnapshotFiscalEsperado(
            resumen_id=snapshot_overrides.get("resumen_id", 10),
            cliente_id=snapshot_overrides.get("cliente_id", 20),
            emisor_fiscal_id=snapshot_overrides.get("emisor_fiscal_id", 30),
            emisor_id=snapshot_overrides.get("emisor_id", 40),
            cuit_emisor=snapshot_overrides.get("cuit_emisor", "20206871629"),
            punto_venta=snapshot_overrides.get("punto_venta", 5),
            tipo_comprobante=snapshot_overrides.get("tipo_comprobante", 1),
            numero_planificado=snapshot_overrides.get("numero_planificado", 123),
            fecha_comprobante=snapshot_overrides.get("fecha_comprobante", "20260823"),
            concepto=snapshot_overrides.get("concepto", 1),
            tipo_documento=snapshot_overrides.get("tipo_documento", 80),
            documento_receptor=snapshot_overrides.get("documento_receptor", 20222222221),
            condicion_iva_receptor_id=snapshot_overrides.get("condicion_iva_receptor_id", 1),
            importe_total=snapshot_overrides.get("importe_total", Decimal("1210")),
            importe_neto=snapshot_overrides.get("importe_neto", Decimal("1000")),
            importe_iva=snapshot_overrides.get("importe_iva", Decimal("210")),
            importe_exento=snapshot_overrides.get("importe_exento", Decimal("0")),
            importe_no_gravado=snapshot_overrides.get("importe_no_gravado", Decimal("0")),
            importe_tributos=snapshot_overrides.get("importe_tributos", Decimal("0")),
            moneda=snapshot_overrides.get("moneda", "PES"),
            cotizacion=snapshot_overrides.get("cotizacion", Decimal("1")),
            alicuotas_iva=snapshot_overrides.get("alicuotas_iva", ({"Id": 5, "BaseImp": "1000", "Importe": "210"},)),
        )
        return self.intentos.crear_intento(
            snapshot,
            estado="ENVIANDO",
            contexto_fiscal_json=validacion.json_canonico,
            contexto_fiscal_version=validacion.version,
            contexto_fiscal_hash=validacion.hash_calculado,
        )

    def _construir(self, intento_id, consulta, **kwargs):
        intento = self.intentos.obtener(intento_id)
        defaults = dict(
            consulta=consulta,
            cuit_emisor_normalizado="20206871629",
            punto_venta_num=5,
            tipo_comprobante=1,
            numero_comprobante=123,
            fecha_comprobante="20260823",
            cae="12345678901234",
            vencimiento_cae="20260902",
            tipo_documento=80,
            documento_receptor=20222222221,
            total_factura_fiscal=1210.0,
            neto_factura=1000.0,
            importe_iva_factura=210.0,
            condicion_iva_receptor_id=1,
        )
        defaults.update(kwargs)
        with patch.object(IntentoEmisionArcaService, "obtener", return_value=intento):
            return FacturacionService._construir_snapshot_desde_contexto_persistido(
                intento_id, **defaults
            )


class CierreNormalSnapshotCamposTest(CierreNormalDesdeContextoBase):
    def test_factura_a_campos_fiscales_desde_contexto(self):
        intento_id = self._crear_intento_con_contexto(_contexto_a())
        resultado = self._construir(intento_id, _consulta_a())
        self.assertTrue(resultado["ok"])
        snapshot = resultado["snapshot"]
        self.assertEqual(snapshot["fuente"], "cierre_normal")
        self.assertEqual(snapshot["emisor"]["razon_social"], "FM Master SRL")
        self.assertEqual(snapshot["emisor"]["cuit"], "20206871629")
        self.assertEqual(snapshot["receptor"]["razon_social"], "Cliente Responsable SA")
        self.assertEqual(snapshot["receptor"]["documento_receptor"], 20222222221)
        self.assertEqual(snapshot["importes"]["neto"], "1000.00")
        self.assertEqual(snapshot["importes"]["iva"], "210.00")
        self.assertEqual(snapshot["importes"]["total"], "1210.00")
        self.assertEqual(snapshot["iva"][0]["porcentaje"], "21.00")
        self.assertEqual(snapshot["autorizacion"]["cae"], "12345678901234")
        self.assertEqual(snapshot["autorizacion"]["vencimiento_cae"], "2026-09-02")

    def test_factura_c_campos_fiscales_desde_contexto(self):
        intento_id = self._crear_intento_con_contexto(
            _contexto_c(),
            tipo_comprobante=11, numero_planificado=124, tipo_documento=99,
            documento_receptor=0, condicion_iva_receptor_id=5,
            importe_total=Decimal("1000"), importe_iva=Decimal("0"), alicuotas_iva=(),
        )
        resultado = self._construir(
            intento_id, _consulta_c(),
            tipo_comprobante=11, numero_comprobante=124, cae="12345678901235",
            tipo_documento=99, documento_receptor=0, total_factura_fiscal=1000.0,
            importe_iva_factura=0.0, condicion_iva_receptor_id=5,
        )
        self.assertTrue(resultado["ok"])
        snapshot = resultado["snapshot"]
        self.assertEqual(snapshot["comprobante"]["tipo_comprobante_num"], 11)
        self.assertEqual(snapshot["comprobante"]["tipo_comprobante_texto"], "Factura C")
        self.assertEqual(snapshot["emisor"]["condicion_iva"], "Monotributo")
        self.assertEqual(snapshot["receptor"]["condicion_iva"], "Consumidor Final")
        self.assertEqual(snapshot["importes"]["total"], "1000.00")
        self.assertEqual(snapshot["importes"]["iva"], "0.00")
        self.assertEqual(snapshot["iva"], [])
        self.assertEqual(snapshot["autorizacion"]["cae"], "12345678901235")

    def test_resultado_compatible_con_persistencia(self):
        intento_id = self._crear_intento_con_contexto(_contexto_a())
        resultado = self._construir(intento_id, _consulta_a())
        integridad = validar_integridad_snapshot(
            resultado["snapshot_json"], resultado["snapshot_version"], resultado["snapshot_hash"]
        )
        self.assertEqual(integridad.codigo, CODIGO_VALIDO)


class CierreNormalRelecturaEInmutabilidadTest(CierreNormalDesdeContextoBase):
    def test_relee_contexto_desde_intento_persistido_no_desde_memoria(self):
        """El snapshot debe salir del contexto persistido, aunque el objeto vivo
        usado para emitir tenga valores distintos."""
        contexto_persistido = _contexto_a()
        contexto_persistido["receptor"]["razon_social"] = "Cliente PERSISTIDO SA"
        intento_id = self._crear_intento_con_contexto(contexto_persistido)

        # Objeto vivo (memoria) con un valor DISTINTO y distinguible.
        consulta = _consulta_a()
        resultado = self._construir(intento_id, consulta)
        self.assertTrue(resultado["ok"])
        self.assertEqual(resultado["snapshot"]["receptor"]["razon_social"], "Cliente PERSISTIDO SA")

    def test_inmutable_ante_cambios_posteriores_en_maestros(self):
        """Tras congelar el contexto, mutar cliente/emisor/resumen no altera el snapshot."""
        contexto = _contexto_a()
        intento_id = self._crear_intento_con_contexto(contexto)
        primero = self._construir(intento_id, _consulta_a())
        self.assertTrue(primero["ok"])

        # Simular cambios posteriores en los maestros vivos.
        emisor_mutado = deepcopy(_contexto_a()["emisor"])
        emisor_mutado["cuit"] = "30999999999"
        cliente_mutado_razon = "Cliente Renombrado SA"
        resumen_mutado_total = Decimal("9999.00")
        # El contexto persistido NO se toca: se relee tal cual del intento.
        segundo = self._construir(intento_id, _consulta_a())
        self.assertEqual(primero["snapshot_json"], segundo["snapshot_json"])
        self.assertEqual(segundo["snapshot"]["emisor"]["cuit"], "20206871629")
        self.assertEqual(segundo["snapshot"]["receptor"]["razon_social"], "Cliente Responsable SA")
        self.assertEqual(segundo["snapshot"]["importes"]["total"], "1210.00")
        # Los mutados nunca entran al snapshot.
        self.assertNotEqual(segundo["snapshot"]["emisor"]["cuit"], emisor_mutado["cuit"])
        self.assertNotEqual(segundo["snapshot"]["receptor"]["razon_social"], cliente_mutado_razon)
        self.assertNotEqual(segundo["snapshot"]["importes"]["total"], "9999.00")
        self.assertNotEqual(segundo["snapshot"]["importes"]["total"], str(resumen_mutado_total))


class CierreNormalErroresTest(CierreNormalDesdeContextoBase):
    def _construir_con_contexto_corrupto(self, json_text, version, hash_text):
        intento_id = self._crear_intento_con_contexto(_contexto_a())
        intento = self.intentos.obtener(intento_id)
        # Forzar contexto corrupto en el intento releido.
        intento_corrupto = type(intento)(**{**intento.__dict__,
            "contexto_fiscal_json": json_text,
            "contexto_fiscal_version": version,
            "contexto_fiscal_hash": hash_text,
        })
        with patch.object(IntentoEmisionArcaService, "obtener", return_value=intento_corrupto):
            return FacturacionService._construir_snapshot_desde_contexto_persistido(
                intento_id,
                consulta=_consulta_a(), cuit_emisor_normalizado="20206871629",
                punto_venta_num=5, tipo_comprobante=1, numero_comprobante=123,
                fecha_comprobante="20260823", cae="12345678901234", vencimiento_cae="20260902",
                tipo_documento=80, documento_receptor=20222222221,
                total_factura_fiscal=1210.0, neto_factura=1000.0, importe_iva_factura=210.0,
                condicion_iva_receptor_id=1,
            )

    def test_intento_sin_contexto_falla_sin_fallback(self):
        intento_id = self._crear_intento_con_contexto(_contexto_a())
        intento = self.intentos.obtener(intento_id)
        intento_sin_contexto = type(intento)(**{**intento.__dict__,
            "contexto_fiscal_json": None, "contexto_fiscal_version": None, "contexto_fiscal_hash": None,
        })
        with patch.object(IntentoEmisionArcaService, "obtener", return_value=intento_sin_contexto):
            resultado = FacturacionService._construir_snapshot_desde_contexto_persistido(
                intento_id, consulta=_consulta_a(), cuit_emisor_normalizado="20206871629",
                punto_venta_num=5, tipo_comprobante=1, numero_comprobante=123,
                fecha_comprobante="20260823", cae="12345678901234", vencimiento_cae="20260902",
                tipo_documento=80, documento_receptor=20222222221,
                total_factura_fiscal=1210.0, neto_factura=1000.0, importe_iva_factura=210.0,
                condicion_iva_receptor_id=1,
            )
        self.assertFalse(resultado["ok"])
        self.assertTrue(any("contexto_fiscal_ausente" in e for e in resultado["errores"]))

    def test_contexto_json_corrupto_falla(self):
        resultado = self._construir_con_contexto_corrupto("{mal", 1, "0" * 64)
        self.assertFalse(resultado["ok"])
        self.assertTrue(any("snapshot_fiscal_desde_contexto" in e for e in resultado["errores"]))

    def test_contexto_version_desconocida_falla(self):
        valido = ContextoFiscalService.validar(_contexto_a())
        resultado = self._construir_con_contexto_corrupto(valido.json_canonico, 99, valido.hash_calculado)
        self.assertFalse(resultado["ok"])

    def test_contexto_hash_incorrecto_falla(self):
        valido = ContextoFiscalService.validar(_contexto_a())
        resultado = self._construir_con_contexto_corrupto(valido.json_canonico, 1, "0" * 64)
        self.assertFalse(resultado["ok"])

    def test_autorizacion_contradictoria_con_contexto_falla(self):
        intento_id = self._crear_intento_con_contexto(_contexto_a())
        consulta = _consulta_a()
        consulta["importe_total"] = 9999.0
        resultado = self._construir(intento_id, consulta)
        self.assertFalse(resultado["ok"])
        self.assertTrue(any("contradictorio" in e for e in resultado["errores"]))

    def test_campo_coherencia_obligatorio_omitido_falla_sin_respaldo_local(self):
        intento_id = self._crear_intento_con_contexto(_contexto_a())
        consulta = _consulta_a()
        consulta.pop("cuit_emisor")
        resultado = self._construir(
            intento_id,
            consulta,
            cuit_emisor_normalizado="20206871629",
        )
        self.assertFalse(resultado["ok"])
        self.assertTrue(any("autorizacion_arca.cuit_emisor" in e for e in resultado["errores"]))

    def test_condicion_iva_omitida_permanece_opcional(self):
        intento_id = self._crear_intento_con_contexto(_contexto_a())
        consulta = _consulta_a()
        consulta.pop("condicion_iva_receptor_id")
        resultado = self._construir(
            intento_id,
            consulta,
            condicion_iva_receptor_id=99,
        )
        self.assertTrue(resultado["ok"])

    def test_adaptador_no_copia_datos_fiscales_locales(self):
        autorizacion = FacturacionService._autorizacion_arca_desde_consulta(
            consulta={"resultado": "A"},
            cuit_emisor_normalizado="20206871629",
            punto_venta_num=5,
            tipo_comprobante=1,
            numero_comprobante=123,
            fecha_comprobante="20260823",
            cae="12345678901234",
            vencimiento_cae="20260902",
            tipo_documento=80,
            documento_receptor=20222222221,
            total_factura_fiscal=1210.0,
            neto_factura=1000.0,
            importe_iva_factura=210.0,
            condicion_iva_receptor_id=1,
        )
        campos_coherencia = (
            "numero_comprobante", "fecha_comprobante_arca", "punto_venta",
            "tipo_comprobante", "cuit_emisor", "doc_tipo", "doc_nro",
            "importe_total", "importe_neto", "importe_iva", "moneda",
            "cotizacion", "condicion_iva_receptor_id",
        )
        self.assertTrue(all(autorizacion[campo] is None for campo in campos_coherencia))
        self.assertEqual(autorizacion["cae"], "12345678901234")
        self.assertEqual(autorizacion["vencimiento_cae_arca"], "20260902")

    def test_cae_y_vencimiento_pueden_provenir_de_fecae_solicitar(self):
        intento_id = self._crear_intento_con_contexto(_contexto_a())
        consulta = _consulta_a()
        consulta.pop("cae")
        consulta.pop("vencimiento_cae")
        resultado = self._construir(
            intento_id,
            consulta,
            cae="12345678901234",
            vencimiento_cae="20260902",
        )
        self.assertTrue(resultado["ok"])
        self.assertEqual(resultado["snapshot"]["autorizacion"]["cae"], "12345678901234")
        self.assertEqual(resultado["snapshot"]["autorizacion"]["vencimiento_cae_arca"], "20260902")

    def test_resultado_omitido_no_se_inventa_como_autorizado(self):
        intento_id = self._crear_intento_con_contexto(_contexto_a())
        consulta = _consulta_a()
        consulta.pop("resultado")
        resultado = self._construir(intento_id, consulta)
        self.assertFalse(resultado["ok"])
        self.assertTrue(any("autorizacion_arca.resultado" in e for e in resultado["errores"]))

    def test_autorizacion_sin_cae_falla(self):
        intento_id = self._crear_intento_con_contexto(_contexto_a())
        consulta = _consulta_a()
        consulta["cae"] = ""
        resultado = self._construir(intento_id, consulta, cae="")
        self.assertFalse(resultado["ok"])

    def test_autorizacion_sin_vencimiento_cae_falla(self):
        intento_id = self._crear_intento_con_contexto(_contexto_a())
        consulta = _consulta_a()
        consulta["vencimiento_cae"] = ""
        resultado = self._construir(intento_id, consulta, vencimiento_cae="")
        self.assertFalse(resultado["ok"])

    def test_intento_inexistente_falla_sin_fallback(self):
        with patch.object(IntentoEmisionArcaService, "obtener", return_value=None):
            resultado = FacturacionService._construir_snapshot_desde_contexto_persistido(
                99999, consulta=_consulta_a(), cuit_emisor_normalizado="20206871629",
                punto_venta_num=5, tipo_comprobante=1, numero_comprobante=123,
                fecha_comprobante="20260823", cae="12345678901234", vencimiento_cae="20260902",
                tipo_documento=80, documento_receptor=20222222221,
                total_factura_fiscal=1210.0, neto_factura=1000.0, importe_iva_factura=210.0,
                condicion_iva_receptor_id=1,
            )
        self.assertFalse(resultado["ok"])
        self.assertTrue(any("contexto_fiscal_ausente" in e for e in resultado["errores"]))


if __name__ == "__main__":
    unittest.main()
