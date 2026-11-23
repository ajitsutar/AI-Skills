"""Editable, ex ante economics for a single-instrument, long/cash strategy."""
from decimal import Decimal
import math

from strategy_design_answer import fields, need
from strategy_registration import origin


def economics_schema(forward=False):
    spec = {
        'position': {'kind': 'long_cash', 'entry_equity_fraction': {'proposal': 1.0}},
        'prices': 'raw_execution_prices_split_shares_cash_dividends',
        'cost_bps_per_side': {'record_pointer': '/cost_bps_per_side'},
        'signal': {'kind': 'sma_crossover', 'windows': {'record_pointer': '/variants/0'}},
        'sample': {'minimum_completed_round_trips': 3},
    }
    if forward:
        spec['execution_quality'] = {'minimum_on_time_filled_fraction': 0.90,
                                     'maximum_adverse_shortfall_bps': 25.0}
    return spec


def finite(value, lo, hi, label, open_left=False):
    need(type(value) in (int, float, Decimal) and math.isfinite(value) and
         (lo < value if open_left else lo <= value) and value <= hi, label)
    return value


def resolve_economics(spec, record, lookup, comparator, forward, primary):
    names = {'position', 'prices', 'cost_bps_per_side', 'signal', 'sample'}
    fields(spec, names | ({'execution_quality'} if forward else set()))
    fields(spec['position'], {'kind', 'entry_equity_fraction'})
    need(spec['position']['kind'] == 'long_cash' and
         spec['prices'] == 'raw_execution_prices_split_shares_cash_dividends', 'SUPPORTED_POSITION_AND_PRICE_BASIS_REQUIRED')
    exposure = origin(spec['position']['entry_equity_fraction'], record, lookup)
    finite(exposure['value'], 0, 1, 'LONG_UNLEVERED_ENTRY_FRACTION_REQUIRED', open_left=True)
    costs = origin(spec['cost_bps_per_side'], record, lookup)
    finite(costs['value'], 0, 9999.999999, 'COST_BPS_PER_SIDE_REQUIRED')
    need(comparator['cash_return']['convention'] != 'unavailable', 'REGISTER_EXECUTABLE_CASH_ACCRUAL_OR_EXPLICIT_PROPOSED_RATE')
    signal = spec['signal']
    need(isinstance(signal, dict), 'TYPED_SIGNAL_REQUIRED')
    if signal.get('kind') == 'sma_crossover':
        fields(signal, {'kind','windows'})
        pair = origin(signal['windows'], record, lookup)
        windows = pair['value']
        need(isinstance(windows,list) and len(windows) == 2 and all(type(n) == int for n in windows)
             and 0 < windows[0] < windows[1], 'ORDERED_FAST_SLOW_SMA_WINDOWS_REQUIRED')
        if 'record_pointer' in primary:
            chosen = lookup(record,primary['record_pointer'])
            need(isinstance(chosen, list) and len(chosen) == 2 and
                 all(type(n) is int for n in chosen) and chosen == windows,
                 'PRIMARY_AND_SIGNAL_WINDOWS_DISAGREE')
            if 'record_pointer' in pair:
                need(primary['record_pointer'] == pair['record_pointer'], 'PRIMARY_AND_SIGNAL_FIELDS_DISAGREE')
        else:
            need(primary == {'proposal': f'SMA({windows[0]},{windows[1]})'}, 'PRIMARY_AND_SIGNAL_WINDOWS_DISAGREE')
        signal = {'kind':'sma_crossover','windows':pair}
    else:
        # Only a declared native boolean target qualifies for level-based startup.
        fields(signal, {'kind','target_field'})
        need(signal['kind'] == 'binary_target' and isinstance(signal['target_field'],dict)
             and set(signal['target_field']) == {'record_pointer'}, 'SUPPLIED_BOOLEAN_TARGET_REQUIRED')
        target = origin(signal['target_field'],record,lookup)
        need(type(target['value']) is bool,'SUPPLIED_BOOLEAN_TARGET_REQUIRED')
        pointer = target['record_pointer']
        need(primary in ({'record_pointer': pointer}, {'proposal': f'binary_target({pointer})'}),
             'PRIMARY_AND_SIGNAL_FIELDS_DISAGREE')
        signal = {'kind':'binary_target','target_field':target}
    fields(spec['sample'],{'minimum_completed_round_trips'})
    floor = spec['sample']['minimum_completed_round_trips']
    need(type(floor) == int and floor >= 2, 'AT_LEAST_TWO_DISTINCT_COMPLETED_EXPOSURES_REQUIRED')
    out = {'position':{'kind':'long_cash','entry_equity_fraction':exposure},'prices':spec['prices'],
           'cost_bps_per_side':costs,'signal':signal,'sample':spec['sample']}
    if forward:
        quality = spec['execution_quality']
        fields(quality,{'minimum_on_time_filled_fraction','maximum_adverse_shortfall_bps'})
        finite(quality['minimum_on_time_filled_fraction'],0,1,'POSITIVE_ON_TIME_FILL_FRACTION_REQUIRED',open_left=True)
        finite(quality['maximum_adverse_shortfall_bps'],0,10000,'SHORTFALL_CAP_BPS_REQUIRED')
        out['execution_quality'] = quality
    return out


