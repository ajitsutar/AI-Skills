"""Canonical source-backed employer diversification references, never recommendations."""
from copy import deepcopy
from datetime import date
from decimal import Context, Decimal, localcontext
import hashlib

from planning_alignment import amount, finish, trade_costs
from planning_comparison import source_alternatives
from portfolio_projection import source_projection, _precision
from quant_common import require


def employer_diversification_baseline(document):
    """Compose three fixed reference paths from checked original UTF-8 source text.

    Required: currency,role,source_utf8,source_sha256,source_ref,source_role.
    Optional source must equal parsed source_utf8. Optional opening_date requires
    opening_date_basis and opening_date_role=user_assumption. included_states,
    if supplied, is explicit; otherwise confirmed/planned/scenario are included
    as conditional references, never authenticated event outcomes.
    """
    text = document.get('source_utf8')
    require(isinstance(text, str), 'ORIGINAL_SOURCE_UTF8_REQUIRED')
    raw = text.encode('utf-8')
    sha = hashlib.sha256(raw).hexdigest()
    require(document.get('source_sha256') == sha, 'ORIGINAL_SOURCE_UTF8_HASH_MISMATCH')
    from report_facts import strict_json
    source = strict_json(raw)
    require(isinstance(source, dict), 'SOURCE_OBJECT_REQUIRED')
    require('source' not in document or document['source'] == source, 'SOURCE_OBJECT_DIFFERS_FROM_CHECKED_UTF8')
    currencies = [source[k] for k in ('currency', 'base_currency') if k in source]
    require(currencies and all(value == document.get('currency') for value in currencies), 'SOURCE_CURRENCY_MISMATCH_NO_FX')
    require(isinstance(document.get('source_ref'), str) and document['source_ref'].strip(), 'SOURCE_REF_REQUIRED')
    require(document.get('source_role') in {'supplied_observation', 'hypothetical_scenario', 'user_assumption', 'unknown'},
            'SOURCE_ROLE_REQUIRED')
    with localcontext(Context(prec=64 + _precision(document) + _precision(source))):
        return _baseline(document, source, sha)


