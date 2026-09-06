"""Tests del constructor puro de snapshot fiscal final desde contexto + autorizacion ARCA.

Bloque 2B.1: el mismo contexto fiscal v1 combinado con autorizaciones ARCA
normalizadas equivalentes (origen fecae_solicitar vs fe_comp_consultar) produce
exactamente el mismo snapshot fiscal final v1, sin consultar maestros, DB ni red.
"""

import dataclasses
import unittest
from copy import deepcopy
from decimal import Decimal

from services.arca.contexto_fiscal_service import ContextoFiscalService
from services.arca.snapshot_fiscal_service import (
    CODIGO_VALIDO,
    SNAPSHOT_VERSION,
    AutorizacionArcaNormalizada,
    SnapshotFiscalError,
    calcular_hash_snapshot,
    construir_snapshot_final_desde_contexto,
    construir_snapshot_final_desde_contexto_persistido,
    normalizar_autorizacion_arca,
    serializar_snapshot_fiscal,
    validar_integridad_snapshot,
)


CREADO_EN = "2026-08-23T12:34:56"


def _contexto_factura_a():
    return {
        "tipo": "contexto_fiscal_arca",
        "version": 1,
        "creado_en": "2026-08-23T12:34:50",
        "ambiente": "HOMOLOGACION",
        "emisor": {
            "emisor_id": 1,
            "emisor_fiscal_id": 1,
            "razon_social": "FM Master SRL",
            "nombre_fantasia": "FM Máster",
            "cuit": "20111111117",
            "condicion_iva": "Responsable Inscripto",
            "domicilio": "Domicilio fiscal 123",
            "ingresos_brutos": "123456",
            "fecha_inicio_actividades": "2020-01-01",
            "punto_venta_num": 5,
        },
        "receptor": {
            "cliente_id": 10,
            "razon_social": "Cliente SA",
            "documento_visible": "20222222221",
            "condicion_iva": "Responsable Inscripto",
            "condicion_iva_receptor_id": 1,
            "domicilio": "Cliente 456 - Localidad",
            "tipo_documento_receptor": 80,
            "documento_receptor": 20222222221,
        },
        "comprobante": {
            "fecha": "2026-08-23",
            "fecha_arca": "20260823",
            "concepto": 1,
            "concepto_descripcion": "1 - Productos",
            "punto_venta_num": 5,
            "tipo_comprobante_num": 1,
            "tipo_comprobante_texto": "Factura A",
            "numero_comprobante_planificado": 123,
            "numero_textual_planificado": "00005-00000123",
            "periodo_servicio_desde": None,
            "periodo_servicio_hasta": None,
            "vencimiento_pago": None,
            "moneda": "PES",
            "cotizacion": Decimal("1"),
        },
        "importes": {
            "total": Decimal("1210.00"),
            "neto": Decimal("1000.00"),
            "iva": Decimal("210.00"),
            "exento": Decimal("0"),
            "no_gravado": Decimal("0"),
            "tributos": Decimal("0"),
        },
        "iva": [
            {
                "id": 5,
                "base_imponible": Decimal("1000.00"),
                "importe": Decimal("210.00"),
                "porcentaje": Decimal("21"),
            }
        ],
        "items": [
            {
                "concepto": "Servicio mensual",
                "descripcion": "Servicio mensual - Publicidad agosto",
                "cantidad": Decimal("1"),
                "precio_unitario": Decimal("1000.00"),
                "subtotal": Decimal("1000.00"),
            }
        ],
    }


def _contexto_factura_c():
    contexto = _contexto_factura_a()
    contexto["emisor"]["condicion_iva"] = "Monotributo"
    contexto["receptor"]["razon_social"] = "Cliente Consumidor"
    contexto["receptor"]["condicion_iva"] = "Consumidor Final"
    contexto["receptor"]["condicion_iva_receptor_id"] = 5
    contexto["receptor"]["documento_visible"] = "0"
    contexto["receptor"]["tipo_documento_receptor"] = 99
    contexto["receptor"]["documento_receptor"] = 0
    contexto["comprobante"]["tipo_comprobante_num"] = 11
    contexto["comprobante"]["tipo_comprobante_texto"] = "Factura C"
    contexto["comprobante"]["numero_comprobante_planificado"] = 124
    contexto["comprobante"]["numero_textual_planificado"] = "00005-00000124"
    contexto["importes"]["total"] = Decimal("1000.00")
    contexto["importes"]["iva"] = Decimal("0")
    contexto["iva"] = []
    return contexto


