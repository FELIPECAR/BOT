"""Trading Cloud: live paper trading with one diagnostic entry per processed M1 bar.
No MT5 trade submission calls, simulated funds only.
"""
from __future__ import annotations

import argparse
import csv
import json
import logging
import math
import os
import signal
import time
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from market_research import MarketResearch, record_exit_quality

SYMBOLS = ('Boom 500 Index', 'Crash 500 Index')
INITIAL_CASH = 100.0
RISK_FRACTION = 0.01
DAILY_LOSS_FRACTION = 0.02
STOP_ATR_MULT = 1.5
TAKE_R_MULT = 2.0
TICK_MAX_AGE_S = 45
CANDLE_MAX_AGE_S = {1: 180, 5: 600}
POLL_S = 1.0
HEARTBEAT_INTERVAL_S = 10.0
# Seguridad V3: recopilar datos y registrar senales, SIN ABRIR nuevas posiciones.
RESEARCH_ONLY = True
FIELDS = ['event_utc','type','symbol','side','volume','entry','exit','stop','take','planned_risk_usd','realized_pnl_usd','cash_after_usd','reason','signal_bar_utc','quote_utc']
DIAG_FIELDS = ['event_utc', 'bar_utc', 'symbol', 'status', 'side', 'reason',
               'close', 'atr14', 'cash_usd', 'quote_utc']


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso(epoch: float) -> str:
    return datetime.fromtimestamp(epoch, timezone.utc).isoformat()


def valid_quote(q, now_s: float) -> bool:
    return (q is not None and math.isfinite(float(q.ask)) and math.isfinite(float(q.bid))
            and q.ask > q.bid > 0 and 0 <= now_s - float(q.time) <= TICK_MAX_AGE_S)


def realized_loss_allowed(cash: float, start_cash: float, day_start_cash: float) -> bool:
    return cash > 0 and cash > day_start_cash - DAILY_LOSS_FRACTION * start_cash


@dataclass
class Position:
    symbol: str
    side: str
    volume: float
    entry: float
    stop: float
    take: float
    planned_risk_usd: float
    signal_bar_utc: str
    opened_utc: str
    entry_quote_utc: str


