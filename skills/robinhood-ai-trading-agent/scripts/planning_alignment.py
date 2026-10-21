"""Explicit offline cash, trade-cost and portfolio calculation contracts.

Money and share calculations use Decimal and serialize as decimal strings. These
are supplied observations/scenarios, never broker availability or execution gates.
"""
from copy import deepcopy
from datetime import date, datetime, time, timedelta, timezone
from decimal import Context, Decimal, ROUND_CEILING, ROUND_FLOOR, localcontext
from fractions import Fraction
import math
import re
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import accounting_tools
import investment_ops
import portfolio_analytics
from quant_common import digest, require, timestamp


def amount(value, name='amount', minimum=None):
    require(not isinstance(value, bool) and isinstance(value, (int, float, str, Decimal)), 'NUMERIC_' + name)
    try:
        result = Decimal(str(value))
    except Exception as exc:
        raise ValueError('NUMERIC_' + name) from exc
    require(result.is_finite(), 'FINITE_' + name)
    require(minimum is None or result >= Decimal(str(minimum)), 'RANGE_' + name)
    return result


def fraction(value, name='fraction'):
    result = amount(value, name, 0)
    require(result <= 1, 'FRACTION_' + name)
    return result


def finish(document, method, **result):
    require(isinstance(document.get('currency'), str) and document['currency'].strip(), 'CURRENCY_REQUIRED')
    require(document.get('role') in {'supplied_observation', 'hypothetical_scenario', 'user_assumption'}, 'INPUT_ROLE_REQUIRED')
    def currency_check(value):
        if isinstance(value,dict):
            if 'currency' in value:require(value['currency']==document['currency'],'NESTED_CURRENCY_MISMATCH_NO_FX_MODEL')
            for child in value.values():currency_check(child)
        elif isinstance(value,list):
            for child in value:currency_check(child)
    # cash_plan is the sole multi-currency operation; existing cash_ladder keeps
    # each currency map separate and disallows events in an unknown currency.
    if method!='cash-plan-contract':currency_check(document)
    def clean(value):
        if isinstance(value, Decimal):
            return str(value)
        if isinstance(value, list):
            return [clean(x) for x in value]
        if isinstance(value, dict):
            return {k: clean(v) for k, v in value.items()}
        return value
    return clean({'method': method + '-1', 'currency': document['currency'], 'input_role': document['role'],
                  'input_sha256': digest(document), 'advisory_only': True,
                  'source_authenticity_verified': False, **result})


def _cost_coefficients(costs, phase, price, orders):
    fixed, variable, detail = Decimal(0), Decimal(0), []
    require(isinstance(costs, list) and len({c['id'] for c in costs}) == len(costs), 'UNIQUE_COST_IDS')
    for row in costs:
        unit, scope = row['unit'], row['phase']
        value = amount(row['amount'], 'cost', 0)
        require(unit in {'per_share', 'per_order', 'bps_notional', 'per_round_trip'}, 'EXPLICIT_COST_UNIT_REQUIRED')
        require(scope in {'entry', 'exit', 'each_side', 'round_trip'}, 'COST_PHASE_REQUIRED')
        if unit == 'per_round_trip':
            require(scope == 'round_trip' and row.get('charged_at') in {'entry', 'exit'}, 'ROUND_TRIP_CHARGE_TIME_REQUIRED')
            applies = row['charged_at'] == phase
        else:
            require(scope != 'round_trip', 'ROUND_TRIP_COST_UNIT_REQUIRED')
            applies = scope in {phase, 'each_side'}
        if not applies:
            continue
        if unit == 'per_order':
            require(type(orders) is int and orders >= 1, 'ORDER_COUNT_REQUIRED')
            fixed += value * orders
        elif unit == 'per_round_trip':
            fixed += value
        elif unit == 'per_share':
            variable += value
        else:
            variable += price * value / 10000
        detail.append(deepcopy(row))
    return fixed, variable, detail


