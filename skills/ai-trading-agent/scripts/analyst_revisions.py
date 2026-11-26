"""Metric-specific revision evidence from a complete pinned original corpus.

Supported original schemas are root events and individual_targets arrays.
Structured values remain structured evidence; raw corroboration is independent.
No network, source rewriting, issuer authentication or free-form claim input.
"""
from copy import deepcopy
from decimal import Context, Decimal, localcontext
import re

from news_sources import stamp
import supplied_research as store

METHOD = 'source-bound-analyst-revisions-1'
METRICS = ('rating', 'target', 'eps', 'revenue')
RAW_CURRENCIES = {'USD','EUR','GBP','JPY','CHF','CAD','AUD','NZD','CNY','HKD','SGD','INR',
                 'KRW','SEK','NOK','DKK','ZAR','BRL','MXN','TWD','TRY','ILS','RUB','AED','SAR'}
FIELDS = ('record_id', 'firm_id', 'analyst_id', 'issuer', 'issued_at', 'event_type',
          'currency', 'price_basis', 'target_horizon', 'fiscal_period', 'eps_basis',
          'unit_revenue', 'revenue_basis') + METRICS
DIMENSIONS = {
    'rating': ('firm_id', 'issuer'),
    'target': ('firm_id', 'issuer', 'currency', 'price_basis', 'target_horizon'),
    'eps': ('firm_id', 'issuer', 'currency', 'fiscal_period', 'eps_basis'),
    'revenue': ('firm_id', 'issuer', 'currency', 'fiscal_period', 'unit_revenue'),
}
TARGET_RECORD_DIMENSIONS = DIMENSIONS['target'] + ('analyst_id',)


def number(value):
    store.require(type(value) in (int, float, Decimal), 'REVISION_FINITE_NUMERIC_VALUE_REQUIRED')
    result = Decimal(str(value))
    store.require(result.is_finite() and result.adjusted() <= 100 and result.adjusted() >= -100,
                  'REVISION_NUMERIC_RANGE_UNSUPPORTED')
    return result


def present(value):
    return type(value) is str and bool(value.strip())


def raw_reference(row, corpus):
    declared = row.get('source')
    if declared is None:
        return {'status': 'NO_RAW_SOURCE_REFERENCE', 'source_id': None, 'text': None}
    store.require(type(declared) is dict and present(declared.get('path'))
                  and present(declared.get('sha256')), 'REVISION_RAW_REFERENCE_SCHEMA')
    name = store.relative(declared['path'])
    matches = [(sid, source) for sid, source in corpus.sources.items()
               if source['path'] == name or source['path'].endswith('/' + name)]
    store.require(len(matches) == 1, 'REVISION_RAW_REFERENCE_MISSING_OR_AMBIGUOUS')
    sid, source = matches[0]
    store.require(source['sha256'] == declared['sha256'], 'REVISION_RAW_REFERENCE_HASH_MISMATCH')
    text = source['raw'].decode('utf8')
    excerpt = declared.get('verbatim_excerpt')
    excerpt_status = ('EXACT_DECLARED_EXCERPT_PRESENT' if type(excerpt) is str and excerpt in text
                      else 'DECLARED_EXCERPT_UNCONFIRMED')
    return {'status': 'PINNED_RAW_SOURCE', 'source_id': sid, 'sha256': source['sha256'],
            'text': text, 'excerpt_status': excerpt_status}


def raw_metric_origin(metric, value, raw, currency=None):
    """Narrow literal label extraction; a missing match never means source absence."""
    text = raw['text']
    if text is None:
        return {'status': 'STRUCTURED_ONLY_RAW_UNAVAILABLE', 'raw_value': None}
    if metric == 'rating':
        found = re.search(r'\brating\s+([^;.\n]+)', text, re.I)
        extracted = found.group(1).strip() if found else None
        matched = extracted is not None and str(value).casefold() == extracted.casefold()
        raw_currency = None
    else:
        found = re.search(r'\b' + re.escape(metric) + r'\s+(?:((?-i:[A-Z]{3}))\s+)?([^\s;\n]+)', text, re.I)
        token = found.group(2).rstrip('.') if found else None
        extracted = token if token is not None and re.fullmatch(r'[+-]?(?:\d+(?:\.\d*)?|\.\d+)', token) else None
        matched = extracted is not None and number(value) == number(Decimal(extracted))
        raw_currency = found.group(1).upper() if found and found.group(1) else None
        if raw_currency is not None and raw_currency not in RAW_CURRENCIES and raw_currency != currency:
            extracted = None; matched = False; raw_currency = None
    currency_conflict = raw_currency is not None and present(currency) and raw_currency != currency
    return {'status': ('STRUCTURED_RAW_CURRENCY_CONFLICT' if currency_conflict else 'LITERAL_RAW_VALUE_MATCH' if matched else
                       'STRUCTURED_RAW_VALUE_CONFLICT' if extracted is not None else
                       'STRUCTURED_ONLY_RAW_FIELD_UNRESOLVED'),
            'raw_value': extracted, 'raw_currency': raw_currency, 'raw_source_id': raw['source_id'],
            'scope': 'FIRST_SUPPORTED_LITERAL_FIELD_LABEL_ONLY_NOT_SEMANTIC_EXTRACTION'}


