"""Point-in-time, long-only follower targets and cash-funded proposals. No I/O."""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal, ROUND_FLOOR
import json


def _need(ok, message):
    if not ok:
        raise ValueError(message)


def _number(value, name, minimum=Decimal('0')):
    _need(not isinstance(value, bool), 'INVALID_NUMBER:' + name)
    try:
        result = Decimal(str(value))
    except Exception as exc:
        raise ValueError('INVALID_NUMBER:' + name) from exc
    _need(result.is_finite() and result >= minimum, 'INVALID_NUMBER:' + name)
    return result


def _time(value):
    result = datetime.fromisoformat(value.replace('Z', '+00:00'))
    _need(result.tzinfo is not None, 'TIMEZONE_REQUIRED')
    return result.astimezone(timezone.utc)


def _weights(value):
    _need(isinstance(value, dict), 'WEIGHTS_OBJECT_REQUIRED')
    result = {str(k): _number(v, 'weight') for k, v in value.items()}
    _need(all(result) and sum(result.values()) <= 1, 'INVALID_WEIGHTS')
    return result


def _latest(records, subject, as_of):
    """Revision chosen by availability first; withdrawn latest never falls back."""
    groups = defaultdict(list)
    for row in records:
        _need(row['subject_id'] == subject and bool(row['event_id']) and bool(row['source_ref']),
              'EVENT_IDENTITY_REQUIRED')
        _need(type(row['revision']) is int and row['revision'] >= 0, 'INVALID_REVISION')
        _need(type(row['withdrawn']) is bool, 'WITHDRAWN_BOOLEAN_REQUIRED')
        event, published, available = (_time(row[x]) for x in ('event_at', 'published_at', 'available_at'))
        _need(event <= published <= available, 'INVALID_INFORMATION_CLOCKS')
        if available <= as_of:
            groups[row['event_id']].append(row)
    result = []
    for key, rows in groups.items():
        # A lower revision arriving later must not replace a correction.
        revision = max(row['revision'] for row in rows)
        selected = [row for row in rows if row['revision'] == revision]
        unique = {json.dumps(row, sort_keys=True, allow_nan=False) for row in selected}
        _need(len(unique) == 1, 'CONFLICTING_REVISION:' + key)
        result.append(selected[0])
    return sorted(result, key=lambda row: (_time(row['event_at']), row['event_id']))