def trade_costs(document):
    """Quote a long round trip or one buy/sell, plus explicit cost-aware sizing.

Required: side, price, quantity, entry_orders, costs[{id,unit,phase,amount}].
    Optional exit_price/exit_orders, budget or required_net_proceeds and quantity_step.
    Standalone sells require transaction_phase=entry|exit for the declared cost rows.
Per-order charges require order counts; per-round-trip charges require charged_at.
"""
    side = document['side']; require(side in {'buy', 'sell'}, 'SIDE_REQUIRED')
    price = amount(document['price'], 'price', '0.000000000001')
    qty = amount(document['quantity'], 'quantity', 0)
    phase='entry' if side=='buy' else document.get('transaction_phase')
    require(phase in {'entry','exit'},'SALE_TRANSACTION_PHASE_REQUIRED')
    fixed, variable, detail = _cost_coefficients(document['costs'], phase, price, document['entry_orders'])
    cost = fixed + variable * qty if qty else Decimal(0)
    gross = qty * price
    result = {'status': 'COMPUTED', 'quantity': qty, 'quantity_unit': 'shares', 'gross_notional': gross,
              'entry_cost': cost if phase=='entry' else None, 'transaction_cost':cost,'applied_cost_phase':phase,
              'entry_cash_debit': gross + cost if side == 'buy' else None,
              'sale_net_proceeds': gross - cost if side == 'sell' else None,
              'entry_cost_records': detail, 'cost_basis': 'explicit amount/unit/phase; no inferred taxes or commissions'}
    if 'budget' in document:
        require(side == 'buy', 'BUDGET_REQUIRES_BUY')
        budget = amount(document['budget'], 'budget', 0)
        step = amount(document['quantity_step'], 'quantity_step', '0.000000000001')
        result.update(quantity_step=step, quantity_step_unit='shares')
        raw = max(Decimal(0), (budget - fixed) / (price + variable))
        affordable = (raw / step).to_integral_value(rounding=ROUND_FLOOR) * step
        debit = affordable * (price + variable) + (fixed if affordable else 0)
        result.update(max_affordable_quantity=affordable, affordable_cash_debit=debit,
                      budget_remainder=budget - debit, quoted_quantity_within_budget=gross + cost <= budget)
    if 'required_net_proceeds' in document:
        require(side == 'sell' and price > variable, 'POSITIVE_NET_PRICE_SALE_REQUIRED')
        needed = amount(document['required_net_proceeds'], 'required_net_proceeds', 0)
        step = amount(document['quantity_step'], 'quantity_step', '0.000000000001')
        result.update(quantity_step=step, quantity_step_unit='shares')
        raw = (needed + fixed) / (price - variable) if needed else Decimal(0)
        sized = (raw / step).to_integral_value(rounding=ROUND_CEILING) * step
        # The legacy decimal field is finite-precision, even when the exact
        # algebraic threshold is recurring. Retain a lossless rational witness.
        threshold = ((Fraction(needed) + Fraction(fixed)) /
                     (Fraction(price) - Fraction(variable))) if needed else Fraction(0)
        result['proceeds_sizing_precision'] = {
            'threshold_quantity_numerator': str(threshold.numerator),
            'threshold_quantity_denominator': str(threshold.denominator),
            'threshold_quantity_unit': 'shares',
            'decimal_quantity_pointer': '/exact_fractional_quantity_for_required_proceeds',
            'decimal_quantity_is_exact': Fraction(raw) == threshold,
            'increment_quantity_pointer': '/minimum_quantity_at_increment',
            'increment_net_proceeds_pointer': '/sized_net_proceeds',
            'required_net_proceeds': needed,
            'quantity_step': step,
            'rounding_direction_for_required_proceeds': 'ceiling_to_declared_quantity_step',
            'display_rule': 'A shortened decimal is approximate; do not label it exact or sufficient without recomputing net proceeds.',
            'broker_increment_verified': False}
        result.update(exact_fractional_quantity_for_required_proceeds=raw,
                      minimum_quantity_at_increment=sized,
                      sized_net_proceeds=sized * (price - variable) - (fixed if sized else 0),
                      quoted_quantity_meets_proceeds=gross - cost >= needed)
    if 'exit_price' in document:
        require(side == 'buy', 'LONG_ROUND_TRIP_ONLY')
        exit_price = amount(document['exit_price'], 'exit_price', 0)
        efixed, evariable, edetail = _cost_coefficients(document['costs'], 'exit', exit_price, document['exit_orders'])
        exit_cost = efixed + evariable * qty if qty else Decimal(0)
        result.update(exit_cost=exit_cost, exit_cost_records=edetail,
                      exit_net_proceeds=qty * exit_price - exit_cost,
                      gross_pnl=qty * (exit_price - price),
                      net_pnl=qty * (exit_price - price) - cost - exit_cost,
                      total_cost=cost + exit_cost)
    else:
        result['round_trip_net_pnl'] = None
    return finish(document, 'trade-cost-contract', **result)


def _cash_date_only(value):
    return isinstance(value, str) and re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2}', value) is not None