def records(corpus):
    rows, unsupported, cutoffs = [], [], []
    for sid, source in corpus.sources.items():
        if source['format'] != 'json':
            continue
        document = source['document']
        if type(document) is not dict:
            unsupported.append(sid); continue
        recognized = False
        if 'individual_targets' in document and present(document.get('as_of')):
            cutoffs.append({'source_id': sid, 'pointer': '/as_of', 'value': document['as_of']})
        for key in ('events', 'individual_targets'):
            if key not in document:
                continue
            recognized = True; values = document[key]
            store.require(type(values) is list and len(values) <= 256, 'BOUNDED_REVISION_RECORD_LIST_REQUIRED')
            for index, value in enumerate(values):
                store.require(type(value) is dict and present(value.get('firm_id'))
                              and present(value.get('issued_at')), 'REVISION_RECORD_IDENTITY_AND_CLOCK_REQUIRED')
                stamp(value['issued_at'])
                for field in FIELDS:
                    if field in value and field not in METRICS:
                        store.require(value[field] is None or type(value[field]) is str, 'REVISION_METADATA_STRING_REQUIRED')
                if 'rating' in value:store.require(present(value['rating']), 'REVISION_RATING_STRING_REQUIRED')
                for metric in METRICS[1:]:
                    if metric in value:number(value[metric])
                raw = raw_reference(value, corpus)
                fields = {k: deepcopy(value[k]) for k in FIELDS if k in value}
                row = {'id': sid + ':' + '/' + key + '/' + str(index), 'record_kind': key,
                       'source_ref': {'source_id': sid, 'pointer': '/' + key + '/' + str(index), 'sha256': source['sha256']},
                       'fields': fields, 'original_fields': deepcopy(fields),
                       'raw_source': {k: v for k, v in raw.items() if k != 'text'},
                       'field_origins': {metric: raw_metric_origin(metric, value[metric], raw, value.get('currency')) for metric in METRICS if metric in value},
                       'raw_initiation_phrase_present': bool(raw['text'] and re.search(r'\binitiated(?: new)? coverage\b', raw['text'], re.I)),
                       'dimension_links': []}
                rows.append(row)
        if not recognized:unsupported.append(sid)
    store.require(len(rows) <= 512, 'BOUNDED_REVISION_CORPUS_REQUIRED')
    unique_cutoffs = {r['value'] for r in cutoffs}
    store.require(len(unique_cutoffs) <= 1, 'CONFLICTING_ORIGINAL_REVISION_CUTOFFS')
    cutoff = next(iter(unique_cutoffs), None)
    for row in rows:
        row['clock_status'] = 'AFTER_ORIGINAL_CUTOFF' if cutoff and stamp(row['fields']['issued_at']) > stamp(cutoff) else 'WITHIN_ORIGINAL_CUTOFF' if cutoff else 'NO_ORIGINAL_CUTOFF'
    return rows, unsupported, cutoffs


