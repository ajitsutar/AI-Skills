"""Offline analyst extraction, coverage, calculation and reporting from pinned bytes.

Bounded grammars are deliberately conservative. Unknown text is evidence to
review, not permission to supply identities, clocks or cohort dimensions.
"""
from __future__ import annotations

from decimal import Decimal
from datetime import date
import hashlib
import json
import math
from pathlib import Path
import re

from source_claims import Corpus, analyst_numbers
from news_sources import stamp

METHOD = 'analyst-sources-1'
FIELDS = ('firm_id', 'analyst_id', 'issuer', 'currency', 'target', 'issued_at',
          'published_at', 'observed_at', 'price_basis', 'target_horizon', 'access', 'url')
DIMENSIONS = ('issuer', 'currency', 'price_basis', 'target_horizon')
AGE_DEFAULTS = {'max_target_age_days': 90, 'max_quote_age_hours': 96}
ORIGINAL_REQUIRED = set(DIMENSIONS) | {'as_of', 'individual_targets'}
ORIGINAL_OPTIONAL = {'provider_consensus', 'analyst_track_records', 'quote', 'source_discovery', *AGE_DEFAULTS}
SOURCE_METADATA = ('published_at', 'observed_at', 'url')
PROVIDER_STATISTICS = ('mean', 'median', 'minimum', 'maximum')
PROVIDER_COUNTS = ('target_count', 'analyst_count')
PROVIDER_FIELDS = ('provider', 'upstream', 'firm_population', 'as_of') + DIMENSIONS + PROVIDER_STATISTICS + PROVIDER_COUNTS + SOURCE_METADATA
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


def _age(value):
    """Use the helper's numeric age domain without silently losing precision."""
    require(type(value) in (int, float, Decimal), 'POSITIVE_FINITE_AGE_POLICY_REQUIRED')
    number = Decimal(str(value))
    require(number.is_finite() and number > 0, 'POSITIVE_FINITE_AGE_POLICY_REQUIRED')
    try:
        converted = value if type(value) is int else float(value)
        finite = math.isfinite(converted)
    except (OverflowError, ValueError):
        raise ValueError('AGE_POLICY_PRECISION_UNSUPPORTED') from None
    require(finite and Decimal(str(converted)) == number,
            'AGE_POLICY_PRECISION_UNSUPPORTED')
    return converted


def _original_shape(document):
    """Recognize root request contracts, never arbitrary neighboring records."""
    if not isinstance(document, dict):
        return False
    controls = set(DIMENSIONS) | {'as_of', *AGE_DEFAULTS}
    return (('individual_targets' in document and bool(controls & set(document))) or
            (set(DIMENSIONS) | {'as_of'} <= set(document) and
             not {'target', 'provider', 'firm_id'} & set(document)))


def _original_contract(document):
    require(ORIGINAL_REQUIRED <= set(document) <= ORIGINAL_REQUIRED | ORIGINAL_OPTIONAL,
            'ORIGINAL_ANALYST_REQUEST_SCHEMA_UNSUPPORTED')
    require(all(isinstance(document[k], str) and document[k].strip() for k in (*DIMENSIONS, 'as_of')),
            'ORIGINAL_ANALYST_REQUEST_DIMENSION_REQUIRED')
    stamp(document['as_of'])
    require(document['target_horizon'] in ('forward_12_months', 'forward_52_weeks'),
            'ORIGINAL_ANALYST_REQUEST_HORIZON_UNSUPPORTED')
    for key in ('individual_targets', 'provider_consensus', 'analyst_track_records', 'source_discovery'):
        if key in document:
            require(isinstance(document[key], list), 'ORIGINAL_ANALYST_REQUEST_COLLECTION_REQUIRED:' + key)
    if 'quote' in document:
        require(document['quote'] is None or isinstance(document['quote'], dict),
                'ORIGINAL_ANALYST_REQUEST_QUOTE_OBJECT_REQUIRED')
    for key in AGE_DEFAULTS:
        if key in document:
            _age(document[key])
    return document


