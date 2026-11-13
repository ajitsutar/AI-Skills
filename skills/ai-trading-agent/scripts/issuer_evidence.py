"""Deterministic business evidence from a pinned, bounded disclosure schema.

The adapter binds original roles, not caller-supplied numbers or conclusions.
Its reports are diagnostic research, not authenticated filings or a complete
contract interpretation. Unknown dates and definitions remain unknown.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal, localcontext
import hashlib
import json
import re

from source_claims import Corpus
from source_lineage import at, parse

METHOD = 'issuer-evidence-1'
TOPICS = ('funding', 'cash_conversion', 'dilution', 'business_position',
          'capital_allocation', 'valuation_objective')
MONITORING = {
    'funding': 'Review maturity funding, operating cash needs and financing terms as new evidence arrives.',
    'cash_conversion': 'Review cash conversion, reinvestment and recurring adjustments over comparable periods.',
    'dilution': 'Review dated share changes and compensation economics without assuming their cause.',
    'business_position': 'Review customer concentration, contract terms and comparable competitive evidence.',
    'capital_allocation': 'Review distributions, acquisitions and their opportunity costs against funding needs.',
    'valuation_objective': 'Review the named valuation objective and its assumptions; a terminal return is not DCF discount closure.',
}
TOKEN = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.:-]{0,79}\Z')
# Paths are roles in the supported original disclosure schema, not caller aliases.
FLOW = {
    'revenue': '/revenue', 'revenue_prior': '/revenue_prior', 'gross_profit': '/gross_profit',
    'interest': '/interest_expense', 'tax': '/income_tax_expense',
    'depreciation': '/cfo_reconciliation_items/depreciation_amortization',
    'stock_compensation': '/cfo_reconciliation_items/stock_compensation',
    'working_capital_change': '/cfo_reconciliation_items/working_capital_change',
    'maintenance_capex': '/capex_detail/maintenance', 'growth_capex': '/capex_detail/growth',
    'acquisitions': '/capital_allocation/acquisitions_cash_paid',
    'dividends': '/capital_allocation/dividends_paid', 'buybacks': '/capital_allocation/buybacks',
    'restructuring': '/expense_disclosures/restructuring',
    'integration_expense': '/expense_disclosures/acquisition_integration',
}
RAW = {'cash': 'cash', 'debt': 'debt', 'ebit': 'ebit_ttm', 'net_income': 'net_income_ttm',
       'cfo': 'cfo_ttm', 'capex': 'capex_ttm', 'market_cap': 'market_cap',
       'preferred_equity': 'preferred_equity', 'noncontrolling_interest': 'noncontrolling_interest'}


def require(ok, code):
    if not ok:
        raise ValueError(code)


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False,
                      allow_nan=False).encode('utf-8')


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def number(value):
    require(not isinstance(value, bool) and isinstance(value, (int, float, Decimal)),
            'ORIGINAL_NUMERIC_TOKEN_REQUIRED')
    result = Decimal(str(value))
    require(result.is_finite(), 'FINITE_NUMBER_REQUIRED')
    require(len(result.as_tuple().digits) <= 50 and (not result or abs(result.adjusted()) <= 100),
            'NUMERIC_RANGE_UNSUPPORTED')
    return result


def numeric_text(value):
    # Fixed-point strings keep source precision; ratios use 260-digit Decimal
    # context. No binary float adaptation or unit rescaling occurs.
    return format(value, 'f') if value is not None else None


def json_value(value):
    if isinstance(value, Decimal):
        return numeric_text(value)
    if isinstance(value, dict):
        return {k: json_value(v) for k, v in value.items()}
    if isinstance(value, list):
        return [json_value(v) for v in value]
    return value


def valid_date(value):
    if value is None:
        return None
    require(isinstance(value, str) and re.fullmatch(r'\d{4}-\d{2}-\d{2}', value), 'ISO_DATE_REQUIRED')
    return date.fromisoformat(value).isoformat()


def optional(record, pointer):
    try:
        return at(record, pointer)
    except (KeyError, IndexError, ValueError, TypeError):
        return None


class Disclosure:
    def __init__(self, corpus, ref):
        require(isinstance(ref, dict) and ref.get('source_id') in corpus.sources, 'ORIGINAL_RECORD_REQUIRED')
        source = corpus.sources[ref['source_id']]
        if set(ref) == {'source_id', 'pointer'}:
            require(source['format'] == 'json', 'STRUCTURED_ORIGINAL_REQUIRED')
            doc = source['document']
        else:
            require(set(ref) == {'source_id', 'start', 'end', 'excerpt', 'pointer'}, 'RECORD_REFERENCE_FIELDS')
            corpus.resolve({k: v for k, v in ref.items() if k != 'pointer'})
            doc = parse(ref['excerpt'])
        require(isinstance(ref['pointer'], str), 'RECORD_POINTER_REQUIRED')
        record = at(doc, ref['pointer'])
        require(isinstance(record, dict) and isinstance(record.get('raw_snapshot_facts'), dict),
                'FINANCIAL_DISCLOSURE_SCHEMA_REQUIRED')
        require(isinstance(record.get('symbol'), str) and TOKEN.fullmatch(record['symbol']), 'ORIGINAL_ISSUER_ID_REQUIRED')
        self.record, self.ref, self.source = record, dict(ref), source
        self.symbol = record['symbol']
        self.currency = record.get('currency')
        require(self.currency is None or isinstance(self.currency, str) and
                re.fullmatch('[A-Z]{3}', self.currency), 'ORIGINAL_CURRENCY_INVALID')
        self.facts = {}

    def ref_at(self, path):
        return {**self.ref, 'pointer': self.ref['pointer'] + path}

    def fact(self, key, path, *, money=True, dates=None, metadata=None):
        value = optional(self.record, path)
        row = {'source_ref': self.ref_at(path), 'source_sha256': self.source['sha256'],
               'original_value': json_value(value), 'value': None,
               'currency': self.currency if money else None,
               'unit_label': json_value(self.record.get('unit')) if money else 'count_or_fraction',
               'dates': {}, 'status': 'SOURCE_FIELD_MISSING_OR_NULL', 'problems': []}
        for role, original in (dates or {}).items():
            try:
                row['dates'][role] = valid_date(original)
            except ValueError:
                row['dates'][role] = None
                row['problems'].append('INVALID_ORIGINAL_DATE:' + role)
        start, end = row['dates'].get('period_start'), row['dates'].get('period_end')
        if start is not None and end is not None and start > end:
            row['problems'].append('REVERSED_ORIGINAL_PERIOD')
        if metadata:
            row['original_metadata'] = json_value(metadata)
            if money and metadata.get('unit') is not None and metadata['unit'] != self.currency:
                row['problems'].append('INCOMPATIBLE_OR_UNSUPPORTED_ORIGINAL_UNIT')
            if money and metadata.get('currency') is not None and metadata['currency'] != self.currency:
                row['problems'].append('CONFLICTING_ORIGINAL_CURRENCY')
            if any(metadata.get(k) is not None and metadata[k] != self.symbol for k in ('symbol', 'issuer', 'entity_id')):
                row['problems'].append('CONFLICTING_ORIGINAL_ENTITY')
        if value is not None:
            try:
                row['value'] = numeric_text(number(value))
                row['status'] = 'ORIGINAL_NUMERIC_FIELD'
                if key in ('cash', 'debt', 'capex', 'maintenance_capex', 'growth_capex',
                           'acquisitions', 'dividends', 'buybacks', 'stock_compensation',
                           'shares_current', 'shares_prior', 'revolver_undrawn', 'revolver_commitment') and number(value) < 0:
                    row['problems'].append('UNSUPPORTED_NEGATIVE_MAGNITUDE')
            except (ValueError, ArithmeticError):
                row['problems'].append('INVALID_ORIGINAL_NUMBER')
                row['status'] = 'INVALID_ORIGINAL_FIELD'
        if money and self.currency is None:
            row['problems'].append('CURRENCY_UNKNOWN')
        self.facts[key] = row
        # A fact's explicit unit has its own scope. Do not borrow a parent scale
        # into an independently labelled raw fact. Other scalar amounts use the
        # disclosure's unit contract; unsupported labels remain unresolved.
        own_unit = metadata is not None and metadata.get('unit') is not None
        label = metadata['unit'] if own_unit else self.record.get('unit')
        scale = (metadata or {}).get('unit_scale', 1) if own_unit else self.record.get('unit_scale', 1)
        row['unit_scale'] = json_value(scale) if money else None
        if money:
            try:
                require(number(scale) > 0, 'POSITIVE_SCALE_REQUIRED')
            except (ValueError, ArithmeticError):
                row['problems'].append('INVALID_ORIGINAL_UNIT_SCALE')
            literal_annotation = isinstance(label, str) and self.currency is not None and re.fullmatch(
                re.escape(self.currency) + r' \(literal [^\n()]+\)', label)
            # This recognizes a declared literal-unit annotation, not arbitrary
            # magnitude prose. Positive magnitude labels remain unsupported.
            if literal_annotation:
                body = label.lower().replace('not millions', '').replace('not thousands', '').replace('not billions', '')
                if re.search(r'\b(?:million|millions|thousand|thousands|billion|billions)\b', body) or scale != 1:
                    literal_annotation = False
            if label != self.currency and not literal_annotation:
                row['problems'].append('UNSUPPORTED_ORIGINAL_UNIT_LABEL')
            row['unit_label'] = json_value(label)
        return row

    def extract(self):
        for key, raw in RAW.items():
            node = self.record['raw_snapshot_facts'].get(raw)
            metadata = node if isinstance(node, dict) else {}
            self.fact(key, '/raw_snapshot_facts/' + raw + '/value', metadata=metadata,
                      dates={name: metadata.get(name) for name in ('period_start', 'period_end')})
        for key, path in FLOW.items():
            # This schema scopes income/cash-flow fields to the issuer statement
            # period, but never applies that period to share counts or balances.
            dates = {} if key == 'revenue_prior' else {
                name: self.record.get(name) for name in ('period_start', 'period_end')}
            if key == 'revenue_prior':
                dates = {'period_start': self.record.get('revenue_prior_period_start'),
                         'period_end': self.record.get('revenue_prior_period_end')}
            self.fact(key, path, dates=dates)
        self.fact('shares_current', '/shares_diluted', money=False,
                  dates={'as_of': self.record.get('share_count_as_of')})
        self.fact('shares_prior', '/shares_diluted_prior', money=False,
                  dates={'as_of': self.record.get('share_count_prior_as_of')})
        self.fact('revolver_undrawn', '/revolver/undrawn')
        self.fact('revolver_commitment', '/revolver/commitment')
        self.fact('customer_revenue_fraction', '/customer_concentration/largest_customer_revenue_fraction', money=False)
        self.fact('restructuring_occurrences', '/expense_disclosures/annual_repeated_restructuring_occurrences', money=False)
        return self

    def value(self, key):
        row = self.facts[key]
        if row['status'] != 'ORIGINAL_NUMERIC_FIELD' or row['problems']:
            return None
        return Decimal(row['value'])

    def metric(self, keys, calculation):
        values = [self.value(k) for k in keys]
        row = {'operand_ids': keys, 'value': None, 'status': 'UNRESOLVED',
               'scope': 'SAME_ORIGINAL_DISCLOSURE_NOMINAL_ARITHMETIC', 'date_compatibility': 'UNKNOWN'}
        dates = [self.facts[k]['dates'] for k in keys]
        if dates and all(d == dates[0] and d and all(v is not None for v in d.values()) for d in dates):
            row['date_compatibility'] = 'MATCHING_EXPLICIT_DATES'
        elif any(d != dates[0] for d in dates):
            row['date_compatibility'] = 'MIXED_OR_UNKNOWN_DATES'
        scales = {str(self.facts[k]['unit_scale']) for k in keys if self.facts[k]['currency'] is not None}
        if len(scales) > 1:
            row['reason'] = 'INCOMPATIBLE_OR_UNKNOWN_UNIT_SCALES'
            return row
        if all(v is not None for v in values):
            try:
                row['value'] = numeric_text(calculation(*values))
                row['status'] = 'DIAGNOSTIC_ARITHMETIC'
            except ArithmeticError:
                row['reason'] = 'ARITHMETIC_UNAVAILABLE'
        else:
            row['unresolved_operand_ids'] = [k for k, v in zip(keys, values) if v is None]
        return row


def change(disclosure, current, prior):
    row = disclosure.metric([current, prior], lambda a, b: (a / b - 1) * 100)
    a, b = disclosure.facts[current], disclosure.facts[prior]
    row.update(current=a, prior=b, measure='point_to_point_percent_change', annual_change_established=False,
               interval='UNKNOWN', annualized_value=None)
    cdate = a['dates'].get('as_of') or a['dates'].get('period_end')
    pdate = b['dates'].get('as_of') or b['dates'].get('period_end')
    if cdate and pdate:
        row['interval_days'] = (date.fromisoformat(cdate) - date.fromisoformat(pdate)).days
        row['interval'] = 'DATED_POINTS' if row['interval_days'] > 0 else 'NONINCREASING_DATES'
    row['interpretation'] = 'Change between supplied points only; no annual period or causal attribution inferred.'
    return row


def funding(disclosure):
    raw = disclosure.record.get('debt_maturities')
    if raw is None:
        return {'status': 'UNRESOLVED', 'reason': 'MATURITY_SCHEDULE_NOT_SUPPLIED', 'rows': []}
    if not isinstance(raw, list) or len(raw) > 256:
        return {'status': 'UNRESOLVED', 'reason': 'UNSUPPORTED_MATURITY_SCHEDULE', 'rows': [], 'original': json_value(raw)}
    rows, identities = [], set()
    for i, item in enumerate(raw):
        key = 'maturity_' + str(i)
        dates = {'due_date': item.get('date')} if isinstance(item, dict) else {}
        disclosure.fact(key, '/debt_maturities/' + str(i) + '/principal', dates=dates,
                        metadata=item if isinstance(item, dict) else {})
        principal, cash = disclosure.value(key), disclosure.value('cash')
        identity = (json.dumps(json_value(item), sort_keys=True),)
        repeated = identity in identities
        identities.add(identity)
        row = {'maturity_fact_id': key, 'cash_fact_id': 'cash', 'maturity': disclosure.facts[key],
               'cash': disclosure.facts['cash'], 'nominal_cash_minus_maturity': None,
               'maturity_relative_to_reported_cash': 'UNKNOWN', 'repeated_identical_row': repeated,
               'future_available_liquidity': 'UNKNOWN', 'funding_sufficiency': 'NOT_ESTABLISHED'}
        if principal is not None and cash is not None and principal >= 0 and cash >= 0:
            if disclosure.facts[key]['unit_scale'] == disclosure.facts['cash']['unit_scale']:
                row['nominal_cash_minus_maturity'] = numeric_text(cash - principal)
                row['maturity_relative_to_reported_cash'] = 'EQUAL' if principal == cash else 'LESS' if principal < cash else 'GREATER'
            else:
                row['reason'] = 'INCOMPATIBLE_OR_UNKNOWN_UNIT_SCALES'
        elif principal is not None and principal < 0 or cash is not None and cash < 0:
            row['reason'] = 'NEGATIVE_CASH_OR_PRINCIPAL_UNSUPPORTED'
        row['nominal_cash_plus_undrawn_borrowing'] = disclosure.metric(['cash', 'revolver_undrawn'], lambda a, b: a+b)
        rows.append(row)
    return {'status': 'SOURCE_SCHEDULE_RETAINED', 'rows': rows,
            'limits': 'Each row compared separately, never summed or treated as cumulative funding. Reported cash is dated; revolver is conditional borrowing, not cash. Duplicate rows are not extra obligations.'}


def operations(d):
    recipes = {
        'net_debt': (['debt', 'cash'], lambda a,b:a-b),
        'ebitda_proxy': (['ebit', 'depreciation'], lambda a,b:a+b),
        'cfo_bridge': (['net_income','depreciation','stock_compensation','working_capital_change'], lambda a,b,c,e:a+b+c+e),
        'cfo_less_capex': (['cfo','capex'], lambda a,b:a-b),
        'cfo_less_maintenance_capex': (['cfo','maintenance_capex'], lambda a,b:a-b),
        'cash_after_capex_acquisitions_distributions': (['cfo','capex','acquisitions','dividends','buybacks'], lambda a,b,c,e,f:a-b-c-e-f),
        'sbc_economic_proxy_after_capex_acquisitions': (['cfo','capex','stock_compensation','acquisitions'], lambda a,b,c,e:a-b-c-e),
        'gross_margin_fraction': (['gross_profit','revenue'],lambda a,b:a/b),
        'ebit_margin_fraction': (['ebit','revenue'],lambda a,b:a/b),
        'net_margin_fraction': (['net_income','revenue'],lambda a,b:a/b),
        'interest_coverage_proxy': (['ebit','interest'],lambda a,b:a/b),
        'cfo_to_net_income': (['cfo','net_income'],lambda a,b:a/b),
        'enterprise_value_diagnostic': (['market_cap','debt','cash','preferred_equity','noncontrolling_interest'],lambda a,b,c,e,f:a+b-c+e+f),
        'ev_to_ebit_diagnostic': (['market_cap','debt','cash','preferred_equity','noncontrolling_interest','ebit'],lambda a,b,c,e,f,g:(a+b-c+e+f)/g),
    }
    result = {name:d.metric(keys,fn) for name,(keys,fn) in recipes.items()}
    bridge = result['cfo_bridge']['value']
    raw_equal = None if bridge is None or d.value('cfo') is None else Decimal(bridge)==d.value('cfo')
    comparison = d.metric(['net_income','depreciation','stock_compensation','working_capital_change','cfo'],
                          lambda a,b,c,e,f:a+b+c+e-f)
    compatible = comparison['status'] == 'DIAGNOSTIC_ARITHMETIC' and comparison['date_compatibility'] == 'MATCHING_EXPLICIT_DATES'
    result['cfo_reconciliation_comparison'] = {'diagnostic_numeric_equal':raw_equal,
        'dimension_comparison':comparison, 'compatible_original_dimensions':compatible,
        'scope':'Raw equality alone is not a reconciled source-period cash bridge.'}
    result['cfo_bridge_matches_reported'] = raw_equal if compatible else None
    result['limits'] = ['Nominal arithmetic retains each operand date; mixed dates are not a matched-period valuation.',
        'Maintenance-only residual is not FCFE; SBC economic proxy is not a cash outflow or available cash.',
        'No recurring expense is automatically added back; historical residuals do not establish future funding.',
        'Disclosure currency governs nominal amounts in this schema; no unit rescaling or contractual definitions are inferred.']
    return result


def covenant(d):
    clause = optional(d.record, '/revolver/covenant')
    proxy = d.metric(['debt','cash','ebit','depreciation'],lambda a,b,c,e:(a-b)/(c+e))
    return {'clause': {'original_value': json_value(clause), 'source_ref': d.ref_at('/revolver/covenant'),
                       'interpretation': 'UNINTERPRETED_ORIGINAL_CONTRACT_EXCERPT'},
            'net_debt_to_ebitda_proxy': proxy, 'contractual_compliance': 'UNKNOWN',
            'contractual_borrowing_headroom': 'UNKNOWN', 'threshold_comparison': 'NOT_EVALUATED',
            'limits': 'A short clause does not supply contractual definitions, permitted adjustments, testing dates or all conditions. A proxy is not compliance.'}


def business(d, peers):
    fraction = d.value('customer_revenue_fraction')
    concentration = {'fact': d.facts['customer_revenue_fraction'],
                     'status': 'SOURCE_REVENUE_FRACTION' if fraction is not None and 0<=fraction<=1 else 'UNRESOLVED',
                     'revenue_at_fraction_diagnostic': d.metric(['revenue','customer_revenue_fraction'],lambda a,b:a*b)
                         if fraction is not None and 0<=fraction<=1 else None,
                     'loss_forecast': 'NOT_ESTABLISHED', 'same_period_basis': 'UNKNOWN'}
    return {'description_quote': {'value': json_value(d.record.get('business_description')),
                                 'source_ref':d.ref_at('/business_description'), 'interpretation':'ATTRIBUTED_ORIGINAL_TEXT'},
            'customer_concentration':concentration,
            'peer_diagnostics':[{'issuer':p.symbol,'source_ref':p.ref,'original_facts':p.facts,
                'ebit_margin_fraction':p.metric(['ebit','revenue'],lambda a,b:a/b),
                'description_quote':json_value(p.record.get('business_description')),
                'economic_comparability':'NOT_ESTABLISHED'} for p in peers],
            'competitive_advantage':'NOT_ESTABLISHED',
            'limits':'Similar ratios do not establish a moat or comparable businesses. Source descriptions are quotations, not authenticated conclusions.'}


def original_object(corpus, ref):
    require(isinstance(ref, dict) and ref.get('source_id') in corpus.sources, 'ORIGINAL_OBJECT_REQUIRED')
    source = corpus.sources[ref['source_id']]
    if set(ref) == {'source_id', 'pointer'}:
        require(source['format'] == 'json', 'JSON_OBJECT_SOURCE_REQUIRED')
        doc = source['document']
    else:
        require(set(ref) == {'source_id','start','end','excerpt','pointer'}, 'OBJECT_REFERENCE_FIELDS')
        corpus.resolve({k:v for k,v in ref.items() if k!='pointer'})
        doc = parse(ref['excerpt'])
    value = at(doc, ref['pointer'])
    require(isinstance(value,dict), 'ORIGINAL_OBJECT_REQUIRED')
    return value


def source_calendar(value):
    """Only explicit original ISO dates or offset-bearing timestamps."""
    if isinstance(value,str):
        try:
            if re.fullmatch(r'\d{4}-\d{2}-\d{2}',value):
                return date.fromisoformat(value)
            parsed = datetime.fromisoformat(value.replace('Z','+00:00'))
            if 'T' in value and parsed.utcoffset() is not None:
                return parsed.astimezone(timezone.utc).date()
        except ValueError:
            pass
    return None


def event_context(corpus, entry, as_of, window):
    require(isinstance(entry,dict) and {'source_ref'} <= set(entry) <= {'source_ref','date_ref'}, 'EVENT_REFERENCE_FIELDS')
    ref=entry['source_ref'];quote=corpus.resolve(ref)
    require(isinstance(quote,str) and 0<len(quote.encode('utf-8'))<=8192, 'BOUNDED_ORIGINAL_EVENT_TEXT_REQUIRED')
    event_date=None;original_date=None
    if 'date_ref' in entry:
        clock=entry['date_ref']
        require(isinstance(clock,dict) and clock.get('source_id')==ref['source_id'], 'EVENT_DATE_SOURCE_MISMATCH')
        if 'pointer' in ref:
            require('pointer' in clock and clock['pointer'].rsplit('/',1)[-1]=='event_date' and
                clock['pointer'].rsplit('/',1)[0]==ref['pointer'].rsplit('/',1)[0] and
                all(clock.get(k)==ref.get(k) for k in ('start','end','excerpt')), 'EVENT_DATE_RECORD_MISMATCH')
        else:
            require('pointer' not in clock and type(clock.get('start')) is int and type(clock.get('end')) is int and
                    ref['start']<=clock['start']<clock['end']<=ref['end'], 'EVENT_DATE_OUTSIDE_QUOTED_EVENT')
        original_date=corpus.resolve(clock);event_date=source_calendar(original_date)
    difference=(event_date-as_of).days if event_date is not None and as_of is not None else None
    return {'source_ref':ref,'source_sha256':corpus.sources[ref['source_id']]['sha256'],
        'original_quote':quote,'interpretation':'ATTRIBUTED_EVENT_CONTEXT_NOT_VERIFIED_OCCURRENCE',
        'date_ref':entry.get('date_ref'),'original_date':json_value(original_date),
        'event_calendar_date':event_date.isoformat() if event_date else None,
        'days_from_selected_source_as_of':difference,
        'comparison_basis':'Calendar-day diagnostic; offset-bearing timestamps normalized to UTC, date-only fields retain their calendar date.',
        'timing_status':'UNKNOWN' if difference is None else 'PAST' if difference<0 else
                        'WITHIN_SELECTED_REVIEW_WINDOW' if difference<=window else 'OUTSIDE_SELECTED_REVIEW_WINDOW',
        'occurrence_verified':False}


def research_plan(corpus, request, d, cash, changes):
    if request is None:
        return {'status':'NOT_REQUESTED','rules':[],'events':[],
                'limits':'Generic monitoring questions alone are not a conditional thesis/invalidation plan.'}
    require(isinstance(request,dict) and {'cadence','rules'} <= set(request) <=
            {'cadence','rules','events','as_of_ref','event_window_days'}, 'RESEARCH_PLAN_FIELDS')
    require(request['cadence'] in ('ON_NEW_SOURCE','MONTHLY','QUARTERLY'), 'RESEARCH_CADENCE_REQUIRED')
    rules=request['rules'];events=request.get('events',[]);window=request.get('event_window_days',90)
    require(isinstance(rules,list) and 0<len(rules)<=16,'BOUNDED_RESEARCH_RULES_REQUIRED')
    require(isinstance(events,list) and len(events)<=16,'BOUNDED_EVENT_CONTEXT_REQUIRED')
    require(type(window) is int and window in (30,90,365),'RESEARCH_WINDOW_REQUIRED')
    asof_raw=corpus.resolve(request['as_of_ref']) if 'as_of_ref' in request else None
    asof=source_calendar(asof_raw)
    metrics={}
    for name,metric in cash.items():
        if isinstance(metric,dict) and 'operand_ids' in metric:
            fractions=name in ('gross_margin_fraction','ebit_margin_fraction','net_margin_fraction')
            ratios=name in ('interest_coverage_proxy','cfo_to_net_income','ev_to_ebit_diagnostic')
            keys=metric['operand_ids']
            metrics[name]={'value':metric['value'],'status':metric['status'],
                'time_compatible':metric['date_compatibility']=='MATCHING_EXPLICIT_DATES',
                'unit':'fraction' if fractions else 'ratio' if ratios else d.currency,
                'unit_scale':1 if fractions or ratios else d.facts[keys[0]]['unit_scale'],
                'operand_ids':keys,'scope':'RETAINED_SOURCE_PERIOD_DIAGNOSTIC'}
    for name,key in (('shares_point_change_percent','shares'),('revenue_point_change_percent','revenue')):
        metrics[name]={'value':changes[key]['value'],'status':changes[key]['status'],
            'time_compatible':changes[key]['interval']!='NONINCREASING_DATES',
            'unit':'percent','unit_scale':1,'scope':'SUPPLIED_POINT_CHANGE_NOT_ANNUAL',
            'operand_ids':changes[key]['operand_ids'],'timing':changes[key]['interval']}
    compare={'lt':lambda a,b:a<b,'le':lambda a,b:a<=b,'gt':lambda a,b:a>b,
             'ge':lambda a,b:a>=b,'eq':lambda a,b:a==b}
    output=[]
    for index,rule in enumerate(rules):
        require(isinstance(rule,dict) and set(rule)=={'purpose','metric','operator','threshold'}, 'RESEARCH_RULE_FIELDS')
        require(rule['purpose'] in ('REVIEW_THESIS','INVALIDATE_HYPOTHESIS'), 'RESEARCH_RULE_PURPOSE')
        require(isinstance(rule['metric'],str) and rule['metric'] in metrics and rule['operator'] in compare,
                'SUPPORTED_RESEARCH_METRIC_AND_COMPARATOR_REQUIRED')
        observation=metrics[rule['metric']];threshold=rule['threshold']
        require(isinstance(threshold,dict), 'TYPED_RESEARCH_THRESHOLD_REQUIRED')
        if threshold.get('kind')=='ANALYST_ASSUMPTION':
            require(set(threshold)=={'kind','value'}, 'ASSUMPTION_THRESHOLD_FIELDS')
            value=number(threshold['value'])
            bound={'kind':'ANALYST_ASSUMPTION','value':numeric_text(value),
                   'unit':observation['unit'],'unit_scale':observation['unit_scale'],
                   'source_observation':False,'interpretation':'DECLARED_RESEARCH_POLICY_CHOICE_NOT_SOURCE_FACT'}
        else:
            require(set(threshold)=={'kind','source_ref'} and threshold['kind']=='SOURCE_THRESHOLD', 'SOURCE_THRESHOLD_FIELDS')
            original=original_object(corpus,threshold['source_ref'])
            require({'metric','value','unit','unit_scale'}<=set(original) and original['metric']==rule['metric'] and
                    original['unit']==observation['unit'],'SOURCE_THRESHOLD_ROLE_OR_UNIT_MISMATCH')
            source_issuer=original.get('issuer')
            require(source_issuer is None or source_issuer==d.symbol,'SOURCE_THRESHOLD_ISSUER_MISMATCH')
            value=number(original['value']);scale=number(original['unit_scale'])
            require(scale>0 and observation['unit_scale'] is not None and scale==Decimal(str(observation['unit_scale'])),
                    'SOURCE_THRESHOLD_SCALE_MISMATCH')
            bound={'kind':'SOURCE_THRESHOLD','value':numeric_text(value),'unit':original['unit'],
                   'unit_scale':numeric_text(scale),'source_ref':threshold['source_ref'],
                   'source_sha256':corpus.sources[threshold['source_ref']['source_id']]['sha256'],
                   'source_issuer':source_issuer,
                   'source_scope':'EXPLICIT_ISSUER' if source_issuer is not None else 'UNSPECIFIED_RESEARCH_POLICY_SCOPE',
                   'selected_application_issuer':d.symbol,
                   'interpretation':'SOURCE_RESEARCH_THRESHOLD_NOT_PROOF_OF_NECESSITY'}
        usable=observation['value'] is not None and observation['status']=='DIAGNOSTIC_ARITHMETIC' and observation['time_compatible']
        met=compare[rule['operator']](Decimal(observation['value']),value) if usable else None
        output.append({'rule_index':index,'purpose':rule['purpose'],'metric':rule['metric'],
            'operator':rule['operator'],'threshold':bound,'observation':observation,
            'condition_met_on_retained_observation':met,
            'evaluation':'UNKNOWN' if met is None else 'CONDITION_MET' if met else 'CONDITION_NOT_MET',
            'hypothesis_scope':{'issuer':d.symbol,'definition':'Proposed metric-bound research hypothesis, retained only while this invalidation condition remains unmet.'
                if rule['purpose']=='INVALIDATE_HYPOTHESIS' else 'A proposed condition for reopening the research thesis, not a finding of invalidity.'},
            'consequence':'Reassess the thesis under this proposed research rule.' if rule['purpose']=='REVIEW_THESIS' else
                          'Treat the stated hypothesis as invalid under this proposed rule if the condition is met; re-evaluate its premises.',
            'objective_truth_established':False,'general_necessity_established':False,
            'general_sufficiency_established':False,'execution_authority':False})
    return {'status':'PROPOSED_CONDITIONAL_RESEARCH_PLAN','cadence':request['cadence'],
        'cadence_status':'PROPOSAL_ONLY_NOT_SCHEDULED','rules':output,
        'purpose_coverage':{k:any(r['purpose']==k for r in output) for k in ('REVIEW_THESIS','INVALIDATE_HYPOTHESIS')},
        'selected_as_of':{'source_ref':request.get('as_of_ref'),'original_value':json_value(asof_raw),
                          'calendar_date':asof.isoformat() if asof else None},
        'event_window_days':window,'events':[event_context(corpus,e,asof,window) for e in events],
        'event_coverage':'SELECTED_SOURCE_EXCERPTS_NOT_EXHAUSTIVE',
        'rolling_review':'Re-evaluate retained facts and these hypotheses at the proposed cadence and when new original-source evidence arrives; preserve prior observations and changes.',
        'limits':'Conditions define a proposed research policy, not universal investment truth, DCF closure, verified event occurrence or authority to trade/schedule. Unknown observations do not satisfy or fail a condition.'}


def render(result):
    """Only fixed templates and original-source values; no caller claim strings."""
    show=lambda x:json.dumps(x,sort_keys=True,ensure_ascii=False,allow_nan=False)
    lines=['# Source-bound issuer evidence',
        'Local source bindings and diagnostic arithmetic; not source authentication, investment correctness or complete semantic verification.',
        'Issuer: '+show(result['issuer']),
        '## Financing',show(result['funding_comparisons']),show(result['covenant_diagnostic']),
        'Maturity comparisons are against dated reported cash. Equal amounts leave zero nominal residual, not a proved shortfall. Future cash needs and availability remain unknown.',
        '## Cash conversion and operations',show(result['cash_operating']),
        '## Dilution and dated changes',show(result['point_changes']),
        'Point-to-point changes are not annual changes without explicit timing; no cause is inferred.',
        '## Business and competitive context',show(result['business_context']),
        '## Capital allocation',show(result['capital_allocation']),
        '## Valuation objective',show(result['valuation_objective']),
        '## Proposed monitoring plan',show(result['monitoring_hypotheses']),
        '## Conditional thesis review and rolling plan',show(result['research_plan']),
        'These are research questions, not necessary or sufficient business conditions, trading triggers or instructions to schedule monitoring.',
        'Research stance: '+show(result['research_stance'])+' (uncomputed opinion).',
        '## Source and topic coverage',show(result['topic_coverage']),show(result['source_coverage']),
        'Original fields and metadata: '+show(result['original_facts']),show(result['limitations'])]
    text='\n\n'.join(lines)+'\n'
    return {'text':text,'sha256':digest(text.encode('utf-8')),'whole_report_semantic_pass':False}


def analyze(request, manifest_path, expected_manifest_sha256, source_root=None):
    require(isinstance(request,dict) and set(request)<= {'issuer_record','peers','monitoring','research_stance','research_plan'}
            and 'issuer_record' in request,'ISSUER_REQUEST_FIELDS')
    peers=request.get('peers',[]);monitor=request.get('monitoring',list(TOPICS));stance=request.get('research_stance','undetermined')
    require(isinstance(peers,list) and len(peers)<=8,'BOUNDED_PEERS_REQUIRED')
    require(isinstance(monitor,list) and len(monitor)<=len(TOPICS) and all(isinstance(x,str) and x in MONITORING for x in monitor)
            and len(set(monitor))==len(monitor),'MONITORING_TOPICS_REQUIRED')
    require(stance in ('watch','undetermined','further_research'),'BOUNDED_STANCE_REQUIRED')
    corpus=Corpus(manifest_path,expected_manifest_sha256,source_root)
    with localcontext() as ctx:
        ctx.prec=260
        d=Disclosure(corpus,request['issuer_record']).extract()
        others=[Disclosure(corpus,p).extract() for p in peers]
        identities=[(p.source['sha256'],p.ref.get('start'),p.ref.get('end'),p.ref['pointer']) for p in [d,*others]]
        require(len(set(identities))==len(identities),'DUPLICATE_ORIGINAL_RECORD')
        require(all(p.symbol!=d.symbol for p in others) and len({p.symbol for p in others})==len(others),'PEER_ISSUER_IDENTITY_DUPLICATED')
        funds=funding(d);cash=operations(d)
        inventory=[{'source_id':sid,'path':s['path'],'sha256':s['sha256'],'format':s['format'],
                    'status':'BYTES_VERIFIED_NOT_SEMANTICALLY_EXHAUSTIVE',
                    'selected':sid in {p.ref['source_id'] for p in [d,*others]}}
                   for sid,s in sorted(corpus.sources.items())]
        result={'method':METHOD,'issuer':{'symbol':d.symbol,'source_ref':d.ref,'source_sha256':d.source['sha256']},
            'original_facts':d.facts,'funding_comparisons':funds,
            'point_changes':{'shares':change(d,'shares_current','shares_prior'), 'revenue':change(d,'revenue','revenue_prior')},
            'covenant_diagnostic':covenant(d),'cash_operating':cash,'business_context':business(d,others),
            'capital_allocation':{k:d.facts[k] for k in ('dividends','buybacks','acquisitions','restructuring','integration_expense','restructuring_occurrences')},
            'valuation_objective':{'DCF_DISCOUNT_CLOSURE':'NOT_EVALUATED','necessary_business_conditions':'NOT_ESTABLISHED',
                'limits':'This disclosure adapter does not construct a DCF or a closure criterion. Use a separately evaluated named-objective section for terminal scenarios; it cannot establish DCF closure.'},
            'monitoring_hypotheses':[{'topic':k,'question':MONITORING[k],'classification':'PROPOSED_RESEARCH_REVIEW',
                'necessity_established':False,'sufficiency_established':False,'execution_authority':False} for k in monitor],
            'research_stance':stance,
            'topic_coverage':{k:{'status':'ADDRESSED_WITH_SOURCE_LIMITS' if k!='valuation_objective' else 'OBJECTIVE_UNEVALUATED',
                                'semantic_completeness_verified':False} for k in TOPICS},
            'source_coverage':{'manifest_sha256':expected_manifest_sha256,'sources':inventory,'sources_verified':len(inventory),
                'selection':'EXPLICIT_ORIGINAL_RECORDS','unselected_sources_retained':True,
                'all_corpus_semantics_reviewed':False,'source_authenticity_verified':False},
            'limitations':['Supported financial-disclosure schema only. Unselected records and other source formats are not semantic evidence of absence.',
                'Whole topic coverage means each topic has a displayed evidence/unknown section, not complete research or a correct investment conclusion.',
                'Arithmetic uses original nominal units, no inferred rescaling; all dates and unit conflicts remain attached. Ratios are rounded in a 260-digit Decimal context.',
                'Qualitative source text is attributed quotation. Monitoring templates are hypotheses, never general necessity or sufficient conditions.']}
        result['research_plan']=research_plan(corpus,request.get('research_plan'),d,cash,result['point_changes'])
        result['report']=render(result)
        return result
