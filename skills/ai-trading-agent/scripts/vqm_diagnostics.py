"""Selected VQM snapshot diagnostics; no scoring or complete-ingress claim."""
import copy
import hashlib
import json
from datetime import date
from decimal import Decimal, localcontext
from news_evidence import decode, pointer
from deterministic_rank import digest, number
from price_audit import timestamp
from vqm_research import fact_value

METHOD = 'vqm-selected-snapshot-diagnostic-1.0.0'


def require(ok, error):
    if not ok:
        raise ValueError(error)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def load_bound(raw, expected):
    require(isinstance(raw, bytes) and sha(raw) == expected, 'INPUT_BYTE_HASH_MISMATCH')
    return decode(raw, exact_numbers=True)


def scalar(doc, path):
    try:
        value = pointer(doc, path)
    except (KeyError, IndexError):
        return {'pointer': path, 'status': 'KEY_NOT_PRESENT_AT_BOUND_POINTER', 'value': None}
    require(not isinstance(value, (dict, list)), 'SCALAR_POINTER_REQUIRED')
    return {'pointer': path, 'status': 'NULL' if value is None else 'PRESENT', 'value': value}


def numeric(value):
    return number(str(value)) if isinstance(value, Decimal) else number(value)


def ratio(a, b, numerator, denominator):
    try:
        a, b = numeric(a), numeric(b)
    except (TypeError, ValueError):
        return {'status': 'UNAVAILABLE_OPERAND', 'value': None,
                'numerator': numerator, 'denominator': denominator}
    if b == 0:
        return {'status': 'UNDEFINED_ZERO_DENOMINATOR', 'value': None,
                'numerator': numerator, 'denominator': denominator}
    with localcontext() as ctx:
        ctx.prec = 40
        return {'status': 'ARITHMETIC_ONLY', 'value': str(a / b),
                'numerator': numerator, 'denominator': denominator}


def check_dates(row, cutoff, profile):
    output = {'age_limit_days': profile['max_financial_period_age_days'],
              'policy_pointer': '/max_financial_period_age_days'}
    try:
        end = date.fromisoformat(row['financial_period_end'])
        start = date.fromisoformat(row['ttm_start'])
        age = (cutoff.date() - end).days
        duration = (end - start).days + 1
        output.update(period_age_days=age, duration_days=duration,
                      age_status='WITHIN_BOUND_POLICY' if 0 <= age <= output['age_limit_days'] else 'OUTSIDE_BOUND_POLICY',
                      duration_status='TTM_LENGTH_SUPPORTED' if 350 <= duration <= 380 else 'TTM_LENGTH_UNSUPPORTED')
    except (KeyError, TypeError, ValueError):
        output.update(age_status='UNKNOWN_INVALID_OR_MISSING_DATE',
                      duration_status='UNKNOWN_INVALID_OR_MISSING_DATE')
    return output