def link_target_dimensions(rows):
    targets = [r for r in rows if r['record_kind'] == 'individual_targets']
    for row in rows:
        f = row['fields']
        if row['record_kind'] != 'events' or 'target' not in f:
            continue
        matches = [t for t in targets if all(t['fields'].get(k) == f.get(k) and f.get(k) is not None
                    for k in ('firm_id', 'issued_at', 'currency')) and 'target' in t['fields']
                   and number(t['fields']['target']) == number(f['target'])]
        dimensions = ('issuer', 'price_basis', 'target_horizon')
        if matches:
            for k in dimensions:
                values = {t['fields'].get(k) for t in matches}
                if len(values) != 1:
                    row['dimension_links'].append({'dimension': k, 'status': 'AMBIGUOUS_CONTEMPORANEOUS_TARGET_DIMENSIONS', 'source_record_refs': [t['source_ref'] for t in matches]})
                    continue
                linked = next(iter(values))
                if not present(f.get(k)) and present(linked):
                    f[k] = linked
                    row['dimension_links'].append({'dimension': k, 'value': linked, 'source_record_refs': [t['source_ref'] for t in matches],
                        'match_basis': ['firm_id', 'issued_at', 'currency', 'target'], 'scope': 'EXACT_CONTEMPORANEOUS_TARGET_RECORD_LINK'})
                elif present(f.get(k)) and present(linked) and f[k] != linked:
                    row['dimension_links'].append({'dimension': k, 'status': 'DECLARED_DIMENSION_CONFLICT', 'source_record_refs': [t['source_ref'] for t in matches]})


def difference(before, after):
    b, a = number(before), number(after)
    precision = max(50, max(a.adjusted(), b.adjusted()) - min(a.as_tuple().exponent, b.as_tuple().exponent) + 3)
    with localcontext(Context(prec=precision)):
        delta = a - b
    with localcontext(Context(prec=50)):
        percent = delta / b * 100 if b else None
    return {'before': str(b), 'after': str(a), 'delta': str(delta),
            'percent_change': str(percent) if percent is not None else None,
            'percent_denominator': str(b), 'percent_status': 'UNDEFINED_ZERO_BASE' if not b else 'COMPUTED_DECIMAL_50_DIGITS',
            'formula': '(after - before) / before * 100', 'units_inferred': False}


def recommendation_gate(rows):
    """Current provider mix, not proof of improvement over a prior vintage."""
    matches = [r for r in rows if r.get('period') == '0m']
    if len(matches) != 1:
        return {'status': 'UNRESOLVED', 'reason': 'UNIQUE_CURRENT_RATING_BOOK_REQUIRED'}
    keys = ('strongBuy', 'buy', 'hold', 'sell', 'strongSell')
    counts = {k: matches[0].get(k) for k in keys}
    # CSV and retained vendor exports often serialize integer counts as text.
    counts = {k: int(v) if isinstance(v, str) and re.fullmatch(r'[0-9]{1,12}', v) else v
              for k, v in counts.items()}
    if not all(type(n) is int and n >= 0 for n in counts.values()):
        return {'status': 'UNRESOLVED', 'reason': 'INCOMPLETE_OR_INVALID_COUNTS', 'counts': counts}
    favorable = counts['buy'] + counts['strongBuy']
    return {'status': 'PASS' if favorable >= 1 and favorable >= counts['hold'] else 'FAIL',
            'counts': counts, 'favorable': favorable, 'unfavorable': counts['sell'] + counts['strongSell'],
            'time_trend_verified': False}


