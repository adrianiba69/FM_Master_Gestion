import shutil
import sys
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

ASSETS_DIR = (APP_DIR if FROZEN else BUNDLE_DIR) / "assets"
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


def preparar_directorios():
    for carpeta in DIRECTORIOS_ESCRITURA:
        carpeta.mkdir(parents=True, exist_ok=True)
    (PDF_DIR / "resumenes").mkdir(parents=True, exist_ok=True)
    MANUALES_DIR.mkdir(parents=True, exist_ok=True)

    base_empaquetada = BUNDLE_DIR / "database" / "fm_master.db"
    if not DATABASE_PATH.exists() and base_empaquetada.is_file():
        shutil.copy2(base_empaquetada, DATABASE_PATH)


preparar_directorios()
