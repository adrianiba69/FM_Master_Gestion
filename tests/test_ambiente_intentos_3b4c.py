"""POST-E2E 3B.4C: intentos ARCA y reconciliacion separados por ambiente. Sin red real."""

import io
import json
import os
import sqlite3
import tempfile
import unittest
from contextlib import closing, redirect_stdout
from decimal import Decimal
from unittest.mock import MagicMock, patch

from database import crear_tabla_intentos_emision_arca, migrar_indices_activos_intentos_emision_arca
from services.arca.contexto_fiscal_service import ContextoFiscalService
from services.arca.homologacion_service import HomologacionService
from services.arca.reconciliacion_contracts import (
    EstadoIntentoEmision,
    ResultadoReconciliacion,
    SnapshotFiscalEsperado,
)
from services.arca.reconciliacion_service import ReconciliacionArcaService
from services.arca.recuperacion_local_service import RecuperacionLocalArcaService
from services.arca.wsaa_login_service import WSAALoginService
from services.arca.wsaa_service import WSAAService
from services.arca.wsfe_service import WSFEService
from services.intento_emision_arca_service import (
    ConflictoIntentoAmbiguoError,
    IntentoEmisionArcaService,
)
from tests._cierre_contexto_helper import configuracion_arca_para_test

H, P = "HOMOLOGACION", "PRODUCCION"
CUIT = "20206871629"
CAE = "86330766550000"
ACTIVO = EstadoIntentoEmision.PENDIENTE_RECONCILIAR
RECONCILIADO = EstadoIntentoEmision.RECONCILIADO
INDICE_AMBIENTE = "idx_intentos_emision_arca_clave_activa_ambiente"
INDICE_HISTORICO = "idx_intentos_emision_arca_clave_activa_historica"
INDICE_GLOBAL_ANTERIOR = "idx_intentos_emision_arca_clave_activa"