def _request_filters(request, corpus):
    """Derive effective selection from an original root, or label literals honestly.

    This runs during every original-source replay, including legacy requests.
    A convenient authored plan cannot override a recognizable original contract.
    """
    reference_mode = 'original_request_ref' in request
    if reference_mode:
        require(set(request) == {'original_request_ref', 'extraction_profile'},
                'ORIGINAL_REQUEST_REFERENCE_NO_LITERAL_OVERRIDES')
        ref = request['original_request_ref']
        require(isinstance(ref, dict) and set(ref) == {'source_id', 'pointer'} and
                isinstance(ref['source_id'], str) and ref['pointer'] == '',
                'ORIGINAL_ANALYST_ROOT_REFERENCE_REQUIRED')
    else:
        require({'as_of', 'cohort', 'extraction_profile'} <= set(request) <=
                {'as_of', 'cohort', 'extraction_profile', *AGE_DEFAULTS},
                'SOURCE_FIRST_REQUEST_KEYS_REQUIRED_NO_LITERAL_TARGETS')
        cohort = request['cohort']
        require(isinstance(cohort, dict) and set(cohort) == set(DIMENSIONS) and
                all(isinstance(v, str) and v.strip() for v in cohort.values()), 'EXPLICIT_COHORT_FILTER_REQUIRED')
        stamp(request['as_of'])
        for key in AGE_DEFAULTS:
            if key in request:
                _age(request[key])
    originals = {}
    for sid, source in corpus.sources.items():
        if source['format'] == 'json' and _original_shape(source['document']):
            originals[sid] = _original_contract(source['document'])
    if reference_mode:
        require(ref['source_id'] in originals, 'ORIGINAL_ANALYST_REQUEST_NOT_FOUND')
        sid = ref['source_id']
    else:
        require(len(originals) <= 1, 'ORIGINAL_ANALYST_REQUEST_AMBIGUOUS')
        sid = next(iter(originals), None)
    supplied = originals[sid] if sid is not None else None
    if supplied is not None and not reference_mode:
        for key in DIMENSIONS:
            require(request['cohort'][key] == supplied[key], 'ORIGINAL_ANALYST_REQUEST_FILTER_MISMATCH:' + key)
        require(request['as_of'] == supplied['as_of'], 'ORIGINAL_ANALYST_REQUEST_FILTER_MISMATCH:as_of')
        for key, default in AGE_DEFAULTS.items():
            if key in request:
                require(_age(request[key]) == _age(supplied.get(key, default)),
                        'ORIGINAL_ANALYST_REQUEST_FILTER_MISMATCH:' + key)
    cohort = {key: supplied[key] for key in DIMENSIONS} if supplied is not None else dict(request['cohort'])
    as_of = supplied['as_of'] if supplied is not None else request['as_of']
    ages, bindings = {}, {}
    for key, default in AGE_DEFAULTS.items():
        authority = supplied if supplied is not None else request
        ages[key] = _age(authority.get(key, default))
    effective = {'as_of': as_of, 'cohort': cohort, **ages}
    for key in ('as_of', *DIMENSIONS, *AGE_DEFAULTS):
        value = cohort[key] if key in DIMENSIONS else effective[key]
        original_present = supplied is not None and key in supplied
        bindings[key] = {
            'effective_value': value,
            'origin': 'ORIGINAL_REQUEST' if original_present else
                      'DECLARED_FILTER' if supplied is None and (key in DIMENSIONS or key in request) else 'DOCUMENTED_DEFAULT',
            'source_ref': {'source_id': sid, 'pointer': '/' + key} if original_present else None,
            'source_sha256': corpus.sources[sid]['sha256'] if original_present else None,
            'source_value': str(supplied[key]) if original_present and isinstance(supplied[key], Decimal)
                            else supplied[key] if original_present else None,
            'source_value_type': 'decimal' if original_present and isinstance(supplied[key], Decimal)
                                 else type(supplied[key]).__name__ if original_present else None,
            'used_for_selection': key != 'max_quote_age_hours'}
    binding = {'status': 'SOURCE_REQUEST_BOUND' if supplied is not None else 'DECLARED_FILTER_ONLY',
        'original_request_ref': {'source_id': sid, 'pointer': ''} if supplied is not None else None,
        'original_request_sha256': corpus.sources[sid]['sha256'] if supplied is not None else None,
        'candidate_original_request_ids': sorted(originals), 'effective_filters': effective, 'fields': bindings,
        'original_member_pointers': ['/' + key.replace('~', '~0').replace('/', '~1') for key in sorted(supplied)] if supplied is not None else [],
        'unconsumed_original_members': [key for key in ('quote', 'analyst_track_records', 'source_discovery')
                                       if supplied is not None and key in supplied],
        'limits': ['Binding proves exact selection fields from the explicitly selected or unique original root, not user-intent semantics or source truth.',
                   'All corpus records remain grammar-scanned; request collections do not narrow the source inventory.',
                   'Quote analytics, performance records and source-discovery claims are not consumed by this cohort producer; quote-age policy is retained but unused.',
                   'Opaque share-basis labels are compared exactly; parser labels are never aliases or defaults for source records.']}
    return effective, binding


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


