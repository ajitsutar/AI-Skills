"""Deterministic news triage and reviewed guidance arithmetic; never a trading signal."""
import argparse
from datetime import date, timedelta
import json
import math
from pathlib import Path
import re
from news_sources import digest, stamp, iso, save_json

METHOD = 'news-language-triage-1.0.0'
# Original small rule set, not a copied proprietary lexicon or trained classifier.
POSITIVE = {'beat', 'beats', 'exceeded', 'exceeds', 'growth', 'record', 'upgrade', 'upgrades', 'improved', 'improves'}
NEGATIVE = {'miss', 'misses', 'missed', 'decline', 'declines', 'downgrade', 'downgrades', 'loss', 'losses', 'default', 'fraud', 'bankruptcy', 'recall', 'breach'}
NEGATORS = {'no', 'not', 'never', 'without', 'unlikely'}
EVENTS = {
    'GUIDANCE_RAISE_HINT': r'\b(raise\w*|increas\w*|lift\w*)\b.{0,50}\b(guidance|outlook|forecast)\b',
    'GUIDANCE_CUT_HINT': r'\b(cut\w*|lower\w*|reduc\w*)\b.{0,50}\b(guidance|outlook|forecast)\b',
    'GUIDANCE_WITHDRAWAL_HINT': r'\b(withdraw\w*|suspend\w*)\b.{0,50}\b(guidance|outlook|forecast)\b',
    'GUIDANCE_REAFFIRMATION_HINT': r'\b(reaffirm\w*|reiterat\w*|maintain\w*)\b.{0,50}\b(guidance|outlook|forecast)\b',
    'GUIDANCE_REVIEW': r'\b(guidance|outlook|forecast|investor day|business update)\b',
    'PREANNOUNCEMENT_REVIEW': r'\b(preliminary|pre.?announce\w*)\b',
    'FINANCING_REVIEW': r'\b(offering|dilution|convertible|refinanc\w*)\b',
    'MATERIAL_RISK_REVIEW': r'\b(halt\w*|bankruptcy|litigation|recall|breach|restat\w*)\b',
}


def sentiment(text):
    words = re.findall(r"[a-z]+", text.lower())
    hits = []
    for i, word in enumerate(words):
        direction = 1 if word in POSITIVE else -1 if word in NEGATIVE else 0
        if direction:
            negated = any(w in NEGATORS for w in words[max(0, i-3):i])
            hits.append({'word': word, 'direction': -direction if negated else direction, 'negated': negated})
    signs = {h['direction'] for h in hits}
    label = 'MIXED' if len(signs) == 2 else 'POSITIVE_LANGUAGE' if signs == {1} else 'NEGATIVE_LANGUAGE' if signs == {-1} else 'UNSCORED'
    return {'label': label, 'rule_score': sum(h['direction'] for h in hits), 'hits': hits,
            'return_prediction': None, 'calibrated_confidence': None}


def issuers(record, aliases):
    text = record['title'] + ' ' + record.get('summary', '')
    found = set(record.get('scope_issuers', []))
    if record['source_kind'] == 'exchange' and record.get('exchange_fields', {}).get('IssueSymbol'):
        found.add(record['exchange_fields']['IssueSymbol'])
    for ticker, names in aliases.items():
        # Bare tickers such as A, IT, ALL and CAT are too ambiguous.
        if re.search(r'\$' + re.escape(ticker) + r'\b', text, re.I):
            found.add(ticker)
        if any(re.search(r'(?<!\w)' + re.escape(name) + r'(?!\w)', text, re.I) for name in names if len(name) >= 4):
            found.add(ticker)
    return sorted(found)


