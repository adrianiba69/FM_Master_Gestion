import shutil
import sys
from pathlib import Path


FROZEN = bool(getattr(sys, "frozen", False))
APP_DIR = Path(sys.executable).resolve().parent if FROZEN else Path(__file__).resolve().parent
BUNDLE_DIR = Path(getattr(sys, "_MEIPASS", APP_DIR)).resolve()

ASSETS_DIR = BUNDLE_DIR / "assets"
DATABASE_DIR = APP_DIR / "database"
BACKUP_DIR = APP_DIR / "backup"
PDF_DIR = APP_DIR / "pdf"
EXPORTS_DIR = APP_DIR / "exports"
DATABASE_PATH = DATABASE_DIR / "fm_master.db"


def preparar_directorios():
    for carpeta in (DATABASE_DIR, BACKUP_DIR, PDF_DIR / "resumenes", EXPORTS_DIR):
        carpeta.mkdir(parents=True, exist_ok=True)

    base_empaquetada = BUNDLE_DIR / "database" / "fm_master.db"
    if not DATABASE_PATH.exists() and base_empaquetada.is_file():
        shutil.copy2(base_empaquetada, DATABASE_PATH)


preparar_directorios()
