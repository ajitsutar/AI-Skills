"""Source-explicit dated asset/cash ledgers and conditional sale-tax arithmetic.

No returns, tax rules, vest-sale conversion, source authenticity or funding gates
are inferred. All dates denote end-of-calendar-date snapshots, not settlement times.
"""
from copy import deepcopy
from datetime import date
from decimal import Context, Decimal, localcontext
import re

from planning_alignment import amount, finish, fraction, trade_costs
from quant_common import require


ZERO = Decimal(0)
ROLES = {'supplied_observation', 'hypothetical_scenario', 'user_assumption', 'unknown'}
STATES = {'confirmed', 'planned', 'scenario', 'unknown'}


def _text(value, name):
    require(isinstance(value, str) and bool(value.strip()), 'TEXT_REQUIRED:' + name)
    return value


def _day(value):
    require(isinstance(value, str) and re.fullmatch(r'\d{4}-\d{2}-\d{2}', value) is not None,
            'CALENDAR_DATE_REQUIRED_NO_MIXED_TIMESTAMPS')
    return date.fromisoformat(value)


def _rows(value, name):
    require(isinstance(value, list) and all(isinstance(row, dict) for row in value), 'OBJECT_ARRAY_REQUIRED:' + name)
    ids = [_text(row.get('id'), name + '.id') for row in value]
    require(len(ids) == len(set(ids)), 'UNIQUE_IDS_REQUIRED:' + name)
    return value


def _source(row, currency):
    require(row.get('currency') == currency, 'EXPLICIT_MATCHING_CURRENCY_REQUIRED_NO_FX')
    _text(row.get('source_ref'), 'source_ref')
    require(row.get('source_role') in ROLES, 'SOURCE_ROLE_REQUIRED')


def _precision(value):
    # Decimal inputs may have many digits or extreme exponents. Use a fresh
    # context, independent of caller rounding/traps, for all monetary arithmetic.
    if isinstance(value, dict):
        return sum(_precision(v) for v in value.values())
    if isinstance(value, list):
        return sum(_precision(v) for v in value)
    if isinstance(value, (str, int, float, Decimal)) and not isinstance(value, bool):
        try:
            n = Decimal(str(value))
            if n.is_finite():
                return len(n.as_tuple().digits) + abs(n.as_tuple().exponent)
        except Exception:
            pass
    return 0


def tax_sensitivity(document):
    """Conditional positive sale tax, with explicit selling-cost gain treatment.

    scenarios[{id,as_of,currency,source_ref,source_role,gross_proceeds,
               selling_costs,cost_basis,tax_rate,selling_costs_reduce_gain}].
    Missing basis/rate/costs/treatment remains unknown, even with zero gross gain.
    Treatment is yes/no/unknown; no tax law, loss credit or netting is inferred.
    """
    with localcontext(Context(prec=64 + _precision(document))):
        rows = []
        for raw in _rows(document.get('scenarios'), 'scenarios'):
            _source(raw, document['currency'])
            _day(raw['as_of'])
            treatment = raw.get('selling_costs_reduce_gain', 'unknown')
            require(treatment in {'yes', 'no', 'unknown'}, 'SELLING_COST_GAIN_TREATMENT_REQUIRED')
            values = {key: amount(raw[key], key, 0) if raw.get(key) is not None else None
                      for key in ('gross_proceeds', 'selling_costs', 'cost_basis')}
            rate = fraction(raw['tax_rate'], 'tax_rate') if raw.get('tax_rate') is not None else None
            missing = [key for key, value in values.items() if value is None]
            if rate is None:
                missing.append('tax_rate')
            if treatment == 'unknown':
                missing.append('selling_costs_reduce_gain')
            gross, costs, basis = (values[key] for key in values)
            net = gross - costs if gross is not None and costs is not None else None
            gain = (gross - basis - (costs if treatment == 'yes' else ZERO)) if (
                gross is not None and basis is not None and treatment != 'unknown'
                and (costs is not None or treatment == 'no')) else None
            tax = max(ZERO, gain) * rate if not missing else None
            rows.append({'id': raw['id'], 'as_of': raw['as_of'], 'source': deepcopy(raw),
                         'status': 'UNRESOLVED' if missing else 'COMPUTED_SCENARIO',
                         'missing_inputs': missing, 'selling_costs_reduce_gain': treatment,
                         'gross_proceeds': gross, 'selling_costs': costs, 'net_sale_proceeds': net,
                         'modeled_taxable_gain': gain, 'positive_tax_estimate': tax,
                         'modeled_tax_earmark': tax,
                         'net_sale_proceeds_after_tax_earmark': net - tax if tax is not None else None,
                         'tax_payment_inferred': False, 'cash_loss_credit_inferred': False})
        return finish(document, 'portfolio-tax-sensitivity', status='UNRESOLVED' if any(
            row['missing_inputs'] for row in rows) else 'COMPUTED_SCENARIOS', scenarios=rows,
            retained_input=deepcopy(document),
            limitations=['Conditional arithmetic using supplied gain treatment and rate; no tax-law determination.',
                         'Positive tax estimate is an earmark scenario, not an actual payment or assessed liability.',
                         'Negative gain receives no automatic cash credit; no cross-sale netting or loss carryforward.',
                         'Selling costs reduce cash proceeds once; reducing the tax base is not a second cash charge.'])


