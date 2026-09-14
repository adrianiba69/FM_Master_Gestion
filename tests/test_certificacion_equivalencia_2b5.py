import copy
import json
import os
import sqlite3
import tempfile
import unittest
from dataclasses import replace
from datetime import datetime
from decimal import Decimal
from unittest.mock import patch

from database import crear_tabla_intentos_emision_arca
from services.arca.cierre_local_arca_service import CierreLocalArcaService
from services.arca.contexto_fiscal_service import ContextoFiscalService
from services.arca.recuperacion_local_service import RecuperacionLocalArcaService
from services.arca.reconciliacion_contracts import ResultadoReconciliacion, SnapshotFiscalEsperado
from services.arca.reconciliacion_service import ReconciliacionArcaService
from services.arca.snapshot_fiscal_pdf_adapter import construir_datos_pdf_desde_snapshot
from services.arca.snapshot_fiscal_service import (
    CODIGO_VALIDO,
    calcular_hash_snapshot,
    serializar_snapshot_fiscal,
    validar_integridad_snapshot,
)
from services.facturacion_service import FacturacionService
from services.intento_emision_arca_service import IntentoEmisionArcaService
from tests.test_cierre_normal_desde_contexto_2b2 import _consulta_a, _consulta_c, _contexto_a, _contexto_c


