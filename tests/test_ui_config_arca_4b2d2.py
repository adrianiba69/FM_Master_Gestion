import inspect
import io
import sqlite3
import tempfile
import unittest
from contextlib import closing, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from database import crear_tabla_emisor_fiscal_arca_config, migrar_emisor_fiscal_arca_config
from services.arca import ambiente_arca
from services.emisor_fiscal_service import EmisorFiscalService
from views import emisores_fiscales as vista
from views.emisores_fiscales import EmisoresFiscalesWindow


class FakeEntry:
    def __init__(self, valor=""):
        self.valor = valor

    def get(self):
        return self.valor

    def delete(self, _inicio, _fin=None):
        self.valor = ""

    def insert(self, _indice, texto):
        self.valor = str(texto) + self.valor


class FakeText(FakeEntry):
    def get(self, _inicio=None, _fin=None):
        return self.valor

    def delete(self, _inicio, _fin=None):
        self.valor = ""


class FakeCombo:
    def __init__(self, valor=""):
        self.valor = valor

    def get(self):
        return self.valor

    def set(self, valor):
        self.valor = valor


class FakeVar(FakeCombo):
    pass


class FakeLabel:
    def __init__(self):
        self.texto = ""

    def configure(self, **opciones):
        self.texto = opciones.get("text", self.texto)


class FakeButton:
    def __init__(self):
        self.state = "normal"

    def configure(self, **opciones):
        self.state = opciones.get("state", self.state)


class FakeTabla:
    def get_children(self):
        return []

    def delete(self, *_args):
        pass

    def insert(self, *_args, **_kwargs):
        pass

    def selection(self):
        return ()

    def selection_remove(self, *_args):
        pass


COLUMNAS_ARCA_LEGACY = "ambiente_arca, punto_venta, ruta_certificado, ruta_clave_privada, carpeta_facturas, configuracion_arca_completa"


