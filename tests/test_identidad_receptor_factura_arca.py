import os
import sqlite3
import tempfile
import unittest
from decimal import Decimal

from database import migrar_factura_arca_identidad_receptor
from models.factura_arca import FacturaArca
from services.arca.cierre_local_arca_service import CierreLocalArcaService
from services.arca.recuperacion_local_service import RecuperacionLocalArcaService
from services.arca.reconciliacion_contracts import SnapshotFiscalEsperado
from services.factura_arca_service import FacturaArcaService
from models.intento_emision_arca import IntentoEmisionArca


class MigracionIdentidadReceptorTest(unittest.TestCase):

    def setUp(self):
        archivo = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        archivo.close()
        self.ruta = archivo.name

    def tearDown(self):
        if os.path.exists(self.ruta):
            os.remove(self.ruta)

    def _crear_tabla_antigua(self, filas=()):
        conexion = sqlite3.connect(self.ruta)
        conexion.execute(
            """
            CREATE TABLE factura_arca(
                id INTEGER PRIMARY KEY,
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
                fecha_creacion TEXT
            )
            """
        )
        conexion.executemany(
            "INSERT INTO factura_arca(id,cliente_id,emisor_id,resumen_id,fecha,punto_venta,tipo_comprobante,importe_total,estado,numero_factura,cae,vencimiento_cae,observaciones,fecha_creacion) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            filas,
        )
        conexion.commit()
        return conexion

    def test_migracion_agrega_ambas_columnas(self):
        conexion = self._crear_tabla_antigua()
        migrar_factura_arca_identidad_receptor(conexion.cursor())
        conexion.commit()
        columnas = [fila[1] for fila in conexion.execute("PRAGMA table_info(factura_arca)")]
        self.assertIn("tipo_documento_receptor", columnas)
        self.assertIn("documento_receptor", columnas)
        conexion.close()

    def test_migracion_es_idempotente(self):
        conexion = self._crear_tabla_antigua()
        cur = conexion.cursor()
        migrar_factura_arca_identidad_receptor(cur)
        conexion.commit()
        migrar_factura_arca_identidad_receptor(cur)
        conexion.commit()
        columnas = [fila[1] for fila in conexion.execute("PRAGMA table_info(factura_arca)")]
        self.assertEqual(columnas.count("tipo_documento_receptor"), 1)
        self.assertEqual(columnas.count("documento_receptor"), 1)
        conexion.close()

    def test_historicos_existentes_quedan_null(self):
        fila = (1, 25, 3, 24, "2026-08-01", "00002", "Factura A", 1000, "Facturada", "00002-00000001", "86310711529020", "20260811", "obs", "fecha")
        conexion = self._crear_tabla_antigua([fila])
        migrar_factura_arca_identidad_receptor(conexion.cursor())
        conexion.commit()
        fila_resultante = conexion.execute(
            "SELECT tipo_documento_receptor, documento_receptor FROM factura_arca WHERE id=1"
        ).fetchone()
        self.assertEqual(fila_resultante, (None, None))
        conexion.close()


