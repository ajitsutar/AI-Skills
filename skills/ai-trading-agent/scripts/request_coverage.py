"""Retain original request scope and assemble an explicitly authored briefing.

Category presence and byte identity are checked, not analytical correctness.
Optional strict report annexes keep their own replay scope. No network or account
operation, financial calculation, source search or prose grading occurs here.
"""
from copy import deepcopy
import argparse
import hashlib
import json
from pathlib import Path
import re

import final_report
import supplied_research as source
from source_claims import Corpus
from source_lineage import at, parse

METHOD = 'request-coverage-delivery-1'
MAX_ROWS = 32
MAX_TEXT = 32768
LIMITS = [
    'Requested category presence is structural coverage, not complete or correct analysis.',
    'Authored interpretations, source plans, access assessments and gap statements are semantically UNVERIFIED.',
    'Original source excerpts are attributed declarations, not authenticated facts or verified conclusions.',
    'Prospective routes are NOT_EXECUTED; no search, purchase, credential request or account action occurs.',
    'Optional checked annexes verify only their own supported contracts, not this authored briefing.',
]


def fields(value, required, optional=()):
    source.require(isinstance(value, dict) and set(required) <= set(value)
                   and set(value) <= set(required) | set(optional), 'DELIVERY_FIELDS_REQUIRED')


def text(value):
    source.require(isinstance(value, str) and bool(value.strip()) and len(value.encode('utf8')) <= MAX_TEXT,
                   'BOUNDED_NONEMPTY_AUTHORED_TEXT_REQUIRED')


def token(value):
    source.require(isinstance(value, str) and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,79}', value),
                   'BOUNDED_ARTIFACT_ID_REQUIRED')


def bound(corpus, ref):
    fields(ref, ('source_id', 'pointer'))
    source.require(isinstance(ref['source_id'], str) and ref['source_id'] in corpus.sources,
                   'REFERENCE_OUTSIDE_ORIGINAL_CORPUS')
    entry = corpus.sources[ref['source_id']]
    source.require(entry['format'] == 'json', 'JSON_ORIGINAL_REQUIRED')
    value = at(json.loads(entry['raw']), ref['pointer'])
    return {'source_ref': deepcopy(ref), 'source_sha256': entry['sha256'],
            'original_value': deepcopy(value), 'status': 'ATTRIBUTED_ORIGINAL_NOT_AUTHENTICATED'}


def validate_plan(plan):
    fields(plan, ('request_ref', 'categories_pointer', 'source_scope_pointer', 'constraints_pointer', 'rows'), ('annexes',))
    # This bounded schema recognizes the complete original category inventory,
    # not an arbitrary array or a literal subset supplied by the answer author.
    source.require(plan['categories_pointer'] == '/requested_categories', 'ORIGINAL_COMPLETE_CATEGORY_INVENTORY_REQUIRED')
    for key in ('source_scope_pointer', 'constraints_pointer'):
        source.require(isinstance(plan[key], str) and plan[key].startswith('/'), 'ORIGINAL_CONSTRAINT_POINTER_REQUIRED')
    source.require(isinstance(plan['rows'], list) and len(plan['rows']) <= MAX_ROWS, 'BOUNDED_CATEGORY_ROWS_REQUIRED')
    annexes = plan.get('annexes', [])
    source.require(isinstance(annexes, list) and len(annexes) <= 8, 'BOUNDED_ANNEX_LIST_REQUIRED')
    seen = set()
    for annex in annexes:
        fields(annex, ('id', 'kind', 'directory', 'receipt_sha256', 'first_response_sha256'), ('response_sha256',))
        token(annex['id'])
        source.require(annex['id'] not in seen, 'DUPLICATE_ANNEX_ID'); seen.add(annex['id'])
        source.require(annex['kind'] in ('final_report', 'canonical_response'), 'SUPPORTED_CHECKED_ANNEX_REQUIRED')
        source.relative(annex['directory'])
        source.require(('response_sha256' in annex) == (annex['kind'] == 'canonical_response'), 'ANNEX_RESPONSE_PIN_REQUIRED')
        for key in ('receipt_sha256', 'first_response_sha256', 'response_sha256'):
            if key in annex:
                source.require(isinstance(annex[key], str) and re.fullmatch('[0-9a-f]{64}', annex[key]), 'ANNEX_SHA256_REQUIRED')
    return plan


