"""Pruebas simuladas y nativas separadas; solo archivos de control temporales."""

import ctypes
import importlib.util
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest
from contextlib import ExitStack
from ctypes import wintypes
from pathlib import Path
from unittest.mock import Mock, patch


_ARCHIVO = Path(__file__).resolve()
_FUENTE = _ARCHIVO.parents[1] / "services" / "bloqueo_instancia_windows.py"
_PLAZO = 20


def _guardias():
    pila = ExitStack()
    denegado = AssertionError("SQLite y red prohibidos en pruebas de bloqueo.")
    for nombre in (
        "sqlite3.connect", "sqlite3.dbapi2.connect",
        "socket.socket.connect", "socket.create_connection",
    ):
        pila.enter_context(patch(nombre, side_effect=denegado))
    pila.enter_context(patch.dict(sys.modules, {
        "main": None, "database": None, "runtime_paths": None,
        "services.backup_service": None,
    }))
    return pila


with _guardias():
    _spec = importlib.util.spec_from_file_location("_bloqueo_3d4c5b", _FUENTE)
    bloqueo = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(bloqueo)


class _Base(unittest.TestCase):
    def setUp(self):
        self.pila = ExitStack()
        self.addCleanup(self.pila.close)
        self.pila.enter_context(_guardias())
        self.raiz = Path(self.pila.enter_context(
            tempfile.TemporaryDirectory(prefix="fm_bloqueo_3d4c5b_")
        )).resolve()

    def comprobar_error_publico(self, error):
        texto = " ".join((str(error), repr(error), repr(error.args), *error.__notes__)) \
            if hasattr(error, "__notes__") else str(error) + repr(error)
        self.assertNotIn(str(self.raiz), texto)
        self.assertNotIn("secreto", texto)
        self.assertNotIn(bloqueo.NOMBRE_ARCHIVO_BLOQUEO, texto)


