"""Bloqueo cooperativo por instalacion, sin dependencias del arranque ni de SQLite.

El llamador indica un directorio absoluto, existente y de confianza, compartido
por todas las instancias de esa instalacion (no cwd ni el temporal del bundle).
Se conserva el archivo ``.fm_master.instancia.lock``; su existencia no significa
que haya una instancia activa. No se escribe ni se trunca su contenido.

Usar con ``with BloqueoInstanciaWindows(directorio):`` durante toda la ejecucion,
o llamar a adquirir()/liberar() explicitamente. No depender del recolector.
Si CloseHandle falla, se informa el error y se conserva el handle para reintentar
liberar() sobre el mismo objeto; no se debe continuar como si se hubiera cerrado.
No es reentrante ni esta pensado para compartir un objeto entre hilos.
"""

import ctypes
import os
from ctypes import wintypes
from pathlib import Path
from types import TracebackType


NOMBRE_ARCHIVO_BLOQUEO = ".fm_master.instancia.lock"
_INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value
_ERROR_LOCK_VIOLATION = 33


class ErrorBloqueoInstancia(RuntimeError):
    """Error publico sanitizado; fase y codigo numerico sirven para diagnostico."""

    def __init__(self, fase: str, codigo_win32: int | None = None):
        super().__init__("No se pudo gestionar el bloqueo de la aplicacion.")
        self.fase = fase
        self.codigo_win32 = codigo_win32


class InstanciaEnUsoError(ErrorBloqueoInstancia):
    def __init__(self):
        super().__init__("adquisicion", _ERROR_LOCK_VIOLATION)
        self.args = ("Ya hay otra instancia de la aplicacion en uso.",)


class _Offsets(ctypes.Structure):
    _fields_ = [("Offset", wintypes.DWORD), ("OffsetHigh", wintypes.DWORD)]


class _Posicion(ctypes.Union):
    _fields_ = [("offsets", _Offsets), ("Pointer", ctypes.c_void_p)]


class _OVERLAPPED(ctypes.Structure):
    _fields_ = [
        ("Internal", ctypes.c_size_t),
        ("InternalHigh", ctypes.c_size_t),
        ("posicion", _Posicion),
        ("hEvent", wintypes.HANDLE),
    ]


class _ApiWindows:
    def __init__(self):
        if os.name != "nt":
            raise ErrorBloqueoInstancia("plataforma")
        try:
            self.dll = ctypes.WinDLL("kernel32", use_last_error=True)
            self.dll.CreateFileW.argtypes = (
                wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p,
                wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE,
            )
            self.dll.CreateFileW.restype = wintypes.HANDLE
            self.dll.LockFileEx.argtypes = (
                wintypes.HANDLE, wintypes.DWORD, wintypes.DWORD,
                wintypes.DWORD, wintypes.DWORD, ctypes.POINTER(_OVERLAPPED),
            )
            self.dll.LockFileEx.restype = wintypes.BOOL
            self.dll.UnlockFileEx.argtypes = (
                wintypes.HANDLE, wintypes.DWORD, wintypes.DWORD,
                wintypes.DWORD, ctypes.POINTER(_OVERLAPPED),
            )
            self.dll.UnlockFileEx.restype = wintypes.BOOL
            self.dll.CloseHandle.argtypes = (wintypes.HANDLE,)
            self.dll.CloseHandle.restype = wintypes.BOOL
        except (OSError, AttributeError):
            raise ErrorBloqueoInstancia("api") from None

    def abrir(self, ruta: Path) -> int:
        # OPEN_ALWAYS, sin FILE_SHARE_DELETE ni SECURITY_ATTRIBUTES heredables.
        handle = self.dll.CreateFileW(str(ruta), 0xC0000000, 0x3, None, 4, 0x80, None)
        if not handle or handle == _INVALID_HANDLE_VALUE:
            raise ErrorBloqueoInstancia("apertura", ctypes.get_last_error())
        return handle

    def bloquear(self, handle: int, solapado: _OVERLAPPED) -> None:
        # EXCLUSIVE_LOCK | FAIL_IMMEDIATELY; un byte desde offset cero, aun sin datos.
        if not self.dll.LockFileEx(handle, 0x3, 0, 1, 0, ctypes.byref(solapado)):
            codigo = ctypes.get_last_error()
            if codigo == _ERROR_LOCK_VIOLATION:
                raise InstanciaEnUsoError()
            raise ErrorBloqueoInstancia("adquisicion", codigo)

    def desbloquear(self, handle: int, solapado: _OVERLAPPED) -> None:
        if not self.dll.UnlockFileEx(handle, 0, 1, 0, ctypes.byref(solapado)):
            raise ErrorBloqueoInstancia("liberacion", ctypes.get_last_error())

    def cerrar(self, handle: int) -> None:
        if not self.dll.CloseHandle(handle):
            raise ErrorBloqueoInstancia("cierre", ctypes.get_last_error())


class BloqueoInstanciaWindows:
    def __init__(self, directorio: str | os.PathLike[str]):
        try:
            ruta = Path(directorio)
            if not ruta.is_absolute() or "\0" in str(ruta):
                raise ValueError
        except (TypeError, ValueError):
            raise ErrorBloqueoInstancia("directorio") from None
        self._ruta = ruta / NOMBRE_ARCHIVO_BLOQUEO
        self._api: _ApiWindows | None = None
        self._handle: int | None = None
        self._bloqueado = False
        self._solapado = _OVERLAPPED()

    def adquirir(self) -> None:
        if self._handle is not None:
            raise ErrorBloqueoInstancia("ya_adquirido")
        api = _ApiWindows()
        self._api = api
        self._solapado = _OVERLAPPED()
        self._handle = api.abrir(self._ruta)
        try:
            api.bloquear(self._handle, self._solapado)
            self._bloqueado = True
        except BaseException as error:
            try:
                self.liberar()
            except ErrorBloqueoInstancia as limpieza:
                error.add_note(str(limpieza))
            raise

    def liberar(self) -> None:
        handle, api = self._handle, self._api
        if handle is None or api is None:
            return
        error = None
        if self._bloqueado:
            try:
                api.desbloquear(handle, self._solapado)
            except ErrorBloqueoInstancia as fallo:
                error = fallo
            else:
                self._bloqueado = False
        try:
            api.cerrar(handle)
        except ErrorBloqueoInstancia as fallo:
            # Conservar el handle para que el llamador pueda reintentar el cierre.
            if error is None:
                error = fallo
            else:
                error.add_note(str(fallo))
        else:
            self._handle = None
            self._api = None
            self._bloqueado = False
        if error is not None:
            raise error

    def __enter__(self) -> "BloqueoInstanciaWindows":
        self.adquirir()
        return self

    def __exit__(
        self,
        tipo: type[BaseException] | None,
        error: BaseException | None,
        traza: TracebackType | None,
    ) -> None:
        try:
            self.liberar()
        except ErrorBloqueoInstancia as limpieza:
            if error is None:
                raise
            error.add_note(str(limpieza))
