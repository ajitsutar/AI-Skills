"""Replayable complete coverage maps using exact original-source quotations.

No free factual paraphrase, currency/period inheritance, arithmetic, source
acquisition or truth certification. Topic relevance/access/lineage stay declared.
"""
from copy import deepcopy
import argparse
import json
from pathlib import Path
import re

import final_report
import supplied_research as store
from source_claims import Corpus
from source_lineage import parse

METHOD = 'exact-source-coverage-1'
ACCESS = {'SUPPLIED_BODY', 'SUPPLIED_EXCERPT', 'RESTRICTED_ACCESS_NOTICE',
          'SEARCH_DISPLAY', 'INDEX_PAGE', 'UNCLASSIFIED'}
RELATIONS = {'REPOST_OF', 'QUOTES', 'REFERS_TO', 'RELATED_UNVERIFIED'}
ROUTES = {'ISSUER_INVESTOR_RELATIONS': 'Issuer investor relations and original releases',
          'REGULATOR_FILINGS': 'Public regulator filings',
          'EXCHANGE_DISCLOSURES': 'Public exchange disclosures',
          'ORIGINAL_PUBLISHER': 'Original public author or publisher material',
          'PUBLIC_SEARCH': 'Public search for relevant original sources'}
GAP_REASONS = {'MISSING_CURRENT_OBSERVATION', 'MISSING_ORIGINAL_DOCUMENT', 'MISSING_POLICY_DISCLOSURE',
               'MISSING_BASIS_OR_PERIOD', 'INCOMPLETE_ACCESS', 'UNRESOLVED_LINEAGE', 'UNREVIEWED'}
LIMITS = [
    'Quotations preserve original wording; sources are attributed, not authenticated.',
    'Topic relevance, access and lineage are explicit participant declarations, not semantic certification.',
    'An adopted topic inventory does not prove complete interpretation of the full original request.',
    'Missing selected evidence means unresolved coverage, not zero, source absence or no activity.',
    'No currency, period, amount, probability or current condition is inferred from another source or passage.',
    'Discovery routes are prospective and NOT_EXECUTED; no external acquisition or account action occurs.',
]


def exact(value, keys, code):
    store.require(type(value) is dict and set(value) == set(keys), code)


def identifier(value):
    store.require(type(value) is str and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,79}', value), 'IDENTIFIER_REQUIRED')


def adopted_scope(raw, request_raw, manifest_pin):
    scope = parse(raw)
    required = {'schema_version', 'original_request', 'manifest_sha256', 'units'}
    store.require(type(scope) is dict and required <= set(scope) <= required | {'analysis_profile', 'require_topic_gap_declarations'}, 'COVERAGE_SCOPE_FIELDS')
    store.require(scope.get('analysis_profile', 'EXACT_SOURCE_ONLY') in ('EXACT_SOURCE_ONLY', 'ANALYST_REVISIONS', 'INSIDER_DISCLOSURES'), 'SUPPORTED_COVERAGE_ANALYSIS_PROFILE')
    store.require(type(scope.get('require_topic_gap_declarations', False)) is bool, 'GAP_REQUIREMENT_BOOLEAN')
    store.require(type(scope['schema_version']) is int and scope['schema_version'] == 1, 'SCOPE_SCHEMA')
    exact(scope['original_request'], ('path', 'sha256'), 'ORIGINAL_REQUEST_REFERENCE')
    store.relative(scope['original_request']['path'])
    store.require(store.digest(request_raw) == scope['original_request']['sha256'], 'ORIGINAL_REQUEST_CHANGED')
    store.require(scope['manifest_sha256'] == manifest_pin, 'SCOPE_ORIGINAL_CORPUS_MISMATCH')
    request_text = request_raw.decode('utf8')
    store.require(request_text.strip(), 'ORIGINAL_REQUEST_EMPTY')
    store.require(type(scope['units']) is list and 0 < len(scope['units']) <= 32, 'BOUNDED_REQUEST_UNITS')
    units = []; seen = set()
    for unit in scope['units']:
        exact(unit, ('id', 'start_byte', 'end_byte', 'sha256'), 'REQUEST_UNIT_FIELDS')
        identifier(unit['id']); store.require(unit['id'] not in seen, 'DUPLICATE_REQUEST_UNIT'); seen.add(unit['id'])
        start, end = unit['start_byte'], unit['end_byte']
        store.require(type(start) is int and type(end) is int and 0 <= start < end <= len(request_raw), 'REQUEST_UNIT_SPAN_RANGE')
        text = request_raw[start:end].decode('utf8')
        request_raw[:start].decode('utf8'); request_raw[end:].decode('utf8')
        store.require(text.strip() and store.digest(request_raw[start:end]) == unit['sha256'], 'REQUEST_UNIT_SPAN_CHANGED')
        units.append({**deepcopy(unit), 'original_request_text': text})
    return scope, request_text, units