def _json_roles(obj, sid, pointer):
    """Bind explicit roles in this record, including its own source metadata.

    Only these three source keys have a nested form. The containing JSON remains
    the pinned evidence; a source path/URL is not followed or authenticated.
    """
    values = {key: obj[key] for key in FIELDS if key in obj}
    bindings = {key: {'source_ref': {'source_id': sid, 'pointer': pointer + '/' + key},
                      'role': key, 'transform': 'DECIMAL' if key == 'target' else 'IDENTITY'}
                for key in values}
    if 'source' in obj:
        source = obj['source']
        require(isinstance(source, dict), 'SOURCE_METADATA_OBJECT_REQUIRED')
        for key in SOURCE_METADATA:
            if key not in source:
                continue
            if key in values:
                # Null and malformed direct values are not repaired by another
                # declaration. Identical duplicates retain the direct pointer.
                require(type(values[key]) is type(source[key]) and values[key] == source[key],
                        'CONFLICTING_SOURCE_METADATA:' + key)
            else:
                values[key] = source[key]
                bindings[key] = {'source_ref': {'source_id': sid,
                                                'pointer': pointer + '/source/' + key},
                                 'role': key, 'transform': 'IDENTITY'}
    require(all(v is None or not isinstance(v, (dict, list)) for v in values.values()),
            'SCALAR_ROLE_FIELDS_REQUIRED')
    return values, bindings


def _provider_candidate(pointer, obj):
    return ('provider' in obj and any(k in obj for k in PROVIDER_STATISTICS + PROVIDER_COUNTS)
            or re.search(r'/provider_consensus/\d+$', pointer) is not None)


def _provider_record(obj, sid, pointer, source, cutoff, root):
    """Canonical same-record declarations, never a parser of surrounding prose."""
    from analyst_evidence import number
    from news_analysis import evidence
    require(set(obj) <= set(PROVIDER_FIELDS) | {'source'}, 'UNSUPPORTED_PROVIDER_ROLE')
    values = {k: obj[k] for k in PROVIDER_FIELDS if k in obj}
    bindings = {k: {'source_ref': {'source_id': sid, 'pointer': pointer + '/' + k},
                    'role': k, 'transform': 'IDENTITY'} for k in values}
    if 'source' in obj:
        require(isinstance(obj['source'], dict), 'SOURCE_METADATA_OBJECT_REQUIRED')
        for key in SOURCE_METADATA:
            if key not in obj['source']:
                continue
            value = obj['source'][key]
            if key in values:
                require(type(value) is type(values[key]) and value == values[key],
                        'CONFLICTING_SOURCE_METADATA:' + key)
            else:
                values[key] = value
                bindings[key] = {'source_ref': {'source_id': sid, 'pointer': pointer + '/source/' + key},
                                 'role': key, 'transform': 'IDENTITY'}
    for key in ('provider', 'as_of') + DIMENSIONS + SOURCE_METADATA:
        require(isinstance(values.get(key), str) and bool(values[key].strip()), 'PROVIDER_UNKNOWN:' + key)
    require(any(values.get(k) is not None for k in PROVIDER_STATISTICS), 'PROVIDER_STATISTIC_REQUIRED')
    require(any(values.get(k) is not None for k in PROVIDER_COUNTS), 'PROVIDER_COUNT_REQUIRED')
    for key in PROVIDER_STATISTICS:
        if key in values:
            number(values[key], True)
    for key in PROVIDER_COUNTS:
        if key in values:
            require(type(values[key]) is int and values[key] > 0, 'POSITIVE_INTEGER_PROVIDER_COUNT_REQUIRED')
    if 'upstream' in values:
        require(isinstance(values['upstream'], str) and bool(values['upstream'].strip()), 'PROVIDER_UPSTREAM_INVALID')
    if 'firm_population' in values:
        population = values['firm_population']
        require(isinstance(population, list) and bool(population) and
                all(isinstance(v, str) and bool(v.strip()) for v in population) and
                len(set(population)) == len(population), 'PROVIDER_POPULATION_INVALID')
        bindings['firm_population']['members'] = [
            {'source_id': sid, 'pointer': pointer + '/firm_population/' + str(i)}
            for i in range(len(population))]
        # A firm list is a declared population, not a derivation of analyst/target
        # counts or individual targets. Those counts need not equal firm count.
    ref = {'source_id': sid, 'pointer': pointer}
    retained_source = {'path': source['path'], 'sha256': source['sha256'],
                       **{key: values[key] for key in SOURCE_METADATA},
                       'verbatim_excerpt': source['text'], 'locator': json.dumps(ref, sort_keys=True)}
    evidence(retained_source, root, cutoff)
    snapshot = values['as_of']
    published = stamp(values['published_at'])
    if re.fullmatch(r'\d{4}-\d{2}-\d{2}', snapshot):
        day = date.fromisoformat(snapshot)
        require(day <= cutoff.date() and day <= published.date(), 'PROVIDER_SNAPSHOT_AFTER_AVAILABILITY')
        precision = 'DATE_ONLY_NO_INTRADAY_TIME_INFERRED'
    else:
        moment = stamp(snapshot)
        require(moment <= cutoff and moment <= published, 'PROVIDER_SNAPSHOT_AFTER_AVAILABILITY')
        precision = 'TIMESTAMP'
    return {**values, 'record_id': digest(encoded(ref)), 'source_ref': ref,
            'bindings': bindings, 'source': retained_source, 'snapshot_precision': precision,
            'source_authenticity_verified': False,
            'constituent_issue_dates': 'UNKNOWN_NOT_DERIVED_FROM_AGGREGATE_SNAPSHOT'}