def _autorizacion_fecae():
    """Autorizacion tal como la obtiene conceptualmente el cierre FECAESolicitar."""
    return {
        "resultado": "A",
        "cae": "12345678901234",
        "vencimiento_cae_arca": "20260902",
        "numero_comprobante": 123,
        "fecha_comprobante_arca": "20260823",
        "punto_venta": 5,
        "tipo_comprobante": 1,
        "cuit_emisor": "20111111117",
        "doc_tipo": 80,
        "doc_nro": 20222222221,
        "importe_total": "1210.00",
        "importe_neto": "1000.00",
        "importe_iva": "210.00",
        "moneda": "PES",
        "cotizacion": "1.00",
        "condicion_iva_receptor_id": 1,
        "origen": "fecae_solicitar",
    }


def _autorizacion_consulta():
    """La misma autorizacion, tal como la obtiene la recuperacion FECompConsultar."""
    return {
        "resultado": "AUTORIZADO",
        "cae": "12345678901234",
        "vencimiento_cae": "2026-09-02",
        "numero_comprobante": 123,
        "fecha_comprobante": "2026-08-23",
        "punto_venta": 5,
        "tipo_comprobante": 1,
        "cuit_emisor": "20111111117",
        "doc_tipo": 80,
        "doc_nro": 20222222221,
        "importe_total": "1210",
        "importe_neto": "1000.0",
        "importe_iva": "210.0",
        "moneda": "PES",
        "cotizacion": "1",
        "condicion_iva_receptor_id": 1,
        "origen": "fe_comp_consultar",
    }


def _autorizacion_fecae_c():
    autorizacion = _autorizacion_fecae()
    autorizacion["cae"] = "12345678901235"
    autorizacion["numero_comprobante"] = 124
    autorizacion["tipo_comprobante"] = 11
    autorizacion["doc_tipo"] = 99
    autorizacion["doc_nro"] = 0
    autorizacion["importe_total"] = "1000.00"
    autorizacion["importe_iva"] = "0.00"
    autorizacion["condicion_iva_receptor_id"] = 5
    return autorizacion