def _cash_date_interval(value, declared_zone):
    """Calendar boundaries are interval limits, never observed cash timestamps.

    Fold/gap midnights are left unresolved. Ordinary DST days use independently
    localized boundaries, so their duration may be 23 or 25 hours, not 24.
    """
    try:
        day = date.fromisoformat(value)
        following = day + timedelta(days=1)
    except (ValueError, OverflowError) as exc:
        raise ValueError('INVALID_CASH_CALENDAR_DATE') from exc
    if declared_zone is None or declared_zone == 'unknown':
        return None, 'DATE_TIMEZONE_REQUIRED'
    require(isinstance(declared_zone, str) and declared_zone.strip(), 'CALENDAR_TIMEZONE_REQUIRED_OR_UNKNOWN')
    if declared_zone in {'UTC', 'Z'}:
        zone = timezone.utc
    elif re.fullmatch(r'[+-][0-9]{2}:[0-9]{2}', declared_zone):
        hours, minutes = int(declared_zone[1:3]), int(declared_zone[4:6])
        require(hours < 24 and minutes < 60, 'CALENDAR_TIMEZONE_INVALID')
        zone = timezone((1 if declared_zone[0] == '+' else -1) * timedelta(hours=hours, minutes=minutes))
    else:
        try:
            zone = ZoneInfo(declared_zone)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError('CALENDAR_TIMEZONE_INVALID_OR_UNAVAILABLE') from exc
    boundaries = []
    for boundary_day in (day, following):
        local = datetime.combine(boundary_day, time.min)
        # A local midnight must round-trip to itself, and must have one UTC
        # interpretation. Never silently select fold=0 for an ambiguous midnight.
        candidates = {local.replace(tzinfo=zone, fold=fold).astimezone(timezone.utc)
                      for fold in (0, 1)
                      if local.replace(tzinfo=zone, fold=fold).astimezone(timezone.utc)
                      .astimezone(zone).replace(tzinfo=None) == local}
        if len(candidates) != 1:
            return None, 'LOCAL_DATE_BOUNDARY_AMBIGUOUS_OR_NONEXISTENT'
        boundaries.append(candidates.pop())
    if boundaries[1] <= boundaries[0]:
        return None, 'LOCAL_DATE_INTERVAL_NOT_ESTABLISHED'
    return tuple(boundaries), None


def _date_ambiguous_cash_plan(document):
    # Finite decimal observations can exceed the process's default precision.
    # Establish enough aligned places for every summed monetary term; a caller's
    # precision, rounding or traps must not silently alter cents or residuals.
    money = [amount(value) for name in ('settled_balances', 'reservations', 'floors')
             for value in document[name].values()]
    money += [amount(event[key]) for event in document['events']
              for key in ('amount', 'reservation_release') if key in event]
    precision = max(28, max((value.adjusted() for value in money), default=0)
                    - min((value.as_tuple().exponent for value in money), default=0)
                    + len(str(len(money) + 1)) + 4)
    with localcontext(Context(prec=precision)):
        return _date_ambiguous_cash_plan_exact(document)


