@echo off
setlocal
cd /d "%~dp0"
echo TRADING CLOUD - INSTALACION EN WINDOWS
echo.
for %%V in (3.12 3.13 3.11 3.10 3.14) do (
    py -%%V -c "import struct,platform,sys; sys.exit(0 if struct.calcsize('P')==8 and platform.machine().upper() in ('AMD64','X86_64') else 1)" >nul 2>&1
    if not errorlevel 1 (
        py -%%V preparar.py
        goto finished
    )
)
python -c "import struct,platform,sys; sys.exit(0 if struct.calcsize('P')==8 and platform.machine().upper() in ('AMD64','X86_64') and (3,10)<=sys.version_info[:2]<=(3,14) else 1)" >nul 2>&1
if not errorlevel 1 (
    python preparar.py
    goto finished
)
echo No se encontro Python compatible de 64 bits.
echo Instala Python 3.10 a 3.14 x64 desde:
echo https://www.python.org/downloads/windows/
echo Incluye pip y el launcher de Python. Luego vuelve a abrir INSTALAR.cmd.
:finished
echo.
pause
endlocal
