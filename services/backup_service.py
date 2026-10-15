import os
import sqlite3
import tempfile
from contextlib import ExitStack, closing
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
    def crear_backup_pre_migracion(cls, ruta_base, directorio_backups):
        """Copia una instantanea verificada; no coordina la futura migracion.

        WAL se lee mediante SQLite, no mediante copia del archivo principal.
        El llamador debe impedir escrituras entre el respaldo y la migracion.
        """
        destino = None
        try:
            if not str(ruta_base or "").strip() or not str(directorio_backups or "").strip():
                raise OSError("Debe indicar la base de origen y el directorio de backups.")
            origen_path = Path(ruta_base).resolve(strict=True)
            if not origen_path.is_file():
                raise OSError("El origen no es un archivo de base SQLite.")
            with origen_path.open("rb") as archivo:
                if archivo.read(16) != b"SQLite format 3\x00":
                    raise OSError("El origen no contiene una cabecera SQLite valida.")
            directorio = Path(directorio_backups).resolve()
            if directorio == origen_path:
                raise OSError("El directorio de backups no puede ser la base de origen.")

            consulta_esquema = (
                "SELECT type, name, tbl_name, sql FROM sqlite_master ORDER BY type, name"
            )
            with ExitStack() as recursos:
                origen = recursos.enter_context(closing(sqlite3.connect(
                    origen_path.as_uri() + "?mode=ro", uri=True,
                )))
                origen.execute("BEGIN")
                if origen.execute("PRAGMA quick_check").fetchall() != [("ok",)]:
                    raise OSError("La verificacion de la base de origen no fue satisfactoria.")
                esquema_origen = origen.execute(consulta_esquema).fetchall()
                version_origen = origen.execute("PRAGMA user_version").fetchone()

                directorio.mkdir(parents=True, exist_ok=True)
                descriptor, nombre = tempfile.mkstemp(
                    prefix=f"pre_migracion_{datetime.now().strftime('%Y%m%d_%H%M%S')}_",
                    suffix=".db", dir=str(directorio),
                )
                destino = Path(nombre)
                with os.fdopen(descriptor, "wb"):
                    pass
                if destino.samefile(origen_path):
                    destino = None
                    raise OSError("El destino coincide con la base de origen.")

                with closing(sqlite3.connect(destino.as_uri() + "?mode=rw", uri=True)) as respaldo:
                    origen.backup(respaldo)

                if destino.stat().st_size == 0:
                    raise OSError("El backup pre-migracion quedo vacio.")
                with closing(sqlite3.connect(destino.as_uri() + "?mode=ro", uri=True)) as verificacion:
                    if verificacion.execute("PRAGMA quick_check").fetchall() != [("ok",)]:
                        raise OSError("La verificacion del backup pre-migracion no fue satisfactoria.")
                    if verificacion.execute(consulta_esquema).fetchall() != esquema_origen:
                        raise OSError("El esquema del backup no coincide con la instantanea del origen.")
                    if verificacion.execute("PRAGMA user_version").fetchone() != version_origen:
                        raise OSError("La version del backup no coincide con la instantanea del origen.")
            return str(destino)
        except Exception as error:
            errores_limpieza = []
            if destino is not None:
                for archivo in (
                    destino,
                    Path(str(destino) + "-journal"),
                    Path(str(destino) + "-wal"),
                    Path(str(destino) + "-shm"),
                ):
                    try:
                        archivo.unlink(missing_ok=True)
                    except OSError as error_limpieza:
                        errores_limpieza.append(str(error_limpieza))
            detalle = f"No se pudo crear un backup pre-migracion verificado: {error}"
            if errores_limpieza:
                detalle += "; no se pudieron eliminar archivos incompletos: " + "; ".join(errores_limpieza)
            raise OSError(detalle) from error

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
