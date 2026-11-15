"""Source-bound news clocks, bounded range arithmetic and saved-output claim checks.

These checks establish retained-byte/field relationships, not source authenticity.
No acquisition, broker action, timestamp substitution or semantic inference occurs.
"""
import argparse
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation, localcontext
import hashlib
import json
from pathlib import Path, PureWindowsPath
import re
import stat

METHOD = 'news-source-evidence-1.1.0'
CLOCK_FIELDS = {
    'publication': {'published_at', 'publication_time'},
    'observation': {'observed_at', 'first_observed_at', 'first_seen_at'},
}
CLOCK_LABELS = {
    'publication': {'Published', 'Publication time'},
    'observation': {'Observed', 'First observed', 'First seen'},
}
DIMENSIONS = ('issuer', 'metric', 'period', 'currency', 'unit')


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('DUPLICATE_JSON_KEY:' + key)
        result[key] = value
    return result


def decode(raw, exact_numbers=False):
    return json.loads(raw.decode('utf-8-sig'), object_pairs_hook=_object,
                      parse_float=Decimal if exact_numbers else float,
                      parse_constant=lambda s: (_ for _ in ()).throw(ValueError('NONFINITE_JSON')))


def pointer(document, path):
    """Strict RFC6901 lookup; no fuzzy keys or expression evaluation."""
    if not isinstance(path, str) or (path and not path.startswith('/')):
        raise ValueError('JSON_POINTER_REQUIRED')
    value = document
    for token in path.split('/')[1:] if path else []:
        if re.search(r'~(?![01])', token):
            raise ValueError('INVALID_POINTER_ESCAPE')
        key = token.replace('~1', '/').replace('~0', '~')
        if isinstance(value, list):
            if not re.fullmatch(r'0|[1-9][0-9]*', key):
                raise ValueError('INVALID_ARRAY_INDEX')
            value = value[int(key)]
        elif isinstance(value, dict):
            value = value[key]
        else:
            raise ValueError('POINTER_NOT_CONTAINER')
    return value


def read_source(root, reference):
    base = Path(root).resolve(strict=True)
    rel = reference['path']
    if (not isinstance(rel, str) or not rel or Path(rel).is_absolute()
            or PureWindowsPath(rel).drive or '\\' in rel or ':' in rel
            or any(p in ('..', '.') for p in rel.split('/'))):
        raise ValueError('UNSAFE_SOURCE_PATH')
    path = base / rel
    for part in [path, *path.parents]:
        if part == base:
            break
        attrs = getattr(part.lstat(), 'st_file_attributes', 0)
        if part.is_symlink() or attrs & getattr(stat, 'FILE_ATTRIBUTE_REPARSE_POINT', 1024):
            raise ValueError('LINKED_SOURCE_PATH')
    path = path.resolve(strict=True)
    if not path.is_relative_to(base) or not path.is_file():
        raise ValueError('UNSAFE_SOURCE_PATH')
    raw = path.read_bytes()
    if digest(raw) != reference['sha256']:
        raise ValueError('SOURCE_HASH_MISMATCH')
    return raw


def selected(raw, selection):
    document = raw if isinstance(raw, (dict, list)) else None
    if 'pointer' in selection:
        value = pointer(document if document is not None else decode(raw, exact_numbers=True), selection['pointer'])
    else:
        if not isinstance(raw, bytes):
            raise ValueError('SCOPED_JSON_POINTER_REQUIRED')
        value = raw.decode('utf-8-sig')
    if 'span' in selection:
        span = selection['span']
        if (not isinstance(value, str) or not isinstance(span, list) or len(span) != 2
                or any(type(x) is not int for x in span) or not 0 <= span[0] < span[1] <= len(value)):
            raise ValueError('INVALID_TEXT_SPAN')
        value = value[span[0]:span[1]]
    return value


def timestamp(value):
    if not isinstance(value, str) or not re.match(r'^\d{4}-\d{2}-\d{2}T', value):
        raise ValueError('FULL_TIMESTAMP_REQUIRED')
    result = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if result.tzinfo is None or result.utcoffset() is None:
        raise ValueError('TIMEZONE_REQUIRED')
    return result.astimezone(timezone.utc)