def declared_gaps(value, corpus):
    store.require(type(value) is list and len(value) <= 32, 'BOUNDED_TOPIC_GAPS')
    result = []; labels = set()
    for gap in value:
        exact(gap, ('requested_evidence_dimension', 'reason', 'reviewed_source_ids', 'source_spans', 'acquisition_route'), 'DECLARED_GAP_FIELDS')
        label = gap['requested_evidence_dimension']
        store.require(type(label) is str and re.fullmatch(r'[A-Za-z][A-Za-z _/-]{0,119}', label)
                      and label.casefold() not in labels, 'NONNUMERIC_EVIDENCE_DIMENSION_LABEL_REQUIRED')
        labels.add(label.casefold())
        store.require(gap['reason'] in GAP_REASONS and gap['acquisition_route'] in ROUTES, 'DECLARED_GAP_ENUM_REQUIRED')
        reviewed = gap['reviewed_source_ids']
        store.require(type(reviewed) is list and all(type(s) is str for s in reviewed)
                      and len(reviewed) == len(set(reviewed)) and set(reviewed) <= set(corpus.sources), 'GAP_REVIEW_SOURCE_IDS')
        store.require(type(gap['source_spans']) is list and len(gap['source_spans']) <= 32, 'BOUNDED_GAP_SOURCE_SPANS')
        spans = []
        for ref in gap['source_spans']:
            exact(ref, ('source_id', 'start_byte', 'end_byte', 'sha256'), 'GAP_SOURCE_SPAN_FIELDS')
            store.require(type(ref['source_id']) is str and ref['source_id'] in reviewed, 'GAP_SPAN_OUTSIDE_REVIEWED_SOURCES')
            raw = corpus.sources[ref['source_id']]['raw']; start, end = ref['start_byte'], ref['end_byte']
            store.require(type(start) is int and type(end) is int and 0 <= start < end <= len(raw), 'GAP_SOURCE_SPAN_RANGE')
            text = raw[start:end].decode('utf8');raw[:start].decode('utf8');raw[end:].decode('utf8')
            store.require(store.digest(raw[start:end]) == ref['sha256'], 'GAP_SOURCE_SPAN_CHANGED')
            spans.append({**deepcopy(ref), 'original_source_text': text})
        result.append({**deepcopy(gap), 'source_spans': spans,
                       'declaration_status': 'PARTICIPANT_DECLARED_UNVERIFIED',
                       'label_meaning': 'Requested evidence dimension; not an asserted factual absence.',
                       'source_absence_established': False, 'acquisition_status': 'NOT_EXECUTED'})
    return result