class Ledger:
    """Atomic checkpoint plus append-only trade events. Checkpoint is authoritative on restart."""
    def __init__(self, base: Path, initial: float = INITIAL_CASH):
        self.base = base
        self.base.mkdir(parents=True, exist_ok=True)
        self.state_path = base / 'paper_state.json'
        self.events_path = base / 'paper_events.csv'
        self.diagnostics_path = base / 'paper_diagnostics.csv'
        self.heartbeat_path = base / 'paper_heartbeat.json'
        self.initial = initial
        self.cash = initial
        self.day = utc_now().date().isoformat()
        self.day_start_cash = initial
        self.positions: dict[str, Position] = {}
        self.last_bar: dict[str, str] = {}
        self.last_signal_bar: dict[str, str] = {}
        self.trade_count = 0
        self.peak_cash = initial
        self.max_drawdown = 0.0
        if self.state_path.exists():
            state = json.loads(self.state_path.read_text(encoding='utf-8'))
            self.initial = float(state['initial'])
            self.cash = float(state['cash'])
            self.day = state['day']
            self.day_start_cash = float(state['day_start_cash'])
            self.positions = {name: Position(**p) for name, p in state['positions'].items()}
            self.last_bar = state['last_bar']
            self.last_signal_bar = state['last_signal_bar']
            self.trade_count = int(state['trade_count'])
            self.peak_cash = float(state['peak_cash'])
            self.max_drawdown = float(state['max_drawdown'])
        else:
            self.save()

    def save(self):
        state = {
            'initial': self.initial, 'cash': self.cash, 'day': self.day,
            'day_start_cash': self.day_start_cash,
            'positions': {k: asdict(v) for k, v in self.positions.items()},
            'last_bar': self.last_bar, 'last_signal_bar': self.last_signal_bar,
            'trade_count': self.trade_count, 'peak_cash': self.peak_cash,
            'max_drawdown': self.max_drawdown,
        }
        tmp = self.state_path.with_suffix('.json.tmp')
        tmp.write_text(json.dumps(state, indent=2), encoding='utf-8')
        os.replace(tmp, self.state_path)

    def event(self, event_type: str, symbol: str = '', **kw):
        data = {'event_utc': utc_now().isoformat(), 'type': event_type, 'symbol': symbol,
                **kw}
        with self.events_path.open('a', encoding='utf-8', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=FIELDS, extrasaction='ignore')
            if f.tell() == 0:
                writer.writeheader()
            writer.writerow(data)

    def diagnostic(self, bar: str, symbol: str, status: str, reason: str = '',
                   side: str = '', close: float | None = None,
                   atr14: float | None = None, quote_utc: str = ''):
        """Per-bar audit; unlike paper_events.csv, this includes NO_SIGNAL."""
        row = dict(event_utc=utc_now().isoformat(), bar_utc=bar,
                   symbol=symbol, status=status, side=side, reason=reason,
                   close=close, atr14=atr14, cash_usd=round(self.cash, 4),
                   quote_utc=quote_utc)
        with self.diagnostics_path.open('a', encoding='utf-8', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=DIAG_FIELDS)
            if f.tell() == 0:
                writer.writeheader()
            writer.writerow(row)

    def rotate_day(self):
        day = utc_now().date().isoformat()
        if day != self.day:
            self.day = day
            self.day_start_cash = self.cash
            self.save()

    def close(self, symbol: str, price: float, pnl: float, reason: str, quote_time: float):
        p = self.positions.pop(symbol)
        self.cash += pnl
        self.trade_count += 1
        self.peak_cash = max(self.peak_cash, self.cash)
        if self.peak_cash > 0:
            self.max_drawdown = max(self.max_drawdown,
                                    (self.peak_cash - self.cash) / self.peak_cash)
        self.save()
        self.event('CLOSE', symbol, side=p.side, volume=p.volume, entry=p.entry,
                   exit=price, stop=p.stop, take=p.take, planned_risk_usd=p.planned_risk_usd,
                   realized_pnl_usd=round(pnl, 4), cash_after_usd=round(self.cash, 4),
                   reason=reason, signal_bar_utc=p.signal_bar_utc,
                   quote_utc=iso(quote_time))


def indicators(df):
    import pandas as pd
    df = df.copy()
    for period in (9, 21, 50):
        df[f'ema{period}'] = df['close'].ewm(span=period, adjust=False).mean()
    prev = df['close'].shift(1)
    tr = pd.concat((df['high']-df['low'], (df['high']-prev).abs(),
                    (df['low']-prev).abs()), axis=1).max(axis=1)
    df['atr14'] = tr.rolling(14).mean()
    return df


def get_candles(mt5, name: str, timeframe, qty: int, max_age_s: int, now_s: float):
    import pandas as pd
    rates = mt5.copy_rates_from_pos(name, timeframe, 1, qty)
    if rates is None or len(rates) < qty:
        raise ValueError(f'{name}: historial incompleto; abre M1 y M5 en MT5')
    df = pd.DataFrame(rates).sort_values('time').reset_index(drop=True)
    last_t = float(df.iloc[-1]['time'])
    period_seconds = {
        mt5.TIMEFRAME_M1: 60,
        mt5.TIMEFRAME_M5: 300
    }.get(timeframe)

    if period_seconds is None or not 0 <= now_s - (last_t + period_seconds) <= period_seconds + 45:
        raise ValueError(f'{name}: vela desactualizada')
    return indicators(df)


