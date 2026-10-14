"""Source-bound routing/replay and dimensioned comparison of local rankings.

No network, new scoring formula, investment conclusion or execution permission.
Input profiles identify installed code; they can never name/import executable code.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
from decimal import Decimal, localcontext
import hashlib
import json
from pathlib import Path

from report_facts import digest, pointer, strict_json

ROOT = Path(__file__).resolve().parents[1]
VERSION = 'ranking-alignment-2'
ROUTES = (
    ('public-vqm-discovery', 'public-vqm-discovery-v1.json', 'public_research.py', (1,)),
    ('vqm-fundamental', 'vqm-fundamental-v1.json', 'vqm_research.py', (1, 2)),
)
DIMENSIONS = ('method_profile', 'snapshot', 'horizon', 'preferences',
              'review_decisions', 'classifier_available')
LIMITS = [
    'Hashes bind retained inputs, not source authenticity or correct source selection.',
    'Installed research scores are not calibrated expected returns or per-name buy eligibility.',
    'Structural agreement is not proof of independent acquisition or earlier model execution.',
    'These diagnostics impose no investment or execution prerequisite.',
]


def require(condition, message):
    if not condition:
        raise ValueError(message)


def _source(record):
    require(isinstance(record, dict) and isinstance(record.get('text'), str), 'SOURCE_TEXT_REQUIRED')
    raw = record['text'].encode('utf-8')
    actual = hashlib.sha256(raw).hexdigest()
    require(record.get('sha256') == actual, 'SOURCE_BYTES_HASH_MISMATCH')
    value = strict_json(raw)
    return value, {'bytes_sha256': actual, 'canonical_sha256': digest(value)}


def installed_routes():
    """Return canonical profile identities and portable installed-code fingerprints.

    Supplied source bytes retain their separate exact hash. Local installed text
    fingerprints normalize universal newlines just like the workflow receipt.
    """
    result = []
    for route, profile_file, implementation, schemas in ROUTES:
        raw = (ROOT / 'profiles' / profile_file).read_bytes()
        profile = strict_json(raw)
        require(profile.get('profile_id') == route, 'INSTALLED_PROFILE_ID_MISMATCH')
        result.append({'profile_id': route, 'profile_version': profile['profile_version'],
                       'profile_sha256': digest(profile),
                       'installed_profile_text_sha256': hashlib.sha256(
                           raw.decode('utf-8').replace('\r\n', '\n').replace('\r', '\n').encode('utf-8')).hexdigest(),
                       'installed_text_hash_basis': 'UTF-8 text; CRLF and CR normalized to LF',
                       'snapshot_schemas': list(schemas), 'implementation': implementation,
                       'implementation_sha256': hashlib.sha256(
                           (ROOT / 'scripts' / implementation).read_text(encoding='utf-8').encode('utf-8')).hexdigest()})
    return result


def _base(document, operation):
    require(isinstance(document, dict) and type(document.get('schema_version')) is int
            and document['schema_version'] == 1,
            'ADAPTER_SCHEMA_1_REQUIRED')
    return {'schema_version': 1, 'adapter_version': VERSION, 'operation': operation,
            'input_sha256': digest(document), 'source_authenticity_verified': False,
            'limitations': list(LIMITS)}


def route_ranking(document):
    """Identify the bound available route independently of the requested method.

    document = {schema_version:1, profile:{text,sha256}, snapshot:{...},
                requested:{profile_id,profile_sha256}, selection_count?:int,
                allow_diagnostic_replay?:bool}
    Profile sha256 in requested/snapshot is canonical JSON, not the bytes hash.
    """
    result = _base(document, 'route-ranking')
    profile, source = _source(document['profile'])
    snapshot = document['snapshot']
    requested = document.get('requested', {})
    require(isinstance(profile, dict) and isinstance(snapshot, dict) and isinstance(requested, dict),
            'PROFILE_SNAPSHOT_REQUEST_OBJECTS_REQUIRED')
    require(set(requested) <= {'profile_id', 'profile_sha256'}, 'UNSUPPORTED_REQUESTED_METHOD_FIELD')
    require(type(document.get('allow_diagnostic_replay', False)) is bool, 'DIAGNOSTIC_FLAG_MUST_BE_BOOLEAN')
    routes = installed_routes()
    available = next((r for r in routes if r['profile_sha256'] == source['canonical_sha256']), None)
    findings = []
    if available is None:
        findings.append('SUPPLIED_PROFILE_NOT_INSTALLED')
    if snapshot.get('profile_sha256') != source['canonical_sha256']:
        findings.append('SNAPSHOT_PROFILE_HASH_MISMATCH')
    if available and (type(snapshot.get('schema_version')) is not int or
                      snapshot['schema_version'] not in available['snapshot_schemas']):
        findings.append('SNAPSHOT_SCHEMA_UNSUPPORTED_FOR_PROFILE')
    bound = available if not findings else None
    request_complete = all(isinstance(requested.get(k), str) and requested[k]
                           for k in ('profile_id', 'profile_sha256'))
    method = ('UNKNOWN' if not request_complete or bound is None else
              'SAME' if all(requested[k] == bound[k] for k in ('profile_id', 'profile_sha256')) else 'DIFFERENT')
    if not request_complete:
        findings.append('REQUESTED_METHOD_IDENTITY_INCOMPLETE')
    elif bound and method == 'DIFFERENT':
        findings.append('REQUESTED_METHOD_DIFFERS_FROM_BOUND_SNAPSHOT')
    result.update(requested=deepcopy(requested), requested_method_relation=method,
                  available_diagnostic_route=bound, requested_route=bound if method == 'SAME' else None,
                  profile_binding=source, snapshot_sha256=digest(snapshot),
                  snapshot_schema=snapshot.get('schema_version'), installed_routes=routes,
                  findings=findings, ranking_execution_verified=False)
    return result


def replay_ranking(document):
    """Call the actual bound installed scorer; never substitute another ranking.

    A nonmatching/unknown request yields no result unless the caller explicitly
    sets allow_diagnostic_replay=true. Such output is diagnostic_result only.
    """
    receipt = route_ranking(document)
    receipt.update(operation='replay-ranking', requested_result=None, diagnostic_result=None)
    route = receipt['available_diagnostic_route']
    is_requested = receipt['requested_method_relation'] == 'SAME'
    if route is None or (not is_requested and not document.get('allow_diagnostic_replay', False)):
        receipt['status'] = 'NOT_REPLAYED'
        return receipt
    snapshot = deepcopy(document['snapshot'])
    count = document.get('selection_count')
    require(count is None or (type(count) is int and count > 0), 'SELECTION_COUNT_MUST_BE_POSITIVE_INTEGER')
    if route['profile_id'] == 'public-vqm-discovery':
        require(count is not None, 'PUBLIC_SELECTION_COUNT_REQUIRED')
    try:
        if route['profile_id'] == 'public-vqm-discovery':
            from public_research import calculate
            output = calculate(snapshot, count)
        else:
            from vqm_research import calculate
            output = calculate(snapshot)
    except (ValueError, KeyError, TypeError, ArithmeticError) as exc:
        receipt.update(status='SCORER_INPUT_ERROR', scorer_error={'type': type(exc).__name__, 'message': str(exc)})
        return receipt
    key = 'requested_result' if is_requested else 'diagnostic_result'
    receipt.update(status='REQUESTED_REPLAY_COMPUTED' if is_requested else 'DIAGNOSTIC_REPLAY_COMPUTED',
                   ranking_execution_verified=True, result_sha256=digest(output))
    receipt[key] = output
    # Selection is a projection of the scorer's preserved order, never new weights.
    ordered = output.get('research_candidates')
    if ordered is None:
        ordered = output['discovery_order']
        ordered = ordered if count is None else ordered[:count]
    receipt['selection'] = {'scope': key, 'requested_count': count, 'candidates': deepcopy(ordered)}
    receipt['classifier'] = {'calibrated_classifier_available': output.get('strong_buy_available'),
                             'per_name_buy_eligibility': 'NOT_ASSESSED'}
    return receipt


def _side(side):
    require(isinstance(side, dict) and isinstance(side.get('sources'), dict)
            and isinstance(side.get('bindings'), dict), 'COMPARISON_SOURCES_AND_BINDINGS_REQUIRED')
    sources, provenance = {}, {}
    for name, record in side['sources'].items():
        sources[name], provenance[name] = _source(record)
    values, bindings = {}, {}
    for dimension in (*DIMENSIONS, 'candidates', 'scores'):
        binding = side['bindings'].get(dimension)
        if binding is None:
            values[dimension] = None
            bindings[dimension] = {'status': 'UNBOUND'}
            continue
        require(isinstance(binding, dict) and binding.get('source_id') in sources,
                'UNKNOWN_BINDING_SOURCE:' + dimension)
        path = binding.get('pointer')
        require(isinstance(path, str), 'BINDING_POINTER_REQUIRED:' + dimension)
        try:
            values[dimension] = deepcopy(pointer(sources[binding['source_id']], path))
            bindings[dimension] = {**binding, 'status': 'BOUND', 'value_sha256': digest(values[dimension])}
        except (KeyError, IndexError):
            values[dimension] = None
            bindings[dimension] = {**binding, 'status': 'PATH_ABSENT'}
    return values, {'sources': provenance, 'bindings': bindings}


def _known(value):
    # Empty metadata is no evidence of an affirmative declaration of no preference.
    return value is not None and value != {} and value != [] and value != ''


def _dimension(left, right):
    known = [_known(left), _known(right)]
    return {'status': ('SAME' if digest(left) == digest(right) else 'DIFFERENT') if all(known) else 'UNKNOWN',
            'left_present': known[0], 'right_present': known[1], 'left': left, 'right': right}


def _diff(left, right, path=''):
    if digest(left) == digest(right):
        return []
    records = []
    if isinstance(left, dict) and isinstance(right, dict):
        for key in sorted(set(left) | set(right)):
            child = path + '/' + key.replace('~', '~0').replace('/', '~1')
            if key in left and key in right:
                records.extend(_diff(left[key], right[key], child))
            else:
                records.append({'pointer': child, 'left_present': key in left, 'right_present': key in right,
                                'left': left.get(key), 'right': right.get(key)})
    elif isinstance(left, list) and isinstance(right, list) and len(left) == len(right):
        for index, (a, b) in enumerate(zip(left, right)):
            records.extend(_diff(a, b, path + '/' + str(index)))
    else:
        records.append({'pointer': path, 'left_present': True, 'right_present': True, 'left': left, 'right': right})
    return records


def _identities(candidates, field):
    if candidates is None:
        return None
    require(isinstance(candidates, list), 'CANDIDATES_MUST_BE_ARRAY')
    identities = [r if isinstance(r, str) else r.get(field) if isinstance(r, dict) else None for r in candidates]
    require(all(isinstance(i, str) and i for i in identities), 'CANDIDATE_ID_REQUIRED')
    require(len(set(identities)) == len(identities), 'DUPLICATE_CANDIDATE_ID')
    return identities


def _scores(rows, field):
    if rows is None:
        return None
    require(isinstance(rows, list), 'SCORES_MUST_BE_ARRAY')
    scores = {}
    for row in rows:
        require(isinstance(row, dict) and isinstance(row.get(field), str) and row[field], 'SCORE_ID_REQUIRED')
        require(row[field] not in scores, 'DUPLICATE_SCORE_ID')
        value = row.get('score')
        if value is not None:
            require(isinstance(value, (int, float, str)) and not isinstance(value, bool), 'NUMERIC_SCORE_REQUIRED')
            value = Decimal(str(value))
            require(value.is_finite(), 'FINITE_SCORE_REQUIRED')
        scores[row[field]] = value
    return scores


def compare_rankings(document):
    """Compare explicit left/right source bindings without inferring metadata.

    document = {schema_version:1, identity_field:'symbol'|'issuer_id',
      left/right:{sources:{id:{text,sha256}}, bindings:{dimension:{source_id,pointer}}}}
    Dimensions: method_profile, snapshot, candidates, scores, horizon, preferences,
    review_decisions, classifier_available. Missing bindings/values remain unknown.
    """
    result = _base(document, 'compare-rankings')
    field = document.get('identity_field')
    require(field in {'symbol', 'issuer_id'}, 'EXPLICIT_IDENTITY_FIELD_REQUIRED')
    limit = document.get('max_snapshot_differences', 1000)
    require(type(limit) is int and limit > 0, 'POSITIVE_DIFFERENCE_LIMIT_REQUIRED')
    left, lp = _side(document['left'])
    right, rp = _side(document['right'])
    for side in (left, right):
        require(side['classifier_available'] is None or type(side['classifier_available']) is bool,
                'CLASSIFIER_AVAILABILITY_MUST_BE_BOOLEAN_OR_NULL')
        for name in ('snapshot', 'method_profile'):
            require(side[name] is None or isinstance(side[name], dict), name.upper() + '_OBJECT_REQUIRED')
        p = side['method_profile']
        if _known(p):
            require(all(isinstance(p.get(k), str) and p[k] for k in ('profile_id', 'profile_version')),
                    'METHOD_PROFILE_ID_AND_VERSION_REQUIRED')
    dimensions = {name: _dimension(left[name], right[name]) for name in DIMENSIONS}
    for side, value in (('left', left['snapshot']), ('right', right['snapshot'])):
        dimensions['snapshot'].pop(side)
        dimensions['snapshot'][side + '_sha256'] = digest(value) if _known(value) else None
    snapshot_diff = _diff(left['snapshot'], right['snapshot']) if all(_known(s['snapshot']) for s in (left, right)) else None
    dimensions['snapshot']['differences'] = None if snapshot_diff is None else snapshot_diff[:limit]
    dimensions['snapshot']['difference_count'] = None if snapshot_diff is None else len(snapshot_diff)
    dimensions['snapshot']['differences_truncated'] = snapshot_diff is not None and len(snapshot_diff) > limit
    ids = [_identities(s['candidates'], field) for s in (left, right)]
    candidate = {'status': 'UNKNOWN', 'identity_field': field, 'left': ids[0], 'right': ids[1]}
    if all(i is not None for i in ids):
        common = sorted(set(ids[0]) & set(ids[1]))
        union = set(ids[0]) | set(ids[1])
        positions = [{identity: index + 1 for index, identity in enumerate(order)} for order in ids]
        candidate.update(status='SAME' if ids[0] == ids[1] else 'DIFFERENT', common=common,
                         common_count=len(common), left_count=len(ids[0]), right_count=len(ids[1]),
                         fraction_of_left=len(common) / len(ids[0]) if ids[0] else None,
                         fraction_of_right=len(common) / len(ids[1]) if ids[1] else None,
                         jaccard=len(common) / len(union) if union else None,
                         left_only=sorted(set(ids[0]) - set(ids[1])), right_only=sorted(set(ids[1]) - set(ids[0])),
                         rank_differences=[{'id': i, 'left_rank': positions[0][i], 'right_rank': positions[1][i]}
                                           for i in common if positions[0][i] != positions[1][i]])
    maps = [_scores(s['scores'], field) for s in (left, right)]
    scores = {'status': 'UNKNOWN', 'method_comparability': dimensions['method_profile']['status'],
              'differences': [], 'unresolved_ids': []}
    if all(m is not None for m in maps):
        common = sorted(set(maps[0]) & set(maps[1]))
        unresolved = sorted((set(maps[0]) ^ set(maps[1])) | {i for i in common if any(m[i] is None for m in maps)})
        with localcontext() as context:
            context.prec = 40
            differences = [{'id': i, 'left': str(maps[0][i]), 'right': str(maps[1][i]),
                            'right_minus_left': str(maps[1][i] - maps[0][i])}
                           for i in common if i not in unresolved and maps[0][i] != maps[1][i]]
        scores.update(status='DIFFERENT' if differences else 'UNKNOWN' if unresolved or not common else 'SAME',
                      differences=differences, unresolved_ids=unresolved)
    result.update(dimensions=dimensions, candidates=candidate, scores=scores,
                  per_name_buy_eligibility={'status': 'NOT_ASSESSED',
                    'reason': 'Classifier availability, null forecasts and candidate overlap cannot establish reviewed eligibility.'},
                  provenance={'left': lp, 'right': rp}, ranking_execution_verified=False)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=('route', 'replay', 'compare'))
    parser.add_argument('input', type=Path)
    args = parser.parse_args()
    operation = {'route': route_ranking, 'replay': replay_ranking, 'compare': compare_rankings}[args.operation]
    print(json.dumps(operation(strict_json(args.input.read_bytes())), indent=2, allow_nan=False))


if __name__ == '__main__':
    main()