def estimate_revision_signal(document):
    """Compare provider EPS vintages in one absolute fiscal bucket; keep signs."""
    from paper_screen import symbols, available, day, named
    cutoff = stamp(document['as_of'])
    output = []
    for row in symbols(document):
        result = {'symbol': row['symbol'], 'issuer_id': row.get('issuer_id'), 'provider': row.get('provider'),
                  'source_ref': row.get('source_ref'), 'observed_at': row.get('observed_at'),
                  'currency': row.get('currency'), 'eps_basis': row.get('eps_basis'),
                  'period': row.get('period'), 'fiscal_period_end': row.get('fiscal_period_end'),
                  'deltas': {}, 'revision_status': 'UNRESOLVED', 'recommendation': {'status': 'UNRESOLVED'}}
        output.append(result)
        if not available(row, cutoff) or not all(named(row.get(k)) for k in ('provider', 'issuer_id')):
            result['reason'] = 'MISSING_OR_FUTURE_SOURCE'
            continue
        recs = row.get('recommendations', [])
        if isinstance(recs, list) and all(isinstance(r, dict) for r in recs):
            result['recommendation'] = recommendation_gate(recs)
        if not named(row.get('period')):
            result['reason'] = 'ESTIMATE_BUCKET_REQUIRED'
            continue
        if row.get('fiscal_period_end') is not None:
            try:
                day(row['fiscal_period_end'])
            except (ValueError, TypeError):
                result['reason'] = 'INVALID_FISCAL_PERIOD_END'
                continue
        trends = row.get('eps_trend', [])
        if not isinstance(trends, list) or not all(isinstance(r, dict) for r in trends):
            result['reason'] = 'TREND_ROWS_REQUIRED'
            continue
        matches = [r for r in trends if r.get('period') == row['period']]
        if len(matches) != 1 or any(matches[0].get(k) is not None and row.get(k) is not None
                                    and matches[0][k] != row[k] for k in ('fiscal_period_end', 'currency', 'eps_basis')):
            result['reason'] = 'NONUNIQUE_OR_MISMATCHED_FISCAL_BUCKET'
            continue
        trend = matches[0]
        for key in ('30daysAgo', '90daysAgo'):
            if trend.get(key) is None or trend.get('current') is None:
                result['deltas'][key] = {'status': 'UNAVAILABLE'}
                continue
            try:
                values = [Decimal(v) if isinstance(v, str) and
                          re.fullmatch(r'[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?', v)
                          else v for v in (trend[key], trend['current'])]
                diff = difference(*values)
            except (ValueError, TypeError, ArithmeticError):
                result['deltas'][key] = {'status': 'INVALID_ESTIMATE_VALUE'}
                continue
            if number(values[0]) <= 0:
                diff.update(percent_change=None, percent_status='UNDEFINED_NONPOSITIVE_BASE')
            result['deltas'][key] = {**diff, 'status': 'OBSERVED_PROVIDER_REVISION'}
        changes = list(result['deltas'].values())
        if all(d['status'] == 'OBSERVED_PROVIDER_REVISION' for d in changes):
            result['both_deltas_positive'] = all(Decimal(d['delta']) > 0 for d in changes)
            if all(named(row.get(k)) for k in ('fiscal_period_end', 'eps_basis', 'currency')):
                result['revision_status'] = 'PASS' if result['both_deltas_positive'] else 'FAIL'
            else:
                result['reason'] = 'SIGNED_VENDOR_BUCKET_CHANGE_ONLY_UNRESOLVED_ESTIMATE_DIMENSIONS'
    return {'as_of': document['as_of'], 'candidates': output,
            'limitation': 'Provider snapshots for a declared fiscal bucket. The 30/90-day and recommendation checks are components only; evaluate other adopted strategy rules separately.'}


def compare(before, after, metric, initiation_conflict, dimensions=None):
    a, b = before['fields'], after['fields']
    dims = dimensions or DIMENSIONS[metric]
    missing = [k for k in dims if not present(a.get(k)) or not present(b.get(k))]
    mismatches = [k for k in dims if present(a.get(k)) and present(b.get(k)) and a[k] != b[k]]
    raw_conflict = any(r['field_origins'][metric]['status'].endswith('_CONFLICT') for r in (before, after))
    dimension_conflict = any(link.get('dimension') in dims and link.get('status') in ('DECLARED_DIMENSION_CONFLICT', 'AMBIGUOUS_CONTEMPORANEOUS_TARGET_DIMENSIONS')
                             for r in (before, after) for link in r['dimension_links'])
    result = {'metric': metric, 'before_record': before['id'], 'after_record': after['id'],
              'dimension_requirements': list(dims), 'missing_dimensions': missing, 'mismatched_dimensions': mismatches,
              'before_dimensions': {k: a.get(k) for k in dims}, 'after_dimensions': {k: b.get(k) for k in dims},
              'raw_value_conflict': raw_conflict, 'dimension_link_conflict': dimension_conflict,
              'whole_request_complete': False}
    if metric == 'rating':
        result['rating_transition'] = {'before': a[metric], 'after': b[metric], 'ordinal_upgrade_or_downgrade_inferred': False}
    elif not mismatches:
        result['reported_numeric_difference'] = difference(a[metric], b[metric])
    else:
        result['reported_numeric_difference'] = None
    if mismatches:
        status = 'NOT_COMPARABLE_METRIC_DIMENSIONS'
    elif initiation_conflict:
        status = 'CONDITIONAL_RAW_DIFFERENCE_UNRESOLVED_COVERAGE_CONFLICT'
    elif missing or dimension_conflict or raw_conflict:
        status = 'CONDITIONAL_REPORTED_DIFFERENCE_UNRESOLVED_EVIDENCE'
    else:
        status = 'MATCHED_REPORTED_REVISION'
    if metric == 'revenue':
        bases = [a.get('revenue_basis'), b.get('revenue_basis')]
        result['revenue_accounting_basis'] = {'before': bases[0], 'after': bases[1], 'status': 'KNOWN_MATCH' if all(present(x) for x in bases) and bases[0] == bases[1] else 'KNOWN_CONFLICT' if all(present(x) for x in bases) else 'UNKNOWN'}
        if result['revenue_accounting_basis']['status'] == 'KNOWN_CONFLICT':
            result['reported_numeric_difference'] = None; status = 'NOT_COMPARABLE_REVENUE_ACCOUNTING_BASIS'
        elif result['revenue_accounting_basis']['status'] == 'UNKNOWN' and status == 'MATCHED_REPORTED_REVISION':
            status = 'REPORTED_NUMERIC_CHANGE_ACCOUNTING_BASIS_UNVERIFIED'
    result['status'] = status
    result['verified_genuine_revision'] = False
    result['interpretation'] = 'A reported-value difference does not establish a clean revision when coverage, raw corroboration or metric dimensions remain unresolved.'
    return result