def assemble(plan, scope_raw, request_raw, corpus):
    scope, request_text, units = adopted_scope(scope_raw, request_raw, corpus.pin)
    exact(plan, ('schema_version', 'units', 'sources'), 'COVERAGE_PLAN_FIELDS')
    store.require(type(plan['schema_version']) is int and plan['schema_version'] == 1, 'PLAN_SCHEMA')
    store.require(type(plan['sources']) is list and len(plan['sources']) <= 128, 'BOUNDED_SOURCE_DISPOSITIONS')
    sources = {}
    for row in plan['sources']:
        exact(row, ('source_id', 'access', 'lineage'), 'SOURCE_DISPOSITION_FIELDS')
        sid = row['source_id']; store.require(type(sid) is str and sid in corpus.sources and sid not in sources, 'SOURCE_ROSTER_MISMATCH')
        store.require(row['access'] in ACCESS, 'ACCESS_DECLARATION_REQUIRED')
        store.require(type(row['lineage']) is list and len(row['lineage']) <= 32, 'BOUNDED_LINEAGE_DECLARATIONS')
        for relation in row['lineage']:
            exact(relation, ('source_id', 'relation'), 'LINEAGE_FIELDS')
            store.require(relation['source_id'] in corpus.sources and relation['source_id'] != sid
                          and relation['relation'] in RELATIONS, 'LINEAGE_DECLARATION_INVALID')
        original = corpus.sources[sid]
        store.require(original['format'] in ('text', 'json'), 'UTF8_SOURCE_FORMAT_REQUIRED')
        body = original['raw'].decode('utf8')
        sources[sid] = {'source_id': sid, 'path': original['path'], 'sha256': original['sha256'],
                       'original_text': body, 'access_declaration': row['access'],
                       'lineage_declarations': deepcopy(row['lineage']),
                       'declaration_status': 'SEMANTICALLY_UNVERIFIED',
                       'quotation_status': 'EXACT_WHOLE_ORIGINAL_SOURCE'}
    store.require(set(sources) == set(corpus.sources), 'INCOMPLETE_ORIGINAL_SOURCE_ROSTER')
    store.require(type(plan['units']) is list and len(plan['units']) <= 32, 'BOUNDED_TOPIC_ROWS')
    rows = {}
    for row in plan['units']:
        needed = {'unit_id', 'source_ids', 'discovery_routes'}
        if scope.get('require_topic_gap_declarations'):needed.add('gaps')
        store.require(type(row) is dict and needed <= set(row) <= needed | {'gaps'}, 'TOPIC_ROW_FIELDS')
        uid = row['unit_id']; store.require(type(uid) is str and uid in {u['id'] for u in units} and uid not in rows, 'TOPIC_ROSTER_MISMATCH')
        ids = row['source_ids']
        store.require(type(ids) is list and all(type(s) is str for s in ids) and len(ids) == len(set(ids))
                      and set(ids) <= set(sources), 'TOPIC_SOURCE_IDS')
        routes = row['discovery_routes']
        store.require(type(routes) is list and all(type(r) is str for r in routes)
                      and len(routes) == len(set(routes)) and set(routes) <= set(ROUTES), 'PROSPECTIVE_DISCOVERY_ROUTES')
        rows[uid] = {'unit_id': uid, 'source_ids': list(ids),
                     'coverage_status': 'EXCERPTS_SELECTED_INTERPRETATION_UNVERIFIED' if ids else 'UNRESOLVED_NO_SOURCE_EXCERPT_SELECTED',
                     'discovery_routes': [{'route': r, 'description': ROUTES[r], 'status': 'NOT_EXECUTED'} for r in routes],
                     'source_absence_established': False,
                     'declared_gaps': declared_gaps(row.get('gaps', []), corpus),
                     'gap_inventory_status': 'DECLARED_GAPS_PRESENT_UNVERIFIED' if row.get('gaps') else 'NO_GAP_DECLARED_NOT_PROOF_OF_COMPLETE_COVERAGE'}
    store.require(set(rows) == {u['id'] for u in units}, 'INCOMPLETE_ADOPTED_REQUEST_UNITS')
    result = {'method': METHOD, 'status': 'SOURCE_BOUND_COVERAGE_MAP_PARTIAL',
            'original_request': {'path': scope['original_request']['path'], 'sha256': store.digest(request_raw), 'text': request_text},
            'units': [{**unit, **rows[unit['id']]} for unit in units],
            'source_inventory': [sources[sid] for sid in corpus.sources],
            'source_absence_established': False, 'semantic_completeness_verified': False,
            'source_authenticity_verified': False, 'currency_or_period_inference_performed': False,
            'additional_authored_fact_prose': False, 'external_acquisition': 'NOT_EXECUTED',
            'execution_authorized': False, 'limitations': LIMITS}
    if scope.get('analysis_profile') == 'ANALYST_REVISIONS':
        import analyst_revisions
        store.require(Path(analyst_revisions.__file__).resolve() == store.ROOT / 'scripts/analyst_revisions.py', 'REVISION_IMPLEMENTATION_OUTSIDE_SKILL')
        result['native_analysis'] = analyst_revisions.analyze(corpus)
        result['limitations'] = LIMITS + ['Native analyst reported-value comparisons use metric-specific dimensions; unresolved coverage conflicts and raw/structured gaps are not clean revision proof.']
    elif scope.get('analysis_profile') == 'INSIDER_DISCLOSURES':
        import insider_disclosures
        store.require(Path(insider_disclosures.__file__).resolve() == store.ROOT / 'scripts/insider_disclosures.py', 'INSIDER_IMPLEMENTATION_OUTSIDE_SKILL')
        result['native_analysis'] = insider_disclosures.analyze(corpus)
        result['limitations'] = LIMITS + ['Insider units and identities are row-local. Listed-row arithmetic is conditional; no current holdings, settled cash, motive or legal conclusion is established.']
    return result