def audit_vqm(raw, raw_sha, profile_raw, profile_sha):
    snapshot = load_bound(raw, raw_sha)
    profile = load_bound(profile_raw, profile_sha)
    require(snapshot.get('schema_version') == 1, 'ONLY_EXISTING_VQM_SCHEMA1_SUPPORTED')
    require(snapshot.get('profile_sha256') == digest(profile), 'PROFILE_CANONICAL_HASH_MISMATCH')
    require(type(profile.get('max_financial_period_age_days')) is int and
            profile['max_financial_period_age_days'] > 0, 'BOUND_FINANCIAL_AGE_POLICY_REQUIRED')
    cutoff = timestamp(snapshot['information_cutoff'])
    sources = {s['source_id']: s for s in snapshot['sources']}
    require(len(sources) == len(snapshot['sources']), 'DUPLICATE_SOURCE_ID')
    rows = snapshot['rows']
    symbols = [r['symbol'] for r in rows]
    require(len(symbols) == len(set(symbols)) and set(symbols) == set(snapshot['universe_symbols']) and
            len(symbols) == len(snapshot['universe_symbols']), 'COMPLETE_UNIVERSE_ROWS_REQUIRED')
    results = []
    for i, row in enumerate(rows):
        path = '/rows/' + str(i)
        dates = check_dates(row, cutoff, profile)
        observations = {}
        for name, kind in [('market_cap', 'market'), ('close_price', 'market'), ('net_income_ttm', 'financial')]:
            factpath = path + '/facts/' + name
            f = row.get('facts', {}).get(name, {})
            sid = f.get('source_id')
            source = sources.get(sid, {})
            record = {'value': scalar(snapshot, factpath + '/value'),
                      'unit': scalar(snapshot, factpath + '/unit'),
                      'period_end': scalar(snapshot, factpath + '/period_end'),
                      'period_start': scalar(snapshot, factpath + '/period_start'),
                      'source_id': sid, 'declared_source_metadata': source,
                      'source_authenticity_verified': False}
            try:
                # Preserve Decimal leaves while adapting to the accepted numeric API.
                native_row = copy.deepcopy(row)
                if isinstance(f.get('value'), Decimal):
                    native_row['facts'][name]['value'] = str(f['value'])
                value = fact_value(native_row, name, sources, cutoff, kind,
                                   row.get('financial_period_end') if kind == 'financial' else None)
                record.update(native_fact_status='SUPPORTED_DECLARATIONS', numeric_value=str(value))
            except (ValueError, KeyError, TypeError, AttributeError) as exc:
                record.update(native_fact_status='UNSUPPORTED_OR_UNRESOLVED', native_error=str(exc))
            observations[name] = record
        errors = [k for k, v in observations.items() if v['native_fact_status'] != 'SUPPORTED_DECLARATIONS']
        extra = []
        if row.get('facts', {}).get('market_cap', {}).get('period_end') != cutoff.date().isoformat():
            extra.append('MARKET_CAP_DATE')
        if row.get('facts', {}).get('net_income_ttm', {}).get('period_start') != row.get('ttm_start'):
            extra.append('TTM_START')
        if row.get('currency') != 'USD': extra.append('CURRENCY_UNSUPPORTED')
        if row.get('accounting_basis') != 'reported_gaap_ttm': extra.append('ACCOUNTING_BASIS')
        if row.get('latest_public_period_checked') is not True: extra.append('LATEST_PERIOD_UNREVIEWED')
        if row.get('source_conflicts') != []: extra.append('SOURCE_CONFLICT_UNRESOLVED')
        eligible = not errors and not extra and dates['age_status'] == 'WITHIN_BOUND_POLICY' and dates['duration_status'] == 'TTM_LENGTH_SUPPORTED'
        def value(name): return row.get('facts', {}).get(name, {}).get('value')
        def ref(name): return path + '/facts/' + name + '/value'
        ratios = {'aggregate_cap_over_income': ratio(value('market_cap'), value('net_income_ttm'), ref('market_cap'), ref('net_income_ttm')),
                  'aggregate_income_over_cap': ratio(value('net_income_ttm'), value('market_cap'), ref('net_income_ttm'), ref('market_cap')),
                  'conditional_share_equivalent': ratio(value('market_cap'), value('close_price'), ref('market_cap'), ref('close_price'))}
        for key in ['market_cap', 'close_price']:
            try:
                if numeric(value(key)) <= 0: extra.append('NONPOSITIVE_' + key.upper())
            except (TypeError, ValueError): pass
        basis = {name: scalar(snapshot, path + '/' + name) for name in
                 ['market_cap_scope', 'price_share_class', 'class_price_mapping', 'common_income_attribution', 'weighted_average_share_basis']}
        income = observations['net_income_ttm'].get('numeric_value')
        sign = 'UNKNOWN' if income is None else 'NEGATIVE' if numeric(income) < 0 else 'ZERO' if numeric(income) == 0 else 'POSITIVE'
        results.append({'row_pointer': path, 'symbol': row['symbol'], 'timing': dates,
                        'timing_disposition': 'CURRENT_PRICE_TRAILING_PERIOD_SUPPORTED_BY_DECLARATIONS' if eligible else 'UNRESOLVED_OR_INELIGIBLE_DECLARATIONS',
                        'timing_disposition_scope': 'Clock, financial-period and supplied freshness declarations only; does not certify positive valuation operands, class mapping or overall comparability.',
                        'valuation_operands_supported': not errors and not extra,
                        'ordinary_period_gap_is_mismatch': False,
                        'unsupported_facts': errors, 'other_checks': extra,
                        'facts': observations, 'ratios': ratios, 'income_sign': sign,
                        'basis': basis, 'actual_total_shares': None, 'reported_eps': None,
                        'ratio_interpretation': 'Aggregate arithmetic only; common-claim interpretation remains conditional. Cap/quote is a conditional equivalent, not a certified all-class count or EPS denominator.'})
    return {'method': METHOD, 'operation': 'vqm_snapshot_observations',
            'inputs': {'snapshot_raw_sha256': raw_sha, 'profile_raw_sha256': profile_sha,
                       'profile_canonical_sha256': digest(profile)},
            'coverage': {'rows_total': len(rows), 'rows_audited': len(results), 'scope': 'all snapshot rows, three named valuation facts and declared profile; no calendar, momentum, scoring or complete user-request certification'},
            'profile_age_limit_days': profile['max_financial_period_age_days'], 'rows': results,
            'calendar_verified': False, 'source_authenticity_verified': False,
            'latest_release_independently_verified': False, 'whole_request_complete': False}


def diagnose_snapshot(raw, package_root, original_error):
    """Describe selected bytes without replacing the original scoring failure."""
    from pathlib import Path
    root = Path(package_root)
    profile_path = 'profiles/vqm-fundamental-v1.json'
    profile_raw = (root / profile_path).read_bytes()
    package_raw = (root / 'PACKAGE-MANIFEST.json').read_bytes()
    require(decode(package_raw)['files'].get(profile_path) == sha(profile_raw),
            'PACKAGED_PROFILE_BYTES_CHANGED')
    profile = load_bound(profile_raw, sha(profile_raw))
    result = {'status': 'SELECTED_SNAPSHOT_AUDIT_ONLY_SCORING_FAILED',
              'full_ingress': 'NOT_BOUND', 'snapshot_raw_sha256': sha(raw),
              'profile_binding': {'path': profile_path, 'raw_sha256': sha(profile_raw),
                                  'canonical_sha256': digest(profile),
                                  'package_manifest_sha256': sha(package_raw)},
              'original_failure': {'type': type(original_error).__name__,
                                   'module': original_error.name, 'message': str(original_error)},
              'score': None, 'ranking': None, 'source_authenticity_verified': False,
              'whole_answer_verified': False,
              'scope': 'Selected snapshot bytes and resolved packaged profile only; no complete ingress/request, calendar, latest-publication or prose certification.'}
    try:
        result['audit'] = audit_vqm(raw, sha(raw), profile_raw, sha(profile_raw))
    except (ValueError, KeyError, TypeError, AttributeError) as error:
        result.update(status='SELECTED_SNAPSHOT_AUDIT_UNAVAILABLE', audit=None,
                      diagnostic_error={'type': type(error).__name__, 'message': str(error)})
    return result
