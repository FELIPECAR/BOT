"""Read-only market-data observations for Trading Cloud's paper simulator.

Historical rows are closed M5/H1 OHLC bars as provided by Deriv MT5.
Quote rows are sampled observations (NOT a complete broker tick history).
This module does not place, modify, or check broker orders.
"""
from __future__ import annotations

import csv
import math
import time
from datetime import datetime, timezone
from pathlib import Path

SYMBOLS = ('Boom 500 Index', 'Crash 500 Index')
BARS_FIELDS = ['bar_utc','open','high','low','close','tick_volume','spread','real_volume','collected_utc']
QUOTE_FIELDS = ['observed_utc','symbol','quote_utc','age_seconds','bid','ask','spread',
                'valid_45s','age_over_5s','note']
EXIT_FIELDS = ['recorded_utc','symbol','side','opened_utc','signal_bar_utc','quote_utc',
               'quote_age_seconds','entry','stop','planned_risk_usd','stop_loss_usd',
               'actual_exit','realized_pnl_usd','stop_overshoot_points','loss_vs_stop_usd','reason',
               'note']
# Nuevos CSV separados: no cambiamos las columnas de los archivos historicos.
GAP_FIELDS = ['observed_utc','symbol','event','previous_quote_utc','current_quote_utc',
              'quote_gap_seconds','observed_gap_seconds','quote_age_seconds','note']
EXIT_AUDIT_FIELDS = EXIT_FIELDS + ['previous_quote_utc','previous_bid','previous_ask',
                 'quote_gap_seconds','observation_gap_seconds','stop_crossed_between_samples',
                 'sample_quality']


def _utc(epoch):
    return datetime.fromtimestamp(float(epoch), timezone.utc).isoformat()