def target_record_coverage(rows):
    """Disposition every target-list record, even when no event row exists.

    Literal horizons are never normalized to a presumed common duration. Same-time
    observations retain separate provenance and cannot supply chronological order.
    """
    assessments,comparisons=[],[]
    def peers(row):
        f=row['fields'];result=[]
        for other in rows:
            g=other['fields']
            if other['id']==row['id'] or 'target' not in g or g['firm_id']!=f['firm_id'] or stamp(g['issued_at'])!=stamp(f['issued_at']):continue
            # Explicitly different issuer/analyst populations are not duplicate
            # observations. Unknown identity remains visible, never imputed.
            if any(present(f.get(k)) and present(g.get(k)) and f[k]!=g[k] for k in ('issuer','analyst_id')):continue
            missing=[k for k in TARGET_RECORD_DIMENSIONS if not present(f.get(k)) or not present(g.get(k))]
            mismatch=[k for k in TARGET_RECORD_DIMENSIONS if present(f.get(k)) and present(g.get(k)) and f[k]!=g[k]]
            value_conflict=number(f['target'])!=number(g['target'])
            result.append({'record_id':other['id'],'source_ref':other['source_ref'],'missing_dimensions':missing,
                'mismatched_dimensions':mismatch,'target_value_conflict':value_conflict,
                'status':'CONFLICTING_SAME_TIME_REPORTED_TARGET' if mismatch or value_conflict else 'PARTIAL_SAME_TIME_TARGET_MATCH' if missing else 'SAME_LITERAL_TARGET_OBSERVATION',
                'independent_observation_verified':False})
        return result
    peer_map={r['id']:peers(r) for r in rows if 'target' in r['fields']}
    for current in [r for r in rows if r['record_kind']=='individual_targets']:
        f=current['fields'];has_target='target' in f
        earlier=[r for r in rows if has_target and 'target' in r['fields'] and r['fields']['firm_id']==f['firm_id']
                 and stamp(r['fields']['issued_at'])<stamp(f['issued_at']) and r['clock_status']!='AFTER_ORIGINAL_CUTOFF']
        earlier.sort(key=lambda r:(stamp(r['fields']['issued_at']),r['id']))
        same=peer_map.get(current['id'],[])
        related=[r for r in rows if r['id']==current['id'] or r['id'] in {p['record_id'] for p in same}]
        initiation=any(str(r['fields'].get('event_type','')).casefold()=='initiation' or r['raw_initiation_phrase_present'] for r in related)
        assessment={'record_id':current['id'],'source_ref':current['source_ref'],'issued_at':f['issued_at'],
            'original_target_value':str(number(f['target'])) if has_target else None,
            'literal_dimensions':{k:f.get(k) for k in TARGET_RECORD_DIMENSIONS},'same_time_observations':same,
            'earlier_same_firm_target_record_ids':[r['id'] for r in earlier],
            'status':'NO_TARGET_VALUE_IN_RECORD' if not has_target else 'AFTER_ORIGINAL_CUTOFF_NOT_COMPARED' if current['clock_status']=='AFTER_ORIGINAL_CUTOFF' else 'EARLIER_TARGETS_DISPOSITIONED' if earlier else 'NO_EARLIER_RECOGNIZED_TARGET_RECORD',
            'source_absence_established':False,'horizon_equivalence_inferred':False}
        assessments.append(assessment)
        if not has_target or current['clock_status']=='AFTER_ORIGINAL_CUTOFF':continue
        for previous in earlier:
            item=compare(previous,current,'target',initiation,TARGET_RECORD_DIMENSIONS)
            item.update(before_source_ref=previous['source_ref'],after_source_ref=current['source_ref'],
                before_issued_at=previous['fields']['issued_at'],after_issued_at=f['issued_at'],
                comparison_route='TARGET_RECORD_CHRONOLOGY',horizon_equivalence_inferred=False,
                before_same_time_observations=peer_map[previous['id']],after_same_time_observations=same)
            conflicts=[p for p in peer_map[previous['id']]+same if p['status']=='CONFLICTING_SAME_TIME_REPORTED_TARGET']
            if conflicts:
                item['status']='UNRESOLVED_SAME_TIME_TARGET_CONFLICT';item['reported_numeric_difference']=None
            item['same_time_conflicting_record_ids']=[p['record_id'] for p in conflicts]
            item['target_horizon_disposition']=('LITERAL_HORIZONS_DIFFER_NO_EQUIVALENCE_ASSUMED' if 'target_horizon' in item['mismatched_dimensions'] else
                'HORIZON_UNKNOWN_NO_EQUIVALENCE_ESTABLISHED' if 'target_horizon' in item['missing_dimensions'] else 'LITERAL_REPORTED_HORIZONS_MATCH')
            if item['status']=='MATCHED_REPORTED_REVISION':item['status']='MATCHED_REPORTED_TARGET_CHANGE'
            comparisons.append(item)
    return {'record_assessments':assessments,'comparisons':comparisons,
            'every_original_target_list_record_dispositioned':True,'same_time_records_ordered_as_revisions':False,
            'comparison_count_is_not_revision_count':True,'semantic_completeness_verified':False}


