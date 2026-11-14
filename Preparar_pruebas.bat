@echo off
setlocal
cd /d "%~dp0"
set "PYTHON_PRUEBAS=%~dp0..\.python313\python.exe"
if not exist "%PYTHON_PRUEBAS%" (
    echo No se encuentra el entorno local Python 3.13.
    pause
    exit /b 1
)
echo Instalando dependencias del entorno local...
"%PYTHON_PRUEBAS%" -m pip install --cache-dir "%~dp0..\.pip-cache" -r requirements.txt
if errorlevel 1 (
    echo No se completaron las dependencias. Revise el error anterior.
    pause
    exit /b 1
)
echo Ejecutando las pruebas...
"%PYTHON_PRUEBAS%" -m unittest discover -v > "%~dp0resultado_pruebas.txt" 2>&1
set "RESULTADO_PRUEBAS=%ERRORLEVEL%"
type "%~dp0resultado_pruebas.txt"
echo.
echo Registro guardado en resultado_pruebas.txt
pause
exit /b %RESULTADO_PRUEBAS%