class ConstructorSnapshotFinalDesdeContextoTest(unittest.TestCase):
    def test_factura_a_campos_fiscales(self):
        resultado = construir_snapshot_final_desde_contexto(
            _contexto_factura_a(), _autorizacion_fecae(), "cierre_normal", CREADO_EN
        )
        self.assertTrue(resultado.ok)
        snapshot = resultado.snapshot
        self.assertEqual(snapshot["version"], SNAPSHOT_VERSION)
        self.assertEqual(snapshot["fuente"], "cierre_normal")
        self.assertEqual(snapshot["ambiente"], "HOMOLOGACION")
        self.assertEqual(snapshot["comprobante"]["tipo_comprobante_num"], 1)
        self.assertEqual(snapshot["comprobante"]["tipo_comprobante_texto"], "Factura A")
        self.assertEqual(snapshot["comprobante"]["numero_comprobante_num"], 123)
        self.assertEqual(snapshot["comprobante"]["numero_textual"], "00005-00000123")
        self.assertEqual(snapshot["importes"]["neto"], "1000.00")
        self.assertEqual(snapshot["importes"]["iva"], "210.00")
        self.assertEqual(snapshot["importes"]["total"], "1210.00")
        iva = snapshot["iva"][0]
        self.assertEqual(iva["id"], 5)
        self.assertEqual(iva["base_imponible"], "1000.00")
        self.assertEqual(iva["importe"], "210.00")
        self.assertEqual(iva["porcentaje"], "21.00")
        self.assertEqual(snapshot["receptor"]["condicion_iva"], "Responsable Inscripto")
        self.assertEqual(snapshot["receptor"]["tipo_documento_receptor"], 80)
        self.assertEqual(snapshot["receptor"]["documento_receptor"], 20222222221)

    def test_factura_a_compatible_con_persistencia(self):
        resultado = construir_snapshot_final_desde_contexto(
            _contexto_factura_a(), _autorizacion_fecae(), "cierre_normal", CREADO_EN
        )
        self.assertEqual(resultado.snapshot_version, SNAPSHOT_VERSION)
        self.assertEqual(resultado.snapshot_json, serializar_snapshot_fiscal(resultado.snapshot))
        self.assertEqual(resultado.snapshot_hash, calcular_hash_snapshot(resultado.snapshot_json))
        integridad = validar_integridad_snapshot(
            resultado.snapshot_json, resultado.snapshot_version, resultado.snapshot_hash
        )
        self.assertTrue(integridad.valido)
        self.assertEqual(integridad.codigo, CODIGO_VALIDO)

    def test_factura_c_campos_fiscales(self):
        resultado = construir_snapshot_final_desde_contexto(
            _contexto_factura_c(), _autorizacion_fecae_c(), "cierre_normal", CREADO_EN
        )
        self.assertTrue(resultado.ok)
        snapshot = resultado.snapshot
        self.assertEqual(snapshot["comprobante"]["tipo_comprobante_num"], 11)
        self.assertEqual(snapshot["comprobante"]["tipo_comprobante_texto"], "Factura C")
        self.assertEqual(snapshot["comprobante"]["numero_comprobante_num"], 124)
        self.assertEqual(snapshot["comprobante"]["numero_textual"], "00005-00000124")
        self.assertEqual(snapshot["importes"]["total"], "1000.00")
        self.assertEqual(snapshot["importes"]["neto"], "1000.00")
        self.assertEqual(snapshot["importes"]["iva"], "0.00")
        self.assertEqual(snapshot["iva"], [])
        self.assertEqual(snapshot["emisor"]["condicion_iva"], "Monotributo")
        self.assertEqual(snapshot["receptor"]["condicion_iva"], "Consumidor Final")
        self.assertEqual(snapshot["receptor"]["tipo_documento_receptor"], 99)
        self.assertEqual(snapshot["receptor"]["documento_receptor"], 0)

    def test_campos_documentales_salen_del_contexto(self):
        contexto = _contexto_factura_a()
        resultado = construir_snapshot_final_desde_contexto(
            contexto, _autorizacion_fecae(), "cierre_normal", CREADO_EN
        )
        snapshot = resultado.snapshot
        self.assertEqual(snapshot["emisor"]["razon_social"], "FM Master SRL")
        self.assertEqual(snapshot["emisor"]["nombre_fantasia"], "FM Máster")
        self.assertEqual(snapshot["emisor"]["cuit"], "20111111117")
        self.assertEqual(snapshot["emisor"]["ingresos_brutos"], "123456")
        self.assertEqual(snapshot["emisor"]["fecha_inicio_actividades"], "2020-01-01")
        self.assertEqual(snapshot["receptor"]["razon_social"], "Cliente SA")
        self.assertEqual(snapshot["receptor"]["documento_visible"], "20222222221")
        self.assertEqual(snapshot["receptor"]["domicilio"], "Cliente 456 - Localidad")
        self.assertEqual(snapshot["comprobante"]["fecha"], "2026-08-23")
        self.assertEqual(snapshot["comprobante"]["fecha_arca"], "20260823")
        self.assertEqual(snapshot["comprobante"]["concepto"], 1)
        self.assertEqual(snapshot["comprobante"]["concepto_descripcion"], "1 - Productos")
        self.assertEqual(snapshot["comprobante"]["moneda"], "PES")
        self.assertEqual(snapshot["comprobante"]["cotizacion"], "1.000000")
        self.assertEqual(snapshot["items"][0]["descripcion"], "Servicio mensual - Publicidad agosto")
        self.assertEqual(snapshot["items"][0]["cantidad"], "1.000000")
        self.assertEqual(snapshot["items"][0]["precio_unitario"], "1000.00")
        self.assertEqual(snapshot["items"][0]["subtotal"], "1000.00")

    def test_cae_y_vencimiento_salen_de_arca(self):
        resultado = construir_snapshot_final_desde_contexto(
            _contexto_factura_a(), _autorizacion_fecae(), "cierre_normal", CREADO_EN
        )
        autorizacion = resultado.snapshot["autorizacion"]
        self.assertEqual(autorizacion["cae"], "12345678901234")
        self.assertEqual(autorizacion["vencimiento_cae"], "2026-09-02")
        self.assertEqual(autorizacion["vencimiento_cae_arca"], "20260902")
        self.assertEqual(autorizacion["resultado"], "AUTORIZADO")
        self.assertEqual(autorizacion["tipo_cod_aut"], "E")
        self.assertEqual(autorizacion["cerrado_en"], CREADO_EN)

    def test_creado_en_por_defecto_es_valido(self):
        resultado = construir_snapshot_final_desde_contexto(
            _contexto_factura_a(), _autorizacion_fecae(), "cierre_normal"
        )
        self.assertTrue(resultado.ok)
        self.assertTrue(resultado.snapshot["creado_en"])

    def test_normalizar_autorizacion_idempotente(self):
        normalizada = normalizar_autorizacion_arca(_autorizacion_fecae())
        self.assertIs(normalizar_autorizacion_arca(normalizada), normalizada)
        self.assertIsInstance(normalizada, AutorizacionArcaNormalizada)

    def test_normalizar_autorizacion_rechaza_no_dict(self):
        with self.assertRaisesRegex(SnapshotFiscalError, "autorizacion_arca"):
            normalizar_autorizacion_arca("no-es-un-dict")

    def test_origen_invalido_falla(self):
        autorizacion = _autorizacion_fecae()
        autorizacion["origen"] = "otro_origen"
        with self.assertRaisesRegex(SnapshotFiscalError, "origen"):
            normalizar_autorizacion_arca(autorizacion)


