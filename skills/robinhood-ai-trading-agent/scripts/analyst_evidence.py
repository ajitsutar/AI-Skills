"""Replay a source-backed analyst evidence pack; do not invent report access or skill."""
import argparse
from datetime import timedelta
import json
import math
from pathlib import Path
import statistics
from news_analysis import evidence
from news_sources import digest, stamp, iso, save_json


def number(value, positive=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or (positive and value <= 0):
        raise ValueError('Finite numeric value required')
    return value


def percentile(values, fraction):
    values = sorted(values)
    index = (len(values)-1)*fraction
    lo = math.floor(index)
    return values[lo] + (values[min(lo+1, len(values)-1)]-values[lo])*(index-lo)


def review(request, source_root):
    cutoff = stamp(request['as_of'])
    dimensions = ('issuer', 'currency', 'price_basis', 'target_horizon')
    if any(not request.get(k) for k in dimensions):
        raise ValueError('Issuer, currency, split/share-price basis and explicit forward target horizon required')
    if request['target_horizon'] not in ('forward_12_months', 'forward_52_weeks'):
        raise ValueError('Use a separate cohort for fiscal-year or unspecified horizons')
    max_age = number(request.get('max_target_age_days', 90), True)
    max_quote_age = number(request.get('max_quote_age_hours', 96), True)
    latest, excluded, aggregates, stats = {}, [], [], []
    for r in request.get('individual_targets', []):
        key = r.get('record_id')
        try:
            evidence(r['source'], source_root, cutoff)
            if any(r.get(k) != request[k] for k in dimensions):
                raise ValueError('TARGET_DIMENSIONS_MISMATCH')
            if not r.get('firm_id') or not r.get('analyst_id'):
                raise ValueError('ANALYST_OR_FIRM_UNKNOWN')
            if r.get('access') not in ('FULL_REPORT', 'ATTRIBUTED_EXCERPT'):
                raise ValueError('REPORT_NOT_ACCESSED')
            issue = stamp(r['issued_at'])
            if issue > stamp(r['source']['published_at']):
                raise ValueError('TARGET_ISSUED_AFTER_SOURCE_PUBLICATION')
            if issue < cutoff - timedelta(days=max_age):
                raise ValueError('STALE_TARGET')
            number(r['target'], True)
            firm = r['firm_id']
            if firm not in latest or issue > stamp(latest[firm]['issued_at']):
                if firm in latest:
                    excluded.append({'record_id': latest[firm]['record_id'], 'reason': 'SUPERSEDED_FIRM_TARGET'})
                latest[firm] = r
            elif issue == stamp(latest[firm]['issued_at']) and r['target'] != latest[firm]['target']:
                # Do not choose whichever simultaneous conflicting extraction appeared first.
                latest[firm] = dict(latest[firm], conflict=True)
                excluded.append({'record_id': key, 'reason': 'CONFLICTING_SAME_TIME_FIRM_TARGET'})
            else:
                excluded.append({'record_id': key, 'reason': 'DUPLICATE_OR_OLDER_FIRM_TARGET'})
        except (ValueError, KeyError, TypeError, OSError) as exc:
            excluded.append({'record_id': key, 'reason': str(exc)})
    rows = []
    for firm in sorted(latest):
        if latest[firm].get('conflict'):
            excluded.append({'record_id': latest[firm]['record_id'], 'reason': 'UNRESOLVED_FIRM_CONFLICT'})
        else:
            rows.append(latest[firm])
    values = [r['target'] for r in rows]
    consensus = {'status': 'UNAVAILABLE', 'independent_firms': len(rows)}
    if values:
        med = statistics.median(values)
        q1, q3 = percentile(values, .25), percentile(values, .75)
        consensus.update(status='PARTIAL_OBSERVED_COHORT', mean=statistics.mean(values), median=med,
                         minimum=min(values), maximum=max(values), q1=q1, q3=q3, iqr_over_median=(q3-q1)/med)
        if request.get('quote'):
            quote = request['quote']
            evidence(quote['source'], source_root, cutoff)
            if any(quote.get(k) != request[k] for k in ('issuer', 'currency', 'price_basis')):
                raise ValueError('Quote and targets must have identical issuer/currency/share basis')
            price = number(quote['price'], True)
            fresh = stamp(quote['source']['published_at']) >= cutoff - timedelta(hours=max_quote_age)
            consensus['quote_status'] = 'WITHIN_DECLARED_RESEARCH_AGE_LIMIT' if fresh else 'STALE'
            consensus['median_implied_price_change_pct'] = (med/price-1)*100 if fresh else None
            consensus['quote_published_at'] = quote['source']['published_at']
    # Provider consensus pools may overlap. Keep them separate; do not average their averages.
    for r in request.get('provider_consensus', []):
        evidence(r['source'], source_root, cutoff)
        for k in ('mean', 'median', 'minimum', 'maximum'):
            if r.get(k) is not None:
                number(r[k], True)
        for k in ('analyst_count', 'target_count'):
            if r.get(k) is not None and (isinstance(r[k], bool) or not isinstance(r[k], int) or r[k] < 1):
                raise ValueError('Positive integer consensus count required')
        if r.get('minimum') is not None and r.get('maximum') is not None:
            if r['minimum'] > r['maximum'] or any(r.get(k) is not None and not r['minimum'] <= r[k] <= r['maximum'] for k in ('mean', 'median')):
                raise ValueError('Invalid provider target range')
        aggregates.append({**r, 'status': 'PROVIDER_REPORTED_NOT_COMBINED',
                           'comparable_dimensions': all(r.get(k) == request[k] for k in dimensions)})
    for r in request.get('analyst_track_records', []):
        evidence(r['source'], source_root, cutoff)
        required = ('analyst_id', 'firm_id', 'provider', 'evaluation_start', 'evaluation_end',
                    'holding_rule', 'benchmark', 'return_definition', 'methodology_url')
        missing = [k for k in required if not r.get(k)]
        for k in ('success_rate_pct', 'average_return_pct'):
            if r.get(k) is None:
                missing.append(k)
        if r.get('success_rate_pct') is not None and not r.get('success_definition'):
            missing.append('success_definition')
        if r.get('success_rate_pct') is not None and not 0 <= number(r['success_rate_pct']) <= 100:
            raise ValueError('Success percentage outside 0..100')
        if r.get('average_return_pct') is not None:
            number(r['average_return_pct'])
        n = r.get('recommendation_count')
        if n is not None and (isinstance(n, bool) or not isinstance(n, int) or n < 1):
            raise ValueError('Positive integer recommendation count required')
        if n is None:
            missing.append('recommendation_count')
        if r.get('evaluation_end') and stamp(r['evaluation_end']) > cutoff:
            raise ValueError('Future performance record')
        if r.get('evaluation_end') and stamp(r['evaluation_end']) > stamp(r['source']['published_at']):
            raise ValueError('Performance period exceeds supporting source publication')
        if r.get('evaluation_start') and r.get('evaluation_end') and stamp(r['evaluation_start']) > stamp(r['evaluation_end']):
            raise ValueError('Performance evaluation period reversed')
        stats.append({**r, 'status': 'PROVIDER_REPORTED_PARTIAL' if missing else 'PROVIDER_REPORTED_WITH_METHOD',
                      'missing': missing, 'independently_reproduced': False,
                      'selection_weight': None})
    return {'method': 'analyst-evidence-1.0.0', 'as_of': iso(cutoff), 'target_horizon': request['target_horizon'],
            'implementation_sha256': digest(Path(__file__).read_bytes()),
            'input_sha256': digest(json.dumps(request, sort_keys=True)), 'consensus': consensus,
            'individual_targets_used': rows, 'excluded': excluded, 'provider_consensus': aggregates,
            'analyst_track_records': stats, 'source_discovery': request.get('source_discovery', []),
            'coverage': 'OBSERVED_SOURCES_ONLY', 'strong_buy_available': False,
            'execution_authorized': False, 'numeric_extraction': 'REVIEWER_SUPPLIED_NOT_AUTOMATICALLY_AUTHENTICATED'}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('input'); p.add_argument('source_root'); p.add_argument('output')
    a = p.parse_args()
    result = review(json.loads(Path(a.input).read_text(encoding='utf-8')), a.source_root)
    save_json(a.output, result)
    print(json.dumps({'consensus': result['consensus'], 'excluded': result['excluded']}, indent=2))


if __name__ == '__main__':
    main()