def signal(m1, m5):
    """First closed M1 break of 10 prior bars; spike filter; M5 closed confirmation."""
    cur, prev, high_tf = m1.iloc[-1], m1.iloc[-2], m5.iloc[-1]
    atr = float(prev['atr14'])
    if not math.isfinite(atr) or atr <= 0:
        return None
    if float(cur['high'] - cur['low']) > 2.5 * atr:
        return None
    prior = m1.iloc[-11:-1]
    up = (cur['ema9'] > cur['ema21'] > prev['ema21']
          and high_tf['ema21'] > high_tf['ema50']
          and cur['close'] > prior['high'].max())
    down = (cur['ema9'] < cur['ema21'] < prev['ema21']
            and high_tf['ema21'] < high_tf['ema50']
            and cur['close'] < prior['low'].min())
    if up:
        return 'BUY', atr
    if down:
        return 'SELL', atr
    return None


def no_signal_reason(m1, m5) -> str:
    """Explanation only; does not modify the existing entry strategy."""
    cur, prev, high_tf = m1.iloc[-1], m1.iloc[-2], m5.iloc[-1]
    atr = float(prev['atr14'])
    if not math.isfinite(atr) or atr <= 0:
        return 'ATR previo no valido'
    if float(cur['high'] - cur['low']) > 2.5 * atr:
        return 'Filtro de volatilidad: rango de vela > 2.5 x ATR'
    prior = m1.iloc[-11:-1]
    up_break = float(cur['close']) > float(prior['high'].max())
    down_break = float(cur['close']) < float(prior['low'].min())
    if not up_break and not down_break:
        return 'Sin ruptura del maximo/minimo de las 10 velas anteriores'
    if up_break:
        return 'Ruptura alcista sin confirmacion simultanea de EMA M1 y M5'
    return 'Ruptura bajista sin confirmacion simultanea de EMA M1 y M5'


def calc_pnl(mt5, symbol: str, side: str, volume: float, entry: float, exit_price: float) -> Optional[float]:
    order = mt5.ORDER_TYPE_BUY if side == 'BUY' else mt5.ORDER_TYPE_SELL
    value = mt5.order_calc_profit(order, symbol, volume, entry, exit_price)
    if value is None or not math.isfinite(float(value)):
        return None
    return float(value)


def entry_plan(mt5, info, quote, side: str, cash: float, atr: float):
    """Minimum volume only; return reason or (entry, stop, take, estimated loss, margin)."""
    vol = float(info.volume_min)
    if vol <= 0 or not math.isfinite(vol):
        return 'volumen minimo invalido'
    spread = float(quote.ask - quote.bid)
    stop_dist = max(STOP_ATR_MULT * atr, float(info.trade_stops_level) * float(info.point),
                    spread * 2, float(info.trade_tick_size) * 2)
    entry = float(quote.ask if side == 'BUY' else quote.bid)
    stop = entry - stop_dist if side == 'BUY' else entry + stop_dist
    take = entry + TAKE_R_MULT * stop_dist if side == 'BUY' else entry - TAKE_R_MULT * stop_dist
    if stop <= 0 or take <= 0:
        return 'precio de salida invalido'
    # Quote-side exit prices: a BUY closes at Bid and SELL at Ask.
    loss = calc_pnl(mt5, info.name, side, vol, entry, stop)
    if loss is None or loss >= 0:
        return 'no se pudo calcular la perdida prevista'
    loss = -loss
    # Add a fixed fraction as provisional adverse-execution buffer; NOT a guaranteed cap.
    stress_exit = stop - 25 if side == 'BUY' else stop + 25
    stressed = calc_pnl(mt5, info.name, side, vol, entry, stress_exit)
    if stressed is None or not math.isfinite(float(stressed)):
        return 'no se pudo calcular escenario de spike'
    # Escenario adverso de 25 puntos: HIPOTESIS, no perdida maxima garantizada.
    # No aceptar una nueva posicion solo porque el stop teorico cabe en el presupuesto.
    if max(0.0, -float(stressed)) > cash * RISK_FRACTION:
        return ('RIESGO RECHAZADO: escenario adverso 25 puntos ' +
                f'${max(0.0, -float(stressed)):.2f} > ${cash*RISK_FRACTION:.2f}')
    if loss > cash * RISK_FRACTION:
        return f'RIESGO RECHAZADO: perdida planificada ${loss:.2f} > ${cash*RISK_FRACTION:.2f}'
    order = mt5.ORDER_TYPE_BUY if side == 'BUY' else mt5.ORDER_TYPE_SELL
    margin = mt5.order_calc_margin(order, info.name, vol, entry)
    if margin is None or not math.isfinite(float(margin)):
        return 'margen no disponible'
    if float(margin) > cash * 0.5:
        return 'margen requerido supera 50% del efectivo simulado'
    return entry, stop, take, loss, float(margin), float(stressed)


