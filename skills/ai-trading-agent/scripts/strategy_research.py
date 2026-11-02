"""Explicit offline strategy identities; causal long/cash simulation and baseline adapter."""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import inspect
import json
import math
from pathlib import Path
from datetime import timedelta

import strategy_lab
from quant_common import digest, integer, require, scalar
from price_audit import timestamp
from report_facts import local_path, strict_json

ROOT = Path(__file__).resolve().parents[1]
DUAL_ID = 'dual-sma-long-cash-1'
OPENING_ID = 'strategy-lab-opening-range-breakout-1'


def implementation_hash():
    return digest({name: (ROOT / 'scripts' / name).read_text(encoding='utf-8')
                   for name in ('strategy_research.py', 'strategy_lab.py', 'quant_common.py',
                                'price_audit.py', 'risk_engine.py', 'report_facts.py')})


def csv_rows(raw):
    rows = list(csv.DictReader(io.StringIO(raw.decode('utf-8-sig'))))
    for row in rows:
        for field in ('open', 'high', 'low', 'close', 'volume'):
            row[field] = float(row[field])
    return rows


def checked_bars(rows, as_of, daily=False):
    require(isinstance(rows, list) and rows, 'BARS_REQUIRED')
    cutoff, parsed = timestamp(as_of), []
    sessions = set()
    for row in rows:
        require(isinstance(row, dict), 'BAR_OBJECT_REQUIRED')
        values = [scalar(row[k], k, minimum=0) for k in ('open', 'high', 'low', 'close', 'volume')]
        o, h, low, close, volume = values
        require(min(o, h, low, close) > 0 and low <= min(o, close) <= max(o, close) <= h,
                'INCONSISTENT_OHLC')
        end, start, finish = [timestamp(row[k]) for k in ('timestamp', 'session_open', 'session_close')]
        require(start < end <= finish and end <= cutoff, 'BAR_TIME_OR_CUTOFF')
        require(not parsed or end > parsed[-1].end, 'ORDERED_UNIQUE_BARS_REQUIRED')
        require(str(row.get('synthetic', 'false')).lower() in ('false', '0', ''), 'SYNTHETIC_BAR_MARKER')
        if daily:
            require(end == finish and start not in sessions, 'ONE_COMPLETED_BAR_PER_SESSION_REQUIRED')
            require(not parsed or start >= parsed[-1].end, 'OVERLAPPING_DAILY_SESSIONS')
        sessions.add(start)
        parsed.append(strategy_lab.Bar(end, start, finish, *values))
    return parsed


