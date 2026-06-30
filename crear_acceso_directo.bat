@echo off
setlocal
set "RAIZ=%~dp0"
set "EJECUTABLE=%RAIZ%dist\FM_Master_Gestion\FM_Master_Gestion.exe"

if not exist "%EJECUTABLE%" (
    echo No se encontro FM_Master_Gestion.exe.
    echo Primero ejecute: python build_exe.py
    pause
    exit /b 1
)

powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "$w = New-Object -ComObject WScript.Shell; $s = $w.CreateShortcut($w.SpecialFolders('Desktop') + '\FM Master Gestion.lnk'); $s.TargetPath = '%EJECUTABLE%'; $s.WorkingDirectory = Split-Path '%EJECUTABLE%'; $s.IconLocation = '%EJECUTABLE%,0'; $s.Description = 'FM Master Gestion'; $s.Save()"

if errorlevel 1 (
    echo No se pudo crear el acceso directo.
    pause
    exit /b 1
)

echo Acceso directo creado correctamente en el Escritorio.
pause
