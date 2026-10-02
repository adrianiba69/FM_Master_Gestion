"""Tests de POST-E2E 3B.3C: escritura/reemplazo atomico del PDF fiscal.

Modulo bajo prueba: services/arca/pdf_fiscal_service.py (PDFFiscalService.generar_factura_c).
Usa filesystem real en TemporaryDirectory. CERO ARCA/WSAA/WSFE. CERO DB.
"""

import unittest
from os import utime as _os_utime
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from reportlab.pdfgen import canvas

from services.arca.pdf_fiscal_service import PDFFiscalService
from services.arca.snapshot_fiscal_pdf_adapter import construir_datos_pdf_desde_snapshot
from tests._cierre_contexto_helper import construir_snapshot_cierre_para_test
from views.facturas_electronicas import FacturasElectronicasFrame


def _datos_pdf(ambiente="HOMOLOGACION", tipo_comprobante_texto="Factura A"):
    resultado = construir_snapshot_cierre_para_test(
        ambiente=ambiente, tipo_comprobante_texto=tipo_comprobante_texto
    )
    return construir_datos_pdf_desde_snapshot(resultado["snapshot"])


def _snapshot_persistido(ambiente="HOMOLOGACION"):
    resultado = construir_snapshot_cierre_para_test(ambiente=ambiente)
    return resultado["snapshot_json"], resultado["snapshot_version"], resultado["snapshot_hash"]


class GeneracionInicialAtomicaTest(unittest.TestCase):
    """A. destino inexistente."""

    def test_destino_inexistente_genera_pdf_final_sin_temporales(self):
        datos = _datos_pdf()
        with TemporaryDirectory() as carpeta:
            destino = Path(carpeta) / "factura.pdf"
            resultado = PDFFiscalService.generar_factura_c(
                ruta_destino=str(destino),
                datos_emisor=datos["datos_emisor"],
                datos_receptor=datos["datos_receptor"],
                datos_comprobante=datos["datos_comprobante"],
            )

            self.assertTrue(resultado["ok"], resultado.get("errores"))
            self.assertEqual(resultado["ruta_pdf"], str(destino))
            self.assertTrue(destino.is_file())
            self.assertGreater(destino.stat().st_size, 0)

            archivos = list(Path(carpeta).iterdir())
            self.assertEqual(archivos, [destino])
            for archivo in archivos:
                self.assertFalse(archivo.name.endswith(".tmp"))


class ReemplazoAtomicoTest(unittest.TestCase):
    """B. destino existente con contenido conocido."""

    def test_generacion_exitosa_reemplaza_destino_sin_timestamp_ni_temporal(self):
        datos = _datos_pdf()
        with TemporaryDirectory() as carpeta:
            destino = Path(carpeta) / "factura.pdf"
            destino.write_bytes(b"%PDF-1.4 contenido viejo valido")

            resultado = PDFFiscalService.generar_factura_c(
                ruta_destino=str(destino),
                datos_emisor=datos["datos_emisor"],
                datos_receptor=datos["datos_receptor"],
                datos_comprobante=datos["datos_comprobante"],
            )

            self.assertTrue(resultado["ok"], resultado.get("errores"))
            self.assertEqual(resultado["ruta_pdf"], str(destino))

            archivos = sorted(p.name for p in Path(carpeta).iterdir())
            self.assertEqual(archivos, ["factura.pdf"])
            self.assertNotEqual(destino.read_bytes(), b"%PDF-1.4 contenido viejo valido")


