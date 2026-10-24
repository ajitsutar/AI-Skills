"""Offline, evidence-bound sentiment research. See references/sentiment-toolkit.md.

python scripts/sentiment_toolkit.py {analyze,trend,fuse,backtest,calibrate,infer-local} input.json output.json
No downloads, training, broker operations, or changes to source evidence.
"""
import argparse
import copy
from collections import defaultdict
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
import math
from pathlib import Path
import re
import sys

VERSION = '1.0.0'
LABELS = ('negative', 'neutral', 'positive')
ASPECTS = {
    'revenue': r'\b(revenue|sales|bookings)\b',
    'earnings': r'\b(earnings|profit|profits|eps|margin|margins)\b',
    'balance_sheet': r'\b(debt|leverage|liquidity|solvency|cash)\b',
    'guidance': r'\b(guidance|outlook|forecast)\b',
    'governance': r'\b(fraud|restatement|lawsuit|governance|investigation)\b',
}
POSITIVE = {'beat', 'beats', 'strong', 'improved', 'improves', 'growth', 'record',
            'raised', 'raises', 'increase', 'increased', 'increases', 'rises', 'rise', 'rising', 'rose', 'up',
            'grew', 'grows', 'growing', 'higher'}
NEGATIVE = {'miss', 'misses', 'weak', 'decline', 'declined', 'falls', 'fell', 'down',
            'declines', 'declining', 'fall', 'falling', 'cut', 'cuts', 'reduced', 'reduces',
            'reduction', 'decrease', 'decreased', 'decreases', 'lower', 'lowered', 'lowering',
            'loss', 'losses', 'fraud', 'restatement'}
NEGATION = {'not', 'no', 'never', 'without'}
BALANCE_DIRECTION = {'increase', 'increased', 'increases', 'rises', 'rise', 'rising', 'rose', 'up',
                     'growth', 'grew', 'grows', 'growing', 'higher', 'raised', 'raises',
                     'decline', 'declined', 'declines', 'declining', 'fall', 'falls', 'fell', 'falling', 'down',
                     'cut', 'cuts', 'reduced', 'reduces', 'reduction', 'decrease', 'decreased',
                     'decreases', 'lower', 'lowered', 'lowering'}
DOCUMENT_KEYS = {
    'analyze': {'as_of', 'window_start', 'half_life_hours', 'entities', 'records', 'source_weights', 'required_aspects'},
    'trend': {'sentiment', 'entity', 'aspect', 'cutoffs'},
    'fuse': {'as_of', 'features'},
    'calibrate': {'rows', 'bins'},
    'backtest': {'sentiment', 'entity', 'aspect', 'threshold', 'cost_bps_per_unit_turnover', 'signal_policy', 'periods'},
}


def validate_document_keys(action, document):
    if not isinstance(document, dict):
        raise ValueError('DOCUMENT_OBJECT_REQUIRED')
    if set(document) - DOCUMENT_KEYS[action]:
        raise ValueError('UNKNOWN_' + action.upper() + '_DOCUMENT_FIELDS')