def analyze(corpus):
    rows, unsupported, cutoffs = records(corpus)
    link_target_dimensions(rows)
    events, comparisons = [], []
    for current in [r for r in rows if r['record_kind'] == 'events']:
        f = current['fields']
        earlier = [r for r in rows if r['fields']['firm_id'] == f['firm_id']
                   and stamp(r['fields']['issued_at']) < stamp(f['issued_at'])
                   and r['clock_status'] != 'AFTER_ORIGINAL_CUTOFF']
        initiation = str(f.get('event_type', '')).casefold() == 'initiation' or current['raw_initiation_phrase_present']
        conflict = initiation and bool(earlier)
        events.append({'record_id': current['id'], 'declared_event_type': f.get('event_type'),
            'coverage_status': 'UNRESOLVED_COVERAGE_CONFLICT' if conflict else 'INITIATION_LABEL_WITHOUT_EARLIER_RECOGNIZED_RECORD' if initiation else 'REPORTED_EVENT',
            'earlier_same_firm_record_ids': [r['id'] for r in earlier],
            'earlier_record_absence_established': False,
            'coverage_conflict_scope': 'Earlier same-firm evidence, when listed, requires issuer, analyst and coverage-scope review; an empty recognized-record list is not source-absence proof.'})
        if current['clock_status'] == 'AFTER_ORIGINAL_CUTOFF':continue
        for metric in METRICS:
            if metric not in f:continue
            candidates = [r for r in earlier if metric in r['fields']]
            if not candidates:
                comparisons.append({'metric': metric, 'after_record': current['id'], 'status': 'NO_EARLIER_RECOGNIZED_METRIC_RECORD', 'source_absence_established': False})
                continue
            # Retain every previous candidate. Never discard a conflicting basis
            # or convenient earlier record to manufacture one clean revision.
            for previous in candidates:
                comparisons.append(compare(previous, current, metric, conflict))
    return {'method': METHOD, 'status': 'PARTIAL_REPORTED_REVISION_EVIDENCE',
            'original_cutoff_refs': cutoffs, 'records': rows, 'event_assessments': events,
            'metric_comparisons': comparisons, 'target_record_coverage': target_record_coverage(rows), 'unsupported_json_sources': unsupported,
            'all_original_sources_bound': list(corpus.sources),
            'schema_scope': 'Root events and individual_targets arrays only; other text is retained by the coverage delivery, not semantically exhaustively parsed.',
            'comparison_count_is_not_revision_count': True,
            'source_authenticity_verified': False, 'semantic_completeness_verified': False,
            'metric_dimensions_are_distinct': True, 'execution_authorized': False}