class EquivalenciaOrigenAutorizacionTest(unittest.TestCase):
    def test_autorizaciones_normalizadas_son_equivalentes(self):
        fecae = normalizar_autorizacion_arca(_autorizacion_fecae())
        consulta = normalizar_autorizacion_arca(_autorizacion_consulta())
        datos_fecae = dataclasses.asdict(fecae)
        datos_consulta = dataclasses.asdict(consulta)
        self.assertEqual(datos_fecae.pop("origen"), "fecae_solicitar")
        self.assertEqual(datos_consulta.pop("origen"), "fe_comp_consultar")
        self.assertEqual(datos_fecae, datos_consulta)

    def test_fecae_y_consulta_producen_el_mismo_snapshot(self):
        contexto = _contexto_factura_a()
        desde_fecae = construir_snapshot_final_desde_contexto(
            contexto, _autorizacion_fecae(), "cierre_normal", CREADO_EN
        )
        desde_consulta = construir_snapshot_final_desde_contexto(
            contexto, _autorizacion_consulta(), "cierre_normal", CREADO_EN
        )
        self.assertEqual(desde_fecae.snapshot, desde_consulta.snapshot)
        self.assertEqual(desde_fecae.snapshot_json, desde_consulta.snapshot_json)
        self.assertEqual(desde_fecae.snapshot_hash, desde_consulta.snapshot_hash)

    def test_fuente_distinta_solo_difiere_en_fuente(self):
        contexto = _contexto_factura_a()
        cierre = construir_snapshot_final_desde_contexto(
            contexto, _autorizacion_fecae(), "cierre_normal", CREADO_EN
        )
        recuperacion = construir_snapshot_final_desde_contexto(
            contexto, _autorizacion_consulta(), "recuperacion", CREADO_EN
        )
        snapshot_cierre = deepcopy(cierre.snapshot)
        snapshot_recuperacion = deepcopy(recuperacion.snapshot)
        self.assertEqual(snapshot_cierre.pop("fuente"), "cierre_normal")
        self.assertEqual(snapshot_recuperacion.pop("fuente"), "recuperacion")
        self.assertEqual(snapshot_cierre, snapshot_recuperacion)