def literal(text):
    # Preserve potentially hostile source Markdown as literal quoted evidence.
    fence = '`' * max(3, 1 + max((len(m) for m in re.findall(r'`+', text)), default=0))
    return fence + '\n' + text + ('' if text.endswith('\n') else '\n') + fence + '\n'


def render(result):
    sources = {s['source_id']: s for s in result['source_inventory']}
    numeric_scope = ('Original quotations are unchanged; native calculations and exact linked dimensions are identified with their limits. '
                     if 'native_analysis' in result else 'No numeric fact is paraphrased or inferred. ')
    parts = ['# Source-bound information coverage map\n',
             'Status: PARTIAL. Exact original quotations follow; topic relevance, access and lineage remain declared. '
             + numeric_scope + 'Current completeness and source absence are not established.\n',
             '## Complete original request\n', literal(result['original_request']['text'])]
    if 'native_analysis' in result:
        analysis = result['native_analysis']
        if analysis['method'] == 'source-bound-insider-disclosures-1':
            parts += ['## Native source-bound insider row review\n',
                      'Reported transaction mechanisms, literal footnotes and separate transaction/filing dates follow. '
                      'Insider currency comes only from explicit row fields; missing currency remains unspecified. '
                      'Quantity/price arithmetic is conditional and does not establish settled cash, current holdings, motive or legal compliance.\n']
            for dataset in analysis['datasets']:
                for row in dataset['rows']:
                    parts += ['### Original insider row\n', literal(store.encode(row).decode('utf8'))]
            parts += ['## Native reported institutional snapshots\n',
                      'Explicit amendments replace their matched same-period predecessor only when the supplied chain is unambiguous. '
                      'Snapshot differences are reported-scope arithmetic, not purchases, sales or current positions. '
                      'Original filing and amendment availability remain separate.\n',
                      literal(store.encode(analysis['institution_snapshots']).decode('utf8'))]
            parts += ['### Complete native analysis and original-source bindings\n', literal(store.encode(analysis).decode('utf8'))]
        else:
            parts += ['## Native metric-specific revision evidence\n',
                  'Reported values are compared within each metric contract. Conditional numeric differences are not verified genuine revisions. '
                  'Original records, source pointers, raw corroboration gaps and dimensions are retained below.\n',
                  '### Coverage events and conflicts\n', literal(store.encode(analysis['event_assessments']).decode('utf8'))]
            for row in analysis['metric_comparisons']:
                parts += ['### Metric comparison: ' + row['metric'] + '\n', literal(store.encode(row).decode('utf8'))]
            parts += ['### Target-record chronology and literal horizon dispositions\n',
                      'Every original target-list record receives a disposition, including records without a revision event. '
                      'Different or unknown horizon labels do not become equal durations. Same-time records retain their separate source bindings.\n',
                      literal(store.encode(analysis['target_record_coverage']).decode('utf8'))]
            parts += ['### Complete native analysis and original-record bindings\n', literal(store.encode(analysis).decode('utf8'))]
    for i, unit in enumerate(result['units'], 1):
        parts += ['## Request unit ' + str(i) + '\n', literal(unit['original_request_text']),
                  'Coverage: ' + unit['coverage_status'] + '. This is not a source-absence finding.\n']
        for sid in unit['source_ids']:
            source = sources[sid]
            parts += ['### Selected original source\n', literal(sid),
                      'Declared access: ' + source['access_declaration'] + '. Selection/relevance is unverified.\n',
                      literal(source['original_text'])]
        for route in unit['discovery_routes']:
            parts += ['Prospective discovery — ' + route['description'] + ': NOT_EXECUTED.\n']
        parts += ['### Declared evidence and access gaps\n', unit['gap_inventory_status'] + '\n']
        for gap in unit['declared_gaps']:
            parts += ['Requested evidence dimension (participant declaration, not a factual absence claim):\n', literal(gap['requested_evidence_dimension']),
                      'Declared reason: ' + gap['reason'] + '. Unverified; source absence is not established.\n',
                      'Reviewed source identifiers (declared):\n', literal(store.encode(gap['reviewed_source_ids']).decode('utf8'))]
            for span in gap['source_spans']:
                parts += ['Exact supporting source passage; its interpretation remains unverified:\n', literal(span['source_id']), literal(span['original_source_text'])]
            parts += ['Prospective acquisition — ' + ROUTES[gap['acquisition_route']] + ': NOT_EXECUTED.\n']
    parts += ['## Complete original-source inventory\n',
              'Every indexed source is retained below, including unselected evidence. Dates and original wording belong to the source; '
              'a declared access/lineage label does not independently verify its meaning.\n']
    for index, source in enumerate(result['source_inventory'], 1):
        parts += ['### Original source ' + str(index) + '\n', literal(source['source_id']), literal(source['path']),
                  'SHA256: ' + source['sha256'] + '\n', 'Declared access: ' + source['access_declaration'] + '\n']
        for relation in source['lineage_declarations']:
            parts += ['Declared lineage: ' + relation['relation'] + ' (unverified). Source identifier:\n', literal(relation['source_id'])]
        parts += [literal(source['original_text'])]
    parts += ['## Limits\n'] + ['- ' + line + '\n' for line in result['limitations']]
    return ('\n'.join(parts).rstrip() + '\n').encode('utf8')


