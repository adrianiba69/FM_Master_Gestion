import sys
from dataclasses import dataclass
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parent


def obtener_directorio_aplicacion(*, frozen=None, executable=None):
    """Devuelve la raíz de escritura sin depender del directorio de trabajo."""
    esta_empaquetada = bool(getattr(sys, "frozen", False)) if frozen is None else frozen
    if esta_empaquetada:
        ejecutable = Path(executable or sys.executable).resolve()
        return ejecutable.parent
    return PROJECT_DIR


FROZEN = bool(getattr(sys, "frozen", False))
APP_DIR = obtener_directorio_aplicacion()
BUNDLE_DIR = Path(getattr(sys, "_MEIPASS", PROJECT_DIR)).resolve() if FROZEN else PROJECT_DIR

ASSETS_DIR = BUNDLE_DIR / "assets"
DATABASE_DIR = APP_DIR / "database"
BACKUP_DIR = APP_DIR / "backup"
PDF_DIR = APP_DIR / "pdf"
MANUALES_DIR = APP_DIR / "manuales"
EXPORTS_DIR = APP_DIR / "exports"
CIERRES_DIR = APP_DIR / "cierres"
DATABASE_PATH = DATABASE_DIR / "fm_master.db"
DIRECTORIOS_ESCRITURA = (
    DATABASE_DIR,
    BACKUP_DIR,
    PDF_DIR,
    MANUALES_DIR,
    EXPORTS_DIR,
    CIERRES_DIR,
)


ESTADO_BASE_EXISTENTE = "BASE_EXISTENTE"
ESTADO_BASE_AUSENTE_CON_RASTROS = "BASE_AUSENTE_CON_RASTROS"
ESTADO_BASE_AUSENTE_SIN_RASTROS = "BASE_AUSENTE_SIN_RASTROS"
SUFIJOS_ARCHIVOS_AUXILIARES_SQLITE = ("-wal", "-shm", "-journal")


@dataclass(frozen=True)
class EstadoArchivoBase:
    estado: str
    ruta_base: Path
    rastros: tuple = ()

    @property
    def existe(self):
        return self.estado == ESTADO_BASE_EXISTENTE


def preparar_directorios():
    """Crea solo directorios de escritura; nunca crea ni copia la base SQLite."""
    for carpeta in DIRECTORIOS_ESCRITURA:
        carpeta.mkdir(parents=True, exist_ok=True)
    (PDF_DIR / "resumenes").mkdir(parents=True, exist_ok=True)


def inspeccionar_archivo_base(*, database_path=None, directorios_escritura=None):
    """Clasifica la base sin abrirla ni modificar el sistema de archivos."""
    ruta_base = Path(database_path or DATABASE_PATH)
    if ruta_base.is_file():
        return EstadoArchivoBase(ESTADO_BASE_EXISTENTE, ruta_base)

    rastros = []
    if ruta_base.exists():
        rastros.append(ruta_base)
    for sufijo in SUFIJOS_ARCHIVOS_AUXILIARES_SQLITE:
        auxiliar = ruta_base.with_name(ruta_base.name + sufijo)
        if auxiliar.exists():
            rastros.append(auxiliar)

    directorios = DIRECTORIOS_ESCRITURA if directorios_escritura is None else directorios_escritura
    for carpeta in (ruta_base.parent, *directorios):
        carpeta = Path(carpeta)
        if carpeta.is_dir() and any(True for _ in carpeta.iterdir()):
            rastros.append(carpeta)

    rastros = tuple(dict.fromkeys(rastros))
    estado = ESTADO_BASE_AUSENTE_CON_RASTROS if rastros else ESTADO_BASE_AUSENTE_SIN_RASTROS
    return EstadoArchivoBase(estado, ruta_base, rastros)