class CertificacionEquivalencia2B5Test(unittest.TestCase):
    CAMPOS_METADATA = {"fuente", "creado_en", "autorizacion.cerrado_en"}

    def setUp(self):
        self.rutas = []

    def tearDown(self):
        for ruta in self.rutas:
            if os.path.exists(ruta):
                os.remove(ruta)

    def _nueva_base(self):
        archivo = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        archivo.close()
        self.rutas.append(archivo.name)
        conexion = sqlite3.connect(archivo.name)
        conexion.executescript(
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
            INSERT INTO resumenes VALUES(10, 'Pendiente', '', '', '', '');
            """
        )
        crear_tabla_intentos_emision_arca(conexion.cursor())
        conexion.commit()
        conexion.close()
        factory = lambda: sqlite3.connect(archivo.name)
        return archivo.name, factory, IntentoEmisionArcaService(factory)

    @staticmethod
    def _snapshot_esperado(contexto):
        receptor = contexto["receptor"]
        emisor = contexto["emisor"]
        comprobante = contexto["comprobante"]
        importes = contexto["importes"]
        return SnapshotFiscalEsperado(
            resumen_id=10,
            cliente_id=receptor["cliente_id"],
            emisor_fiscal_id=emisor["emisor_fiscal_id"],
            emisor_id=emisor["emisor_id"],
            cuit_emisor=emisor["cuit"],
            punto_venta=comprobante["punto_venta_num"],
            tipo_comprobante=comprobante["tipo_comprobante_num"],
            numero_planificado=comprobante["numero_comprobante_planificado"],
            fecha_comprobante=comprobante["fecha_arca"],
            concepto=comprobante["concepto"],
            tipo_documento=receptor["tipo_documento_receptor"],
            documento_receptor=receptor["documento_receptor"],
            condicion_iva_receptor_id=receptor["condicion_iva_receptor_id"],
            importe_total=Decimal(str(importes["total"])),
            importe_neto=Decimal(str(importes["neto"])),
            importe_iva=Decimal(str(importes["iva"])),
            importe_exento=Decimal(str(importes["exento"])),
            importe_no_gravado=Decimal(str(importes["no_gravado"])),
            importe_tributos=Decimal(str(importes["tributos"])),
            moneda=comprobante["moneda"],
            cotizacion=Decimal(str(comprobante["cotizacion"])),
            alicuotas_iva=tuple(contexto["iva"]),
        )

    def _crear_intento(self, intentos, contexto):
        validacion = ContextoFiscalService.validar(contexto)
        self.assertTrue(validacion.valido, validacion.errores)
        intento_id = intentos.crear_intento(
            self._snapshot_esperado(contexto),
            estado="PENDIENTE_RECONCILIAR",
            contexto_fiscal_json=validacion.json_canonico,
            contexto_fiscal_version=validacion.version,
            contexto_fiscal_hash=validacion.hash_calculado,
        )
        return intento_id, intentos.obtener(intento_id)

    @staticmethod
    def _fila_snapshot(ruta):
        conexion = sqlite3.connect(ruta)
        try:
            return conexion.execute(
                "SELECT id, snapshot_fiscal_json, snapshot_version, snapshot_hash FROM factura_arca"
            ).fetchone()
        finally:
            conexion.close()

    def _validar_persistencia(self, fila):
        _, json_text, version, hash_text = fila
        integridad = validar_integridad_snapshot(json_text, version, hash_text)
        self.assertEqual(integridad.codigo, CODIGO_VALIDO)
        self.assertEqual(version, 1)
        self.assertEqual(json_text, serializar_snapshot_fiscal(integridad.snapshot))
        self.assertEqual(hash_text, calcular_hash_snapshot(json_text))
        self.assertEqual(hash_text, calcular_hash_snapshot(serializar_snapshot_fiscal(integridad.snapshot)))
        return integridad.snapshot

    @classmethod
    def _sin_metadata(cls, snapshot):
        fiscal = copy.deepcopy(snapshot)
        fiscal.pop("fuente")
        fiscal.pop("creado_en")
        fiscal["autorizacion"].pop("cerrado_en")
        return fiscal

    @classmethod
    def _diferencias(cls, normal, recuperado):
        diferencias = set()
        if normal["fuente"] != recuperado["fuente"]:
            diferencias.add("fuente")
        if normal["creado_en"] != recuperado["creado_en"]:
            diferencias.add("creado_en")
        if normal["autorizacion"]["cerrado_en"] != recuperado["autorizacion"]["cerrado_en"]:
            diferencias.add("autorizacion.cerrado_en")
        return diferencias

    def _camino_normal(self, contexto, consulta):
        ruta, factory, intentos = self._nueva_base()
        intento_id, intento = self._crear_intento(intentos, contexto)
        comprobante = contexto["comprobante"]
        receptor = contexto["receptor"]
        importes = contexto["importes"]

        class FechaCierreNormal(datetime):
            @classmethod
            def now(cls, tz=None):
                return cls(2030, 1, 2, 3, 4, 5)

        with (
            patch.object(IntentoEmisionArcaService, "obtener", return_value=intento),
            patch("services.arca.snapshot_fiscal_service.datetime", FechaCierreNormal),
        ):
            construido = FacturacionService._construir_snapshot_desde_contexto_persistido(
                intento_id=intento_id,
                consulta=consulta,
                cuit_emisor_normalizado="20999999999",
                punto_venta_num=99,
                tipo_comprobante=99,
                numero_comprobante=999,
                fecha_comprobante="19990101",
                cae="",
                vencimiento_cae="",
                tipo_documento=96,
                documento_receptor=99999999,
                total_factura_fiscal=999.0,
                neto_factura=999.0,
                importe_iva_factura=999.0,
                condicion_iva_receptor_id=99,
            )
        self.assertTrue(construido["ok"], construido.get("errores"))

        cierre = CierreLocalArcaService(factory).cerrar_emision_confirmada(
            intento_id=intento_id,
            resumen_id=10,
            cliente_id=receptor["cliente_id"],
            emisor_id=contexto["emisor"]["emisor_id"],
            fecha=comprobante["fecha_arca"],
            punto_venta=str(comprobante["punto_venta_num"]),
            tipo_comprobante=comprobante["tipo_comprobante_texto"],
            importe_total=float(Decimal(str(importes["total"]))),
            numero_factura=comprobante["numero_textual_planificado"],
            cae=consulta["cae"],
            vencimiento_cae=consulta["vencimiento_cae"],
            tipo_documento_receptor=receptor["tipo_documento_receptor"],
            documento_receptor=receptor["documento_receptor"],
            snapshot_fiscal_json=construido["snapshot_json"],
            snapshot_version=construido["snapshot_version"],
            snapshot_hash=construido["snapshot_hash"],
        )
        self.assertTrue(cierre.ok, cierre.mensaje)
        primera = self._fila_snapshot(ruta)

        repetido = CierreLocalArcaService(factory).cerrar_emision_confirmada(
            intento_id=intento_id,
            resumen_id=10,
            cliente_id=receptor["cliente_id"],
            emisor_id=contexto["emisor"]["emisor_id"],
            fecha=comprobante["fecha_arca"],
            punto_venta=str(comprobante["punto_venta_num"]),
            tipo_comprobante=comprobante["tipo_comprobante_texto"],
            importe_total=float(Decimal(str(importes["total"]))),
            numero_factura=comprobante["numero_textual_planificado"],
            cae=consulta["cae"],
            vencimiento_cae=consulta["vencimiento_cae"],
            tipo_documento_receptor=receptor["tipo_documento_receptor"],
            documento_receptor=receptor["documento_receptor"],
            snapshot_fiscal_json=construido["snapshot_json"],
            snapshot_version=construido["snapshot_version"],
            snapshot_hash=construido["snapshot_hash"],
        )
        self.assertTrue(repetido.ok, repetido.mensaje)
        self.assertEqual(repetido.factura_arca_id, cierre.factura_arca_id)
        self.assertEqual(self._fila_snapshot(ruta), primera)
        return self._validar_persistencia(primera), primera

    def _camino_recuperacion(self, contexto, consulta):
        ruta, factory, intentos = self._nueva_base()
        intento_id, _ = self._crear_intento(intentos, contexto)
        recuperacion = RecuperacionLocalArcaService(factory, intentos)
        consultas = []

        def consultar(**kwargs):
            consultas.append(kwargs)
            return {"ok": True, **consulta}

        class EmisorTecnico:
            @staticmethod
            def obtener(emisor_id):
                return (
                    emisor_id, "Emisor vivo mutado", "", "20999999999", "", "", 99, 1, "",
                    "Homologacion", "", "", "", "cert.fake", "clave.fake", "C:/trabajo-fake", 1,
                )

        reconciliacion = ReconciliacionArcaService(
            intentos,
            EmisorTecnico,
            consultar,
            recuperacion,
        )
        resultado = reconciliacion.reconciliar_intento(intento_id)
        self.assertTrue(resultado.ok)
        self.assertEqual(resultado.resultado, ResultadoReconciliacion.AUTORIZADO)
        primera = self._fila_snapshot(ruta)

        repetido = reconciliacion.reconciliar_intento(intento_id)
        self.assertTrue(repetido.ok)
        self.assertEqual(repetido.resultado, ResultadoReconciliacion.AUTORIZADO)
        self.assertEqual(repetido.factura_arca_id, resultado.factura_arca_id)
        self.assertEqual(len(consultas), 1)
        self.assertEqual(self._fila_snapshot(ruta), primera)
        return self._validar_persistencia(primera), primera

    def _certificar(self, contexto, consulta):
        objetos_vivos = {
            "emisor": {"razon_social": "Emisor mutado", "domicilio": "Otro", "iibb": "999"},
            "cliente": {"razon_social": "Cliente mutado", "documento": "99999999"},
            "resumen": {"descripcion": "Resumen mutado", "importe": Decimal("999")},
            "servicio": {"descripcion": "Servicio mutado", "importe": Decimal("999")},
        }
        self.assertNotEqual(objetos_vivos["emisor"]["razon_social"], contexto["emisor"]["razon_social"])

        normal, fila_normal = self._camino_normal(contexto, consulta)
        recuperado, fila_recuperado = self._camino_recuperacion(contexto, consulta)

        self.assertEqual(self._sin_metadata(normal), self._sin_metadata(recuperado))
        diferencias = self._diferencias(normal, recuperado)
        self.assertEqual(diferencias, self.CAMPOS_METADATA)
        self.assertEqual(normal["fuente"], "cierre_normal")
        self.assertEqual(recuperado["fuente"], "recuperacion")
        self.assertNotEqual(fila_normal[3], fila_recuperado[3])
        self.assertNotEqual(fila_normal[1], fila_recuperado[1])
        self.assertEqual(
            construir_datos_pdf_desde_snapshot(normal),
            construir_datos_pdf_desde_snapshot(recuperado),
        )
        self.assertEqual(normal["emisor"]["razon_social"], contexto["emisor"]["razon_social"])
        self.assertEqual(normal["receptor"]["razon_social"], contexto["receptor"]["razon_social"])
        self.assertEqual(normal["items"], recuperado["items"])
        return normal, recuperado

    def test_equivalencia_fiscal_documental_factura_a(self):
        contexto = _contexto_a()
        contexto["comprobante"].update(
            periodo_servicio_desde="2026-08-01",
            periodo_servicio_hasta="2026-08-31",
            vencimiento_pago="2026-09-10",
        )
        normal, recuperado = self._certificar(contexto, _consulta_a())
        for snapshot in (normal, recuperado):
            self.assertEqual(snapshot["comprobante"]["tipo_comprobante_texto"], "Factura A")
            self.assertEqual(snapshot["receptor"]["condicion_iva"], "Responsable Inscripto")
            self.assertEqual(snapshot["importes"], {
                "exento": "0.00", "iva": "210.00", "neto": "1000.00",
                "no_gravado": "0.00", "total": "1210.00", "tributos": "0.00",
            })
            self.assertEqual(snapshot["iva"][0]["porcentaje"], "21.00")
            self.assertEqual(snapshot["autorizacion"]["cae"], "12345678901234")

    def test_equivalencia_fiscal_documental_factura_c(self):
        contexto = _contexto_c()
        contexto["comprobante"].update(
            periodo_servicio_desde="2026-08-01",
            periodo_servicio_hasta="2026-08-31",
            vencimiento_pago="2026-09-10",
        )
        normal, recuperado = self._certificar(contexto, _consulta_c())
        for snapshot in (normal, recuperado):
            self.assertEqual(snapshot["comprobante"]["tipo_comprobante_texto"], "Factura C")
            self.assertEqual(snapshot["receptor"]["condicion_iva"], "Consumidor Final")
            self.assertEqual(snapshot["importes"]["total"], "1000.00")
            self.assertEqual(snapshot["importes"]["iva"], "0.00")
            self.assertEqual(snapshot["iva"], [])
            self.assertEqual(snapshot["autorizacion"]["cae"], "12345678901235")

    def test_json_hash_difieren_solo_por_metadatos_intencionales(self):
        normal, recuperado = self._certificar(_contexto_a(), _consulta_a())
        self.assertNotEqual(serializar_snapshot_fiscal(normal), serializar_snapshot_fiscal(recuperado))
        self.assertEqual(self._sin_metadata(normal), self._sin_metadata(recuperado))


if __name__ == "__main__":
    unittest.main()