class FalloDuranteGeneracionTest(unittest.TestCase):
    """C. fallo de canvas/save antes del replace."""

    def test_fallo_en_save_conserva_destino_original_y_limpia_temporal(self):
        datos = _datos_pdf()
        contenido_original = b"%PDF-1.4 contenido original intacto"
        with TemporaryDirectory() as carpeta:
            destino = Path(carpeta) / "factura.pdf"
            destino.write_bytes(contenido_original)

            with patch.object(canvas.Canvas, "save", side_effect=OSError("disco lleno")):
                resultado = PDFFiscalService.generar_factura_c(
                    ruta_destino=str(destino),
                    datos_emisor=datos["datos_emisor"],
                    datos_receptor=datos["datos_receptor"],
                    datos_comprobante=datos["datos_comprobante"],
                )

            self.assertFalse(resultado["ok"])
            self.assertEqual(destino.read_bytes(), contenido_original)
            archivos = sorted(p.name for p in Path(carpeta).iterdir())
            self.assertEqual(archivos, ["factura.pdf"])


class FalloDuranteReplaceTest(unittest.TestCase):
    """D. os.replace falla (archivo bloqueado en Windows)."""

    def test_permission_error_en_replace_conserva_destino_y_limpia_temporal(self):
        datos = _datos_pdf()
        contenido_original = b"%PDF-1.4 contenido original bloqueado"
        with TemporaryDirectory() as carpeta:
            destino = Path(carpeta) / "factura.pdf"
            destino.write_bytes(contenido_original)

            with patch("services.arca.pdf_fiscal_service.os.replace", side_effect=PermissionError("denegado")):
                resultado = PDFFiscalService.generar_factura_c(
                    ruta_destino=str(destino),
                    datos_emisor=datos["datos_emisor"],
                    datos_receptor=datos["datos_receptor"],
                    datos_comprobante=datos["datos_comprobante"],
                )

            self.assertFalse(resultado["ok"])
            self.assertEqual(resultado.get("tipo_error"), "archivo_bloqueado")
            self.assertEqual(destino.read_bytes(), contenido_original)
            archivos = sorted(p.name for p in Path(carpeta).iterdir())
            self.assertEqual(archivos, ["factura.pdf"])

    def test_oserror_winerror_32_en_replace_se_reconoce_como_bloqueo(self):
        datos = _datos_pdf()
        with TemporaryDirectory() as carpeta:
            destino = Path(carpeta) / "factura.pdf"
            destino.write_bytes(b"%PDF-1.4 original")

            error_bloqueo = OSError("The process cannot access the file because it is being used by another process")
            error_bloqueo.winerror = 32
            with patch("services.arca.pdf_fiscal_service.os.replace", side_effect=error_bloqueo):
                resultado = PDFFiscalService.generar_factura_c(
                    ruta_destino=str(destino),
                    datos_emisor=datos["datos_emisor"],
                    datos_receptor=datos["datos_receptor"],
                    datos_comprobante=datos["datos_comprobante"],
                )

            self.assertFalse(resultado["ok"])
            self.assertEqual(resultado.get("tipo_error"), "archivo_bloqueado")
            self.assertEqual(destino.read_bytes(), b"%PDF-1.4 original")

    def test_oserror_generico_en_replace_no_se_marca_como_bloqueo(self):
        datos = _datos_pdf()
        with TemporaryDirectory() as carpeta:
            destino = Path(carpeta) / "factura.pdf"
            destino.write_bytes(b"%PDF-1.4 original")

            with patch("services.arca.pdf_fiscal_service.os.replace", side_effect=OSError("disco desconectado")):
                resultado = PDFFiscalService.generar_factura_c(
                    ruta_destino=str(destino),
                    datos_emisor=datos["datos_emisor"],
                    datos_receptor=datos["datos_receptor"],
                    datos_comprobante=datos["datos_comprobante"],
                )

            self.assertFalse(resultado["ok"])
            self.assertNotIn("tipo_error", resultado)
            self.assertEqual(destino.read_bytes(), b"%PDF-1.4 original")


