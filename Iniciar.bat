@echo off
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
  py -m venv .venv
  if errorlevel 1 goto error
)
.venv\Scripts\python.exe -m pip install -r requirements.txt
if errorlevel 1 goto error
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0instalar_ocr.ps1"
if errorlevel 1 goto error
.venv\Scripts\python.exe app.py
if errorlevel 1 goto error
exit /b 0
:error
echo No se pudo iniciar. Revise el mensaje anterior y la instalacion de Python.
pause