def _providers(corpus, formats, cutoff, request):
    from analyst_evidence import review
    rows, gaps = [], []
    for sid, source in sorted(corpus.sources.items()):
        if source['format'] != 'json':
            continue
        for pointer, obj in _objects(source['document']):
            if 'provider_consensus' in obj:
                collection = obj['provider_consensus']
                if not isinstance(collection, list) or any(not isinstance(v, dict) for v in collection):
                    gaps.append({'source_ref': {'source_id': sid, 'pointer': pointer + '/provider_consensus'},
                                 'reason': 'PROVIDER_RECORD_ARRAY_REQUIRED', 'kind': 'UNRESOLVED_PROVIDER_CONSENSUS'})
            if not _provider_candidate(pointer, obj):
                continue
            try:
                require('json_records' in formats, 'UNSUPPORTED_PROVIDER_RECORD')
                row = _provider_record(obj, sid, pointer, source, cutoff, corpus.root)
                # Reuse the direct helper's range/count/source validation. One
                # malformed pool must not erase other retained pools or targets.
                review({'as_of': request['as_of'], **request['cohort'],
                        'provider_consensus': [row]}, corpus.root)
                rows.append(row)
            except (ValueError, TypeError, KeyError, ArithmeticError, OSError) as exc:
                gaps.append({'source_ref': {'source_id': sid, 'pointer': pointer},
                             'reason': str(exc), 'kind': 'UNRESOLVED_PROVIDER_CONSENSUS'})
    return rows, gaps


