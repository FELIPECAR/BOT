@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Ejecuta primero INSTALAR.cmd en esta carpeta.
    goto finished
)
".venv\Scripts\python.exe" -u simulator.py --summary
:finished
echo.
pause
endlocal