def same(a, b):
    """JSON value equality with exact decimal numerics and distinct booleans."""
    numeric = (int, float, Decimal)
    if isinstance(a, numeric) and isinstance(b, numeric) and type(a) is not bool and type(b) is not bool:
        return Decimal(str(a)) == Decimal(str(b))
    if type(a) is not type(b):
        return False
    if isinstance(a, dict):
        return set(a) == set(b) and all(same(a[k], b[k]) for k in a)
    if isinstance(a, list):
        return len(a) == len(b) and all(same(x, y) for x, y in zip(a, b))
    return a == b


def clock(raw, spec, role):
    """A source observation field cannot stand in for a publication field."""
    kind = spec.get('kind')
    if kind == 'unknown':
        if spec.get('value') is not None:
            raise ValueError('UNKNOWN_CLOCK_WITH_VALUE')
        return {'kind': kind, 'value': None, 'role': role}
    if kind == 'assumption':
        if not isinstance(spec.get('reason'), str) or not spec['reason'].strip():
            raise ValueError('ASSUMPTION_REASON_REQUIRED')
        timestamp(spec['value'])
        return {'kind': kind, 'value': spec['value'], 'role': role, 'reason': spec['reason']}
    if kind != 'source':
        raise ValueError('CLOCK_KIND_REQUIRED')
    if 'pointer' in spec:
        key = spec['pointer'].rsplit('/', 1)[-1]
        if key not in CLOCK_FIELDS[role] or 'span' in spec:
            raise ValueError('CLOCK_ROLE_BINDING_MISMATCH')
        value = selected(raw, spec)
    else:
        label = spec.get('label')
        if label not in CLOCK_LABELS[role] or not isinstance(raw, bytes):
            raise ValueError('CLOCK_ROLE_BINDING_MISMATCH')
        matches = re.findall(r'^' + re.escape(label) + r':[ \t]*([^\r\n]+)\r?$', raw.decode('utf-8-sig'), re.M)
        if len(matches) != 1:
            raise ValueError('CLOCK_LABEL_MISSING_OR_AMBIGUOUS')
        value = matches[0].strip()
    timestamp(value)
    if 'value' in spec and spec['value'] != value:
        raise ValueError('CLOCK_VALUE_DIFFERS_FROM_SOURCE')
    return {'kind': 'source', 'role': role, 'value': value,
            'binding': {k: spec[k] for k in ('pointer', 'label') if k in spec}}


def field(raw, spec):
    kind = spec.get('kind')
    if kind == 'unknown':
        if spec.get('value') is not None:
            raise ValueError('UNKNOWN_FIELD_WITH_VALUE')
        return {'kind': kind, 'value': None}
    if kind == 'declared':
        if not isinstance(spec.get('reason'), str) or not spec['reason'].strip():
            raise ValueError('DECLARED_FIELD_REASON_REQUIRED')
        return {'kind': kind, 'value': spec['value'], 'reason': spec['reason']}
    if kind != 'source' or not any(k in spec for k in ('pointer', 'span')):
        raise ValueError('SOURCE_FIELD_BINDING_REQUIRED')
    value = selected(raw, spec)
    if isinstance(value, (dict, list)) or value is None or type(value) is bool:
        raise ValueError('SCALAR_SOURCE_FIELD_REQUIRED')
    if 'value' in spec and not same(spec['value'], value):
        raise ValueError('FIELD_VALUE_DIFFERS_FROM_SOURCE')
    return {'kind': kind, 'value': str(value) if isinstance(value, Decimal) else value,
            'binding': {k: spec[k] for k in ('pointer', 'span') if k in spec}}


