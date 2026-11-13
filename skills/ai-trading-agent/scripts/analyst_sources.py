"""Offline analyst extraction, coverage, calculation and reporting from pinned bytes.

Bounded grammars are deliberately conservative. Unknown text is evidence to
review, not permission to supply identities, clocks or cohort dimensions.
"""
from __future__ import annotations

from decimal import Decimal
import hashlib
import json
from pathlib import Path
import re

from source_claims import Corpus, analyst_numbers
from news_sources import stamp

METHOD = 'analyst-sources-1'
FIELDS = ('firm_id', 'analyst_id', 'issuer', 'currency', 'target', 'issued_at',
          'published_at', 'observed_at', 'price_basis', 'target_horizon', 'access', 'url')
DIMENSIONS = ('issuer', 'currency', 'price_basis', 'target_horizon')
TOKEN = r'[A-Za-z0-9][A-Za-z0-9_.-]*'
NUMBER = r'[0-9]+(?:\.[0-9]+)?'
FULL = re.compile(
    rf'Firm (?P<firm_id>{TOKEN}), analyst (?P<analyst_id>{TOKEN}), '
    rf'issued (?P<issued_at>\d{{4}}-\d{{2}}-\d{{2}}T\d{{2}}:\d{{2}}:\d{{2}}(?:Z|[+-]\d{{2}}:\d{{2}})): '
    rf'(?P<issuer>{TOKEN}) target (?P<currency>[A-Z]{{3}}) (?P<target>{NUMBER}) '
    r'per (?P<price_basis>common share); horizon (?P<target_horizon>[a-z0-9_]+); '
    r'access (?P<access>[A-Z_]+)\. No split adjustment\.(?: Targets are opinions\.)?')
REVISION = re.compile(
    rf'(?P<firm_id>{TOKEN}) initiated new coverage (?P<issue_date_text>[^:\n]+): '
    rf'(?P<context>[^\n]*); target (?P<currency>[A-Z]{{3}}) (?P<target>{NUMBER})\.'
    r'(?: No prior same-basis estimate is supplied\.)?')
RELEVANT = re.compile(r'\b(?:target|targets|consensus)\b', re.I)


def require(ok, message):
    if not ok:
        raise ValueError(message)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False,
                      allow_nan=False, default=str).encode('utf-8')


def _objects(value, pointer=''):
    if isinstance(value, dict):
        yield pointer, value
        for key, child in value.items():
            yield from _objects(child, pointer + '/' + key.replace('~', '~0').replace('/', '~1'))
    elif isinstance(value, list):
        for i, child in enumerate(value):
            yield from _objects(child, pointer + '/' + str(i))


def _array_text(value, pointer=''):
    if isinstance(value, dict):
        for key, child in value.items():
            yield from _array_text(child, pointer + '/' + key.replace('~', '~0').replace('/', '~1'))
    elif isinstance(value, list):
        for i, child in enumerate(value):
            if isinstance(child, str) and RELEVANT.search(child):
                yield pointer + '/' + str(i)
            else:
                yield from _array_text(child, pointer + '/' + str(i))


def _labelled(text, sid, start):
    """Canonical key:value records; no regex/field mappings supplied by caller."""
    values, bindings = {}, {}
    cursor = 0
    for segment in text.split(';'):
        match = re.fullmatch(r'\s*([a-z_]+)\s*:\s*(.*?)\s*', segment)
        require(match is not None, 'UNSUPPORTED_LABELLED_RECORD')
        key, value = match.groups()
        require(key in FIELDS and key not in values and value, 'UNKNOWN_OR_DUPLICATE_ROLE')
        values[key] = value
        bindings[key] = {'source_ref': {'source_id': sid, 'start': start + cursor + match.start(2),
                                      'end': start + cursor + match.end(2), 'excerpt': value},
                         'role': key, 'transform': 'DECIMAL' if key == 'target' else 'IDENTITY'}
        cursor += len(segment) + 1
    require('target' in values, 'TARGET_ROLE_REQUIRED')
    return values, bindings


def _record(sid, ref, values, bindings, grammar):
    fields = {key: values.get(key) for key in FIELDS}
    require(all(value is None or isinstance(value, str) for key, value in fields.items()
                if key != 'target'), 'TEXT_ROLE_FIELD_REQUIRED')
    target = fields['target']
    if target is not None:
        require(not isinstance(target, bool), 'TARGET_NUMBER_REQUIRED')
        number = Decimal(str(target))
        require(number.is_finite() and number > 0, 'POSITIVE_FINITE_TARGET_REQUIRED')
        fields['target'] = analyst_numbers(number)
    missing = [key for key in FIELDS if fields[key] is None]
    return {'record_id': digest(encoded({'source': sid, 'ref': ref})),
            'source_id': sid, 'source_ref': ref, 'fields': fields, 'bindings': bindings,
            'missing_fields': missing, 'extraction_status': 'PARTIAL' if missing else 'EXTRACTED',
            'grammar': grammar, 'source_authenticity_verified': False}