def dual_sma(bars, as_of, fast=20, slow=60, initial_cash=1.0,
             cost_per_side_bps=10, delay_bars=0, capital_fraction=1.0,
             terminal_policy='mark', initial_signal_policy='enter_if_above',
             missed_entry_signal_indices=None, data_kind='supplied_unverified'):
    """Trailing dual-SMA crossings; fractional long/cash; fill at open after 1+delay bars.

    A queued target-state order stays scheduled, even if another crossing occurs
    before its fill; all crossings are queued in causal order. An absent/illiquid
    due bar produces an unfilled order, never a clamped or postponed fill. Equality
    is neutral. The first complete slow window can enter if explicitly configured.
    """
    parsed = checked_bars(bars, as_of, daily=True)
    integer(fast, 'fast', 1); integer(slow, 'slow', fast + 1)
    integer(delay_bars, 'delay_bars', 0)
    initial_cash = scalar(initial_cash, 'initial_cash', minimum=0)
    require(initial_cash > 0, 'POSITIVE_INITIAL_CASH_REQUIRED')
    fee = scalar(cost_per_side_bps, 'cost_per_side_bps', 0, 9999) / 10000
    capital_fraction = scalar(capital_fraction, 'capital_fraction', 0, 1)
    require(capital_fraction > 0, 'POSITIVE_CAPITAL_FRACTION_REQUIRED')
    require(terminal_policy in ('mark', 'liquidate_last_close'), 'TERMINAL_POLICY_REQUIRED')
    require(initial_signal_policy in ('enter_if_above', 'cross_only'), 'INITIAL_SIGNAL_POLICY_REQUIRED')
    require(isinstance(data_kind, str) and data_kind, 'DATA_KIND_REQUIRED')
    missed = [] if missed_entry_signal_indices is None else missed_entry_signal_indices
    require(isinstance(missed, list) and len(set(missed)) == len(missed), 'UNIQUE_MISSED_SIGNAL_INDICES')
    for index in missed:
        integer(index, 'missed_entry_signal_index', 0, len(parsed) - 1)
    parameters = {'fast': fast, 'slow': slow, 'initial_cash': initial_cash,
                  'cost_per_side_bps': cost_per_side_bps, 'delay_bars': delay_bars,
                  'capital_fraction': capital_fraction, 'terminal_policy': terminal_policy,
                  'initial_signal_policy': initial_signal_policy,
                  'missed_entry_signal_indices': missed, 'data_kind': data_kind}
    cash, quantity, peak, max_dd, fees = initial_cash, 0.0, initial_cash, 0.0, 0.0
    orders, fills, decisions, curve = [], [], [], []
    previous_spread = None
    position_cost = 0.0
    realized = 0.0

    def fill(action, price, at, index, reason, signal_index=None):
        nonlocal cash, quantity, fees, position_cost, realized
        if action == 'enter':
            if quantity > 0:
                return 'ALREADY_LONG'
            value = cash * capital_fraction / (1 + fee)
            units, charge = value / price, value * fee
            cash -= value + charge
            quantity, position_cost = units, value + charge
        else:
            if quantity == 0:
                return 'ALREADY_CASH'
            units, value = quantity, quantity * price
            charge = value * fee
            cash += value - charge
            realized += value - charge - position_cost
            quantity, position_cost = 0.0, 0.0
        fees += charge
        fills.append({'action': action, 'bar_index': index, 'at': at.isoformat(),
                      'signal_index': signal_index, 'price': price, 'quantity': units,
                      'notional': value, 'fee': charge, 'reason': reason,
                      'cash_after': cash, 'quantity_after': quantity})
        return 'FILLED'

    for i, bar in enumerate(parsed):
        # Only previously completed closes can have created these orders.
        for order in orders:
            if order['due_index'] == i:
                if order['action'] == 'enter' and order['signal_index'] in missed:
                    order['status'] = 'MISSED_ENTRY_SCENARIO'
                elif bar.volume <= 0:
                    order['status'] = 'UNFILLED_NO_VOLUME'
                else:
                    order['status'] = fill(order['action'], bar.open, bar.session_open, i,
                                           'scheduled_next_open', order['signal_index'])
        if i + 1 >= slow:
            fast_mean = math.fsum(b.close for b in parsed[i-fast+1:i+1]) / fast
            slow_mean = math.fsum(b.close for b in parsed[i-slow+1:i+1]) / slow
            spread = fast_mean - slow_mean
            action = None
            if previous_spread is None:
                if spread > 0 and initial_signal_policy == 'enter_if_above':
                    action = 'enter'
            elif spread > 0 and previous_spread <= 0:
                action = 'enter'
            elif spread < 0 and previous_spread >= 0:
                action = 'exit'
            decisions.append({'bar_index': i, 'decision_at': bar.end.isoformat(),
                              'fast_mean': fast_mean, 'slow_mean': slow_mean, 'action': action})
            if action:
                orders.append({'signal_index': i, 'decision_at': bar.end.isoformat(), 'action': action,
                               'due_index': i + 1 + delay_bars, 'status': 'PENDING'})
            previous_spread = spread
        # A predeclared end-of-sample liquidation is modeled at last close, not
        # a close-signal order filled at the same close. Its fee enters this mark.
        if i == len(parsed) - 1 and quantity and terminal_policy == 'liquidate_last_close':
            if bar.volume > 0:
                fill('exit', bar.close, bar.end, i, 'predeclared_terminal_close')
            else:
                orders.append({'signal_index': None, 'due_index': i, 'action': 'terminal_exit',
                               'status': 'UNFILLED_NO_VOLUME'})
        equity = cash + quantity * bar.close
        peak = max(peak, equity)
        max_dd = max(max_dd, 1 - equity / peak)
        curve.append({'timestamp': bar.end.isoformat(), 'cash': cash, 'quantity': quantity,
                      'close': bar.close, 'equity': equity, 'fees_cumulative': fees})
    for order in orders:
        if order['status'] == 'PENDING':
            order['status'] = 'UNFILLED_BEYOND_DATA'
    final = curve[-1]['equity']
    return {'status': 'SIMULATED', 'strategy_id': DUAL_ID, 'implementation_sha256': implementation_hash(),
            'bars_sha256': digest(bars), 'input_sha256': digest({'bars': bars, 'as_of': as_of, **parameters}),
            'as_of': as_of, 'parameters': parameters, 'signals': decisions, 'orders': orders, 'fills': fills,
            'signal_history_status': 'READY' if len(parsed) >= slow else 'INSUFFICIENT_SIGNAL_HISTORY',
            'equity_curve': curve, 'final_equity': final, 'total_return': final / initial_cash - 1,
            'max_drawdown': max_dd, 'total_fees': fees, 'realized_pnl': realized,
            'unrealized_pnl': quantity * parsed[-1].close - position_cost,
            'open_quantity': quantity, 'cash': cash,
            'accounting_residual': final - initial_cash - realized - (quantity * parsed[-1].close - position_cost),
            'assumptions': {'direction': 'long_or_cash_only', 'sizing': 'fractional shares; no leverage',
                            'signal': 'completed-close trailing fast/slow SMA crossing; equality neutral',
                            'fill': 'provided daily bar open at decision index + 1 + delay; no clamping',
                            'pending_orders': 'causal target-state queue; later crossings do not cancel earlier scheduled orders',
                            'drawdown_basis': 'every completed bar equity including cash, marked position and paid entry/exit fees',
                            'price_basis': 'supplied OHLC; no dividend, split, settlement, depth or borrowing model'},
            'limitations': ['Supplied sessions and observations are not authenticated; missing sessions are not reconstructed.',
                           'Explicit costs are modeled per-side notional fees, not observed broker fills.',
                           'Terminal close liquidation is a declared boundary assumption and can affect results.'],
            'execution_authorized': False}


