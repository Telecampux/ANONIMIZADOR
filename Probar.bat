@echo off
setlocal
cd /d "%~dp0"
py -3.13 -c "import sys" >nul 2>&1
if not errorlevel 1 (
    py -3.13 -m unittest discover -v
    exit /b
)
if exist "..\.python313\python.exe" (
    "..\.python313\python.exe" -m unittest discover -v
    exit /b
)
echo No se pudo iniciar Python 3.13. Compruebe su instalacion y permisos.
exit /b 1
