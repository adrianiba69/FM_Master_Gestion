import json
import os
import sqlite3
import tempfile
import unittest
from decimal import Decimal

from database import crear_tabla_intentos_emision_arca
from services.arca.contexto_fiscal_service import (
    CODIGO_CONTEXTO_CORRUPTO,
    CODIGO_CONTEXTO_DIFERENTE,
    CODIGO_CONTEXTO_IDEMPOTENTE,
    CODIGO_CONTEXTO_VALIDO,
    ContextoFiscalService,
)
from services.intento_emision_arca_service import IntentoEmisionArcaService


class ContextoFiscalServiceTest(unittest.TestCase):
    def contexto(self):
        return {
            "tipo": "contexto_fiscal_arca",
            "version": 1,
            "creado_en": "2026-08-28T12:30:00",
            "ambiente": "HOMOLOGACION",
            "emisor": {
                "emisor_id": 1,
                "emisor_fiscal_id": 2,
                "razon_social": "Emisor SA",
                "cuit": "20206871629",
                "punto_venta_num": 5,
            },
            "receptor": {
                "cliente_id": 3,
                "razon_social": "Cliente SA",
                "documento_visible": "30712345678",
                "tipo_documento_receptor": 80,
                "documento_receptor": 30712345678,
            },
            "comprobante": {
                "fecha": "20260828",
                "fecha_arca": "20260828",
                "tipo_comprobante_num": 1,
                "numero_comprobante_planificado": 123,
            },
            "importes": {"total": Decimal("1210.00"), "neto": Decimal("1000.00")},
            "iva": [{"id": 5, "base_imponible": Decimal("1000.00")}],
            "items": [{"descripcion": "Servicio", "subtotal": Decimal("1000.00")}],
        }

    def test_contexto_valido_y_canonico(self):
        resultado = ContextoFiscalService.validar(self.contexto())
        self.assertTrue(resultado.valido)
        self.assertEqual(resultado.codigo, CODIGO_CONTEXTO_VALIDO)
        self.assertEqual(resultado.contexto["comprobante"]["fecha"], "2026-08-28")
        self.assertEqual(resultado.contexto["importes"]["total"], "1210")
        self.assertEqual(resultado.hash_calculado, ContextoFiscalService.calcular_hash(resultado.json_canonico))

    def test_orden_de_claves_no_cambia_json_ni_hash(self):
        contexto = self.contexto()
        invertido = {clave: contexto[clave] for clave in reversed(list(contexto))}
        primero = ContextoFiscalService.validar(contexto)
        segundo = ContextoFiscalService.validar(invertido)
        self.assertEqual(primero.json_canonico, segundo.json_canonico)
        self.assertEqual(primero.hash_calculado, segundo.hash_calculado)

    def test_rechaza_float_y_version_desconocida(self):
        contexto = self.contexto()
        contexto["importes"]["total"] = 1210.0
        self.assertFalse(ContextoFiscalService.validar(contexto).valido)
        contexto = self.contexto()
        contexto["version"] = 99
        self.assertEqual(ContextoFiscalService.validar(contexto).codigo, "VERSION_INVALIDA")

    def test_rechaza_secreto_y_fecha_invalida(self):
        contexto = self.contexto()
        contexto["token"] = "no debe persistirse"
        self.assertFalse(ContextoFiscalService.validar(contexto).valido)
        contexto = self.contexto()
        contexto["comprobante"]["fecha"] = "28/08/2026"
        self.assertFalse(ContextoFiscalService.validar(contexto).valido)

    def test_validar_integridad_detecta_hash_corrupto(self):
        validacion = ContextoFiscalService.validar(self.contexto())
        resultado = ContextoFiscalService.validar_integridad(
            validacion.json_canonico, 1, "0" * 64
        )
        self.assertFalse(resultado.valido)
        self.assertEqual(resultado.codigo, "HASH_INVALIDO")