class DestinoNuevoConFalloTest(unittest.TestCase):
    """E. destino nuevo + fallo: no debe quedar archivo final parcial ni temporal."""

    def test_fallo_en_save_sin_destino_previo_no_deja_nada(self):
        datos = _datos_pdf()
        with TemporaryDirectory() as carpeta:
            destino = Path(carpeta) / "factura_nueva.pdf"

            with patch.object(canvas.Canvas, "save", side_effect=OSError("disco lleno")):
                resultado = PDFFiscalService.generar_factura_c(
                    ruta_destino=str(destino),
                    datos_emisor=datos["datos_emisor"],
                    datos_receptor=datos["datos_receptor"],
                    datos_comprobante=datos["datos_comprobante"],
                )

            self.assertFalse(resultado["ok"])
            self.assertFalse(destino.exists())
            self.assertEqual(list(Path(carpeta).iterdir()), [])

    def test_fallo_en_replace_sin_destino_previo_no_deja_nada(self):
        datos = _datos_pdf()
        with TemporaryDirectory() as carpeta:
            destino = Path(carpeta) / "factura_nueva.pdf"

            with patch("services.arca.pdf_fiscal_service.os.replace", side_effect=PermissionError("denegado")):
                resultado = PDFFiscalService.generar_factura_c(
                    ruta_destino=str(destino),
                    datos_emisor=datos["datos_emisor"],
                    datos_receptor=datos["datos_receptor"],
                    datos_comprobante=datos["datos_comprobante"],
                )

            self.assertFalse(resultado["ok"])
            self.assertFalse(destino.exists())
            self.assertEqual(list(Path(carpeta).iterdir()), [])


class FacturaAyCComparteEscritorTest(unittest.TestCase):
    """I. Factura A y C usan el mismo escritor atomico."""

    def test_factura_a_y_c_generan_correctamente_con_el_mismo_metodo(self):
        with TemporaryDirectory() as carpeta:
            for tipo in ("Factura A", "Factura C"):
                datos = _datos_pdf(tipo_comprobante_texto=tipo)
                destino = Path(carpeta) / f"{tipo.replace(' ', '_')}.pdf"
                resultado = PDFFiscalService.generar_factura_c(
                    ruta_destino=str(destino),
                    datos_emisor=datos["datos_emisor"],
                    datos_receptor=datos["datos_receptor"],
                    datos_comprobante=datos["datos_comprobante"],
                )
                self.assertTrue(resultado["ok"], resultado.get("errores"))
                self.assertTrue(destino.is_file())


class AmbienteHomologacionProduccionIndependienteTest(unittest.TestCase):
    """K. La atomicidad no mezcla ni altera el bucket H/P resuelto por 3B.3B."""

    def test_generar_en_dos_destinos_distintos_no_se_mezclan(self):
        with TemporaryDirectory() as carpeta:
            destino_h = Path(carpeta) / "Homologacion" / "facturas" / "factura.pdf"
            destino_p = Path(carpeta) / "Produccion" / "facturas" / "factura.pdf"

            datos_h = _datos_pdf(ambiente="HOMOLOGACION")
            datos_p = _datos_pdf(ambiente="PRODUCCION")

            resultado_h = PDFFiscalService.generar_factura_c(
                ruta_destino=str(destino_h),
                datos_emisor=datos_h["datos_emisor"],
                datos_receptor=datos_h["datos_receptor"],
                datos_comprobante=datos_h["datos_comprobante"],
            )
            resultado_p = PDFFiscalService.generar_factura_c(
                ruta_destino=str(destino_p),
                datos_emisor=datos_p["datos_emisor"],
                datos_receptor=datos_p["datos_receptor"],
                datos_comprobante=datos_p["datos_comprobante"],
            )

            self.assertTrue(resultado_h["ok"])
            self.assertTrue(resultado_p["ok"])
            self.assertEqual(resultado_h["ruta_pdf"], str(destino_h))
            self.assertEqual(resultado_p["ruta_pdf"], str(destino_p))
            self.assertTrue(destino_h.is_file())
            self.assertTrue(destino_p.is_file())