INITIAL = 'Start flat with no outstanding order, no borrowing, and all capital in the registered quote currency.'
EXECUTION = ('At the first eligible regular-session opening auction following a qualified completed close, '
             'model a market-on-open transaction at the unadjusted official opening price. No same-close execution. '
             'If the next scheduled eligible auction, price or point-in-time calendar cannot be verified, '
             'record the missed or unknown execution and its unfilled quantity. Do not carry the order or assume a fill.')
EVENT = 'distinct completed flat-to-long-to-flat exposures in the primary book'


def warmup(economics):
    signal = economics['signal']
    if signal['kind'] == 'binary_target':
        return ('Use the supplied binary target only when it is known at the completed close. '
                'The first qualified true target from flat schedules entry, false schedules exit only from long.')
    fast, slow = signal['windows']['value']
    return (f'At each eligible completed close, compare trailing arithmetic means of {fast} and {slow} '
            f'consecutive point-in-time split-normalized completed closes. Require {slow} such closes for a formed pair. '
            'The first nonzero fast-minus-slow sign seeds the previous qualified sign without an order, even when positive. '
            'Equality before seeding leaves the signal uninitialized. Later equality retains the last nonzero sign and position. '
            'After seeding, a negative-to-positive crossing schedules entry from flat; a positive-to-negative crossing schedules '
            'exit from long. Repeated signs and redundant position changes generate no order. Historical pre-window bars may '
            'seed the signal but cannot open a position or submit a pre-window order. Missing required bars reset the rolling '
            'history and prior sign; preserve existing holdings and log the gap. Restart with a newly seeded sign. '
            'Apply each shadow variant with its own windows, state and journal.')


def adverse_shortfall_bps(side, intended, arrival_midpoint, fills, fees, residual_close=None):
    '''Return adverse bps for a reconciled order with quote-currency fees.'''
    def decimal(value):
        need(type(value) in (int, float, Decimal), 'NUMERIC_ORDER_INPUT_REQUIRED')
        number = Decimal(str(value))
        need(number.is_finite(), 'FINITE_ORDER_INPUT_REQUIRED')
        return number

    need(side in ('buy', 'sell'), 'ORDER_SIDE_REQUIRED')
    quantity, midpoint, fee = map(decimal, (intended, arrival_midpoint, fees))
    need(quantity > 0 and midpoint > 0, 'POSITIVE_ORDER_AND_MIDPOINT_REQUIRED')
    outstanding = quantity
    difference = Decimal(0)
    for fill_quantity, fill_price in fills:
        units, price = map(decimal, (fill_quantity, fill_price))
        need(0 < units <= outstanding and price > 0, 'INVALID_OR_OVERFILLED_ORDER')
        difference += units * (price - midpoint)
        outstanding -= units
    if outstanding:
        close = decimal(residual_close)
        need(close > 0, 'POSITIVE_RESIDUAL_MARK_REQUIRED')
        difference += outstanding * (close - midpoint)
    signed = difference if side == 'buy' else -difference
    return max(Decimal(0), 10000 * (signed + fee) / (quantity * midpoint))


