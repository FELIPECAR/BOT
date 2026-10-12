"""Prepare an isolated Windows environment for the existing research bot."""
from pathlib import Path
import platform
import struct
import subprocess
import sys
import venv


def main():
    root = Path(__file__).resolve().parent
    if sys.platform != 'win32' or platform.machine().upper() not in ('AMD64', 'X86_64'):
        print('Este paquete requiere Windows x64. No se ha realizado la instalacion.')
        return 1
    if struct.calcsize('P') != 8 or not (3, 10) <= sys.version_info[:2] <= (3, 14):
        print('Usa Python 3.10 a 3.14 de 64 bits; por ejemplo, Python 3.12 x64.')
        print('Descarga oficial: https://www.python.org/downloads/windows/')
        return 1
    target = root / '.venv'
    python = target / 'Scripts' / 'python.exe'
    print('Instalando en:', root, flush=True)
    print('Python:', sys.version.split()[0], '(64 bits)', flush=True)
    print('Se descargaran MetaTrader5, pandas y numpy desde PyPI.', flush=True)
    try:
        if not python.exists():
            venv.EnvBuilder(with_pip=True).create(target)
        subprocess.run([str(python), '-m', 'pip', 'install', '--upgrade', 'pip'],
                       check=True, cwd=root)
        subprocess.run([str(python), '-m', 'pip', 'install', '--only-binary=:all:',
                        '-r', str(root / 'requirements.txt')], check=True, cwd=root)
        subprocess.run([str(python), '-m', 'pip', 'check'], check=True, cwd=root)
        subprocess.run([str(python), '-c',
                        'import MetaTrader5, pandas, numpy; print("Dependencias OK")'],
                       check=True, cwd=root)
    except (subprocess.CalledProcessError, OSError) as error:
        print('\nINSTALACION INCOMPLETA:', error)
        print('Toma una captura del primer error y de esta ventana.')
        return 1
    print('\nINSTALACION TERMINADA. Falta comprobar la conexion en tu PC.')
    print('1. Abre Deriv MT5 de escritorio e inicia sesion en tu cuenta DEMO.')
    print('2. Abre Boom 500 Index y Crash 500 Index, con graficos M1 y M5.')
    print('3. Ejecuta INICIAR.cmd en esta misma carpeta.')
    print('El bot recopila datos y senales; las nuevas entradas estan deshabilitadas.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