class IntentoContextoFiscalPersistenceTest(unittest.TestCase):
    def setUp(self):
        archivo = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        archivo.close()
        self.ruta_db = archivo.name
        conexion = sqlite3.connect(self.ruta_db)
        crear_tabla_intentos_emision_arca(conexion.cursor())
        conexion.commit()
        conexion.close()
        self.service = IntentoEmisionArcaService(lambda: sqlite3.connect(self.ruta_db))

    def tearDown(self):
        if os.path.exists(self.ruta_db):
            os.remove(self.ruta_db)

    def contexto(self):
        return ContextoFiscalServiceTest().contexto()

    def insertar_intento(self, contexto=None):
        contexto_valores = (None, None, None)
        if contexto:
            validacion = ContextoFiscalService.validar(contexto)
            contexto_valores = (
                validacion.json_canonico,
                1,
                validacion.hash_calculado,
            )
        conexion = sqlite3.connect(self.ruta_db)
        conexion.execute(
            "INSERT INTO intentos_emision_arca(" 
            "resumen_id,cliente_id,emisor_fiscal_id,emisor_id,cuit_emisor,punto_venta," 
            "tipo_comprobante,numero_planificado,fecha_comprobante,concepto,tipo_documento," 
            "documento_receptor,condicion_iva_receptor_id,importe_total,importe_neto,importe_iva," 
            "importe_exento,importe_no_gravado,importe_tributos,moneda,cotizacion,alicuotas_iva," 
            "estado,creado_en,actualizado_en,contexto_fiscal_json,contexto_fiscal_version,contexto_fiscal_hash) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (1, 2, 3, 4, "20206871629", 5, 1, 123, "20260828", 1, 80, 30712345678, 1,
             "1210.00", "1000.00", "210.00", "0.00", "0.00", "0.00", "PES", "1.000000", "[]",
             "PENDIENTE_RECONCILIAR", "2026-08-28", "2026-08-28",
                         *contexto_valores),
        )
        intento_id = conexion.execute("SELECT last_insert_rowid()").fetchone()[0]
        conexion.commit()
        conexion.close()
        return intento_id

    def test_migracion_idempotente_y_historico_null_carga(self):
        conexion = sqlite3.connect(self.ruta_db)
        try:
            crear_tabla_intentos_emision_arca(conexion.cursor())
            crear_tabla_intentos_emision_arca(conexion.cursor())
            nombres = [fila[1] for fila in conexion.execute("PRAGMA table_info(intentos_emision_arca)")]
            self.assertEqual(
                [nombre for nombre in nombres if nombre.startswith("contexto_fiscal_")],
                ["contexto_fiscal_json", "contexto_fiscal_version", "contexto_fiscal_hash"],
            )
            conexion.commit()
        finally:
            conexion.close()
        self.assertIsNotNone(self.service.obtener(self.insertar_intento()))

    def test_guardado_idempotente_diferente_y_corrupcion(self):
        contexto = self.contexto()
        validacion = ContextoFiscalService.validar(contexto)
        intento_id = self.insertar_intento()
        primero = self.service.guardar_contexto_fiscal_si_ausente(
            intento_id, validacion.json_canonico, 1, validacion.hash_calculado
        )
        self.assertTrue(primero.ok)
        segundo = self.service.guardar_contexto_fiscal_si_ausente(
            intento_id, validacion.json_canonico, 1, validacion.hash_calculado
        )
        self.assertEqual(segundo.codigo, CODIGO_CONTEXTO_IDEMPOTENTE)
        contexto_diferente = self.contexto()
        contexto_diferente["emisor"]["razon_social"] = "Otro SA"
        validacion_diferente = ContextoFiscalService.validar(contexto_diferente)
        diferente = self.service.guardar_contexto_fiscal_si_ausente(
            intento_id,
            validacion_diferente.json_canonico,
            1,
            validacion_diferente.hash_calculado,
        )
        self.assertEqual(diferente.codigo, CODIGO_CONTEXTO_DIFERENTE)
        conexion = sqlite3.connect(self.ruta_db)
        conexion.execute("UPDATE intentos_emision_arca SET contexto_fiscal_hash=? WHERE id=?", ("0" * 64, intento_id))
        conexion.commit()
        conexion.close()
        corrupto = self.service.guardar_contexto_fiscal_si_ausente(
            intento_id, validacion.json_canonico, 1, validacion.hash_calculado
        )
        self.assertEqual(corrupto.codigo, CODIGO_CONTEXTO_CORRUPTO)

    def test_columnas_parcialmente_pobladas_detectadas(self):
        contexto = self.contexto()
        validacion = ContextoFiscalService.validar(contexto)
        intento_id = self.insertar_intento()
        conexion = sqlite3.connect(self.ruta_db)
        try:
            conexion.execute(
                "UPDATE intentos_emision_arca SET contexto_fiscal_json=? WHERE id=?",
                (validacion.json_canonico, intento_id),
            )
            conexion.commit()
        finally:
            conexion.close()
        resultado = self.service.guardar_contexto_fiscal_si_ausente(
            intento_id, validacion.json_canonico, 1, validacion.hash_calculado
        )
        self.assertEqual(resultado.codigo, CODIGO_CONTEXTO_CORRUPTO)


if __name__ == "__main__":
    unittest.main()