def basis(raw, spec, metric):
    if spec.get('kind') != 'source_phrase':
        result = field(raw, spec)
        if result['kind'] == 'source':
            path = spec.get('pointer', '')
            if path.rsplit('/', 1)[-1] != 'accounting_basis' or 'span' in spec:
                raise ValueError('BASIS_FIELD_OR_SCOPED_PHRASE_REQUIRED')
            # Structured basis must be attached to this same metric object.
            parent = pointer(raw if isinstance(raw, dict) else decode(raw, exact_numbers=True), path.rsplit('/', 1)[0])
            if parent.get('metric') != metric:
                raise ValueError('BASIS_METRIC_SCOPE_MISMATCH')
        return result
    quote = selected(raw, spec)
    value = spec.get('value')
    if not isinstance(value, str) or not value.strip() or not isinstance(quote, str):
        raise ValueError('BASIS_PHRASE_REQUIRED')
    # Deliberately narrow lexical associations; other prose stays unknown/declared.
    m, b = re.escape(metric), re.escape(value)
    adjacent = re.search(r'(?<![\w\-‐‑‒–—−])' + b + r'\s+' + m + r'(?!\w)', quote, re.I)
    suffix = re.search(r'(?<!\w)' + m + r'(?:\s+guidance)?(?:\s+is)?\s+(?:[A-Z]{3}\s+)?'
                       r'[\d.,\s–-]+(?:to\s+[\d.,\s]+)?(?:million|billion|percent|%)?'
                       r'\s+on\s+(?:a\s+)?' + b + r'\s+basis\b', quote, re.I)
    if not adjacent and not suffix:
        raise ValueError('BASIS_PHRASE_DOES_NOT_BIND_METRIC')
    match = adjacent or suffix
    # Inspect original surrounding text as well: a clipped excerpt cannot remove
    # the "non-" or negation that changes a basis association.
    container = selected(raw, {'pointer': spec['pointer']} if 'pointer' in spec else {})
    start = spec.get('span', [0, len(container)])[0] + match.start()
    end = spec.get('span', [0, len(container)])[0] + match.end()
    if start and re.match(r'[\w\-‐‑‒–—−]', container[start-1]):
        raise ValueError('BASIS_PHRASE_AMBIGUOUS_CONTEXT')
    left = max([container.rfind(c, 0, start) for c in '.!?;\r\n']) + 1
    right_candidates = [container.find(c, end) for c in '.!?;\r\n']
    right = min([x for x in right_candidates if x >= 0] or [len(container)])
    # Remove the explicitly claimed compound basis itself; e.g. non-GAAP is a
    # valid literal basis, while GAAP cannot be extracted from non-GAAP.
    association = container[start:end]
    without_basis = re.sub(re.escape(value), '', association, count=1, flags=re.I)
    context = container[left:start] + without_basis + container[end:right]
    if re.search(r'\b(?:not|non|no|neither|without|excluding|except|versus|vs|rather)\b', context, re.I):
        raise ValueError('BASIS_PHRASE_AMBIGUOUS_CONTEXT')
    return {'kind': 'source', 'value': value, 'binding': {k: spec[k] for k in ('pointer', 'span') if k in spec},
            'scope': 'LIMITED_LEXICAL_BASIS_ASSOCIATION', 'excerpt': quote}


def number(value):
    if type(value) is bool:
        raise ValueError('FINITE_NUMBER_REQUIRED')
    try:
        result = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError('FINITE_NUMBER_REQUIRED') from exc
    if not result.is_finite():
        raise ValueError('FINITE_NUMBER_REQUIRED')
    if len(result.as_tuple().digits) > 24 or not -24 <= result.as_tuple().exponent <= 24:
        raise ValueError('NUMERIC_PRECISION_OUTSIDE_SUPPORTED_BOUNDS')
    return result


def scoped_source(item, root):
    raw = read_source(root, item['source'])
    # Scope a structured archive to one original record before resolving fields.
    # JSON strings retain their exact contents, including line endings and offsets.
    if 'record_pointer' in item['source']:
        scoped = pointer(decode(raw, exact_numbers=True), item['source']['record_pointer'])
        if not isinstance(scoped, dict):
            raise ValueError('SOURCE_RECORD_OBJECT_REQUIRED')
        return raw, scoped
    return raw, raw


