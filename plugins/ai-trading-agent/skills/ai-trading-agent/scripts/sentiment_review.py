"""Bind qualitative reviewer interpretations to evidence; never compute a buy signal.

CLI: sentiment_review.py triage.json review.json new-output.json
The triage input is news_analysis.analyze output (as_of and records required).
Review schema::

    {"as_of": "2026-10-20T22:00:00Z", "window_start": "2026-10-19T22:00:00Z",
     "required_dimensions": ["news", "analyst"],
     "dimensions": {
       "news": {"status": "reviewed", "interpretation": "Reviewer interpretation",
                "evidence": [{"url": "https://issuer.example/release",
                              "observed_at": "2026-10-20T21:00:00Z",
                              "published_at": "2026-10-20T20:00:00Z"}]},
       "analyst": {"status": "unavailable", "reason": "Documented access limitation"},
       "price_volume": {"status": "not_attempted", "reason": "Outside declared scope"},
       "positioning": {"status": "not_attempted", "reason": "Outside declared scope"},
       "social": {"status": "not_attempted", "reason": "Outside declared scope"}},
     "event_reviews": [{"event_ids": ["actual-triage-event-id"],
                        "event_group_id": "reviewed-economic-event",
                        "interpretation": "Reviewer interpretation, not lexical output",
                        "evidence": [{"url": "https://issuer.example/release",
                                      "observed_at": "2026-10-20T21:00:00Z"}]}],
     "conclusion": "Optional supplied reviewer conclusion"}

All five dimensions must be disclosed; required_dimensions defaults to news and
analyst. Reviewed dimensions need evidence and interpretation; other statuses need
a reason. event_id is shorthand for a one-element event_ids list. Multiple event
IDs may share one interpretation for paraphrased syndication. Repeated groups or
clusters across reviews are rejected. Timestamps require explicit timezone.
published_at is optional; missing dates are never invented. Older/failed source
context is retained unchanged and never becomes fresh corroboration through review.
Evidence checks bind references and dates, not source truth or investment merit.
"""
import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
from urllib.parse import urlsplit

DIMENSIONS = ('news', 'analyst', 'price_volume', 'positioning', 'social')


def timestamp(value):
    if not isinstance(value, str):
        raise ValueError('TIMESTAMP_REQUIRED')
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError as exc:
        raise ValueError('INVALID_TIMESTAMP') from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError('TIMEZONE_REQUIRED')
    return parsed


def nonempty(value):
    return isinstance(value, str) and bool(value.strip())


def evidence(rows, cutoff):
    if not isinstance(rows, list) or not rows:
        raise ValueError('EVIDENCE_REQUIRED')
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError('INVALID_EVIDENCE_RECORD')
        url = urlsplit(row.get('url', ''))
        if url.scheme not in ('https', 'http') or not url.hostname or url.username or bool(url.password):
            raise ValueError('INVALID_EVIDENCE_URL')
        observed = timestamp(row.get('observed_at'))
        if observed > cutoff:
            raise ValueError('FUTURE_OBSERVATION')
        if row.get('published_at') is not None:
            published = timestamp(row['published_at'])
            if published > cutoff:
                raise ValueError('FUTURE_PUBLICATION')
            if published > observed:
                raise ValueError('OBSERVATION_PRECEDES_PUBLICATION')