def _date_ambiguous_cash_plan_exact(document):
    """Monotone cash envelopes, with explicit relaxation for unresolved dates.

    Positive flows at the earliest limits and nonpositive flows at the latest
    limits bound the most favorable path; reversing them bounds the adverse
    path. Limits at an exclusive day end are symbolic, not fabricated times.
    Missing zones relax only those events' ordering to anywhere after opening.
    """
    start = timestamp(document['as_of']).astimezone(timezone.utc)
    maps = {name: {c: amount(v, name, 0 if name != 'settled_balances' else None)
                   for c, v in document[name].items()}
            for name in ('settled_balances', 'reservations', 'floors')}
    settled, reservations, floors = (maps[name] for name in ('settled_balances', 'reservations', 'floors'))
    require(set(settled) == set(reservations) == set(floors), 'CURRENCY_MAP_MISMATCH')
    require(document['currency'] in settled, 'BASE_CURRENCY_NOT_IN_CASH_MAP')
    source = deepcopy(document['events'])
    require(len({e['id'] for e in source}) == len(source), 'DUPLICATE_CASH_EVENT')
    require(all(isinstance(e['id'], str) and e['id'].strip() for e in source), 'CASH_EVENT_ID_REQUIRED')
    prepared, ignored, missing, temporal = [], [], [], []
    release_totals = {c: Decimal(0) for c in settled}
    for event in source:
        kind, currency = event.get('kind'), event['currency']
        require(kind in {'cash_credit', 'cash_debit', 'withdrawal', 'trade_settlement', 'external_obligation'}, 'CASH_EVENT_KIND_REQUIRED')
        require(currency in settled, 'UNKNOWN_CURRENCY')
        value = amount(event['amount'], 'cash_amount')
        if kind in {'withdrawal', 'cash_debit', 'external_obligation'}:
            require(value <= 0, 'DEBIT_SIGN_REQUIRED')
        release = amount(event.get('reservation_release', 0), 'reservation_release', 0)
        require(release <= max(Decimal(0), -value), 'RELEASE_CANNOT_EXCEED_MATCHING_DEBIT')
        require(type(event.get('confirmed')) is bool, 'CONFIRMATION_FLAG_REQUIRED')
        excluded = value > 0 and not event['confirmed']
        value_at = event['available_at']
        timing = {'id': event['id'], 'source_available_at': value_at,
                  'precision': 'calendar_date' if _cash_date_only(value_at) else 'timestamp',
                  'included_in_cash_path': not excluded}
        interval, problem, exact = None, None, None
        if _cash_date_only(value_at):
            declared_zone = event.get('calendar_timezone', document.get('calendar_timezone'))
            interval, problem = _cash_date_interval(value_at, declared_zone)
            timing.update(calendar_timezone=declared_zone, interval=None,
                          observed_availability_timestamp=None)
            if interval is not None:
                low, high = interval
                timing['interval'] = {'start_inclusive': low.isoformat(), 'end_exclusive': high.isoformat(),
                                      'boundary_basis': 'Declared local calendar day; boundaries are not observed availability.'}
                require(high > start, 'FUTURE_EVENTS_ONLY_OPENING_BALANCE_ALREADY_INCLUDES_PAST')
                if low <= start:
                    problem = 'DATE_OVERLAPS_AS_OF_OPENING_INCLUSION_UNKNOWN'
            if problem:
                timing['unresolved_reason'] = problem
                if not excluded:
                    missing.append({'id': event['id'], 'reason': problem,
                                    'needed': 'Supply a timezone-aware availability timestamp strictly after as_of, or a valid calendar_timezone and evidence this event is not already included in the opening balance.'})
        else:
            exact = timestamp(value_at).astimezone(timezone.utc)
            require(exact > start, 'FUTURE_EVENTS_ONLY_OPENING_BALANCE_ALREADY_INCLUDES_PAST')
            timing['at'] = exact.isoformat()
        temporal.append(timing)
        if excluded:
            ignored.append(event['id'])
            continue
        require(event.get('evidence'), 'CASH_TIMING_EVIDENCE_REQUIRED')
        release_totals[currency] += release
        prepared.append({'source': event, 'amount': value, 'release': release,
                         'effect': value + release, 'exact': exact, 'interval': interval,
                         'timing': timing})
    require(all(release_totals[c] <= reservations[c] for c in settled), 'RESERVATION_ALREADY_RELEASED_OR_MISSING')
    opening = {c: settled[c] - reservations[c] for c in settled}
    unresolved = bool(missing)
    assumptions = [
        'Each included source event occurs exactly once after as_of and is not already included in the opening balance.',
        'All supplied later demands remain in the path, even after negative cash; negative balances describe unfunded demand, not borrowing.',
        'Date-only events may occur anywhere within their declared date interval; no particular availability time is observed.',
        'Exact timestamps stay fixed; at equal modeled instants debits precede credits, then event id breaks ties.'
    ]
    if unresolved:
        assumptions.append('For an unresolved calendar interval, ordering is relaxed to anywhere after opening, including before or after every fixed event. These are broad conditional bounds, not a verified date-feasible path. An interval overlapping as_of is conditioned on its event occurring after as_of.')

    def scenario(favorable):
        ordered = []
        for event in prepared:
            positive = event['effect'] > 0
            earliest = positive == favorable
            # Position bands: unrestricted early, established times, unrestricted
            # late. At one UTC boundary, exclusive-end limits precede exact/start
            # instants; a conditional just-after-opening limit follows opening.
            if event['exact'] is not None:
                key, placement = (1, event['exact'], 1), 'supplied_exact_timestamp'
            elif event['interval'] is None:
                key = (0 if earliest else 2, start, 0)
                placement = 'conditional_before_all_fixed_events' if earliest else 'conditional_after_all_fixed_events'
            else:
                low, high = event['interval']
                if earliest:
                    key = (1, max(low, start), 2 if low <= start else 1)
                    placement = 'conditional_just_after_as_of' if low <= start else 'start_of_declared_date_limit'
                else:
                    key, placement = (1, high, 0), 'just_before_declared_date_end_limit'
            key += (0 if event['amount'] < 0 else 1, event['source']['id'])
            ordered.append((key, event, placement))
        balances, holds = dict(opening), dict(reservations)
        trough = {c: {'minimum_available': opening[c], 'first_minimum_event_id': None,
                      'first_minimum_at': document['as_of'], 'floor': floors[c]} for c in settled}
        timeline, breaches, flows = [], [], {c: Decimal(0) for c in settled}
        for c in settled:
            if opening[c] < floors[c]:
                breaches.append({'id': None, 'at': document['as_of'], 'currency': c,
                                 'available': opening[c], 'floor': floors[c]})
        for _, event, placement in sorted(ordered, key=lambda item: item[0]):
            raw = event['source']; c = raw['currency']
            holds[c] -= event['release']
            balances[c] += event['effect']; flows[c] += event['amount']
            row = {'id': raw['id'], 'kind': raw['kind'], 'currency': c,
                   'source_available_at': raw['available_at'],
                   'at': raw['available_at'] if event['exact'] is not None else None,
                   'timing_placement': placement, 'cash_flow': event['amount'],
                   'reservation_release': event['release'], 'available': balances[c],
                   'remaining_reservation': holds[c]}
            timeline.append(row)
            if balances[c] < trough[c]['minimum_available']:
                trough[c].update(minimum_available=balances[c], first_minimum_event_id=raw['id'], first_minimum_at=row['at'])
            if balances[c] < floors[c]:
                breaches.append({**row, 'floor': floors[c]})
        for c in settled:
            trough[c]['maximum_floor_gap'] = max(Decimal(0), floors[c] - trough[c]['minimum_available'])
        return {'status': 'SHORTFALL' if breaches else 'PROJECTED_COVERED',
                'interpretation': 'Conditional ordering bound; no date-only point is an observed timestamp.',
                'timeline': timeline, 'troughs': trough, 'breaches': breaches,
                'ending_available': balances, 'remaining_reservations': holds,
                'net_external_cash_flows': flows,
                'conservation_residual': {c: balances[c] - (settled[c] + flows[c] - holds[c]) for c in settled}}

    favorable, adverse = scenario(True), scenario(False)
    bounds = {}
    for c in settled:
        lo = adverse['troughs'][c]['minimum_available']; hi = favorable['troughs'][c]['minimum_available']
        require(lo <= hi, 'CASH_TIMING_ENVELOPE_ORDER')
        bounds[c] = {'minimum_available_range': {'lower': lo, 'upper': hi},
                     'maximum_floor_gap_range': {'lower': max(Decimal(0), floors[c] - hi),
                                                'upper': max(Decimal(0), floors[c] - lo)},
                     'ending_available_range': {'lower': adverse['ending_available'][c],
                                                'upper': favorable['ending_available'][c]},
                     'floor': floors[c],
                     'shortfall_classification': 'IN_EVERY_CONDITIONAL_ORDERING' if hi < floors[c] else
                         'POSSIBLE_DEPENDING_ON_ORDERING' if lo < floors[c] else 'NONE_WITHIN_CONDITIONAL_BOUNDS'}
    status = 'UNRESOLVED_TIMING' if unresolved else 'DATE_ONLY_TIMING_ENVELOPE'
    helper = {'status': status, 'timeline': None,
              'ending_available': None if unresolved else favorable['ending_available'],
              'remaining_reservations': None if unresolved else favorable['remaining_reservations'],
              'ignored_unconfirmed_credits': ignored, 'execution_authorized': False}
    return finish(document, 'cash-plan-contract', status=status, helper_result=helper,
                  source_events=source, event_timing=temporal, missing_data=missing,
                  scenario_assumptions=assumptions,
                  envelope_basis='RELAXED_CONDITIONAL_ORDERING_BOUNDS' if unresolved else 'DECLARED_CALENDAR_INTERVAL_ORDERING_BOUNDS',
                  scenarios={'favorable_ordering': favorable, 'adverse_ordering': adverse},
                  cash_bounds=bounds, troughs=None, event_times_unchanged=True,
                  noncash_events_not_funding=deepcopy(document.get('noncash_events', [])),
                  spendable_cash=None, execution_authorized=False,
                  limitation='Conditional cash bounds, not broker buying power or trade permission. Date boundaries are not observed settlement times; withdrawals and all subsequent demands remain unchanged.')