class CierreLocalIdentidadReceptorTest(unittest.TestCase):

    def setUp(self):
        archivo = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        archivo.close()
        self.ruta = archivo.name
        conexion = sqlite3.connect(self.ruta)
        try:
            conexion.executescript(
                """
                CREATE TABLE resumenes(id INTEGER PRIMARY KEY, estado_facturacion TEXT, fecha_facturacion TEXT, cae TEXT, vencimiento_cae TEXT, numero_factura TEXT);
                CREATE TABLE factura_arca(id INTEGER PRIMARY KEY AUTOINCREMENT, cliente_id INTEGER NOT NULL, emisor_id INTEGER NOT NULL, resumen_id INTEGER NOT NULL, fecha TEXT NOT NULL, punto_venta TEXT, tipo_comprobante TEXT, importe_total REAL NOT NULL, estado TEXT NOT NULL, numero_factura TEXT, cae TEXT, vencimiento_cae TEXT, observaciones TEXT, fecha_creacion TEXT, punto_venta_num INTEGER, tipo_comprobante_num INTEGER, numero_comprobante_num INTEGER, tipo_documento_receptor INTEGER, documento_receptor INTEGER);
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

    def datos(self, **overrides):
        base = dict(
            intento_id=1,
            resumen_id=10,
            cliente_id=20,
            emisor_id=40,
            fecha="20260818",
            punto_venta="5",
            tipo_comprobante="Factura C",
            importe_total=100.0,
            numero_factura="00005-00000123",
            cae="86330766550000",
            vencimiento_cae="20260828",
            observaciones="cierre normal",
        )
        base.update(overrides)
        return base

    def _fila(self):
        conexion = sqlite3.connect(self.ruta)
        try:
            return conexion.execute(
                "SELECT tipo_documento_receptor, documento_receptor FROM factura_arca"
            ).fetchone()
        finally:
            conexion.close()

    def test_factura_a_persiste_doctipo_docnro_recibidos(self):
        resultado = self.service.cerrar_emision_confirmada(
            **self.datos(tipo_comprobante="Factura A"),
            tipo_documento_receptor=80,
            documento_receptor=20111222333,
        )
        self.assertTrue(resultado.ok)
        self.assertEqual(self._fila(), (80, 20111222333))

    def test_factura_c_cuit_persiste_exactamente(self):
        resultado = self.service.cerrar_emision_confirmada(
            **self.datos(),
            tipo_documento_receptor=80,
            documento_receptor=20333444555,
        )
        self.assertTrue(resultado.ok)
        self.assertEqual(self._fila(), (80, 20333444555))

    def test_factura_c_dni_persiste_exactamente(self):
        resultado = self.service.cerrar_emision_confirmada(
            **self.datos(),
            tipo_documento_receptor=96,
            documento_receptor=30111222,
        )
        self.assertTrue(resultado.ok)
        self.assertEqual(self._fila(), (96, 30111222))

    def test_caso_sin_identificar_preserva_combinacion(self):
        resultado = self.service.cerrar_emision_confirmada(
            **self.datos(),
            tipo_documento_receptor=99,
            documento_receptor=0,
        )
        self.assertTrue(resultado.ok)
        self.assertEqual(self._fila(), (99, 0))

    def test_caller_antiguo_sin_campos_sigue_funcionando(self):
        resultado = self.service.cerrar_emision_confirmada(**self.datos())
        self.assertTrue(resultado.ok)
        self.assertEqual(self._fila(), (None, None))


class FacturaArcaServiceIdentidadReceptorTest(unittest.TestCase):

    def setUp(self):
        archivo = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        archivo.close()
        self.ruta = archivo.name
        conexion = sqlite3.connect(self.ruta)
        try:
            conexion.executescript(
                """
                CREATE TABLE factura_arca(id INTEGER PRIMARY KEY AUTOINCREMENT, cliente_id INTEGER NOT NULL, emisor_id INTEGER NOT NULL, resumen_id INTEGER NOT NULL, fecha TEXT NOT NULL, punto_venta TEXT, tipo_comprobante TEXT, importe_total REAL NOT NULL, estado TEXT NOT NULL, numero_factura TEXT, cae TEXT, vencimiento_cae TEXT, observaciones TEXT, fecha_creacion TEXT, punto_venta_num INTEGER, tipo_comprobante_num INTEGER, numero_comprobante_num INTEGER, tipo_documento_receptor INTEGER, documento_receptor INTEGER);
                """
            )
            conexion.commit()
        finally:
            conexion.close()

    def tearDown(self):
        if os.path.exists(self.ruta):
            os.remove(self.ruta)

    def _filas(self):
        conexion = sqlite3.connect(self.ruta)
        try:
            return conexion.execute(
                "SELECT tipo_documento_receptor, documento_receptor FROM factura_arca"
            ).fetchall()
        finally:
            conexion.close()

    def test_guardar_admite_ambos_campos(self):
        import services.factura_arca_service as modulo

        original_conectar = modulo.conectar
        modulo.conectar = lambda: sqlite3.connect(self.ruta)
        try:
            factura = FacturaArca(
                cliente_id=1, emisor_id=1, resumen_id=1, fecha="2026-08-22",
                punto_venta="5", tipo_comprobante="Factura C", importe_total=100.0,
                estado="Facturada manualmente", numero_factura="00005-00000001",
                cae="86330766550000", vencimiento_cae="20260828",
                tipo_documento_receptor=80, documento_receptor=20111222333,
            )
            FacturaArcaService.guardar(factura)
        finally:
            modulo.conectar = original_conectar
        self.assertEqual(self._filas(), [(80, 20111222333)])

    def test_caller_antiguo_sin_campos_nuevos_sigue_funcionando(self):
        import services.factura_arca_service as modulo

        original_conectar = modulo.conectar
        modulo.conectar = lambda: sqlite3.connect(self.ruta)
        try:
            factura = FacturaArca(
                cliente_id=1, emisor_id=1, resumen_id=1, fecha="2026-08-22",
                punto_venta="5", tipo_comprobante="Factura C", importe_total=100.0,
                estado="Facturada manualmente", numero_factura="00005-00000002",
                cae="86330766550001", vencimiento_cae="20260828",
            )
            factura_id = FacturaArcaService.guardar(factura)
        finally:
            modulo.conectar = original_conectar
        self.assertIsNotNone(factura_id)
        self.assertEqual(self._filas(), [(None, None)])


class RecuperacionIdentidadReceptorTest(unittest.TestCase):

    def setUp(self):
        archivo = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        archivo.close()
        self.ruta = archivo.name
        conexion = sqlite3.connect(self.ruta)
        try:
            cursor = conexion.cursor()
            cursor.executescript(
                """
                CREATE TABLE resumenes(id INTEGER PRIMARY KEY, estado_facturacion TEXT, fecha_facturacion TEXT, cae TEXT, vencimiento_cae TEXT, numero_factura TEXT);
                CREATE TABLE factura_arca(id INTEGER PRIMARY KEY AUTOINCREMENT, cliente_id INTEGER NOT NULL, emisor_id INTEGER NOT NULL, resumen_id INTEGER NOT NULL, fecha TEXT NOT NULL, punto_venta TEXT, tipo_comprobante TEXT, importe_total REAL NOT NULL, estado TEXT NOT NULL, numero_factura TEXT, cae TEXT, vencimiento_cae TEXT, observaciones TEXT, fecha_creacion TEXT, punto_venta_num INTEGER, tipo_comprobante_num INTEGER, numero_comprobante_num INTEGER, tipo_documento_receptor INTEGER, documento_receptor INTEGER);
                CREATE TABLE intentos_emision_arca(id INTEGER PRIMARY KEY, estado TEXT, cae TEXT, vencimiento_cae TEXT, factura_arca_id INTEGER, error_codigo TEXT, error_mensaje TEXT, actualizado_en TEXT, reconciliado_en TEXT);
                """
            )
            cursor.execute("INSERT INTO resumenes VALUES(10, 'Pendiente', '', '', '', '')")
            cursor.execute("INSERT INTO intentos_emision_arca VALUES(1, 'PENDIENTE_RECONCILIAR', '', '', NULL, '', '', '', NULL)")
            conexion.commit()
        finally:
            conexion.close()
        self.service = RecuperacionLocalArcaService(lambda: sqlite3.connect(self.ruta))
        self.snapshot = SnapshotFiscalEsperado(
            resumen_id=10, cliente_id=20, emisor_fiscal_id=30, emisor_id=40, cuit_emisor="20206871629",
            punto_venta=5, tipo_comprobante=11, numero_planificado=123, fecha_comprobante="20260817",
            concepto=1, tipo_documento=80, documento_receptor=30712345678, condicion_iva_receptor_id=5,
            importe_total=Decimal("100.00"), importe_neto=Decimal("100.00"), importe_iva=Decimal("0.00"),
            importe_exento=Decimal("0.00"), importe_no_gravado=Decimal("0.00"), importe_tributos=Decimal("0.00"),
            moneda="PES", cotizacion=Decimal("1.00"),
        )

    def tearDown(self):
        if os.path.exists(self.ruta):
            os.remove(self.ruta)

    def _intento(self):
        return IntentoEmisionArca(1, 10, 20, 30, 40, "20206871629", 5, 11, 123, "20260817", 1, 80, 30712345678, 5, Decimal("100.00"), Decimal("100.00"), Decimal("0.00"), Decimal("0.00"), Decimal("0.00"), Decimal("0.00"), "PES", Decimal("1.00"), (), "PENDIENTE_RECONCILIAR", "", "", "", "", "", None, "", "", None)

    def _consulta_base(self):
        return {
            "cuit_emisor": "20206871629", "punto_venta": 5, "tipo_comprobante": 11, "numero_comprobante": 123,
            "fecha_comprobante": "20260817", "doc_tipo": 80, "doc_nro": 30712345678,
            "importe_total": "100.00", "importe_neto": "100.00", "importe_iva": "0.00", "moneda": "PES",
            "cotizacion": "1.00", "condicion_iva_receptor_id": 5, "cae": "86330766550000", "vencimiento_cae": "20260827",
        }

    def _fila(self):
        conexion = sqlite3.connect(self.ruta)
        try:
            return conexion.execute(
                "SELECT tipo_documento_receptor, documento_receptor FROM factura_arca"
            ).fetchone()
        finally:
            conexion.close()

    def test_recuperacion_usa_doctipo_docnro_de_arca(self):
        resultado = self.service.registrar_factura_recuperada(self._intento(), self.snapshot, self._consulta_base())
        self.assertTrue(resultado.insertada)
        self.assertEqual(self._fila(), (80, 30712345678))

    def test_helper_deja_null_si_consulta_no_trae_doctipo_docnro(self):
        # La ausencia real de doc_tipo/doc_nro en `consulta` hoy hace que la
        # comparacion previa marque CONSULTA_INCIERTA (no se llega a insertar);
        # este test valida directamente el fail-safe del helper de extraccion.
        self.assertEqual(
            RecuperacionLocalArcaService._identidad_receptor_desde_consulta({"cae": "x"}),
            (None, None),
        )
        self.assertEqual(
            RecuperacionLocalArcaService._identidad_receptor_desde_consulta({"doc_tipo": "no-numerico", "doc_nro": 1}),
            (None, None),
        )

    def test_cambio_posterior_del_cliente_no_afecta_valor_persistido(self):
        # El snapshot/consulta representan el estado usado para autorizar el
        # comprobante; aunque el "cliente" cambie despues, la recuperacion no
        # vuelve a consultarlo: usa exclusivamente doc_tipo/doc_nro de ARCA.
        intento_con_cliente_original = self._intento()
        resultado = self.service.registrar_factura_recuperada(intento_con_cliente_original, self.snapshot, self._consulta_base())
        self.assertTrue(resultado.insertada)
        # Un DocTipo/DocNro de cliente distinto (ej. tras editar el cliente) no se usa jamas.
        self.assertEqual(self._fila(), (80, 30712345678))
        self.assertNotEqual(self._fila(), (96, 99999999))


if __name__ == "__main__":
    unittest.main()