def annex_check(annex, directory):
    directory = source.safe(directory)
    receipt = source.read(directory / 'receipt.json')
    source.require(source.digest(receipt) == annex['receipt_sha256'], 'ANNEX_RECEIPT_HASH_MISMATCH')
    if annex['kind'] == 'canonical_response':
        final_report.verify_response(directory)
        response = source.read(directory / 'response.json')
        source.require(source.digest(response) == annex['response_sha256'], 'ANNEX_RESPONSE_HASH_MISMATCH')
        response_name = 'report/first-response.md'
    else:
        final_report.verify(directory, expected_output_contract=final_report.STRICT)
        response_name = 'first-response.md'
    source.require(source.digest(source.read(directory / response_name)) == annex['first_response_sha256'],
                   'ANNEX_FIRST_RESPONSE_HASH_MISMATCH')
    return {'id': annex['id'], 'kind': annex['kind'], 'status': 'ANNEX_CONTRACT_REPLAYED_ONLY',
            'receipt_sha256': annex['receipt_sha256'], 'first_response_sha256': annex['first_response_sha256'],
            'readable_path': 'annexes/' + annex['id'] + '/' + response_name,
            **({'response_sha256': annex['response_sha256'], 'response_path': 'annexes/' + annex['id'] + '/response.json'}
               if annex['kind'] == 'canonical_response' else {}),
            'complete_briefing_verified': False}


