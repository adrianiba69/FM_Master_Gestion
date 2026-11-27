"""Etapa 3D.4C.5D.6: compatibilidad segura de clientes históricos (solo diagnóstico).

El esquema histórico 9b6a850, después de crear_base(), conserva en ``clientes`` tres columnas
que el esquema actual no tiene: ``servicio TEXT``, ``importe REAL`` y ``descuento REAL``.
Estas pruebas demuestran, SOLO con bases ficticias en archivos temporales, que:

* la única diferencia estructural con el esquema actual son esas tres columnas;
* sus valores y tipos de almacenamiento se conservan y las operaciones actuales no los alteran;
* los servicios reales de clientes, comerciales y fiscales (sin red) devuelven resultados
  idénticos en ambos esquemas;
* la huella estructural oficial sigue distinguiendo ambos esquemas y rechaza variantes.

No se registra ninguna huella como autorizada ni se modifica política, huella ni servicios.
El recálculo de servicios de crear_base() ya está diagnosticado (3D.4C.5D.3) y se mantiene
separado de las pruebas de conservación de clientes.
"""

import re
import shutil
import sqlite3
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

import database as database_real
from models.cliente import Cliente
from models.cobro import Cobro
from models.contacto import Contacto
from models.oportunidad import Oportunidad
from models.servicio import Servicio
from services.cliente_service import ClienteService
from services.cobro_service import CobroService
from services.contacto_service import ContactoService
from services.facturacion_service import FacturacionService
from services.informes_service import InformesService
from services.oportunidad_service import OportunidadService
from services.resumen_service import ResumenService
from services.servicio_service import ServicioService
from services.sqlite_huella_estructural import (
    calcular_huella_estructural_sqlite,
    representacion_estructural_sqlite,
)
from tests.test_compatibilidad_esquemas_historicos_3d4c5c2 import (
    ESQUEMAS_HISTORICOS,
    database as database_aislado,
)

H_9B = "build_0_2_2_9b6a850"
HUELLA_ACTUAL = "650cc300b59db14e5621f922cd77a55d08739ec843729bdb61ccf6e33e4b7fa3"
HUELLA_9B_SIN_MIGRAR = "36215ac6d972429268edf1f94154305363c6426b927044f02fcd66d8fb0ebf6a"
HUELLA_9B_MIGRADA = "cceefd20ccfddbe3fee9161e319b9ee9db7d4e1fdef3e105d055b4a588111727"
HUELLA_COMUN_8C_49_MIGRADOS = "b78314c4db609c4c953d4484475e0712695c1a9e5380906b8717e038b36e8a36"
COLUMNAS_HISTORICAS = ("servicio", "importe", "descuento")
RAIZ = Path(__file__).resolve().parents[1]
RUTA_REAL = database_real.DB_NAME

# Columnas de clientes en 9b6a850 (orden físico histórico).
COLUMNAS_9B = (
    "id", "codigo", "razon_social", "responsable", "direccion", "localidad", "telefono", "whatsapp",
    "email", "cuit", "iva", "servicio", "importe", "descuento", "vencimiento", "estado",
    "observaciones", "fecha_alta",
)
# Cubre NULL, vacío, texto, caracteres especiales, positivos, cero, negativos y decimales.
CLIENTES = (
    {"id": 1, "codigo": "C001", "razon_social": "Alfa Ficticia SA", "responsable": "Ana", "localidad": "Rosario",
     "telefono": "341-000001", "whatsapp": "341-100001", "email": "alfa@ficticio.test", "cuit": "30-00000000-1",
     "iva": "Responsable Inscripto", "servicio": "Hosting Básico", "importe": 1500.5, "descuento": 10.0,
     "vencimiento": 10, "estado": "Activo", "observaciones": "ficticio", "fecha_alta": "2024-01-01"},
    {"id": 2, "codigo": "C002", "razon_social": "Beta Ficticia SRL", "iva": "Monotributo",
     "servicio": None, "importe": None, "descuento": None, "estado": "Activo", "fecha_alta": "2024-01-02"},
    {"id": 3, "codigo": "C003", "razon_social": "Gamma Ficticia", "servicio": "", "importe": 0.0,
     "descuento": 0.0, "estado": "Baja", "observaciones": "", "fecha_alta": "2024-01-03"},
    {"id": 4, "codigo": "C004", "razon_social": "Delta Ñandú 'S.A.' \"ficticia\" %_;--",
     "servicio": "Diseño 'web' \"ñandú\" ✓ 100% _x; --", "importe": -250.75, "descuento": 5.5,
     "vencimiento": 20, "estado": "Activo", "fecha_alta": "2024-01-04"},
    {"id": 5, "codigo": "C005", "razon_social": "Épsilon Ficticia", "servicio": "123", "importe": 1234567.891,
     "descuento": 99.99, "estado": "Activo", "fecha_alta": "2024-01-05"},
    {"id": 6, "codigo": "C006", "razon_social": None, "servicio": "Solo servicio", "importe": 0.1,
     "descuento": -1.0, "estado": "Activo", "fecha_alta": "2024-01-06"},
    {"id": 7, "codigo": "C007", "razon_social": "", "servicio": "Razón vacía", "importe": 1e15,
     "descuento": 0.0, "estado": "Activo", "fecha_alta": "2024-01-07"},
)
ID_ALTO_ELIMINADO = 99


