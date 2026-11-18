"""Bound offline fund comparison and deterministic delivery; no execution actions.

A finite report schema, not a verifier of arbitrary host prose or source truth.
Existing source allocation and friction calculations are called unchanged.
"""
from copy import deepcopy
from decimal import Context, Decimal, InvalidOperation, localcontext
from fractions import Fraction
import hashlib
import json

from quant_common import require
from report_facts import strict_json, pointer
from source_exposure import source_allocation_context
from portfolio_decision import friction_context

FIELDS = ('role', 'horizon', 'current_holdings', 'capital_use', 'liquidity', 'loss_tolerance',
          'account_type', 'tax_jurisdiction', 'tax_residency')
TIMELINES = ('proposed_positions', 'future_positions')
LIMITS = [
    'Completeness covers only declared supported source scopes, never all original user intent or external accounts.',
    'Source authenticity is not verified. Byte-bound prose establishes quoted text, not its semantic interpretation.',
    'Issuer overlap uses supplied identities and composition; absent identity or holdings remains unknown.',
    'No overall ranking, forecast, allocation preference or universal holding-period threshold is inferred.',
    'Generated projections are verified exactly; additional free-form host prose is outside this verifier.',
]


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + '\n'


def _hash(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def _clean(value):
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return {k: _clean(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_clean(v) for v in value]
    return value


def _source(source):
    require(isinstance(source, dict) and isinstance(source.get('text'), str), 'WHOLE_SOURCE_TEXT_REQUIRED')
    require(_hash(source['text']) == source.get('sha256'), 'SOURCE_BYTES_HASH_MISMATCH')
    require(isinstance(source.get('id'), str) and source['id'], 'SOURCE_ID_REQUIRED')
    return source['text'].encode('utf-8')


def _context(source):
    raw = _source(source)
    scope = source.get('scope')
    require(isinstance(scope, str) and scope.strip(), 'EXPLICIT_CONTEXT_SCOPE_REQUIRED')
    adapter = source.get('adapter')
    binding = source.get('bindings', {})
    require(isinstance(binding, dict), 'CONTEXT_BINDINGS_OBJECT_REQUIRED')
    complete = adapter == 'fund_report_context_v1' and binding == {'root': ''}
    parsed = None
    if adapter in {'fund_report_context_v1', 'json_pointers_v1'}:
        strict_json(raw)  # duplicate-key/nonfinite validation; never use binary float facts
        parsed = json.loads(raw.decode('utf-8-sig'), parse_float=Decimal, parse_int=Decimal)
        require(isinstance(parsed, dict), 'CONTEXT_OBJECT_REQUIRED')
    if complete:
        require(parsed.get('schema_version') == Decimal(1) and isinstance(parsed['schema_version'], Decimal),
                'CONTEXT_SCHEMA_VERSION_REQUIRED')
    facts = {}
    for field in FIELDS + TIMELINES:
        state, value, location = 'MAPPING_REQUIRED', None, None
        if complete:
            location = '/' + field
            if field not in parsed:
                state = 'NOT_SUPPLIED'
            else:
                value = parsed[field]
                state = 'UNKNOWN_FROM_SOURCE' if value is None else 'SUPPLIED'
        elif adapter == 'json_pointers_v1' and field in binding:
            location = binding[field]
            try:
                value = pointer(parsed, location)
                state = 'UNKNOWN_FROM_SOURCE' if value is None else 'SUPPLIED'
            except (KeyError, ValueError, TypeError, IndexError):
                pass
        elif adapter == 'text_spans_v1' and field in binding:
            span = binding[field]
            require(isinstance(span, dict) and set(span) == {'start', 'end', 'sha256'}, 'EXACT_SPAN_BINDING_REQUIRED')
            start, end = span['start'], span['end']
            require(type(start) is int and type(end) is int and 0 <= start < end <= len(raw), 'INVALID_BYTE_SPAN')
            selected = raw[start:end]
            require(hashlib.sha256(selected).hexdigest() == span['sha256'], 'SPAN_BYTES_HASH_MISMATCH')
            value = selected.decode('utf-8')
            location = deepcopy(span)
            state = 'SUPPLIED_BOUND_SPAN'
        if field in ('current_holdings',) + TIMELINES and state == 'SUPPLIED':
            require(isinstance(value, (list, dict)), 'HOLDINGS_COLLECTION_REQUIRED:' + field)
            if isinstance(value, list):
                require(all(isinstance(row, dict) for row in value), 'HOLDING_OBJECT_REQUIRED')
            if not value:
                state = 'EMPTY_SUPPLIED_COLLECTION'
        elif field in ('current_holdings',) + TIMELINES and state == 'SUPPLIED_BOUND_SPAN':
            state = 'MAPPING_REQUIRED'  # prose is retained, never silently parsed into a portfolio
        facts[field] = {'state': state, 'value': deepcopy(value), 'provenance': [{
            'source_id': source['id'], 'sha256': source['sha256'], 'location': location,
            'adapter': adapter, 'scope': scope}]}
    return scope, facts, complete


def _contexts(sources):
    scopes, coverage = {}, []
    for source in sources:
        scope, facts, complete = _context(source)
        coverage.append({'source_id': source['id'], 'scope': scope, 'whole_supported_inventory': complete})
        target = scopes.setdefault(scope, {})
        for field, fact in facts.items():
            old = target.get(field)
            if old is None:
                target[field] = fact
                continue
            unknown_mapping = {'MAPPING_REQUIRED', 'NOT_SUPPLIED'}
            if old['state'] not in unknown_mapping and fact['state'] not in unknown_mapping:
                require(old['value'] == fact['value'], 'CONFLICTING_CONTEXT_BINDINGS:' + scope + ':' + field)
            if old['state'] in unknown_mapping and fact['state'] not in unknown_mapping:
                fact['provenance'] = old['provenance'] + fact['provenance']
                target[field] = fact
            else:
                old['provenance'].extend(fact['provenance'])
    return scopes, coverage


def _number(value):
    # Resource bounds, not an economic ceiling or a 0..1 holdings validator.
    if isinstance(value, bool) or value is None or len(str(value)) > 128:
        return None
    try:
        number = Decimal(str(value))
        if not number.is_finite() or number < 0 or abs(number.adjusted()) > 100:
            return None
        return number
    except InvalidOperation:
        return None


def _quotes(sources, symbol):
    observations = []
    for source in sources:
        raw = _source(source)
        if source.get('adapter') not in {'portfolio_context_v1', 'explicit_collections_v1'}:
            continue
        parsed = json.loads(raw.decode('utf-8-sig'), parse_float=Decimal, parse_int=Decimal)
        root = source['bindings']['root']
        paths = ([root + '/funds'] if source['adapter'] == 'portfolio_context_v1'
                 else source['bindings'].get('funds', []))
        for path in paths:
            try:
                funds = pointer(parsed, path)
            except (KeyError, ValueError):
                continue
            for index, fund in enumerate(funds):
                if fund.get('symbol') != symbol:
                    continue
                present = 'bid_ask_spread_bps' in fund
                value = fund.get('bid_ask_spread_bps')
                number = _number(value)
                observations.append({'state': 'VALID' if number is not None else 'INVALID' if present and value is not None else 'UNKNOWN',
                    'value': str(number) if number is not None else None, 'raw_value': _clean(value),
                    'source_id': source['id'], 'sha256': source['sha256'],
                    'pointer': path + '/' + str(index) + '/bid_ask_spread_bps',
                    'quote_time': _clean(fund.get('quote_as_of')),
                    'reference_price_basis': fund.get('quote_reference_price_basis')})
    values = {Decimal(o['value']) for o in observations if o['state'] == 'VALID'}
    unresolved = not observations or any(o['state'] != 'VALID' for o in observations) or len(values) != 1
    return {'semantic_kind': 'quoted_full_bid_ask_spread', 'unit': 'bps',
            'status': 'UNRESOLVED' if unresolved else 'SOURCE_BOUND_OBSERVATION',
            'value': None if unresolved else observations[0]['value'], 'observations': observations,
            'execution_cost_inferred': False}


def _fraction(value):
    number = _number(value)
    return None if number is None or number > 1 else Fraction(number)


def _composition(mapped, fund_evidence):
    leaves, gaps = [], []
    def walk(node, weight, path):
        kind = node.get('instrument_type', 'unknown')
        if kind != 'fund':
            leaves.append({'symbol': node.get('symbol'), 'issuer_id': node.get('issuer_id'),
                           'instrument_type': kind, 'share_class': node.get('share_class'),
                           'sector': node.get('sector'), 'industry': node.get('industry'),
                           'total_fund_weight_fraction': str(weight), 'path': path})
            return
        children = (node.get('lookthrough') or {}).get('constituents')
        if children is None:
            gaps.append({'path': path, 'reason': 'FUND_COMPOSITION_UNKNOWN'})
            return
        basis = fund_evidence.get(node.get('symbol'))
        if basis is not None and basis['status'] != 'COMPUTED':
            gaps.append({'path': path, 'reason': basis['reason']})
            return
        weights = ([_fraction(r['total_fund_fraction']['numerator']) for r in basis['rows']]
                   if basis is not None else [_fraction(c.get('weight')) for c in children])
        require(len(weights) == len(children), 'FUND_MEMBERSHIP_EVIDENCE_MISMATCH')
        if any(w is None for w in weights) or sum(weights, Fraction(0)) > 1:
            gaps.append({'path': path, 'reason': 'FUND_WEIGHTS_UNRESOLVED'})
            return
        if sum(weights, Fraction(0)) < 1:
            gaps.append({'path': path, 'reason': 'UNCOVERED_FUND_WEIGHT',
                         'total_fund_weight_fraction': str(weight * (1 - sum(weights, Fraction(0))))})
        for i, (child, child_weight) in enumerate(zip(children, weights)):
            walk(child, weight * child_weight, path + '/' + str(i))
    walk(mapped, Fraction(1), '')
    groups = {}
    for leaf in leaves:
        issuer = leaf['issuer_id']
        if issuer and leaf['instrument_type'] != 'cash':
            groups[issuer] = groups.get(issuer, Fraction(0)) + Fraction(leaf['total_fund_weight_fraction'])
    sector_groups = {}
    for leaf in leaves:
        if leaf.get('sector') and leaf['instrument_type'] != 'cash':
            sector_groups[leaf['sector']] = sector_groups.get(leaf['sector'], Fraction(0)) + Fraction(leaf['total_fund_weight_fraction'])
    return {'leaves': leaves, 'issuer_total_fund_weight_fractions': {k: str(v) for k, v in groups.items()},
            'sector_total_fund_weight_fractions': {k: str(v) for k, v in sector_groups.items()},
            'gaps': gaps, 'known_equity_exposure': any(x['instrument_type'] == 'equity' for x in leaves)}


def _overlap(facts, identities, composition):
    field = facts['current_holdings']
    rows = []
    if field['state'] not in {'SUPPLIED', 'EMPTY_SUPPLIED_COLLECTION'}:
        return {'status': field['state'], 'reason': 'Current holdings are unknown or unmapped, not empty.', 'rows': []}
    holdings = field['value']
    if isinstance(holdings, dict):
        holdings = [{'symbol': symbol, 'source_position_value': deepcopy(value),
                     'position_role': value.get('position_role', 'current') if isinstance(value, dict) else 'current',
                     'source_symbol_conflict': isinstance(value, dict) and 'symbol' in value and value['symbol'] != symbol}
                    for symbol, value in holdings.items()]
    for index, holding in enumerate(holdings):
        symbol = holding.get('symbol')
        identity = identities.get(symbol, {})
        issuer = identity.get('issuer_id')
        reason = None
        if holding.get('source_symbol_conflict'):
            reason = 'HOLDING_MAPPING_SYMBOL_CONFLICT'
        elif holding.get('position_role', 'current') != 'current':
            reason = 'NONCURRENT_RECORD_IN_CURRENT_COLLECTION'
        elif identity.get('instrument_type') == 'cash' or identity.get('kind') == 'cash':
            reason = 'CASH_NOT_DIRECT_ISSUER_EXPOSURE'
        elif identity.get('instrument_type') == 'fund' or identity.get('kind') == 'ETF':
            reason = 'CURRENT_FUND_IS_NOT_A_DIRECT_ISSUER_POSITION'
        elif not issuer:
            reason = 'ISSUER_IDENTITY_UNKNOWN'
        fraction = composition['issuer_total_fund_weight_fractions'].get(issuer)
        rows.append({'source_index': index, 'holding': deepcopy(holding), 'issuer_id': issuer,
                     'status': reason or ('SUPPLIED_ISSUER_OVERLAP' if fraction is not None else
                        'NO_MATCH_IN_KNOWN_COMPOSITION_UNKNOWN_REMAINDER_PRESERVED'),
                     'fund_total_weight_fraction': fraction if reason is None else None,
                     'share_class': identity.get('share_class')})
    return {'status': 'EMPTY_SUPPLIED_COLLECTION' if not rows else 'SOURCE_MEMBERSHIP_RETAINED',
            'rows': rows, 'scope': 'Direct issuer overlap only; no dollar allocation, alternative purchase or absent exposure is inferred.'}


def _assessment(facts, composition, overlap):
    values = {k: deepcopy(facts[k]) for k in ('role', 'horizon', 'capital_use', 'liquidity', 'loss_tolerance')}
    conditions = []
    if composition['known_equity_exposure']:
        conditions.append('Supplied composition establishes equity exposure. Losses can persist through the requested use date; diversification among equities does not establish principal preservation. A longer horizon alone does not guarantee recovery.')
        conditions.append('If the stated role requires reliable capital at the stated horizon, this equity exposure creates a funding shortfall risk. If this is a risk-bearing equity sleeve and loss capacity is sufficient, assess the supplied concentration and current issuer overlap before choosing a role or size.')
    else:
        conditions.append('The supplied composition does not establish equity exposure. Asset-class risk and suitability for the bound role and horizon remain unresolved; do not infer equity merely from fund membership.')
    conditions.append('If capital use is inflexible or loss tolerance is insufficient, market losses may conflict with the requested role and horizon. If use can be deferred and losses absorbed, that conditional risk capacity still does not guarantee recovery or justify an allocation.')
    conditions.append('Liquidity observations concern trading access and friction; they do not establish stable principal at the requested horizon.')
    if composition['issuer_total_fund_weight_fractions']:
        conditions.append('Known issuer and sector weights below describe concentration on a total-fund basis. Shared issuers with current direct holdings can add concentration even across different share classes; unknown composition prevents a complete diversification conclusion.')
    if any(facts[k]['state'] in {'NOT_SUPPLIED', 'UNKNOWN_FROM_SOURCE', 'MAPPING_REQUIRED'} for k in ('capital_use', 'liquidity', 'loss_tolerance')):
        conditions.append('Personal constraints are incomplete. The preceding branches are conditional assessments, not supplied preferences or an unconditional selection.')
    return {'bound_context': values, 'conditional_assessment': conditions,
            'known_issuer_total_fund_weights': composition['issuer_total_fund_weight_fractions'],
            'known_sector_total_fund_weights': composition['sector_total_fund_weight_fractions'],
            'current_holdings_overlap': overlap, 'ranking': None}


# These names have declared semantics in portfolio_context_v1. Other names remain
# raw observations; no unit, period, benchmark or currency is guessed for them.
METRICS = {
    'annual_expense_ratio': ('fraction', 'annual'),
    'average_daily_dollar_volume': ('currency_per_day', 'daily_average_unspecified_lookback'),
    'tracking_difference_last_year': ('signed_return_fraction', 'last_year'),
    'distribution_yield': ('distribution_fraction', None),
}


def _metric_number(value, signed=False):
    if isinstance(value, bool) or value is None or len(str(value)) > 128:
        return None
    try:
        number = Decimal(str(value))
        if not number.is_finite() or abs(number.adjusted()) > 100 or (number < 0 and not signed):
            return None
        return number
    except InvalidOperation:
        return None


def _scaled(number, factor):
    with localcontext(Context(prec=512)):
        return str(number * Decimal(factor))


def _exact_fund_record(sources, binding):
    original = next(s for s in sources if s['id'] == binding['source_id'])
    raw = _source(original)
    require(original['sha256'] == binding['source_bytes_sha256'], 'FUND_SOURCE_BINDING_HASH')
    exact = json.loads(raw.decode('utf-8-sig'), parse_float=Decimal, parse_int=Decimal)
    return _clean(pointer(exact, binding['pointer']))


def _metric_facts(sources, symbol):
    observations = {name: [] for name in METRICS}
    tax_character = []
    for source in sources:
        if source.get('adapter') not in {'portfolio_context_v1', 'explicit_collections_v1'}:
            continue
        raw = _source(source)
        parsed = json.loads(raw.decode('utf-8-sig'), parse_float=Decimal, parse_int=Decimal)
        root_path = source['bindings']['root']; root = pointer(parsed, root_path)
        paths = ([root_path + '/funds'] if source['adapter'] == 'portfolio_context_v1'
                 else source['bindings'].get('funds', []))
        for path in paths:
            try:
                records = pointer(parsed, path)
            except (KeyError, ValueError):
                continue
            for index, record in enumerate(records):
                if record.get('symbol') != symbol:
                    continue
                base = {'source_id': source['id'], 'sha256': source['sha256'],
                        'record_pointer': path + '/' + str(index)}
                for name, (unit, default_period) in METRICS.items():
                    raw_value = record.get(name)
                    value = _metric_number(raw_value, signed=name.startswith('tracking_'))
                    period = record.get(name + '_period', default_period)
                    item = {**base, 'pointer': base['record_pointer'] + '/' + name,
                        'state': 'SUPPLIED' if value is not None else 'INVALID' if name in record and raw_value is not None else 'NOT_SUPPLIED',
                        'value': str(value) if value is not None else None,
                        'raw_value': _clean(raw_value), 'unit': unit, 'period': _clean(period),
                        'observed_as_of': _clean(root.get('as_of')),
                        'currency': root.get('currency') if name == 'average_daily_dollar_volume' else None,
                        'benchmark': record.get('benchmark') if name.startswith('tracking_') else None}
                    if value is not None and name != 'average_daily_dollar_volume':
                        item['percent'] = _scaled(value, '100')
                        item['basis_points'] = _scaled(value, '10000')
                    observations[name].append(item)
                tax_character.append({**base, 'value': _clean(record.get('distribution_tax_character')),
                    'pointer': base['record_pointer'] + '/distribution_tax_character'})
    metrics = {}
    for name, items in observations.items():
        keys = {(x['value'], x['unit'], _json(x['period']), x['currency'], _json(x['benchmark']), _json(x['observed_as_of']))
                for x in items if x['state'] == 'SUPPLIED'}
        resolved = bool(items) and all(x['state'] == 'SUPPLIED' for x in items) and len(keys) == 1
        metrics[name] = {'status': 'SOURCE_BOUND_OBSERVATION' if resolved else 'UNRESOLVED',
                         'fact': deepcopy(items[0]) if resolved else None, 'observations': items}
    return {'metrics': metrics, 'distribution_tax_character': tax_character,
        'interpretations': {
            'fees': 'The annual expense ratio is recurring fund expense drag, not an execution charge or a forecast of net return. A lower expense observation alone is not an overall recommendation.',
            'liquidity': 'The full bid-ask quote describes quoted width; supplied average daily dollar volume describes trading activity in its stated currency. Quote size/time, volume lookback, market impact and execution reference can be unknown. Neither observation guarantees execution or stable principal.',
            'tracking': 'Tracking difference is the supplied fund-versus-benchmark return difference for its stated period, not tracking-error volatility or a forecast. Different benchmark identities prevent a like-for-like tracking-quality ranking. Expenses may already be reflected; do not subtract the expense ratio again without a defined return basis.',
            'distributions': 'Distribution yield is a cash-distribution observation, not total return, guaranteed income or evidence of superior performance. Period and tax character may be unknown; a larger distribution is not automatically an economic gain.',
            'tax': 'Tax suitability depends on account type, jurisdiction/residency and distribution character. Taxable distributions may affect current tax cash flow, while sheltered-account treatment can differ. Unknown character or account rules prevent a specific tax-efficiency ranking; no tax rate or tax liability is inferred.'}}


def _pair_comparisons(funds):
    comparisons = []
    for i, left in enumerate(funds):
        for right in funds[i+1:]:
            facts = {}
            for name in METRICS:
                a = left['separate_observations']['metrics'][name]['fact']
                b = right['separate_observations']['metrics'][name]['fact']
                result = {'left': deepcopy(a), 'right': deepcopy(b), 'status': 'UNKNOWN_COMPARABILITY',
                          'numeric_relation': None, 'overall_preference_inferred': False}
                if a and b:
                    av, bv = Decimal(a['value']), Decimal(b['value'])
                    if name == 'annual_expense_ratio' and a['period'] == b['period'] == 'annual':
                        result['status'] = 'ANNUAL_EXPENSE_OBSERVATIONS_COMPARABLE'
                        result['numeric_relation'] = 'equal' if av == bv else 'left_lower' if av < bv else 'right_lower'
                        with localcontext(Context(prec=512)):
                            result['right_minus_left_basis_points'] = str((bv - av) * Decimal(10000))
                        result['meaning'] = 'Expense drag only; other differences and future net returns remain separate.'
                    elif name == 'average_daily_dollar_volume':
                        if a['currency'] and a['currency'] == b['currency'] and a['observed_as_of'] and a['observed_as_of'] == b['observed_as_of']:
                            result['status'] = 'SAME_CURRENCY_DATED_VOLUME_OBSERVATIONS'
                            result['numeric_relation'] = 'equal' if av == bv else 'left_larger' if av > bv else 'right_larger'
                            result['meaning'] = 'Supplied daily activity comparison; equal lookback, future depth, capacity and impact are not established.'
                        else:
                            result['meaning'] = 'Currency or observation-date comparability is missing or mismatched; no FX or temporal equivalence is invented.'
                    elif name == 'tracking_difference_last_year':
                        if a['benchmark'] and b['benchmark'] and a['benchmark'] != b['benchmark']:
                            result['status'] = 'DIFFERENT_BENCHMARKS_NO_TRACKING_QUALITY_RANK'
                        elif a['benchmark'] and a['benchmark'] == b['benchmark'] and a['period'] == b['period'] and a['observed_as_of'] and a['observed_as_of'] == b['observed_as_of']:
                            result['status'] = 'SAME_BENCHMARK_PERIOD_OBSERVATIONS'
                            result['numeric_relation'] = 'equal' if av == bv else 'left_higher' if av > bv else 'right_higher'
                        result['meaning'] = 'Observed tracking difference only, not tracking error, a forecast or expense-adjusted performance reconstructed a second time.'
                    elif name == 'distribution_yield':
                        if a['period'] is not None and a['period'] == b['period'] and a['observed_as_of'] and a['observed_as_of'] == b['observed_as_of']:
                            result['status'] = 'SAME_PERIOD_DISTRIBUTION_OBSERVATIONS'
                            result['numeric_relation'] = 'equal' if av == bv else 'left_larger' if av > bv else 'right_larger'
                        result['meaning'] = 'Cash distributions only; unknown period or tax character blocks stronger comparison, and distributions are not total return.'
                facts[name] = result
            aq, bq = left['quote'], right['quote']
            quote_pair = {'left': deepcopy(aq), 'right': deepcopy(bq), 'status': 'UNKNOWN_COMPARABILITY',
                          'numeric_relation': None, 'execution_cost_inferred': False,
                          'meaning': 'Reported full quote width only; reference prices, timestamps and executable size may differ or be unknown. No modeled cost or execution-quality ranking follows.'}
            if aq['status'] == bq['status'] == 'SOURCE_BOUND_OBSERVATION':
                av, bv = Decimal(aq['value']), Decimal(bq['value'])
                quote_pair['status'] = 'REPORTED_BPS_WIDTH_OBSERVATIONS_ONLY'
                quote_pair['numeric_relation'] = 'equal' if av == bv else 'left_narrower' if av < bv else 'right_narrower'
            facts['quoted_full_bid_ask_spread'] = quote_pair
            comparisons.append({'left_symbol': left['symbol'], 'right_symbol': right['symbol'],
                                'criteria': facts, 'overall_ranking': None})
    return comparisons


def build_report(document):
    require(isinstance(document, dict), 'DOCUMENT_OBJECT_REQUIRED')
    require(set(document) <= {'schema_version', 'currency', 'request', 'context_sources', 'exposure_sources', 'friction_models'}, 'UNSUPPORTED_REPORT_INPUT_FIELD')
    require(document.get('schema_version') == 1 and type(document['schema_version']) is int, 'REPORT_SCHEMA_VERSION_REQUIRED')
    require(isinstance(document.get('currency'), str) and document['currency'], 'CURRENCY_REQUIRED')
    request = document.get('request')
    require(isinstance(request, dict), 'WHOLE_ORIGINAL_REQUEST_REQUIRED')
    contexts = [request] + document.get('context_sources', [])
    exposure_sources = document.get('exposure_sources')
    require(isinstance(exposure_sources, list) and exposure_sources, 'EXPOSURE_SOURCES_REQUIRED')
    ids = [s.get('id') for s in contexts + exposure_sources]
    require(len(ids) == len(set(ids)), 'UNIQUE_SOURCE_IDS_REQUIRED')
    scopes, context_inventory = _contexts(contexts)
    # Empty gross rows intentionally make no invented account allocation. The
    # existing operation still consumes all declared identities/fund holdings.
    exposure = source_allocation_context({'schema_version': 1, 'currency': document['currency'],
        'role': 'supplied_observation', 'denominator': {}, 'rows': [], 'sources': exposure_sources})
    identities = {x['symbol']: x['values'] for x in exposure['identity_context']}
    models = document.get('friction_models', {})
    require(isinstance(models, dict), 'FRICTION_MODELS_OBJECT_REQUIRED')
    funds = []
    symbols = {x['symbol'] for x in exposure['fund_context']}
    require(set(models) <= symbols, 'MODEL_FOR_UNDECLARED_FUND')
    for fund in exposure['fund_context']:
        symbol = fund['symbol']
        quote = _quotes(exposure_sources, symbol)
        model = models.get(symbol)
        if model is None:
            native_input = {'currency': document['currency'], 'role': 'supplied_observation',
                            'price_basis': 'unknown', 'modeled_slippage': None, 'costs': None}
            assumptions = None
        else:
            require(set(model) == {'scenario_name', 'input'} and isinstance(model['scenario_name'], str) and model['scenario_name'].strip(), 'NAMED_MODEL_SCENARIO_REQUIRED')
            native_input = deepcopy(model['input'])
            require(native_input.get('role') in {'hypothetical_scenario', 'user_assumption'}, 'EXPLICIT_MODEL_ASSUMPTION_ROLE_REQUIRED')
            require(native_input.get('currency') == document['currency'], 'MODEL_CURRENCY_MISMATCH')
            require('quoted_spread' not in native_input, 'QUOTE_MUST_COME_FROM_SOURCE')
            assumptions = model['scenario_name']
        if quote['status'] == 'SOURCE_BOUND_OBSERVATION':
            native_input['quoted_spread'] = {'amount': quote['value'], 'unit': 'bps'}
        native = friction_context(native_input)
        composition = _composition({**fund['mapped_context'], 'symbol': symbol},
            {x['symbol']: x['weight_basis_evidence'] for x in exposure['fund_context']})
        assessments = {}
        for scope, facts in scopes.items():
            overlap = _overlap(facts, identities, composition)
            assessments[scope] = _assessment(facts, composition, overlap)
        funds.append({'symbol': symbol, 'source_record': _exact_fund_record(exposure_sources, fund['source_binding']),
            'source_binding': fund['source_binding'], 'weight_basis_evidence': fund['weight_basis_evidence'],
            'composition': composition, 'quote': quote, 'friction': native,
            'separate_observations': _metric_facts(exposure_sources, symbol),
            'friction_assumption': assumptions, 'assessment_by_scope': assessments,
            'position_scope': 'Compared fund observation; current ownership only from bound current holdings.'})
    ready = bool(funds) and all(x['whole_supported_inventory'] for x in context_inventory)
    ready = ready and exposure['complete_context_receipt']['all_declared_collections_consumed'] is True
    ready = ready and not exposure['mapping_conflicts']
    ready = ready and all(f['state'] != 'MAPPING_REQUIRED' for facts in scopes.values() for f in facts.values())
    return _clean({'schema_version': 1, 'method': 'bound-fund-comparison-report-1',
        'status': 'COMPLETE_FOR_BOUND_SCOPE' if ready else 'PARTIAL_BOUND_REPORT',
        'currency': document['currency'], 'input_sha256': _hash(_json(document)),
        'retained_input': deepcopy(document), 'contexts': scopes, 'context_inventory': context_inventory,
        'funds': funds, 'criterion_comparisons': _pair_comparisons(funds),
        'source_exposure': exposure, 'limitations': list(LIMITS),
        'advisory_only': True, 'source_authenticity_verified': False})


def _display(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False)


def _render(report, compact=False):
    lines = ['# Bound fund comparison', 'Delivery status: ' + report['status']]
    for scope, facts in report['contexts'].items():
        lines += ['## Context: ' + _display(scope)]
        for field, fact in facts.items():
            lines.append(field + ': ' + fact['state'] + '; ' + _display(fact['value']))
    for fund in report['funds']:
        lines += ['## Fund: ' + _display(fund['symbol']), fund['position_scope'],
                  'Full bid-ask quote observation (bps): ' + _display(fund['quote']),
                  'Execution model: ' + fund['friction']['status'] + '; named assumption: ' + _display(fund['friction_assumption']),
                  'Native applied costs (only explicit model; no quote conversion): ' + _display(fund['friction']['applied_costs']),
                  'Native unresolved reasons: ' + _display(fund['friction']['unresolved']),
                  'Composition and unknown remainder: ' + _display(fund['composition']),
                  'Denominator evidence: ' + _display(fund['weight_basis_evidence'])]
        for scope, assessment in fund['assessment_by_scope'].items():
            lines += ['### Conditional role/horizon assessment: ' + _display(scope),
                      'Bound role: ' + _display(assessment['bound_context']['role']),
                      'Bound horizon: ' + _display(assessment['bound_context']['horizon'])]
            lines += assessment['conditional_assessment']
            lines += ['Current holdings overlap: ' + _display(assessment['current_holdings_overlap'])]
        for label, interpretation in fund['separate_observations']['interpretations'].items():
            lines.append(label + ': ' + interpretation)
        lines.append('Source-bound separate metric facts: ' + _display(fund['separate_observations']['metrics']))
        lines.append('Distribution tax character: ' + _display(fund['separate_observations']['distribution_tax_character']))
        # Preserve independent fees/tracking/distribution observations without
        # turning raw fields into returns, rankings, or applied execution costs.
        lines.append('Retained separate source observations (not derived costs, returns or rankings): ' + _display(fund['source_record']))
    lines += ['## Criterion-specific comparisons (no overall ranking)', _display(report['criterion_comparisons'])]
    if not compact:
        lines += ['## Source denominator labels', report['source_exposure']['fund_weight_report']]
    lines += ['## Limits'] + report['limitations']
    return '\n\n'.join(lines) + '\n'


def render_report(report):
    # Regeneration binds every field to the original corpus: editing the
    # canonical object cannot remove known holdings/horizon and retain status.
    expected = build_report(report['retained_input'])
    require(report == expected, 'CANONICAL_REPORT_DOES_NOT_MATCH_BOUND_INPUT')
    return {'markdown': _render(report), 'structured_json': _json(report), 'summary': _render(report, compact=True)}


def fund_comparison_report(document):
    report = build_report(document)
    artifacts = render_report(report)
    return {'report': report, 'artifacts': artifacts,
            'artifact_sha256': {key: _hash(value) for key, value in artifacts.items()}}


def verify_delivery(document, delivery):
    require(delivery == fund_comparison_report(document), 'DELIVERY_DOES_NOT_MATCH_REGENERATED_REPORT')
    return {'status': 'VERIFIED_GENERATED_PROJECTIONS', 'additional_host_prose_verified': False}