def assemble(plan, corpus, annex_root):
    request = bound(corpus, plan['request_ref'])
    original = request['original_value']
    source.require(isinstance(original, dict), 'WHOLE_ORIGINAL_REQUEST_REQUIRED')
    # Do not redirect recognized original constraint fields to a convenient
    # unrelated string/object. Other source schemas remain explicitly selected
    # declarations and the entire original request is retained for review.
    if 'source_scope' in original:
        source.require(plan['source_scope_pointer'] == '/source_scope', 'ORIGINAL_SOURCE_SCOPE_REQUIRED')
    if 'session_rules' in original:
        source.require(plan['constraints_pointer'] == '/session_rules', 'ORIGINAL_SESSION_RULES_REQUIRED')
    categories = at(original, plan['categories_pointer'])
    source.require(isinstance(categories, list) and 0 < len(categories) <= MAX_ROWS
                   and all(isinstance(c, str) and c.strip() for c in categories)
                   and len(set(categories)) == len(categories), 'UNIQUE_ORIGINAL_CATEGORIES_REQUIRED')
    scope = at(original, plan['source_scope_pointer'])
    constraints = at(original, plan['constraints_pointer'])
    text(scope)
    source.require(isinstance(constraints, dict) and bool(constraints), 'ORIGINAL_CONSTRAINT_OBJECT_REQUIRED')
    annexes = [annex_check(a, annex_root / a['id']) for a in plan.get('annexes', [])]
    annex_ids = {a['id'] for a in annexes}
    rows = {}
    for row in plan['rows']:
        fields(row, ('category', 'observations', 'analysis', 'free_source_plan', 'optional_access', 'remaining_gaps', 'supporting_annex_ids'))
        category = row['category']; text(category)
        source.require(category not in rows, 'DUPLICATE_CATEGORY_ROW: ' + category)
        source.require(category in categories, 'UNREQUESTED_CATEGORY_ROW: ' + category)
        text(row['analysis'])
        source.require(isinstance(row['observations'], list) and len(row['observations']) <= 64, 'BOUNDED_OBSERVATIONS_REQUIRED')
        observations = []
        for observation in row['observations']:
            fields(observation, ('source_ref', 'interpretation'))
            text(observation['interpretation'])
            observations.append({**bound(corpus, observation['source_ref']),
                'authored_interpretation': observation['interpretation'], 'interpretation_status': 'SEMANTICALLY_UNVERIFIED'})
        free = row['free_source_plan']; fields(free, ('routes', 'no_route_reason'))
        source.require(isinstance(free['routes'], list) and len(free['routes']) <= 16, 'BOUNDED_ROUTE_LIST_REQUIRED')
        if free['routes']:
            source.require(free['no_route_reason'] is None, 'ROUTES_OR_NO_ROUTE_REASON_REQUIRED')
        else:
            text(free['no_route_reason'])
        for route in free['routes']:
            fields(route, ('source_kind', 'purpose', 'stopping_condition', 'execution_status'))
            for key in ('source_kind', 'purpose', 'stopping_condition'): text(route[key])
            source.require(route['execution_status'] == 'NOT_EXECUTED', 'PROSPECTIVE_ROUTE_NOT_EXECUTED_REQUIRED')
        optional = row['optional_access']; fields(optional, ('assessment', 'improvement_or_no_need_reason', 'source_refs'))
        text(optional['assessment']); text(optional['improvement_or_no_need_reason'])
        source.require(isinstance(optional['source_refs'], list) and len(optional['source_refs']) <= 32, 'BOUNDED_ACCESS_REFERENCES_REQUIRED')
        access = [bound(corpus, ref) for ref in optional['source_refs']]
        source.require(isinstance(row['remaining_gaps'], list) and len(row['remaining_gaps']) <= 32, 'BOUNDED_GAP_LIST_REQUIRED')
        for gap in row['remaining_gaps']: text(gap)
        ids = row['supporting_annex_ids']
        source.require(isinstance(ids, list) and all(isinstance(i, str) for i in ids)
                       and len(set(ids)) == len(ids) and set(ids) <= annex_ids, 'UNKNOWN_OR_DUPLICATE_SUPPORTING_ANNEX')
        rows[category] = {'category': category, 'observations': observations,
            'authored_analysis': row['analysis'], 'free_source_plan': deepcopy(free),
            'optional_access': {'authored_assessment': optional['assessment'],
                'authored_improvement_or_no_need_reason': optional['improvement_or_no_need_reason'], 'original_access_records': access},
            'authored_remaining_gaps': deepcopy(row['remaining_gaps']), 'supporting_annex_ids': list(ids),
            'authored_content_status': 'SEMANTICALLY_UNVERIFIED'}
    missing = [c for c in categories if c not in rows]
    source.require(not missing, 'INCOMPLETE_REQUEST_SCOPE: ' + json.dumps(missing))
    return {'method': METHOD, 'status': 'REQUESTED_CATEGORY_ROWS_PRESENT',
            'coverage': {'original_categories': categories, 'represented_categories': list(categories),
                'missing_categories': [], 'structural_coverage_only': True, 'semantic_completeness_verified': False},
            'original_request': request,
            'original_source_scope': {'pointer': plan['source_scope_pointer'], 'value': scope},
            'original_constraints': {'pointer': plan['constraints_pointer'], 'value': constraints,
                'meaning': 'Retained declarations; no external action is performed and no permission is inferred.'},
            'rows': [rows[c] for c in categories], 'annexes': annexes, 'limitations': LIMITS,
            'authored_content_status': 'SEMANTICALLY_UNVERIFIED', 'request_correctness_verified': False,
            'execution_authorized': False}


def render(result):
    parts = ['# Requested-category briefing and source plan\n',
             'This is the complete retained set of requested category rows. Presence is structural coverage only; '
             'the authored analysis and plans remain **semantically UNVERIFIED**. Checked annexes retain their separate scope.\n',
             '## Original scope and constraints\n', '```json\n' + source.encode({
                 'scope': result['original_source_scope'], 'constraints': result['original_constraints']}).decode().rstrip() + '\n```\n']
    for index, row in enumerate(result['rows'], 1):
        # JSON quoting prevents author/source Markdown from changing section or
        # certification labels. These fields are displayed, never executed.
        parts.extend(['## Requested category ' + str(index) + '\n',
                      '```json\n' + source.encode(row).decode().rstrip() + '\n```\n'])
    if result['annexes']:
        parts.append('## Separately checked annexes\n')
        for annex in result['annexes']:
            parts.append('- [' + annex['id'] + '](' + annex['readable_path'] + ') — annex contract only; not certification of this briefing.\n')
    parts.extend(['## Verification limits\n', *['- ' + line + '\n' for line in LIMITS]])
    return ('\n'.join(parts).rstrip() + '\n').encode('utf8')