def cash_plan(document):
    """Exact timestamp path, or explicit calendar-date ordering bounds."""
    if any(_cash_date_only(row.get('available_at')) for row in document['events']):
        return _date_ambiguous_cash_plan(document)
    names = ('as_of', 'settled_balances', 'reservations', 'events', 'floors')
    inputs = deepcopy({k: document[k] for k in names})
    for name in ('settled_balances', 'reservations', 'floors'):
        inputs[name] = {c: float(amount(v)) for c, v in inputs[name].items()}
    require(document['currency'] in inputs['settled_balances'], 'BASE_CURRENCY_NOT_IN_CASH_MAP')
    for row in inputs['events']:
        require(row.get('kind') in {'cash_credit', 'cash_debit', 'withdrawal', 'trade_settlement', 'external_obligation'}, 'CASH_EVENT_KIND_REQUIRED')
        row['amount'] = float(amount(row['amount']))
        if row['kind'] in {'withdrawal', 'cash_debit', 'external_obligation'}:
            require(row['amount'] <= 0, 'DEBIT_SIGN_REQUIRED')
        if 'reservation_release' in row:
            row['reservation_release'] = float(amount(row['reservation_release'], minimum=0))
    result = investment_ops.cash_ladder(**inputs)
    troughs = {}
    for currency, opening in inputs['settled_balances'].items():
        points = [{'at': inputs['as_of'], 'available': opening - inputs['reservations'][currency]}]
        points += [r for r in result['timeline'] if r['currency'] == currency]
        worst = min(points, key=lambda r: r['available'])
        troughs[currency] = {'minimum_available': worst['available'], 'first_minimum_at': worst['at'],
                            'floor': inputs['floors'][currency],
                            'maximum_floor_gap': max(0, inputs['floors'][currency] - worst['available'])}
    return finish(document, 'cash-plan-contract', status=result['status'], helper_result=result, troughs=troughs,
                  event_times_unchanged=True, noncash_events_not_funding=document.get('noncash_events', []),
                  spendable_cash=None, limitation='Conditional cash plan, not broker buying power; withdrawal dates are never shifted by trade settlement.')