class ContratoRetornoRegeneracionVistaTest(unittest.TestCase):
    """F/G. Todas las ramas de _regenerar_pdf_fiscal_factura devuelven 3 elementos
    (ruta_pdf, regenerado, advertencia_persistencia); archivo bloqueado propaga
    PermissionError para que la UI muestre "cerralo e intentá nuevamente"."""

    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.carpeta_facturas = self._tmp.name
        self.ruta_estandar = str(Path(self.carpeta_facturas) / "Homologacion" / "facturas" / "x.pdf")

    def _frame(self):
        return object.__new__(FacturasElectronicasFrame)

    def _factura(self):
        json_texto, version, hash_texto = _snapshot_persistido("HOMOLOGACION")
        return {
            "factura_id": 99,
            "snapshot_fiscal_json": json_texto,
            "snapshot_version": version,
            "snapshot_hash": hash_texto,
            "ruta_pdf_relativa": None,
            "ruta_pdf_absoluta": None,
        }

    # F.19-20 (rama 1): no requiere regenerar -> 3 elementos, sin tocar filesystem.
    def test_no_requiere_regenerar_retorna_3_tupla(self):
        Path(self.ruta_estandar).parent.mkdir(parents=True, exist_ok=True)
        Path(self.ruta_estandar).write_bytes(
            b"%PDF importe neto gravado IVA importe total"
        )
        frame = self._frame()

        resultado = frame._regenerar_pdf_fiscal_factura(
            factura=self._factura(),
            valores_fila=(),
            emisor_fiscal=(),
            carpeta_facturas=self.carpeta_facturas,
            ruta_pdf_estandar=self.ruta_estandar,
            ruta_pdf_resuelta=self.ruta_estandar,
            cliente_id=10,
            tipo_factura="Factura A",
            codigo_factura="00002-00000010",
            forzar_regeneracion=False,
            forzar_reemplazo_estandar=True,
        )

        self.assertEqual(len(resultado), 3)
        ruta, regenerado, advertencia = resultado
        self.assertFalse(regenerado)
        self.assertIsNone(advertencia)
        self.assertEqual(str(ruta), self.ruta_estandar)

    # F.19-20 (rama 2): datos_pdf falsy (legacy sin resumen) -> 3 elementos.
    def test_datos_pdf_falsy_retorna_3_tupla(self):
        frame = self._frame()
        factura = self._factura()

        with patch.object(frame, "_construir_datos_pdf_para_regeneracion", return_value=None):
            resultado = frame._regenerar_pdf_fiscal_factura(
                factura=factura,
                valores_fila=(),
                emisor_fiscal=(),
                carpeta_facturas=self.carpeta_facturas,
                ruta_pdf_estandar=self.ruta_estandar,
                ruta_pdf_resuelta=self.ruta_estandar,
                cliente_id=10,
                tipo_factura="Factura A",
                codigo_factura="00002-00000010",
                forzar_regeneracion=True,
                forzar_reemplazo_estandar=True,
            )

        self.assertEqual(len(resultado), 3)
        ruta, regenerado, advertencia = resultado
        self.assertFalse(regenerado)
        self.assertIsNone(advertencia)

    # F.19-20 (rama 3): fallo controlado de generar_factura_c (no bloqueo) -> 3 elementos.
    def test_fallo_controlado_de_generacion_retorna_3_tupla(self):
        frame = self._frame()
        factura = self._factura()

        with (
            patch.object(
                frame, "_construir_datos_pdf_para_regeneracion",
                return_value={"datos_emisor": {}, "datos_receptor": {}, "datos_comprobante": {}},
            ),
            patch(
                "views.facturas_electronicas.PDFFiscalService.generar_factura_c",
                return_value={"ok": False, "errores": ["disco lleno"]},
            ),
        ):
            resultado = frame._regenerar_pdf_fiscal_factura(
                factura=factura,
                valores_fila=(),
                emisor_fiscal=(),
                carpeta_facturas=self.carpeta_facturas,
                ruta_pdf_estandar=self.ruta_estandar,
                ruta_pdf_resuelta=self.ruta_estandar,
                cliente_id=10,
                tipo_factura="Factura A",
                codigo_factura="00002-00000010",
                forzar_regeneracion=True,
                forzar_reemplazo_estandar=True,
            )

        self.assertEqual(len(resultado), 3)
        ruta, regenerado, advertencia = resultado
        self.assertFalse(regenerado)
        self.assertIsNone(advertencia)

    # G.21-22: archivo bloqueado -> PermissionError (para que la UI muestre "cerralo e intentá nuevamente").
    def test_archivo_bloqueado_en_generar_factura_c_levanta_permission_error(self):
        frame = self._frame()
        factura = self._factura()

        with (
            patch.object(
                frame, "_construir_datos_pdf_para_regeneracion",
                return_value={"datos_emisor": {}, "datos_receptor": {}, "datos_comprobante": {}},
            ),
            patch(
                "views.facturas_electronicas.PDFFiscalService.generar_factura_c",
                return_value={
                    "ok": False,
                    "errores": ["No se pudo reemplazar el PDF fiscal destino: denegado"],
                    "tipo_error": "archivo_bloqueado",
                },
            ),
        ):
            with self.assertRaises(PermissionError):
                frame._regenerar_pdf_fiscal_factura(
                    factura=factura,
                    valores_fila=(),
                    emisor_fiscal=(),
                    carpeta_facturas=self.carpeta_facturas,
                    ruta_pdf_estandar=self.ruta_estandar,
                    ruta_pdf_resuelta=self.ruta_estandar,
                    cliente_id=10,
                    tipo_factura="Factura A",
                    codigo_factura="00002-00000010",
                    forzar_regeneracion=True,
                    forzar_reemplazo_estandar=True,
                )

    # H.23: reemplazo fallido (fallo controlado) NO modifica ruta_pdf_relativa/absoluta.
    def test_fallo_de_generacion_no_modifica_rutas_persistidas(self):
        frame = self._frame()
        factura = self._factura()
        factura["ruta_pdf_relativa"] = r"Homologacion\facturas\anterior.pdf"
        factura["ruta_pdf_absoluta"] = str(Path(self.carpeta_facturas) / "Homologacion" / "facturas" / "anterior.pdf")

        with (
            patch.object(
                frame, "_construir_datos_pdf_para_regeneracion",
                return_value={"datos_emisor": {}, "datos_receptor": {}, "datos_comprobante": {}},
            ),
            patch(
                "views.facturas_electronicas.PDFFiscalService.generar_factura_c",
                return_value={"ok": False, "errores": ["disco lleno"]},
            ),
            patch("views.facturas_electronicas.FacturaArcaService.actualizar_ruta_pdf") as actualizar,
        ):
            frame._regenerar_pdf_fiscal_factura(
                factura=factura,
                valores_fila=(),
                emisor_fiscal=(),
                carpeta_facturas=self.carpeta_facturas,
                ruta_pdf_estandar=self.ruta_estandar,
                ruta_pdf_resuelta=self.ruta_estandar,
                cliente_id=10,
                tipo_factura="Factura A",
                codigo_factura="00002-00000010",
                forzar_regeneracion=True,
                forzar_reemplazo_estandar=True,
            )

        actualizar.assert_not_called()
        self.assertEqual(factura["ruta_pdf_relativa"], r"Homologacion\facturas\anterior.pdf")