def contexto(ambiente=H, numero=123):
    return {
        "tipo": "contexto_fiscal_arca", "version": 1, "creado_en": "2026-08-17T10:00:00",
        "ambiente": ambiente,
        "emisor": {
            "emisor_id": 40, "emisor_fiscal_id": 30, "razon_social": "Emisor congelado",
            "nombre_fantasia": "Emisor", "cuit": CUIT, "condicion_iva": "Monotributo",
            "domicilio": "Domicilio emisor", "ingresos_brutos": "123",
            "fecha_inicio_actividades": "2020-01-01", "punto_venta_num": 5,
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
            "numero_comprobante_planificado": numero, "numero_textual_planificado": f"00005-{numero:08d}",
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


def snapshot(resumen_id=10, numero=123):
    return SnapshotFiscalEsperado(
        resumen_id=resumen_id, cliente_id=20, emisor_fiscal_id=30, emisor_id=40, cuit_emisor=CUIT,
        punto_venta=5, tipo_comprobante=11, numero_planificado=numero, fecha_comprobante="20260817",
        concepto=1, tipo_documento=80, documento_receptor=30712345678, condicion_iva_receptor_id=5,
        importe_total=Decimal("100.00"), importe_neto=Decimal("100.00"), importe_iva=Decimal("0.00"),
        importe_exento=Decimal("0.00"), importe_no_gravado=Decimal("0.00"),
        importe_tributos=Decimal("0.00"), moneda="PES", cotizacion=Decimal("1.00"),
    )


def consulta_autorizada(numero=123):
    return {
        "ok": True, "resultado": "A", "cuit_emisor": CUIT, "punto_venta": 5, "tipo_comprobante": 11,
        "numero_comprobante": numero, "fecha_comprobante": "2026-08-17", "doc_tipo": 80,
        "doc_nro": 30712345678, "importe_total": "100.00", "importe_neto": "100.00",
        "importe_iva": "0.00", "moneda": "PES", "cotizacion": "1.00", "condicion_iva_receptor_id": 5,
        "cae": CAE, "vencimiento_cae": "20260827",
    }


class ConsultaFake:
    def __init__(self, respuesta=None):
        self.respuesta = respuesta
        self.llamadas = []

    def __call__(self, **kwargs):
        self.llamadas.append(kwargs)
        return self.respuesta


class EmisorFake:
    def obtener_configuracion_arca(self, emisor_id, ambiente):
        return configuracion_arca_para_test(
            ambiente, emisor_id, "c.crt", "k.key", "C:/t",
        )

    # El ambiente "vivo" del emisor es deliberadamente el contrario: nunca debe decidir.
    def obtener(self, emisor_id):
        return (30, "Emisor", "", CUIT, "", "", 5, 1, "", "Homologación", "", "", "", "c.crt", "k.key", "C:/t", 1)


class ConexionCommitFallido:
    def __init__(self, conexion):
        self._conexion = conexion

    def cursor(self):
        return self._conexion.cursor()

    def commit(self):
        raise sqlite3.OperationalError("commit simulado")

    def rollback(self):
        self._conexion.rollback()

    def close(self):
        self._conexion.close()


class Base3B4C(unittest.TestCase):
    def setUp(self):
        archivo = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        archivo.close()
        self.ruta = archivo.name
        with closing(sqlite3.connect(self.ruta)) as conexion:
            conexion.executescript(
                """
                CREATE TABLE resumenes(id INTEGER PRIMARY KEY, estado_facturacion TEXT, fecha_facturacion TEXT,
                    cae TEXT, vencimiento_cae TEXT, numero_factura TEXT);
                CREATE TABLE factura_arca(id INTEGER PRIMARY KEY AUTOINCREMENT, cliente_id INTEGER NOT NULL,
                    emisor_id INTEGER NOT NULL, resumen_id INTEGER NOT NULL, fecha TEXT NOT NULL,
                    punto_venta TEXT, tipo_comprobante TEXT, importe_total REAL NOT NULL, estado TEXT NOT NULL,
                    numero_factura TEXT, cae TEXT, vencimiento_cae TEXT, observaciones TEXT, fecha_creacion TEXT,
                    punto_venta_num INTEGER, tipo_comprobante_num INTEGER, numero_comprobante_num INTEGER,
                    tipo_documento_receptor INTEGER, documento_receptor INTEGER, snapshot_fiscal_json TEXT,
                    snapshot_version INTEGER, snapshot_hash TEXT, ambiente_arca TEXT);
                INSERT INTO resumenes VALUES(10, 'Pendiente', '', '', '', '');
                INSERT INTO resumenes VALUES(11, 'Pendiente', '', '', '', '');
                """
            )
            crear_tabla_intentos_emision_arca(conexion.cursor())
            conexion.commit()
        self.factory = lambda: sqlite3.connect(self.ruta)
        self.intentos = IntentoEmisionArcaService(self.factory)

    def tearDown(self):
        if os.path.exists(self.ruta):
            os.remove(self.ruta)

    def sql(self, consulta, parametros=()):
        with closing(sqlite3.connect(self.ruta)) as conexion:
            filas = conexion.execute(consulta, parametros).fetchall()
            conexion.commit()
            return filas

    def crear(self, ambiente=H, estado=ACTIVO, numero=123, resumen_id=10, **kwargs):
        validacion = ContextoFiscalService.validar(contexto(ambiente, numero))
        self.assertTrue(validacion.valido, validacion.errores)
        return self.intentos.crear_intento(
            snapshot(resumen_id, numero), estado,
            contexto_fiscal_json=validacion.json_canonico,
            contexto_fiscal_version=validacion.version,
            contexto_fiscal_hash=validacion.hash_calculado,
            **kwargs,
        )

    def reescribir_contexto(self, intento_id, mutar):
        ctx = json.loads(self.sql("SELECT contexto_fiscal_json FROM intentos_emision_arca WHERE id=?", (intento_id,))[0][0])
        mutar(ctx)
        validacion = ContextoFiscalService.validar(ctx)
        self.sql(
            "UPDATE intentos_emision_arca SET contexto_fiscal_json=?, contexto_fiscal_hash=? WHERE id=?",
            (validacion.json_canonico, validacion.hash_calculado, intento_id),
        )

    def factura(self, ambiente, resumen_id=10, numero=123, cae=CAE, emisor_id=40):
        with closing(sqlite3.connect(self.ruta)) as conexion:
            cursor = conexion.execute(
                "INSERT INTO factura_arca(cliente_id,emisor_id,resumen_id,fecha,punto_venta,tipo_comprobante,"
                "importe_total,estado,numero_factura,cae,vencimiento_cae,punto_venta_num,tipo_comprobante_num,"
                "numero_comprobante_num,ambiente_arca) VALUES(20,?,?,'20260817','5','Factura C',100,"
                "'Facturada manualmente',?,?,'20260827',5,11,?,?)",
                (emisor_id, resumen_id, f"00005-{numero:08d}", cae, numero, ambiente),
            )
            conexion.commit()
            return cursor.lastrowid

    def reconciliado(self, ambiente_intento, ambiente_factura, cae_intento=CAE, **kwargs):
        intento_id = self.crear(ambiente_intento, RECONCILIADO)
        factura_id = self.factura(ambiente_factura, **kwargs)
        self.sql(
            "UPDATE intentos_emision_arca SET factura_arca_id=?, cae=?, vencimiento_cae='20260827' WHERE id=?",
            (factura_id, cae_intento, intento_id),
        )
        return intento_id, factura_id

    def servicio(self, respuesta=None):
        consulta = ConsultaFake(respuesta)
        servicio = ReconciliacionArcaService(
            self.intentos, EmisorFake(), consulta, RecuperacionLocalArcaService(self.factory)
        )
        return servicio, consulta


def insertar_crudo(conexion, ambiente, estado="PENDIENTE_RECONCILIAR", numero=123):
    conexion.execute(
        "INSERT INTO intentos_emision_arca(resumen_id,cliente_id,emisor_fiscal_id,emisor_id,cuit_emisor,"
        "punto_venta,tipo_comprobante,numero_planificado,fecha_comprobante,concepto,tipo_documento,"
        "documento_receptor,condicion_iva_receptor_id,importe_total,importe_neto,importe_iva,importe_exento,"
        "importe_no_gravado,importe_tributos,moneda,cotizacion,alicuotas_iva,estado,creado_en,actualizado_en,"
        "ambiente_arca) VALUES(10,20,30,40,?,5,11,?,'20260817',1,80,1,5,'100','100','0','0','0','0','PES','1',"
        "'[]',?,'t','t',?)",
        (CUIT, numero, estado, ambiente),
    )


class IndicesIntentosTest(Base3B4C):
    def test_ddl_final_de_los_indices_activos(self):
        ddl = dict(self.sql("SELECT name, sql FROM sqlite_master WHERE type='index' AND name LIKE 'idx_intentos_emision_arca_clave_activa%'"))
        self.assertNotIn(INDICE_GLOBAL_ANTERIOR, ddl)
        self.assertIn("ambiente_arca, cuit_emisor, punto_venta, tipo_comprobante, numero_planificado", ddl[INDICE_AMBIENTE])
        self.assertIn("ambiente_arca IS NOT NULL", ddl[INDICE_AMBIENTE])
        self.assertIn("(cuit_emisor, punto_venta, tipo_comprobante, numero_planificado)", ddl[INDICE_HISTORICO])
        self.assertIn("ambiente_arca IS NULL", ddl[INDICE_HISTORICO])
        for sentencia in ddl.values():
            self.assertIn("'PENDIENTE_RECONCILIAR', 'ENVIANDO', 'CONFLICTO_MANUAL'", sentencia)

    def test_mismo_ambiente_activo_bloqueado_h_h_y_p_p(self):
        for ambiente in (H, P):
            with self.subTest(ambiente=ambiente):
                self.sql("DELETE FROM intentos_emision_arca")
                self.crear(ambiente)
                with self.assertRaises(sqlite3.IntegrityError):
                    self.crear(ambiente, resumen_id=11)

    def test_h_y_p_misma_identidad_coexisten(self):
        self.crear(H)
        self.crear(P, resumen_id=11)
        self.assertEqual(self.sql("SELECT ambiente_arca FROM intentos_emision_arca ORDER BY id"), [(H,), (P,)])

    def test_null_null_protegido_y_ambiente_conocido_independiente(self):
        with closing(sqlite3.connect(self.ruta)) as conexion:
            insertar_crudo(conexion, None)
            with self.assertRaises(sqlite3.IntegrityError):
                insertar_crudo(conexion, None)
            insertar_crudo(conexion, H)
            insertar_crudo(conexion, P)

    def test_estados_terminales_no_reservan_identidad(self):
        for ambiente in (H, P, None):
            with closing(sqlite3.connect(self.ruta)) as conexion:
                for _ in range(2):
                    insertar_crudo(conexion, ambiente, estado="RECONCILIADO")
                    insertar_crudo(conexion, ambiente, estado="NO_AUTORIZADO")

    def test_conflicto_manual_sigue_reservando_identidad(self):
        self.crear(H, EstadoIntentoEmision.CONFLICTO_MANUAL)
        with self.assertRaises(sqlite3.IntegrityError):
            self.crear(H, resumen_id=11)

    def test_duplicados_nulos_preexistentes_omiten_solo_el_indice_historico_sin_perder_datos(self):
        with closing(sqlite3.connect(self.ruta)) as conexion:
            conexion.execute(f"DROP INDEX {INDICE_AMBIENTE}")
            conexion.execute(f"DROP INDEX {INDICE_HISTORICO}")
            insertar_crudo(conexion, None)
            insertar_crudo(conexion, None)
            conexion.commit()
            antes = conexion.execute("SELECT * FROM intentos_emision_arca ORDER BY id").fetchall()
            salida = io.StringIO()
            with redirect_stdout(salida):
                migrar_indices_activos_intentos_emision_arca(conexion.cursor())
            indices = {fila[0] for fila in conexion.execute("SELECT name FROM sqlite_master WHERE type='index'")}
            self.assertIn(INDICE_AMBIENTE, indices)
            self.assertNotIn(INDICE_HISTORICO, indices)
            self.assertNotIn(INDICE_GLOBAL_ANTERIOR, indices)
            self.assertIn(INDICE_HISTORICO, salida.getvalue())
            self.assertEqual(conexion.execute("SELECT * FROM intentos_emision_arca ORDER BY id").fetchall(), antes)

    def test_migracion_repetida_es_idempotente(self):
        antes = self.sql("SELECT name, sql FROM sqlite_master WHERE type='index' ORDER BY name")
        with closing(sqlite3.connect(self.ruta)) as conexion:
            salida = io.StringIO()
            with redirect_stdout(salida):
                migrar_indices_activos_intentos_emision_arca(conexion.cursor())
                migrar_indices_activos_intentos_emision_arca(conexion.cursor())
        self.assertEqual(salida.getvalue(), "")
        self.assertEqual(self.sql("SELECT name, sql FROM sqlite_master WHERE type='index' ORDER BY name"), antes)

    def test_indice_global_anterior_se_retira_y_no_bloquea_h_p(self):
        ruta = self.ruta + ".legacy"
        try:
            with closing(sqlite3.connect(ruta)) as conexion:
                conexion.execute(
                    "CREATE TABLE intentos_emision_arca(id INTEGER PRIMARY KEY, cuit_emisor TEXT, punto_venta INTEGER,"
                    " tipo_comprobante INTEGER, numero_planificado INTEGER, estado TEXT)"
                )
                conexion.execute(
                    f"CREATE UNIQUE INDEX {INDICE_GLOBAL_ANTERIOR} ON intentos_emision_arca(cuit_emisor, punto_venta,"
                    " tipo_comprobante, numero_planificado) WHERE estado IN ('PENDIENTE_RECONCILIAR','ENVIANDO','CONFLICTO_MANUAL')"
                )
                conexion.execute("INSERT INTO intentos_emision_arca VALUES(1,?,5,11,123,'ENVIANDO')", (CUIT,))
                migrar_indices_activos_intentos_emision_arca(conexion.cursor())
                nombres = {fila[0] for fila in conexion.execute("SELECT name FROM sqlite_master WHERE type='index'")}
                self.assertNotIn(INDICE_GLOBAL_ANTERIOR, nombres)
                self.assertEqual(conexion.execute("SELECT ambiente_arca FROM intentos_emision_arca").fetchall(), [(None,)])
                for ambiente in (H, P):
                    conexion.execute(
                        "INSERT INTO intentos_emision_arca(cuit_emisor,punto_venta,tipo_comprobante,numero_planificado,"
                        "estado,ambiente_arca) VALUES(?,5,11,123,'ENVIANDO',?)", (CUIT, ambiente),
                    )
                with self.assertRaises(sqlite3.IntegrityError):
                    conexion.execute(
                        "INSERT INTO intentos_emision_arca(cuit_emisor,punto_venta,tipo_comprobante,numero_planificado,"
                        "estado) VALUES(?,5,11,123,'ENVIANDO')", (CUIT,),
                    )
        finally:
            if os.path.exists(ruta):
                os.remove(ruta)


class CreacionIntentosTest(Base3B4C):
    def test_nuevo_h_persiste_ambiente_contexto_e_identidad(self):
        intento = self.intentos.obtener(self.crear(H))
        self.assertEqual(intento.ambiente_arca, H)
        self.assertEqual(json.loads(intento.contexto_fiscal_json)["ambiente"], H)
        _, codigo, _ = IntentoEmisionArcaService.evaluar_coherencia_contexto(
            json.loads(intento.contexto_fiscal_json), intento.cuit_emisor, intento.punto_venta,
            intento.tipo_comprobante, intento.numero_planificado, intento.ambiente_arca,
        )
        self.assertIsNone(codigo)

    def test_nuevo_p_persiste_p_solo_en_capa_local(self):
        self.assertEqual(self.intentos.obtener(self.crear(P)).ambiente_arca, P)

    def test_ambiente_columna_contradice_contexto_falla_sin_persistir(self):
        with self.assertRaises(ValueError):
            self.crear(H, ambiente_arca=P)
        self.assertEqual(self.sql("SELECT COUNT(*) FROM intentos_emision_arca"), [(0,)])

    def test_identidad_escalar_contradice_contexto_falla(self):
        validacion = ContextoFiscalService.validar(contexto(H, 123))
        with self.assertRaises(ValueError):
            self.intentos.crear_intento(
                snapshot(10, 999), ACTIVO, contexto_fiscal_json=validacion.json_canonico,
                contexto_fiscal_version=validacion.version, contexto_fiscal_hash=validacion.hash_calculado,
            )

    def test_contexto_con_ambiente_ausente_invalido_o_alias_falla_para_intento_moderno(self):
        for ambiente in (None, "", "DESCONOCIDO", "Homologación", "homologacion"):
            with self.subTest(ambiente=ambiente):
                ctx = contexto(H)
                if ambiente is None:
                    ctx.pop("ambiente")
                else:
                    ctx["ambiente"] = ambiente
                validacion = ContextoFiscalService.validar(ctx)
                with self.assertRaises(ValueError):
                    self.intentos.crear_intento(
                        snapshot(), ACTIVO, contexto_fiscal_json=validacion.json_canonico,
                        contexto_fiscal_version=validacion.version, contexto_fiscal_hash=validacion.hash_calculado,
                    )

    def test_ambiente_explicito_no_canonico_falla(self):
        with self.assertRaises(ValueError):
            self.intentos.crear_intento(snapshot(), ACTIVO, ambiente_arca="QA")

    def test_legacy_sin_contexto_sigue_compatible_con_ambiente_desconocido(self):
        intento = self.intentos.obtener(self.intentos.crear_intento(snapshot(), ACTIVO))
        self.assertIsNone(intento.ambiente_arca)
        self.assertIsNone(intento.contexto_fiscal_json)

    def test_null_activo_coincidente_es_ambiguedad_para_nueva_h_o_p(self):
        for ambiente in (H, P):
            with self.subTest(ambiente=ambiente):
                self.sql("DELETE FROM intentos_emision_arca")
                self.intentos.crear_intento(snapshot(), ACTIVO)
                with self.assertRaises(ConflictoIntentoAmbiguoError):
                    self.crear(ambiente, resumen_id=11)
                self.assertEqual(self.sql("SELECT ambiente_arca FROM intentos_emision_arca"), [(None,)])

    def test_null_terminal_no_es_ambiguo(self):
        self.crear(H, RECONCILIADO)
        self.sql("UPDATE intentos_emision_arca SET ambiente_arca=NULL")
        self.assertTrue(self.crear(P, resumen_id=11))

    def test_esquema_fisicamente_antiguo_sin_columna(self):
        with closing(sqlite3.connect(self.ruta)) as conexion:
            conexion.execute(f"DROP INDEX {INDICE_AMBIENTE}")
            conexion.execute(f"DROP INDEX {INDICE_HISTORICO}")
            conexion.execute("ALTER TABLE intentos_emision_arca DROP COLUMN ambiente_arca")
            conexion.commit()
        intento = self.intentos.obtener(self.intentos.crear_intento(snapshot(), ACTIVO))
        self.assertIsNone(intento.ambiente_arca)
        with self.assertRaises(ValueError):
            self.crear(H, resumen_id=11)
        self.assertEqual(len(self.intentos.listar_activos_por_resumen(10)), 1)

    def test_caida_antes_del_commit_no_deja_intento(self):
        servicio = IntentoEmisionArcaService(lambda: ConexionCommitFallido(sqlite3.connect(self.ruta)))
        validacion = ContextoFiscalService.validar(contexto(H))
        with self.assertRaises(sqlite3.OperationalError):
            servicio.crear_intento(
                snapshot(), ACTIVO, contexto_fiscal_json=validacion.json_canonico,
                contexto_fiscal_version=validacion.version, contexto_fiscal_hash=validacion.hash_calculado,
            )
        self.assertEqual(self.sql("SELECT COUNT(*) FROM intentos_emision_arca"), [(0,)])

    def test_caida_posterior_conserva_evidencia_para_reconciliar(self):
        intento_id = self.crear(H)
        reabierto = IntentoEmisionArcaService(self.factory).obtener(intento_id)
        fila = self.sql(
            "SELECT contexto_fiscal_json, contexto_fiscal_hash, ambiente_arca FROM intentos_emision_arca WHERE id=?",
            (intento_id,),
        )[0]
        self.assertTrue(all(fila))
        self.assertEqual(reabierto.estado, ACTIVO.value)
        servicio, consulta = self.servicio(consulta_autorizada())
        self.assertTrue(servicio.reconciliar_intento(intento_id).ok)
        self.assertEqual(len(consulta.llamadas), 1)


class BusquedasIntentosTest(Base3B4C):
    def buscar(self, ambiente):
        return self.intentos.buscar_activos_por_clave_fiscal(CUIT, 5, 11, 123, ambiente)

    def test_h_activo_no_bloquea_p_y_p_activo_no_bloquea_h(self):
        self.crear(H)
        self.assertEqual(self.buscar(P), ([], []))
        self.sql("DELETE FROM intentos_emision_arca")
        self.crear(P)
        self.assertEqual(self.buscar(H), ([], []))

    def test_mismo_ambiente_activo_se_detecta(self):
        intento_id = self.crear(H)
        exactos, ambiguos = self.buscar(H)
        self.assertEqual([i.id for i in exactos], [intento_id])
        self.assertEqual(ambiguos, [])

    def test_null_coincidente_se_informa_aparte(self):
        intento_id = self.intentos.crear_intento(snapshot(), ACTIVO)
        for ambiente in (H, P):
            exactos, ambiguos = self.buscar(ambiente)
            self.assertEqual(exactos, [])
            self.assertEqual([i.id for i in ambiguos], [intento_id])

    def test_busqueda_exige_ambiente_canonico_y_el_listado_legacy_no_cambia(self):
        with self.assertRaises(ValueError):
            self.buscar(None)
        self.crear(H)
        self.crear(P, resumen_id=11)
        self.assertEqual(len(self.intentos.obtener_por_clave_fiscal(CUIT, 5, 11, 123)), 2)
        self.assertEqual(len(self.intentos.obtener_por_clave_fiscal(CUIT, 5, 11, 123, P)), 1)


class ReconciliacionNoTerminalTest(Base3B4C):
    def test_h_y_p_consultan_su_propio_ambiente_con_mocks_sin_fecae(self):
        with patch.object(WSFEService, "fe_cae_solicitar") as fecae:
            for ambiente, resumen in ((H, 10), (P, 11)):
                with self.subTest(ambiente=ambiente):
                    intento_id = self.crear(ambiente, resumen_id=resumen)
                    servicio, consulta = self.servicio(consulta_autorizada())
                    resultado = servicio.reconciliar_intento(intento_id)
                    self.assertTrue(resultado.ok)
                    self.assertEqual(consulta.llamadas[0]["ambiente"], ambiente)
            fecae.assert_not_called()
        self.assertEqual(self.sql("SELECT ambiente_arca FROM factura_arca ORDER BY id"), [(H,), (P,)])

    def assert_sin_red(self, intento_id, esperado, estado):
        servicio, consulta = self.servicio(consulta_autorizada())
        resultado = servicio.reconciliar_intento(intento_id)
        self.assertEqual(resultado.resultado, esperado)
        self.assertEqual(consulta.llamadas, [])
        self.assertEqual(self.intentos.obtener(intento_id).estado, estado)
        self.assertEqual(self.sql("SELECT COUNT(*) FROM factura_arca"), [(0,)])

    def test_columna_y_contexto_contradictorios_son_conflicto_sin_red(self):
        for columna, ctx in ((H, P), (P, H)):
            with self.subTest(columna=columna):
                self.sql("DELETE FROM intentos_emision_arca")
                intento_id = self.crear(columna)
                self.reescribir_contexto(intento_id, lambda c, ctx=ctx: c.update(ambiente=ctx))
                self.assert_sin_red(intento_id, ResultadoReconciliacion.CONFLICTO, "CONFLICTO_MANUAL")

    def test_identidad_escalar_contradice_contexto_es_conflicto_sin_red(self):
        intento_id = self.crear(H)
        self.sql("UPDATE intentos_emision_arca SET numero_planificado=999 WHERE id=?", (intento_id,))
        self.assert_sin_red(intento_id, ResultadoReconciliacion.CONFLICTO, "CONFLICTO_MANUAL")

    def test_contexto_corrupto_o_hash_invalido_es_incierto_sin_red(self):
        casos = {
            "json": "UPDATE intentos_emision_arca SET contexto_fiscal_json='{mal' WHERE id=?",
            "hash": "UPDATE intentos_emision_arca SET contexto_fiscal_hash='" + "0" * 64 + "' WHERE id=?",
            "ausente": "UPDATE intentos_emision_arca SET contexto_fiscal_json=NULL, contexto_fiscal_version=NULL, contexto_fiscal_hash=NULL WHERE id=?",
        }
        for nombre, sentencia in casos.items():
            with self.subTest(caso=nombre):
                self.sql("DELETE FROM intentos_emision_arca")
                intento_id = self.crear(H)
                self.sql(sentencia, (intento_id,))
                self.assert_sin_red(intento_id, ResultadoReconciliacion.CONSULTA_INCIERTA, "PENDIENTE_RECONCILIAR")

    def test_ambiente_de_contexto_invalido_es_incierto_sin_red(self):
        for ambiente in (None, "DESCONOCIDO"):
            with self.subTest(ambiente=ambiente):
                self.sql("DELETE FROM intentos_emision_arca")
                intento_id = self.crear(H)
                self.reescribir_contexto(
                    intento_id, lambda c, a=ambiente: c.pop("ambiente") if a is None else c.update(ambiente=a)
                )
                self.assert_sin_red(intento_id, ResultadoReconciliacion.CONSULTA_INCIERTA, "PENDIENTE_RECONCILIAR")

    def test_columna_null_no_atribuye_ambiente_ni_consulta(self):
        for origen in ("moderno_con_contexto", "legacy_sin_contexto"):
            with self.subTest(origen=origen):
                self.sql("DELETE FROM intentos_emision_arca")
                if origen == "legacy_sin_contexto":
                    intento_id = self.intentos.crear_intento(snapshot(), ACTIVO)
                else:
                    intento_id = self.crear(H)
                    self.sql("UPDATE intentos_emision_arca SET ambiente_arca=NULL WHERE id=?", (intento_id,))
                self.assert_sin_red(intento_id, ResultadoReconciliacion.CONSULTA_INCIERTA, "PENDIENTE_RECONCILIAR")
                self.assertIsNone(self.intentos.obtener(intento_id).ambiente_arca)


class ReconciliadoTerminalTest(Base3B4C):
    def evaluar(self, intento_id):
        servicio, consulta = self.servicio(consulta_autorizada())
        with patch.object(WSFEService, "fe_cae_solicitar") as fecae:
            resultado = servicio.reconciliar_intento(intento_id)
        self.assertEqual(consulta.llamadas, [])
        fecae.assert_not_called()
        self.assertEqual(self.intentos.obtener(intento_id).estado, "RECONCILIADO")
        return resultado

    def test_vinculo_correcto_es_exito_local_e_idempotente(self):
        for ambiente in (H, P):
            with self.subTest(ambiente=ambiente):
                self.sql("DELETE FROM intentos_emision_arca")
                self.sql("DELETE FROM factura_arca")
                intento_id, factura_id = self.reconciliado(ambiente, ambiente)
                primero, segundo = self.evaluar(intento_id), self.evaluar(intento_id)
                self.assertTrue(primero.ok and segundo.ok)
                self.assertEqual((primero.factura_arca_id, segundo.factura_arca_id), (factura_id, factura_id))

    def test_factura_inexistente_no_es_exito(self):
        intento_id = self.crear(H, RECONCILIADO)
        self.sql("UPDATE intentos_emision_arca SET factura_arca_id=88 WHERE id=?", (intento_id,))
        resultado = self.evaluar(intento_id)
        self.assertFalse(resultado.ok)
        self.assertEqual(resultado.resultado, ResultadoReconciliacion.CONFLICTO)

    def test_ambiente_cruzado_h_p_y_p_h_no_es_exito(self):
        for ambiente_intento, ambiente_factura in ((H, P), (P, H)):
            with self.subTest(intento=ambiente_intento):
                self.sql("DELETE FROM intentos_emision_arca")
                self.sql("DELETE FROM factura_arca")
                intento_id, factura_id = self.reconciliado(ambiente_intento, ambiente_factura)
                resultado = self.evaluar(intento_id)
                self.assertFalse(resultado.ok)
                self.assertEqual(resultado.resultado, ResultadoReconciliacion.CONFLICTO)
                self.assertEqual(self.intentos.obtener(intento_id).factura_arca_id, factura_id)

    def test_factura_con_ambiente_null_no_es_exito_automatico(self):
        intento_id, factura_id = self.reconciliado(H, None)
        resultado = self.evaluar(intento_id)
        self.assertFalse(resultado.ok)
        self.assertEqual(resultado.resultado, ResultadoReconciliacion.CONSULTA_INCIERTA)
        self.assertEqual(self.sql("SELECT ambiente_arca FROM factura_arca WHERE id=?", (factura_id,)), [(None,)])

    def test_intento_sin_ambiente_o_sin_contexto_no_es_exito(self):
        intento_id, _ = self.reconciliado(H, H)
        self.sql("UPDATE intentos_emision_arca SET ambiente_arca=NULL WHERE id=?", (intento_id,))
        self.assertEqual(self.evaluar(intento_id).resultado, ResultadoReconciliacion.CONSULTA_INCIERTA)
        self.sql("UPDATE intentos_emision_arca SET ambiente_arca=?, contexto_fiscal_hash='x' WHERE id=?", (H, intento_id))
        self.assertEqual(self.evaluar(intento_id).resultado, ResultadoReconciliacion.CONSULTA_INCIERTA)

    def test_identidad_resumen_o_emisor_contradictorios_no_son_exito(self):
        casos = {
            "numero": {"numero": 999},
            "resumen": {"resumen_id": 11},
            "emisor": {"emisor_id": 41},
        }
        for nombre, cambios in casos.items():
            with self.subTest(caso=nombre):
                self.sql("DELETE FROM intentos_emision_arca")
                self.sql("DELETE FROM factura_arca")
                intento_id, _ = self.reconciliado(H, H, **cambios)
                resultado = self.evaluar(intento_id)
                self.assertFalse(resultado.ok)
                self.assertEqual(resultado.resultado, ResultadoReconciliacion.CONFLICTO)

    def test_cae_contradictorio_no_es_exito(self):
        intento_id, _ = self.reconciliado(H, H, cae_intento="11111111111111")
        resultado = self.evaluar(intento_id)
        self.assertFalse(resultado.ok)
        self.assertEqual(resultado.resultado, ResultadoReconciliacion.CONFLICTO)

    def test_cae_ausente_en_un_lado_no_bloquea(self):
        intento_id, _ = self.reconciliado(H, H, cae_intento="")
        self.assertTrue(self.evaluar(intento_id).ok)

    def test_factura_sin_columna_ambiente_no_se_puede_demostrar(self):
        intento_id, _ = self.reconciliado(H, H)
        with closing(sqlite3.connect(self.ruta)) as conexion:
            conexion.execute("ALTER TABLE factura_arca DROP COLUMN ambiente_arca")
            conexion.commit()
        self.assertEqual(self.evaluar(intento_id).resultado, ResultadoReconciliacion.CONSULTA_INCIERTA)

    def test_terminal_contradictorio_no_se_modifica(self):
        intento_id, factura_id = self.reconciliado(H, P)
        antes = self.sql("SELECT * FROM intentos_emision_arca WHERE id=?", (intento_id,))
        self.evaluar(intento_id)
        self.assertEqual(self.sql("SELECT * FROM intentos_emision_arca WHERE id=?", (intento_id,)), antes)
        self.assertEqual(self.sql("SELECT ambiente_arca FROM factura_arca WHERE id=?", (factura_id,)), [(P,)])


class RecuperacionAmbienteTest(Base3B4C):
    def recuperar(self, intento_id):
        intento = self.intentos.obtener(intento_id)
        return RecuperacionLocalArcaService(self.factory).registrar_factura_recuperada(
            intento, snapshot(intento.resumen_id), consulta_autorizada()
        )

    def test_h_p_coexisten_sin_reutilizacion_cruzada(self):
        resultado_h = self.recuperar(self.crear(H, resumen_id=10))
        resultado_p = self.recuperar(self.crear(P, resumen_id=11))
        self.assertTrue(resultado_h.insertada and resultado_p.insertada)
        self.assertNotEqual(resultado_h.factura_arca_id, resultado_p.factura_arca_id)

    def test_repeticion_mismo_ambiente_es_idempotente(self):
        intento_id = self.crear(H)
        primero = self.recuperar(intento_id)
        segundo = self.recuperar(intento_id)
        self.assertEqual(primero.factura_arca_id, segundo.factura_arca_id)
        self.assertEqual(self.sql("SELECT COUNT(*) FROM factura_arca"), [(1,)])

    def test_intento_con_ambiente_null_no_se_adopta(self):
        intento_id = self.crear(H)
        self.sql("UPDATE intentos_emision_arca SET ambiente_arca=NULL WHERE id=?", (intento_id,))
        resultado = self.recuperar(intento_id)
        self.assertEqual(resultado.resultado, ResultadoReconciliacion.CONSULTA_INCIERTA)
        self.assertEqual(self.sql("SELECT COUNT(*) FROM factura_arca"), [(0,)])

    def test_columna_y_contexto_contradictorios_son_conflicto(self):
        intento_id = self.crear(H)
        self.reescribir_contexto(intento_id, lambda c: c.update(ambiente=P))
        resultado = self.recuperar(intento_id)
        self.assertEqual(resultado.resultado, ResultadoReconciliacion.CONFLICTO)
        self.assertEqual(self.sql("SELECT COUNT(*) FROM factura_arca"), [(0,)])

    def test_factura_historica_null_con_misma_identidad_es_conflicto_no_adopcion(self):
        self.factura(None)
        resultado = self.recuperar(self.crear(H))
        self.assertEqual(resultado.resultado, ResultadoReconciliacion.CONFLICTO)
        self.assertEqual(self.sql("SELECT ambiente_arca FROM factura_arca"), [(None,)])

    def test_factura_del_ambiente_contrario_vinculada_es_conflicto(self):
        factura_id = self.factura(P)
        intento_id = self.crear(H)
        self.sql("UPDATE intentos_emision_arca SET factura_arca_id=? WHERE id=?", (factura_id, intento_id))
        self.assertEqual(self.recuperar(intento_id).resultado, ResultadoReconciliacion.CONFLICTO)


class PreenvioAmbienteTest(Base3B4C):
    def preenvio(self, intentos=None):
        from services.arca.preenvio_arca_service import PreenvioArcaService
        return PreenvioArcaService(intentos or self.intentos)

    def test_flujo_moderno_persiste_intento_contexto_y_ambiente_antes_de_enviar(self):
        for ambiente in (H, P):
            with self.subTest(ambiente=ambiente):
                self.sql("DELETE FROM intentos_emision_arca")
                visto = []

                def enviar():
                    visto.append(self.sql("SELECT estado, ambiente_arca, contexto_fiscal_hash FROM intentos_emision_arca"))
                    return {"ok": True, "resultado": "A"}

                resultado = self.preenvio().enviar_una_vez_con_contexto(snapshot(), contexto(ambiente), enviar)
                self.assertTrue(resultado.ok)
                self.assertEqual(visto[0][0][:2], ("ENVIANDO", ambiente))
                self.assertTrue(visto[0][0][2])

    def test_ambiente_persistido_distinto_del_contexto_no_envia(self):
        from dataclasses import replace

        class IntentosAdulterados:
            def __init__(self, real):
                self.real = real

            def crear_intento(self, *args, **kwargs):
                return self.real.crear_intento(*args, **kwargs)

            def obtener(self, intento_id):
                return replace(self.real.obtener(intento_id), ambiente_arca=P)

            def actualizar_estado(self, *args, **kwargs):
                raise AssertionError("no debe marcar ENVIANDO")

        enviar = MagicMock()
        resultado = self.preenvio(IntentosAdulterados(self.intentos)).enviar_una_vez_con_contexto(
            snapshot(), contexto(H), enviar
        )
        self.assertFalse(resultado.ok)
        enviar.assert_not_called()

    def test_contexto_incoherente_con_snapshot_no_crea_intento_ni_envia(self):
        enviar = MagicMock()
        resultado = self.preenvio().enviar_una_vez_con_contexto(snapshot(numero=999), contexto(H, 123), enviar)
        self.assertFalse(resultado.ok)
        enviar.assert_not_called()
        self.assertEqual(self.sql("SELECT COUNT(*) FROM intentos_emision_arca"), [(0,)])


class ProduccionBloqueadaTest(Base3B4C):
    def emitir(self, ambiente, ctx):
        preenvio = MagicMock()
        with patch.object(WSAAService, "guardar_tra") as tra, \
                patch.object(WSAALoginService, "login_homologacion") as login, \
                patch.object(WSFEService, "fe_comp_ultimo_autorizado") as ultimo, \
                patch.object(WSFEService, "fe_cae_solicitar") as solicitar:
            resultado = HomologacionService.emitir_comprobante_prueba(
                ruta_certificado="c.crt", ruta_clave="k.key", cuit_emisor=CUIT, punto_venta=5,
                tipo_comprobante=11, condicion_iva_receptor_id=5, concepto=1, tipo_documento=80,
                documento_receptor=30712345678, importe_total=100, importe_neto=100, importe_iva=0,
                importe_exento=0, fecha_comprobante="20260817", carpeta_trabajo=tempfile.gettempdir(),
                contexto_fiscal_base=ctx, exigir_contexto_fiscal=True, preenvio_service=preenvio,
                ambiente=ambiente,
            )
        for mock in (tra, login, ultimo, solicitar, preenvio.enviar_una_vez_con_contexto, preenvio.enviar_una_vez):
            mock.assert_not_called()
        self.assertEqual(self.sql("SELECT COUNT(*) FROM intentos_emision_arca"), [(0,)])
        return resultado

    def test_emision_nueva_produccion_sigue_bloqueada_antes_de_intento_y_red(self):
        resultado = self.emitir("PRODUCCION", contexto(P))
        self.assertFalse(resultado["ok"])
        self.assertTrue(any("Producción" in e or "Produccion" in e for e in resultado["errores"]))

    def test_ambiente_de_emision_distinto_del_contexto_falla_antes_de_red(self):
        resultado = self.emitir("HOMOLOGACION", contexto(P))
        self.assertFalse(resultado["ok"])
        self.assertTrue(any("no coincide" in e for e in resultado["errores"]))


if __name__ == "__main__":
    unittest.main()