def dimension(raw, scoped, item, name, spec):
    """Bind an archive issuer header without claiming document subject identity."""
    if spec.get('kind') != 'source_context':
        return field(scoped, spec)
    if name != 'issuer' or 'span' in spec:
        raise ValueError('ARCHIVE_CONTEXT_ONLY_FOR_ISSUER')
    record_path = item['source'].get('record_pointer')
    container_path = spec.get('container_pointer')
    path = spec.get('pointer')
    if (not isinstance(record_path, str) or not record_path.startswith('/') or
            not isinstance(container_path, str) or
            (container_path and not container_path.startswith('/')) or
            not record_path.startswith(container_path + '/') or
            path not in ('/issuer', '/issuer/id', '/issuer/name')):
        raise ValueError('ANCESTOR_ISSUER_CONTEXT_BINDING_REQUIRED')
    container = pointer(decode(raw, exact_numbers=True), container_path)
    if not isinstance(container, dict):
        raise ValueError('ARCHIVE_CONTEXT_OBJECT_REQUIRED')
    value = pointer(container, path)
    if not isinstance(value, str) or not value.strip():
        raise ValueError('ARCHIVE_ISSUER_SCALAR_REQUIRED')
    if 'value' in spec and not same(spec['value'], value):
        raise ValueError('FIELD_VALUE_DIFFERS_FROM_SOURCE')
    return {'kind': 'source_context', 'value': value,
            'binding': {'container_pointer': container_path, 'pointer': path,
                        'record_pointer': record_path},
            'scope': 'ARCHIVE_HEADER_NOT_DOCUMENT_SUBJECT_IDENTITY',
            'semantic_identity_verified': False}


def record(item, root):
    raw, scoped = scoped_source(item, root)
    clocks = {role: clock(scoped, item['clocks'][role], role) for role in CLOCK_FIELDS}
    fields = {name: dimension(raw, scoped, item, name, item['fields'][name])
              for name in (*DIMENSIONS, 'low', 'high')}
    if any(not isinstance(fields[k]['value'], str) or not fields[k]['value'].strip() for k in DIMENSIONS):
        raise ValueError('NAMED_COMPARISON_DIMENSIONS_REQUIRED')
    fields['accounting_basis'] = basis(scoped, item['fields']['accounting_basis'], fields['metric']['value'])
    if any(fields[k]['kind'] != 'source' for k in ('low', 'high')):
        raise ValueError('SOURCE_BOUND_NUMERIC_RANGE_REQUIRED')
    low, high = (number(fields[k]['value']) for k in ('low', 'high'))
    if low > high:
        raise ValueError('REVERSED_RANGE')
    return {'id': item['id'], 'source': item['source'], 'clocks': clocks, 'fields': fields}