def build_targets(document):
    """Build sleeve and aggregated targets; uncertain sleeves preserve baselines."""
    as_of = _time(document['as_of'])
    _need(document['currency'] == 'USD', 'ONLY_USD_SUPPORTED')
    cap = _number(document['max_position_weight'], 'max_position_weight')
    _need(0 < cap <= 1, 'INVALID_POSITION_CAP')
    sleeves = document['sleeves']
    _need(isinstance(sleeves, list) and sleeves, 'SLEEVES_REQUIRED')
    _need(len({s['id'] for s in sleeves}) == len(sleeves), 'DUPLICATE_SLEEVE')
    budgets = [_number(s['budget_weight'], 'budget_weight') for s in sleeves]
    _need(all(b > 0 for b in budgets) and sum(budgets) <= 1, 'INVALID_SLEEVE_BUDGETS')
    combined, frozen, outputs, warnings = defaultdict(Decimal), set(), [], []
    scope = set()
    for sleeve, budget in zip(sleeves, budgets):
        current = _weights(sleeve['current_weights'])
        weights, local_frozen = dict(current), set()
        mode = sleeve['mode']
        _need(mode in ('snapshot', 'events', 'inverse'), 'UNKNOWN_FOLLOWER_MODE')
        age = _number(sleeve['max_age_days'], 'max_age_days')
        checked = _time(sleeve['checked_at'])
        _need(checked <= as_of, 'FUTURE_SOURCE_CHECK')
        ready = sleeve['source_status'] == 'verified' and Decimal(str((as_of - checked).total_seconds())) <= age * 86400
        reasons = []
        rows = []
        if ready:
            try:
                rows = _latest(sleeve.get('records', []), sleeve['subject_id'], as_of)
            except ValueError as error:
                if str(error).startswith('CONFLICTING_REVISION:'):
                    ready = False
                    reasons.append(str(error))
                else:
                    raise
        if not ready:
            local_frozen.update(current)
            reasons.append('SOURCE_UNAVAILABLE_OR_STALE_KEEP_EXISTING')
        elif mode == 'snapshot':
            if not rows:
                local_frozen.update(current)
                reasons.append('NO_AVAILABLE_SNAPSHOT_KEEP_EXISTING')
            else:
                newest_time = max(_time(row['event_at']) for row in rows)
                newest = [row for row in rows if _time(row['event_at']) == newest_time]
                row = newest[0]
                stale = Decimal(str((as_of - newest_time).total_seconds())) > age * 86400
                if len(newest) != 1 or row['withdrawn'] or stale or row.get('complete_reported_basket') is not True:
                    local_frozen.update(current)
                    reasons.append('SNAPSHOT_AMBIGUOUS_WITHDRAWN_STALE_OR_INCOMPLETE_KEEP_EXISTING')
                else:
                    _need(row['currency'] == document['currency'], 'SNAPSHOT_CURRENCY_MISMATCH')
                    values = defaultdict(Decimal)
                    for position in row['positions']:
                        if position.get('asset_type') == 'common_stock' and position.get('eligible_common') is True:
                            values[position['security_id']] += _number(position['market_value'], 'market_value')
                    total = sum(values.values())
                    if not total:
                        local_frozen.update(current)
                        reasons.append('EMPTY_ELIGIBLE_BASKET_KEEP_EXISTING')
                    else:
                        weights = {key: value / total for key, value in values.items()}
                        reasons.append('REPORTED_COMMON_STOCK_BASKET_ONLY_CASH_HEDGES_AND_OTHER_ASSETS_UNKNOWN')
        else:
            policy = sleeve['allocation_policy']
            _need(policy in (('user_weights', 'active_equal') if mode == 'inverse' else ('user_weights',)), 'EXPLICIT_ALLOCATION_POLICY_REQUIRED')
            configured = _weights(sleeve.get('user_weights', {}))
            partial_policy = sleeve['partial_sell_policy']
            _need(partial_policy in ('hold', 'exit'), 'EXPLICIT_PARTIAL_SELL_POLICY_REQUIRED')
            by_security = defaultdict(list)
            for row in rows:
                security = row['security_id']
                scope.add(security)
                by_security[security].append(row)
            for security, events in by_security.items():
                events = [row for row in events if Decimal(str((as_of - _time(row['event_at'])).total_seconds())) <= age * 86400]
                if not events:
                    local_frozen.add(security)
                    reasons.append('EXPIRED_ECONOMIC_SIGNAL_KEEP_EXISTING:' + security)
                    continue
                grouped = defaultdict(list)
                for row in events:
                    grouped[_time(row['event_at'])].append(row)
                ambiguous = any(len({(r['action'], r.get('sale_scope'), r['withdrawn']) for r in rs}) > 1 for rs in grouped.values())
                if ambiguous or any(r['withdrawn'] for r in events):
                    local_frozen.add(security)
                    reasons.append('CONFLICT_OR_WITHDRAWAL_KEEP_EXISTING:' + security)
                    continue
                for row in events:
                    _need(row['action'] in ('BUY', 'SELL'), 'UNSUPPORTED_ACTION')
                    if row.get('eligible_common') is not True or row.get('qualifying') is not True:
                        continue
                    if mode == 'inverse':
                        if row['action'] == 'BUY':
                            weights.pop(security, None)
                        elif policy == 'active_equal':
                            weights[security] = Decimal(1)
                        else:
                            _need(security in configured, 'MISSING_USER_WEIGHT:' + security)
                            weights[security] = configured[security]
                    elif row['action'] == 'BUY':
                        _need(security in configured, 'MISSING_USER_WEIGHT:' + security)
                        weights[security] = configured[security]
                    elif row.get('sale_scope') == 'full' or (row.get('sale_scope') == 'partial' and partial_policy == 'exit'):
                        weights.pop(security, None)
                    else:
                        local_frozen.add(security)
                        reasons.append('PARTIAL_OR_UNKNOWN_SALE_KEEP_EXISTING:' + security)
            for security in local_frozen:
                if security in current:
                    weights[security] = current[security]
                else:
                    weights.pop(security, None)
            if policy == 'active_equal':
                fixed = sum((weights.get(key, Decimal(0)) for key in local_frozen), Decimal(0))
                active = [key for key, value in weights.items() if key not in local_frozen and value > 0]
                for key in active:
                    weights[key] = (1 - fixed) / len(active)
            _need(sum(weights.values()) <= Decimal('1.000000000001'), 'USER_TARGETS_EXCEED_SLEEVE')
        scope.update(current)
        scope.update(weights)
        frozen.update(local_frozen)
        for security, weight in weights.items():
            combined[security] += budget * weight
        outputs.append({'id': sleeve['id'], 'mode': mode, 'budget_weight': float(budget),
                        'weights': {k: float(v) for k, v in sorted(weights.items())},
                        'frozen_security_ids': sorted(local_frozen), 'notes': reasons})
        warnings.extend(sleeve['id'] + ':' + reason for reason in reasons)
    targets = {key: min(cap, value) for key, value in combined.items() if value > 0}
    overflow = sum(combined.values()) - sum(targets.values())
    return {'as_of': document['as_of'], 'target_weights': {k: float(v) for k, v in sorted(targets.items())},
            'target_cash_weight': float(max(Decimal(0), 1 - sum(targets.values()))), 'cap_overflow_cash_weight': float(overflow),
            'scope_security_ids': sorted(scope), 'frozen_security_ids': sorted(frozen), 'sleeves': outputs,
            'notes': warnings, 'target_basis': 'fraction_of_total_account_nav_before_trades',
            'frozen_target_note': 'Nominal capped targets are not attained for frozen securities; current holdings remain unchanged.',
            'status': 'proposed_targets_not_orders'}