def dual_sma_variants(bars, as_of, variants, initial_cash=1.0, terminal_policy='mark',
                      initial_signal_policy='enter_if_above', data_kind='supplied_unverified'):
    require(isinstance(variants, list) and variants, 'VARIANTS_REQUIRED')
    require(all(isinstance(v, dict) and isinstance(v.get('id'), str) and v['id'] for v in variants), 'VARIANT_IDS_REQUIRED')
    require(len({v['id'] for v in variants}) == len(variants), 'UNIQUE_VARIANT_IDS')
    permitted = {'id', 'fast', 'slow', 'cost_per_side_bps', 'delay_bars', 'capital_fraction', 'missed_entry_signal_indices'}
    runs = []
    for variant in variants:
        arguments = {'bars': bars, 'as_of': as_of, 'initial_cash': initial_cash,
                     'terminal_policy': terminal_policy, 'initial_signal_policy': initial_signal_policy,
                     'data_kind': data_kind, **{k: v for k, v in variant.items() if k != 'id'}}
        declared_parameters = {k: v for k, v in arguments.items() if k not in ('bars', 'as_of')}
        try:
            require(not set(variant) - permitted, 'UNSUPPORTED_VARIANT_PARAMETER')
            bound = inspect.signature(dual_sma).bind(**arguments)
            bound.apply_defaults()
            declared_parameters = {k: v for k, v in bound.arguments.items() if k not in ('bars', 'as_of')}
            result = dual_sma(**arguments)
            declared_parameters = result['parameters']
        except (ValueError, KeyError, TypeError, OverflowError) as exc:
            result = {'status': 'REJECTED_INPUT', 'reason': type(exc).__name__ + ':' + str(exc),
                      'parameters': declared_parameters}
        baseline = runs[0]['parameters'] if runs else declared_parameters
        changed = {k: {'baseline': baseline[k], 'variant': value}
                   for k, value in declared_parameters.items() if k in baseline and value != baseline[k]}
        for k in sorted(set(baseline) ^ set(declared_parameters)):
            changed[k] = {'baseline': baseline.get(k), 'variant': declared_parameters.get(k),
                          'baseline_present': k in baseline, 'variant_present': k in declared_parameters}
        runs.append({'id': variant['id'], 'result': result, 'parameters': declared_parameters, 'changed_parameters': changed,
                     'comparison': 'BASELINE' if not runs else 'ONE_PARAMETER_CHANGED' if len(changed) == 1
                                   else 'MULTIPLE_PARAMETERS_CHANGED' if changed else 'IDENTICAL_PARAMETERS',
                     'effect_attribution': 'No isolated parameter attribution when multiple parameters change; no winner selection.'})
    computed = sum(r['result']['status'] == 'SIMULATED' for r in runs)
    return {'status': 'SIMULATED' if computed == len(runs) else 'PARTIAL_ANALYSIS' if computed else 'NO_COMPUTED_JOBS',
            'computed_variants': computed, 'declared_variants': len(runs),
            'strategy_id': DUAL_ID, 'implementation_sha256': implementation_hash(),
            'bars_sha256': digest(bars), 'baseline_id': variants[0]['id'], 'runs': runs,
            'selection': 'ALL_DECLARED_VARIANTS_RETAINED_NO_OPTIMIZATION', 'execution_authorized': False}