def run(base: Path, reset: bool = False):
    import MetaTrader5 as mt5
    import pandas as pd  # noqa: F401
    if reset:
        raise RuntimeError('La opcion --reset esta bloqueada en V3 para proteger el historial.')
    ledger = Ledger(base)
    if not mt5.initialize(timeout=30000):
        raise RuntimeError(f'Conexion MT5 fallida: {mt5.last_error()}')
    try:
        account = mt5.account_info()
        if account is None or account.trade_mode != mt5.ACCOUNT_TRADE_MODE_DEMO:
            raise RuntimeError('BLOQUEO: inicia sesion en cuenta DEMO antes de ejecutar')
        if 'deriv' not in (str(account.company) + str(account.server)).lower():
            raise RuntimeError('BLOQUEO: cuenta no identificada como Deriv')
        login = account.login  # used for runtime consistency only, never logged
        info = {}
        for name in SYMBOLS:
            sym = mt5.symbol_info(name)
            if sym is None:
                raise RuntimeError(f'Instrumento inexistente: {name}')
            if not sym.visible and not mt5.symbol_select(name, True):
                raise RuntimeError(f'No se pudo activar {name}')
            info[name] = mt5.symbol_info(name)
        print('TRADING CLOUD / PAPER ONLY / DEMO / USD 100 inicial')
        print('Nunca envia ordenes. Ctrl+C para detener. Salida:', base)
        print('V3 INVESTIGACION: no se abren posiciones ficticias nuevas; se conservan el saldo y el historial.')
        print('Si quedo una posicion ficticia anterior, se seguira hasta su cierre; no se abre otra.')
        print('Un stop es teorico; spikes pueden exceder 1% y el limite diario.')
        recorder = MarketResearch(base / 'market_data', mt5)
        warned: dict[str, str] = {}
        last_heartbeat_s = 0.0
        while True:
            a = mt5.account_info()
            if (a is None or a.trade_mode != mt5.ACCOUNT_TRADE_MODE_DEMO
                or a.login != login or 'deriv' not in (str(a.company)+str(a.server)).lower()):
                raise RuntimeError('BLOQUEO: cambio de cuenta o perdida de sesion MT5')
            ledger.rotate_day()
            now_s = utc_now().timestamp()
            quotes = {}
            for name in SYMBOLS:
                quote = mt5.symbol_info_tick(name)
                # Read-only price sampling, including delayed quotes; no broker orders.
                try:
                    recorder.observe_quote(name, quote, now_s)
                except Exception as err:  # Monitoring must not stop the paper engine.
                    if warned.get(name) != 'research':
                        print(f'{name}: registro de mercado no disponible: {err}')
                        warned[name] = 'research'
                if not valid_quote(quote, now_s):
                    if warned.get(name) != 'tick':
                        print(f'{name}: precio inexistente, invalido o desactualizado; se omite')
                        warned[name] = 'tick'
                    continue
                quotes[name] = quote
                warned.pop(name, None)
                p = ledger.positions.get(name)
                if p:
                    exit_price = float(quote.bid if p.side == 'BUY' else quote.ask)
                    reason = ('STOP' if (exit_price <= p.stop if p.side == 'BUY' else exit_price >= p.stop)
                              else 'TAKE' if (exit_price >= p.take if p.side == 'BUY' else exit_price <= p.take)
                              else None)
                    if reason:
                        pnl = calc_pnl(mt5, name, p.side, p.volume, p.entry, exit_price)
                        if pnl is not None:
                            ledger.close(name, exit_price, pnl, reason, quote.time)
                            try:
                                record_exit_quality(base / 'market_data', mt5, p,
                                                    exit_price, pnl, reason, quote, now_s,
                                                    previous_quote=recorder.prior_quote.get(name))
                            except Exception as err:  # The position has already been checkpointed.
                                print(f'{name}: no se guardo detalle de salida: {err}')
                            print(f'CERRADA {name} {reason}: P/L simulado ${pnl:+.2f}; saldo ${ledger.cash:.2f}')
                # no new trades while any simulated position exists across both instruments
                if ledger.positions or not realized_loss_allowed(ledger.cash, ledger.initial, ledger.day_start_cash):
                    continue
                try:
                    m1 = get_candles(mt5, name, mt5.TIMEFRAME_M1, 200,
                                     CANDLE_MAX_AGE_S[1], now_s)
                    m5 = get_candles(mt5, name, mt5.TIMEFRAME_M5, 120,
                                     CANDLE_MAX_AGE_S[5], now_s)
                    bar = iso(float(m1.iloc[-1]['time']))
                    if ledger.last_bar.get(name) == bar:
                        continue
                    ledger.last_bar[name] = bar
                    ledger.save()
                    found = signal(m1, m5)
                    last_close = float(m1.iloc[-1]['close'])
                    last_atr = float(m1.iloc[-2]['atr14'])
                    quote_utc = iso(quote.time)
                    if not found:
                        reason_no_signal = no_signal_reason(m1, m5)
                        ledger.diagnostic(bar, name, 'NO_SIGNAL', reason_no_signal,
                                          close=last_close, atr14=last_atr,
                                          quote_utc=quote_utc)
                        print(f'VELA {name} {bar}: SIN SENAL - {reason_no_signal}')
                        continue
                    if ledger.last_signal_bar.get(name) == bar:
                        continue
                    side, atr = found
                    ledger.diagnostic(bar, name, 'SIGNAL', 'Senal tecnica detectada',
                                      side=side, close=last_close, atr14=last_atr,
                                      quote_utc=quote_utc)
                    print(f'VELA {name} {bar}: SENAL {side}; solo investigacion, sin nueva posicion')
                    if RESEARCH_ONLY:
                        ledger.diagnostic(bar, name, 'RESEARCH_ONLY',
                                          'Entrada ficticia deshabilitada mientras se estudia el riesgo',
                                          side=side, close=last_close, atr14=last_atr,
                                          quote_utc=quote_utc)
                        continue
                    ledger.last_signal_bar[name] = bar
                    ledger.save()
                    plan = entry_plan(mt5, info[name], quote, side, ledger.cash, atr)
                    if isinstance(plan, str):
                        print(name, side, plan)
                        ledger.event('REJECT', name, side=side, reason=plan,
                                     signal_bar_utc=bar, quote_utc=iso(quote.time))
                        ledger.diagnostic(bar, name, 'REJECT', plan, side=side,
                                          close=last_close, atr14=last_atr,
                                          quote_utc=quote_utc)
                        continue
                    entry, stop, take, risk, margin, stressed = plan
                    p = Position(name, side, float(info[name].volume_min), entry, stop,
                                 take, risk, bar, utc_now().isoformat(), iso(quote.time))
                    ledger.positions[name] = p
                    ledger.save()
                    ledger.event('OPEN', name, side=side, volume=p.volume,
                                 entry=entry, stop=stop, take=take,
                                 planned_risk_usd=round(risk, 4),
                                 cash_after_usd=round(ledger.cash, 4),
                                 signal_bar_utc=bar, quote_utc=iso(quote.time),
                                 reason=f'margen estimado ${margin:.2f}; spike 25p P/L ${stressed:.2f}')
                    ledger.diagnostic(bar, name, 'OPEN', 'Posicion simulada aceptada',
                                      side=side, close=last_close, atr14=last_atr,
                                      quote_utc=quote_utc)
                    print(f'ABIERTA SIMULADA {name} {side} {p.volume} lote; riesgo previsto ${risk:.2f}; escenario 25p ${stressed:.2f}')
                except (ValueError, RuntimeError) as err:
                    if warned.get(name) != str(err):
                        print(f'{name}: {err}')
                        warned[name] = str(err)
            # Historical M5/H1 collection is separate from the active M1/M5 strategy.
            try:
                recorder.update_closed_bars(now_s)
            except Exception as err:  # Market-data export is not a trade condition.
                if warned.get('research_bars') != str(err):
                    print(f'Registro M5/H1: {err}')
                    warned['research_bars'] = str(err)
            if now_s - last_heartbeat_s >= HEARTBEAT_INTERVAL_S:
                beat = {
                    'event_utc': utc_now().isoformat(),
                    'mode': 'SOLO SIMULACION / INVESTIGACION SIN NUEVAS ENTRADAS',
                    'markets': {
                        symbol: {
                            'quote_valid': symbol in quotes,
                            'quote_utc': iso(quotes[symbol].time) if symbol in quotes else None,
                            'quote_age_seconds': round(max(0.0, now_s - quotes[symbol].time), 1)
                                if symbol in quotes else None,
                        } for symbol in SYMBOLS
                    },
                }
                temp = ledger.heartbeat_path.with_suffix('.json.tmp')
                temp.write_text(json.dumps(beat), encoding='utf-8')
                os.replace(temp, ledger.heartbeat_path)
                last_heartbeat_s = now_s
            time.sleep(POLL_S)
    except KeyboardInterrupt:
        print('\nDetenido; estado simulado conservado. Reinicia con el mismo script.')
    finally:
        mt5.shutdown()