def rebalance(document):
    """Conservative cash-only funding: proposed sales never fund proposed buys."""
    targets = build_targets(document['target_document'])
    as_of = _time(targets['as_of'])
    _need(document['currency'] == 'USD', 'ONLY_USD_SUPPORTED')
    _need(document['open_orders'] == [], 'RECONCILE_OPEN_ORDERS_FIRST')
    max_age = _number(document['max_quote_age_seconds'], 'max_quote_age_seconds')
    holdings_age = _number(document['max_holdings_age_seconds'], 'max_holdings_age_seconds')
    holdings_at = _time(document['holdings_at'])
    _need(0 <= Decimal(str((as_of - holdings_at).total_seconds())) <= holdings_age, 'STALE_OR_FUTURE_HOLDINGS')
    cash = _number(document['settled_cash'], 'settled_cash')
    receivables = _number(document['pending_receivables'], 'pending_receivables')
    floor = _number(document['cash_floor'], 'cash_floor')
    reserve = _number(document['reserved_cash'], 'reserved_cash')
    _need(reserve <= cash, 'RESERVED_CASH_EXCEEDS_SETTLED_CASH')
    fee = _number(document['fixed_fee_per_trade'], 'fixed_fee_per_trade')
    bps = _number(document['cost_bps'], 'cost_bps') / 10000
    _need(bps < 1, 'INVALID_COST_RATE')
    minimum = _number(document['min_trade_notional'], 'min_trade_notional')
    rows = document['holdings']
    _need(len({r['security_id'] for r in rows}) == len(rows), 'DUPLICATE_HOLDING')
    holdings, prices, steps = {}, {}, {}
    for row in rows:
        qty = _number(row['quantity'], 'quantity')
        owned = _number(row['follower_quantity'], 'follower_quantity')
        _need(owned <= qty, 'FOLLOWER_QUANTITY_EXCEEDS_HOLDING')
        holdings[row['security_id']] = (qty, owned)
    wanted = set(holdings) | set(targets['target_weights'])
    for security in sorted(wanted):
        quote = document['quotes'][security]
        _need(bool(quote['source_ref']) and quote['price_basis'] == 'unadjusted', 'OBSERVED_UNADJUSTED_QUOTE_REQUIRED')
        observed, available = _time(quote['observed_at']), _time(quote['available_at'])
        _need(observed <= available <= as_of and Decimal(str((as_of - observed).total_seconds())) <= max_age, 'STALE_OR_FUTURE_QUOTE:' + security)
        prices[security] = _number(quote['price'], 'price')
        steps[security] = _number(quote['quantity_step'], 'quantity_step')
        _need(prices[security] > 0 and steps[security] > 0, 'POSITIVE_PRICE_AND_STEP_REQUIRED')
    nav = cash + receivables + sum(qty * prices[key] for key, (qty, _) in holdings.items())
    supplied_nav = _number(document['account_nav'], 'account_nav')
    _need(nav > 0 and abs(nav - supplied_nav) <= Decimal('.01'), 'NAV_RECONCILIATION_FAILED')
    frozen = set(targets['frozen_security_ids'])
    scope = set(targets['scope_security_ids'])
    proposals, desired_buys, deferred = [], [], []
    unassigned = [key for key, (_, owned) in holdings.items() if owned > 0 and key not in scope]
    deferred.extend({'security_id': key, 'reason': 'NO_CURRENT_FOLLOWER_SCOPE_KEEP_EXISTING'} for key in sorted(unassigned))
    for security in sorted(scope):
        if security in frozen:
            deferred.append({'security_id': security, 'reason': 'FROZEN_SIGNAL_KEEP_EXISTING'})
            continue
        if security not in wanted:
            continue
        held = holdings.get(security, (Decimal(0), Decimal(0)))[1]
        desired = nav * _number(targets['target_weights'].get(security, 0), 'target_weight') / prices[security]
        delta = desired - held
        step = steps[security]
        quantity = (abs(delta) / step).to_integral_value(rounding=ROUND_FLOOR) * step
        notional = quantity * prices[security]
        if not quantity or notional < minimum:
            continue
        cost = fee + notional * bps
        if delta < 0:
            if notional <= cost:
                deferred.append({'security_id': security, 'reason': 'SALE_COST_EXCEEDS_PROCEEDS'})
            else:
                proposals.append({'security_id': security, 'action': 'SELL', 'quantity': str(quantity),
                                  'estimated_notional': str(notional), 'estimated_cost': str(cost),
                                  'estimated_unsettled_proceeds': str(notional - cost)})
        else:
            desired_buys.append((security, quantity, notional))
    available_cash = max(Decimal(0), cash - floor - reserve)
    variable_cost = sum(n * (1 + bps) for _, _, n in desired_buys)
    factor = min(Decimal(1), max(Decimal(0), available_cash - fee * len(desired_buys)) / variable_cost) if variable_cost else Decimal(0)
    spent = Decimal(0)
    for security, desired, _ in desired_buys:
        quantity = (desired * factor / steps[security]).to_integral_value(rounding=ROUND_FLOOR) * steps[security]
        notional = quantity * prices[security]
        if not quantity or notional < minimum:
            deferred.append({'security_id': security, 'reason': 'CASH_FLOOR_COST_ROUNDING_OR_MINIMUM'})
            continue
        cost = fee + notional * bps
        spent += notional + cost
        proposals.append({'security_id': security, 'action': 'BUY', 'quantity': str(quantity),
                          'estimated_notional': str(notional), 'estimated_cost': str(cost)})
        if quantity < desired:
            deferred.append({'security_id': security, 'reason': 'PARTIALLY_FUNDED_TARGET'})
    _need(spent <= available_cash, 'INTERNAL_CASH_CONSERVATION_FAILED')
    sales = sum(Decimal(p['estimated_unsettled_proceeds']) for p in proposals if p['action'] == 'SELL')
    return {'targets': targets, 'account_nav': str(nav), 'proposals': proposals, 'deferred': deferred,
            'buy_funding_policy': 'pro_rata_from_settled_cash_only_no_sale_proceeds',
            'available_cash_for_buys': str(available_cash), 'estimated_buy_cash_use': str(spent),
            'settled_cash_if_buys_fill': str(cash - spent), 'estimated_new_unsettled_sale_proceeds': str(sales),
            'existing_pending_receivables_not_spendable': str(receivables),
            'cash_floor_shortfall_before_trades': str(max(Decimal(0), floor + reserve - cash)),
            'notes': ['Targets are pretrade intentions; feasible proposals do not promise the final target allocation.',
                      'Costs are supplied estimates. Taxes, slippage and actual fills are not calculated.',
                      'Only declared follower_quantity can be sold; unrelated quantities remain untouched.',
                      'Frozen overlapping securities stay unchanged even when another sleeve has a fresh signal.'],
            'status': 'proposals_only_no_orders_submitted'}


if __name__ == '__main__':
    import argparse
    import hashlib
    from pathlib import Path
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input', type=Path)
    arguments = parser.parse_args()
    payload = json.loads(arguments.input.read_text(encoding='utf-8-sig'))
    operations = {'build_targets': build_targets, 'rebalance': rebalance}
    _need(payload['operation'] in operations, 'UNKNOWN_OPERATION')
    output = operations[payload['operation']](**payload['inputs'])
    output['input_sha256'] = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode()).hexdigest()
    output['implementation_sha256'] = hashlib.sha256(Path(__file__).read_bytes().replace(b'\r\n', b'\n')).hexdigest()
    print(json.dumps(output, indent=2, allow_nan=False))