def _extract(corpus, formats):
    records, unresolved, inventory, unsupported = [], [], [], []
    for sid, source in sorted(corpus.sources.items()):
        count = 0
        before = len(unresolved)
        if source['format'] == 'bytes':
            unsupported.append(sid)
        elif source['format'] == 'json':
            for pointer in _array_text(source['document']):
                count += 1
                unresolved.append({'source_ref': {'source_id': sid, 'pointer': pointer},
                                   'reason': 'UNSUPPORTED_TARGET_JSON'})
            for pointer, obj in _objects(source['document']):
                # Canonical role keys bind scalars within a single object. No
                # ancestor metadata, aliases or sibling-record borrowing.
                if 'target' not in obj:
                    for key, value in obj.items():
                        if (re.search(r'target|consensus', key, re.I) or
                            isinstance(value, str) and RELEVANT.search(value)):
                            count += 1
                            unresolved.append({'source_ref': {'source_id': sid, 'pointer': pointer + '/' +
                                key.replace('~', '~0').replace('/', '~1')}, 'reason': 'UNSUPPORTED_TARGET_JSON'})
                    continue
                for key, value in obj.items():
                    if key not in FIELDS and (re.search(r'target|consensus', key, re.I) or
                                              isinstance(value, str) and RELEVANT.search(value)):
                        count += 1
                        unresolved.append({'source_ref': {'source_id': sid, 'pointer': pointer + '/' +
                            key.replace('~', '~0').replace('/', '~1')}, 'reason': 'UNSUPPORTED_ADDITIONAL_TARGET_JSON'})
                count += 1
                ref = {'source_id': sid, 'pointer': pointer + '/target'}
                if 'json_records' not in formats or isinstance(obj['target'], (list, dict)):
                    unresolved.append({'source_ref': ref, 'reason': 'UNSUPPORTED_TARGET_RECORD'})
                    continue
                values = {k: obj[k] for k in FIELDS if k in obj}
                bindings = {k: {'source_ref': {'source_id': sid, 'pointer': pointer + '/' + k},
                                'role': k, 'transform': 'DECIMAL' if k == 'target' else 'IDENTITY'} for k in values}
                try:
                    require(all(v is None or not isinstance(v, (dict, list)) for v in values.values()),
                            'SCALAR_ROLE_FIELDS_REQUIRED')
                    records.append(_record(sid, ref, values, bindings, 'canonical_json_record'))
                except (ValueError, TypeError, ArithmeticError) as exc:
                    unresolved.append({'source_ref': ref, 'reason': str(exc)})
        else:
            offset = 0
            for line in source['text'].splitlines(keepends=True):
                text = line.rstrip('\r\n')
                start = offset
                offset += len(line)
                if not RELEVANT.search(text):
                    continue
                count += 1
                ref = {'source_id': sid, 'start': start, 'end': start + len(text), 'excerpt': text}
                if 'labelled_records' in formats and re.search(r'(?:^|;)\s*target\s*:', text):
                    try:
                        values, bindings = _labelled(text, sid, start)
                        records.append(_record(sid, ref, values, bindings, 'canonical_labelled_record'))
                    except (ValueError, TypeError, ArithmeticError) as exc:
                        unresolved.append({'source_ref': ref, 'reason': str(exc)})
                    continue
                match = FULL.fullmatch(text) if 'labelled_sentences' in formats else None
                grammar = 'explicit_analyst_sentence'
                if match is None and 'labelled_sentences' in formats:
                    match = REVISION.fullmatch(text)
                    grammar = 'partial_revision_sentence'
                if match is None:
                    unresolved.append({'source_ref': ref, 'reason': 'UNSUPPORTED_TARGET_TEXT'})
                    continue
                values, bindings = {}, {}
                for key in FIELDS:
                    if key not in match.groupdict():
                        continue
                    raw = match[key]
                    values[key] = raw
                    field_ref = {'source_id': sid, 'start': start + match.start(key),
                                 'end': start + match.end(key), 'excerpt': raw}
                    transform = 'DECIMAL' if key == 'target' else 'IDENTITY'
                    if key == 'price_basis':
                        values[key] = 'common_share_unadjusted'
                        transform = 'EXPLICIT_COMMON_SHARE_AND_NO_SPLIT_ADJUSTMENT'
                    bindings[key] = {'source_ref': field_ref, 'record_ref': ref,
                                     'role': key, 'transform': transform}
                record = _record(sid, ref, values, bindings, grammar)
                record['uninterpreted_fields'] = {}
                for key in ('issue_date_text', 'context'):
                    if key in match.groupdict():
                        raw = match[key]
                        record['uninterpreted_fields'][key] = {'value': raw,
                            'source_ref': {'source_id': sid, 'start': start + match.start(key),
                                           'end': start + match.end(key), 'excerpt': raw},
                            'interpretation': 'RETAINED_TEXT_NOT_TYPED_OR_INHERITED_METADATA'}
                records.append(record)
        inventory.append({'source_id': sid, 'path': source['path'], 'sha256': source['sha256'],
                          'candidate_count': count, 'status': 'UNSUPPORTED' if sid in unsupported else
                          'UNRESOLVED_CANDIDATES' if len(unresolved) > before else 'SCANNED'})
    return records, unresolved, inventory, unsupported