def replay(directory, expected_scope_sha256, expected_manifest_sha256):
    directory = store.safe(directory); context = parse(store.read(directory / 'context.json'))
    store.require(context['method'] == METHOD and context['scope_sha256'] == expected_scope_sha256
                  and context['manifest_sha256'] == expected_manifest_sha256, 'EXTERNAL_COVERAGE_PINS_MISMATCH')
    store.require(context['implementation_sha256'] == store.implementations()
                  and context['version_sha256'] == store.digest(store.read(store.ROOT / 'VERSION')), 'COVERAGE_IMPLEMENTATION_CHANGED')
    scope_raw = store.read(directory / 'scope.json'); request_raw = store.read(directory / 'original-request.txt')
    plan_raw = store.read(directory / 'plan.json'); metadata_raw = store.read(directory / 'metadata.json')
    store.require(store.digest(scope_raw) == expected_scope_sha256 and store.digest(plan_raw) == context['plan_sha256']
                  and store.digest(metadata_raw) == context['metadata_sha256'], 'COVERAGE_INPUT_CHANGED')
    corpus = Corpus(directory / 'ingress.json', expected_manifest_sha256, directory / 'originals')
    result = assemble(parse(plan_raw), scope_raw, request_raw, corpus)
    metadata = final_report.response_metadata(metadata_raw)
    first = render(result)
    response = store.encode({**result, 'case_id': metadata['case_id'],
        'candidate_version': store.read(store.ROOT / 'VERSION').decode().strip(),
        'input_hashes': {**{s['path']: s['sha256'] for s in corpus.sources.values()},
                         result['original_request']['path']: store.digest(request_raw)},
        'runtime_model_metadata': metadata['runtime_model_metadata'],
        'evidence_paths': metadata.get('evidence_paths', []),
        'execution_limitations': metadata.get('execution_limitations', []),
        'metadata_status': 'PARTICIPANT_DECLARATIONS_NOT_ANALYTICAL_CLAIMS',
        'first_response_sha256': store.digest(first)})
    store.require(len(first) <= store.MAX_FILE and len(response) <= store.MAX_FILE, 'COVERAGE_OUTPUT_TOO_LARGE')
    return first, response


