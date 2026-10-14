"""Offline cash ladders, execution shortfall, money-weighted returns and attribution."""
from __future__ import annotations

import math
import numpy as np
from scipy.optimize import brentq

from quant_common import cli, require, scalar, timestamp


def cash_ladder(as_of, settled_balances, reservations, events, floors):
    """Per-currency available cash; debit-before-credit at equal availability time.

    Only explicit available_at dates are used. Planned/unconfirmed credits are
    excluded, and no FX conversion or implicit margin borrowing funds a shortfall.
    """
    start = timestamp(as_of)
    require(set(settled_balances) == set(reservations) == set(floors), 'CURRENCY_MAP_MISMATCH')
    reserved = {c: scalar(v, 'reservation', 0) for c, v in reservations.items()}
    balances = {c: scalar(v, 'settled_balance')-reserved[c]
                for c, v in settled_balances.items()}
    minimum = {c: scalar(v, 'floor', 0) for c, v in floors.items()}
    breaches = [{'at': as_of, 'currency': c, 'available': v, 'floor': minimum[c]}
                for c, v in balances.items() if v < minimum[c]]
    require(len({e['id'] for e in events}) == len(events), 'DUPLICATE_CASH_EVENT')
    timeline, ignored, planned = [], [], []
    for e in events:
        at = timestamp(e['available_at'])
        require(at > start, 'FUTURE_EVENTS_ONLY_OPENING_BALANCE_ALREADY_INCLUDES_PAST')
        require(e['currency'] in balances, 'UNKNOWN_CURRENCY')
        amount = scalar(e['amount'], 'cash_amount')
        release = scalar(e.get('reservation_release', 0), 'reservation_release', 0)
        require(release <= max(0, -amount), 'RELEASE_CANNOT_EXCEED_MATCHING_DEBIT')
        require(type(e.get('confirmed')) is bool, 'CONFIRMATION_FLAG_REQUIRED')
        if amount > 0 and e['confirmed'] is not True:
            ignored.append(e['id'])
            continue
        require(e.get('evidence'), 'CASH_TIMING_EVIDENCE_REQUIRED')
        planned.append((at, 0 if amount < 0 else 1, e['id'], e))
    for at, _, _, e in sorted(planned):
        c = e['currency']
        release = e.get('reservation_release', 0)
        require(release <= reserved[c], 'RESERVATION_ALREADY_RELEASED_OR_MISSING')
        # Consumption of an existing hold must not charge the same cash twice.
        reserved[c] -= release
        balances[c] += e['amount']+release
        timeline.append({'id': e['id'], 'at': at.isoformat(), 'currency': c,
                         'available': balances[c], 'remaining_reservation': reserved[c]})
        if balances[c] < minimum[c]:
            breaches.append({**timeline[-1], 'floor': minimum[c]})
    return {'status': 'SHORTFALL' if breaches else 'PROJECTED_COVERED', 'breaches': breaches,
            'timeline': timeline, 'ending_available': balances, 'remaining_reservations': reserved,
            'ignored_unconfirmed_credits': ignored,
            'execution_authorized': False,
            'limitation': 'Forecast conditional on confirmed timing. Broker available settled cash still controls every order; no fixed 24-hour or same-day rotation assumption.'}


def implementation_shortfall(side, intended_quantity, decision_price, arrival_price,
                             terminal_price, fills, fees=0):
    require(side in {'buy', 'sell'}, 'SIDE_REQUIRED')
    direction = 1 if side == 'buy' else -1
    intended = scalar(intended_quantity, 'intended_quantity', 1e-12)
    decision = scalar(decision_price, 'decision_price', 1e-12)
    arrival = scalar(arrival_price, 'arrival_price', 1e-12)
    terminal = scalar(terminal_price, 'terminal_price', 1e-12)
    explicit = scalar(fees, 'fees', 0)
    require(len({f['id'] for f in fills}) == len(fills), 'DUPLICATE_FILL')
    qty = sum(scalar(f['quantity'], 'quantity', 1e-12) for f in fills)
    require(qty <= intended+1e-9, 'OVERFILL')
    execution = sum(direction*f['quantity']*(scalar(f['price'], 'price', 1e-12)-arrival) for f in fills)
    delay = direction*qty*(arrival-decision)
    opportunity = direction*(intended-qty)*(terminal-decision)
    total = execution+delay+opportunity+explicit
    return {'filled_quantity': qty, 'unfilled_quantity': intended-qty,
            'delay_cost': delay, 'execution_cost_vs_arrival': execution,
            'opportunity_cost': opportunity, 'fees': explicit, 'total_shortfall': total,
            'shortfall_bps_of_intended_notional': total/(intended*decision)*10000,
            'limitation': 'Positive is cost for both sides; consistent raw-price, currency and evaluation horizon required. Opportunity cost is benchmark dependent.'}