def _latest(records, cutoff, issuer):
    groups, unresolved, excluded, future, other_issuer = {}, [], [], [], []
    for record in records:
        fields = record['fields']
        try:
            require(fields['issuer'] is not None, 'ISSUER_UNKNOWN')
            if fields['issuer'] != issuer:
                other_issuer.append(record['record_id'])
                continue
            require(isinstance(fields['firm_id'], str) and fields['firm_id'], 'FIRM_UNKNOWN')
            require(fields['target'] is not None, 'TARGET_UNKNOWN')
            when = stamp(fields['issued_at'])
            known_availability = [stamp(fields[key]) for key in ('published_at', 'observed_at')
                                  if fields[key] is not None]
            if when > cutoff or any(clock > cutoff for clock in known_availability):
                future.append(record['record_id'])
                continue
        except (ValueError, TypeError, KeyError, AttributeError):
            unresolved.append(record['record_id'])
            continue
        groups.setdefault(fields['firm_id'], []).append((when, record))
    latest = []
    for firm, rows in sorted(groups.items()):
        newest = max(when for when, _ in rows)
        selected = [row for when, row in rows if when == newest]
        earlier = [row['record_id'] for when, row in rows if when < newest]
        conflict = len({row['fields']['target'] for row in selected}) > 1
        mixed = len({tuple(row['fields'][key] for key in DIMENSIONS) for row in selected}) > 1
        latest.append({'firm_id': firm, 'record_ids': sorted(r['record_id'] for r in selected),
                       'selected_records': [{'record_id': row['record_id'], 'fields': row['fields'],
                                             'source_ref': row['source_ref']} for row in
                                            sorted(selected, key=lambda row: row['record_id'])],
                       'issued_at': selected[0]['fields']['issued_at'],
                       'status': 'MIXED_LATEST_DIMENSIONS' if mixed else
                                 'CONFLICTING_LATEST' if conflict else 'LATEST_PARSEABLE_ISSUE',
                       'older_record_ids': sorted(earlier)})
        excluded.extend(earlier)
    return {'status': 'UNRESOLVED' if unresolved else 'PARSEABLE_ISSUES_ONLY',
            'by_firm': latest, 'unresolved_record_ids': unresolved,
            'older_record_ids': sorted(excluded),
            'excluded_future_record_ids': sorted(future),
            'excluded_other_issuer_record_ids': sorted(other_issuer),
            'requested_issuer': issuer,
            'scope': 'Requested issuer only; unknown issuer or issue dates remain unresolved. Missing publication/observation clocks do not prove availability. No cross-dimension aggregation.'}