def replay(directory):
    directory = source.safe(directory)
    context = parse(source.read(directory / 'context.json'))
    source.require(context['method'] == METHOD and context['implementation_sha256'] == source.implementations(), 'DELIVERY_IMPLEMENTATION_CHANGED')
    source.require(context['version_sha256'] == source.digest(source.read(source.ROOT / 'VERSION')), 'DELIVERY_VERSION_CHANGED')
    raw = source.read(directory / 'original-plan.json')
    source.require(source.digest(raw) == context['plan_sha256'], 'DELIVERY_PLAN_CHANGED')
    metadata_raw = source.read(directory / 'original-metadata.json')
    source.require(source.digest(metadata_raw) == context['metadata_sha256'], 'DELIVERY_METADATA_CHANGED')
    metadata = final_report.response_metadata(metadata_raw)
    plan = validate_plan(parse(raw))
    corpus = Corpus(directory / 'ingress.json', context['manifest_sha256'], directory / 'originals')
    result = assemble(plan, corpus, directory / 'annexes')
    first = render(result)
    response = source.encode({**result, 'case_id': metadata['case_id'],
                              'candidate_version': source.read(source.ROOT / 'VERSION').decode('utf8').strip(),
                              'input_hashes': {entry['path']: entry['sha256'] for entry in corpus.sources.values()},
                              'runtime_model_metadata': metadata['runtime_model_metadata'],
                              'evidence_paths': metadata.get('evidence_paths', []),
                              'execution_limitations': metadata.get('execution_limitations', []),
                              'metadata_status': 'PARTICIPANT_DECLARATIONS_NOT_VERIFIED',
                              'first_response_sha256': source.digest(first),
                              'artifact_association_method': METHOD})
    return first, response, context


def compose(plan_path, output_dir, manifest_path, expected_manifest_sha256, source_root=None, metadata_path=None):
    output = source.safe(output_dir); output.mkdir(parents=True, exist_ok=False)
    try:
        raw = source.read(plan_path); source.write(output, 'original-plan.json', raw)
        plan = validate_plan(parse(raw))
        metadata_raw = source.read(metadata_path) if metadata_path is not None else source.encode({
            'case_id': 'unspecified', 'runtime_model_metadata': {'model': 'unknown', 'effort': 'unknown'}})
        final_report.response_metadata(metadata_raw)
        source.write(output, 'original-metadata.json', metadata_raw)
        corpus = Corpus(manifest_path, expected_manifest_sha256, source_root)
        manifest_raw = source.read(manifest_path)
        source.require(source.digest(manifest_raw) == expected_manifest_sha256, 'MANIFEST_CHANGED_DURING_DELIVERY')
        source.write(output, 'ingress.json', manifest_raw)
        total = 0
        for entry in corpus.sources.values():
            total += len(entry['raw']); source.require(total <= source.MAX_TOTAL, 'DELIVERY_INPUTS_TOO_LARGE')
            source.write(output, 'originals/' + source.relative(entry['path']), entry['raw'])
        base = source.safe(plan_path).parent
        for annex in plan.get('annexes', []):
            original = source.safe(base / source.relative(annex['directory']))
            source.require(original.is_relative_to(base), 'ANNEX_OUTSIDE_PLAN_DIRECTORY')
            annex_check(annex, original)
            inventory = source.file_inventory(original) | {'receipt.json': source.digest(source.read(original / 'receipt.json'))}
            for name, sha in inventory.items():
                data = source.read(original / source.relative(name))
                source.require(source.digest(data) == sha, 'ANNEX_CHANGED_DURING_COPY')
                total += len(data); source.require(total <= source.MAX_TOTAL, 'DELIVERY_INPUTS_TOO_LARGE')
                source.write(output, 'annexes/' + annex['id'] + '/' + name, data)
            annex_check(annex, output / 'annexes' / annex['id'])
        context = {'method': METHOD, 'manifest_sha256': expected_manifest_sha256,
                   'plan_sha256': source.digest(raw), 'implementation_sha256': source.implementations(),
                   'metadata_sha256': source.digest(metadata_raw),
                   'version_sha256': source.digest(source.read(source.ROOT / 'VERSION'))}
        source.write(output, 'context.json', source.encode(context))
        first, response, _ = replay(output)
        source.require(len(first) <= source.MAX_FILE and len(response) <= source.MAX_FILE, 'DELIVERY_TOO_LARGE')
        source.write(output, 'first-response.md', first); source.write(output, 'response.json', response)
        receipt = {'method': METHOD, 'status': 'STRUCTURAL_SCOPE_AND_BYTES_CHECKED',
                   'first_response_sha256': source.digest(first), 'response_sha256': source.digest(response),
                   'manifest_sha256': expected_manifest_sha256, 'authored_content_status': 'SEMANTICALLY_UNVERIFIED',
                   'semantic_completeness_verified': False, 'request_correctness_verified': False,
                   'artifacts': source.file_inventory(output)}
        source.write(output, 'receipt.json', source.encode(receipt))
        return verify(output)
    except Exception as error:
        source.write(output, 'failure.json', source.encode({'method': METHOD, 'status': 'INCOMPLETE_OR_INVALID_DELIVERY',
            'error_type': type(error).__name__, 'error': str(error), 'semantic_completeness_verified': False}))
        raise