def period_evidence(item, row, root):
    """Keep a literal period label separate from optional exact source dates."""
    _, scoped = scoped_source(item, root)
    boundaries = item.get('period_boundaries', {})
    if not isinstance(boundaries, dict) or set(boundaries) - {'start', 'end'}:
        raise ValueError('PERIOD_BOUNDARIES_START_END_ONLY')
    dates = {}
    for name in ('start', 'end'):
        info = field(scoped, boundaries.get(name, {'kind': 'unknown'}))
        if info['kind'] not in ('source', 'unknown'):
            raise ValueError('EXACT_PERIOD_DATES_REQUIRE_SOURCE_BINDINGS')
        if info['kind'] == 'source':
            if not isinstance(info['value'], str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', info['value']):
                raise ValueError('EXACT_PERIOD_DATE_REQUIRED')
            date.fromisoformat(info['value'])
        dates[name] = info
    known = [dates[k]['value'] is not None for k in ('start', 'end')]
    if any(known) and not all(known):
        raise ValueError('EXACT_PERIOD_BOUNDARIES_REQUIRE_BOTH_DATES')
    if all(known) and dates['start']['value'] > dates['end']['value']:
        raise ValueError('REVERSED_PERIOD_BOUNDARIES')
    return {'label': row['fields']['period'], 'start': dates['start'], 'end': dates['end'],
            'scope': 'SOURCE_BOUND_DATES_NOT_LABEL_EQUIVALENCE_PROOF' if all(known)
            else 'LABEL_ONLY_EXACT_CALENDAR_BOUNDARIES_UNKNOWN'}


def withdrawal_evidence(scoped, spec, metric):
    """Recognize only an explicit same-metric status or a bounded whole clause."""
    if spec.get('kind') == 'source':
        path = spec.get('pointer', '')
        if path.rsplit('/', 1)[-1] not in ('status', 'guidance_status') or 'span' in spec:
            raise ValueError('WITHDRAWAL_STATUS_FIELD_REQUIRED')
        parent = pointer(scoped if isinstance(scoped, dict) else decode(scoped, exact_numbers=True),
                         path.rsplit('/', 1)[0])
        info = field(scoped, spec)
        if parent.get('metric') != metric or info['value'] != 'withdrawn':
            raise ValueError('WITHDRAWAL_STATUS_METRIC_MISMATCH')
        return info
    if spec.get('kind') != 'source_phrase':
        raise ValueError('SOURCE_BOUND_WITHDRAWAL_REQUIRED')
    quote = selected(scoped, spec)
    container = selected(scoped, {'pointer': spec['pointer']} if 'pointer' in spec else {})
    if not isinstance(quote, str) or not isinstance(container, str) or not quote.strip():
        raise ValueError('WITHDRAWAL_PHRASE_REQUIRED')
    start, end = spec.get('span', [0, len(container)])
    # Inspect the original full sentence, so clipping cannot hide a condition,
    # negation, attribution or a different metric. Line wrapping and semicolons
    # do not end that context. Complex prose remains rejected.
    left = max(container.rfind(c, 0, start) for c in '.!?') + 1
    content_end = end
    while content_end > start and container[content_end - 1] in '.!?;\r\n \t':
        content_end -= 1
    endings = [container.find(c, content_end) for c in '.!?']
    right = min([x for x in endings if x >= 0] or [len(container)])
    clause = container[left:right].strip().rstrip('.!?;').strip()
    m = re.escape(metric)
    active = r'(?:the company|the issuer|we)\s+(?:(?:has|have)\s+)?(?:withdrew|withdrawn)\s+(?:its\s+|our\s+|the\s+)?' + m + r'\s+(?:guidance|outlook)'
    passive = m + r'\s+(?:guidance|outlook)\s+(?:has been|is)\s+withdrawn'
    if not re.fullmatch('(?:' + active + '|' + passive + ')', clause, re.I):
        raise ValueError('WITHDRAWAL_PHRASE_UNRESOLVED')
    if not re.search(r'\b(?:withdrew|withdrawn)\b', quote, re.I) or not re.search(m, quote, re.I):
        raise ValueError('WITHDRAWAL_SPAN_MISSING_METRIC_OR_ACTION')
    if 'value' in spec and spec['value'] != 'withdrawn':
        raise ValueError('FIELD_VALUE_DIFFERS_FROM_SOURCE')
    return {'kind': 'source', 'value': 'withdrawn', 'excerpt': quote,
            'binding': {k: spec[k] for k in ('pointer', 'span') if k in spec},
            'scope': 'LIMITED_LITERAL_WITHDRAWAL_CLAUSE_NOT_SOURCE_AUTHENTICITY'}


def withdrawal_record(item, root):
    raw, scoped = scoped_source(item, root)
    clocks = {role: clock(scoped, item['clocks'][role], role) for role in CLOCK_FIELDS}
    fields = {name: dimension(raw, scoped, item, name, item['fields'].get(name, {'kind': 'unknown'}))
              for name in DIMENSIONS}
    metric = fields['metric']
    if metric['kind'] != 'source' or not isinstance(metric['value'], str) or not metric['value'].strip():
        raise ValueError('SOURCE_BOUND_WITHDRAWAL_METRIC_REQUIRED')
    for name in DIMENSIONS:
        if fields[name]['value'] is not None and (not isinstance(fields[name]['value'], str) or
                                                not fields[name]['value'].strip()):
            raise ValueError('NAMED_OR_UNKNOWN_WITHDRAWAL_DIMENSION_REQUIRED')
    fields['accounting_basis'] = basis(scoped, item['fields'].get('accounting_basis', {'kind': 'unknown'}), metric['value'])
    for name in ('low', 'high'):
        info = field(scoped, item['fields'].get(name, {'kind': 'unknown'}))
        if info['kind'] != 'unknown':
            raise ValueError('WITHDRAWAL_IS_NOT_A_NUMERIC_GUIDANCE_RANGE')
        fields[name] = info
    status = withdrawal_evidence(scoped, item['withdrawal'], metric['value'])
    return {'id': item['id'], 'source': item['source'], 'clocks': clocks, 'fields': fields,
            'withdrawal': status}


def guidance(request, root):
    """Source-bound ranges and withdrawal statements without manufactured fields."""
    item = request['current']
    status = item.get('status', 'issued')
    if status not in ('issued', 'withdrawn'):
        raise ValueError('GUIDANCE_STATUS_MUST_BE_ISSUED_OR_WITHDRAWN')
    if status == 'issued':
        if request.get('previous') is None:
            raise ValueError('ISSUED_RANGE_COMPARISON_REQUIRES_PREVIOUS')
        if request['previous'].get('status', 'issued') != 'issued':
            raise ValueError('ISSUED_RANGE_COMPARISON_REQUIRES_ISSUED_PREVIOUS')
        result = compare(request, root)
        periods = [period_evidence(request[k], row, root)
                   for k, row in zip(('previous', 'current'), result['records'])]
        known = [p['start']['value'] is not None for p in periods]
        mismatch = all(known) and any(periods[0][k]['value'] != periods[1][k]['value'] for k in ('start', 'end'))
        if mismatch:
            result['mismatched_dimensions'].append('exact_period_boundaries')
            result['arithmetic'] = None
            if result['comparison_status'] != 'EXCLUDED_AT_CUTOFF':
                result['comparison_status'] = 'NOT_COMPARABLE'
        elif any(known) and not all(known):
            result['limitations'].append('EXACT_PERIOD_BOUNDARIES_NOT_MATCHED_BOTH_RECORDS')
            if result['comparison_status'] == 'SOURCE_BOUND_DISCLOSURE_CHANGE':
                result['comparison_status'] = 'ARITHMETIC_ONLY'
        result.update(mode='guidance', guidance_status='issued', period_evidence=periods)
        return result
    cutoff = timestamp(request['as_of'])
    current = withdrawal_record(item, root)
    previous = record(request['previous'], root) if request.get('previous') is not None else None
    if previous is not None and request['previous'].get('status', 'issued') != 'issued':
        raise ValueError('WITHDRAWAL_PRIOR_RANGE_MUST_BE_ISSUED')
    rows = [previous, current] if previous is not None else [current]
    periods = [period_evidence(request['previous'], previous, root)] if previous is not None else []
    periods.append(period_evidence(item, current, root))
    reasons, future = [], False
    for row in rows:
        for role, info in row['clocks'].items():
            if info['kind'] != 'source':
                reasons.append(row['id'] + ':' + role.upper() + '_' + info['kind'].upper())
            elif timestamp(info['value']) > cutoff:
                future = True
                reasons.append(row['id'] + ':' + role.upper() + '_AFTER_CUTOFF')
        pub, obs = (row['clocks'][k] for k in ('publication', 'observation'))
        if pub['kind'] == obs['kind'] == 'source' and timestamp(obs['value']) < timestamp(pub['value']):
            reasons.append(row['id'] + ':OBSERVED_BEFORE_PUBLICATION')
        reasons.extend(row['id'] + ':' + k.upper() + '_' + v['kind'].upper()
                       for k, v in row['fields'].items() if k not in ('low', 'high') and v['kind'] != 'source')
    order = 'NO_PRIOR_RANGE'
    if previous is not None:
        a, b = previous['clocks']['publication'], current['clocks']['publication']
        order = 'UNKNOWN_PUBLICATION_ORDER'
        if a['kind'] == b['kind'] == 'source':
            x, y = timestamp(a['value']), timestamp(b['value'])
            order = 'LATER_DISCLOSURE' if y > x else 'SAME_PUBLICATION' if y == x else 'EARLIER_DISCLOSURE'
        if order != 'LATER_DISCLOSURE':
            reasons.append(order)
    matched = previous is not None and all(
        previous['fields'][k]['value'] is not None and
        previous['fields'][k]['value'] == current['fields'][k]['value'] and
        all(row['fields'][k]['kind'] == 'source' or
            (k == 'issuer' and row['fields'][k]['kind'] == 'source_context')
            for row in (previous, current))
        for k in (*DIMENSIONS, 'accounting_basis'))
    if matched and all(p['start']['value'] is not None for p in periods):
        matched = all(periods[0][k]['value'] == periods[1][k]['value'] for k in ('start', 'end'))
    elif matched and any(p['start']['value'] is not None for p in periods):
        matched = False
        reasons.append('EXACT_PERIOD_BOUNDARIES_NOT_MATCHED_BOTH_RECORDS')
    if previous is not None and not matched:
        reasons.append('PRIOR_RANGE_DIMENSIONS_NOT_MATCHED')
    clock_problem = any('PUBLICATION_' in x or 'OBSERVATION_' in x or 'OBSERVED_BEFORE' in x or
                        x in ('UNKNOWN_PUBLICATION_ORDER', 'SAME_PUBLICATION', 'EARLIER_DISCLOSURE') for x in reasons)
    classification = None if future or clock_problem else 'WITHDRAWN' if matched else 'WITHDRAWAL_PRIOR_RANGE_UNKNOWN'
    return {'method': METHOD, 'mode': 'guidance', 'guidance_status': 'withdrawn', 'as_of': request['as_of'],
            'comparison_status': 'EXCLUDED_AT_CUTOFF' if future else 'WITHDRAWAL_REVIEW_REQUIRED' if clock_problem else 'SOURCE_BOUND_WITHDRAWAL_STATEMENT',
            'classification': classification, 'publication_order': order, 'limitations': sorted(set(reasons)),
            'records': rows, 'period_evidence': periods, 'arithmetic': None,
            'prior_range': {k: previous['fields'][k]['value'] for k in ('low', 'high')} if classification == 'WITHDRAWN' else None,
            'range_change': None, 'midpoint_change': None, 'withdrawal_is_zero_guidance': False,
            'source_authenticity_verified': False, 'semantic_extraction_verified': False, 'execution_authorized': False,
            'input_sha256': digest(json.dumps(request, sort_keys=True, default=str).encode()),
            'implementation_sha256': digest(Path(__file__).read_bytes())}


def compare(request, root):
    cutoff = timestamp(request['as_of'])
    old, new = (record(request[k], root) for k in ('previous', 'current'))
    reasons = []
    future = False
    for row in (old, new):
        for role, info in row['clocks'].items():
            if info['kind'] != 'source':
                reasons.append(row['id'] + ':' + role.upper() + '_' + info['kind'].upper())
            elif timestamp(info['value']) > cutoff:
                future = True
                reasons.append(row['id'] + ':' + role.upper() + '_AFTER_CUTOFF')
        pub, obs = (row['clocks'][k] for k in ('publication', 'observation'))
        if pub['kind'] == obs['kind'] == 'source' and timestamp(obs['value']) < timestamp(pub['value']):
            reasons.append(row['id'] + ':OBSERVED_BEFORE_PUBLICATION')
        reasons.extend(row['id'] + ':' + k.upper() + '_' + v['kind'].upper()
                       for k, v in row['fields'].items() if v['kind'] != 'source')
    publications = [row['clocks']['publication'] for row in (old, new)]
    order = 'UNKNOWN_PUBLICATION_ORDER'
    if all(x['kind'] == 'source' for x in publications):
        a, b = (timestamp(x['value']) for x in publications)
        order = 'LATER_DISCLOSURE' if b > a else 'SAME_PUBLICATION' if b == a else 'EARLIER_DISCLOSURE'
    if order != 'LATER_DISCLOSURE':
        reasons.append(order)
    mismatch = [k for k in DIMENSIONS if old['fields'][k]['value'] != new['fields'][k]['value']]
    ob, nb = (row['fields']['accounting_basis']['value'] for row in (old, new))
    if ob is not None and nb is not None and ob != nb:
        mismatch.append('accounting_basis')
    arithmetic = None
    if not mismatch and not future:
        lo, hi = (number(old['fields'][k]['value']) for k in ('low', 'high'))
        nl, nh = (number(new['fields'][k]['value']) for k in ('low', 'high'))
        with localcontext() as context:
            context.prec = 80
            x, y = nl-lo, nh-hi
            mid, newmid = (lo+hi)/2, (nl+nh)/2
            label = ('UNCHANGED_RANGE' if x == y == 0 else 'RAISED_RANGE' if x >= 0 and y >= 0
                     else 'LOWERED_RANGE' if x <= 0 and y <= 0 else 'MIXED_RANGE_CHANGE')
            arithmetic = {'range_direction': label, 'previous_midpoint': str(mid), 'current_midpoint': str(newmid),
                          'lower_endpoint_change': str(x), 'upper_endpoint_change': str(y),
                          'midpoint_change': str(newmid-mid),
                          'midpoint_change_pct': str((newmid-mid)/mid*100) if mid > 0 else None,
                          'ranges_overlap': max(lo, nl) <= min(hi, nh)}
    status = ('EXCLUDED_AT_CUTOFF' if future else 'NOT_COMPARABLE' if mismatch else
              'ARITHMETIC_ONLY' if reasons else 'SOURCE_BOUND_DISCLOSURE_CHANGE')
    return {'method': METHOD, 'mode': 'compare', 'comparison_status': status,
            'as_of': request['as_of'], 'publication_order': order, 'limitations': sorted(set(reasons)),
            'mismatched_dimensions': mismatch, 'arithmetic': arithmetic,
            'records': [old, new], 'source_authenticity_verified': False,
            'semantic_extraction_verified': False, 'execution_authorized': False,
            'input_sha256': digest(json.dumps(request, sort_keys=True, default=str).encode()),
            'implementation_sha256': digest(Path(__file__).read_bytes())}


def audit_claims(request, root):
    raw = read_source(root, request['output'])
    output = decode(raw, exact_numbers=True)
    if not isinstance(output, dict) or not output.get('method'):
        raise ValueError('SAVED_HELPER_OUTPUT_REQUIRED')
    claims = request['claims']
    if not isinstance(claims, list) or not claims:
        raise ValueError('NONEMPTY_CLAIMS_REQUIRED')
    ids = [c.get('id') for c in claims]
    if any(not isinstance(i, str) or not i.strip() for i in ids) or len(set(ids)) != len(ids):
        raise ValueError('UNIQUE_CLAIM_IDS_REQUIRED')
    rows = []
    for claim in claims:
        try:
            actual = pointer(output, claim['pointer'])
            mode = claim.get('relation', 'equals')
            if mode not in ('equals', 'contains'):
                raise ValueError('CLAIM_RELATION_UNSUPPORTED')
            expected = claim['value']
            supported = same(actual, expected) if mode == 'equals' else (
                isinstance(actual, list) and any(same(x, expected) for x in actual))
            rendered = json.loads(json.dumps(actual, default=str))
            rows.append({'id': claim['id'], 'pointer': claim['pointer'], 'actual': rendered,
                         'actual_json_type': 'number' if type(actual) in (int, float, Decimal) else type(actual).__name__,
                         'claimed': expected, 'supported': supported})
        except (KeyError, IndexError):
            rows.append({'id': claim['id'], 'pointer': claim['pointer'], 'supported': False,
                         'reason': 'OUTPUT_POINTER_ABSENT'})
    return {'method': METHOD, 'mode': 'audit', 'status': 'PASS' if all(x['supported'] for x in rows) else 'CLAIM_MISMATCH',
            'output': request['output'], 'output_method': output['method'], 'claims': rows,
            'scope': 'Exact saved-output attribution only; no prose, source-truth or execution authenticity certification.',
            'input_sha256': digest(json.dumps(request, sort_keys=True, default=str).encode()),
            'implementation_sha256': digest(Path(__file__).read_bytes()), 'execution_authorized': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('compare', 'guidance', 'audit'))
    parser.add_argument('input')
    parser.add_argument('source_root')
    parser.add_argument('output')
    args = parser.parse_args()
    request = decode(Path(args.input).read_bytes(), exact_numbers=True)
    result = {'compare': compare, 'guidance': guidance, 'audit': audit_claims}[args.mode](request, args.source_root)
    with Path(args.output).open('x', encoding='utf-8') as stream:
        json.dump(result, stream, indent=2, allow_nan=False, default=str)
        stream.write('\n')
    print(json.dumps(result, indent=2, allow_nan=False, default=str))


if __name__ == '__main__':
    main()