class StMtimeHeuristicaRegeneracionTest(unittest.TestCase):
    """st_mtime solo decide si conviene regenerar; jamás selecciona identidad
    documental entre candidatos (eso ya lo resuelve 3B.3B antes de llegar aquí)."""

    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.carpeta_facturas = self._tmp.name

    def _frame(self):
        return object.__new__(FacturasElectronicasFrame)

    def _factura(self):
        json_texto, version, hash_texto = _snapshot_persistido("HOMOLOGACION")
        return {
            "factura_id": 99,
            "snapshot_fiscal_json": json_texto,
            "snapshot_version": version,
            "snapshot_hash": hash_texto,
            "ruta_pdf_relativa": None,
            "ruta_pdf_absoluta": None,
        }

    def test_resuelta_mas_nueva_que_estandar_dispara_regeneracion(self):
        carpeta = Path(self.carpeta_facturas)
        ruta_estandar = carpeta / "estandar.pdf"
        ruta_resuelta = carpeta / "resuelta.pdf"
        contenido_valido = b"%PDF importe neto gravado IVA importe total"
        ruta_estandar.write_bytes(contenido_valido)
        ruta_resuelta.write_bytes(contenido_valido)

        ahora = ruta_estandar.stat().st_mtime
        _os_utime(str(ruta_estandar), (ahora - 100, ahora - 100))
        _os_utime(str(ruta_resuelta), (ahora + 100, ahora + 100))

        frame = self._frame()
        with patch.object(frame, "_construir_datos_pdf_para_regeneracion", return_value=None) as mock_datos:
            frame._regenerar_pdf_fiscal_factura(
                factura=self._factura(),
                valores_fila=(),
                emisor_fiscal=(),
                carpeta_facturas=self.carpeta_facturas,
                ruta_pdf_estandar=str(ruta_estandar),
                ruta_pdf_resuelta=str(ruta_resuelta),
                cliente_id=10,
                tipo_factura="Factura A",
                codigo_factura="00002-00000010",
                forzar_regeneracion=False,
                forzar_reemplazo_estandar=True,
            )
        # Si decidio regenerar, debio intentar construir los datos del PDF.
        mock_datos.assert_called_once()

    def test_resuelta_no_mas_nueva_no_dispara_regeneracion(self):
        carpeta = Path(self.carpeta_facturas)
        ruta_estandar = carpeta / "estandar.pdf"
        ruta_resuelta = carpeta / "resuelta.pdf"
        contenido_valido = b"%PDF importe neto gravado IVA importe total"
        ruta_estandar.write_bytes(contenido_valido)
        ruta_resuelta.write_bytes(contenido_valido)

        ahora = ruta_estandar.stat().st_mtime
        _os_utime(str(ruta_estandar), (ahora, ahora))
        _os_utime(str(ruta_resuelta), (ahora - 100, ahora - 100))

        frame = self._frame()
        with patch.object(frame, "_construir_datos_pdf_para_regeneracion") as mock_datos:
            resultado = frame._regenerar_pdf_fiscal_factura(
                factura=self._factura(),
                valores_fila=(),
                emisor_fiscal=(),
                carpeta_facturas=self.carpeta_facturas,
                ruta_pdf_estandar=str(ruta_estandar),
                ruta_pdf_resuelta=str(ruta_resuelta),
                cliente_id=10,
                tipo_factura="Factura A",
                codigo_factura="00002-00000010",
                forzar_regeneracion=False,
                forzar_reemplazo_estandar=True,
            )
        mock_datos.assert_not_called()
        self.assertEqual(resultado, (ruta_estandar, False, None))


class LegacyPdfTimestampedLocalizableTest(unittest.TestCase):
    """J. Un PDF historico con sufijo timestamp (legado pre-3B.3C) sigue siendo
    localizable por la busqueda historica de 3B.3B; no se generan nuevos timestamp."""

    def test_pdf_timestamped_historico_es_encontrado_por_busqueda_compatible(self):
        with TemporaryDirectory() as carpeta:
            archivo_legacy = Path(carpeta) / "Cliente_Factura_A_00002-00000010_20260101_101500.pdf"
            archivo_legacy.write_bytes(b"%PDF legado")

            with patch("views.facturas_electronicas.nombre_cliente_archivo", return_value="Cliente"):
                candidatos = FacturasElectronicasFrame._buscar_pdf_historico_compatible(
                    carpeta_facturas=carpeta,
                    cliente_id=10,
                    tipo_factura="Factura A",
                    codigo_factura="00002-00000010",
                )

            self.assertEqual(candidatos, [archivo_legacy])


if __name__ == "__main__":
    unittest.main()