def _crear_historica(ruta):
    con = sqlite3.connect(ruta)
    try:
        for _, _, _, sql in ESQUEMAS_HISTORICOS[H_9B][2]:
            con.execute(sql)
        _insertar_clientes(con, historicas=True)
        con.commit()
    finally:
        con.close()


def _insertar_clientes(con, *, historicas):
    for fila in CLIENTES:
        datos = {k: v for k, v in fila.items() if historicas or k not in COLUMNAS_HISTORICAS}
        con.execute(
            f'INSERT INTO clientes({",".join(datos)}) VALUES ({",".join("?" * len(datos))})',
            tuple(datos.values()),
        )
    con.execute("INSERT INTO clientes(id, codigo) VALUES (?, 'TMP')", (ID_ALTO_ELIMINADO,))
    con.execute("DELETE FROM clientes WHERE id=?", (ID_ALTO_ELIMINADO,))


def _crear_base(ruta):
    with patch.object(database_real, "DB_NAME", ruta):
        database_real.crear_base()


def _crear_actual(ruta):
    Path(ruta).touch()  # conectar() abre con mode=rw y no crea archivos
    _crear_base(ruta)
    con = sqlite3.connect(ruta)
    try:
        _insertar_clientes(con, historicas=False)
        con.commit()
    finally:
        con.close()


def _abrir(ruta):
    return sqlite3.connect(ruta)


def _huella(con):
    resultado = calcular_huella_estructural_sqlite(con)
    assert resultado.confiable, resultado.razones
    return resultado.huella


def _filas_con_tipo(con, tabla, columnas):
    seleccion = ",".join(f'"{c}", typeof("{c}")' for c in columnas)
    return con.execute(f'SELECT {seleccion} FROM "{tabla}" ORDER BY id').fetchall()


def _columnas(con, tabla):
    return [f[1] for f in con.execute(f'PRAGMA table_info("{tabla}")')]


def _secuencias(con):
    return dict(con.execute("SELECT name, seq FROM sqlite_sequence"))