def analyze(report, config, as_of, lookback_hours=72):
    cutoff = stamp(as_of)
    if not math.isfinite(lookback_hours) or lookback_hours <= 0:
        raise ValueError('Positive finite lookback required')
    latest, rejected = {}, []
    for record in report['records']:
        if stamp(record['available_at']) > cutoff:
            rejected.append({'event_id': record['event_id'], 'reason': 'NOT_YET_OBSERVED_OR_FUTURE_DATED'})
            continue
        key = (record['source_id'], record.get('source_item_id') or record['url'] or record['title'])
        rank = lambda r: (r['available_at'], r.get('updated_at') or r.get('published_at') or '', r['event_id'])
        if key not in latest or rank(record) > rank(latest[key]):
            latest[key] = record
    records = []
    for record in latest.values():
        published = record.get('updated_at') or record.get('published_at') or record.get('event_at')
        window_start = cutoff - timedelta(hours=lookback_hours)
        recent_date = published is not None and stamp(published) >= window_start
        recent_observation = stamp(record['first_seen_at']) >= window_start
        if not recent_date and not recent_observation and record['evidence_kind'] != 'EXCHANGE_STATUS_EVENT':
            continue
        text = record['title'] + ' ' + record.get('summary', '')
        names = issuers(record, config.get('issuer_aliases', {}))
        review = sorted(k for k, pattern in EVENTS.items() if re.search(pattern, text, re.I))
        language = sentiment(text)
        if record['evidence_kind'] == 'FILING_METADATA_ONLY':
            language = sentiment('')
            review.append('READ_FILING_AND_EXHIBITS')
        if record['evidence_kind'] == 'EXCHANGE_STATUS_EVENT':
            language = sentiment('')
            review.append('VERIFY_CURRENT_HALT_AND_TRADE_RESUMPTION')
        # Confidence is not invented for headlines, ambiguous entities or missing times.
        eligible = (recent_date and len(names) == 1 and not record['flags'] and
                    record.get('source_refresh_status', 'PARSED') in ('PARSED', 'UNCHANGED') and
                    record['evidence_kind'] != 'FILING_METADATA_ONLY' and record['source_kind'] != 'macro')
        cluster = digest(json.dumps([names, re.sub(r'\W+', ' ', record['title'].lower()).strip()]))
        records.append({**record, 'issuers': names, 'language': language, 'review_events': review,
                        'recency_basis': 'DATED_EVENT_WITHIN_WINDOW' if recent_date else 'RECENT_OBSERVATION_OLD_OR_UNKNOWN_DATELINE' if recent_observation else 'EXCHANGE_STATUS_RECHECK_REQUIRED',
                        'cluster_id': cluster, 'issuer_sentiment_usable_for_research': eligible,
                        'requires_primary_review': True})
    records.sort(key=lambda r: (r['available_at'], r['event_id']))
    clusters = {}
    for r in records:
        if r['issuer_sentiment_usable_for_research']:
            clusters.setdefault((r['issuers'][0], r['cluster_id']), []).append(r)
    totals = {}
    for (issuer, _), rows in sorted(clusters.items()):
        labels = {r['language']['label'] for r in rows}
        # Conflicting excerpts of the same headline are unresolved, not multiple votes.
        label = next(iter(labels)) if len(labels) == 1 else 'MIXED'
        totals.setdefault(issuer, {}).setdefault(label, 0)
        totals[issuer][label] += 1
    gaps = [s for s in report['sources'] if s['status'] not in ('PARSED', 'EMPTY_VALID', 'UNCHANGED')]
    return {'method': METHOD, 'as_of': iso(cutoff), 'lookback_hours': lookback_hours,
            'implementation_sha256': digest(Path(__file__).read_bytes()),
            'input_sha256': digest(json.dumps(report, sort_keys=True)),
            'configuration_sha256': digest(json.dumps(config, sort_keys=True)),
            'records': records, 'excluded': rejected, 'unique_headline_cluster_counts': totals,
            'source_gaps_or_unpolled': gaps, 'coverage': 'PARTIAL_CONFIGURED_SOURCES',
            'alpha_validated': False, 'execution_authorized': False}


def evidence(ref, root, cutoff):
    base = Path(root).resolve()
    path = (base / ref['path']).resolve()
    if base not in path.parents or not path.is_file():
        raise ValueError('Missing or unsafe evidence path')
    raw = path.read_bytes()
    if not raw or digest(raw) != ref['sha256']:
        raise ValueError('Evidence bytes/hash mismatch')
    if not ref.get('url', '').startswith('https://'):
        raise ValueError('Evidence URL required')
    if stamp(ref['published_at']) > cutoff or stamp(ref['observed_at']) > cutoff:
        raise ValueError('Evidence not available at cutoff')
    if stamp(ref['observed_at']) < stamp(ref['published_at']):
        raise ValueError('Evidence observed before its publication')
    quote = ref.get('verbatim_excerpt', '')
    if not quote or quote not in raw.decode('utf-8', errors='replace') or not ref.get('locator'):
        raise ValueError('Saved UTF-8 evidence must contain the excerpt and have a locator')
    return digest(raw)


