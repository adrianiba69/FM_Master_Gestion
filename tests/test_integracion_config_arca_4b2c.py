from contextlib import ExitStack
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import Mock, patch

from database import crear_tabla_emisor_fiscal_arca_config
from services.arca.homologacion_service import HomologacionService
from services.arca.reconciliacion_contracts import ResultadoReconciliacion
from services.arca.reconciliacion_service import ReconciliacionArcaService
from services.arca.recuperacion_local_service import RecuperacionLocalArcaService
from services.arca.wsaa_service import WSAAService
from services.arca.wsaa_login_service import WSAALoginService
from services.arca.wsfe_service import WSFEService
from services.emisor_fiscal_service import EmisorFiscalService
from services.facturacion_service import FacturacionService
from tests.test_ambiente_intentos_3b4c import Base3B4C, H, P, contexto, consulta_autorizada


class IntegracionConfigArcaTest(Base3B4C):
    def setUp(self):
        super().setUp()
        self.sql("CREATE TABLE emisores_fiscales(id INTEGER PRIMARY KEY, ambiente_arca TEXT, "
                 "punto_venta TEXT, ruta_certificado TEXT, ruta_clave_privada TEXT, carpeta_facturas TEXT)")
        self.sql("INSERT INTO emisores_fiscales VALUES(30, 'Producción', '999', 'legacy.crt', 'legacy.key', 'C:/legacy')")
        conexion = self.factory()
        try:
            crear_tabla_emisor_fiscal_arca_config(conexion.cursor())
            conexion.commit()
        finally:
            conexion.close()
        parche = patch("services.emisor_fiscal_service.conectar", side_effect=self.factory)
        parche.start()
        self.addCleanup(parche.stop)
        red = patch("urllib.request.urlopen", side_effect=AssertionError("Red real prohibida"))
        self.red = red.start()
        self.addCleanup(red.stop)

    def config(self, ambiente, pv=5):
        self.sql("INSERT INTO emisor_fiscal_arca_config(emisor_fiscal_id,ambiente_arca,punto_venta,"
                 "ruta_certificado,ruta_clave_privada,carpeta_facturas) VALUES(30,?,?,?,?,?)",
                 (ambiente, str(pv), ambiente + ".crt", ambiente + ".key", "C:/" + ambiente))

    def emitir(self, ambiente=H, tipo="Factura C"):
        emisor = (30, "Emisor", "", "20206871629", "Responsable Inscripto", tipo, 999, 1, "",
                  ambiente, "", "", "", "legacy.crt", "legacy.key", "C:/legacy")
        cliente = (20, "", "Cliente", "", "", "", "", "", "", "", "30712345678", "Responsable Inscripto")
        resumen = SimpleNamespace(id=10, estado_facturacion="Pendiente", cliente_id=20, emisor_fiscal_id=30, total=100,
                                  conceptos=[object()])
        fiscal = {"ok": True, "tipo_comprobante": 1 if tipo == "Factura A" else 11,
                  "neto_factura": 100, "alicuota_iva": 21 if tipo == "Factura A" else 0,
                  "importe_iva_factura": 21 if tipo == "Factura A" else 0,
                  "total_factura_fiscal": 121 if tipo == "Factura A" else 100,
                  "importe_exento_factura": 0, "importe_tot_conc": 0, "importe_tributos": 0,
                  "alicuotas_iva": [], "condicion_iva_receptor_id": 1}
        with ExitStack() as pila:
            pila.enter_context(patch("services.facturacion_service.ResumenService.obtener", return_value=resumen))
            pila.enter_context(patch("services.facturacion_service.FacturaArcaService.listar_por_resumen", return_value=[]))
            pila.enter_context(patch("services.facturacion_service.IntentoEmisionArcaService.listar_activos_por_resumen", return_value=[]))
            for nombre, valor in (
                ("validar_resumen_para_facturar", {"ok": True}),
                ("resolver_cliente", {"ok": True, "cliente": cliente}),
                ("resolver_conceptos", {"ok": True, "resumen": resumen, "conceptos": [object()]}),
                ("resolver_emisor", {"ok": True, "resumen": resumen, "emisor_fiscal": emisor}),
                ("_resolver_emisor_facturacion_id", (40, "id")),
                ("_armar_items_factura_desde_resumen", [{"importe": 100, "cantidad": 1,
                                                       "precio_unitario": 100, "descripcion": "Servicio"}]),
                ("calcular_importes_fiscales", fiscal),
                ("_sumar_importes_items", 100),
                ("_obtener_periodo_facturado", ("", "")),
            ):
                pila.enter_context(patch.object(FacturacionService, nombre, return_value=valor))
            pila.enter_context(patch("services.facturacion_service.FacturaArcaService.validar_pre_guardado", return_value={"ok": True}))
            resolver = pila.enter_context(patch.object(EmisorFiscalService, "obtener_configuracion_arca",
                                                      wraps=EmisorFiscalService.obtener_configuracion_arca))
            enviar = pila.enter_context(patch.object(FacturacionService, "emitir_en_arca",
                                                    return_value={"ok": False, "errores": ["Frontera de prueba"]}))
            resultado = FacturacionService.emitir_desde_resumen(
                10, {"tipo_factura": tipo, "condicion_iva": "Responsable Inscripto", "modalidad_comprobante": "Resumen + Factura", "emisor_fiscal_id_confirmado": 30}
            )
        return resultado, enviar, resolver

    def reconciliar(self, intento_id):
        consulta = Mock(return_value=consulta_autorizada())
        servicio = ReconciliacionArcaService(
            self.intentos, EmisorFiscalService, consulta, RecuperacionLocalArcaService(self.factory)
        )
        with patch.object(WSFEService, "fe_cae_solicitar") as solicitar:
            resultado = servicio.reconciliar_intento(intento_id)
        solicitar.assert_not_called()
        self.red.assert_not_called()
        return resultado, consulta

    def test_emision_h_a_y_c_usa_hija_h_y_congela_su_pv(self):
        self.config(H, pv=5)
        self.config(P, pv=9)
        for tipo in ("Factura A", "Factura C"):
            with self.subTest(tipo=tipo):
                _resultado, enviar, resolver = self.emitir(tipo=tipo)
                resolver.assert_called_once_with(30, H)
                enviar.assert_called_once()
                datos = enviar.call_args.kwargs
                self.assertEqual((datos["ruta_certificado"], datos["ruta_clave"], datos["punto_venta"],
                                  datos["carpeta_trabajo"]), (H + ".crt", H + ".key", 5, "C:/" + H))
                ctx = datos["contexto_fiscal_base"]
                self.assertEqual(ctx["ambiente"], H)
                self.assertEqual(ctx["version"], 1)
                self.assertEqual(ctx["emisor"]["punto_venta_num"], 5)
                self.assertEqual(ctx["comprobante"]["punto_venta_num"], 5)
                self.red.assert_not_called()

    def test_emision_sin_hija_exacta_no_usa_otro_ambiente_ni_legacy(self):
        for hay_p in (False, True):
            with self.subTest(hay_p=hay_p):
                if hay_p:
                    self.config(P)
                resultado, enviar, _resolver = self.emitir()
                self.assertEqual(resultado["etapa"], "configuracion_arca")
                enviar.assert_not_called()
                self.red.assert_not_called()

    def test_emision_p_bloqueada_antes_de_resolver_credenciales_o_enviar(self):
        self.config(P)
        resultado, enviar, resolver = self.emitir(P)
        self.assertFalse(resultado["ok"])
        resolver.assert_not_called()
        enviar.assert_not_called()
        self.assertEqual(self.sql("SELECT COUNT(*) FROM intentos_emision_arca"), [(0,)])

    def llamada_homologacion(self, ctx, pv=5):
        with ExitStack() as pila:
            mocks = [pila.enter_context(patch.object(clase, metodo)) for clase, metodo in (
                (WSAAService, "guardar_tra"), (WSAALoginService, "login_homologacion"),
                (WSFEService, "fe_comp_ultimo_autorizado"), (WSFEService, "fe_cae_solicitar"),
            )]
            mocks[1].return_value = {"ok": False, "errores": ["Frontera de prueba"]}
            resultado = HomologacionService.emitir_comprobante_prueba(
                ruta_certificado=H + ".crt", ruta_clave=H + ".key", cuit_emisor="20206871629",
                punto_venta=pv, tipo_comprobante=11, condicion_iva_receptor_id=5, concepto=1,
                tipo_documento=80, documento_receptor=30712345678, importe_total=100,
                importe_neto=100, importe_iva=0, importe_exento=0, fecha_comprobante="20260817",
                carpeta_trabajo="C:/H", contexto_fiscal_base=ctx, exigir_contexto_fiscal=True,
                datos_intento={"emisor_fiscal_id": 30}, ambiente=H,
            )
        return resultado, mocks

    def test_pv_y_emisor_contradictorios_bloquean_antes_de_tra_wsaa_wsfe(self):
        for campo in ("emisor_pv", "comprobante_pv", "emisor_id"):
            with self.subTest(campo=campo):
                ctx = contexto(H)
                if campo == "emisor_pv":
                    ctx["emisor"]["punto_venta_num"] = 9
                elif campo == "comprobante_pv":
                    ctx["comprobante"]["punto_venta_num"] = 9
                else:
                    ctx["emisor"]["emisor_fiscal_id"] = 99
                resultado, mocks = self.llamada_homologacion(ctx)
                self.assertFalse(resultado["ok"])
                for mock in mocks:
                    mock.assert_not_called()
                self.red.assert_not_called()

    def test_contexto_coherente_alcanza_frontera_wsaa(self):
        _resultado, mocks = self.llamada_homologacion(contexto(H))
        mocks[0].assert_called_once()
        mocks[1].assert_called_once()
        mocks[2].assert_not_called()
        mocks[3].assert_not_called()

    def test_reconciliacion_h_y_p_usa_configuracion_congelada_y_no_legacy(self):
        self.config(H)
        self.config(P)
        for ambiente, resumen_id in ((H, 10), (P, 11)):
            with self.subTest(ambiente=ambiente):
                self.sql("UPDATE emisores_fiscales SET ambiente_arca=?, punto_venta='999'",
                         ("Producción" if ambiente == H else "Homologación",))
                intento_id = self.crear(ambiente, resumen_id=resumen_id)
                resultado, consulta = self.reconciliar(intento_id)
                self.assertTrue(resultado.ok, resultado.errores)
                consulta.assert_called_once()
                datos = consulta.call_args.kwargs
                self.assertEqual((datos["ambiente"], datos["ruta_certificado"], datos["ruta_clave"],
                                  datos["punto_venta"]), (ambiente, ambiente + ".crt", ambiente + ".key", 5))

    def test_reconciliacion_config_ausente_o_solo_opuesta_no_consulta(self):
        for ambiente in (H, P):
            for solo_opuesta in (False, True):
                with self.subTest(ambiente=ambiente, solo_opuesta=solo_opuesta):
                    self.sql("DELETE FROM intentos_emision_arca")
                    self.sql("DELETE FROM emisor_fiscal_arca_config")
                    if solo_opuesta:
                        self.config(P if ambiente == H else H)
                    resultado, consulta = self.reconciliar(self.crear(ambiente))
                    self.assertEqual(resultado.resultado, ResultadoReconciliacion.CONSULTA_INCIERTA)
                    consulta.assert_not_called()

    def test_pv_hija_distinto_no_reemplaza_pv_congelado(self):
        self.config(H, pv=9)
        intento_id = self.crear(H)
        antes = self.intentos.obtener(intento_id).contexto_fiscal_json
        resultado, consulta = self.reconciliar(intento_id)
        self.assertEqual(resultado.resultado, ResultadoReconciliacion.CONSULTA_INCIERTA)
        consulta.assert_not_called()
        self.assertEqual(self.intentos.obtener(intento_id).contexto_fiscal_json, antes)

    def test_emisor_escalar_contradictorio_no_consulta_con_configuracion_de_otro(self):
        self.config(H)
        intento_id = self.crear(H)
        self.sql("UPDATE intentos_emision_arca SET emisor_fiscal_id=99 WHERE id=?", (intento_id,))
        resultado, consulta = self.reconciliar(intento_id)
        self.assertFalse(resultado.ok)
        consulta.assert_not_called()

    def test_contexto_ausente_o_corrupto_no_resuelve_configuracion(self):
        for corrupto in (False, True):
            with self.subTest(corrupto=corrupto):
                self.sql("DELETE FROM intentos_emision_arca")
                intento_id = self.crear(H)
                self.sql("UPDATE intentos_emision_arca SET contexto_fiscal_json=? WHERE id=?",
                         ("{mal" if corrupto else None, intento_id))
                with patch.object(EmisorFiscalService, "obtener_configuracion_arca") as resolver:
                    resultado, consulta = self.reconciliar(intento_id)
                self.assertEqual(resultado.resultado, ResultadoReconciliacion.CONSULTA_INCIERTA)
                resolver.assert_not_called()
                consulta.assert_not_called()

    def test_reconciliado_terminal_valido_no_necesita_config_actual_ni_red(self):
        intento_id, _factura_id = self.reconciliado(H, H)
        with patch.object(EmisorFiscalService, "obtener_configuracion_arca") as resolver:
            resultado, consulta = self.reconciliar(intento_id)
        self.assertTrue(resultado.ok)
        resolver.assert_not_called()
        consulta.assert_not_called()

    def test_configuracion_incoherente_de_provider_falla_cerrado(self):
        self.config(H)
        config = EmisorFiscalService.obtener_configuracion_arca(30, H)
        for config_alterada in (replace(config, ambiente_arca=P), replace(config, emisor_fiscal_id=99)):
            with self.subTest(configuracion=config_alterada):
                self.sql("DELETE FROM intentos_emision_arca")
                intento_id = self.crear(H)
                with patch.object(EmisorFiscalService, "obtener_configuracion_arca", return_value=config_alterada):
                    resultado, consulta = self.reconciliar(intento_id)
                self.assertFalse(resultado.ok)
                consulta.assert_not_called()