def _tablas(con):
    return sorted(f[0] for f in con.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"))


def _instantanea(con):
    """Contenido completo con tipos de almacenamiento, esquema y secuencias."""
    tablas = {t: _filas_con_tipo(con, t, sorted(_columnas(con, t))) if "id" in _columnas(con, t)
              else sorted(con.execute(f'SELECT * FROM "{t}"').fetchall(), key=repr)
              for t in _tablas(con)}
    esquema = sorted(con.execute("SELECT type, name, tbl_name, sql FROM sqlite_master").fetchall(), key=repr)
    return {"tablas": tablas, "esquema": esquema, "secuencias": _secuencias(con)}


class _Base(unittest.TestCase):
    """Todas las pruebas operan sobre archivos temporales; DATABASE_PATH real queda bloqueado."""

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory(prefix="fm_5d6_")
        cls.dir = Path(cls._tmp.name)
        cls.ruta_actual = str(cls.dir / "actual.db")
        cls.ruta_hist = str(cls.dir / "historica.db")
        cls.ruta_migrada = str(cls.dir / "migrada.db")
        cls.ruta_migrada_2 = str(cls.dir / "migrada_2.db")
        cls.addClassCleanup(cls._tmp.cleanup)
        cls._bloqueo = patch.object(database_real, "DB_NAME", str(cls.dir / "bloqueada.db"))
        cls._bloqueo.start()
        cls.addClassCleanup(cls._bloqueo.stop)
        _crear_actual(cls.ruta_actual)
        _crear_historica(cls.ruta_hist)
        shutil.copy2(cls.ruta_hist, cls.ruta_migrada)
        _crear_base(cls.ruta_migrada)
        shutil.copy2(cls.ruta_migrada, cls.ruta_migrada_2)
        _crear_base(cls.ruta_migrada_2)

    def setUp(self):
        self.assertNotEqual(database_real.DB_NAME, RUTA_REAL)
        self.assertTrue(database_real.DB_NAME.startswith(str(self.dir)))


class EstructuraTest(_Base):
    def test_huellas_oficiales_actual_y_9b6a850(self):
        for ruta, esperada in ((self.ruta_actual, HUELLA_ACTUAL), (self.ruta_migrada, HUELLA_9B_MIGRADA),
                               (self.ruta_hist, HUELLA_9B_SIN_MIGRAR)):
            con = _abrir(ruta)
            self.addCleanup(con.close)
            self.assertEqual(_huella(con), esperada)
        self.assertEqual(len({HUELLA_ACTUAL, HUELLA_9B_MIGRADA, HUELLA_9B_SIN_MIGRAR,
                              HUELLA_COMUN_8C_49_MIGRADOS}), 4)

    def test_la_unica_diferencia_son_tres_columnas_de_clientes(self):
        a, c = _abrir(self.ruta_actual), _abrir(self.ruta_migrada)
        self.addCleanup(a.close)
        self.addCleanup(c.close)
        ra, rc = representacion_estructural_sqlite(a), representacion_estructural_sqlite(c)
        self.assertEqual({k: v for k, v in ra.items() if k != "tablas"},
                         {k: v for k, v in rc.items() if k != "tablas"})
        ta = {t["nombre"]: t for t in ra["tablas"]}
        tc = {t["nombre"]: t for t in rc["tablas"]}
        self.assertEqual(set(ta), set(tc))
        distintas = [n for n in ta if ta[n] != tc[n]]
        self.assertEqual(distintas, ["clientes"])
        # Todo lo demás de clientes (claves foráneas, índices, restricciones) es idéntico.
        self.assertEqual({k: v for k, v in ta["clientes"].items() if k != "columnas"},
                         {k: v for k, v in tc["clientes"].items() if k != "columnas"})
        col_a = {x["nombre"]: x for x in ta["clientes"]["columnas"]}
        col_c = {x["nombre"]: x for x in tc["clientes"]["columnas"]}
        self.assertEqual(set(col_c) - set(col_a), set(COLUMNAS_HISTORICAS))
        self.assertEqual(set(col_a) - set(col_c), set())
        for nombre in col_a:
            self.assertEqual(col_a[nombre], col_c[nombre], nombre)
        self.assertEqual(
            {n: col_c[n] for n in COLUMNAS_HISTORICAS},
            {"servicio": {"nombre": "servicio", "tipo": "TEXT", "no_nulo": 0, "defecto": None, "pk": 0},
             "importe": {"nombre": "importe", "tipo": "REAL", "no_nulo": 0, "defecto": None, "pk": 0},
             "descuento": {"nombre": "descuento", "tipo": "REAL", "no_nulo": 0, "defecto": None, "pk": 0}},
        )

    def test_objetos_asociados_son_los_mismos_y_no_hay_triggers_ni_vistas(self):
        a, c = _abrir(self.ruta_actual), _abrir(self.ruta_migrada)
        self.addCleanup(a.close)
        self.addCleanup(c.close)
        consulta = "SELECT type, name, tbl_name FROM sqlite_master ORDER BY type, name"
        self.assertEqual(a.execute(consulta).fetchall(), c.execute(consulta).fetchall())
        self.assertEqual(c.execute("SELECT COUNT(*) FROM sqlite_master WHERE type IN ('trigger','view')").fetchone(),
                         (0,))
        for tabla in _tablas(a):
            self.assertEqual(a.execute(f'PRAGMA foreign_key_list("{tabla}")').fetchall(),
                             c.execute(f'PRAGMA foreign_key_list("{tabla}")').fetchall(), tabla)
            self.assertEqual(sorted(f[1:] for f in a.execute(f'PRAGMA index_list("{tabla}")')),
                             sorted(f[1:] for f in c.execute(f'PRAGMA index_list("{tabla}")')), tabla)

    def test_el_orden_fisico_difiere_y_la_huella_no_lo_distingue(self):
        a, c = _abrir(self.ruta_actual), _abrir(self.ruta_migrada)
        self.addCleanup(a.close)
        self.addCleanup(c.close)
        ca, cc = _columnas(a, "clientes"), _columnas(c, "clientes")
        self.assertNotEqual(ca, [n for n in cc if n not in COLUMNAS_HISTORICAS])
        self.assertEqual([cc[11], cc[12], cc[13]], list(COLUMNAS_HISTORICAS))
        # La representación ordena las columnas por nombre: el orden físico no forma parte de la huella.
        nombres = [x["nombre"] for t in representacion_estructural_sqlite(c)["tablas"]
                   if t["nombre"] == "clientes" for x in t["columnas"]]
        self.assertEqual(nombres, sorted(nombres))

    def test_integridad_claves_foraneas_y_segunda_ejecucion(self):
        for ruta in (self.ruta_migrada, self.ruta_migrada_2):
            con = _abrir(ruta)
            self.addCleanup(con.close)
            self.assertEqual(con.execute("PRAGMA integrity_check").fetchall(), [("ok",)])
            self.assertEqual(con.execute("PRAGMA foreign_key_check").fetchall(), [])
        a, b = _abrir(self.ruta_migrada), _abrir(self.ruta_migrada_2)
        self.addCleanup(a.close)
        self.addCleanup(b.close)
        self.assertEqual(_instantanea(a), _instantanea(b))
        self.assertEqual(_huella(b), HUELLA_9B_MIGRADA)


class ConservacionDeValoresTest(_Base):
    def test_valores_y_tipos_historicos_se_conservan_exactamente(self):
        h, m = _abrir(self.ruta_hist), _abrir(self.ruta_migrada)
        self.addCleanup(h.close)
        self.addCleanup(m.close)
        self.assertEqual(_filas_con_tipo(h, "clientes", COLUMNAS_9B), _filas_con_tipo(m, "clientes", COLUMNAS_9B))
        esperado = {
            1: (("Hosting Básico", "text"), (1500.5, "real"), (10.0, "real")),
            2: ((None, "null"), (None, "null"), (None, "null")),
            3: (("", "text"), (0.0, "real"), (0.0, "real")),
            4: (("Diseño 'web' \"ñandú\" ✓ 100% _x; --", "text"), (-250.75, "real"), (5.5, "real")),
            5: (("123", "text"), (1234567.891, "real"), (99.99, "real")),
            6: (("Solo servicio", "text"), (0.1, "real"), (-1.0, "real")),
            7: (("Razón vacía", "text"), (1e15, "real"), (0.0, "real")),
        }
        for id_, valores in esperado.items():
            fila = m.execute(
                "SELECT servicio, typeof(servicio), importe, typeof(importe), descuento, typeof(descuento) "
                "FROM clientes WHERE id=?", (id_,)).fetchone()
            self.assertEqual(((fila[0], fila[1]), (fila[2], fila[3]), (fila[4], fila[5])), valores, id_)

    def test_identificadores_y_sqlite_sequence_de_clientes(self):
        h, m = _abrir(self.ruta_hist), _abrir(self.ruta_migrada)
        self.addCleanup(h.close)
        self.addCleanup(m.close)
        self.assertEqual([f[0] for f in m.execute("SELECT id FROM clientes ORDER BY id")], [1, 2, 3, 4, 5, 6, 7])
        self.assertEqual(_secuencias(h)["clientes"], ID_ALTO_ELIMINADO)
        self.assertEqual(_secuencias(m)["clientes"], ID_ALTO_ELIMINADO)
        nuevo = m.execute("INSERT INTO clientes(nombre) VALUES ('x')").lastrowid
        self.assertEqual(nuevo, ID_ALTO_ELIMINADO + 1)
        m.rollback()

    def test_columnas_comunes_y_nombre_vacio_con_razon_social(self):
        h, m = _abrir(self.ruta_hist), _abrir(self.ruta_migrada)
        self.addCleanup(h.close)
        self.addCleanup(m.close)
        # 9b6a850 no tenía nombre: crear_base() lo agrega como '' para todos los clientes.
        self.assertEqual({f[0] for f in m.execute("SELECT nombre FROM clientes")}, {""})
        self.assertEqual(m.execute("SELECT COUNT(*) FROM clientes").fetchone(), (7,))
        self.assertEqual(
            m.execute("SELECT COALESCE(NULLIF(razon_social, ''), nombre) FROM clientes ORDER BY id").fetchall(),
            [("Alfa Ficticia SA",), ("Beta Ficticia SRL",), ("Gamma Ficticia",),
             ("Delta Ñandú 'S.A.' \"ficticia\" %_;--",), ("Épsilon Ficticia",), ("",), ("",)],
        )

    def test_las_tablas_nuevas_arrancan_vacias_y_el_recalculo_de_servicios_no_toca_clientes(self):
        # Separación explícita: 9b6a850 solo tenía clientes; el resto lo crea crear_base().
        h, m = _abrir(self.ruta_hist), _abrir(self.ruta_migrada)
        self.addCleanup(h.close)
        self.addCleanup(m.close)
        self.assertEqual(_tablas(h), ["clientes"])
        for tabla in ("servicios", "resumenes", "cobros", "servicio_renovaciones", "resumen_conceptos"):
            self.assertEqual(m.execute(f'SELECT COUNT(*) FROM "{tabla}"').fetchone(), (0,), tabla)

    def test_no_se_inventan_equivalencias_en_tablas_actuales(self):
        m = _abrir(self.ruta_migrada)
        self.addCleanup(m.close)
        self.assertEqual(m.execute("SELECT COUNT(*) FROM servicios").fetchone(), (0,))
        self.assertEqual(m.execute("SELECT COUNT(*) FROM catalogo_servicios WHERE nombre LIKE '%Hosting B%'")
                         .fetchone(), (0,))

    def test_la_segunda_ejecucion_no_cambia_valores_historicos(self):
        a, b = _abrir(self.ruta_migrada), _abrir(self.ruta_migrada_2)
        self.addCleanup(a.close)
        self.addCleanup(b.close)
        self.assertEqual(_filas_con_tipo(a, "clientes", sorted(_columnas(a, "clientes"))),
                         _filas_con_tipo(b, "clientes", sorted(_columnas(b, "clientes"))))


def _normalizar(valor):
    if isinstance(valor, str):
        return re.sub(r"\d{4}-\d\d-\d\d[T ]\d\d:\d\d:\d\d(\.\d+)?", "<ts>", valor)
    if isinstance(valor, (list, tuple)):
        return [_normalizar(v) for v in valor]
    if isinstance(valor, dict):
        return {k: _normalizar(v) for k, v in valor.items()}
    if valor is None or isinstance(valor, (int, float, bytes)):
        return valor
    return _normalizar(repr(valor))


def _capturar(funcion):
    try:
        return ("ok", _normalizar(funcion()))
    except Exception as error:  # el tipo y el mensaje deben ser idénticos en ambos esquemas
        return ("error", type(error).__name__, str(error))


def _cliente_nuevo(**extra):
    base = dict(razon_social="Cliente Nuevo Ñ", codigo="N001", nombre_comercial="Nuevo", responsable="Nora",
                direccion="Calle 1", localidad="Rosario", telefono="341-9", whatsapp="341-8",
                email="n@ficticio.test", cuit="30-11111111-1", iva="Monotributo", tipo_factura="C",
                monotributo_facturacion="Monotributo 1", modalidad_comprobante="Factura electrónica",
                emisor_habitual="FM Master 98.3", vencimiento=15, estado="Activo", observaciones="obs",
                fecha_alta="2026-01-01", fecha_modificacion="2026-01-01")
    base.update(extra)
    return Cliente(**base)


def _flujos():
    """Ejecuta flujos reales contra la base redirigida; devuelve resultados comparables."""
    r = {}
    alta = _cliente_nuevo()
    r["alta"] = _capturar(lambda: ClienteService.guardar(alta))
    nuevo_id = r["alta"][1]
    r["obtener_nuevo"] = _capturar(lambda: ClienteService.obtener(nuevo_id))
    r["obtener_historicos"] = _capturar(lambda: [ClienteService.obtener(i) for i in range(1, 8)])
    r["busqueda"] = _capturar(lambda: [ClienteService.buscar(t) for t in ("Ficticia", "Nuevo", "ñandú", "%", "_", "zzz", "")])
    r["listado"] = _capturar(ClienteService.listar)
    r["contactos"] = _capturar(ClienteService.listar_contactos)
    modificado = _cliente_nuevo(id=nuevo_id, razon_social="Cliente Modificado", modalidad_comprobante="Solo Resumen",
                                emisor_habitual="Monotributo 2", fecha_modificacion="2026-02-01")
    r["modificar"] = _capturar(lambda: ClienteService.actualizar(modificado))
    r["obtener_modificado"] = _capturar(lambda: ClienteService.obtener(nuevo_id))
    hist = _cliente_nuevo(id=1, razon_social="Alfa Modificada", codigo="C001")
    r["modificar_historico"] = _capturar(lambda: ClienteService.actualizar(hist))
    r["obtener_historico_1"] = _capturar(lambda: ClienteService.obtener(1))

    servicio = Servicio(cliente_id=1, concepto="Hosting Ficticio", descripcion="d", cantidad=2, importe=1000.0,
                        descuento=100.0, fecha_inicio="2026-01-01", fecha_fin="2026-12-31", renovable=1)
    r["servicio_alta"] = _capturar(lambda: ServicioService.guardar(servicio))
    r["servicio_listar"] = _capturar(lambda: ServicioService.listar(1))
    r["total_cliente"] = _capturar(lambda: ServicioService.total_cliente(1, date(2026, 2, 1)))
    r["renovar"] = _capturar(lambda: ServicioService.listar_para_renovacion(date(2027, 1, 15)))
    r["resumen_generar"] = _capturar(lambda: ResumenService.generar_desde_servicios(1, date(2026, 2, 1)))
    r["resumen_listar"] = _capturar(lambda: ResumenService.listar(1))
    r["resumen_obtener_cliente"] = _capturar(lambda: ResumenService.obtener_cliente(1))
    r["resumen_emisor"] = _capturar(lambda: ResumenService.obtener_emisor_de_cliente(1))
    r["resumen_pendientes"] = _capturar(lambda: ResumenService.listar_pendientes(date(2026, 3, 1)))
    r["cobro_alta"] = _capturar(lambda: CobroService.guardar(
        Cobro(cliente_id=1, fecha="2026-02-05", importe=500.0, forma_pago="Efectivo", comprobante="R-1",
              observaciones="ficticio")))
    r["cobro_listar"] = _capturar(lambda: CobroService.listar(1))
    r["cuenta_corriente"] = _capturar(lambda: (CobroService.totales(1), CobroService.resumenes_cliente(1)))
    r["crm_contacto"] = _capturar(lambda: ContactoService.guardar(
        Contacto(cliente_id=1, fecha="2026-02-01", hora="10:00", tipo="Llamada", resultado="Pendiente",
                 observaciones="o", proximo_contacto="2099-01-01", vendedor="v", creado="2026-02-01T10:00:00")))
    r["crm_listar"] = _capturar(lambda: ContactoService.listar(1))
    r["crm_resumen"] = _capturar(lambda: (ContactoService.resumen_cliente(1), ContactoService.semaforo_cliente(1),
                                          ContactoService.semaforo_cliente(2)))
    r["oportunidad"] = _capturar(lambda: OportunidadService.guardar(
        Oportunidad(cliente_id=1, nombre_potencial="Pot", telefono="1", whatsapp="1", email="e@f.test",
                    fecha="2026-02-01", origen="Web", servicio_interes="Hosting", importe_estimado=10.0,
                    probabilidad=50.0, estado="Nueva", proximo_contacto="2099-01-01", observaciones="o",
                    creado="2026-02-01T10:00:00")))
    r["oportunidad_listar"] = _capturar(lambda: OportunidadService.listar("Alfa"))
    for informe in ("Clientes activos", "Clientes con saldo pendiente", "Servicios activos",
                    "Resúmenes emitidos por período", "Cobros por período", "Facturación mensual",
                    "Deuda total por cliente"):
        r["informe:" + informe] = _capturar(lambda i=informe: InformesService.generar(
            i, "2026-01-01", "2026-12-31")["filas"])
    r["informe:agenda"] = _capturar(lambda: InformesService.generar(
        "Agenda Telefónica de Clientes", agenda_todos=True, agenda_telefono=True, agenda_whatsapp=True,
        agenda_email=True)["filas"])
    # Contexto fiscal y emisor/modalidad, sin red.
    r["fiscal_cliente"] = _capturar(lambda: FacturacionService.resolver_cliente(1))
    r["fiscal_conceptos"] = _capturar(lambda: FacturacionService.resolver_conceptos(1))
    r["fiscal_emisor"] = _capturar(lambda: FacturacionService.resolver_emisor(1))
    r["fiscal_validar"] = _capturar(lambda: FacturacionService.validar_resumen_para_facturar(1))
    modalidades = []
    for modalidad, emisor in (("Solo Resumen", ""), ("Solo Resumen", "FM Master 98.3"), ("Factura electrónica", "EMISOR:1"),
                              ("Factura electrónica", "Monotributo 1"), ("Factura electrónica", "Monotributo 2")):
        ClienteService.actualizar(_cliente_nuevo(id=2, razon_social="Beta Ficticia SRL", codigo="C002",
                                                 modalidad_comprobante=modalidad, emisor_habitual=emisor,
                                                 monotributo_facturacion="No aplica"))
        con = database_real.conectar()
        try:
            modalidades.append(_normalizar(ResumenService._resolver_datos_fiscales_cliente(con.cursor(), 2)))
        finally:
            con.close()
    r["emisor_modalidad"] = ("ok", modalidades)
    return r


def _copiar_y_flujos(origen, destino):
    shutil.copy2(origen, destino)
    trazas = []
    conectar_original = sqlite3.connect

    def conectar_con_traza(*args, **kwargs):
        con = conectar_original(*args, **kwargs)
        con.set_trace_callback(trazas.append)
        return con

    with patch.object(database_real, "DB_NAME", destino), patch.object(sqlite3, "connect", conectar_con_traza):
        resultados = _flujos()
    return resultados, trazas


class CompatibilidadFuncionalTest(_Base):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.ra, cls.ta = _copiar_y_flujos(cls.ruta_actual, str(cls.dir / "func_actual.db"))
        cls.rm, cls.tm = _copiar_y_flujos(cls.ruta_migrada, str(cls.dir / "func_migrada.db"))

    def test_todos_los_flujos_devuelven_resultados_identicos_en_ambos_esquemas(self):
        self.assertEqual(list(self.ra), list(self.rm))
        for nombre in self.ra:
            with self.subTest(flujo=nombre):
                self.assertEqual(self.ra[nombre], self.rm[nombre])

    def test_flujos_representativos_no_fallaron_en_ninguno(self):
        obligatorios = ("alta", "obtener_nuevo", "obtener_historicos", "busqueda", "listado", "contactos",
                        "modificar", "servicio_alta", "servicio_listar", "resumen_generar", "resumen_listar",
                        "resumen_obtener_cliente", "cobro_alta", "cuenta_corriente", "crm_contacto",
                        "crm_resumen", "oportunidad", "emisor_modalidad", "fiscal_cliente", "fiscal_conceptos")
        for esquema, resultados in (("actual", self.ra), ("migrada", self.rm)):
            for nombre in obligatorios:
                self.assertEqual(resultados[nombre][0], "ok", (esquema, nombre, resultados[nombre]))

    def test_contrato_posicional_de_obtener_es_el_mismo(self):
        campos = ("id", "codigo", "razon_social", "nombre_comercial", "responsable", "direccion", "localidad",
                  "telefono", "whatsapp", "email", "cuit", "iva", "tipo_factura", "monotributo_facturacion",
                  "emisor_id", "emisor_recomendado_id", "vencimiento", "estado", "observaciones", "fecha_alta",
                  "fecha_modificacion", "modalidad_comprobante", "emisor_habitual")
        for resultados in (self.ra, self.rm):
            for fila in resultados["obtener_historicos"][1]:
                self.assertEqual(len(fila), len(campos))
            fila = resultados["obtener_nuevo"][1]
            self.assertEqual(fila[campos.index("razon_social")], "Cliente Nuevo Ñ")
            self.assertEqual(fila[campos.index("cuit")], "30-11111111-1")
            self.assertEqual(fila[campos.index("iva")], "Monotributo")
            self.assertEqual(fila[campos.index("modalidad_comprobante")], "Factura electrónica")

    def test_clientes_historicos_con_nombre_vacio_usan_razon_social(self):
        filas = self.rm["obtener_historicos"][1]
        self.assertEqual([f[2] for f in filas[:5]], ["Alfa Ficticia SA", "Beta Ficticia SRL", "Gamma Ficticia",
                                                     "Delta Ñandú 'S.A.' \"ficticia\" %_;--", "Épsilon Ficticia"])
        self.assertEqual([f[2] for f in filas[5:]], ["", ""])
        # Defaults de COALESCE para históricos sin modalidad/emisor explícitos.
        self.assertEqual((filas[1][21], filas[1][22]), ("Solo Resumen", "FM Master 98.3"))

    def test_los_valores_historicos_sobreviven_a_las_operaciones_actuales(self):
        con = _abrir(str(self.dir / "func_migrada.db"))
        self.addCleanup(con.close)
        h = _abrir(self.ruta_hist)
        self.addCleanup(h.close)
        antes, despues = _historicas(h), _historicas(con)
        # Incluye el cliente 1 modificado vía ClienteService.actualizar.
        for id_ in range(1, 8):
            self.assertEqual(despues[id_], antes[id_], id_)
        nuevo = self.rm["alta"][1]
        self.assertEqual(despues[nuevo], (None, "null", None, "null", None, "null"))

    def test_ninguna_consulta_usa_select_todas_las_columnas_ni_insert_sin_columnas(self):
        for trazas in (self.ta, self.tm):
            for sql in trazas:
                if "clientes" not in sql.lower():
                    continue
                self.assertIsNone(re.search(r"select\s+(distinct\s+)?\*\s+from\s+clientes", sql, re.I), sql)
                self.assertIsNone(re.search(r"\b(c|cl|clientes)\.\*", sql, re.I), sql)
                self.assertIsNone(re.search(r"into\s+clientes\s*(values|select)", sql, re.I), sql)

    def test_integridad_tras_los_flujos(self):
        for nombre in ("func_actual.db", "func_migrada.db"):
            con = _abrir(str(self.dir / nombre))
            self.addCleanup(con.close)
            self.assertEqual(con.execute("PRAGMA integrity_check").fetchall(), [("ok",)], nombre)
            self.assertEqual(con.execute("PRAGMA foreign_key_check").fetchall(), [], nombre)

    def test_la_estructura_tras_los_flujos_se_mantiene(self):
        for nombre, esperada in (("func_actual.db", HUELLA_ACTUAL), ("func_migrada.db", HUELLA_9B_MIGRADA)):
            con = _abrir(str(self.dir / nombre))
            self.addCleanup(con.close)
            self.assertEqual(_huella(con), esperada, nombre)


COLUMNAS_HISTORICAS_ORDEN = COLUMNAS_HISTORICAS


def _historicas(con):
    """id -> (valor, tipo) de servicio, importe y descuento."""
    filas = con.execute(
        "SELECT id, servicio, typeof(servicio), importe, typeof(importe), descuento, typeof(descuento) "
        "FROM clientes ORDER BY id").fetchall()
    return {f[0]: f[1:] for f in filas}


class EliminacionDeClienteTest(_Base):
    def test_eliminar_un_cliente_solo_quita_su_fila(self):
        ruta = str(self.dir / "eliminar.db")
        shutil.copy2(self.ruta_migrada, ruta)
        with patch.object(database_real, "DB_NAME", ruta):
            ClienteService.eliminar(3)
        con = _abrir(ruta)
        self.addCleanup(con.close)
        h = _abrir(self.ruta_hist)
        self.addCleanup(h.close)
        antes = _historicas(h)
        despues = _historicas(con)
        self.assertEqual(set(despues), {1, 2, 4, 5, 6, 7})
        for id_ in despues:
            self.assertEqual(despues[id_], antes[id_])
        self.assertEqual(_secuencias(con)["clientes"], ID_ALTO_ELIMINADO)


class FkYModalidadTest(_Base):
    def test_claves_foraneas_hacia_clientes_en_el_esquema_migrado(self):
        con = _abrir(self.ruta_migrada)
        self.addCleanup(con.close)
        con.execute("PRAGMA foreign_keys=ON")
        with self.assertRaises(sqlite3.IntegrityError):
            con.execute("INSERT INTO cobros(cliente_id, fecha, importe) VALUES (12345, '2026-01-01', 1)")
        con.rollback()
        con.execute("INSERT INTO cobros(cliente_id, fecha, importe) VALUES (4, '2026-01-01', 1)")
        self.assertEqual(con.execute("PRAGMA foreign_key_check").fetchall(), [])
        con.rollback()


def _variante(*, reemplazos=(), antes_extra=(), despues_extra=()):
    """Esquema 9b6a850 modificado, migrado con crear_base() en memoria (aislado)."""
    con = sqlite3.connect(":memory:")
    for _, _, _, sql in ESQUEMAS_HISTORICOS[H_9B][2]:
        for viejo, nuevo in reemplazos:
            sql = sql.replace(viejo, nuevo)
        con.execute(sql)
    for sql in antes_extra:
        con.execute(sql)
    con.commit()
    con.execute("BEGIN IMMEDIATE")
    database_aislado.crear_base(conexion=con)
    con.commit()
    for sql in despues_extra:
        con.execute(sql)
    con.commit()
    return con


COBROS_SIN_FK = (
    "CREATE TABLE cobros(id INTEGER PRIMARY KEY AUTOINCREMENT, cliente_id INTEGER NOT NULL, fecha TEXT NOT NULL,"
    " importe REAL NOT NULL DEFAULT 0, forma_pago TEXT, comprobante TEXT, factura_arca_id INTEGER,"
    " observaciones TEXT)"
)


class ValidacionEstrictaTest(unittest.TestCase):
    def test_la_huella_oficial_distingue_variantes_y_no_las_acepta_genericamente(self):
        variantes = {
            "columna_adicional_desconocida": _variante(despues_extra=("ALTER TABLE clientes ADD COLUMN extra_a TEXT",)),
            "otra_columna_adicional": _variante(despues_extra=("ALTER TABLE clientes ADD COLUMN extra_b TEXT",)),
            "tipo_incompatible": _variante(reemplazos=(("importe REAL", "importe TEXT"),)),
            "restriccion_modificada": _variante(reemplazos=(("servicio TEXT", "servicio TEXT NOT NULL DEFAULT ''"),)),
            "default_modificado": _variante(reemplazos=(("descuento REAL", "descuento REAL DEFAULT 0"),)),
            "fk_faltante": _variante(antes_extra=(COBROS_SIN_FK,)),
            "indice_adicional": _variante(despues_extra=("CREATE INDEX idx_clientes_servicio_x ON clientes(servicio)",)),
            "indice_faltante": _variante(despues_extra=("DROP INDEX idx_resumenes_cliente",)),
            "sin_columnas_historicas": _variante(reemplazos=(
                ("        servicio TEXT,\n", ""), ("        importe REAL,\n", ""), ("        descuento REAL,\n", ""))),
        }
        huellas = {}
        for nombre, con in variantes.items():
            self.addCleanup(con.close)
            huellas[nombre] = _huella(con)
        conocidas = {HUELLA_ACTUAL, HUELLA_9B_MIGRADA, HUELLA_9B_SIN_MIGRAR, HUELLA_COMUN_8C_49_MIGRADOS}
        for nombre, huella in huellas.items():
            self.assertNotIn(huella, conocidas - ({HUELLA_ACTUAL} if nombre == "sin_columnas_historicas" else set()),
                             nombre)
        # Dos esquemas con columnas adicionales distintas tampoco son equivalentes entre sí.
        self.assertNotEqual(huellas["columna_adicional_desconocida"], huellas["otra_columna_adicional"])
        self.assertEqual(len(set(huellas.values())) - (huellas["sin_columnas_historicas"] == HUELLA_ACTUAL),
                         len(huellas) - (huellas["sin_columnas_historicas"] == HUELLA_ACTUAL))

    def test_las_huellas_de_referencia_se_mantienen_en_memoria(self):
        con = _variante()
        self.addCleanup(con.close)
        self.assertEqual(_huella(con), HUELLA_9B_MIGRADA)


class AislamientoDelModuloTest(unittest.TestCase):
    def test_el_codigo_de_produccion_no_depende_del_orden_ni_de_las_columnas_historicas(self):
        archivos = list(RAIZ.glob("*.py")) + list((RAIZ / "pdf").glob("*.py"))
        for carpeta in ("services", "views", "models", "scripts"):
            archivos += list((RAIZ / carpeta).rglob("*.py"))
        self.assertGreater(len(archivos), 30)
        for ruta in archivos:
            texto = ruta.read_text(encoding="utf-8", errors="replace")
            with self.subTest(archivo=ruta.name):
                self.assertIsNone(re.search(r"select\s+(distinct\s+)?\*\s+from\s+clientes\b", texto, re.I))
                self.assertIsNone(re.search(r"\b(c|cl|cli)\.\*", texto))
                self.assertIsNone(re.search(r"into\s+clientes\b(?!\s*\()", texto, re.I))
                self.assertIsNone(re.search(r"\b(c|cl|cli|clientes)\.(servicio|importe|descuento)\b", texto))

    def test_el_modelo_cliente_declara_los_campos_pero_el_servicio_no_los_persiste(self):
        campos = Cliente.__dataclass_fields__
        for nombre in COLUMNAS_HISTORICAS:
            self.assertIn(nombre, campos)
        fuente = (RAIZ / "services" / "cliente_service.py").read_text(encoding="utf-8")
        for nombre in COLUMNAS_HISTORICAS:
            self.assertNotRegex(fuente, rf"\b{nombre}\b")

    def test_database_real_bloqueada_durante_la_clase_base(self):
        self.assertTrue(str(RUTA_REAL).endswith("fm_master.db"))
        self.assertNotIn("fm_5d6_", str(RUTA_REAL))


if __name__ == "__main__":
    unittest.main()