class InmutabilidadDesdeContextoPersistidoTest(unittest.TestCase):
    def _contexto_desde_maestros(self, cliente, emisor, resumen):
        contexto = _contexto_factura_a()
        contexto["emisor"]["razon_social"] = emisor["razon_social"]
        contexto["emisor"]["cuit"] = emisor["cuit"]
        contexto["receptor"]["razon_social"] = cliente["razon_social"]
        contexto["receptor"]["documento_visible"] = cliente["documento_visible"]
        contexto["receptor"]["documento_receptor"] = cliente["documento_receptor"]
        contexto["importes"]["total"] = resumen["total"]
        contexto["importes"]["neto"] = resumen["neto"]
        contexto["importes"]["iva"] = resumen["iva"]
        return contexto

    def _autorizacion_desde_contexto(self, contexto):
        validacion = ContextoFiscalService.validar(contexto)
        self.assertTrue(validacion.valido)
        normalizado = validacion.contexto
        return {
            "resultado": "A",
            "cae": "12345678901234",
            "vencimiento_cae_arca": "20260902",
            "numero_comprobante": normalizado["comprobante"]["numero_comprobante_planificado"],
            "fecha_comprobante_arca": normalizado["comprobante"]["fecha"],
            "punto_venta": normalizado["comprobante"]["punto_venta_num"],
            "tipo_comprobante": normalizado["comprobante"]["tipo_comprobante_num"],
            "cuit_emisor": normalizado["emisor"]["cuit"],
            "doc_tipo": normalizado["receptor"]["tipo_documento_receptor"],
            "doc_nro": normalizado["receptor"]["documento_receptor"],
            "importe_total": normalizado["importes"]["total"],
            "importe_neto": normalizado["importes"]["neto"],
            "importe_iva": normalizado["importes"]["iva"],
            "moneda": normalizado["comprobante"]["moneda"],
            "cotizacion": normalizado["comprobante"]["cotizacion"],
            "condicion_iva_receptor_id": None,
            "origen": "fecae_solicitar",
        }

    def test_cambios_posteriores_en_maestros_no_alteran_snapshot(self):
        cliente = {"razon_social": "Cliente SA", "documento_visible": "20222222221", "documento_receptor": 20222222221}
        emisor = {"razon_social": "FM Master SRL", "cuit": "20111111117"}
        resumen = {"total": Decimal("1210.00"), "neto": Decimal("1000.00"), "iva": Decimal("210.00")}

        contexto = self._contexto_desde_maestros(cliente, emisor, resumen)
        validacion = ContextoFiscalService.validar(contexto)
        self.assertTrue(validacion.valido)
        persistido_json = validacion.json_canonico
        persistido_version = validacion.version
        persistido_hash = validacion.hash_calculado

        autorizacion = self._autorizacion_desde_contexto(contexto)
        primero = construir_snapshot_final_desde_contexto_persistido(
            persistido_json, persistido_version, persistido_hash, autorizacion, "cierre_normal", CREADO_EN
        )
        self.assertTrue(primero.ok)

        # Cambios posteriores en los maestros: no deben afectar al contexto persistido.
        cliente["razon_social"] = "Cliente Renombrado SA"
        emisor["cuit"] = "30999999999"
        resumen["total"] = Decimal("9999.00")
        contexto_mutado = self._contexto_desde_maestros(cliente, emisor, resumen)
        self.assertNotEqual(
            ContextoFiscalService.validar(contexto_mutado).hash_calculado, persistido_hash
        )

        segundo = construir_snapshot_final_desde_contexto_persistido(
            persistido_json, persistido_version, persistido_hash, autorizacion, "cierre_normal", CREADO_EN
        )
        self.assertEqual(primero.snapshot_json, segundo.snapshot_json)
        self.assertEqual(primero.snapshot_hash, segundo.snapshot_hash)
        self.assertEqual(segundo.snapshot["receptor"]["razon_social"], "Cliente SA")
        self.assertEqual(segundo.snapshot["emisor"]["cuit"], "20111111117")
        self.assertEqual(segundo.snapshot["importes"]["total"], "1210.00")

    def test_contexto_persistido_hash_corrupto_falla(self):
        validacion = ContextoFiscalService.validar(_contexto_factura_a())
        with self.assertRaisesRegex(SnapshotFiscalError, "persistido invalido"):
            construir_snapshot_final_desde_contexto_persistido(
                validacion.json_canonico, validacion.version, "0" * 64,
                _autorizacion_fecae(), "cierre_normal", CREADO_EN,
            )

    def test_contexto_persistido_json_invalido_falla(self):
        with self.assertRaisesRegex(SnapshotFiscalError, "persistido invalido"):
            construir_snapshot_final_desde_contexto_persistido(
                "{mal", 1, "0" * 64, _autorizacion_fecae(), "cierre_normal", CREADO_EN,
            )

    def test_contexto_persistido_version_desconocida_falla(self):
        validacion = ContextoFiscalService.validar(_contexto_factura_a())
        with self.assertRaisesRegex(SnapshotFiscalError, "persistido invalido"):
            construir_snapshot_final_desde_contexto_persistido(
                validacion.json_canonico, 2, validacion.hash_calculado,
                _autorizacion_fecae(), "cierre_normal", CREADO_EN,
            )