def resolve_document(action, document):
    """Materialize effective defaults for a portable frozen operation contract."""
    if action not in DOCUMENT_KEYS:
        raise ValueError('UNKNOWN_DETERMINISTIC_ACTION')
    validate_document_keys(action, document)
    result = copy.deepcopy(document)
    if action == 'analyze':
        result.setdefault('window_start', '1900-01-01T00:00:00Z')
        result.setdefault('half_life_hours', 72)
        result.setdefault('required_aspects', ['overall', *ASPECTS])
        result.setdefault('records', [])
        result.setdefault('source_weights', {})
        for row in result['records']:
            result['source_weights'].setdefault(row['source'], 1.0)
    elif action in ('trend', 'backtest'):
        result['sentiment'] = resolve_document('analyze', result['sentiment'])
        if action == 'backtest':
            result.setdefault('threshold', 0)
            result.setdefault('cost_bps_per_unit_turnover', 0)
            result.setdefault('signal_policy', 'long_cash')
            for period in result['periods']:
                period.setdefault('cash_return', 0)
    elif action == 'calibrate':
        result.setdefault('bins', 10)
    elif action != 'fuse':
        raise ValueError('UNKNOWN_DETERMINISTIC_ACTION')
    return result


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                     ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def text_hash(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def timestamp(value):
    if not isinstance(value, str):
        raise ValueError('TIMESTAMP_REQUIRED')
    result = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if result.tzinfo is None or result.utcoffset() is None:
        raise ValueError('TIMEZONE_REQUIRED')
    return result


def number(value, name, low=None, high=None):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError('INVALID_' + name)
    if low is not None and value < low or high is not None and value > high:
        raise ValueError('OUT_OF_RANGE_' + name)
    return float(value)


def nonempty(value, name):
    if not isinstance(value, str) or not value.strip():
        raise ValueError('REQUIRED_' + name)
    return value


def probabilities(values):
    if not isinstance(values, dict) or set(values) != set(LABELS):
        raise ValueError('EXACT_THREE_LABEL_PROBABILITIES_REQUIRED')
    values = {k: number(v, 'PROBABILITY', 0, 1) for k, v in values.items()}
    if not math.isclose(sum(values.values()), 1, abs_tol=1e-6):
        raise ValueError('PROBABILITIES_MUST_SUM_TO_ONE')
    return values


def binding(record, annotation):
    """Bind probabilities to the exact evidence, span, target and aspect."""
    return digest({'record_id': record['id'], 'text_sha256': text_hash(record['text']),
                   'source': record['source'], 'published_at': record['published_at'],
                   'available_at': record['available_at'], 'entity': annotation['entity'],
                   'aspect': annotation['aspect'], 'start': annotation['start'],
                   'end': annotation['end'],
                   'span': record['text'][annotation['start']:annotation['end']]})


def matches(text, entities):
    return [entity for entity, aliases in sorted(entities.items())
            if any(re.search(r'(?<!\w)' + re.escape(alias) + r'(?!\w)', text, re.I)
                   for alias in aliases)]


def baseline(text, aspect):
    words = re.findall(r"[a-z]+", text.lower())
    if aspect == 'balance_sheet':
        targets = {'debt' if w in {'debt', 'leverage'} else w
                   for w in words if w in {'debt', 'leverage', 'cash', 'liquidity', 'solvency'}}
        if len(targets) > 1:
            return {'polarity': None, 'probabilities': None,
                    'status': 'UNSCORED_AMBIGUOUS_BALANCE_TARGETS', 'hits': []}
    hits = []
    for i, word in enumerate(words):
        sign = 1 if word in POSITIVE else -1 if word in NEGATIVE else 0
        if not sign:
            continue
        if any(w in NEGATION for w in words[max(0, i - 3):i]):
            sign *= -1
        # Higher debt/leverage is not favorable merely because it 'rises'.
        if aspect == 'balance_sheet' and any(w in {'debt', 'leverage'} for w in words):
            if word in BALANCE_DIRECTION:
                sign *= -1
        hits.append({'word': word, 'sign': sign, 'token_index': i})
    if not hits:
        return {'polarity': None, 'probabilities': None, 'status': 'UNSCORED_NO_RULE_HIT', 'hits': []}
    # An evidence score, deliberately not a fabricated class probability.
    return {'polarity': sum(h['sign'] for h in hits) / len(hits), 'probabilities': None,
            'status': 'SCORED_LOW_ASSURANCE', 'hits': hits}


def annotations_for(record, entities):
    if 'annotations' in record:
        annotations = record['annotations']
        if not isinstance(annotations, list):
            raise ValueError('ANNOTATIONS_LIST_REQUIRED')
        return annotations, []
    annotations, omitted = [], []
    # Do not propagate a company name across clauses: ambiguous pronouns remain missing.
    for span in re.finditer(r'[^.;!?]+', record['text']):
        text = span.group()
        found = matches(text, entities)
        aspects = [a for a, pattern in ASPECTS.items() if re.search(pattern, text, re.I)]
        if len(found) != 1 or len(aspects) > 1:
            omitted.append({'start': span.start(), 'end': span.end(),
                            'reason': 'ENTITY_OR_ASPECT_AMBIGUOUS', 'entities': found, 'aspects': aspects})
            continue
        annotations.append({'entity': found[0], 'aspect': aspects[0] if aspects else 'overall',
                            'start': span.start(), 'end': span.end()})
    return annotations, omitted


def validate_entities(entities):
    if not isinstance(entities, dict) or not entities:
        raise ValueError('ENTITY_ALIASES_REQUIRED')
    for entity, aliases in entities.items():
        nonempty(entity, 'ENTITY')
        if not isinstance(aliases, list) or not aliases:
            raise ValueError('ALIASES_REQUIRED')
        for alias in aliases:
            nonempty(alias, 'ALIAS')


def analyze(document):
    validate_document_keys('analyze', document)
    cutoff = timestamp(document['as_of'])
    start = timestamp(document.get('window_start', '1900-01-01T00:00:00Z'))
    if start > cutoff:
        raise ValueError('INVALID_WINDOW')
    half_life = number(document.get('half_life_hours', 72), 'HALF_LIFE', 0)
    if half_life == 0:
        raise ValueError('POSITIVE_HALF_LIFE_REQUIRED')
    entities = document['entities']
    validate_entities(entities)
    weights = {k: number(v, 'SOURCE_WEIGHT', 0) for k, v in document.get('source_weights', {}).items()}
    records = document.get('records', [])
    scored, excluded, omissions, seen = [], [], [], set()
    for record in records:
        key = nonempty(record.get('id'), 'RECORD_ID')
        if key in seen:
            raise ValueError('DUPLICATE_RECORD_ID')
        seen.add(key)
        nonempty(record.get('text'), 'TEXT')
        nonempty(record.get('source'), 'SOURCE')
        pub, available = timestamp(record['published_at']), timestamp(record['available_at'])
        if available < pub:
            raise ValueError('AVAILABLE_BEFORE_PUBLICATION')
        reason = 'FUTURE_OR_UNAVAILABLE' if max(pub, available) > cutoff else 'OUTSIDE_WINDOW' if pub < start else None
        if reason:
            excluded.append({'id': key, 'reason': reason})
            continue
        annotations, omitted = annotations_for(record, entities)
        omissions.extend({'id': key, **o} for o in omitted)
        spans_seen = set()
        for annotation in annotations:
            entity = annotation['entity']
            aspect = nonempty(annotation.get('aspect'), 'ASPECT')
            left, right = annotation['start'], annotation['end']
            if entity not in entities:
                raise ValueError('UNKNOWN_ENTITY')
            if any(isinstance(i, bool) or not isinstance(i, int) for i in (left, right)) or not 0 <= left < right <= len(record['text']):
                raise ValueError('INVALID_EVIDENCE_SPAN')
            span_key = (entity, aspect, left, right)
            if span_key in spans_seen:
                raise ValueError('DUPLICATE_ANNOTATION')
            spans_seen.add(span_key)
            span = record['text'][left:right]
            if entity not in matches(record['text'], entities):
                raise ValueError('TARGET_NOT_IN_DOCUMENT')
            explicit = 'annotations' in record
            result = baseline(span, aspect)
            method = 'deterministic_context_rules_v1'
            model = None
            supplied = annotation.get('prediction')
            if supplied is not None:
                if supplied.get('binding_sha256') != binding(record, annotation):
                    raise ValueError('PREDICTION_EVIDENCE_BINDING_MISMATCH')
                model = {'id': nonempty(supplied.get('model_id'), 'MODEL_ID'),
                         'revision': nonempty(supplied.get('model_revision'), 'MODEL_REVISION')}
                if model['revision'].lower() in {'main', 'latest', 'master'}:
                    raise ValueError('PINNED_MODEL_REVISION_REQUIRED')
                computed = timestamp(supplied['computed_at'])
                if computed < available:
                    raise ValueError('PREDICTION_BEFORE_EVIDENCE_AVAILABLE')
                if computed > cutoff:
                    omissions.append({'id': key, 'entity': entity, 'aspect': aspect,
                                      'reason': 'PREDICTION_NOT_AVAILABLE_AT_CUTOFF'})
                    continue
                prob = probabilities(supplied['probabilities'])
                method = 'supplied_probabilities_not_independently_inferred'
                result = {'polarity': prob['positive'] - prob['negative'], 'probabilities': prob,
                          'status': 'SCORED_SUPPLIED_PREDICTION', 'hits': []}
            age_hours = (cutoff - pub).total_seconds() / 3600
            weight = weights.get(record['source'], 1.0) * 2 ** (-age_hours / half_life)
            event = record.get('reviewed_event_id')
            if event is not None:
                nonempty(event, 'REVIEWED_EVENT_ID')
                nonempty(record.get('event_review_note'), 'EVENT_REVIEW_NOTE')
            normalized = ' '.join(re.findall(r'\w+', span.lower()))
            # Exact normalized duplicates only. Near-similarity is flagged below, never collapsed.
            group = 'reviewed:' + event if event else 'exact:' + digest([normalized, pub.astimezone(timezone.utc).isoformat()])
            scored.append({'record_id': key, 'entity': entity, 'aspect': aspect,
                           'span': span, 'start': left, 'end': right, 'binding_sha256': binding(record, annotation),
                           'group': group, 'source': record['source'], 'published_at': record['published_at'],
                           'available_at': record['available_at'], 'weight': weight, 'method': method,
                           'model': model, 'attribution': 'supplied_span_annotation' if explicit else 'unambiguous_clause_rule',
                           **result})
    groups = defaultdict(list)
    for row in scored:
        groups[(row['entity'], row['aspect'], row['group'])].append(row)
    event_rows = []
    for (entity, aspect, group), rows in sorted(groups.items()):
        unique = {}
        for row in rows:
            if row['polarity'] is None or row['weight'] <= 0:
                continue
            fingerprint = digest([' '.join(re.findall(r'\w+', row['span'].lower())),
                                  timestamp(row['published_at']).astimezone(timezone.utc).isoformat(),
                                  row['polarity']])
            if fingerprint not in unique or row['weight'] > unique[fingerprint]['weight']:
                unique[fingerprint] = row
        valid = list(unique.values())
        denom = sum(r['weight'] for r in valid)
        polarity = sum(r['weight'] * r['polarity'] for r in valid) / denom if denom else None
        event_rows.append({'entity': entity, 'aspect': aspect, 'group': group,
                           'record_ids': sorted({r['record_id'] for r in rows}),
                           'polarity': polarity, 'weight': max((r['weight'] for r in valid), default=0),
                           'contradictory': any(r['polarity'] > 0 for r in valid) and any(r['polarity'] < 0 for r in valid)})
    # Flag candidate syndication conservatively; never equate similarity with same economic event.
    candidates = []
    for i, a in enumerate(scored):
        ta = set(re.findall(r'\w+', a['span'].lower()))
        for b in scored[i + 1:]:
            if (a['entity'], a['aspect']) != (b['entity'], b['aspect']) or a['group'] == b['group']:
                continue
            tb = set(re.findall(r'\w+', b['span'].lower()))
            similarity = len(ta & tb) / len(ta | tb) if ta | tb else 0
            if len(ta | tb) >= 6 and similarity >= 0.85:
                candidates.append({'record_ids': [a['record_id'], b['record_id']], 'jaccard': similarity,
                                   'status': 'REVIEW_NEEDED_NOT_MERGED'})
    summaries = []
    expected = document.get('required_aspects', ['overall', *ASPECTS])
    if not isinstance(expected, list) or not expected or any(not isinstance(a, str) or not a.strip() for a in expected):
        raise ValueError('REQUIRED_ASPECTS_LIST_REQUIRED')
    for entity in sorted(entities):
        aspects = sorted(set(expected) | {r['aspect'] for r in event_rows if r['entity'] == entity})
        for aspect in aspects:
            rows = [r for r in event_rows if r['entity'] == entity and r['aspect'] == aspect]
            valid = [r for r in rows if r['polarity'] is not None and r['weight'] > 0]
            denom = sum(r['weight'] for r in valid)
            value = sum(r['weight'] * r['polarity'] for r in valid) / denom if denom else None
            summaries.append({'entity': entity, 'aspect': aspect, 'polarity': value,
                              'status': 'MISSING' if value is None else 'NEUTRAL_OR_BALANCED' if abs(value) < 1e-12 else 'SCORED',
                              'distinct_event_count': len(rows), 'scored_event_count': len(valid),
                              'contradictory': any(r['contradictory'] for r in rows) or
                                  (any(r['polarity'] > 0 for r in valid) and any(r['polarity'] < 0 for r in valid))})
    return {'schema': 'sentiment-toolkit/1', 'tool_version': VERSION, 'input_sha256': digest(document),
            'as_of': document['as_of'], 'scores': scored, 'events': event_rows, 'summary': summaries,
            'excluded_records': excluded, 'omitted_spans': omissions, 'possible_duplicates': candidates,
            'coverage': {'record_count': len(records), 'eligible_record_count': len(records) - len(excluded),
                         'scored_span_count': sum(r['polarity'] is not None for r in scored),
                         'unscored_span_count': sum(r['polarity'] is None for r in scored),
                         'missing_entity_aspects': [{'entity': r['entity'], 'aspect': r['aspect']} for r in summaries if r['polarity'] is None]},
            'limitations': ['Source weights and event IDs are supplied judgments, not learned reliability.',
                            'Rule scores are low-assurance lexical evidence, not calibrated probabilities or forecasts.',
                            'Supplied timestamps, provenance and target/aspect annotations are not independently verified.',
                            'No predictive advantage or execution authorization is established.']}


def calibrate(document):
    """Multiclass Brier, log loss, accuracy and equal-width confidence ECE."""
    validate_document_keys('calibrate', document)
    rows = document['rows']
    if not isinstance(rows, list) or not rows:
        raise ValueError('CALIBRATION_ROWS_REQUIRED')
    count = document.get('bins', 10)
    if isinstance(count, bool) or not isinstance(count, int) or not 1 <= count <= 100:
        raise ValueError('INVALID_BIN_COUNT')
    groups, brier, logloss, correct, seen = defaultdict(list), 0, 0, 0, set()
    model_keys = set()
    for row in rows:
        key = nonempty(row.get('id'), 'ROW_ID')
        if key in seen:
            raise ValueError('DUPLICATE_CALIBRATION_ID')
        seen.add(key)
        if row['label'] not in LABELS:
            raise ValueError('INVALID_LABEL')
        model_keys.add((nonempty(row.get('model_id'), 'MODEL_ID'), nonempty(row.get('model_revision'), 'MODEL_REVISION')))
        if timestamp(row['predicted_at']) >= timestamp(row['label_available_at']):
            raise ValueError('PREDICTION_MUST_PRECEDE_LABEL_AVAILABILITY')
        p = probabilities(row['probabilities'])
        winner = max(LABELS, key=lambda x: p[x])  # tie order fixed and disclosed
        hit = int(winner == row['label'])
        confidence = p[winner]
        brier += sum((p[k] - int(k == row['label'])) ** 2 for k in LABELS)
        logloss -= math.log(max(p[row['label']], 1e-15))
        correct += hit
        groups[min(count - 1, int(confidence * count))].append((confidence, hit))
    if len(model_keys) != 1:
        raise ValueError('CALIBRATE_ONE_PINNED_MODEL_AT_A_TIME')
    if next(iter(model_keys))[1].lower() in {'main', 'master', 'latest'}:
        raise ValueError('PINNED_MODEL_REVISION_REQUIRED')
    bins = []
    for key, values in sorted(groups.items()):
        bins.append({'lower': key / count, 'upper': (key + 1) / count, 'count': len(values),
                     'mean_confidence': sum(v[0] for v in values) / len(values),
                     'accuracy': sum(v[1] for v in values) / len(values)})
    n = len(rows)
    return {'input_sha256': digest(document), 'sample_count': n, 'multiclass_brier_sum': brier / n,
            'log_loss': logloss / n, 'accuracy': correct / n,
            'expected_calibration_error': sum(b['count'] / n * abs(b['mean_confidence'] - b['accuracy']) for b in bins),
            'bins': bins, 'tie_order': list(LABELS), 'model': list(next(iter(model_keys))),
            'status': 'DESCRIPTIVE_SUPPLIED_HOLDOUT_LABELS_NOT_PROOF_OF_GENERALIZATION'}


def trend(document):
    """Snapshots and expanding z-scores using prior scored snapshots only."""
    validate_document_keys('trend', document)
    cutoffs = document['cutoffs']
    parsed = [timestamp(t) for t in cutoffs]
    if not parsed or any(b <= a for a, b in zip(parsed, parsed[1:])):
        raise ValueError('STRICTLY_INCREASING_CUTOFFS_REQUIRED')
    history, rows = [], []
    for cutoff in cutoffs:
        result = analyze({**document['sentiment'], 'as_of': cutoff})
        value = next((r['polarity'] for r in result['summary']
                      if r['entity'] == document['entity'] and r['aspect'] == document['aspect']), None)
        n = len(history)
        mean = sum(history) / n if n else None
        sd = math.sqrt(sum((v - mean) ** 2 for v in history) / (n - 1)) if n >= 2 else None
        z = (value - mean) / sd if value is not None and sd and sd > 0 else None
        rows.append({'as_of': cutoff, 'polarity': value, 'prior_observation_count': n,
                     'prior_mean': mean, 'prior_sample_sd': sd, 'prior_only_z_score': z,
                     'status': 'MISSING' if value is None else 'INSUFFICIENT_OR_CONSTANT_HISTORY' if z is None else 'NORMALIZED'})
        if value is not None:
            history.append(value)
    return {'input_sha256': digest(document), 'rows': rows,
            'normalization': 'Expanding prior nonmissing observations; sample standard deviation; no future fit.',
            'limitation': 'Overlapping news windows induce dependence; z-score is not a predictive significance test.'}


def fuse(document):
    """Transparent fixed-weight composite of already normalized supplied features."""
    validate_document_keys('fuse', document)
    cutoff = timestamp(document['as_of'])
    features = document['features']
    if not features:
        raise ValueError('FEATURES_REQUIRED')
    rows, seen = [], set()
    numerator = denominator = total_weight = 0.0
    for feature in features:
        name = nonempty(feature.get('name'), 'FEATURE_NAME')
        if name in seen:
            raise ValueError('DUPLICATE_FEATURE')
        seen.add(name)
        weight = number(feature['weight'], 'FEATURE_WEIGHT', 0)
        total_weight += weight
        status = 'MISSING'
        value = feature.get('value')
        if value is not None:
            value = number(value, 'NORMALIZED_FEATURE', -1, 1)
            nonempty(feature.get('normalization'), 'NORMALIZATION_METHOD')
            if not re.fullmatch(r'[0-9a-fA-F]{64}', str(feature.get('evidence_sha256', ''))):
                raise ValueError('VALID_FEATURE_EVIDENCE_SHA256_REQUIRED')
            available = timestamp(feature['available_at'])
            observed = timestamp(feature['observed_at'])
            if available < observed:
                raise ValueError('FEATURE_AVAILABLE_BEFORE_OBSERVED')
            status = 'FUTURE_OR_UNAVAILABLE' if available > cutoff else 'INCLUDED'
            if status == 'INCLUDED':
                numerator += weight * value
                denominator += weight
        rows.append({'name': name, 'value': value, 'weight': weight, 'status': status})
    return {'input_sha256': digest(document), 'as_of': document['as_of'], 'features': rows,
            'composite': numerator / denominator if denominator else None,
            'weight_coverage': denominator / total_weight if total_weight else None,
            'status': 'COMPLETE' if denominator and denominator == total_weight else 'PARTIAL' if denominator else 'MISSING',
            'method': 'Supplied fixed positive weights, normalized over available features; no trained policy or return forecast.'}


def backtest(document):
    """Signal at decision time, next interval exposure; turnover costs including liquidation."""
    validate_document_keys('backtest', document)
    data = document['sentiment']
    bars = document['periods']
    if not isinstance(bars, list) or not bars:
        raise ValueError('PERIODS_REQUIRED')
    entity, aspect = document['entity'], document['aspect']
    threshold = number(document.get('threshold', 0), 'THRESHOLD', 0, 1)
    bps = number(document.get('cost_bps_per_unit_turnover', 0), 'COST_BPS', 0, 10000)
    if document.get('signal_policy', 'long_cash') != 'long_cash':
        raise ValueError('ONLY_LONG_CASH_IMPLEMENTED')
    rows, prev_exposure, wealth, basewealth, last_end = [], 0, 1, 1, None
    for i, bar in enumerate(bars):
        decision, begin, end = timestamp(bar['decision_at']), timestamp(bar['start']), timestamp(bar['end'])
        if not decision < begin < end or last_end is not None and begin < last_end:
            raise ValueError('CAUSAL_NONOVERLAPPING_PERIODS_REQUIRED')
        last_end = end
        ret = number(bar['asset_return'], 'RETURN', -1)
        cash = number(bar.get('cash_return', 0), 'CASH_RETURN', -1)
        frozen = {**data, 'as_of': bar['decision_at']}
        result = analyze(frozen)
        selected = next((r for r in result['summary'] if r['entity'] == entity and r['aspect'] == aspect), None)
        score = selected['polarity'] if selected else None
        exposure = int(score is not None and score > threshold)
        turnover = abs(exposure - prev_exposure)
        cost = turnover * bps / 10000
        gross = exposure * ret + (1 - exposure) * cash
        # Costs deducted before investment; explicitly compound rather than silently subtract bps.
        factor = (1 - cost) * (1 + gross)
        basecost = bps / 10000 if i == 0 else 0
        basefactor = (1 - basecost) * (1 + ret)
        if i == len(bars) - 1:
            factor *= 1 - exposure * bps / 10000
            basefactor *= 1 - bps / 10000
        wealth *= factor
        basewealth *= basefactor
        rows.append({'decision_at': bar['decision_at'], 'start': bar['start'], 'end': bar['end'],
                     'polarity': score, 'exposure': exposure, 'turnover': turnover,
                     'entry_rebalance_cost_fraction': cost, 'final_exit_cost_fraction': exposure * bps / 10000 if i == len(bars) - 1 else 0,
                     'gross_return': gross, 'net_return': factor - 1, 'wealth': wealth,
                     'buy_hold_wealth': basewealth, 'evidence_snapshot_sha256': result['input_sha256']})
        prev_exposure = exposure
    return {'input_sha256': digest(document), 'periods': rows, 'net_total_return': wealth - 1,
            'buy_hold_net_total_return': basewealth - 1, 'excess_return': wealth - basewealth,
            'missing_signal_periods': sum(r['polarity'] is None for r in rows),
            'status': 'EXPLORATORY_FIXED_POLICY_REPLAY',
            'limitations': ['Supplied returns and historical availability require independent validation.',
                            'Threshold, source weights and model must be fixed before held-out evaluation.',
                            'No intraperiod execution, market impact, shorting, tax or out-of-sample guarantee.']}


def infer_local(document):
    """Optional HF classifier; only an existing directory, hash-pinned files and packages."""
    model = document['model']
    license_info = model.get('license', {})
    for key in ('identifier', 'source_url', 'intended_use', 'weights_terms', 'training_data_terms_review'):
        nonempty(license_info.get(key), 'MODEL_LICENSE_' + key.upper())
    if license_info.get('use_permitted_attestation') is not True:
        raise ValueError('MODEL_USE_PERMISSION_ATTESTATION_REQUIRED')
    directory = Path(model['directory']).resolve()
    if not directory.is_dir():
        return {'status': 'UNAVAILABLE', 'reason': 'LOCAL_MODEL_DIRECTORY_MISSING', 'input_sha256': digest(document)}
    revision = nonempty(model.get('revision'), 'MODEL_REVISION')
    if revision.lower() in {'main', 'master', 'latest'}:
        raise ValueError('PINNED_MODEL_REVISION_REQUIRED')
    files = model.get('files_sha256')
    if not isinstance(files, dict) or not files or 'config.json' not in files:
        raise ValueError('MODEL_FILE_HASH_MANIFEST_REQUIRED')
    actual_files = {p.relative_to(directory).as_posix(): p for p in directory.rglob('*') if p.is_file()}
    if set(actual_files) != set(files):
        raise ValueError('MODEL_MANIFEST_FILE_SET_MISMATCH')
    for name, path in actual_files.items():
        if path.is_symlink() or not path.resolve().is_relative_to(directory):
            raise ValueError('MODEL_LINK_OUTSIDE_DIRECTORY')
        hasher = hashlib.sha256()
        with path.open('rb') as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b''):
                hasher.update(chunk)
        if hasher.hexdigest() != files[name]:
            raise ValueError('MODEL_FILE_HASH_MISMATCH')
    if not any(n.endswith('.safetensors') for n in files):
        raise ValueError('SAFETENSORS_WEIGHTS_REQUIRED')
    versions = model.get('package_versions', {})
    if set(versions) != {'torch', 'transformers', 'tokenizers', 'safetensors'}:
        raise ValueError('PINNED_RUNTIME_VERSIONS_REQUIRED')
    try:
        observed = {name: importlib.metadata.version(name) for name in versions}
    except importlib.metadata.PackageNotFoundError:
        return {'status': 'UNAVAILABLE', 'reason': 'OPTIONAL_MODEL_DEPENDENCY_MISSING', 'input_sha256': digest(document)}
    if versions != observed:
        return {'status': 'UNAVAILABLE', 'reason': 'PINNED_RUNTIME_VERSION_MISMATCH', 'observed_versions': observed, 'input_sha256': digest(document)}
    try:
        import torch
        from transformers import AutoModelForSequenceClassification, AutoTokenizer
        tokenizer = AutoTokenizer.from_pretrained(str(directory), local_files_only=True, trust_remote_code=False)
        classifier, loading = AutoModelForSequenceClassification.from_pretrained(
            str(directory), local_files_only=True, trust_remote_code=False,
            use_safetensors=True, output_loading_info=True)
        if any(loading.get(k) for k in ('missing_keys', 'unexpected_keys', 'mismatched_keys', 'error_msgs')):
            raise ValueError('INCOMPLETE_OR_MISMATCHED_CLASSIFIER_WEIGHTS')
        classifier.to('cpu')
        classifier.eval()
        torch.set_num_threads(1)
        torch.use_deterministic_algorithms(True)
        mapping = {int(k): v for k, v in model['label_mapping'].items()}
        if set(mapping) != set(range(classifier.config.num_labels)) or sorted(mapping.values()) != sorted(LABELS):
            raise ValueError('EXPLICIT_THREE_CLASS_LABEL_MAPPING_REQUIRED')
        configured = {int(k): str(v).lower() for k, v in classifier.config.id2label.items()}
        if set(configured.values()) == set(LABELS) and configured != mapping:
            raise ValueError('LABEL_MAPPING_CONTRADICTS_MODEL_CONFIG')
        predictions = []
        for row in document['items']:
            record, annotation = row['record'], row['annotation']
            left, right = annotation['start'], annotation['end']
            if any(isinstance(i, bool) or not isinstance(i, int) for i in (left, right)) or not 0 <= left < right <= len(record['text']):
                raise ValueError('INVALID_EVIDENCE_SPAN')
            if timestamp(record['available_at']) < timestamp(record['published_at']):
                raise ValueError('AVAILABLE_BEFORE_PUBLICATION')
            if timestamp(record['available_at']) > datetime.now(timezone.utc):
                raise ValueError('FUTURE_EVIDENCE_UNAVAILABLE')
            span = record['text'][annotation['start']:annotation['end']]
            nonempty(span, 'SPAN')
            encoded = tokenizer(span, return_tensors='pt', truncation=False)
            maximum = min(int(model.get('max_tokens', 512)), int(getattr(classifier.config, 'max_position_embeddings', 512)))
            if encoded['input_ids'].shape[-1] > maximum:
                raise ValueError('SPAN_EXCEEDS_MODEL_CONTEXT_NO_SILENT_TRUNCATION')
            with torch.no_grad():
                prob = torch.softmax(classifier(**encoded).logits, dim=-1)[0].tolist()
            # Availability is the actual completion receipt, never the batch start or a backdated input.
            computed_at = datetime.now(timezone.utc)
            predictions.append({'record_id': record['id'], 'entity': annotation['entity'], 'aspect': annotation['aspect'],
                                'prediction': {'binding_sha256': binding(record, annotation),
                                               'model_id': nonempty(model.get('id'), 'MODEL_ID'), 'model_revision': revision,
                                               'model_manifest_sha256': digest(files), 'computed_at': computed_at.isoformat(),
                                               'probabilities': {mapping[i]: p for i, p in enumerate(prob)}}})
        return {'status': 'INFERRED_LOCAL_MODEL', 'input_sha256': digest(document), 'predictions': predictions,
                'runtime_versions': observed, 'model_license': license_info,
                'portable_contract_sha256': digest({'model': {k: v for k, v in model.items() if k != 'directory'}, 'items': document['items']}),
                'scope': 'Whole supplied span sentiment; entity/aspect attribution is supplied, not learned.'}
    except (ImportError, OSError, RuntimeError) as exc:
        return {'status': 'UNAVAILABLE', 'reason': 'LOCAL_MODEL_RUNTIME_FAILURE',
                'error_type': type(exc).__name__, 'input_sha256': digest(document)}


OPERATIONS = {'sentiment.analyze': analyze, 'sentiment.trend': trend,
              'sentiment.fuse': fuse, 'sentiment.calibrate': calibrate, 'sentiment.backtest': backtest}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('analyze', 'trend', 'fuse', 'calibrate', 'backtest', 'infer-local'))
    parser.add_argument('input', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    document = json.loads(args.input.read_text(encoding='utf-8-sig'))
    result = {'analyze': analyze, 'trend': trend, 'fuse': fuse, 'calibrate': calibrate, 'backtest': backtest, 'infer-local': infer_local}[args.action](document)
    # Preserve evidence and previous outputs: the caller chooses a fresh output path.
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, indent=2, ensure_ascii=False, allow_nan=False)
        stream.write('\n')
    return 2 if result.get('status') == 'UNAVAILABLE' else 0


if __name__ == '__main__':
    sys.exit(main())