def render_economics(e, bench, display):
    fraction = display(e['position']['entry_equity_fraction'])
    costs = display(e['cost_bps_per_side'])
    lines = [
        '- Proposed position and execution accounting - begin with unit NAV. At entry allocate fraction '
        + fraction + ' of available cash (including the fee budget) to the long position. '
        'With opening price P, available cash C, and side cost k = ' + costs +
        ' / 10,000, buy q = fraction × C / [P × (1 + k)] fractional shares. Debit q × P × (1 + k). '
        'Hold the resulting shares without daily rebalancing. On exit sell the entire holding and credit q × P × (1 − k). '
        'Charge both entries and exits on actual transacted notional, including partials. Holds incur zero turnover.',
        '- Carry and price basis - accrue only settled idle cash at the registered comparator cash rate over elapsed '
        'calendar days between consecutive valuation or cash-flow timestamps. Apply splits to shares before the effective open; '
        'on the ex-date recognize an untaxed dividend receivable from the entitled prior holding, then transfer it to cash on payment. '
        'Receivables earn no interest. Reconstruct any signal-history split adjustment using only actions public at the signal cutoff. '
        'Book raw prices, cash distributions and split changes once; require the corresponding action ledger.',
        '- Return and comparison - on each eligible open mark NAV immediately before that auction’s trades as cash + '
        'shares × raw open + receivables. The interval return is next pre-trade NAV / current pre-trade NAV − 1, including '
        'the current opening trade costs, interim carry and distributions. Use the next eligible open only when both endpoints lie within '
        'the inclusive registered evaluation window. The final eligible open is the terminal mark and cannot initiate '
        'another measured interval; if an intermediate opening mark is missing, flag the incomplete interval. Mark remaining holdings at the '
        'endpoint with no invented exit. Pair matching opening intervals in the registered currency, subtract comparator '
        'net return from strategy net return per interval and average on the registered primary sample. Missing price, '
        'cash rate, corporate action, execution or comparator evidence makes the affected assessment inconclusive.',
    ]
    if bench['kind'] == 'cash':
        lines.append('- Comparator book - hold the initial NAV entirely in cash, accrue using the same day-count and rate; zero turnover.')
    elif bench['kind'] == 'buy_and_hold':
        lines.append('- Comparator book - at the first included opening auction invest all initial cash in the registered '
                     'identifier using the same entry fee budget, price and distribution conventions. Hold to the common '
                     'terminal mark. Charge exit costs only if a real modeled liquidation is prescribed for both books.')
    else:
        lines.append('- Comparator series - require a synchronized total-return level series for the registered identifier '
                     'in the same currency. Use adjacent level ratios minus one, including its published distributions '
                     'and embedded expenses; add no hypothetical index-trading fees. Missing basis or clock is inconclusive.')
    lines.append('- Qualified activity - count one exposure only after positive executed entry quantity is followed by '
                 'a fully executed exit returning the primary book to flat within the sample. Deduplicate partials by '
                 'exposure ID. Flat holds, repeated signals, unmatched orders, unfilled intentions, an open final position '
                 'and shadow variants add zero. Below the floor report inconclusive even with many decision rows.')
    if 'execution_quality' in e:
        q = e['execution_quality']
        lines.extend([
            '- Execution-quality gates - after identity and quantity reconciliation, calculate on-time filled fraction '
            'as the arithmetic mean over all intended nonzero primary orders of min(eligible opening-auction fill quantity / '
            'intended quantity, 1). Fully evidenced rejections, missed opens and cancellations contribute zero; partials '
            'contribute their filled proportion. Require fraction ≥ ' + str(q['minimum_on_time_filled_fraction']) + '.',
            '- Also require mean adverse execution shortfall ≤ ' + str(q['maximum_adverse_shortfall_bps']) +
            ' bps. For each reconciled order let Q > 0 be intended quantity, M > 0 its timestamped arrival bid/ask midpoint, '
            's = +1 for buys and −1 for sells. For each fill i use its executed quantity q_i and actual price P_i. '
            'Outstanding quantity U = Q − sum(q_i) must be nonnegative. For U > 0 mark unfilled opportunity cost '
            'at the same session’s official close C; when U = 0 the unfilled term is zero and no C is needed. '
            'With F the total actual order fees in quote currency, adverse bps = max(0, 10000 × '
            '(s × [sum(q_i × (P_i − M)) + U × (C − M)] + F) / (Q × M)). '
            'Average these order-level adverse bps with equal order weights. An illustrative fee-free buy of 100 '
            'shares at 101 against arrival 100 costs ' + str(adverse_shortfall_bps('buy', 100, 100, [(100, 101)], 0)) +
            ' bps. In the observed book '
            'use actual fills and fees rather than adding the modeled side cost again. Keep observed and modeled ledgers separate.',
            '- Failure of either threshold with sufficient verified coverage fails the operations criterion. Zero intended '
            'orders, absent reference quotes or prices, missing timestamps, or insufficient completed activity is inconclusive. '
            'A clean link count alone cannot establish execution quality; unresolved identity discrepancies still hold evaluation.'
        ])
    return lines