def summary(base: Path):
    ledger = Ledger(base)
    wins = losses = 0
    net = 0.0
    if ledger.events_path.exists():
        with ledger.events_path.open(encoding='utf-8', newline='') as f:
            for row in csv.DictReader(f):
                if row['type'] == 'CLOSE':
                    x = float(row['realized_pnl_usd'])
                    wins += x > 0
                    losses += x < 0
                    net += x
    print(json.dumps({'modo':'SOLO SIMULACION', 'capital_inicial_usd': ledger.initial,
        'saldo_realizado_usd': round(ledger.cash, 4),
        'pnl_realizado_usd': round(net, 4), 'operaciones_cerradas': ledger.trade_count,
        'nuevas_entradas_habilitadas': not RESEARCH_ONLY,
        'ganadoras': wins, 'perdedoras': losses,
        'max_drawdown_saldo_cerrado_pct': round(100*ledger.max_drawdown, 3),
        'posiciones_abiertas': [asdict(p) for p in ledger.positions.values()]}, indent=2))
    if ledger.diagnostics_path.exists():
        counts = {}
        latest = {}
        with ledger.diagnostics_path.open(encoding='utf-8', newline='') as f:
            for row in csv.DictReader(f):
                key = (row['symbol'], row['status'])
                counts[key] = counts.get(key, 0) + 1
                latest[row['symbol']] = row
        print('DIAGNOSTICO POR MERCADO (desde la actualizacion):')
        for (symbol, status), count in sorted(counts.items()):
            print(f'  {symbol} | {status}: {count}')
        for symbol, row in sorted(latest.items()):
            print(f"  ULTIMA {symbol}: {row['bar_utc']} | {row['status']} | {row['reason']}")
    else:
        print('Todavia no hay diagnosticos por vela.')
    print('Saldo NO incluye el P/L flotante de las posiciones abiertas.')
    print('Datos de seguimiento en vivo, NO backtest y NO resultados de trading real.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Deriv MT5: simulacion en vivo, nunca envia ordenes')
    parser.add_argument('--summary', action='store_true', help='solo leer resultados guardados')
    parser.add_argument('--reset', action='store_true', help='BORRA historial y reinicia saldo simulado')
    args = parser.parse_args()
    base = Path(__file__).resolve().parent / 'paper_data'
    if args.summary:
        summary(base)
    else:
        run(base, args.reset)


