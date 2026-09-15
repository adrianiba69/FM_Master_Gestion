import os
import sqlite3
import tempfile
import unittest
from copy import deepcopy
from dataclasses import replace
from decimal import Decimal

from database import crear_tabla_intentos_emision_arca
from services.arca import ambiente_arca
from services.arca.contexto_fiscal_service import ContextoFiscalService
from services.arca.reconciliacion_contracts import (
    EstadoIntentoEmision,
    ResultadoReconciliacion,
    SnapshotFiscalEsperado,
)
from services.arca.reconciliacion_service import ReconciliacionArcaService
from services.arca.recuperacion_local_service import ResultadoRecuperacionLocal
from services.intento_emision_arca_service import IntentoEmisionArcaService


class EmisorTecnicoFake:
    def __init__(self):
        self.llamadas = []

    def obtener(self, emisor_id):
        self.llamadas.append(emisor_id)
        return (
            30, "Nombre actual mutado", "", "20999999999", "", "", 99, 1, "",
            "Homologacion", "", "", "", "cert.crt", "clave.key", "C:/trabajo", 1,
        )


class ConsultaSecuencialFake:
    def __init__(self, *respuestas):
        self.respuestas = list(respuestas)
        self.llamadas = []

    def __call__(self, **kwargs):
        self.llamadas.append(kwargs)
        respuesta = self.respuestas.pop(0)
        if isinstance(respuesta, Exception):
            raise respuesta
        return respuesta


class RecuperacionMarcadoraFake:
    def __init__(self, intentos):
        self.intentos = intentos
        self.llamadas = []

    def registrar_factura_recuperada(self, intento, snapshot, consulta):
        self.llamadas.append((intento, snapshot, consulta))
        self.intentos.guardar_resultado_reconciliacion(
            intento.id,
            ResultadoReconciliacion.AUTORIZADO,
            cae=consulta["cae"],
            vencimiento_cae=consulta["vencimiento_cae"],
            factura_arca_id=88,
        )
        return ResultadoRecuperacionLocal(ResultadoReconciliacion.AUTORIZADO, 88, True)