def compose(plan, scope, scope_pin, manifest, manifest_pin, source_root, output, metadata=None):
    output = store.safe(output); root = store.safe(source_root)
    store.require(not output.exists() and not output.is_relative_to(store.ROOT)
                  and not root.is_relative_to(output), 'NEW_PRIVATE_COVERAGE_OUTPUT_REQUIRED')
    scope_raw = store.read(scope); store.require(store.digest(scope_raw) == scope_pin, 'EXTERNAL_SCOPE_PIN_MISMATCH')
    scope_doc = parse(scope_raw)
    request_path = store.safe(root / store.relative(scope_doc['original_request']['path']))
    store.require(request_path.is_relative_to(root), 'ORIGINAL_REQUEST_OUTSIDE_ROOT')
    request_raw = store.read(request_path)
    corpus = Corpus(manifest, manifest_pin, root); plan_raw = store.read(plan)
    assemble(parse(plan_raw), scope_raw, request_raw, corpus)
    metadata_raw = store.read(metadata) if metadata is not None else store.encode({'case_id': 'unspecified', 'runtime_model_metadata': {'model': 'unknown', 'effort': 'unknown'}})
    final_report.response_metadata(metadata_raw)
    output.mkdir(parents=True, exist_ok=False)
    for name, raw in [('scope.json', scope_raw), ('original-request.txt', request_raw), ('plan.json', plan_raw),
                      ('metadata.json', metadata_raw), ('ingress.json', store.read(manifest))]:
        store.write(output, name, raw)
    total = len(request_raw)
    for source in corpus.sources.values():
        total += len(source['raw']); store.require(total <= store.MAX_TOTAL, 'COVERAGE_INPUTS_TOO_LARGE')
        store.write(output, 'originals/' + store.relative(source['path']), source['raw'])
    context = {'method': METHOD, 'scope_sha256': scope_pin, 'manifest_sha256': manifest_pin,
               'plan_sha256': store.digest(plan_raw), 'metadata_sha256': store.digest(metadata_raw),
               'implementation_sha256': store.implementations(),
               'version_sha256': store.digest(store.read(store.ROOT / 'VERSION'))}
    store.write(output, 'context.json', store.encode(context))
    first, response = replay(output, scope_pin, manifest_pin)
    store.write(output, 'first-response.md', first); store.write(output, 'response.json', response)
    receipt = {'method': METHOD, 'status': 'EXACT_SOURCE_COVERAGE_REPLAYED', 'scope_sha256': scope_pin,
               'manifest_sha256': manifest_pin, 'first_response_sha256': store.digest(first),
               'response_sha256': store.digest(response), 'semantic_completeness_verified': False,
               'artifacts': store.file_inventory(output)}
    store.write(output, 'receipt.json', store.encode(receipt))
    return verify(output, scope_pin, manifest_pin)


def verify(directory, expected_scope_sha256, expected_manifest_sha256, first_response=None, response=None):
    directory = store.safe(directory); receipt = parse(store.read(directory / 'receipt.json'))
    store.require(receipt.get('method') == METHOD and receipt.get('status') == 'EXACT_SOURCE_COVERAGE_REPLAYED'
                  and receipt.get('semantic_completeness_verified') is False, 'COVERAGE_RECEIPT_REQUIRED')
    store.require(receipt.get('scope_sha256') == expected_scope_sha256
                  and receipt.get('manifest_sha256') == expected_manifest_sha256, 'RECEIPT_EXTERNAL_PINS_MISMATCH')
    store.require(receipt['artifacts'] == store.file_inventory(directory), 'COVERAGE_ARTIFACTS_CHANGED')
    first, structured = replay(directory, expected_scope_sha256, expected_manifest_sha256)
    store.require(first == store.read(directory / 'first-response.md') and structured == store.read(directory / 'response.json')
                  and receipt['first_response_sha256'] == store.digest(first) and receipt['response_sha256'] == store.digest(structured), 'COVERAGE_REPLAY_MISMATCH')
    if first_response is not None:store.require(store.read(first_response) == first, 'PUBLISHED_FIRST_DIFFERS_FROM_COVERAGE')
    if response is not None:store.require(store.read(response) == structured, 'PUBLISHED_JSON_DIFFERS_FROM_COVERAGE')
    return dict(receipt)


def main():
    p = argparse.ArgumentParser(description=__doc__); sub = p.add_subparsers(dest='mode', required=True)
    c = sub.add_parser('compose'); c.add_argument('plan'); c.add_argument('--scope', required=True)
    c.add_argument('--scope-sha256', required=True); c.add_argument('--manifest', required=True)
    c.add_argument('--manifest-sha256', required=True); c.add_argument('--source-root', required=True)
    c.add_argument('--output', required=True); c.add_argument('--metadata')
    v = sub.add_parser('verify'); v.add_argument('directory'); v.add_argument('--scope-sha256', required=True)
    v.add_argument('--manifest-sha256', required=True); v.add_argument('--first-response'); v.add_argument('--response')
    a = p.parse_args()
    try:
        result = compose(a.plan, a.scope, a.scope_sha256, a.manifest, a.manifest_sha256, a.source_root, a.output, a.metadata) if a.mode == 'compose' else verify(a.directory, a.scope_sha256, a.manifest_sha256, a.first_response, a.response)
        print(store.encode(result).decode()); return 0
    except (ValueError, KeyError, TypeError, OSError, UnicodeError) as error:
        print(json.dumps({'status': 'INCOMPLETE_OR_INVALID_COVERAGE', 'error': str(error)})); return 1


if __name__ == '__main__':raise SystemExit(main())
