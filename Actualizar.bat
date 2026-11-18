@echo off
cd /d "%~dp0"
if exist "%~dp0.venv\Scripts\python.exe" (
  "%~dp0.venv\Scripts\python.exe" "%~dp0Actualizador\actualizar.py" --direct "%~dp0"
) else (
  py -3 "%~dp0Actualizador\actualizar.py" --direct "%~dp0"
)
if errorlevel 1 (
  echo.
  echo No se pudo completar la actualizacion. Revise el error mostrado arriba.
  pause
  exit /b 1
)
echo.
echo Actualizacion terminada. Puede abrir Iniciar.bat.
pause
