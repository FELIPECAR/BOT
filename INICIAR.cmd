@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Ejecuta primero INSTALAR.cmd en esta carpeta.
    goto finished
)
".venv\Scripts\python.exe" -u comprobar_mt5.py
if errorlevel 1 goto finished
echo.
echo El bot registrara precios y senales. Ctrl+C permite detenerlo.
echo Conserva MT5 abierto y el PC encendido mientras recopilas datos.
".venv\Scripts\python.exe" -u simulator.py
if errorlevel 1 echo El bot termino con un error. Toma una captura de esta ventana.
:finished
echo.
pause
endlocal