class ReconciliacionContexto2B4Test(unittest.TestCase):
    def setUp(self):
        archivo = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        archivo.close()
        self.ruta = archivo.name
        conexion = sqlite3.connect(self.ruta)
        crear_tabla_intentos_emision_arca(conexion.cursor())
        conexion.commit()
        conexion.close()
        self.intentos = IntentoEmisionArcaService(lambda: sqlite3.connect(self.ruta))

    def tearDown(self):
        if os.path.exists(self.ruta):
            os.remove(self.ruta)

    @staticmethod
    def _contexto_c():
        return {
            "tipo": "contexto_fiscal_arca", "version": 1, "creado_en": "2026-09-14T10:00:00",
            "ambiente": "HOMOLOGACION",
            "emisor": {
                "emisor_id": 40, "emisor_fiscal_id": 30, "razon_social": "Emisor congelado",
                "nombre_fantasia": "Marca congelada", "cuit": "20206871629",
                "condicion_iva": "Monotributo", "domicilio": "Domicilio congelado",
                "ingresos_brutos": "123", "fecha_inicio_actividades": "2020-01-01",
                "punto_venta_num": 5,
            },
            "receptor": {
                "cliente_id": 20, "razon_social": "Cliente congelado", "documento_visible": "30712345678",
                "condicion_iva": "Consumidor Final", "condicion_iva_receptor_id": 5,
                "domicilio": "Domicilio cliente congelado", "tipo_documento_receptor": 80,
                "documento_receptor": 30712345678,
            },
            "comprobante": {
                "fecha": "2026-09-14", "fecha_arca": "20260914", "concepto": 1,
                "concepto_descripcion": "1 - Productos", "punto_venta_num": 5,
                "tipo_comprobante_num": 11, "tipo_comprobante_texto": "Factura C",
                "numero_comprobante_planificado": 123, "numero_textual_planificado": "00005-00000123",
                "periodo_servicio_desde": None, "periodo_servicio_hasta": None,
                "vencimiento_pago": None, "moneda": "PES", "cotizacion": Decimal("1"),
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

    @classmethod
    def _contexto_a(cls):
        contexto = cls._contexto_c()
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
        return contexto

    @staticmethod
    def _snapshot(contexto):
        return SnapshotFiscalEsperado(
            resumen_id=10,
            cliente_id=contexto["receptor"]["cliente_id"],
            emisor_fiscal_id=contexto["emisor"]["emisor_fiscal_id"],
            emisor_id=contexto["emisor"]["emisor_id"],
            cuit_emisor=contexto["emisor"]["cuit"],
            punto_venta=contexto["comprobante"]["punto_venta_num"],
            tipo_comprobante=contexto["comprobante"]["tipo_comprobante_num"],
            numero_planificado=contexto["comprobante"]["numero_comprobante_planificado"],
            fecha_comprobante=contexto["comprobante"]["fecha_arca"],
            concepto=1,
            tipo_documento=contexto["receptor"]["tipo_documento_receptor"],
            documento_receptor=contexto["receptor"]["documento_receptor"],
            condicion_iva_receptor_id=contexto["receptor"]["condicion_iva_receptor_id"],
            importe_total=Decimal(str(contexto["importes"]["total"])),
            importe_neto=Decimal(str(contexto["importes"]["neto"])),
            importe_iva=Decimal(str(contexto["importes"]["iva"])),
            importe_exento=Decimal("0"), importe_no_gravado=Decimal("0"),
            importe_tributos=Decimal("0"), moneda="PES", cotizacion=Decimal("1"),
        )

    @staticmethod
    def _consulta(contexto):
        return {
            "ok": True, "resultado": "A", "cuit_emisor": contexto["emisor"]["cuit"],
            "punto_venta": contexto["comprobante"]["punto_venta_num"],
            "tipo_comprobante": contexto["comprobante"]["tipo_comprobante_num"],
            "numero_comprobante": contexto["comprobante"]["numero_comprobante_planificado"],
            "fecha_comprobante": contexto["comprobante"]["fecha_arca"],
            "doc_tipo": contexto["receptor"]["tipo_documento_receptor"],
            "doc_nro": contexto["receptor"]["documento_receptor"],
            "importe_total": str(contexto["importes"]["total"]),
            "importe_neto": str(contexto["importes"]["neto"]),
            "importe_iva": str(contexto["importes"]["iva"]),
            "moneda": "PES", "cotizacion": "1",
            "condicion_iva_receptor_id": contexto["receptor"]["condicion_iva_receptor_id"],
            "cae": "71345678901234", "vencimiento_cae": "20260924",
        }

    def _crear_intento(self, contexto=None, estado=EstadoIntentoEmision.PENDIENTE_RECONCILIAR):
        contexto = contexto or self._contexto_c()
        validacion = ContextoFiscalService.validar(contexto)
        self.assertTrue(validacion.valido, validacion.errores)
        return self.intentos.crear_intento(
            self._snapshot(contexto),
            estado,
            contexto_fiscal_json=validacion.json_canonico,
            contexto_fiscal_version=validacion.version,
            contexto_fiscal_hash=validacion.hash_calculado,
        )

    def _servicio(self, *respuestas):
        consulta = ConsultaSecuencialFake(*respuestas)
        recuperacion = RecuperacionMarcadoraFake(self.intentos)
        servicio = ReconciliacionArcaService(
            self.intentos,
            EmisorTecnicoFake(),
            consulta,
            recuperacion,
        )
        return servicio, consulta, recuperacion

    def _servicio_con_emisor_vivo(self, emisor_vivo, *respuestas):
        class EmisorVivoFake:
            def __init__(self, fila):
                self.fila = fila
                self.llamadas = []

            def obtener(self, emisor_id):
                self.llamadas.append(emisor_id)
                return self.fila

        consulta = ConsultaSecuencialFake(*respuestas)
        recuperacion = RecuperacionMarcadoraFake(self.intentos)
        proveedor = EmisorVivoFake(emisor_vivo)
        servicio = ReconciliacionArcaService(
            self.intentos,
            proveedor,
            consulta,
            recuperacion,
        )
        return servicio, consulta, recuperacion, proveedor

    def _assert_pendiente_sin_recuperacion(self, intento_id, recuperacion):
        intento = self.intentos.obtener(intento_id)
        self.assertEqual(intento.estado, EstadoIntentoEmision.PENDIENTE_RECONCILIAR.value)
        self.assertIsNone(intento.factura_arca_id)
        self.assertEqual(recuperacion.llamadas, [])

    def _limpiar_intentos(self):
        conexion = sqlite3.connect(self.ruta)
        conexion.execute("DELETE FROM intentos_emision_arca")
        conexion.commit()
        conexion.close()

    def test_contexto_valido_arca_coherente_factura_c(self):
        contexto = self._contexto_c()
        intento_id = self._crear_intento(contexto)
        servicio, consulta, recuperacion = self._servicio(self._consulta(contexto))

        resultado = servicio.reconciliar_intento(intento_id)

        self.assertTrue(resultado.ok)
        self.assertEqual(resultado.resultado, ResultadoReconciliacion.AUTORIZADO)
        self.assertEqual(len(recuperacion.llamadas), 1)
        self.assertEqual(consulta.llamadas[0]["cuit_emisor"], "20206871629")
        self.assertEqual(consulta.llamadas[0]["punto_venta"], 5)
        self.assertEqual(consulta.llamadas[0]["ambiente"], ambiente_arca.AMBIENTE_HOMOLOGACION)

    def test_contexto_valido_arca_coherente_factura_a(self):
        contexto = self._contexto_a()
        intento_id = self._crear_intento(contexto)
        servicio, _, recuperacion = self._servicio(self._consulta(contexto))

        resultado = servicio.reconciliar_intento(intento_id)

        self.assertTrue(resultado.ok)
        self.assertEqual(resultado.resultado, ResultadoReconciliacion.AUTORIZADO)
        self.assertEqual(len(recuperacion.llamadas), 1)

    def test_maestros_documentales_mutados_no_contaminan_decision(self):
        contexto = self._contexto_c()
        intento_id = self._crear_intento(contexto)
        conexion = sqlite3.connect(self.ruta)
        conexion.execute(
            "UPDATE intentos_emision_arca SET cuit_emisor='20999999999', punto_venta=99, "
            "tipo_comprobante=1, numero_planificado=999, documento_receptor=99999999, "
            "condicion_iva_receptor_id=1, importe_total='999', importe_neto='999', importe_iva='99' "
            "WHERE id=?",
            (intento_id,),
        )
        conexion.commit()
        conexion.close()
        servicio, consulta, recuperacion = self._servicio(self._consulta(contexto))

        resultado = servicio.reconciliar_intento(intento_id)

        self.assertTrue(resultado.ok)
        self.assertEqual(len(recuperacion.llamadas), 1)
        self.assertEqual(consulta.llamadas[0]["cuit_emisor"], contexto["emisor"]["cuit"])
        self.assertEqual(consulta.llamadas[0]["numero_comprobante"], 123)

    def test_ambiente_del_contexto_prevalece_sobre_emisor_mutable(self):
        casos = (
            (ambiente_arca.AMBIENTE_HOMOLOGACION, "Producción"),
            (ambiente_arca.AMBIENTE_PRODUCCION, "Homologación"),
        )
        for ambiente_contexto, ambiente_emisor_vivo in casos:
            with self.subTest(ambiente_contexto=ambiente_contexto, ambiente_emisor_vivo=ambiente_emisor_vivo):
                self._limpiar_intentos()
                contexto = self._contexto_c()
                contexto["ambiente"] = ambiente_contexto
                intento_id = self._crear_intento(contexto)
                emisor_vivo = (
                    30, "Nombre actual mutado", "", "20999999999", "", "", 99, 1, "",
                    ambiente_emisor_vivo, "", "", "", "cert.crt", "clave.key", "C:/trabajo", 1,
                )
                servicio, consulta, recuperacion, proveedor = self._servicio_con_emisor_vivo(
                    emisor_vivo,
                    self._consulta(contexto),
                )

                resultado = servicio.reconciliar_intento(intento_id)

                self.assertTrue(resultado.ok)
                self.assertEqual(len(recuperacion.llamadas), 1)
                self.assertEqual(proveedor.llamadas, [30])
                self.assertEqual(consulta.llamadas[0]["ambiente"], ambiente_contexto)

    def test_ambiente_invalido_no_consulta_ni_asume_homologacion(self):
        casos = (None, "", "DESCONOCIDO")
        for ambiente in casos:
            with self.subTest(ambiente=ambiente):
                self._limpiar_intentos()
                contexto = self._contexto_c()
                if ambiente is None:
                    contexto.pop("ambiente")
                else:
                    contexto["ambiente"] = ambiente
                intento_id = self._crear_intento(contexto)
                servicio, consulta, recuperacion = self._servicio(self._consulta(self._contexto_c()))

                resultado = servicio.reconciliar_intento(intento_id)

                self.assertEqual(resultado.resultado, ResultadoReconciliacion.CONSULTA_INCIERTA)
                self.assertEqual(consulta.llamadas, [])
                self._assert_pendiente_sin_recuperacion(intento_id, recuperacion)

    def test_contradicciones_arca_son_conflicto(self):
        cambios = {
            "cuit_emisor": "20999999999", "punto_venta": 6, "tipo_comprobante": 1,
            "numero_comprobante": 124, "fecha_comprobante": "20260915", "doc_tipo": 96,
            "doc_nro": 99999999, "importe_total": "101", "importe_neto": "99",
            "importe_iva": "1", "moneda": "USD", "cotizacion": "2",
            "condicion_iva_receptor_id": 1,
        }
        for campo, valor in cambios.items():
            with self.subTest(campo=campo):
                self._limpiar_intentos()
                contexto = self._contexto_c()
                intento_id = self._crear_intento(contexto)
                consulta_arca = self._consulta(contexto)
                consulta_arca[campo] = valor
                servicio, _, recuperacion = self._servicio(consulta_arca)
                resultado = servicio.reconciliar_intento(intento_id)
                self.assertEqual(resultado.resultado, ResultadoReconciliacion.CONFLICTO)
                self.assertEqual(
                    self.intentos.obtener(intento_id).estado,
                    EstadoIntentoEmision.CONFLICTO_MANUAL.value,
                )
                self.assertEqual(recuperacion.llamadas, [])

    def test_campos_arca_obligatorios_ausentes_son_consulta_incierta(self):
        campos = (
            "resultado", "cae", "vencimiento_cae", "numero_comprobante", "fecha_comprobante",
            "cuit_emisor", "punto_venta", "tipo_comprobante", "doc_tipo", "doc_nro",
            "importe_total", "importe_neto", "importe_iva", "moneda", "cotizacion",
        )
        for campo in campos:
            with self.subTest(campo=campo):
                self._limpiar_intentos()
                contexto = self._contexto_c()
                intento_id = self._crear_intento(contexto)
                consulta_arca = self._consulta(contexto)
                consulta_arca.pop(campo)
                servicio, _, recuperacion = self._servicio(consulta_arca)
                resultado = servicio.reconciliar_intento(intento_id)
                self.assertEqual(resultado.resultado, ResultadoReconciliacion.CONSULTA_INCIERTA)
                self._assert_pendiente_sin_recuperacion(intento_id, recuperacion)

    def test_condicion_iva_arca_ausente_es_opcional(self):
        contexto = self._contexto_c()
        intento_id = self._crear_intento(contexto)
        consulta_arca = self._consulta(contexto)
        consulta_arca.pop("condicion_iva_receptor_id")
        servicio, _, recuperacion = self._servicio(consulta_arca)

        resultado = servicio.reconciliar_intento(intento_id)

        self.assertTrue(resultado.ok)
        self.assertEqual(len(recuperacion.llamadas), 1)

    def test_contexto_corrupto_incompatible_o_historico_no_consulta(self):
        casos = ("json", "version", "hash", "parcial", "estructura", "historico")
        for caso in casos:
            with self.subTest(caso=caso):
                self._limpiar_intentos()
                if caso == "historico":
                    contexto = self._contexto_c()
                    intento_id = self.intentos.crear_intento(self._snapshot(contexto))
                else:
                    contexto = self._contexto_c()
                    intento_id = self._crear_intento(contexto)
                    if caso == "estructura":
                        contexto_invalido = deepcopy(contexto)
                        contexto_invalido.pop("emisor")
                        validacion = ContextoFiscalService.validar(contexto_invalido)
                        valores = (validacion.json_canonico, validacion.version, validacion.hash_calculado)
                    else:
                        intento = self.intentos.obtener(intento_id)
                        valores = (
                            "{mal" if caso == "json" else intento.contexto_fiscal_json,
                            99 if caso == "version" else intento.contexto_fiscal_version,
                            "0" * 64 if caso == "hash" else intento.contexto_fiscal_hash,
                        )
                        if caso == "parcial":
                            valores = (intento.contexto_fiscal_json, None, intento.contexto_fiscal_hash)
                    conexion = sqlite3.connect(self.ruta)
                    conexion.execute(
                        "UPDATE intentos_emision_arca SET contexto_fiscal_json=?, contexto_fiscal_version=?, contexto_fiscal_hash=? WHERE id=?",
                        (*valores, intento_id),
                    )
                    conexion.commit()
                    conexion.close()
                servicio, consulta, recuperacion = self._servicio(self._consulta(contexto))
                resultado = servicio.reconciliar_intento(intento_id)
                self.assertEqual(resultado.resultado, ResultadoReconciliacion.CONSULTA_INCIERTA)
                self.assertEqual(consulta.llamadas, [])
                self._assert_pendiente_sin_recuperacion(intento_id, recuperacion)

    def test_resultado_no_autorizado_es_terminal_sin_recuperacion(self):
        contexto = self._contexto_c()
        intento_id = self._crear_intento(contexto)
        consulta_arca = self._consulta(contexto)
        consulta_arca.update(ok=False, resultado="R", cae="", vencimiento_cae="")
        servicio, consulta, recuperacion = self._servicio(consulta_arca)

        primero = servicio.reconciliar_intento(intento_id)
        segundo = servicio.reconciliar_intento(intento_id)

        self.assertEqual(primero.resultado, ResultadoReconciliacion.NO_AUTORIZADO)
        self.assertEqual(segundo.resultado, ResultadoReconciliacion.NO_AUTORIZADO)
        self.assertEqual(len(consulta.llamadas), 1)
        self.assertEqual(recuperacion.llamadas, [])

    def test_no_encontrado_y_error_tecnico_son_consulta_incierta(self):
        for respuesta in (
            {"ok": False, "resultado": "", "errores": ["Comprobante inexistente"]},
            TimeoutError("timeout simulado"),
        ):
            with self.subTest(respuesta=type(respuesta).__name__):
                self._limpiar_intentos()
                contexto = self._contexto_c()
                intento_id = self._crear_intento(contexto)
                servicio, _, recuperacion = self._servicio(respuesta)
                resultado = servicio.reconciliar_intento(intento_id)
                self.assertEqual(resultado.resultado, ResultadoReconciliacion.CONSULTA_INCIERTA)
                self._assert_pendiente_sin_recuperacion(intento_id, recuperacion)

    def test_consulta_incierta_puede_reintentarse_y_recuperar(self):
        contexto = self._contexto_c()
        intento_id = self._crear_intento(contexto)
        incompleta = self._consulta(contexto)
        incompleta.pop("importe_total")
        servicio, consulta, recuperacion = self._servicio(incompleta, self._consulta(contexto))

        primero = servicio.reconciliar_intento(intento_id)
        segundo = servicio.reconciliar_intento(intento_id)

        self.assertEqual(primero.resultado, ResultadoReconciliacion.CONSULTA_INCIERTA)
        self.assertTrue(segundo.ok)
        self.assertEqual(len(consulta.llamadas), 2)
        self.assertEqual(len(recuperacion.llamadas), 1)

    def test_estados_terminales_no_reconsultan(self):
        contexto = self._contexto_c()
        reconciliado_id = self._crear_intento(contexto, EstadoIntentoEmision.RECONCILIADO)
        conflicto_id = self._crear_intento(contexto, EstadoIntentoEmision.CONFLICTO_MANUAL)
        conexion = sqlite3.connect(self.ruta)
        conexion.execute("UPDATE intentos_emision_arca SET factura_arca_id=88 WHERE id=?", (reconciliado_id,))
        conexion.commit()
        conexion.close()
        servicio, consulta, recuperacion = self._servicio(self._consulta(contexto), self._consulta(contexto))

        reconciliado = servicio.reconciliar_intento(reconciliado_id)
        conflicto = servicio.reconciliar_intento(conflicto_id)

        self.assertTrue(reconciliado.ok)
        self.assertEqual(conflicto.resultado, ResultadoReconciliacion.CONFLICTO)
        self.assertEqual(consulta.llamadas, [])
        self.assertEqual(recuperacion.llamadas, [])


if __name__ == "__main__":
    unittest.main()