def opening_range(bars, as_of, initial_cash=100000, risk_fraction=.001, capital_fraction=.05,
                  slippage_bps=5, fee_per_share=.005, opening_bars=3, bar_minutes=5,
                  trade_start=0, data_kind='supplied_unverified'):
    parsed = checked_bars(bars, as_of)
    integer(opening_bars, 'opening_bars', 1); integer(bar_minutes, 'bar_minutes', 1)
    integer(trade_start, 'trade_start', 0, len(parsed) - 1)
    scalar(initial_cash, 'initial_cash', 0); require(initial_cash > 0, 'POSITIVE_INITIAL_CASH_REQUIRED')
    for key, value in (('risk_fraction', risk_fraction), ('capital_fraction', capital_fraction)):
        scalar(value, key, 0, 1); require(value > 0, 'POSITIVE_FRACTION_REQUIRED')
    scalar(slippage_bps, 'slippage_bps', 0, 9999)
    scalar(fee_per_share, 'fee_per_share', 0)
    require(isinstance(data_kind, str) and data_kind, 'DATA_KIND_REQUIRED')
    step = timedelta(minutes=bar_minutes)
    for i, bar in enumerate(parsed):
        require(bar.end - step >= bar.session_open, 'BAR_INTERVAL_BEFORE_SESSION_OPEN')
        require(not i or bar.end - step >= parsed[i-1].end, 'OVERLAPPING_BAR_INTERVALS')
    parameters = dict(initial_cash=initial_cash, risk_fraction=risk_fraction, capital_fraction=capital_fraction,
                      slippage_bps=slippage_bps, fee_per_share=fee_per_share,
                      opening_bars=opening_bars, bar_minutes=bar_minutes, trade_start=trade_start)
    result = strategy_lab.replay(parsed, 'opening_range_breakout', **parameters)
    return {'status': 'SIMULATED', 'strategy_id': OPENING_ID, 'implementation_sha256': implementation_hash(),
            'bars_sha256': digest(bars), 'input_sha256': digest({'bars': bars, 'as_of': as_of, **parameters, 'data_kind': data_kind}),
            'as_of': as_of, 'data_kind': data_kind, 'parameters': parameters, 'result': result,
            'fixed_rules': {'opening_range': 'first opening_bars completed bars at bar_minutes cadence',
                            'entry': 'upward range crossover, 1.5x opening volume; next eligible bar open',
                            'direction': 'long_only', 'stop_target_ordering': 'stop_first',
                            'target_reward_multiple': 2.5, 'last_entry_buffer_minutes': 30,
                            'session_exit_buffer_minutes': 10, 'terminal_policy': 'mark_unsold_position'},
            'limitation': 'Exact existing strategy_lab baseline; OHLC cannot establish intrabar ordering, queue position or observed fills.',
            'execution_authorized': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=('dual-sma', 'variants', 'opening-range'))
    parser.add_argument('csv'); parser.add_argument('parameters')
    parser.add_argument('--private-output', required=True)
    args = parser.parse_args()
    try:
        source, params, output = map(local_path, (args.csv, args.parameters, args.private_output))
        require(not output.is_relative_to(ROOT), 'OUTPUT_OUTSIDE_SKILL_REQUIRED')
        raw, parameters_raw = source.read_bytes(), params.read_bytes()
        parameters = strict_json(parameters_raw)
        require(isinstance(parameters, dict) and 'bars' not in parameters, 'PARAMETER_OBJECT_REQUIRED')
        function = {'dual-sma': dual_sma, 'variants': dual_sma_variants, 'opening-range': opening_range}[args.operation]
        result = function(csv_rows(raw), **parameters)
        bundle = {'operation': args.operation, 'source_csv_sha256': hashlib.sha256(raw).hexdigest(),
                  'parameters_file_sha256': hashlib.sha256(parameters_raw).hexdigest(),
                  'parameters': parameters, 'result': result, 'result_sha256': digest(result)}
        with output.open('x', encoding='utf-8') as handle:
            json.dump(bundle, handle, indent=2, allow_nan=False)
            handle.write('\n')
    except (ValueError, KeyError, TypeError, OSError, OverflowError):
        parser.exit(2, 'Strategy research failed: invalid inputs, unavailable local file or existing output. No private values were printed.\n')


if __name__ == '__main__':
    main()