def review(triage, document):
    cutoff = timestamp(document.get('as_of'))
    start = timestamp(document.get('window_start'))
    if start > cutoff:
        raise ValueError('INVALID_WINDOW')
    if timestamp(triage.get('as_of')) != cutoff:
        raise ValueError('TRIAGE_CUTOFF_MISMATCH')
    indexed = {}
    for row in triage.get('records', []):
        if not isinstance(row, dict):
            raise ValueError('INVALID_TRIAGE_RECORD')
        key = row.get('event_id')
        if not nonempty(key) or key in indexed:
            raise ValueError('INVALID_OR_DUPLICATE_TRIAGE_EVENT')
        indexed[key] = row
    dimensions = document.get('dimensions', {})
    if set(dimensions) != set(DIMENSIONS):
        raise ValueError('ALL_FIVE_DIMENSIONS_REQUIRED')
    required = document.get('required_dimensions', ['news', 'analyst'])
    if not isinstance(required, list) or not required or len(set(required)) != len(required) or not set(required) <= set(DIMENSIONS):
        raise ValueError('INVALID_REQUIRED_DIMENSIONS')
    gaps, partial = [], []
    for name in DIMENSIONS:
        item = dimensions[name]
        if not isinstance(item, dict):
            raise ValueError('INVALID_DIMENSION_RECORD')
        status = item.get('status')
        if status not in ('reviewed', 'unavailable', 'not_attempted'):
            raise ValueError('INVALID_DIMENSION_STATUS')
        if status == 'reviewed':
            evidence(item.get('evidence'), cutoff)
            if not nonempty(item.get('interpretation')):
                raise ValueError('REVIEWER_INTERPRETATION_REQUIRED')
        else:
            if not nonempty(item.get('reason')):
                raise ValueError('GAP_REASON_REQUIRED')
            if status == 'unavailable':
                partial.append(name)
            elif name in required:
                gaps.append(name)
            else:
                partial.append(name)
    retained, clusters, groups = [], set(), set()
    for item in document.get('event_reviews', []):
        if not isinstance(item, dict):
            raise ValueError('INVALID_EVENT_REVIEW')
        keys = item.get('event_ids', [item.get('event_id')])
        if not isinstance(keys, list) or not keys or len(set(keys)) != len(keys) or any(key not in indexed for key in keys):
            raise ValueError('UNKNOWN_EVENT_REFERENCE')
        originals = [indexed[key] for key in keys]
        item_clusters = {row.get('cluster_id') or key for key, row in zip(keys, originals)}
        group = item.get('event_group_id', originals[0].get('cluster_id') or keys[0])
        if not nonempty(group):
            raise ValueError('INVALID_EVENT_GROUP')
        if item_clusters & clusters or group in groups:
            raise ValueError('DUPLICATE_EVENT_GROUP_REVIEW')
        clusters.update(item_clusters)
        groups.add(group)
        evidence(item.get('evidence'), cutoff)
        if not nonempty(item.get('interpretation')):
            raise ValueError('REVIEWER_INTERPRETATION_REQUIRED')
        for original in originals:
            for field in ('first_seen_at', 'available_at', 'published_at', 'updated_at', 'event_at'):
                if original.get(field) is not None and timestamp(original[field]) > cutoff:
                    raise ValueError('FUTURE_TRIAGE_EVENT')
        retained.append({'event_ids': keys, 'event_group_id': group,
                         'automatic_language': originals[0].get('language'),
                         'automatic_language_by_event': {key: row.get('language') for key, row in zip(keys, originals)},
                         'source_context_by_event': {key: {field: row.get(field) for field in
                             ('recency_basis', 'issuer_sentiment_usable_for_research', 'flags',
                              'source_refresh_status', 'evidence_kind', 'source_kind',
                              'published_at', 'updated_at', 'first_seen_at', 'available_at')}
                             for key, row in zip(keys, originals)},
                         'reviewer_interpretation': item['interpretation'],
                         'evidence': item['evidence']})
    if dimensions['news']['status'] == 'reviewed' and not retained:
        raise ValueError('NEWS_EVENT_REVIEW_REQUIRED')
    unreviewed = sorted({r.get('cluster_id') or key for key, r in indexed.items()} - clusters)
    if unreviewed:
        gaps.append('unreviewed_news_event_groups')
    digest = lambda value: hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()
    return {'method': 'qualitative-evidence-review-1.0.0', 'as_of': document['as_of'],
            'window_start': document['window_start'], 'triage_sha256': digest(triage),
            'review_input_sha256': digest(document), 'dimensions': dimensions,
            'required_dimensions': required,
            'event_reviews': retained, 'unreviewed_event_groups': unreviewed,
            'coverage_status': 'INCOMPLETE' if gaps else 'PARTIAL' if partial else 'REVIEWED_DECLARED_SCOPE',
            'material_gaps': gaps, 'access_or_scope_gaps': partial,
            'reviewer_conclusion': document.get('conclusion'),
            'conclusion_kind': 'SUPPLIED_REVIEWER_INTERPRETATION_NOT_COMPUTED_SIGNAL',
            'evidence_validation': 'REFERENCE_AND_TIMESTAMP_CHECKS_NOT_SOURCE_AUTHENTICITY',
            'unscored_meaning': 'NO_LEXICON_HITS_NOT_NEUTRAL_NEGATIVE_OR_COMPLETE',
            'computed_sentiment_score': None, 'return_prediction': None,
            'execution_permission_effect': 'NONE_RESEARCH_ONLY', 'alpha_validated': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('triage')
    parser.add_argument('review')
    parser.add_argument('output')
    args = parser.parse_args()
    result = review(json.loads(Path(args.triage).read_text(encoding='utf-8-sig')),
                    json.loads(Path(args.review).read_text(encoding='utf-8-sig')))
    output = Path(args.output)
    if output.resolve() in (Path(args.triage).resolve(), Path(args.review).resolve()):
        raise ValueError('OUTPUT_MUST_NOT_OVERWRITE_INPUT')
    with output.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, indent=2)
        stream.write('\n')


if __name__ == '__main__':
    main()