def analyze(request, manifest_path, expected_manifest_sha256, source_root=None):
    require(isinstance(request, dict) and set(request) == {'as_of', 'cohort', 'extraction_profile'},
            'SOURCE_FIRST_REQUEST_KEYS_REQUIRED_NO_LITERAL_TARGETS')
    profile = request['extraction_profile']
    require(isinstance(profile, dict) and set(profile) == {'formats'} and
            isinstance(profile['formats'], list) and profile['formats'] and
            len(profile['formats']) == len(set(profile['formats'])) and
            set(profile['formats']) <= {'json_records', 'labelled_records', 'labelled_sentences'}, 'SUPPORTED_PROFILE_REQUIRED')
    cohort = request['cohort']
    require(isinstance(cohort, dict) and set(cohort) == set(DIMENSIONS) and
            all(isinstance(v, str) and v for v in cohort.values()), 'EXPLICIT_COHORT_FILTER_REQUIRED')
    cutoff = stamp(request['as_of'])
    corpus = Corpus(manifest_path, expected_manifest_sha256, source_root)
    records, gaps, inventory, unsupported = _extract(corpus, set(profile['formats']))
    latest = _latest(records, cutoff, cohort['issuer'])
    rows, excluded = [], []
    for record in records:
        fields = record['fields']; reasons = []
        for key in FIELDS:
            if fields[key] is None:
                reasons.append('UNKNOWN:' + key)
        for key in DIMENSIONS:
            if fields[key] != cohort[key]:
                reasons.append('COHORT_MISMATCH:' + key)
        if reasons:
            excluded.append({'record_id': record['record_id'], 'reasons': reasons})
            continue
        source = corpus.sources[record['source_id']]
        # The downstream helper validates exact retained bytes/excerpt and clocks.
        excerpt = source['text'] if source['format'] == 'json' else record['source_ref']['excerpt']
        rows.append({**fields, 'record_id': record['record_id'],
                     'source': {'path': source['path'], 'sha256': source['sha256'],
                                'published_at': fields['published_at'], 'observed_at': fields['observed_at'],
                                'verbatim_excerpt': excerpt, 'url': fields['url'],
                                'locator': json.dumps(record['source_ref'], sort_keys=True)}})
    from analyst_evidence import review
    eligible = review({'as_of': request['as_of'], **cohort, 'individual_targets': rows}, corpus.root)
    incomplete = bool(gaps or unsupported or latest['unresolved_record_ids'])
    coverage = {'status': 'INCOMPLETE' if incomplete else 'SUPPORTED_GRAMMARS_SCANNED',
                'all_source_ids': sorted(corpus.sources), 'unresolved_candidates': gaps,
                'unsupported_sources': unsupported, 'semantic_completeness_verified': False,
                'source_absence_established': False}
    result = {'schema_version': 1, 'method': METHOD, 'manifest_sha256': expected_manifest_sha256,
              'request_sha256': digest(encoded(request)), 'implementation_sha256': digest(Path(__file__).read_bytes()),
              'source_inventory': inventory, 'records': records, 'coverage': coverage,
              'observed_latest': latest, 'eligible_cohort': {'status': 'HELPER_FILTERED_OBSERVED_ROWS',
                  'result': eligible, 'excluded': excluded}, 'source_authenticity_verified': False,
              'execution_authorized': False,
              'limits': ['Only the documented bounded grammars are supported; no whole-corpus semantic completeness.',
                         'Cohort filter values never fill missing source metadata.',
                         'Older eligible rows and latest observed issues are separate populations.',
                         'Provider pools and unsupported narrative are unresolved, not inferred constituent records.']}
    lines = ['Source-first analyst evidence', 'Coverage: ' + coverage['status'] + '.',
             'All ' + str(len(inventory)) + ' manifest sources inspected. Semantic completeness and publisher authenticity are not verified.',
             'Latest parseable issues for requested issuer (unknown issuer/date records remain unresolved; missing availability clocks are not proof of availability):']
    for row in latest['by_firm']:
        lines.append(json.dumps(row, sort_keys=True))
    lines += ['Unresolved issue record IDs: ' + json.dumps(latest['unresolved_record_ids']),
              'Unresolved extracted records: ' + json.dumps([record for record in records
                  if record['record_id'] in latest['unresolved_record_ids']], sort_keys=True),
              'Excluded future issue IDs: ' + json.dumps(latest['excluded_future_record_ids']),
              'Excluded other issuer IDs: ' + json.dumps(latest['excluded_other_issuer_record_ids']),
              'Separate eligible cohort: ' + json.dumps(eligible['consensus'], sort_keys=True),
              'Eligible record IDs: ' + json.dumps([r['record_id'] for r in eligible['individual_targets_used']]),
              'Exclusions: ' + json.dumps(excluded + eligible['excluded'], sort_keys=True),
              'Unsupported candidates: ' + str(len(gaps)) + '; unsupported sources: ' + json.dumps(unsupported),
              'This report certifies neither arbitrary prose nor an investment conclusion.']
    text = '\n'.join(lines) + '\n'
    result['report'] = {'text': text, 'sha256': digest(text.encode('utf-8')), 'whole_report_semantic_pass': False}
    return result