def verify(directory, published_first_response=None, published_response=None):
    directory = source.safe(directory)
    receipt = parse(source.read(directory / 'receipt.json'))
    source.require(receipt.get('method') == METHOD and receipt.get('status') == 'STRUCTURAL_SCOPE_AND_BYTES_CHECKED'
                   and receipt.get('semantic_completeness_verified') is False
                   and receipt.get('request_correctness_verified') is False
                   and receipt.get('authored_content_status') == 'SEMANTICALLY_UNVERIFIED', 'DELIVERY_RECEIPT_REQUIRED')
    source.require(receipt['artifacts'] == source.file_inventory(directory), 'DELIVERY_ARTIFACTS_CHANGED')
    first, response, context = replay(directory)
    source.require(source.read(directory / 'first-response.md') == first
                   and source.read(directory / 'response.json') == response, 'DELIVERY_REPLAY_MISMATCH')
    source.require(receipt['first_response_sha256'] == source.digest(first)
                   and receipt['response_sha256'] == source.digest(response)
                   and receipt['manifest_sha256'] == context['manifest_sha256'], 'DELIVERY_RECEIPT_HASH_MISMATCH')
    if published_first_response is not None:
        source.require(source.read(published_first_response) == first, 'PUBLISHED_BRIEFING_DIFFERS')
    if published_response is not None:
        source.require(source.read(published_response) == response, 'PUBLISHED_DELIVERY_RESPONSE_DIFFERS')
    return dict(receipt)


def main():
    parser = argparse.ArgumentParser(description=__doc__); sub = parser.add_subparsers(dest='mode', required=True)
    p = sub.add_parser('compose'); p.add_argument('plan'); p.add_argument('--output', required=True)
    p.add_argument('--manifest', required=True); p.add_argument('--manifest-sha256', required=True); p.add_argument('--source-root')
    p.add_argument('--metadata', help='Optional declared case/model/evidence metadata; no analytical overrides.')
    p = sub.add_parser('verify'); p.add_argument('directory'); p.add_argument('--first-response'); p.add_argument('--response')
    args = parser.parse_args()
    try:
        result = compose(args.plan, args.output, args.manifest, args.manifest_sha256, args.source_root, args.metadata) if args.mode == 'compose' else verify(args.directory, args.first_response, args.response)
        print(source.encode(result).decode()); return 0
    except (ValueError, KeyError, TypeError, OSError) as error:
        print(json.dumps({'status': 'INCOMPLETE_OR_INVALID_DELIVERY', 'error': str(error)})); return 1


if __name__ == '__main__':
    raise SystemExit(main())