def _extract(corpus, formats):
    records, unresolved, inventory, unsupported = [], [], [], []
    for sid, source in sorted(corpus.sources.items()):
        count = 0
        before = len(unresolved)
        if source['format'] == 'bytes':
            unsupported.append(sid)
        elif source['format'] == 'json':
            provider_roots = [p for p, obj in _objects(source['document']) if _provider_candidate(p, obj)]
            for pointer in _array_text(source['document']):
                count += 1
                unresolved.append({'source_ref': {'source_id': sid, 'pointer': pointer},
                                   'reason': 'UNSUPPORTED_TARGET_JSON'})
            for pointer, obj in _objects(source['document']):
                if any(pointer == p or pointer.startswith(p + '/') for p in provider_roots):
                    continue
                # Canonical roles bind within this record, with only the
                # documented own-source metadata extension. No inheritance.
                if 'target' not in obj:
                    for key, value in obj.items():
                        if key == 'provider_consensus' and isinstance(value, list):
                            continue
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
                try:
                    values, bindings = _json_roles(obj, sid, pointer)
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
    require(isinstance(request, dict) and 'extraction_profile' in request,
            'SOURCE_FIRST_REQUEST_KEYS_REQUIRED_NO_LITERAL_TARGETS')
    profile = request['extraction_profile']
    require(isinstance(profile, dict) and set(profile) == {'formats'} and
            isinstance(profile['formats'], list) and profile['formats'] and
            len(profile['formats']) == len(set(profile['formats'])) and
            set(profile['formats']) <= {'json_records', 'labelled_records', 'labelled_sentences'}, 'SUPPORTED_PROFILE_REQUIRED')
    corpus = Corpus(manifest_path, expected_manifest_sha256, source_root)
    effective, request_binding = _request_filters(request, corpus)
    cohort = effective['cohort']
    cutoff = stamp(effective['as_of'])
    records, gaps, inventory, unsupported = _extract(corpus, set(profile['formats']))
    providers, provider_gaps = _providers(corpus, set(profile['formats']), cutoff, effective)
    gaps.extend(provider_gaps)
    for item in inventory:
        item['provider_candidate_count'] = sum(row['source_ref']['source_id'] == item['source_id']
            for row in providers + provider_gaps)
        if any(gap['source_ref']['source_id'] == item['source_id'] for gap in provider_gaps):
            item['status'] = 'UNRESOLVED_CANDIDATES'
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
    eligible = review({'as_of': effective['as_of'], **cohort,
                       **{key: effective[key] for key in AGE_DEFAULTS}, 'individual_targets': rows,
                       'provider_consensus': providers}, corpus.root)
    incomplete = bool(gaps or unsupported or latest['unresolved_record_ids'])
    coverage = {'status': 'INCOMPLETE' if incomplete else 'SUPPORTED_GRAMMARS_SCANNED',
                'all_source_ids': sorted(corpus.sources), 'unresolved_candidates': gaps,
                'unsupported_sources': unsupported, 'semantic_completeness_verified': False,
                'source_absence_established': False}
    result = {'schema_version': 1, 'method': METHOD, 'manifest_sha256': expected_manifest_sha256,
              'request_sha256': digest(encoded(request)), 'request_binding': request_binding,
              'implementation_sha256': digest(Path(__file__).read_bytes()),
              'source_inventory': inventory, 'records': records, 'coverage': coverage,
              'observed_latest': latest, 'eligible_cohort': {'status': 'HELPER_FILTERED_OBSERVED_ROWS',
                  'result': eligible, 'excluded': excluded}, 'source_authenticity_verified': False,
              'execution_authorized': False,
              'limits': ['Only the documented bounded grammars are supported; no whole-corpus semantic completeness.',
                         'Cohort filter values never fill missing source metadata.',
                         'Older eligible rows and latest observed issues are separate populations.',
                         'Provider pools remain separate declarations, never inferred constituent targets or averaged provider means.',
                         'A provider snapshot does not date individual recommendations; unspecified issue dates remain unknown.']}
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
              'Original request binding: ' + json.dumps(request_binding, sort_keys=True),
              'Cohort dimensions: ' + json.dumps(cohort, sort_keys=True),
              'Separate provider-reported pools (not combined; each comparability flag is dimension equality only): ' +
                  json.dumps(eligible['provider_consensus'], sort_keys=True),
              'Population-specific declared lineage (statistical independence unestablished): ' +
                  json.dumps(eligible['source_population_provenance'], sort_keys=True),
              'Provider snapshot dates do not establish constituent issue dates. Unknown dates remain unknown; provider means are never averaged.',
              'Unresolved provider candidates: ' + json.dumps(provider_gaps, sort_keys=True),
              'Eligible record IDs: ' + json.dumps([r['record_id'] for r in eligible['individual_targets_used']]),
              'Exclusions: ' + json.dumps(excluded + eligible['excluded'], sort_keys=True),
              'Unsupported candidates: ' + str(len(gaps)) + '; unsupported sources: ' + json.dumps(unsupported),
              'This report certifies neither arbitrary prose nor an investment conclusion.']
    text = '\n'.join(lines) + '\n'
    result['report'] = {'text': text, 'sha256': digest(text.encode('utf-8')), 'whole_report_semantic_pass': False}
    return result
