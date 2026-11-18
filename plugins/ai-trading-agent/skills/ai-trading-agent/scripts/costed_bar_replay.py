"""Original standard-library-only, bounded, single-instrument bar paper replay.

Complete-bar volume is a prior-observation liquidity proxy. Output fills are
modeled, not observed. No external engine, service, broker or network is used.
See references/costed-bar-replay.md for the closed schema and conventions.
"""
from datetime import datetime, timezone
from decimal import (Context, Decimal, DivisionByZero, InvalidOperation, Overflow,
                     ROUND_FLOOR, ROUND_HALF_EVEN, localcontext)
import re


def _keys(value, names, label):
    if type(value) is not dict or set(value) != set(names):
        raise ValueError(f"{label} must contain exactly: {', '.join(sorted(names))}")


def _number(value, label, positive=False):
    if not isinstance(value, str) or not re.fullmatch(r"(?:0|[1-9][0-9]*)(?:\.[0-9]+)?", value):
        raise ValueError(f"{label} must be a nonnegative finite decimal string")
    if len(value.replace('.', '')) > 36 or ('.' in value and len(value.split('.')[1]) > 18):
        raise ValueError(f"{label} exceeds 36 digits or 18 decimal places")
    result = Decimal(value)
    if positive and result <= 0:
        raise ValueError(f"{label} must be positive")
    return result


def _time(value, label):
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?Z", value):
        raise ValueError(f"{label} must be a UTC timestamp ending in Z")
    try:
        return datetime.fromisoformat(value[:-1] + '+00:00')
    except ValueError as exc:
        raise ValueError(f"invalid {label}") from exc


def _stamp(value):
    return value.astimezone(timezone.utc).isoformat().replace('+00:00', 'Z')


def _text(value):
    result = format(value, 'f')
    return result.rstrip('0').rstrip('.') if '.' in result else result


def simulate(document):
    """Return reproducible modeled fills; reject missing or extra conventions."""
    context = Context(prec=120, rounding=ROUND_HALF_EVEN, Emin=-999999, Emax=999999,
                      capitals=1, clamp=0, flags=[], traps=[InvalidOperation, DivisionByZero, Overflow])
    with localcontext(context):
        return _simulate(document)