def xirr(cashflows):
    """ACT/365 annual money-weighted rate for a conventional one-switch cash stream.

    Investor perspective: contributions negative, withdrawals/terminal NAV positive.
    Nonconventional multiple sign changes return ambiguity, not a selected root.
    """
    require(len(cashflows) >= 2, 'CASHFLOWS_REQUIRED')
    grouped = {}
    for f in cashflows:
        at = timestamp(f['at'])
        grouped[at] = grouped.get(at, 0.)+scalar(f['amount'], 'cashflow')
    rows = [(t, v) for t, v in sorted(grouped.items()) if v != 0]
    require(len(rows) >= 2 and rows[0][0] < rows[-1][0], 'DISTINCT_CASHFLOW_DATES_REQUIRED')
    signs = np.sign([v for _, v in rows])
    changes = int(np.count_nonzero(signs[1:] != signs[:-1]))
    if signs[0] != -1 or signs[-1] != 1 or changes != 1:
        return {'status': 'AMBIGUOUS_OR_NONCONVENTIONAL_CASHFLOWS', 'annual_xirr': None, 'sign_changes': changes}
    times = np.array([(t-rows[0][0]).total_seconds()/(365*86400) for t, _ in rows])
    amounts = np.array([v for _, v in rows])
    # Root in log(1+r); scale exponents to avoid overflow on long horizons.
    def npv(lograte):
        powers = -lograte*times
        return float(amounts @ np.exp(powers-powers.max()))
    lower, upper = -30., 30.
    if npv(lower)*npv(upper) > 0:
        return {'status': 'ROOT_OUTSIDE_NUMERICAL_BRACKET', 'annual_xirr': None}
    root = brentq(npv, lower, upper, xtol=1e-13)
    return {'status': 'COMPUTED', 'annual_xirr': math.expm1(root), 'day_count': 'ACT/365',
            'limitation': 'Terminal value must be supplied; annualization of a short period is not a return forecast.'}


def brinson(groups):
    """Single-period Brinson-Fachler, including interaction; weights include cash."""
    require(groups and len({g['name'] for g in groups}) == len(groups), 'GROUP_IDS')
    wp = np.array([scalar(g['portfolio_weight'], 'weight', 0, 1) for g in groups])
    wb = np.array([scalar(g['benchmark_weight'], 'weight', 0, 1) for g in groups])
    rp = np.array([scalar(g['portfolio_return'], 'return', -1) for g in groups])
    rb = np.array([scalar(g['benchmark_return'], 'return', -1) for g in groups])
    require(abs(wp.sum()-1) < 1e-9 and abs(wb.sum()-1) < 1e-9, 'WEIGHTS_MUST_SUM_TO_ONE_INCLUDE_CASH')
    benchmark = float(wb @ rb)
    allocation = (wp-wb)*(rb-benchmark)
    selection = wb*(rp-rb)
    interaction = (wp-wb)*(rp-rb)
    excess = float(wp @ rp)-benchmark
    return {'active_return': excess, 'allocation': float(allocation.sum()),
            'selection': float(selection.sum()), 'interaction': float(interaction.sum()),
            'reconciliation_error': excess-float((allocation+selection+interaction).sum()),
            'benchmark_appropriateness': 'NOT_ASSESSED',
            'causal_attribution_assessed': False,
            'limitation': 'Arithmetic Brinson-Fachler decomposition for one period and consistent beginning weights. Selection is a formula label, not proof of stock-selection skill, investment cause, execution quality or policy compliance. Equal assumed portfolio/benchmark weights force zero allocation and interaction; they do not establish actual policy weights. Benchmark comparability and completeness of costs remain caller evidence. Multi-period linking and intraperiod trading need separate accounting.'}


if __name__ == '__main__':
    cli({'cash_ladder': cash_ladder, 'shortfall': implementation_shortfall,
         'xirr': xirr, 'attribution': brinson})