def cash_projection(document):
    """One declared annual-effective rate, actual event times and ACT/365F."""
    start, end = timestamp(document['start_at']), timestamp(document['end_at'])
    require(end > start and document['day_count'] == 'ACT/365F', 'EXPLICIT_TIME_AND_ACT365F_REQUIRED')
    rate = amount(document['annual_effective_rate'], 'rate'); require(rate > -1, 'RATE_ABOVE_MINUS_ONE')
    balance = float(amount(document['opening_cash'], 'opening_cash', 0))
    floor = float(amount(document['floor'], 'floor', 0))
    rows = document['events']; require(len({r['id'] for r in rows}) == len(rows), 'UNIQUE_EVENT_IDS')
    prepared, ignored = [], []
    for row in rows:
        at = timestamp(row['at']); value = float(amount(row['amount']))
        require(start <= at <= end, 'EVENT_OUTSIDE_PROJECTION')
        require(row.get('kind') in {'withdrawal', 'deposit', 'cash_distribution'}, 'CASH_ONLY_EVENTS')
        require(row['kind'] != 'withdrawal' or value <= 0, 'WITHDRAWAL_DEBIT_REQUIRED')
        require(type(row.get('confirmed')) is bool, 'CONFIRMATION_FLAG_REQUIRED')
        if value > 0 and not row['confirmed']:
            ignored.append(row['id']); continue
        prepared.append((at, value >= 0, row['id'], value))
    timeline = [{'at': start.isoformat(), 'balance': balance, 'kind': 'opening'}]
    previous = start; interest = 0.; flows = 0.; stop = False
    for at, _, identifier, value in sorted(prepared) + [(end, True, None, 0.)]:
        earned = balance * ((1 + float(rate)) ** ((at - previous).total_seconds() / (365 * 86400)) - 1)
        require(math.isfinite(earned), 'NONFINITE_PROJECTION')
        balance += earned; interest += earned
        timeline.append({'at': at.isoformat(), 'kind': 'before_flow' if identifier else 'terminal', 'balance': balance})
        if identifier is not None:
            balance += value; flows += value
            timeline.append({'at': at.isoformat(), 'id': identifier, 'kind': 'after_flow', 'cash_flow': value, 'balance': balance})
        previous = at
        if balance < 0:
            stop = True; break
    worst = min(timeline, key=lambda r: r['balance'])
    return finish(document, 'timed-cash-projection', status='UNFUNDED_SHORTFALL' if stop else 'COMPUTED',
                  ending_cash=None if stop else balance, last_modeled_cash=balance,
                  minimum_balance=worst['balance'], minimum_at=worst['at'], maximum_floor_gap=max(0, floor-worst['balance']),
                  interest_earned=interest, net_external_cash_flows_processed=flows, timeline=timeline,
                  ignored_unconfirmed_credits=ignored, conservation_residual=balance-float(amount(document['opening_cash']))-flows-interest,
                  measurement_period={'start':document['start_at'],'end':document['end_at']},
                  limitation='Explicit constant-rate scenario; projection stops at unfunded negative cash, with no inferred borrowing or deferred withdrawal.')


def vest_reconciliation(document):
    cutoff = timestamp(document['as_of']); rows=[]
    totals = {k: Decimal(0) for k in ('gross_shares','withheld_shares','sold_for_tax_shares','net_shares')}
    settled_cash = Decimal(0)
    require(len({r['id'] for r in document['grants']}) == len(document['grants']), 'UNIQUE_GRANT_IDS')
    for grant in document['grants']:
        gross = amount(grant['gross_shares'], minimum=0)
        withheld = amount(grant['shares_withheld_for_tax'], minimum=0)
        sold = amount(grant['shares_sold_for_tax'], minimum=0)
        require(withheld+sold <= gross, 'TAX_SHARES_EXCEED_GROSS')
        vest_date = date.fromisoformat(grant['vest_date'])
        require(grant['status'] in {'future_scheduled','vested'}, 'GRANT_STATUS_REQUIRED')
        require(grant['status'] != 'vested' or vest_date <= cutoff.date(), 'FUTURE_VEST_CANNOT_BE_OBSERVED_VESTED')
        net = gross-withheld-sold
        row = {'id':grant['id'],'vest_date':grant['vest_date'],'status':grant['status'], 'gross_shares':gross,
               'withheld_shares':withheld,'sold_for_tax_shares':sold,'tax_shares':withheld+sold,
               'tax_share_fraction':(withheld+sold)/gross if gross else None,'net_shares':net,
               'net_share_value_at_supplied_vest_assumption':None,'settled_sale_cash_observed':Decimal(0)}
        if grant.get('assumed_vest_price') is not None:
            row['net_share_value_at_supplied_vest_assumption'] = net*amount(grant['assumed_vest_price'], minimum=0)
        sale = grant.get('sale')
        if sale:
            require(grant['status']=='vested' and sale.get('confirmed') is True, 'CONFIRMED_VEST_AND_SALE_REQUIRED')
            sale_qty=amount(sale['sold_net_shares'],minimum=0);proceeds=amount(sale['net_cash_proceeds'],minimum=0)
            require(sale_qty<=net, 'SALE_EXCEEDS_NET_SHARES')
            require(sale_qty>0 or proceeds==0,'ZERO_SHARE_SALE_CANNOT_CREATE_CASH')
            executed, settled = timestamp(sale['executed_at']), timestamp(sale['settled_at'])
            require(executed.date()>=vest_date and settled>=executed, 'SALE_SETTLEMENT_ORDER')
            require(executed<=cutoff,'OBSERVED_SALE_EXECUTION_AFTER_CUTOFF')
            require(sale.get('evidence'), 'SALE_EVIDENCE_REQUIRED')
            if settled<=cutoff:
                row['settled_sale_cash_observed']=proceeds
                settled_cash+=row['settled_sale_cash_observed']
        rows.append(row)
        for key in totals: totals[key]+=row[key]
    return finish(document,'vest-share-cash-reconciliation',grants=rows,totals=totals,
                  total_tax_shares=totals['withheld_shares']+totals['sold_for_tax_shares'],
                  tax_share_fraction=(totals['withheld_shares']+totals['sold_for_tax_shares'])/totals['gross_shares'] if totals['gross_shares'] else None,
                  observed_settled_sale_cash=settled_cash,total_spendable_cash=None,
                  future_grants_are_cash=False,combined_future_concentration=None,
                  limitation='Grant-date values stay separate; no mixed-date portfolio valuation, implied sale, tax liability or broker availability.')


