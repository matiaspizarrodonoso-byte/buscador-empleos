@echo off
chcp 65001 >nul
cd /d "%~dp0"
python buscador.py
if errorlevel 1 (
  echo.
  echo Hubo un error. Verifica que Python este instalado y ejecuta:
  echo pip install -r requirements.txt
)
pause