class UiConfiguracionArcaPorAmbienteTest(unittest.TestCase):
    def setUp(self):
        self.temporal = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporal.cleanup)
        self.raiz = Path(self.temporal.name)
        self.base = self.raiz / "config.db"
        self.h = ("00002", str(self.raiz / "h" / "cert_h.crt"), str(self.raiz / "h" / "clave_h.key"), str(self.raiz / "h" / "fact"))
        self.p = ("00009", str(self.raiz / "p" / "cert_p.crt"), str(self.raiz / "p" / "clave_p.key"), str(self.raiz / "p" / "fact"))
        with closing(sqlite3.connect(self.base)) as conexion:
            conexion.execute(
                "CREATE TABLE emisores_fiscales(id INTEGER PRIMARY KEY, razon_social TEXT NOT NULL DEFAULT '', "
                "nombre_fantasia TEXT, cuit TEXT, condicion_iva TEXT, tipo_factura TEXT, punto_venta TEXT, "
                "activo INTEGER DEFAULT 1, observaciones TEXT, ambiente_arca TEXT DEFAULT 'Homologación', "
                "domicilio TEXT DEFAULT '', ingresos_brutos TEXT DEFAULT '', fecha_inicio_actividades TEXT DEFAULT '', "
                "ruta_certificado TEXT DEFAULT '', ruta_clave_privada TEXT DEFAULT '', carpeta_facturas TEXT DEFAULT '', "
                "configuracion_arca_completa INTEGER DEFAULT 0)"
            )
            conexion.execute(
                "INSERT INTO emisores_fiscales(id, razon_social, nombre_fantasia, cuit, condicion_iva, tipo_factura, "
                "punto_venta, activo, observaciones, ambiente_arca, domicilio, ingresos_brutos, fecha_inicio_actividades, "
                "ruta_certificado, ruta_clave_privada, carpeta_facturas, configuracion_arca_completa) "
                "VALUES(1,'Emisor Uno','Uno','20-11111111-2','Monotributo','Factura C',?,1,'','Homologación',"
                "'Calle 1','IIBB','2020-01-01',?,?,?,1)",
                self.h,
            )
            crear_tabla_emisor_fiscal_arca_config(conexion.cursor())
            with redirect_stdout(io.StringIO()):
                migrar_emisor_fiscal_arca_config(conexion.cursor())
            conexion.commit()

        for objetivo, opciones in (
            ("services.emisor_fiscal_service.conectar", {"side_effect": lambda: sqlite3.connect(self.base)}),
            ("urllib.request.urlopen", {"side_effect": AssertionError("red prohibida")}),
        ):
            parche = patch(objetivo, **opciones)
            parche.start()
            self.addCleanup(parche.stop)
        parche_mb = patch.object(vista, "messagebox")
        self.messagebox = parche_mb.start()
        self.addCleanup(parche_mb.stop)
        self.messagebox.askyesno.return_value = True
        parche_fd = patch.object(vista, "filedialog")
        self.filedialog = parche_fd.start()
        self.addCleanup(parche_fd.stop)
        self.ventana = self.construir_ventana()

    # -- utilidades --------------------------------------------------------
    @staticmethod
    def construir_ventana():
        ventana = object.__new__(EmisoresFiscalesWindow)
        ventana.emisor_id_actual = None
        ventana.filtro_estado = "Todos"
        ventana._inicializar_estado_arca()
        for nombre in ("entry_razon_social", "entry_domicilio", "entry_nombre_fantasia", "entry_cuit",
                       "entry_ingresos_brutos", "entry_fecha_inicio_actividades", "entry_buscar"):
            setattr(ventana, nombre, FakeEntry())
        ventana.combo_condicion_iva = FakeCombo("Monotributo")
        ventana.combo_tipo_factura = FakeCombo("Factura C")
        ventana.text_observaciones = FakeText()
        ventana.var_activo = FakeVar(1)
        ventana.tabla = FakeTabla()
        ventana.label_ambiente_activo = FakeLabel()
        ventana.botones_ambiente_activo = {ambiente: FakeButton() for ambiente in ventana.AMBIENTES_ARCA}
        for ambiente in ventana.AMBIENTES_ARCA:
            ventana.arca_entries[ambiente] = {campo: FakeEntry() for campo in ventana.CAMPOS_ARCA}
            ventana.arca_estado_labels[ambiente] = FakeLabel()
        return ventana

    def sql(self, consulta, parametros=()):
        with closing(sqlite3.connect(self.base)) as conexion:
            filas = conexion.execute(consulta, parametros).fetchall()
            conexion.commit()
            return filas

    def hija(self, ambiente, emisor_id=1):
        filas = self.sql(
            "SELECT id, punto_venta, ruta_certificado, ruta_clave_privada, carpeta_facturas FROM emisor_fiscal_arca_config "
            "WHERE emisor_fiscal_id=? AND ambiente_arca=?",
            (emisor_id, ambiente),
        )
        return filas[0] if filas else None

    def legacy_arca(self, emisor_id=1):
        return self.sql(f"SELECT {COLUMNAS_ARCA_LEGACY} FROM emisores_fiscales WHERE id=?", (emisor_id,))[0]

    def snapshot_db(self):
        return (
            self.sql("SELECT * FROM emisores_fiscales ORDER BY id"),
            self.sql("SELECT * FROM emisor_fiscal_arca_config ORDER BY id"),
        )

    def valores(self, ambiente):
        return self.ventana._valores_formulario_arca(ambiente)

    def escribir(self, ambiente, campo, valor):
        entrada = self.ventana.arca_entries[ambiente][campo]
        entrada.delete(0, "end")
        entrada.insert(0, valor)

    def estado(self, ambiente):
        return self.ventana.arca_estado_labels[ambiente].texto

    def crear_p(self):
        EmisorFiscalService.guardar_configuracion_arca(1, "PRODUCCION", *self.p)

    def mensajes(self):
        llamadas = []
        for metodo in (self.messagebox.showerror, self.messagebox.showwarning, self.messagebox.showinfo):
            llamadas.extend(" ".join(str(a) for a in llamada.args) for llamada in metodo.call_args_list)
        return llamadas

    # -- carga -------------------------------------------------------------
    def test_carga_h_y_p_independientes(self):
        self.crear_p()
        self.ventana._cargar_emisor(1)
        self.assertEqual(self.valores("HOMOLOGACION"), self.h)
        self.assertEqual(self.valores("PRODUCCION"), self.p)
        self.assertEqual(self.estado("HOMOLOGACION"), "Estado: Configurado")
        self.assertEqual(self.estado("PRODUCCION"), "Estado: Configurado")
        self.assertEqual(self.ventana.ambiente_activo, "HOMOLOGACION")
        self.assertEqual(self.ventana.label_ambiente_activo.texto, "Homologación")
        self.assertEqual(self.ventana.botones_ambiente_activo["HOMOLOGACION"].state, "disabled")
        self.assertEqual(self.ventana.botones_ambiente_activo["PRODUCCION"].state, "normal")

    def test_falta_p_campos_vacios_sin_copiar_h_ni_crear_hija(self):
        antes = self.snapshot_db()
        self.ventana._cargar_emisor(1)
        self.assertEqual(self.valores("PRODUCCION"), ("", "", "", ""))
        self.assertEqual(self.estado("PRODUCCION"), "Estado: Sin configurar")
        self.assertEqual(self.snapshot_db(), antes)
        self.assertIsNone(self.hija("PRODUCCION"))

    def test_cambiar_pestana_no_cambia_ambiente_activo(self):
        fuente = inspect.getsource(EmisoresFiscalesWindow._crear_seccion_arca)
        bloque_tabview = fuente.split("CTkTabview(", 1)[1].split(")", 1)[0]
        self.assertNotIn("command", bloque_tabview)
        self.crear_p()
        self.ventana._cargar_emisor(1)
        self.escribir("PRODUCCION", "punto_venta", "00011")
        self.ventana._refrescar_estado_arca("PRODUCCION")
        self.assertEqual(self.ventana.ambiente_activo, "HOMOLOGACION")
        self.assertEqual(self.legacy_arca()[0], "Homologación")

    # -- seleccionar -------------------------------------------------------
    def test_seleccionar_archivos_no_persiste(self):
        self.ventana._cargar_emisor(1)
        antes = self.snapshot_db()
        self.filedialog.askopenfilename.return_value = "C:/ficticio/nuevo.crt"
        self.filedialog.askdirectory.return_value = "C:/ficticio/carpeta"
        self.ventana._seleccionar_certificado("PRODUCCION")
        self.ventana._seleccionar_clave_privada("PRODUCCION")
        self.ventana._seleccionar_carpeta_facturas("PRODUCCION")
        self.assertEqual(self.valores("PRODUCCION"), ("", "C:/ficticio/nuevo.crt", "C:/ficticio/nuevo.crt", "C:/ficticio/carpeta"))
        self.assertEqual(self.valores("HOMOLOGACION"), self.h)
        self.assertEqual(self.estado("PRODUCCION"), "Estado: Cambios sin guardar")
        self.assertEqual(self.estado("HOMOLOGACION"), "Estado: Configurado")
        self.assertEqual(self.snapshot_db(), antes)

    def test_metodos_de_persistencia_inmediata_eliminados(self):
        for nombre in ("_persistir_ruta_certificado", "_persistir_ruta_clave_privada", "_persistir_ruta_carpeta_facturas"):
            self.assertFalse(hasattr(EmisoresFiscalesWindow, nombre))

    # -- guardado ----------------------------------------------------------
    def test_guardar_h_no_toca_p_y_espeja_por_servicio(self):
        self.crear_p()
        hija_p = self.hija("PRODUCCION")
        self.ventana._cargar_emisor(1)
        self.escribir("HOMOLOGACION", "punto_venta", "00003")
        self.ventana.guardar_emisor()
        self.assertEqual(self.hija("HOMOLOGACION")[1], "00003")
        self.assertEqual(self.hija("PRODUCCION"), hija_p)
        self.assertEqual(self.legacy_arca()[:2], ("Homologación", "00003"))

    def test_guardar_p_no_toca_h_ni_legacy(self):
        self.crear_p()
        hija_h, legacy = self.hija("HOMOLOGACION"), self.legacy_arca()
        self.ventana._cargar_emisor(1)
        self.escribir("PRODUCCION", "ruta_certificado", "otro_p.crt")
        self.ventana.guardar_emisor()
        self.assertEqual(self.hija("PRODUCCION")[2], "otro_p.crt")
        self.assertEqual(self.hija("HOMOLOGACION"), hija_h)
        self.assertEqual(self.legacy_arca(), legacy)

    def test_guardar_sin_cambios_arca_no_crea_ni_altera_hijas(self):
        hijas, legacy = self.sql("SELECT * FROM emisor_fiscal_arca_config"), self.legacy_arca()
        self.ventana._cargar_emisor(1)
        self.ventana.entry_razon_social.valor = "Razon Nueva"
        with patch.object(EmisorFiscalService, "guardar_configuracion_arca") as guardar_arca:
            self.ventana.guardar_emisor()
        guardar_arca.assert_not_called()
        self.assertEqual(self.sql("SELECT * FROM emisor_fiscal_arca_config"), hijas)
        self.assertEqual(self.legacy_arca(), legacy)
        self.assertEqual(self.sql("SELECT razon_social FROM emisores_fiscales WHERE id=1")[0][0], "Razon Nueva")
        self.assertIsNone(self.hija("PRODUCCION"))

    def test_p_con_cambios_crea_solo_p(self):
        hija_h = self.hija("HOMOLOGACION")
        self.ventana._cargar_emisor(1)
        for campo, valor in zip(self.ventana.CAMPOS_ARCA, ("9", "p.crt", "p.key", "p_fact")):
            self.escribir("PRODUCCION", campo, valor)
        self.ventana.guardar_emisor()
        self.assertEqual(self.hija("PRODUCCION")[1:], ("00009", "p.crt", "p.key", "p_fact"))
        self.assertEqual(self.hija("HOMOLOGACION"), hija_h)

    def test_no_hay_escritura_legacy_directa_desde_la_vista(self):
        fuente = inspect.getsource(vista)
        self.assertNotIn("EmisorFiscalService.actualizar(", fuente)
        self.assertNotIn("validar_configuracion_arca(", fuente)
        self.crear_p()
        self.ventana._cargar_emisor(1)
        self.escribir("HOMOLOGACION", "carpeta_facturas", "h_nueva")
        self.escribir("PRODUCCION", "carpeta_facturas", "p_nueva")
        with patch.object(EmisorFiscalService, "actualizar", side_effect=AssertionError("escritura legacy")) as actualizar:
            self.ventana.guardar_emisor()
        actualizar.assert_not_called()
        self.assertEqual(self.hija("HOMOLOGACION")[4], "h_nueva")
        self.assertEqual(self.hija("PRODUCCION")[4], "p_nueva")
        self.assertEqual(self.legacy_arca()[4], "h_nueva")

    def test_error_arca_conserva_formulario_sin_rutas_en_mensaje(self):
        hija_h = self.hija("HOMOLOGACION")
        self.ventana._cargar_emisor(1)
        self.escribir("HOMOLOGACION", "punto_venta", "0")
        self.ventana.guardar_emisor()
        self.assertEqual(self.hija("HOMOLOGACION"), hija_h)
        self.assertEqual(self.ventana.emisor_id_actual, 1)
        self.assertEqual(self.estado("HOMOLOGACION"), "Estado: Cambios sin guardar")
        self.messagebox.showerror.assert_called_once()
        self.messagebox.showinfo.assert_not_called()
        self.assertFalse(any(str(self.raiz) in mensaje for mensaje in self.mensajes()))

    # -- ambiente activo ---------------------------------------------------
    def test_cambio_de_ambiente_activo_usa_api(self):
        self.crear_p()
        self.ventana._cargar_emisor(1)
        with patch.object(
            EmisorFiscalService, "cambiar_ambiente_arca_activo", wraps=EmisorFiscalService.cambiar_ambiente_arca_activo
        ) as cambiar:
            self.assertTrue(self.ventana.cambiar_ambiente_activo("PRODUCCION"))
        cambiar.assert_called_once_with(1, "PRODUCCION")
        self.messagebox.askyesno.assert_called_once()
        self.assertIn("NO habilita", self.messagebox.askyesno.call_args.args[1])
        self.assertEqual(self.legacy_arca()[:5], ("Producción", *self.p))
        self.assertEqual(self.ventana.label_ambiente_activo.texto, "Producción")
        self.assertEqual(self.ventana.botones_ambiente_activo["PRODUCCION"].state, "disabled")
        with self.assertRaises(ambiente_arca.EmisionProduccionNoHabilitadaError):
            ambiente_arca.asegurar_emision_habilitada(self.legacy_arca()[0])

    def test_destino_inexistente_mantiene_ambiente_anterior(self):
        self.ventana._cargar_emisor(1)
        antes = self.snapshot_db()
        self.assertFalse(self.ventana.cambiar_ambiente_activo("PRODUCCION"))
        self.messagebox.showerror.assert_called_once()
        self.assertEqual(self.ventana.ambiente_activo, "HOMOLOGACION")
        self.assertEqual(self.ventana.label_ambiente_activo.texto, "Homologación")
        self.assertEqual(self.snapshot_db(), antes)

    def test_cambios_sin_guardar_del_destino_impiden_cambio(self):
        self.crear_p()
        self.ventana._cargar_emisor(1)
        self.escribir("PRODUCCION", "punto_venta", "00015")
        antes = self.snapshot_db()
        with patch.object(EmisorFiscalService, "cambiar_ambiente_arca_activo") as cambiar:
            self.assertFalse(self.ventana.cambiar_ambiente_activo("PRODUCCION"))
        cambiar.assert_not_called()
        self.messagebox.showwarning.assert_called_once()
        self.assertEqual(self.ventana.ambiente_activo, "HOMOLOGACION")
        self.assertEqual(self.snapshot_db(), antes)

    def test_cancelar_confirmacion_produccion_no_cambia(self):
        self.crear_p()
        self.ventana._cargar_emisor(1)
        self.messagebox.askyesno.return_value = False
        antes = self.snapshot_db()
        self.assertFalse(self.ventana.cambiar_ambiente_activo("PRODUCCION"))
        self.assertEqual(self.snapshot_db(), antes)

    # -- nuevo emisor --------------------------------------------------------
    def test_nuevo_emisor_sin_datos_arca_no_crea_hijas(self):
        self.ventana._cargar_emisor(1)
        self.ventana.nuevo_emisor()
        self.assertEqual(self.valores("HOMOLOGACION"), ("", "", "", ""))
        self.assertEqual(self.valores("PRODUCCION"), ("", "", "", ""))
        self.assertEqual(self.ventana.ambiente_activo, "HOMOLOGACION")
        self.assertEqual(self.ventana.botones_ambiente_activo["PRODUCCION"].state, "disabled")
        self.ventana.entry_razon_social.valor = "Nuevo"
        self.ventana.entry_cuit.valor = "20-33333333-4"
        self.ventana.guardar_emisor()
        nuevo_id = self.sql("SELECT id FROM emisores_fiscales WHERE razon_social='Nuevo'")[0][0]
        self.assertEqual(self.sql("SELECT * FROM emisor_fiscal_arca_config WHERE emisor_fiscal_id=?", (nuevo_id,)), [])
        self.assertEqual(self.legacy_arca(nuevo_id), ("Homologación", "", "", "", "", 0))

    def test_nuevo_emisor_con_h_crea_solo_h(self):
        self.ventana.nuevo_emisor()
        self.ventana.entry_razon_social.valor = "Nuevo H"
        self.ventana.entry_cuit.valor = "20-44444444-5"
        for campo, valor in zip(self.ventana.CAMPOS_ARCA, ("4", "n.crt", "n.key", "n_fact")):
            self.escribir("HOMOLOGACION", campo, valor)
        self.ventana.guardar_emisor()
        nuevo_id = self.sql("SELECT id FROM emisores_fiscales WHERE razon_social='Nuevo H'")[0][0]
        self.assertEqual(self.hija("HOMOLOGACION", nuevo_id)[1:], ("00004", "n.crt", "n.key", "n_fact"))
        self.assertIsNone(self.hija("PRODUCCION", nuevo_id))
        self.assertEqual(self.legacy_arca(nuevo_id)[:5], ("Homologación", "00004", "n.crt", "n.key", "n_fact"))

    # -- produccion / validacion legacy -----------------------------------
    def test_advertencia_produccion_presente(self):
        self.assertIn("PRODUCCIÓN — Configuración solamente.", EmisoresFiscalesWindow.ADVERTENCIA_PRODUCCION)
        self.assertIn("La emisión real permanece bloqueada.", EmisoresFiscalesWindow.ADVERTENCIA_PRODUCCION)
        fuente = inspect.getsource(EmisoresFiscalesWindow._crear_pestana_arca)
        self.assertIn('if ambiente == "PRODUCCION"', fuente)
        self.assertIn("self.ADVERTENCIA_PRODUCCION", fuente)
        self.assertNotIn("habilitad", EmisoresFiscalesWindow.ADVERTENCIA_PRODUCCION.lower())

    def test_validacion_legacy_retirada(self):
        self.assertFalse(hasattr(EmisoresFiscalesWindow, "validar_configuracion_arca_actual"))
        self.assertNotIn("EmisorFiscalService.validar_configuracion_arca(", inspect.getsource(vista))


if __name__ == "__main__":
    unittest.main()