def portfolio_reconciliation(document):
    equity=amount(document['declared_equity'],minimum='0.000000000001'); cash=amount(document['explicit_cash'],minimum=0)
    positions=deepcopy(document['positions']); funds=deepcopy(document['funds'])
    position_value=sum((amount(r['quantity'],minimum=0)*amount(r['mark'],minimum='0.000000000001') for r in positions),Decimal(0))
    legacy_positions=deepcopy(positions)
    for row in legacy_positions:
        row['quantity']=float(amount(row['quantity'],minimum=0));row['mark']=float(amount(row['mark'],minimum='0.000000000001'))
    identified=position_value+cash; unexplained=equity-identified
    # The helper's equity argument is an expansion ceiling, not a substituted NAV.
    helper=portfolio_analytics.lookthrough(legacy_positions,float(max(equity,position_value)),funds)
    def weights(exposures):
        return {key:{'value':value,'fraction_of_declared_equity':float(amount(value)/equity),
                     'fraction_of_identified_assets':float(amount(value)/identified) if identified else None}
                for key,value in exposures.items()}
    result={'status':'RECONCILED' if unexplained==0 else 'UNEXPLAINED_EQUITY_DIFFERENCE',
            'declared_equity':equity,'identified_position_value':position_value,'explicit_cash':cash,
            'identified_assets':identified,'unexplained_equity_difference':unexplained,
            'unexplained_fraction_of_declared_equity':unexplained/equity,
            'issuer_exposures':weights(helper['issuer_exposure']),'sector_exposures':weights(helper['sector_exposure']),
            'unknown_fund_value_within_identified_positions':helper['unknown_fund_value'],
            'embedded_fund_cash':helper['embedded_fund_cash'],'fund_sources':helper['fund_sources'],
            'conservation_residual':equity-position_value-cash-unexplained,
            'arithmetic_basis':'Account reconciliation uses original Decimal quantities/marks; legacy look-through expansion uses binary floats.',
            'denominator_note':'Identified assets include explicit top-level cash. Unknown fund constituents remain inside identified positions; unexplained equity is separate.',
            'limitation':'Declared snapshot only; constraints on one rebalance do not establish permanent concentration.'}
    if document.get('contribution_allocations') is not None:
        require(document.get('unchanged_marks_assumption') is True,'EXPLICIT_FIXED_MARK_CONTRIBUTION_SCENARIO_REQUIRED')
        additions=document['contribution_allocations']; by_symbol={p['symbol']:p for p in positions}
        require(len(by_symbol)==len(positions),'UNIQUE_POSITION_SYMBOLS_FOR_CONTRIBUTIONS')
        total=Decimal(0)
        for symbol,value in additions.items():
            value=amount(value,minimum=0);require(symbol in by_symbol,'CONTRIBUTION_POSITION_AND_MARK_REQUIRED')
            by_symbol[symbol]['quantity']=str(amount(by_symbol[symbol]['quantity'])+value/amount(by_symbol[symbol]['mark']));total+=value
        changed={**document,'positions':positions,'declared_equity':str(equity+total)}
        changed.pop('contribution_allocations');changed.pop('unchanged_marks_assumption',None)
        result['contribution_only_scenario']=portfolio_reconciliation(changed)
        result['contribution_only_scenario']['assumption']='Supplied marks/fund weights unchanged; contributions add equity; no sales modeled.'
    return finish(document,'portfolio-denominator-reconciliation',**result)


