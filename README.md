# FM Master Gestion

Aplicacion de escritorio para la administracion comercial de FM Master.

## Instalar dependencias

Desde PowerShell, dentro de la carpeta del proyecto:

```powershell
python -m pip install -r requirements.txt
```

## Ejecutar el programa

```powershell
python main.py
```

La base SQLite y los archivos generados se guardan en las carpetas `database`,
`backup`, `pdf` y `exports`.

## Generar el ejecutable

```powershell
python build_exe.py
```

El resultado queda en:

```text
dist/FM_Master_Gestion/
```

El archivo para iniciar la aplicacion es `FM_Master_Gestion.exe`. Se debe
distribuir la carpeta completa generada por PyInstaller, ya que contiene las
dependencias, recursos y carpetas de datos necesarias.

Si existe un icono `.ico` dentro de `assets`, el script lo aplica
automaticamente. El logo PNG y el resto de los recursos se incluyen siempre.