def _baseline(document, original, sha):
    source = deepcopy(original)
    def day(value):
        require(isinstance(value, str), 'SOURCE_CALENDAR_LABEL_REQUIRED')
        return date.fromisoformat(value[:10]).isoformat()
    opening = day(source.get('as_of'))
    opening_binding = {'date': opening, 'role': document['source_role'], 'basis': 'Original source as_of calendar label.'}
    if 'opening_date' in document:
        require(document.get('opening_date_role') == 'user_assumption' and
                isinstance(document.get('opening_date_basis'), str) and document['opening_date_basis'].strip(),
                'EXPLICIT_OPENING_DATE_ASSUMPTION_REQUIRED')
        opening = day(document['opening_date'])
        source['as_of'] = opening
        opening_binding = {'date': opening, 'role': 'user_assumption', 'basis': document['opening_date_basis'],
                           'limitation': 'Source balances are carried to the user-bound opening date, not observed anew.'}
    baseline = source.get('baseline_rebalance')
    employer = source.get('employer')
    require(isinstance(baseline, dict) and isinstance(employer, dict), 'PORTFOLIO_AND_EMPLOYER_SOURCE_REQUIRED')
    symbol = employer.get('symbol')
    require(isinstance(symbol, str) and symbol.strip(), 'EMPLOYER_SYMBOL_REQUIRED')
    holdings = baseline.get('holdings')
    require(isinstance(holdings, dict), 'SOURCE_HOLDINGS_LEDGER_REQUIRED')
    current = amount(holdings[symbol], 'direct_units', 0) if holdings.get(symbol) is not None else None
    if current is None:
        # The stated employer symbol supplies the asset identity, but no missing
        # opening quantity is filled from grants or the separate employer field.
        source['baseline_rebalance']['holdings'][symbol] = None
    declared = employer.get('current_vested_quantity')
    mismatch = declared is not None and current is not None and amount(declared, 'employer_declared_units', 0) != current
    if mismatch:
        # Neither conflicting source observation silently wins. Propagate the
        # conflict through holdings and sale units while retaining original bytes.
        source['baseline_rebalance']['holdings'][symbol] = None
        current = None
    selected = document.get('included_states', ['confirmed', 'planned', 'scenario'])
    require(isinstance(selected, list) and len(selected) == len(set(selected)) and
            all(x in {'confirmed', 'planned', 'scenario'} for x in selected), 'EXPLICIT_INCLUDED_STATES_REQUIRED')
    grants, included = [], []
    for index, grant in enumerate(employer.get('grant_records', [])):
        require(isinstance(grant, dict), 'SOURCE_GRANT_OBJECT_REQUIRED')
        vest_date = day(grant.get('vest_date'))
        units = [amount(grant[k], k, 0) if grant.get(k) is not None else None
                 for k in ('gross_shares', 'shares_withheld_for_tax', 'shares_sold_for_tax')]
        net = units[0] - units[1] - units[2] if all(x is not None for x in units) else None
        require(net is None or net >= 0, 'TAX_SHARES_EXCEED_GRANT')
        mark = amount(grant['assumed_vest_price'], 'source_vest_price', 0) if grant.get('assumed_vest_price') is not None else None
        state = 'planned' if grant.get('status') == 'future_scheduled' else 'unknown'
        active = state in selected and vest_date > opening
        row = {'source_index': index, 'date': vest_date, 'state': state, 'included': active,
               'gross_shares': units[0], 'withheld_tax_shares': units[1], 'sold_tax_shares': units[2],
               'net_retained_shares': net, 'source_vest_price_assumption': mark,
               'source_gross_grant_valuation': units[0] * mark if units[0] is not None and mark is not None else None,
               'source_net_grant_valuation': net * mark if net is not None and mark is not None else None,
               'source_ref': document['source_ref'] + '/employer/grant_records/' + str(index),
               'original_grant': deepcopy(grant)}
        grants.append(row)
        if active:
            included.append(row)
    included.sort(key=lambda row: (row['date'], row['source_index']))
    target = max((row['date'] for row in included), default=opening)
    require(all(row['date'] > opening for row in grants), 'SOURCE_GRANTS_ALREADY_IN_OPENING_UNRESOLVED')
    price = baseline.get('prices', {}).get(symbol)
    if price is not None:
        price = amount(price, 'opening_employer_mark', 0)
    cost_source = source.get('cost_assumptions', {})
    require(isinstance(cost_source, dict), 'SOURCE_COST_ASSUMPTIONS_OBJECT_REQUIRED')
    fee, slippage = cost_source.get('fee_per_trade'), cost_source.get('one_way_slippage_bps')
    costs = None if fee is None or slippage is None else [
        {'id': 'source-fee', 'unit': 'per_order', 'phase': 'each_side', 'amount': str(amount(fee, 'fee', 0))},
        {'id': 'source-slippage', 'unit': 'bps_notional', 'phase': 'each_side', 'amount': str(amount(slippage, 'slippage', 0))}]
    common = {'currency': document['currency'], 'role': document['role'], 'source': source,
              'source_ref': document['source_ref'], 'source_role': document['source_role'],
              'date_basis': 'source_calendar_label', 'target_date': target, 'included_states': selected,
              'mark_policy': 'carry_forward_supplied', 'opening_tax_reserve': baseline.get('tax_reserve'),
              'other_assets': deepcopy(source.get('other_assets')), 'liabilities': deepcopy(source.get('liabilities'))}
    def paths(sale_basis):
        receipts = []
        vest_sales = []
        def sale(identifier, sale_date, units, sale_price, pointer):
            if units == 0:
                return None
            trade = {'side': 'sell', 'price': str(sale_price) if sale_price is not None and sale_price > 0 else None,
                     'quantity': str(units) if units is not None else None, 'entry_orders': 1,
                     'transaction_phase': 'exit', 'costs': deepcopy(costs)}
            receipt = trade_costs({**trade, 'currency': document['currency'], 'role': document['role']}) if all(
                trade[k] is not None for k in ('price', 'quantity', 'costs')) else None
            receipts.append({'id': identifier, 'date': sale_date, 'sale_price_basis': sale_basis,
                             'quantity': units, 'sale_price': sale_price, 'trade_cost_receipt': receipt,
                             'incremental_sale_tax': None, 'tax_status': 'Unknown cost-gain treatment, tax selection and prior reserve.'})
            return {'id': identifier, 'date': sale_date, 'state': 'scenario', 'kind': 'trade',
                    'asset_id': symbol, 'currency': document['currency'], 'source_role': 'user_assumption',
                    'source_ref': document['source_ref'] + pointer + '/reference-sale',
                    'included_in_opening': False, 'trade': trade}
        for grant in included:
            sale_price = price if sale_basis == 'opening_mark_no_price_change' else grant['source_vest_price_assumption']
            flow = sale('reference-vest-sale-' + str(grant['source_index']), grant['date'],
                        grant['net_retained_shares'], sale_price, '/employer/grant_records/' + str(grant['source_index']))
            if flow is not None:
                vest_sales.append(flow)
        direct_date = included[0]['date'] if included else None
        direct_sale = sale('reference-direct-sale', direct_date, current, price, '/baseline_rebalance/holdings/' + symbol) if direct_date else None
        alternatives = [{'id': 'retain', 'scenario_flows': []},
                        {'id': 'sell_all_net_vests', 'scenario_flows': deepcopy(vest_sales)},
                        {'id': 'sell_all_direct_and_net', 'scenario_flows': ([direct_sale] if direct_sale else []) + deepcopy(vest_sales)}]
        if not included:
            return {'status': 'NO_INCLUDED_FUTURE_VEST_DATE', 'alternatives': None, 'sale_receipts': receipts,
                    'limitation': 'No future supplied reference sale date is invented; opening retained projection is separate.'}
        comparison = source_alternatives({**common, 'alternatives': alternatives})
        sensitivity_common = deepcopy(common)
        sensitivity_common.update(opening_tax_reserve=0, liabilities=[], other_assets=None,
                                  residual_policy='carry_opening_reconciliation_difference')
        try:
            sensitivity = source_alternatives({**sensitivity_common, 'alternatives': alternatives})
        except ValueError as exc:
            # A negative/unknown asset discrepancy cannot be manufactured into
            # a positive residual; retain primary output and disclose the limit.
            sensitivity = {'status': 'UNRESOLVED', 'reason': str(exc)}
        return {'status': 'COMPUTED_CONDITIONAL_REFERENCES', 'alternatives': comparison,
                'sale_receipts': receipts, 'direct_sale_date_convention': 'First included supplied vest date.',
                'denominator_sensitivity': {'name': 'carry_residual_no_liabilities_no_prior_tax_reserve',
                    'primary': False, 'assumptions': ['Carry nonnegative opening reconciliation residual as unclassified assets.',
                    'Assume no target liabilities and no prior tax earmark for this sensitivity only.',
                    'No incremental sale-tax payment or earmark is inferred; values are before unknown discretionary-sale tax.'],
                    'comparison': sensitivity}}
    primary = paths('opening_mark_no_price_change')
    sensitivity = paths('source_vest_price_sales_same_opening_target_marks')
    retained = source_projection(common)
    return finish(document, 'employer-diversification-baseline',
                  status='DATED_ALTERNATIVES_COMPARED' if included else primary['status'],
                  source_sha256_checked=sha, source_utf8_byte_count=len(document['source_utf8'].encode('utf-8')),
                  original_source_retained=True, source_authentication_inferred=False,
                  opening_binding=opening_binding, target_date=target, included_states=selected,
                  reference_convention='Opening marks for all target position values and baseline sale prices; no price change assumption, not a forecast.',
                  execution_convention='One hypothetical sale transaction per included net vest; opening direct units sold on first included vest date.',
                  grant_valuations=grants, direct_quantity_conflict=mismatch, direct_quantity_unknown=current is None,
                  primary_result=primary['alternatives'],
                  denominator_sensitivity=primary.get('denominator_sensitivity'),
                  source_vest_price_sensitivity=sensitivity['alternatives'],
                  source_vest_price_sensitivity_is_primary=False,
                  source_vest_price_denominator_sensitivity=sensitivity.get('denominator_sensitivity'),
                  baseline_sale_receipts=primary['sale_receipts'], source_vest_sale_receipts=sensitivity['sale_receipts'],
                  retained_projection=retained, selected_alternative=None, objective_weights=None,
                  employment_dependency=employer.get('salary_dependency'), source_tax_lots=deepcopy(source.get('tax_lots')),
                  source_tax_rate_assumptions=deepcopy(employer.get('tax_rate_assumptions')),
                  retained_input=deepcopy(document),
                  limitations=['Canonical paths are analytical references, not preferred trades or execution conditions.',
                               'Known grant tax-share dispositions do not establish final tax adequacy or incremental sale tax.',
                               'Unspecified reserve, residual, liabilities, sale price and costs remain unknown in primary results.',
                               'Date-only vest/sale aggregation does not establish intraday settlement, transfers or spendability.',
                               'Proposed transactions, recurring purchases and alternative user scenarios are not substituted into this fixed reference.',
                               'Observed cross-model differences from different sale quantities or prices remain unresolved until compared on the same convention.'])