def cash_reconciliation(document):
    """Dated ledger uses the existing helper; aggregate cash bridge has no timing claim."""
    if document['mode']=='dated_ledger':
        helper=accounting_tools.cash_reconciliation(**{k:document[k] for k in ('opening_cash','entries','broker_cash','as_of')})
        return finish(document,'dated-cash-reconciliation',helper_result=helper,spendable_cash=None)
    require(document['mode']=='aggregate_bridge','CASH_RECONCILIATION_MODE_REQUIRED')
    entries=document['entries'];require(len({r['id'] for r in entries})==len(entries),'UNIQUE_LEDGER_IDS')
    opening=amount(document['opening_cash']);ending=opening+sum((amount(r['amount']) for r in entries),Decimal(0))
    observed=amount(document['observed_cash'])
    return finish(document,'aggregate-cash-reconciliation',calculated_cash=ending,observed_cash=observed,
                  difference=ending-observed,reconciled=ending==observed,spendable_cash=None,
                  status='RECONCILED' if ending==observed else 'UNRESOLVED_DIFFERENCE',
                  limitation='Signed aggregate bridge; posting, settlement, holds and broker spending availability are not inferred.')


def trade_history_costs(document):
    require(document['pnl_basis'] in {'gross_before_costs','net_after_costs'},'PNL_BASIS_REQUIRED')
    rows=[]; trades=document['trades'];require(len({r['id'] for r in trades})==len(trades),'UNIQUE_TRADE_IDS')
    for trade in trades:
        value=amount(trade['pnl']);fees=amount(trade['fees'],minimum=0);slippage=amount(trade['slippage'],minimum=0)
        net=value-fees-slippage if document['pnl_basis']=='gross_before_costs' else value
        gross=value if document['pnl_basis']=='gross_before_costs' else value+fees+slippage
        rows.append({'id':trade['id'],'gross_pnl':gross,'fees':fees,'slippage':slippage,'net_pnl':net})
    def summary(field):
        values=[r[field] for r in rows];wins=[v for v in values if v>0];losses=[v for v in values if v<0]
        return {'total':sum(values,Decimal(0)),'wins':len(wins),'losses':len(losses),'flat':len(values)-len(wins)-len(losses),
                'average_win':sum(wins)/len(wins) if wins else None,'average_loss':sum(losses)/len(losses) if losses else None}
    return finish(document,'gross-net-trade-history',rows=rows,gross=summary('gross_pnl'),net=summary('net_pnl'),
                  attribution_to_execution_or_investment=None,limitation='Supplied costs only; gross/net outcome groups use their respective signs, not inferred causes or scalability.')


def session_pnl(document):
    start,end=timestamp(document['session_start']),timestamp(document['as_of']);require(end>=start,'SESSION_TIME_ORDER')
    missing=[];rows=[];session_total=Decimal(0);lifetime_total=Decimal(0)
    for row in document['open_positions']:
        qty=amount(row['quantity'],minimum=0);mark=amount(row['current_mark'],minimum=0)
        lifetime=qty*(mark-amount(row['basis_per_share'])) if row.get('basis_per_share') is not None else None
        value=None
        if row.get('session_start_mark') is None or row.get('unchanged_quantity_in_session') is not True or row.get('session_fees') is None:
            missing.append({'id':row['id'],'reason':'PRIOR_MARK_UNCHANGED_QUANTITY_OR_SESSION_FEES_MISSING'})
        else:
            value=qty*(mark-amount(row['session_start_mark']))-amount(row['session_fees'],minimum=0);session_total+=value
        if lifetime is not None:lifetime_total+=lifetime
        rows.append({'id':row['id'],'basis_to_mark_unrealized':lifetime,'session_mark_change_net_costs':value})
    realized=[]
    for row in document['closed_trades']:
        value=amount(row['quantity'],minimum=0)*(amount(row['sell_price'])-amount(row['buy_price']))-amount(row['fees'],minimum=0)
        eligible=bool(row.get('opened_at') and row.get('closed_at') and start<=timestamp(row['opened_at'])<=timestamp(row['closed_at'])<=end)
        if eligible:session_total+=value
        else:missing.append({'id':row['id'],'reason':'INTRASESSION_ENTRY_EXIT_NOT_ESTABLISHED'})
        realized.append({'id':row['id'],'realized_trade_pnl':value,'included_in_session_pnl':eligible})
    if document.get('coverage_complete') is not True or document.get('session_distributions') is None:
        missing.append({'reason':'COMPLETE_SESSION_COVERAGE_OR_DISTRIBUTIONS_MISSING'})
    else:session_total+=amount(document['session_distributions'])
    close=timestamp(document['exchange_session_close']) if document.get('exchange_session_close') else None
    return finish(document,'session-vs-basis-pnl',status='PARTIAL' if missing else 'COMPUTED',positions=rows,realized_trades=realized,
                  session_pnl=None if missing else session_total,observed_basis_to_mark_sum=lifetime_total,missing=missing,
                  after_declared_session_close=end>close if close else None,
                  limitation='Lifetime basis is not the prior-session mark; no exchange close, overnight holding or complete daily P&L is inferred.')