def _simulate(inputs):
    _keys(inputs, {'schema_version', 'as_of', 'currency', 'asset_class', 'initial_cash',
                  'bars', 'signals', 'costs', 'max_participation', 'time_in_force', 'quantity_step'}, 'document')
    if type(inputs['schema_version']) is not int or inputs['schema_version'] != 1:
        raise ValueError('schema_version must be integer 1')
    cutoff = _time(inputs['as_of'], 'as_of')
    if not isinstance(inputs['currency'], str) or not re.fullmatch(r'[A-Z]{3}', inputs['currency']):
        raise ValueError('currency must be three uppercase ASCII letters')
    if inputs['asset_class'] not in ('equity', 'etf', 'spot_crypto'):
        raise ValueError('asset_class must be equity, etf or spot_crypto')
    if inputs['time_in_force'] not in ('carry', 'cancel'):
        raise ValueError('time_in_force must be carry or cancel')
    cash = _number(inputs['initial_cash'], 'initial_cash')
    initial_cash = cash
    step = _number(inputs['quantity_step'], 'quantity_step', True)
    participation = _number(inputs['max_participation'], 'max_participation', True)
    if participation > 1:
        raise ValueError('max_participation must be <= 1')
    _keys(inputs['costs'], {'spread_bps', 'slippage_bps', 'fee_bps', 'fixed_fee'}, 'costs')
    costs = {key: _number(value, key) for key, value in inputs['costs'].items()}
    impact = (costs['spread_bps'] / 2 + costs['slippage_bps']) / 10000
    fee_rate = costs['fee_bps'] / 10000
    if impact >= 1 or fee_rate >= 1:
        raise ValueError('half spread plus slippage and fee_bps must each be below 10000 bps')
    for field in ('bars', 'signals'):
        if type(inputs[field]) is not list or len(inputs[field]) > 100000:
            raise ValueError(f'{field} must be a list with at most 100000 entries')
    if not inputs['bars']:
        raise ValueError('at least one bar is required')
    by_close, events, previous_close = {}, [], None
    for i, raw in enumerate(inputs['bars']):
        _keys(raw, {'open_at', 'close_at', 'available_at', 'open', 'close', 'volume'}, f'bar {i}')
        bar = {key: _time(raw[key], key) for key in ('open_at', 'close_at', 'available_at')}
        bar.update({key: _number(raw[key], key, key != 'volume') for key in ('open', 'close', 'volume')})
        if not bar['open_at'] < bar['close_at'] <= bar['available_at'] <= cutoff:
            raise ValueError('bar requires open_at < close_at <= available_at <= as_of')
        if previous_close is not None and bar['open_at'] < previous_close:
            raise ValueError('bars must be chronological and nonoverlapping')
        previous_close = bar['close_at']
        by_close[bar['close_at']] = bar
        events.append((bar['open_at'], 1, i, 'open', bar))
        events.append((bar['available_at'], -1, i, 'mark', bar))
    previous_signal = None
    for i, raw in enumerate(inputs['signals']):
        _keys(raw, {'timestamp', 'available_at', 'side', 'quantity'}, f'signal {i}')
        timestamp = _time(raw['timestamp'], 'signal timestamp')
        available = _time(raw['available_at'], 'signal available_at')
        if timestamp not in by_close or not by_close[timestamp]['available_at'] <= available <= cutoff:
            raise ValueError('signal must reference a bar close and satisfy full bar availability <= signal availability <= as_of')
        if previous_signal is not None and timestamp <= previous_signal:
            raise ValueError('signal timestamps must be unique and increasing')
        previous_signal = timestamp
        if raw['side'] not in ('buy', 'sell'):
            raise ValueError('signal side must be buy or sell')
        quantity = _number(raw['quantity'], 'signal quantity', True)
        if quantity % step:
            raise ValueError('signal quantity must be a multiple of quantity_step')
        signal = dict(order_id=i + 1, timestamp=timestamp, available_at=available,
                      side=raw['side'], quantity=quantity)
        events.append((available, 0, i, 'signal', signal))
    events.sort(key=lambda event: event[:3])
    position, total_fees = Decimal(0), Decimal(0)
    pending, latest_mark, latest_volume = None, None, None
    fills, journal, marks = [], [], []

    def cancel(at, reason):
        nonlocal pending
        if pending is not None:
            journal.append({'event': 'cancel', 'at': _stamp(at), 'order_id': pending['order_id'],
                            'remaining': _text(pending['remaining']), 'reason': reason})
            pending = None

    def floor_step(value):
        return (value / step).to_integral_value(rounding=ROUND_FLOOR) * step

    for at, _, _, kind, payload in events:
        if kind == 'signal':
            cancel(at, 'replaced_by_new_signal')
            pending = dict(payload, remaining=payload['quantity'])
            journal.append({'event': 'submit', 'at': _stamp(at), 'order_id': pending['order_id'],
                            'side': pending['side'], 'quantity': _text(pending['quantity'])})
        elif kind == 'mark':
            # A delayed older bar must not replace a more recent observation.
            if latest_mark is None or payload['close_at'] > latest_mark['close_at']:
                latest_mark = payload
                marks.append({'observed_at': _stamp(at), 'price_at': _stamp(payload['close_at']),
                              'cash': _text(cash), 'position': _text(position),
                              'equity': _text(cash + position * payload['close'])})
            if latest_volume is None or payload['close_at'] > latest_volume['close_at']:
                latest_volume = payload
        elif pending is not None and at > pending['timestamp'] and at > pending['available_at']:
            prior = latest_volume
            capacity = Decimal(0) if prior is None else floor_step(prior['volume'] * participation)
            buying = pending['side'] == 'buy'
            price = payload['open'] * (1 + impact if buying else 1 - impact)
            quantity = min(pending['remaining'], capacity)
            if buying:
                affordable = max(Decimal(0), cash - costs['fixed_fee']) / (price * (1 + fee_rate))
                quantity = min(quantity, floor_step(affordable))
            else:
                quantity = min(quantity, position)
                if cash + quantity * price * (1 - fee_rate) < costs['fixed_fee']:
                    quantity = Decimal(0)
            if quantity > 0:
                fee = quantity * price * fee_rate + costs['fixed_fee']
                cash += -quantity * price - fee if buying else quantity * price - fee
                position += quantity if buying else -quantity
                pending['remaining'] -= quantity
                total_fees += fee
                if cash < 0 or position < 0:
                    raise ArithmeticError('cash or long-only invariant violated')
                fill = {'order_id': pending['order_id'], 'at': _stamp(at), 'side': pending['side'],
                        'quantity': _text(quantity), 'price': _text(price), 'fee': _text(fee),
                        'cash': _text(cash), 'position': _text(position),
                        'liquidity_reference_close': _stamp(prior['close_at'])}
                fills.append(fill)
                journal.append(dict(fill, event='modeled_fill'))
            if pending['remaining'] == 0:
                pending = None
            elif inputs['time_in_force'] == 'cancel':
                cancel(at, 'first_eligible_open_remainder')
    final_mark = latest_mark['close']
    pending_output = None if pending is None else {
        'order_id': pending['order_id'], 'side': pending['side'],
        'remaining': _text(pending['remaining']), 'available_at': _stamp(pending['available_at'])}
    return {'schema_version': 1, 'engine': 'original_costed_bar_replay_v1', 'status': 'modeled',
            'production_qualified': False, 'as_of': _stamp(cutoff), 'currency': inputs['currency'],
            'asset_class': inputs['asset_class'], 'initial_cash': _text(initial_cash),
            'cash': _text(cash), 'position': _text(position), 'final_mark': _text(final_mark),
            'equity': _text(cash + position * final_mark), 'total_fees': _text(total_fees),
            'pending_order': pending_output, 'fills': fills, 'journal': journal, 'marks': marks,
            'assumptions': ['One instrument; long-only; immediate cash settlement; zero initial position.',
                'Signals replace pending remainder on arrival; opens strictly after source close and signal availability only.',
                'Open quotes assumed observable at open_at; available_at denotes complete-bar availability.',
                'Capacity uses latest available completed bar volume, not observed opening liquidity.',
                'Buy/sell price is open plus/minus half spread and slippage; fixed fee per nonzero fill.',
                '120-digit HALF_EVEN Decimal arithmetic with explicit context; quantity rounded down to step.',
                'Amounts share the stated currency; no currency/tick rounding or currency conversion.',
                'No shorts, margin, actions, funding, impact, queues, exchange calendars, broker or live execution.']}


def _load_json(text):
    import json
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError('duplicate JSON key: ' + key)
            result[key] = value
        return result
    def invalid(value):
        raise ValueError('nonfinite JSON literal: ' + value)
    return json.loads(text, object_pairs_hook=pairs, parse_constant=invalid)


if __name__ == '__main__':
    import argparse
    import json
    from pathlib import Path
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input', help='JSON document path')
    args = parser.parse_args()
    result = simulate(_load_json(Path(args.input).read_text(encoding='utf-8')))
    print(json.dumps(result, indent=2, allow_nan=False))
