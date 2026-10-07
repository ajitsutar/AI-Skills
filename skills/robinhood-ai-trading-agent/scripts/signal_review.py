"""Recompute supported live entry signals from retained completed market bars."""
import hashlib
import math
from decimal import ROUND_FLOOR, ROUND_CEILING
from pathlib import Path

from risk_engine import canonical_hash, dec, timestamp
from strategy_lab import Bar, signal
from trading_calendar import audit_timestamps


def implementation_hash():
    root=Path(__file__).resolve().parent
    return hashlib.sha256((root/'strategy_lab.py').read_bytes()+(root/'signal_review.py').read_bytes()).hexdigest()


def evaluate_signal(order, evidence, registered, snapshot, now):
    reasons=[]
    if order['setup'] != 'opening_range_breakout':
        raise ValueError('No bundled live signal adapter for this tactical setup; implement and validate before promotion')
    parameters=registered['signal_parameters']
    if set(parameters) != {'opening_bars','bar_minutes'} or any(type(v) is not int or v <= 0 for v in parameters.values()):
        raise ValueError('Explicit positive whole-bar signal parameters required')
    if (order['setup_version'] != registered['version'] or evidence['symbol'] != order['symbol']
            or evidence['data_kind'] != 'market' or evidence['audit_passed'] is not True or not evidence['source']):
        reasons.append('SIGNAL_VERSION_SYMBOL_OR_DATA_AUDIT_MISMATCH')
    if registered['implementation_sha256'] != implementation_hash():
        reasons.append('SIGNAL_CODE_CHANGED_REVALIDATE_AND_REAUTHORIZE')
    if canonical_hash(evidence['bars']) != evidence['bars_hash']:
        reasons.append('SIGNAL_BAR_HASH_MISMATCH')
    bars=[]
    opening,closing=timestamp(snapshot['session']['open']),timestamp(snapshot['session']['close'])
    for row in evidence['bars']:
        values=[float(row[k]) for k in ('open','high','low','close','volume')]
        o,h,l,c,v=values
        end=timestamp(row['timestamp'])
        if (not all(math.isfinite(x) for x in values) or min(values[:4]) <= 0 or v < 0
                or l > min(o,c) or h < max(o,c) or l > h or not opening < end <= min(now,closing)):
            raise ValueError('Invalid, unfinished or out-of-session signal bar')
        if row.get('synthetic',False) is not False:
            raise ValueError('Synthetic signal bars rejected')
        bars.append(Bar(end,opening,closing,*values))
    if not bars:
        raise ValueError('Completed signal bars required')
    coverage=audit_timestamps([bar.end for bar in bars],opening.date().isoformat(),opening.date().isoformat(),
                              parameters['bar_minutes'],through=bars[-1].end)
    if not coverage['complete']:
        reasons.append('SIGNAL_SESSION_BAR_GAP')
    if not 0 <= (now-bars[-1].end).total_seconds() < parameters['bar_minutes']*60:
        reasons.append('SIGNAL_EXPIRED')
    if timestamp(order['signal_at']) != bars[-1].end:
        reasons.append('ORDER_SIGNAL_TIMESTAMP_MISMATCH')
    expected=signal(bars,order['setup'],**parameters)
    if not expected or expected['action'] != 'enter':
        reasons.append('NO_CURRENT_REGISTERED_ENTRY_SIGNAL')
    else:
        tick=dec(snapshot['quotes'][order['symbol']]['tick_size'])
        stop=(dec(expected['stop'])/tick).to_integral_value(rounding=ROUND_CEILING)*tick
        target=(dec(expected['target'])/tick).to_integral_value(rounding=ROUND_FLOOR)*tick
        cap=(dec(expected['entry_limit'])/tick).to_integral_value(rounding=ROUND_FLOOR)*tick
        if dec(order['stop_price']) != stop or dec(order['target_price']) != target or dec(order['limit_price']) > cap:
            reasons.append('ORDER_DIFFERS_FROM_REGISTERED_SIGNAL_ECONOMICS')
    return dict(eligible=not reasons,reasons=reasons,implementation_sha256=implementation_hash(),
                parameters_hash=canonical_hash(parameters),bars_hash=evidence['bars_hash'])
