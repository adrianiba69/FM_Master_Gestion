import os
import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path

from runtime_paths import BACKUP_DIR, DATABASE_PATH


class BackupService:
    DATABASE_PATH = DATABASE_PATH
    BACKUP_DIR = BACKUP_DIR

    @classmethod
    def listar_backups(cls):
        cls.BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        return sorted(
            cls.BACKUP_DIR.glob("backup_????????_??????.db"),
            key=lambda archivo: archivo.stat().st_mtime,
            reverse=True,
        )

    @classmethod
    def existe_backup_del_dia(cls, fecha=None):
        dia = fecha or date.today()
        patron = f"backup_{dia.strftime('%Y%m%d')}_??????.db"
        cls.BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        return any(cls.BACKUP_DIR.glob(patron))

    @classmethod
    def crear_backup(cls):
        if not cls.DATABASE_PATH.exists():
            raise OSError(f"No se encontro la base de datos: {cls.DATABASE_PATH}")

        cls.BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        momento = datetime.now().replace(microsecond=0)
        destino = cls._destino_disponible(momento)

        origen = sqlite3.connect(str(cls.DATABASE_PATH))
        respaldo = sqlite3.connect(str(destino))
        try:
            origen.backup(respaldo)
            resultado = respaldo.execute("PRAGMA quick_check").fetchone()
            if not resultado or resultado[0] != "ok":
                raise OSError("La verificacion del backup no fue satisfactoria.")
        except Exception:
            respaldo.close()
            origen.close()
            if destino.exists():
                destino.unlink()
            raise
        else:
            respaldo.close()
            origen.close()

        if destino.stat().st_size == 0:
            destino.unlink()
            raise OSError("El archivo de backup quedo vacio.")
        return str(destino.resolve())

    @classmethod
    def crear_backup_automatico(cls):
        if cls.existe_backup_del_dia():
            return None
        return cls.crear_backup()

    @classmethod
    def abrir_carpeta(cls):
        cls.BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        try:
            os.startfile(str(cls.BACKUP_DIR.resolve()))
        except (AttributeError, OSError) as error:
            raise OSError("No se pudo abrir la carpeta de backups.") from error

    @classmethod
    def ultimo_backup(cls):
        backups = cls.listar_backups()
        return backups[0] if backups else None

    @classmethod
    def _destino_disponible(cls, momento):
        candidato = momento
        while True:
            nombre = f"backup_{candidato.strftime('%Y%m%d_%H%M%S')}.db"
            destino = cls.BACKUP_DIR / nombre
            if not destino.exists():
                return destino
            candidato += timedelta(seconds=1)