class BloqueoSimuladoTests(_Base):
    """No se llama a kernel32: errores, firmas ABI y ciclo de recursos con dobles."""

    def setUp(self):
        super().setUp()
        self.dll = Mock()
        self.dll.CreateFileW.return_value = 0x1234567887654321
        self.dll.LockFileEx.return_value = 1
        self.dll.UnlockFileEx.return_value = 1
        self.dll.CloseHandle.return_value = 1
        self.cargar = self.pila.enter_context(patch.object(
            ctypes, "WinDLL", return_value=self.dll, create=True,
        ))
        self.ultimo_error = self.pila.enter_context(patch.object(
            ctypes, "get_last_error", return_value=5, create=True,
        ))
        self.pila.enter_context(patch.object(bloqueo.os, "name", "nt"))

    def test_firmas_y_flags_sin_truncar_sin_heredar(self):
        with bloqueo.BloqueoInstanciaWindows(self.raiz) as recurso:
            handle = self.dll.CreateFileW.return_value
            self.assertEqual(recurso._handle, handle)
            self.cargar.assert_called_once_with("kernel32", use_last_error=True)
            self.dll.CreateFileW.assert_called_once_with(
                str(self.raiz / bloqueo.NOMBRE_ARCHIVO_BLOQUEO),
                0xC0000000, 3, None, 4, 0x80, None,
            )
            self.assertEqual(self.dll.CreateFileW.restype, wintypes.HANDLE)
            self.assertEqual(self.dll.CreateFileW.argtypes, (
                wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p,
                wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE,
            ))
            self.assertEqual(self.dll.LockFileEx.argtypes, (
                wintypes.HANDLE, wintypes.DWORD, wintypes.DWORD,
                wintypes.DWORD, wintypes.DWORD, ctypes.POINTER(bloqueo._OVERLAPPED),
            ))
            self.assertEqual(self.dll.UnlockFileEx.argtypes, (
                wintypes.HANDLE, wintypes.DWORD, wintypes.DWORD,
                wintypes.DWORD, ctypes.POINTER(bloqueo._OVERLAPPED),
            ))
            self.assertEqual(self.dll.CloseHandle.argtypes, (wintypes.HANDLE,))
            for nombre in ("LockFileEx", "UnlockFileEx", "CloseHandle"):
                self.assertEqual(getattr(self.dll, nombre).restype, wintypes.BOOL)
            self.assertEqual(self.dll.LockFileEx.call_args.args[:5], (handle, 3, 0, 1, 0))
            solapado = ctypes.cast(
                self.dll.LockFileEx.call_args.args[-1],
                ctypes.POINTER(bloqueo._OVERLAPPED),
            ).contents
            self.assertEqual(bytes(solapado), bytes(ctypes.sizeof(solapado)))
        self.assertEqual(
            [llamada[0] for llamada in self.dll.mock_calls],
            ["CreateFileW", "LockFileEx", "UnlockFileEx", "CloseHandle"],
        )
        self.assertEqual(self.dll.UnlockFileEx.call_args.args[:4], (handle, 0, 1, 0))
        self.dll.CloseHandle.assert_called_once_with(handle)
        self.assertIsNone(recurso._handle)

    def test_fallo_apertura_no_bloquea_ni_cierra_handle_invalido(self):
        for handle in (None, 0, bloqueo._INVALID_HANDLE_VALUE):
            with self.subTest(handle=handle):
                self.dll.reset_mock()
                self.dll.CreateFileW.return_value = handle
                with self.assertRaises(bloqueo.ErrorBloqueoInstancia) as fallo:
                    bloqueo.BloqueoInstanciaWindows(self.raiz).adquirir()
                self.assertEqual(fallo.exception.fase, "apertura")
                self.assertEqual(fallo.exception.codigo_win32, 5)
                self.assertNotIsInstance(fallo.exception, bloqueo.InstanciaEnUsoError)
                self.dll.LockFileEx.assert_not_called()
                self.dll.CloseHandle.assert_not_called()
                self.comprobar_error_publico(fallo.exception)

    def test_conflicto_se_distingue_de_otros_fallos(self):
        for codigo in (33, 5, 32, 6, 8, 997):
            with self.subTest(codigo=codigo):
                self.dll.reset_mock()
                self.dll.LockFileEx.return_value = 0
                self.ultimo_error.return_value = codigo
                recurso = bloqueo.BloqueoInstanciaWindows(self.raiz)
                with self.assertRaises(bloqueo.ErrorBloqueoInstancia) as fallo:
                    recurso.adquirir()
                self.assertEqual(
                    isinstance(fallo.exception, bloqueo.InstanciaEnUsoError), codigo == 33,
                )
                self.assertEqual(fallo.exception.codigo_win32, codigo)
                self.dll.UnlockFileEx.assert_not_called()
                self.dll.CloseHandle.assert_called_once()
                self.assertIsNone(recurso._handle)
                self.comprobar_error_publico(fallo.exception)

    def test_fallo_api_y_plataforma_no_se_interpretan_como_libre(self):
        self.cargar.side_effect = OSError("ruta secreto " + str(self.raiz))
        with self.assertRaises(bloqueo.ErrorBloqueoInstancia) as fallo:
            bloqueo.BloqueoInstanciaWindows(self.raiz).adquirir()
        self.assertEqual(fallo.exception.fase, "api")
        self.assertTrue(fallo.exception.__suppress_context__)
        self.comprobar_error_publico(fallo.exception)
        with patch.object(bloqueo.os, "name", "no_windows"):
            with self.assertRaises(bloqueo.ErrorBloqueoInstancia) as fallo:
                bloqueo._ApiWindows()
        self.assertEqual(fallo.exception.fase, "plataforma")
        self.dll.CreateFileW.assert_not_called()

    def test_directorio_invalido_no_abre_archivos(self):
        for directorio in (None, "", "relativo secreto", str(self.raiz) + "\0secreto"):
            with self.subTest(directorio=directorio):
                with self.assertRaises(bloqueo.ErrorBloqueoInstancia) as fallo:
                    bloqueo.BloqueoInstanciaWindows(directorio)
                self.assertEqual(fallo.exception.fase, "directorio")
                self.comprobar_error_publico(fallo.exception)
        self.dll.CreateFileW.assert_not_called()

    def test_excepcion_e_interrupciones_del_contexto_se_preservan(self):
        for error in (ValueError("cuerpo"), KeyboardInterrupt(), SystemExit(7)):
            with self.subTest(tipo=type(error).__name__):
                self.dll.reset_mock()
                with self.assertRaises(type(error)) as fallo:
                    with bloqueo.BloqueoInstanciaWindows(self.raiz):
                        raise error
                self.assertIs(fallo.exception, error)
                self.dll.UnlockFileEx.assert_called_once()
                self.dll.CloseHandle.assert_called_once()

    def test_fallo_unlock_igualmente_cierra_y_se_informa(self):
        self.dll.UnlockFileEx.return_value = 0
        recurso = bloqueo.BloqueoInstanciaWindows(self.raiz)
        with self.assertRaises(bloqueo.ErrorBloqueoInstancia) as fallo:
            with recurso:
                pass
        self.assertEqual(fallo.exception.fase, "liberacion")
        self.assertIsNone(recurso._handle)
        self.dll.CloseHandle.assert_called_once()
        recurso.liberar()
        self.dll.CloseHandle.assert_called_once()

    def test_fallo_close_conserva_handle_y_permite_reintentar(self):
        recurso = bloqueo.BloqueoInstanciaWindows(self.raiz)
        recurso.adquirir()
        self.dll.CloseHandle.side_effect = (0, 1)
        with self.assertRaises(bloqueo.ErrorBloqueoInstancia) as fallo:
            recurso.liberar()
        self.assertEqual(fallo.exception.fase, "cierre")
        self.assertIsNotNone(recurso._handle)
        recurso.liberar()
        self.assertIsNone(recurso._handle)
        self.dll.UnlockFileEx.assert_called_once()
        self.assertEqual(self.dll.CloseHandle.call_count, 2)

    def test_fallo_doble_de_limpieza_no_oculta_error_del_cuerpo(self):
        error = RuntimeError("error original")
        recurso = bloqueo.BloqueoInstanciaWindows(self.raiz)
        self.dll.UnlockFileEx.return_value = 0
        self.dll.CloseHandle.return_value = 0
        with self.assertRaises(RuntimeError) as fallo:
            with recurso:
                raise error
        self.assertIs(fallo.exception, error)
        self.assertTrue(error.__notes__)
        self.assertIsNotNone(recurso._handle)
        self.dll.UnlockFileEx.return_value = 1
        self.dll.CloseHandle.return_value = 1
        recurso.liberar()
        self.assertIsNone(recurso._handle)

    def test_fallo_al_adquirir_y_al_cerrar_preserva_conflicto(self):
        self.dll.LockFileEx.return_value = 0
        self.ultimo_error.return_value = 33
        self.dll.CloseHandle.return_value = 0
        recurso = bloqueo.BloqueoInstanciaWindows(self.raiz)
        with self.assertRaises(bloqueo.InstanciaEnUsoError) as fallo:
            recurso.adquirir()
        self.assertTrue(fallo.exception.__notes__)
        self.assertIsNotNone(recurso._handle)
        self.comprobar_error_publico(fallo.exception)
        self.dll.CloseHandle.return_value = 1
        recurso.liberar()

    def test_interrupcion_en_adquisicion_cierra_handle(self):
        error = KeyboardInterrupt()
        self.dll.LockFileEx.side_effect = error
        with self.assertRaises(KeyboardInterrupt) as fallo:
            bloqueo.BloqueoInstanciaWindows(self.raiz).adquirir()
        self.assertIs(fallo.exception, error)
        self.dll.CloseHandle.assert_called_once()

    def test_no_reentrante_y_liberacion_idempotente(self):
        recurso = bloqueo.BloqueoInstanciaWindows(self.raiz)
        recurso.liberar()
        with recurso:
            with self.assertRaises(bloqueo.ErrorBloqueoInstancia):
                recurso.adquirir()
            self.dll.CreateFileW.assert_called_once()
        recurso.liberar()
        with recurso:
            pass
        self.assertEqual(self.dll.CreateFileW.call_count, 2)
        self.assertEqual(self.dll.CloseHandle.call_count, 2)