def _append(path: Path, fields: list[str], row: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a', encoding='utf-8', newline='') as f:
        writer=csv.DictWriter(f, fieldnames=fields, extrasaction='ignore')
        if f.tell()==0:
            writer.writeheader()
        writer.writerow(row)


def _last_bar_epoch(path: Path):
    if not path.exists():
        return -1.0
    last = None
    with path.open(encoding='utf-8', newline='') as f:
        for row in csv.DictReader(f):
            if row.get('bar_utc'):
                last = row['bar_utc']
    if last:
        try:
            return datetime.fromisoformat(last).timestamp()
        except ValueError:
            pass
    return -1.0


class MarketResearch:
    def __init__(self, folder: Path, mt5):
        self.folder=Path(folder)
        self.mt5=mt5
        self.folder.mkdir(parents=True, exist_ok=True)
        self.last_bars={}
        for symbol in SYMBOLS:
            for label in ('M5','H1'):
                self.last_bars[(symbol,label)]=_last_bar_epoch(self._bar_path(symbol,label))
        self.last_fetch=0.0
        self.last_quote={}
        self.last_observation={}
        self.last_seen_quote={}
        self.prior_quote={}
        self.freeze_reported={}

    def _bar_path(self, symbol, label):
        return self.folder / (symbol.lower().replace(' ','_')+'_'+label.lower()+'.csv')

    def observe_quote(self, symbol, q, now_s):
        """Sample changed quotes; audit the observed sampling gaps."""
        stamp_s = (float(q.time_msc)/1000.0 if q is not None and getattr(q, 'time_msc', 0)
                   else float(q.time) if q is not None else None)
        previous = self.last_seen_quote.get(symbol)
        if stamp_s is not None and previous is not None:
            prev_stamp, prev_bid, prev_ask, prev_obs = previous
            quote_gap = stamp_s - prev_stamp
            observed_gap = now_s - prev_obs
            event = None
            if quote_gap < -0.001:
                event = 'QUOTE_TIME_BACKWARD'
            elif quote_gap == 0:
                if observed_gap >= 5.0 and self.freeze_reported.get(symbol) != stamp_s:
                    event = 'UNCHANGED_QUOTE_5S'
                    self.freeze_reported[symbol] = stamp_s
            elif quote_gap > 3.0 or observed_gap > 5.0:
                event = 'SAMPLE_GAP'
            if event:
                _append(self.folder/'quote_gaps.csv', GAP_FIELDS,
                        {'observed_utc': _utc(now_s), 'symbol': symbol, 'event': event,
                         'previous_quote_utc': _utc(prev_stamp), 'current_quote_utc': _utc(stamp_s),
                         'quote_gap_seconds': round(quote_gap, 3),
                         'observed_gap_seconds': round(observed_gap, 3),
                        'quote_age_seconds': round(now_s-stamp_s, 3),
                         'note': 'brecha ENTRE muestras observadas; no prueba perdida de ticks del broker'})
        if stamp_s is not None and q is not None:
            if previous is None or stamp_s != previous[0]:
                self.prior_quote[symbol] = previous
                self.last_seen_quote[symbol] = (stamp_s, float(q.bid), float(q.ask), now_s)
        last_obs=self.last_observation.get(symbol, 0)
        stamp = float(getattr(q, 'time_msc', 0) or getattr(q,'time', 0)*1000) if q is not None else None
        bid = float(q.bid) if q is not None else None
        ask = float(q.ask) if q is not None else None
        ident=(stamp,bid,ask)
        if ident == self.last_quote.get(symbol) and now_s-last_obs < 60:
            return
        self.last_quote[symbol]=ident
        self.last_observation[symbol]=now_s
        qt=float(q.time) if q is not None else None
        age=now_s-qt if qt is not None else None
        plausible=(age is not None and math.isfinite(age) and 0<=age<=45 and
                   bid is not None and ask is not None and
                   math.isfinite(bid) and math.isfinite(ask) and ask>bid>0)
        row={'observed_utc':_utc(now_s),'symbol':symbol,
             'quote_utc':_utc(qt) if qt is not None and qt>0 else '',
             'age_seconds':round(age,3) if age is not None else '',
             'bid':bid if bid is not None else '', 'ask':ask if ask is not None else '',
             'spread':round(ask-bid,6) if ask is not None and bid is not None else '',
             'valid_45s':int(plausible),
             'age_over_5s':int(age is None or age>5 or age<0),
             'note':'observacion muestreada; NO historial completo de ticks'}
        _append(self.folder/'quote_observations.csv',QUOTE_FIELDS,row)

    def update_closed_bars(self, now_s):
        """Backfill closed MT5 M5/H1 bars once, then poll every 30 seconds."""
        if now_s-self.last_fetch<30:
            return
        self.last_fetch=now_s
        settings=(('M5', self.mt5.TIMEFRAME_M5,300,500),
                  ('H1', self.mt5.TIMEFRAME_H1,3600,300))
        for symbol in SYMBOLS:
            for label,timeframe,seconds,qty in settings:
                rows=self.mt5.copy_rates_from_pos(symbol,timeframe,1,qty)
                if rows is None or len(rows)==0:
                    continue
                key=(symbol,label)
                last=self.last_bars[key]
                path=self._bar_path(symbol,label)
                for bar in sorted(rows,key=lambda b:int(b['time'])):
                    ts=float(bar['time'])
                    if ts<=last or ts+seconds>now_s:
                        continue  # Never use a still-forming or future bar.
                    row={'bar_utc':_utc(ts), 'open':float(bar['open']),
                         'high':float(bar['high']), 'low':float(bar['low']),
                         'close':float(bar['close']),
                         'tick_volume':int(bar['tick_volume']), 'spread':int(bar['spread']),
                         'real_volume':int(bar['real_volume']), 'collected_utc':_utc(now_s)}
                    _append(path,BARS_FIELDS,row)
                    last=ts
                self.last_bars[key]=last


def record_exit_quality(folder,mt5,position,exit_price,pnl,reason,quote,now_s,previous_quote=None):
    """Report deviations from theoretical stop; never reinterpret a gap as a known spike."""
    order=mt5.ORDER_TYPE_BUY if position.side=='BUY' else mt5.ORDER_TYPE_SELL
    estimated=mt5.order_calc_profit(order,position.symbol,position.volume,
                                    position.entry,position.stop)
    estimated=float(estimated) if estimated is not None else float('nan')
    stop_loss=-estimated if math.isfinite(estimated) and estimated<0 else None
    over=(max(0.0,position.stop-exit_price) if position.side=='BUY' else
          max(0.0,exit_price-position.stop)) if reason=='STOP' else 0.0
    row = {'recorded_utc':_utc(now_s),'symbol':position.symbol,'side':position.side,
             'opened_utc':position.opened_utc,'signal_bar_utc':position.signal_bar_utc,
             'quote_utc':_utc(quote.time),'quote_age_seconds':round(now_s-quote.time,3),
             'entry':position.entry,'stop':position.stop,
             'planned_risk_usd':position.planned_risk_usd,
             'stop_loss_usd':round(stop_loss,4) if stop_loss is not None else '',
             'actual_exit':exit_price,'realized_pnl_usd':round(pnl,4),
             'stop_overshoot_points':round(over,6),
             'loss_vs_stop_usd':round(max(0.0,estimated-pnl),4) if math.isfinite(estimated) else '',
             'reason':reason,
             'note':'salida al precio observado; saltos intermedios desconocidos'}
    _append(Path(folder)/'exit_quality.csv', EXIT_FIELDS, row)
    prior_stamp, prior_bid, prior_ask, prior_observed = previous_quote if previous_quote else (None,None,None,None)
    current_stamp=(float(quote.time_msc)/1000.0 if getattr(quote,'time_msc',0)
                   else float(quote.time))
    crossed = (prior_bid > position.stop and float(quote.bid) <= position.stop
               if position.side == 'BUY' else
               prior_ask < position.stop and float(quote.ask) >= position.stop) if previous_quote else None
    gap=(current_stamp-prior_stamp) if prior_stamp is not None else None
    observed_gap=(now_s-prior_observed) if prior_observed is not None else None
    age=now_s-current_stamp
    quality=('NO_EVALUABLE' if previous_quote is None else
             'MUESTRA_CON_BRECHA' if gap < 0 or gap > 3 or observed_gap > 5 or age > 5 or age < 0
             else 'MUESTRAS_PROXIMAS_NO_TICKS_COMPLETOS')
    row.update({'previous_quote_utc': _utc(prior_stamp) if prior_stamp is not None else '',
                'previous_bid': prior_bid if prior_bid is not None else '',
                'previous_ask': prior_ask if prior_ask is not None else '',
                'quote_gap_seconds': round(gap,3) if gap is not None else '',
                'observation_gap_seconds': round(observed_gap,3) if observed_gap is not None else '',
                'stop_crossed_between_samples': int(crossed) if crossed is not None else '',
                'sample_quality': quality})
    _append(Path(folder)/'exit_quality_v2.csv', EXIT_AUDIT_FIELDS, row)