def dated_projection(document):
    """Project an explicitly supplied long-asset ledger through dated flows.

    Required opening {as_of,currency,source_ref,source_role,cash,tax_reserve,
                      positions:[{id,quantity}]}; target_date; included_states;
    flows; marks; mark_policy=target_date_only|carry_forward_supplied.
    All flow/mark rows have source metadata; see reference for kind-specific fields.
    """
    with localcontext(Context(prec=64 + _precision(document))):
        return _dated_projection(document)


def _dated_projection(document):
    currency = document['currency']
    opening = document['opening']
    require(isinstance(opening, dict), 'OPENING_OBJECT_REQUIRED')
    _source(opening, currency)
    start, target = _day(opening['as_of']), _day(document['target_date'])
    require(target >= start, 'TARGET_BEFORE_OPENING')
    selected = document.get('included_states')
    require(isinstance(selected, list) and len(selected) == len(set(selected))
            and all(state in STATES - {'unknown'} for state in selected), 'EXPLICIT_INCLUDED_STATES_REQUIRED')
    policy = document.get('mark_policy')
    require(policy in {'target_date_only', 'carry_forward_supplied'}, 'EXPLICIT_MARK_POLICY_REQUIRED')
    cash = amount(opening['cash'], 'opening_cash') if opening.get('cash') is not None else None
    reserve = amount(opening['tax_reserve'], 'opening_tax_reserve', 0) if opening.get('tax_reserve') is not None else None
    positions = {row['id']: amount(row['quantity'], 'quantity', 0) if row.get('quantity') is not None else None
                 for row in _rows(opening.get('positions'), 'positions')}
    opening_positions = dict(positions)
    flows = _rows(document.get('flows'), 'flows')
    marks = _rows(document.get('marks'), 'marks')
    require(len({row.get('asset_id') for row in marks}) == len(marks), 'ONE_TARGET_MARK_PER_ASSET_REQUIRED')
    mark_by_asset = {}
    for mark in marks:
        _source(mark, currency)
        asset = _text(mark.get('asset_id'), 'asset_id')
        mark_day = _day(mark['as_of'])
        require(mark_day <= target, 'MARK_AFTER_TARGET')
        if mark.get('price') is not None:
            amount(mark['price'], 'mark_price', 0)
        mark_by_asset[asset] = mark
    audit, timeline, unresolved = [], [], []
    if cash is None:
        unresolved.append({'id': 'opening', 'reason': 'OPENING_CASH_UNKNOWN'})
    if reserve is None:
        unresolved.append({'id': 'opening', 'reason': 'OPENING_TAX_RESERVE_UNKNOWN'})
    prepared = []
    kinds = {'cash_credit', 'cash_debit', 'external_obligation', 'tax_payment', 'reserve_change', 'vest', 'trade'}
    for raw in flows:
        _source(raw, currency)
        day = _day(raw['date'])
        require(day > start, 'FLOW_NOT_AFTER_OPENING_ALREADY_INCLUDED_OR_AMBIGUOUS')
        require(raw.get('state') in STATES, 'EXPLICIT_FLOW_STATE_REQUIRED')
        require(raw.get('kind') in kinds, 'FLOW_KIND_REQUIRED')
        require(type(raw.get('included_in_opening')) is bool and raw['included_in_opening'] is False,
                'FLOW_MUST_EXPLICITLY_BE_EXCLUDED_FROM_OPENING')
        reasons = []
        if day > target:
            reasons.append('AFTER_TARGET_DATE')
        if raw['state'] not in selected:
            reasons.append('STATE_NOT_INCLUDED')
        audit.append({'id': raw['id'], 'date': raw['date'], 'kind': raw['kind'], 'state': raw['state'],
                      'included': not reasons, 'exclusion_reasons': reasons, 'source': deepcopy(raw)})
        if not reasons:
            prepared.append(raw)
    # Date-only inputs do not establish intraday availability. Aggregate each
    # day's deltas before reporting its end balance; id order is for display only.
    for day in sorted({row['date'] for row in prepared}):
        day_cash, day_reserve, unknown_cash, unknown_reserve = ZERO, ZERO, False, False
        changes, applied = {}, []
        for raw in sorted((r for r in prepared if r['date'] == day), key=lambda r: r['id']):
            kind = raw['kind']
            cd, rd, change, detail = ZERO, ZERO, None, None
            if kind in {'cash_credit', 'cash_debit', 'external_obligation', 'tax_payment', 'reserve_change'}:
                value = amount(raw['amount'], 'flow_amount', None if kind == 'reserve_change' else 0) if raw.get('amount') is not None else None
                if kind == 'reserve_change':
                    rd = value
                else:
                    cd = value if kind == 'cash_credit' or value is None else -value
                if kind == 'tax_payment':
                    # Never release an earmark automatically: its relationship
                    # to this payment must be explicit, including explicit zero.
                    release = amount(raw['reserve_release'], 'reserve_release', 0) if raw.get('reserve_release') is not None else None
                    require(value is None or release is None or release <= value, 'RESERVE_RELEASE_EXCEEDS_PAYMENT')
                    rd = -release if release is not None else None
            elif kind == 'vest':
                asset = _text(raw.get('asset_id'), 'asset_id')
                qty = amount(raw['quantity'], 'vest_quantity', 0) if raw.get('quantity') is not None else None
                change = (asset, qty)
            else:
                asset = _text(raw.get('asset_id'), 'asset_id')
                trade = raw.get('trade')
                require(isinstance(trade, dict), 'TRADE_OBJECT_REQUIRED')
                require(trade.get('side') in {'buy', 'sell'}, 'SIDE_REQUIRED')
                require(not any(key in trade for key in ('exit_price', 'budget', 'required_net_proceeds')),
                        'SINGLE_TRADE_NO_SIZING_OR_ROUND_TRIP')
                qty = amount(trade['quantity'], 'trade_quantity', 0) if trade.get('quantity') is not None else None
                change = (asset, qty if trade['side'] == 'buy' or qty is None else -qty)
                needed = ['price', 'quantity', 'entry_orders', 'costs']
                if trade['side'] == 'sell':
                    needed.append('transaction_phase')
                if any(trade.get(key) is None for key in needed):
                    cd = None
                else:
                    detail = trade_costs({**deepcopy(trade), 'currency': currency, 'role': document['role']})
                    cd = amount(detail['sale_net_proceeds']) if trade['side'] == 'sell' else -amount(detail['entry_cash_debit'])
            if cd is None:
                unknown_cash = True
                unresolved.append({'id': raw['id'], 'reason': 'FLOW_CASH_UNKNOWN'})
            else:
                day_cash += cd
            if rd is None:
                unknown_reserve = True
                unresolved.append({'id': raw['id'], 'reason': 'FLOW_RESERVE_UNKNOWN'})
            else:
                day_reserve += rd
            if change:
                asset, qty = change
                previous = changes.get(asset, ZERO)
                changes[asset] = previous + qty if previous is not None and qty is not None else None
            applied.append({'id': raw['id'], 'cash_delta': cd, 'tax_reserve_delta': rd,
                            'asset_quantity_delta': {'asset_id': change[0], 'quantity': change[1]} if change else None,
                            'trade_calculation': detail})
        cash = cash + day_cash if cash is not None and not unknown_cash else None
        reserve = reserve + day_reserve if reserve is not None and not unknown_reserve else None
        require(reserve is None or reserve >= 0, 'TAX_RESERVE_RELEASE_EXCEEDS_RESERVE')
        for asset, qty in changes.items():
            previous = positions.get(asset, ZERO)
            positions[asset] = previous + qty if previous is not None and qty is not None else None
            require(positions[asset] is None or positions[asset] >= 0, 'ASSET_SALE_EXCEEDS_LONG_QUANTITY')
        timeline.append({'date': day, 'cash': cash, 'tax_reserve': reserve,
                         'cash_after_tax_earmark': cash - reserve if cash is not None and reserve is not None else None,
                         'positions': dict(positions), 'applied_flows': applied})
    valued, total = [], ZERO
    for asset, qty in positions.items():
        mark = mark_by_asset.get(asset)
        reasons = []
        if qty is None:
            reasons.append('QUANTITY_UNKNOWN')
        if qty != ZERO:
            if not mark or mark.get('price') is None:
                reasons.append('TARGET_MARK_UNKNOWN')
            elif mark['as_of'] != document['target_date'] and policy != 'carry_forward_supplied':
                reasons.append('MARK_DATE_MISMATCH')
        value = ZERO if qty == ZERO else qty * amount(mark['price']) if not reasons else None
        if value is None:
            total = None
        elif total is not None:
            total += value
        for reason in reasons:
            unresolved.append({'id': asset, 'reason': reason})
        valued.append({'asset_id': asset, 'quantity': qty, 'mark': deepcopy(mark), 'market_value': value,
                       'valuation_basis': 'zero_quantity' if qty == ZERO else 'unresolved' if reasons else
                                          'target_date_supplied_mark' if mark['as_of'] == document['target_date'] else
                                          'explicit_carried_forward_mark_no_return_forecast',
                       'unresolved': reasons})
    def valued_balances(name):
        # Unclassified source balances are retained, never allocated to holdings
        # or treated as cash. Explicit [] means supplied none; omission is unknown.
        if document.get(name) is None:
            unresolved.append({'id': name, 'reason': 'BALANCE_LEDGER_UNKNOWN'})
            return None, []
        balance, details = ZERO, []
        for row in _rows(document[name], name):
            _source(row, currency)
            observed = _day(row['as_of'])
            require(observed <= target, 'BALANCE_AFTER_TARGET')
            value = amount(row['amount'], name + '.amount', 0) if row.get('amount') is not None else None
            reasons = []
            if value is None:
                reasons.append('BALANCE_AMOUNT_UNKNOWN')
            if observed != target and policy != 'carry_forward_supplied':
                reasons.append('BALANCE_DATE_MISMATCH')
            if reasons:
                balance = None
                unresolved.extend({'id': row['id'], 'reason': reason} for reason in reasons)
            elif balance is not None:
                balance += value
            details.append({'source': deepcopy(row), 'value': value if not reasons else None,
                            'valuation_basis': 'unresolved' if reasons else 'target_date_supplied_value'
                                               if observed == target else 'explicit_carried_forward_value_no_return_forecast',
                            'unresolved': reasons})
        return balance, details

    identified = cash + total if cash is not None and total is not None else None
    other, other_details = valued_balances('other_assets')
    liabilities, liability_details = valued_balances('liabilities')
    assets = identified + other if identified is not None and other is not None else None
    equity = assets - liabilities if assets is not None and liabilities is not None else None
    excluded = [row for row in audit if not row['included']]
    return finish(document, 'dated-portfolio-projection', status='UNRESOLVED' if unresolved else 'COMPUTED_CONDITIONAL_PROJECTION',
                  opening_as_of=opening['as_of'], target_date=document['target_date'],
                  retained_input=deepcopy(document), opening_positions=opening_positions,
                  included_states=selected, mark_policy=policy, cash=cash, tax_reserve=reserve,
                  cash_after_tax_earmark=cash - reserve if cash is not None and reserve is not None else None,
                  position_values=valued, total_position_value=total, identified_assets=identified,
                  other_assets_value=other, other_assets_valuations=other_details, total_assets=assets,
                  total_liabilities=liabilities, liability_valuations=liability_details, net_equity=equity,
                  net_equity_reason='Assets less explicitly supplied target liability balances; missing ledgers remain unknown.',
                  unresolved=unresolved, flow_audit=audit, excluded_supplied_flows=excluded, timeline=timeline,
                  supplied_flows_all_included=not excluded, future_returns_inferred=False,
                  limitations=['Conditional end-of-date ledger; dates do not prove intraday liquidity or settlement availability.',
                               'Included flow states are explicit scenarios, not evidence that planned or scenario flows will happen.',
                               'Tax reserves remain assets and reduce only cash after earmark; tax payments reduce assets.',
                               'Vest events add asset units, never cash; a later sale needs its own dated trade and price.',
                               'All supplied flows are audited, including omitted obligations; absent flows are not inferred.',
                               'Other assets retain supplied unclassified residuals without allocation or conversion to cash.',
                               'Liabilities are explicit target balances, not inferred effects of obligations or payments.',
                               'No borrowing permission, account completeness, source freshness or future returns are inferred.'])