@unittest.skipUnless(os.name == "nt", "Pruebas nativas exclusivas de Windows")
class BloqueoNativoWindowsTests(_Base):
    """API Windows real, archivos temporales y procesos ficticios supervisados."""

    def intentar_en_otro_proceso(self, directorio):
        proceso = subprocess.run(
            [sys.executable, "-B", str(_ARCHIVO), "--intentar", str(directorio)],
            capture_output=True, text=True, timeout=_PLAZO, check=False,
        )
        self.assertEqual(proceso.returncode, 0, proceso.stdout + proceso.stderr)
        resultado = json.loads(proceso.stdout)
        self.assertNotEqual(resultado["pid"], os.getpid())
        return resultado["estado"]

    def test_segunda_instancia_rechazada_y_adquisicion_tras_liberar(self):
        with bloqueo.BloqueoInstanciaWindows(self.raiz):
            self.assertEqual(self.intentar_en_otro_proceso(self.raiz), "ocupada")
        self.assertEqual(self.intentar_en_otro_proceso(self.raiz), "adquirida")

    def test_archivo_preexistente_no_se_trunca_ni_se_elimina(self):
        archivo = self.raiz / bloqueo.NOMBRE_ARCHIVO_BLOQUEO
        contenido = b"control ficticio: conservar contenido\x00\xff"
        archivo.write_bytes(contenido)
        for _ in range(2):
            with bloqueo.BloqueoInstanciaWindows(self.raiz):
                pass
            self.assertEqual(archivo.read_bytes(), contenido)

    def test_crea_archivo_vacio_y_persiste(self):
        archivo = self.raiz / bloqueo.NOMBRE_ARCHIVO_BLOQUEO
        self.assertFalse(archivo.exists())
        with bloqueo.BloqueoInstanciaWindows(self.raiz):
            self.assertTrue(archivo.is_file())
            with self.assertRaises(OSError):
                archivo.unlink()
        self.assertEqual(archivo.read_bytes(), b"")
        with bloqueo.BloqueoInstanciaWindows(self.raiz):
            pass

    def test_excepcion_libera_para_otro_proceso(self):
        error = ValueError("prueba ficticia")
        with self.assertRaises(ValueError) as fallo:
            with bloqueo.BloqueoInstanciaWindows(self.raiz):
                raise error
        self.assertIs(fallo.exception, error)
        self.assertEqual(self.intentar_en_otro_proceso(self.raiz), "adquirida")

    def test_directorios_distintos_son_instalaciones_independientes(self):
        otra = self.raiz / "otra instalacion"
        otra.mkdir()
        with bloqueo.BloqueoInstanciaWindows(self.raiz):
            self.assertEqual(self.intentar_en_otro_proceso(otra), "adquirida")

    def test_ruta_con_espacios_y_unicode(self):
        directorio = self.raiz / "Instalaci\u00f3n ficticia \u6d4b\u8bd5 con espacios"
        directorio.mkdir()
        with bloqueo.BloqueoInstanciaWindows(directorio):
            self.assertEqual(self.intentar_en_otro_proceso(directorio), "ocupada")
        self.assertEqual(self.intentar_en_otro_proceso(directorio), "adquirida")

    def test_permiso_denegado_real_por_archivo_solo_lectura(self):
        archivo = self.raiz / bloqueo.NOMBRE_ARCHIVO_BLOQUEO
        archivo.write_bytes(b"ficticio")
        archivo.chmod(0o444)
        try:
            with self.assertRaises(bloqueo.ErrorBloqueoInstancia) as fallo:
                bloqueo.BloqueoInstanciaWindows(self.raiz).adquirir()
            self.assertEqual(fallo.exception.fase, "apertura")
            self.assertEqual(fallo.exception.codigo_win32, 5)
            self.assertNotIsInstance(fallo.exception, bloqueo.InstanciaEnUsoError)
            self.comprobar_error_publico(fallo.exception)
        finally:
            archivo.chmod(0o666)

    def test_directorio_ausente_no_se_crea_y_error_no_revela_ruta(self):
        directorio = self.raiz / "secreto ausente"
        with self.assertRaises(bloqueo.ErrorBloqueoInstancia) as fallo:
            bloqueo.BloqueoInstanciaWindows(directorio).adquirir()
        self.assertEqual(fallo.exception.fase, "apertura")
        self.assertFalse(directorio.exists())
        self.comprobar_error_publico(fallo.exception)

    def test_handle_no_heredable_y_estructura_abi(self):
        dll = ctypes.WinDLL("kernel32", use_last_error=True)
        dll.GetHandleInformation.argtypes = (wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD))
        dll.GetHandleInformation.restype = wintypes.BOOL
        bits = ctypes.sizeof(ctypes.c_void_p) * 8
        self.assertEqual(ctypes.sizeof(bloqueo._OVERLAPPED), 32 if bits == 64 else 20)
        self.assertEqual(bloqueo._OVERLAPPED.hEvent.offset, 24 if bits == 64 else 16)
        with bloqueo.BloqueoInstanciaWindows(self.raiz) as recurso:
            flags = wintypes.DWORD()
            self.assertTrue(dll.GetHandleInformation(recurso._handle, ctypes.byref(flags)))
            self.assertEqual(flags.value & 1, 0)

    def test_sin_fugas_en_exito_y_conflictos(self):
        dll = ctypes.WinDLL("kernel32", use_last_error=True)
        dll.GetCurrentProcess.argtypes = ()
        dll.GetCurrentProcess.restype = wintypes.HANDLE
        dll.GetProcessHandleCount.argtypes = (wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD))
        dll.GetProcessHandleCount.restype = wintypes.BOOL

        def contar():
            cuenta = wintypes.DWORD()
            self.assertTrue(dll.GetProcessHandleCount(dll.GetCurrentProcess(), ctypes.byref(cuenta)))
            return cuenta.value

        with bloqueo.BloqueoInstanciaWindows(self.raiz):
            pass
        inicial = contar()
        for _ in range(100):
            with bloqueo.BloqueoInstanciaWindows(self.raiz):
                with self.assertRaises(bloqueo.InstanciaEnUsoError):
                    with bloqueo.BloqueoInstanciaWindows(self.raiz):
                        self.fail("Se concedieron dos bloqueos.")
        self.assertEqual(contar(), inicial)

    def test_terminacion_forzada_libera_bloqueo(self):
        with subprocess.Popen(
            [sys.executable, "-B", str(_ARCHIVO), "--mantener", str(self.raiz)],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        ) as proceso:
            try:
                limite = time.monotonic() + _PLAZO
                while not (self.raiz / "listo.txt").exists():
                    self.assertIsNone(proceso.poll(), "El hijo termino antes de adquirir.")
                    self.assertLess(time.monotonic(), limite, "El hijo no respondio.")
                    time.sleep(0.02)
                self.assertEqual(self.intentar_en_otro_proceso(self.raiz), "ocupada")
                proceso.kill()
                proceso.communicate(timeout=_PLAZO)
                self.assertIsNotNone(proceso.poll())
                # Windows puede demorar la liberacion tras terminar el proceso.
                limite = time.monotonic() + 5
                while True:
                    try:
                        with bloqueo.BloqueoInstanciaWindows(self.raiz):
                            break
                    except bloqueo.InstanciaEnUsoError:
                        self.assertLess(time.monotonic(), limite, "No se libero el bloqueo.")
                        time.sleep(0.02)
            finally:
                if proceso.poll() is None:
                    proceso.kill()
                proceso.communicate(timeout=_PLAZO)


def _hijo(modo, directorio):
    with _guardias():
        try:
            with bloqueo.BloqueoInstanciaWindows(directorio):
                if modo == "--mantener":
                    (directorio / "listo.txt").write_text("listo", encoding="ascii")
                    sys.stdin.read(1)
                estado = "adquirida"
        except bloqueo.InstanciaEnUsoError:
            estado = "ocupada"
    print(json.dumps({"estado": estado, "pid": os.getpid()}), flush=True)


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] in ("--intentar", "--mantener"):
        _hijo(sys.argv[1], Path(sys.argv[2]))
    else:
        unittest.main()