class ErroresConstructorSnapshotFinalTest(unittest.TestCase):
    def _construir(self, contexto, autorizacion):
        return construir_snapshot_final_desde_contexto(
            contexto, autorizacion, "cierre_normal", CREADO_EN
        )

    def test_contexto_invalido_falla(self):
        with self.assertRaisesRegex(SnapshotFiscalError, "contexto_fiscal invalido"):
            self._construir("no-es-un-contexto", _autorizacion_fecae())

    def test_version_contexto_desconocida_falla(self):
        contexto = _contexto_factura_a()
        contexto["version"] = 99
        with self.assertRaisesRegex(SnapshotFiscalError, "version invalida"):
            self._construir(contexto, _autorizacion_fecae())

    def test_autorizacion_sin_cae_falla(self):
        autorizacion = _autorizacion_fecae()
        del autorizacion["cae"]
        with self.assertRaisesRegex(SnapshotFiscalError, "cae"):
            self._construir(_contexto_factura_a(), autorizacion)

    def test_autorizacion_sin_vencimiento_cae_falla(self):
        autorizacion = _autorizacion_fecae()
        del autorizacion["vencimiento_cae_arca"]
        with self.assertRaisesRegex(SnapshotFiscalError, "vencimiento_cae"):
            self._construir(_contexto_factura_a(), autorizacion)

    def test_resultado_no_autorizado_falla(self):
        autorizacion = _autorizacion_fecae()
        autorizacion["resultado"] = "R"
        with self.assertRaisesRegex(SnapshotFiscalError, "resultado"):
            self._construir(_contexto_factura_a(), autorizacion)

    def test_cuit_contradictorio_falla(self):
        autorizacion = _autorizacion_fecae()
        autorizacion["cuit_emisor"] = "30999999999"
        with self.assertRaisesRegex(SnapshotFiscalError, "cuit_emisor contradictorio"):
            self._construir(_contexto_factura_a(), autorizacion)

    def test_punto_venta_contradictorio_falla(self):
        autorizacion = _autorizacion_fecae()
        autorizacion["punto_venta"] = 6
        with self.assertRaisesRegex(SnapshotFiscalError, "punto_venta contradictorio"):
            self._construir(_contexto_factura_a(), autorizacion)

    def test_tipo_comprobante_contradictorio_falla(self):
        autorizacion = _autorizacion_fecae()
        autorizacion["tipo_comprobante"] = 11
        with self.assertRaisesRegex(SnapshotFiscalError, "tipo_comprobante contradictorio"):
            self._construir(_contexto_factura_a(), autorizacion)

    def test_numero_comprobante_contradictorio_falla(self):
        autorizacion = _autorizacion_fecae()
        autorizacion["numero_comprobante"] = 124
        with self.assertRaisesRegex(SnapshotFiscalError, "numero_comprobante contradictorio"):
            self._construir(_contexto_factura_a(), autorizacion)

    def test_fecha_contradictoria_falla(self):
        autorizacion = _autorizacion_fecae()
        autorizacion["fecha_comprobante_arca"] = "20260824"
        with self.assertRaisesRegex(SnapshotFiscalError, "fecha_comprobante contradictorio"):
            self._construir(_contexto_factura_a(), autorizacion)

    def test_doc_tipo_contradictorio_falla(self):
        autorizacion = _autorizacion_fecae()
        autorizacion["doc_tipo"] = 96
        with self.assertRaisesRegex(SnapshotFiscalError, "doc_tipo contradictorio"):
            self._construir(_contexto_factura_a(), autorizacion)

    def test_doc_nro_contradictorio_falla(self):
        autorizacion = _autorizacion_fecae()
        autorizacion["doc_nro"] = 20222222222
        with self.assertRaisesRegex(SnapshotFiscalError, "doc_nro contradictorio"):
            self._construir(_contexto_factura_a(), autorizacion)

    def test_total_contradictorio_falla(self):
        autorizacion = _autorizacion_fecae()
        autorizacion["importe_total"] = "9999.00"
        with self.assertRaisesRegex(SnapshotFiscalError, "importe_total contradictorio"):
            self._construir(_contexto_factura_a(), autorizacion)

    def test_neto_contradictorio_falla(self):
        autorizacion = _autorizacion_fecae()
        autorizacion["importe_neto"] = "999.00"
        with self.assertRaisesRegex(SnapshotFiscalError, "importe_neto contradictorio"):
            self._construir(_contexto_factura_a(), autorizacion)

    def test_iva_contradictorio_falla(self):
        autorizacion = _autorizacion_fecae()
        autorizacion["importe_iva"] = "105.00"
        with self.assertRaisesRegex(SnapshotFiscalError, "importe_iva contradictorio"):
            self._construir(_contexto_factura_a(), autorizacion)

    def test_moneda_contradictoria_falla(self):
        autorizacion = _autorizacion_fecae()
        autorizacion["moneda"] = "USD"
        with self.assertRaisesRegex(SnapshotFiscalError, "moneda contradictorio"):
            self._construir(_contexto_factura_a(), autorizacion)

    def test_cotizacion_contradictoria_falla(self):
        autorizacion = _autorizacion_fecae()
        autorizacion["cotizacion"] = "2.00"
        with self.assertRaisesRegex(SnapshotFiscalError, "cotizacion contradictorio"):
            self._construir(_contexto_factura_a(), autorizacion)

    def test_condicion_iva_contradictoria_falla(self):
        autorizacion = _autorizacion_fecae()
        autorizacion["condicion_iva_receptor_id"] = 5
        with self.assertRaisesRegex(SnapshotFiscalError, "condicion_iva_receptor_id contradictorio"):
            self._construir(_contexto_factura_a(), autorizacion)

    def test_condicion_iva_ausente_en_contexto_se_omite(self):
        contexto = _contexto_factura_a()
        del contexto["receptor"]["condicion_iva_receptor_id"]
        resultado = self._construir(contexto, _autorizacion_fecae())
        self.assertTrue(resultado.ok)

    def test_condicion_iva_ausente_en_autorizacion_se_omite(self):
        autorizacion = _autorizacion_fecae()
        autorizacion["condicion_iva_receptor_id"] = None
        resultado = self._construir(_contexto_factura_a(), autorizacion)
        self.assertTrue(resultado.ok)


if __name__ == "__main__":
    unittest.main()