def guidance_change(request, source_root):
    cutoff = stamp(request['as_of'])
    old, new = request.get('previous'), request['current']
    keys = ('issuer', 'metric', 'period_start', 'period_end', 'currency', 'unit', 'accounting_basis')
    for item in [i for i in (old, new) if i is not None]:
        if any(not item.get(k) for k in keys):
            raise ValueError('Explicit guidance dimensions required')
        if date.fromisoformat(item['period_start']) > date.fromisoformat(item['period_end']):
            raise ValueError('Guidance period end precedes start')
        if item['source'].get('source_kind') not in ('issuer', 'sec'):
            raise ValueError('Primary issuer/SEC guidance evidence required')
        evidence(item['source'], source_root, cutoff)
        if item['status'] not in ('issued', 'withdrawn'):
            raise ValueError('Guidance status must be issued or withdrawn')
        if item['status'] == 'issued':
            if any(isinstance(item[k], bool) or not isinstance(item[k], (int, float)) or not math.isfinite(item[k]) for k in ('low', 'high')) or item['low'] > item['high']:
                raise ValueError('Finite ordered guidance range required')
    result = {'method': 'guidance-range-comparison-1.0.0', 'as_of': iso(cutoff),
              'implementation_sha256': digest(Path(__file__).read_bytes()),
              'classification': None, 'economic_direction': 'REQUIRES_METRIC_AND_CONTEXT_REVIEW',
              'numeric_extraction': 'REVIEWER_SUPPLIED_NOT_AUTOMATICALLY_AUTHENTICATED',
              'execution_authorized': False}
    if old and stamp(new['source']['published_at']) <= stamp(old['source']['published_at']):
        raise ValueError('Current disclosure must be later than previous disclosure')
    if old and any(old[k] != new[k] for k in keys):
        result['classification'] = 'NOT_COMPARABLE'
    elif new['status'] == 'withdrawn':
        result['classification'] = 'WITHDRAWN' if old and old['status'] == 'issued' else 'WITHDRAWAL_PRIOR_RANGE_UNKNOWN'
    elif not old or old['status'] == 'withdrawn':
        result['classification'] = 'ISSUED'
    else:
        lo, hi = new['low'] - old['low'], new['high'] - old['high']
        oldmid, newmid = (old['low'] + old['high']) / 2, (new['low'] + new['high']) / 2
        label = ('UNCHANGED_RANGE' if lo == hi == 0 else 'RAISED_RANGE' if lo >= 0 and hi >= 0
                 else 'LOWERED_RANGE' if lo <= 0 and hi <= 0 else 'MIXED_RANGE_CHANGE')
        result.update(classification=label, previous_midpoint=oldmid, current_midpoint=newmid,
                      midpoint_change=newmid-oldmid, midpoint_change_pct=(newmid/oldmid-1)*100 if oldmid > 0 else None,
                      ranges_overlap=max(old['low'], new['low']) <= min(old['high'], new['high']))
    result['input_sha256'] = digest(json.dumps(request, sort_keys=True))
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    subs = p.add_subparsers(dest='mode', required=True)
    n = subs.add_parser('triage')
    n.add_argument('news'); n.add_argument('config'); n.add_argument('as_of'); n.add_argument('output')
    n.add_argument('--lookback-hours', type=float, default=72)
    g = subs.add_parser('guidance')
    g.add_argument('input'); g.add_argument('source_root'); g.add_argument('output')
    a = p.parse_args()
    read = lambda path: json.loads(Path(path).read_text(encoding='utf-8'))
    result = (analyze(read(a.news), read(a.config), a.as_of, a.lookback_hours) if a.mode == 'triage'
              else guidance_change(read(a.input), a.source_root))
    save_json(a.output, result)
    print(json.dumps({k: v for k, v in result.items() if k != 'records'}, indent=2))


if __name__ == '__main__':
    main()
