@echo off
setlocal EnableExtensions EnableDelayedExpansion

echo ==============================================
echo Iniciando actualizacion de FM Master Gestion
echo ==============================================
echo.

set "SRC=C:\Users\Usuario\Desktop\FM_Master_Gestion"
set "DST=C:\Users\Usuario\Desktop\FM_Master_Gestion_Produccion"
set "DB_DIR=%DST%\database"
set "DB_FILE=%DB_DIR%\fm_master.db"
set "BKP_DIR=%DST%\backup"

if not exist "%DST%" (
    echo ERROR: No existe la carpeta destino:
    echo %DST%
    echo.
    pause
    exit /b 1
)

if not exist "%BKP_DIR%" (
    mkdir "%BKP_DIR%"
)

echo Creando backup de base de datos de produccion...
for /f %%i in ('powershell -NoProfile -Command "Get-Date -Format yyyyMMdd_HHmmss"') do set "TS=%%i"
set "DB_BKP=%BKP_DIR%\fm_master_%TS%.db"

if exist "%DB_FILE%" (
    copy /Y "%DB_FILE%" "%DB_BKP%" >nul
    if errorlevel 1 (
        echo ERROR: No se pudo crear el backup de la base de datos.
        echo.
        pause
        exit /b 1
    )
    echo Backup creado: %DB_BKP%
) else (
    echo ADVERTENCIA: No se encontro la base de datos en produccion.
    echo Se continua sin backup de DB.
)

echo.
echo Copiando archivos desde desarrollo a produccion...
robocopy "%SRC%" "%DST%" /E /R:2 /W:2 /NFL /NDL /NP /NJS /NJH ^
    /XD "%SRC%\backup" "%SRC%\__pycache__" "%SRC%\.git" "%SRC%\.venv" "%SRC%\dist" "%SRC%\build" ^
    /XF "fm_master.db" "*.db" "*.pyc"
set "RC=%ERRORLEVEL%"

if %RC% GEQ 8 (
    echo.
    echo ERROR: Fallo la copia con robocopy. Codigo: %RC%
    echo.
    pause
    exit /b %RC%
)

echo.
echo Actualizacion finalizada.
echo Base de datos de produccion conservada.
echo.
pause
exit /b 0
