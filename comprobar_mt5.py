"""Check the bot's actual prerequisites; never submit broker orders."""
from pathlib import Path
import ast
import math
import platform
import struct
import sys
import time

from simulator import SYMBOLS, TICK_MAX_AGE_S, get_candles, valid_quote


def check_source(root):
    for name in ('simulator.py', 'market_research.py'):
        tree = ast.parse((root / name).read_text(encoding='utf-8'))
        if any(isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
               and node.func.attr in ('order_send', 'order_check')
               for node in ast.walk(tree)):
            raise RuntimeError('El archivo contiene llamadas ajenas a esta version de investigacion: ' + name)
    import simulator
    if simulator.RESEARCH_ONLY is not True:
        raise RuntimeError('RESEARCH_ONLY debe permanecer en True para este paquete.')


def diagnose(mt5):
    """Accept only the original bot's demo account and fresh-data requirements."""
    if not mt5.initialize(timeout=15000):
        print('[ERROR] Conexion con MT5 fallida:', mt5.last_error())
        print('Abre Deriv MT5 de escritorio e inicia sesion; vuelve a ejecutar INICIAR.cmd.')
        return 1
    try:
        terminal = mt5.terminal_info()
        if terminal is None or not terminal.connected:
            print('[ERROR] MT5 no esta conectado. Revisa la conexion dentro de MT5.')
            return 1
        account = mt5.account_info()
        if account is None or account.trade_mode != mt5.ACCOUNT_TRADE_MODE_DEMO:
            print('[ERROR] Inicia sesion en la cuenta DEMO antes de continuar.')
            return 1
        if 'deriv' not in (str(account.company) + str(account.server)).lower():
            print('[ERROR] La cuenta conectada no se identifica como Deriv.')
            return 1
        if str(account.currency).upper() != 'USD':
            print('[ERROR] Esta version calcula el capital virtual en USD; utiliza una demo en USD.')
            return 1
        print('[OK] MT5 conectado a una cuenta demo Deriv en USD.')
        failed = False
        for name in SYMBOLS:
            info = mt5.symbol_info(name)
            if info is None:
                print('[ERROR]', name, ': instrumento inexistente en esta cuenta.')
                print('Selecciona la demo Deriv que ofrezca Boom 500 y Crash 500.')
                failed = True
                continue
            if not info.visible and not mt5.symbol_select(name, True):
                print('[ERROR]', name, ': no se pudo mostrar el instrumento en MT5.')
                failed = True
                continue
            quote = mt5.symbol_info_tick(name)
            now_s = time.time()
            if not valid_quote(quote, now_s):
                age = now_s - float(quote.time) if quote is not None else None
                print('[ERROR]', name, ': precio inexistente, invalido o desactualizado.')
                if age is not None and math.isfinite(age):
                    print('Edad del precio:', round(age, 2), 'segundos; limite:', TICK_MAX_AGE_S)
                print('Verifica la conexion de MT5 y sincroniza fecha y hora de Windows.')
                failed = True
            else:
                print('[OK]', name, ': precio reciente disponible.')
            for label, timeframe, qty, max_age in (
                ('M1', mt5.TIMEFRAME_M1, 200, 180),
                ('M5', mt5.TIMEFRAME_M5, 120, 600),
            ):
                try:
                    bars = get_candles(mt5, name, timeframe, qty, max_age, time.time())
                    if len(bars) != qty:
                        raise ValueError('historial incompleto')
                except (ValueError, RuntimeError) as error:
                    print('[ERROR]', name, label, ':', error)
                    print('Abre su grafico ' + label + ', espera a que cargue el historial y repite INICIAR.cmd.')
                    failed = True
                else:
                    print('[OK]', name, label, ':', qty, 'velas cerradas y recientes.')
        if failed:
            print('\nCorrige los puntos marcados [ERROR] y vuelve a ejecutar INICIAR.cmd.')
            return 1
        print('\nCONEXION Y DATOS OK. Iniciando investigacion de precios y senales.')
        return 0
    finally:
        mt5.shutdown()


def main():
    print('COMPROBACION DEL BOT - INVESTIGACION DEMO', flush=True)
    if sys.platform != 'win32' or struct.calcsize('P') != 8 or platform.machine().upper() not in ('AMD64', 'X86_64'):
        print('[ERROR] Se requiere Windows x64 y Python de 64 bits.')
        return 1
    try:
        check_source(Path(__file__).resolve().parent)
        import MetaTrader5 as mt5
        import pandas
        print('Python:', sys.version.split()[0], '| MetaTrader5:', mt5.__version__, '| pandas:', pandas.__version__)
        return diagnose(mt5)
    except ImportError as error:
        print('[ERROR] Dependencia faltante:', error)
        print('Ejecuta primero INSTALAR.cmd.')
        return 1
    except Exception as error:
        print('[ERROR]', error)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
