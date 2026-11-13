"""Compose fixed offline research reports and bind the exact final response.

Replay is local consistency, not source authenticity or arbitrary-prose grading.
Only new private directories are written; verify is read-only.
"""
from pathlib import Path
import argparse
import json
import re
import sys

import handoff_report as exact_json
import supplied_research as source
from source_lineage import load_manifest, parse

METHOD = 'final-report-1'
RESPONSE = 'first-response.md'
ANALYSIS = 'analysis.json'
STRICT = 'STRUCTURED_RESEARCH_ONLY'
LEGACY = 'LEGACY_UNAUDITED_COMPATIBILITY'
ENVELOPE_METHOD = 'final-response-envelope-1'
READINESS = 'strict-terminal-execution-1'
PREPARATION = 'preparation.json'
FINAL_FILES = frozenset((RESPONSE, ANALYSIS, 'audit.json', 'receipt.json'))
MAX_SECTIONS = 8
MAX_PROSE = 128 * 1024
CONCLUSION_OBJECTIVES = ('AFTER_COST_CAPITAL_PRESERVATION', 'DCF_DISCOUNT_CLOSURE')
require = source.require


def encoded(value):
    """Retain Decimal numeric types in derived requests, not string metadata."""
    return (exact_json.encode(value) + '\n').encode('utf-8')


def fields(value, required, optional=()):
    require(isinstance(value, dict) and set(required) <= set(value) <= set(required) | set(optional),
            'EXACT_PLAN_OR_SECTION_FIELDS_REQUIRED')


def plan(raw):
    doc = parse(raw)
    fields(doc, {'sections'}, {'unverified_prose', 'objective_conclusion_required', 'output_contract'})
    require(doc.get('output_contract', LEGACY) in (LEGACY, STRICT), 'SUPPORTED_OUTPUT_CONTRACT_REQUIRED')
    strict = doc.get('output_contract') == STRICT
    require(not strict or 'unverified_prose' not in doc, 'STRICT_REPORT_FORBIDS_FREE_PROSE')
    require('objective_conclusion_required' not in doc or type(doc['objective_conclusion_required']) is bool,
            'CONCLUSION_REQUIREMENT_BOOLEAN_REQUIRED')
    require(isinstance(doc['sections'], list) and 0 < len(doc['sections']) <= MAX_SECTIONS,
            'BOUNDED_NONEMPTY_SECTIONS_REQUIRED')
    for index, row in enumerate(doc['sections']):
        require(isinstance(row, dict), 'SECTION_OBJECT_REQUIRED')
        kind = row.get('kind')
        if kind == 'source_report':
            fields(row, {'kind', 'producer', 'request'})
            require(row['producer'] in source.PRODUCERS and isinstance(row['request'], dict),
                    'SUPPORTED_SOURCE_PRODUCER_REQUIRED')
        elif kind == 'source_claim':
            fields(row, {'kind', 'request'}, {'label'})
            require(not strict or 'label' not in row, 'STRICT_REPORT_FORBIDS_CALLER_LABEL')
            require(isinstance(row['request'], dict) and row['request'].get('operation') in ('accounting', 'presence'),
                    'ACCOUNTING_OR_PRESENCE_REQUIRED')
            require('label' not in row or row['request']['operation'] == 'accounting' and
                    row['label'] in ('diagnostic_ratio', 'basic_eps', 'diluted_eps'), 'SUPPORTED_ACCOUNTING_LABEL_REQUIRED')
        elif kind == 'issuer_facts':
            fields(row, {'kind', 'request'})
            require(isinstance(row['request'], dict), 'ISSUER_REQUEST_REQUIRED')
        elif kind == 'terminal_objectives':
            fields(row, {'kind', 'contract', 'document'})
            require(isinstance(row['contract'], dict) and isinstance(row['document'], dict),
                    'WORKFLOW_CONTRACT_AND_BOUND_DOCUMENT_REQUIRED')
        elif kind == 'objective_conclusion':
            fields(row, {'kind', 'evidence_section', 'objective_id', 'domain_scope'},
                   {'research_judgment', 'include_boundaries'})
            ref = row['evidence_section']
            require(type(ref) is int and 0 <= ref < index and
                    doc['sections'][ref].get('kind') == 'terminal_objectives',
                    'EARLIER_TERMINAL_EVIDENCE_REQUIRED')
            require(row['objective_id'] in CONCLUSION_OBJECTIVES and row['domain_scope'] == 'SUPPLIED_ROWS',
                    'SUPPORTED_OBJECTIVE_AND_EXPLICIT_DOMAIN_REQUIRED')
            require('include_boundaries' not in row or type(row['include_boundaries']) is bool,
                    'BOUNDARY_OPTION_BOOLEAN_REQUIRED')
            require(not row.get('include_boundaries') or row['objective_id'] == 'AFTER_COST_CAPITAL_PRESERVATION',
                    'BOUNDARIES_REQUIRE_CAPITAL_PRESERVATION_OBJECTIVE')
            if 'research_judgment' in row:
                fields(row['research_judgment'], {'stance'})
                require(row['research_judgment']['stance'] in ('favorable', 'unfavorable', 'undetermined'),
                        'ENUMERATED_ANALYST_STANCE_REQUIRED')
        else:
            raise ValueError('UNSUPPORTED_SECTION_KIND')
    if doc.get('objective_conclusion_required'):
        terminals = {i for i, row in enumerate(doc['sections']) if row['kind'] == 'terminal_objectives'}
        referenced = {row['evidence_section'] for row in doc['sections'] if row['kind'] == 'objective_conclusion'}
        require(terminals and terminals == referenced, 'CONCLUSION_REQUIRED_FOR_EACH_TERMINAL_SECTION')
    if 'unverified_prose' in doc:
        require(isinstance(doc['unverified_prose'], str) and doc['unverified_prose'].strip() and
                len(doc['unverified_prose'].encode('utf-8')) <= MAX_PROSE, 'BOUNDED_UNVERIFIED_PROSE_REQUIRED')
    return doc


def retain_corpus(output, manifest, pin, root):
    raw = source.read(manifest)
    require(source.digest(raw) == pin, 'EXTERNAL_MANIFEST_PIN_MISMATCH')
    definition = parse(raw)
    require(isinstance(definition, dict) and isinstance(definition.get('sources'), list) and
            0 < len(definition['sources']) <= 10000, 'BOUNDED_ORIGINAL_CORPUS_REQUIRED')
    load_manifest(manifest, pin, root)
    names, total = set(), 0
    source.write(output, 'ingress.json', raw)
    for row in definition['sources']:
        name = source.relative(row['path']); path = source.safe(root / name)
        require(path.is_relative_to(root) and name.casefold() not in names, 'ORIGINAL_PATH_OR_ALIAS')
        names.add(name.casefold()); content = source.read(path); total += len(content)
        require(total <= source.MAX_TOTAL and source.digest(content) == row['sha256'], 'ORIGINAL_SIZE_OR_HASH')
        source.write(output, 'originals/' + name, content)


def producer_request(section):
    producer = 'issuer_evidence' if section['kind'] == 'issuer_facts' else section.get('producer', 'source_claims')
    return {'producer': producer, 'producer_request': section['request']}


def workflow_plan(section, definition):
    return {'schema_version': 1, 'network_mode': 'offline', 'contract': section['contract'],
            'sources': [{key: row[key] for key in ('id', 'path', 'sha256', 'format')} |
                        {'role': 'supplied_original_bytes_semantic_role_unverified'} for row in definition['sources']],
            'jobs': [{'id': 'terminal', 'operation': 'financial.terminal_scenarios',
                      'arguments': {'document': section['document']}}],
            'claims': [], 'requirements': []}


def make_section(section, directory, manifest, pin, originals):
    directory.mkdir()
    if section['kind'] == 'objective_conclusion':
        source.write(directory, 'conclusion-request.json', encoded(section))
    elif section['kind'] in ('source_report', 'source_claim', 'issuer_facts'):
        request = directory / 'request.json'
        source.write(directory, 'request.json', encoded(producer_request(section)))
        source.run(request, directory / 'producer', manifest, pin, originals)
    else:
        import research_workflow as workflow
        raw = workflow.encode(workflow_plan(section, parse(source.read(manifest))))
        source.write(directory, 'workflow-plan.json', raw)
        # Build executes only the fixed terminal operation; reader is restricted
        # to the externally pinned complete original inventory above.
        allowed = {row['path'] for row in parse(source.read(manifest))['sources']}
        def reader(name):
            require(name in allowed, 'UNRETAINED_WORKFLOW_SOURCE')
            return source.read(originals / source.relative(name))
        work = directory / 'workflow'; work.mkdir()
        artifacts = workflow.build(raw, reader, artifact_writer=lambda name, data: source.write(work, name, data))
        # The builder's writer retains every artifact as produced, including
        # failures before completion. No caller-created results are accepted.
        require('receipt.json' in artifacts, 'WORKFLOW_RECEIPT_REQUIRED')


def replay_section(section, directory, manifest, pin):
    if section['kind'] in ('source_report', 'source_claim', 'issuer_facts'):
        expected = encoded(producer_request(section))
        require(source.read(directory / 'request.json') == expected and
                source.read(directory / 'producer/original-request.json') == expected,
                'SECTION_REQUEST_DIFFERS_FROM_PLAN')
        require(source.read(directory / 'producer/ingress.json') == source.read(manifest), 'SECTION_CORPUS_DIFFERS')
        audit = source.verify(directory / 'producer')
        result_raw = source.read(directory / 'producer/result.json')
        require(source.digest(result_raw) == audit['result_sha256'], 'PRODUCER_CHANGED_AFTER_REPLAY')
        result = parse(result_raw)
        body = source.read(directory / 'producer/report.md', source.MAX_REPORT).decode('utf-8')
        # Keep the complete fixed producer report, not chosen sentences. The
        # link is deterministically rebased when embedded in the final file.
        prefix = directory.name
        body = body.replace('[Complete structured evidence](result.json)',
                            '[Complete structured evidence](sections/' + prefix + '/producer/result.json)')
        if section['kind'] == 'source_claim':
            import report_claims
            claim = {'id': 'source-assessment', 'kind': 'source_presence',
                     'evidence': {'artifact': 'source', 'pointer': ''}}
            if section['request']['operation'] == 'accounting':
                label = section.get('label')
                if label is None:
                    label = {'DILUTED_EPS_SOURCE_BOUND': 'diluted_eps', 'BASIC_EPS_SOURCE_BOUND': 'basic_eps'}.get(
                        result.get('classification'), 'diagnostic_ratio')
                claim.update(kind='accounting_label', label=label)
            typed_plan = {'artifacts': {'source': {'path': 'producer/result.json', 'sha256': source.digest(result_raw)}},
                          'segments': [{'claim': claim}]}
            rendered = report_claims.compile_report(typed_plan, {'source': result_raw})
            checked = report_claims.audit_saved_report(typed_plan, {'source': result_raw}, rendered['report'].encode('utf-8'))
            require(not checked['differences'], 'TYPED_REPORT_REPLAY_MISMATCH')
            body += '\n' + rendered['report']
        return body, {'kind': section['kind'], 'source_audit': audit,
                      'result_sha256': source.digest(result_raw)}
    import research_workflow as workflow
    import financial_alignment
    definition = parse(source.read(manifest))
    expected = workflow.encode(workflow_plan(section, definition))
    require(source.read(directory / 'workflow-plan.json') == expected and
            source.read(directory / 'workflow/plan.json') == expected, 'WORKFLOW_PLAN_DIFFERS')
    audit = workflow.verify(directory / 'workflow')
    result_raw = source.read(directory / 'workflow/result.json')
    result = workflow.read_result(result_raw)
    require(len(result['jobs']) == 1 and result['jobs'][0]['operation'] == 'financial.terminal_scenarios',
            'EXACT_TERMINAL_JOB_REQUIRED')
    job = result['jobs'][0]
    require(any(row['kind'] == 'SOURCE' for row in result['bindings'][0]['arguments']),
            'TERMINAL_ORIGINAL_SOURCE_BINDING_REQUIRED')
    if job['status'] != 'COMPUTED':
        body = 'Terminal objective report unavailable. Replayed job status: ' + json.dumps(job['status']) + \
               '; reason: ' + json.dumps(job.get('reason')) + '. No objective success is established.\n'
    else:
        arguments = workflow.report_facts.strict_json(source.read(directory / 'workflow/jobs/0000/arguments.json'))
        native = financial_alignment.terminal_scenarios(arguments['document'])
        # The installed workbench adds this fixed nonexecution field to each
        # native result. Compare its exact wrapper too; do not drop other keys
        # or relax numerical equality to make a retained result pass.
        require(job['result'].get('execution_authorized') is False and
                workflow.encode(dict(native, execution_authorized=False)) == workflow.encode(job['result']),
                'NATIVE_TERMINAL_RESULT_MISMATCH')
        body = native['diagnostic_objectives']['report']
    body += '\n[Complete terminal results and input bindings](sections/' + directory.name + '/workflow/result.json).\n'
    body += 'Inputs are source-selected values or explicit assumptions; byte binding does not certify their semantic roles or economic feasibility.\n'
    return body, {'kind': section['kind'], 'workflow_audit': audit, 'job_status': job['status'],
                  'result_sha256': source.digest(result_raw)}


def replay_conclusion(section, directory, doc, manifest, pin):
    """Resolve an operative conclusion from replay, never a supplied outcome."""
    require(source.read(directory / 'conclusion-request.json') == encoded(section), 'CONCLUSION_REQUEST_CHANGED')
    index = section['evidence_section']; evidence = directory.parent / str(index).zfill(3)
    # Independently replay the referenced source-bound calculation, including
    # its native output comparison. An earlier saved success flag is not used.
    _, replayed = replay_section(doc['sections'][index], evidence, manifest, pin)
    import research_workflow as workflow
    result = workflow.read_result(source.read(evidence / 'workflow/result.json'))
    job = result['jobs'][0]
    conclusion = {'kind': 'objective_conclusion', 'evidence_section': index,
                  'source_result_sha256': replayed['result_sha256'],
                  'objective_id': section['objective_id'], 'domain_scope': section['domain_scope'],
                  'domain_exhaustive': False, 'general_joint_necessity_established': False,
                  'investment_correctness_verified': False, 'rows': []}
    lines = ['# Objective conclusion',
             'Requested objective: ' + section['objective_id'] + '.',
             'Evidence: replayed terminal section ' + str(index + 1) +
             '; source selections and declared assumptions remain as retained.']
    if section['objective_id'] == 'DCF_DISCOUNT_CLOSURE':
        conclusion['status'] = 'NOT_EVALUATED'
        lines.append('DCF discount closure: NOT_EVALUATED. This terminal evidence has no evaluated DCF cash-flow '
                     'model or closure criterion. No requirements for closing a DCF discount are established. '
                     'A capital-preservation result cannot answer this different objective.')
    elif job['status'] != 'COMPUTED':
        conclusion['status'] = 'UNRESOLVED_EVIDENCE'
        lines.append('Capital preservation: UNRESOLVED_EVIDENCE. Terminal calculation status ' +
                     json.dumps(job['status']) + '; no passing rows or necessary conditions are established.')
    else:
        diagnostic = job['result']['diagnostic_objectives']
        require(diagnostic['objective_id'] == section['objective_id'] and
                diagnostic['measure'] == 'net_total_return_fraction' and diagnostic['operator'] == '>=' and
                diagnostic['target'] == 0, 'REPLAYED_OBJECTIVE_CONTRACT_MISMATCH')
        rows = diagnostic['rows']
        require(isinstance(rows, list) and rows, 'NONEMPTY_REPLAYED_OBJECTIVE_ROWS_REQUIRED')
        require(all(row['objective_id'] == section['objective_id'] and
                    row['kind'] in ('supplied_scenario', 'declared_sensitivity') and
                    (row['met'] is None or type(row['met']) is bool) for row in rows),
                'REPLAYED_ROW_SCOPE_MISMATCH')
        conclusion.update(status='EVALUATED_SUPPLIED_ROWS_ONLY', rows=rows,
                          measure=diagnostic['measure'], operator=diagnostic['operator'], target=diagnostic['target'],
                          horizon_years=diagnostic['horizon_years'])
        lines.append('Comparator: net_total_return_fraction >= 0 after modeled costs; horizon ' +
                     str(diagnostic['horizon_years']) + ' years. This is capital preservation, not strictly '
                     'positive return, cash outperformance, a user investment target or DCF discount closure.')
        lines.append('Domain: the supplied scenario rows and explicitly declared sensitivity rows below. '
                     'Derived probes are separate diagnostics, not additional supplied rows; the economic domain is not exhaustive.')
        for key, label in ((True, 'Meeting the comparator'), (False, 'Not meeting the comparator'),
                           (None, 'Unresolved comparator')):
            selected = [{'id': row['id'], 'kind': row['kind']} for row in rows if row['met'] is key]
            lines.append(label + ', within this domain only: ' + json.dumps(selected, ensure_ascii=False) + '.')
        lines.append('Only the listed passing rows meet this comparator among these supplied rows. '
                     'This does not make their joint assumptions necessary in general, establish a unique pathway, '
                     'or establish sufficient business conditions for discount closure. Unresolved rows are not failures or successes.')
        if section.get('include_boundaries'):
            conclusion['boundaries'] = []
            for item in job['result']['conditional_exit_multiple_diagnostics']:
                require(item['criterion']['id'] == section['objective_id'] and
                        item['varied_parameter'] == 'exit_ev_to_ebit', 'BOUNDARY_OBJECTIVE_OR_PARAMETER_MISMATCH')
                solution = item.get('solution')
                verified = item['status'] in ('CONDITIONAL_BOUNDARY_COMPUTED', 'ALREADY_SATISFIED_AT_DOMAIN_MINIMUM')
                boundary = {'base_scenario_id': item['base_scenario_id'], 'status': item['status'],
                            'held_assumptions': item['held_assumptions'], 'domain': item.get('domain'),
                            'threshold': solution['minimum_multiple'] if verified else None,
                            'threshold_relation': item['boundary_replay']['exact_retained_operand_relation'] if verified else None,
                            'above_probe': item.get('above_probe'),
                            'strict_positive_return_established_by_equality': False}
                conclusion['boundaries'].append(boundary)
                label = json.dumps(item['base_scenario_id'], ensure_ascii=False)
                if verified:
                    minimum = boundary['threshold']
                    lines.append('Conditional minimum exit EV/EBIT for ' + label + ': ' + str(minimum['value']) +
                                 ' (exact ' + minimum['exact_numerator'] + '/' + minimum['exact_denominator'] +
                                 '); threshold outcome relation ' + boundary['threshold_relation'] +
                                 '. All other row inputs are held fixed within the retained investable-price domain.')
                    if item['status'] == 'CONDITIONAL_BOUNDARY_COMPUTED':
                        lines.append('This is the zero-return boundary; equality does not establish strictly positive return.')
                    else:
                        lines.append('The domain minimum already satisfies the comparator. This minimum is not necessarily '
                                     'an equality or zero-return break-even point.')
                else:
                    lines.append('Conditional minimum for ' + label + ': unavailable; diagnostic status ' +
                                 json.dumps(item['status']) + '. No verified threshold is established.')
                probe = boundary['above_probe']
                if probe:
                    value = probe['multiple']
                    lines.append('Separate higher-multiple probe for ' + label + ': ' + str(value['value']) +
                                 ' (exact ' + value['exact_numerator'] + '/' + value['exact_denominator'] +
                                 '); outcome relation ' + probe['exact_retained_operand_relation'] +
                                 '. This probe is not the threshold and must not be relabelled as break-even.')
            lines.append('These one-parameter thresholds and probes are mathematical diagnostics, not plausible-multiple '
                         'forecasts, general joint necessity, cash outperformance or DCF discount closure. '
                         'The conclusion audit retains every held input and domain alongside the threshold/probe roles.')
    if 'research_judgment' in section:
        stance = section['research_judgment']['stance']
        conclusion['research_judgment'] = {'stance': stance, 'status': 'ANALYST_OPINION_NOT_COMPUTED'}
        lines.append('Analyst-selected research stance: ' + stance +
                     '. This is an uncomputed opinion, not inferred from the comparator, source facts or a verified investment conclusion.')
    lines.append('Any separate unaudited commentary may still contain unsupported or contradictory claims. '
                 'This typed conclusion does not certify that commentary or the entire report.')
    return '\n\n'.join(lines) + '\n', conclusion


def _replay_artifacts(directory):
    context = parse(source.read(directory / 'context.json'))
    require(context['method'] == METHOD and context['implementation_sha256'] == source.implementations(),
            'FINAL_REPORT_IMPLEMENTATION_CHANGED')
    require(context['version_sha256'] == source.digest(source.read(source.ROOT / 'VERSION')) and
            context['candidate_version'] == source.read(source.ROOT / 'VERSION').decode('utf-8').strip(),
            'FINAL_REPORT_PACKAGE_VERSION_CHANGED')
    raw = source.read(directory / 'original-plan.json')
    require(source.digest(raw) == context['plan_sha256'], 'ORIGINAL_PLAN_CHANGED')
    doc = plan(raw); manifest = directory / 'ingress.json'; pin = context['manifest_sha256']
    load_manifest(manifest, pin, directory / 'originals')
    # load_manifest verifies all source bytes. Section identities and order are
    # rederived from the original plan; no extra or missing section is accepted.
    require({p.name for p in (directory / 'sections').iterdir()} ==
            {str(i).zfill(3) for i in range(len(doc['sections']))}, 'SECTION_SET_CHANGED')
    pieces = ['# Final supplied-source research report\n\n'
              'Replayed local evidence and generated statements; source authenticity, request completeness and investment correctness are not certified.\n\n']
    sections = []; canonical_sections = []
    for index, section in enumerate(doc['sections']):
        section_dir = directory / 'sections' / str(index).zfill(3)
        body, checked = (replay_conclusion(section, section_dir, doc, manifest, pin)
                         if section['kind'] == 'objective_conclusion' else
                         replay_section(section, section_dir, manifest, pin))
        # Readiness is execution of the declared operation, not its economic
        # outcome. Unknown EPS, unsupported DCF and negative returns are findings.
        # Never infer or insert a role to make a rejected terminal input execute.
        if doc.get('output_contract') == STRICT and section['kind'] == 'terminal_objectives':
            require(checked['job_status'] == 'COMPUTED',
                    'STRICT_TERMINAL_PREPARATION_NOT_READY: section ' + str(index) +
                    '; job status ' + checked['job_status'])
        pieces.append('## Section ' + str(index + 1) + '\n\n' + body.rstrip() + '\n\n')
        sections.append(checked)
        if section['kind'] == 'objective_conclusion':
            result = checked
            producer = 'replayed_objective_conclusion'
        else:
            is_source = section['kind'] in ('source_report', 'source_claim', 'issuer_facts')
            name = 'producer/result.json' if is_source else 'workflow/result.json'
            result_raw = source.read(section_dir / name)
            require(source.digest(result_raw) == checked['result_sha256'], 'SECTION_RESULT_CHANGED_AFTER_REPLAY')
            result = parse(result_raw)
            producer = producer_request(section)['producer'] if is_source else 'financial.terminal_scenarios'
        canonical_sections.append({'section_index': index, 'kind': section['kind'], 'producer_or_operation': producer,
            'input_request': section, 'request_sha256': source.digest(encoded(section)),
            'evidence_audit': checked, 'result': result})
    spans = []
    if 'unverified_prose' in doc:
        pieces.append('## Unaudited prose\n\nThe following text is not verified by the source, calculation or report checks.\n\n')
        start = len(''.join(pieces).encode('utf-8')); prose = doc['unverified_prose']
        spans.append({'start_byte': start, 'end_byte': start + len(prose.encode('utf-8')),
                      'sha256': source.digest(prose.encode('utf-8')), 'status': 'UNAUDITED_PROSE_NOT_CERTIFIED'})
        pieces.append(prose + '\n')
    final = ''.join(pieces).encode('utf-8')
    require(len(final) <= source.MAX_REPORT, 'FINAL_REPORT_TOO_LARGE')
    require(source.implementations() == context['implementation_sha256'], 'IMPLEMENTATION_CHANGED_DURING_FINAL_REPLAY')
    limitations = [{'code': 'LOCAL_REPLAY_NOT_SOURCE_AUTHENTICITY'}, {'code': 'REQUEST_COMPLETENESS_NOT_VERIFIED'},
                   {'code': 'INVESTMENT_CORRECTNESS_NOT_VERIFIED'}, {'code': 'REJECTED_UNKNOWN_DIAGNOSTIC_STATES_RETAINED'}]
    if spans: limitations.append({'code': 'UNAUDITED_PROSE_PRESENT'})
    canonical = {'schema_version': 1, 'method': 'final-analysis-1',
        'output_contract': doc.get('output_contract', LEGACY), 'candidate_version': context['candidate_version'],
        'plan_sha256': context['plan_sha256'],
        'manifest_sha256': pin, 'first_response_sha256': source.digest(final), 'sections': canonical_sections,
        'limitations': limitations, 'whole_report_semantic_pass': False, 'source_authenticity_verified': False,
        'request_completeness_verified': False, 'execution_authorized': False}
    analysis = encoded(canonical)
    require(len(analysis) <= source.MAX_FILE, 'CANONICAL_ANALYSIS_TOO_LARGE')
    audit = {'method': METHOD, 'status': 'PARTIAL_UNAUDITED_PROSE' if spans else 'FINAL_REPORT_REPLAY_AND_BYTES_MATCH',
             'response_file': RESPONSE, 'final_response_sha256': source.digest(final),
             'analysis_file': ANALYSIS, 'analysis_sha256': source.digest(analysis), 'output_contract': canonical['output_contract'],
             'plan_sha256': context['plan_sha256'], 'manifest_sha256': pin,
             'sections': sections, 'unverified_spans': spans, 'whole_report_semantic_pass': False,
             'source_authenticity_verified': False, 'request_completeness_verified': False, 'execution_authorized': False,
             'limits': ['Exact output consistency only; no independent authenticity, arbitrary prose grading or complete task coverage.',
                        'Partial, rejected and unknown producer findings remain partial, rejected and unknown.']}
    if 'objective_conclusion_required' in doc:
        audit['objective_conclusion_required'] = doc['objective_conclusion_required']
    if doc.get('output_contract') == STRICT:
        audit['readiness_policy'] = READINESS
    return final, analysis, audit


def replay(directory):
    """Compatibility interface; canonical structured output is replayed as well."""
    final, _, audit = _replay_artifacts(directory)
    return final, audit


def _prepared_inventory(directory):
    return {name: pin for name, pin in source.file_inventory(directory).items()
            if name not in FINAL_FILES and name != PREPARATION}


def _check_preparation(directory, final, analysis, audit, expected_pin=None):
    raw = source.read(directory / PREPARATION)
    require(expected_pin is None or source.digest(raw) == expected_pin, 'PREPARATION_PIN_CHANGED')
    saved = parse(raw)
    expected = {'method': 'final-preparation-1', 'status': 'PREPARED_FOR_FINALIZATION',
                'readiness_policy': READINESS, 'output_contract': audit['output_contract'],
                'final_response_sha256': source.digest(final), 'analysis_sha256': source.digest(analysis),
                'audit_sha256': source.digest(source.encode(audit)),
                'artifacts': _prepared_inventory(directory), 'whole_report_semantic_pass': False}
    require(saved == expected, 'PREPARATION_REPLAY_OR_ARTIFACTS_CHANGED')
    return raw


def prepare(plan_path, output_dir, manifest_path, expected_manifest_sha256, source_root=None):
    """Execute and replay a fresh preparation without writing a first response.

    Rejections retain workflow input/result/reason and failure.json. Correct the
    declared input in a new plan/directory; no existing preparation is promoted.
    """
    original = source.safe(plan_path); output = source.safe(output_dir); manifest = source.safe(manifest_path)
    root = source.safe(source_root) if source_root is not None else manifest.parent
    require(not output.exists() and not output.is_relative_to(source.ROOT) and
            not original.is_relative_to(output) and not manifest.is_relative_to(output), 'NEW_PRIVATE_OUTPUT_REQUIRED')
    output.mkdir(parents=True); stage = 'retain_plan'
    try:
        raw = source.read(original); source.write(output, 'original-plan.json', raw); doc = plan(raw)
        stage = 'retain_complete_original_corpus'
        retain_corpus(output, manifest, expected_manifest_sha256, root)
        context = {'method': METHOD, 'plan_sha256': source.digest(raw), 'manifest_sha256': expected_manifest_sha256,
                   'implementation_sha256': source.implementations(),
                   'candidate_version': source.read(source.ROOT / 'VERSION').decode('utf-8').strip(),
                   'version_sha256': source.digest(source.read(source.ROOT / 'VERSION'))}
        source.write(output, 'context.json', source.encode(context)); (output / 'sections').mkdir()
        for index, section in enumerate(doc['sections']):
            stage = 'section_' + str(index)
            make_section(section, output / 'sections' / str(index).zfill(3), output / 'ingress.json',
                         expected_manifest_sha256, output / 'originals')
        stage = 'source_calculation_and_final_report_replay'
        final, analysis, audit = _replay_artifacts(output)
        receipt = {'method': 'final-preparation-1', 'status': 'PREPARED_FOR_FINALIZATION',
                   'readiness_policy': READINESS, 'output_contract': audit['output_contract'],
                   'final_response_sha256': source.digest(final), 'analysis_sha256': source.digest(analysis),
                   'audit_sha256': source.digest(source.encode(audit)),
                   'artifacts': _prepared_inventory(output), 'whole_report_semantic_pass': False}
        raw_preparation = source.encode(receipt)
        source.write(output, PREPARATION, raw_preparation)
        require(source.read(output / PREPARATION) == raw_preparation and
                _prepared_inventory(output) == receipt['artifacts'], 'PREPARATION_CHANGED_DURING_WRITE')
        return {**receipt, 'preparation_sha256': source.digest(raw_preparation)}
    except Exception as exc:
        source.write(output, 'failure.json', source.encode({'method': METHOD, 'status': 'FAILED_RETAINED_PARTIAL',
                     'stage': stage, 'error_type': type(exc).__name__, 'error': str(exc), 'whole_report_semantic_pass': False}))
        raise


def finalize(directory, expected_preparation_sha256):
    """Replay the exact pinned preparation before its first final artifact write."""
    directory = source.safe(directory)
    require(not directory.is_relative_to(source.ROOT), 'PRIVATE_PREPARATION_REQUIRED')
    require(isinstance(expected_preparation_sha256, str) and
            re.fullmatch('[0-9a-f]{64}', expected_preparation_sha256), 'EXTERNAL_PREPARATION_PIN_REQUIRED')
    require(not any((directory / name).exists() for name in FINAL_FILES) and
            not (directory / 'failure.json').exists(), 'UNFINALIZED_SUCCESSFUL_PREPARATION_REQUIRED')
    # Check the caller's reviewed preparation before potentially costly replay.
    require(source.digest(source.read(directory / PREPARATION)) == expected_preparation_sha256,
            'PREPARATION_PIN_CHANGED')
    final, analysis, audit = _replay_artifacts(directory)
    raw_preparation = _check_preparation(directory, final, analysis, audit, expected_preparation_sha256)
    context = parse(source.read(directory / 'context.json'))
    source.write(directory, RESPONSE, final); source.write(directory, ANALYSIS, analysis)
    source.write(directory, 'audit.json', source.encode(audit))
    require(source.read(directory / RESPONSE, source.MAX_REPORT) == final and
            source.read(directory / ANALYSIS) == analysis and
            source.read(directory / PREPARATION) == raw_preparation and
            _prepared_inventory(directory) == parse(raw_preparation)['artifacts'], 'FINALIZATION_INPUT_OR_OUTPUT_CHANGED')
    receipt = {**audit, 'implementation_sha256': context['implementation_sha256'],
               'context_sha256': source.digest(source.read(directory / 'context.json')),
               'audit_sha256': source.digest(source.read(directory / 'audit.json')),
               'artifacts': source.file_inventory(directory)}
    source.write(directory, 'receipt.json', source.encode(receipt)); return receipt


def compose(plan_path, output_dir, manifest_path, expected_manifest_sha256, source_root=None):
    """Normal one-call route: prepare, then finalize only if preparation succeeds."""
    prepared = prepare(plan_path, output_dir, manifest_path, expected_manifest_sha256, source_root)
    return finalize(output_dir, prepared['preparation_sha256'])


def verify(directory, final_response_path=None, structured_analysis_path=None, expected_output_contract=None):
    directory = source.safe(directory); receipt = parse(source.read(directory / 'receipt.json'))
    require(receipt['method'] == METHOD and receipt['status'] in ('FINAL_REPORT_REPLAY_AND_BYTES_MATCH', 'PARTIAL_UNAUDITED_PROSE')
            and receipt['response_file'] == RESPONSE and receipt['whole_report_semantic_pass'] is False, 'FINAL_RECEIPT_REQUIRED')
    require(receipt['artifacts'] == source.file_inventory(directory), 'FINAL_ARTIFACT_SET_OR_BYTES_CHANGED')
    final, analysis, audit = _replay_artifacts(directory)
    # Legacy artifact replay remains available under its pinned implementation.
    # New strict outputs cannot omit the preparation checkpoint to bypass it.
    if audit['output_contract'] == STRICT or (directory / PREPARATION).exists():
        _check_preparation(directory, final, analysis, audit)
    require(source.read(directory / RESPONSE, source.MAX_REPORT) == final, 'FINAL_RESPONSE_BYTES_MISMATCH')
    require(source.read(directory / ANALYSIS) == analysis, 'CANONICAL_ANALYSIS_MISMATCH')
    if expected_output_contract is not None:
        require(expected_output_contract in (LEGACY, STRICT) and audit['output_contract'] == expected_output_contract,
                'REQUIRED_OUTPUT_CONTRACT_MISMATCH')
    require(source.encode(audit) == source.read(directory / 'audit.json'), 'FINAL_AUDIT_CHANGED')
    context = parse(source.read(directory / 'context.json'))
    expected = {**audit, 'implementation_sha256': context['implementation_sha256'],
                'context_sha256': source.digest(source.read(directory / 'context.json')),
                'audit_sha256': source.digest(source.read(directory / 'audit.json')), 'artifacts': source.file_inventory(directory)}
    require(source.encode(expected) == source.read(directory / 'receipt.json'), 'FINAL_RECEIPT_REPLAY_MISMATCH')
    if final_response_path is not None:
        require(source.read(final_response_path, source.MAX_REPORT) == final, 'PUBLISHED_RESPONSE_DIFFERS')
    if structured_analysis_path is not None:
        require(source.read(structured_analysis_path) == analysis, 'PUBLISHED_ANALYSIS_DIFFERS')
    return audit


def response_metadata(raw):
    """Only participant identity/environment declarations; no analytic overrides."""
    value = parse(raw)
    fields(value, {'case_id', 'runtime_model_metadata'}, {'execution_limitations', 'evidence_paths'})
    require(isinstance(value['case_id'], str) and re.fullmatch(r'[A-Za-z0-9_.-]{1,128}', value['case_id']),
            'BOUNDED_DECLARED_ID_REQUIRED')
    runtime = value['runtime_model_metadata']
    fields(runtime, {'model', 'effort'}, {'python', 'model_identity_status'})
    require(all(isinstance(v, str) and 0 < len(v) <= 128 and not any(ord(c) < 32 for c in v)
                for v in runtime.values()), 'BOUNDED_RUNTIME_METADATA_REQUIRED')
    if 'model_identity_status' in runtime:
        require(runtime['model_identity_status'] in ('UNKNOWN', 'PARTICIPANT_REPORTED', 'HOST_EXPOSED'),
                'RUNTIME_IDENTITY_STATUS_REQUIRED')
    limits = value.get('execution_limitations', [])
    require(isinstance(limits, list) and len(limits) <= 32, 'BOUNDED_ENVIRONMENT_LIMITS_REQUIRED')
    codes = {'MEMORY_CONTEXT_AVAILABLE', 'MODEL_IDENTITY_UNEXPOSED', 'CAPTURE_INCOMPLETE',
             'RUNTIME_DIFFERENCE', 'OTHER_UNVERIFIED_ENVIRONMENT'}
    for row in limits:
        fields(row, {'code'}, {'detail'})
        require(row['code'] in codes, 'ENVIRONMENT_LIMIT_CODE_REQUIRED')
        require('detail' not in row or isinstance(row['detail'], str) and 0 < len(row['detail']) <= 2048,
                'BOUNDED_UNVERIFIED_ENVIRONMENT_DETAIL_REQUIRED')
    references = value.get('evidence_paths', [])
    require(isinstance(references, list) and len(references) <= 256, 'BOUNDED_EVIDENCE_REFERENCES_REQUIRED')
    for row in references:
        fields(row, {'path', 'sha256'})
        source.relative(row['path'])
        require(isinstance(row['sha256'], str) and re.fullmatch('[0-9a-f]{64}', row['sha256']), 'EVIDENCE_HASH_REQUIRED')
    require(len({row['path'] for row in references}) == len(references), 'UNIQUE_EVIDENCE_REFERENCES_REQUIRED')
    return value


def _response_projection(report_directory, metadata_raw):
    receipt_raw = source.read(report_directory / 'receipt.json')
    audit = verify(report_directory, expected_output_contract=STRICT)
    require(source.read(report_directory / 'receipt.json') == receipt_raw, 'REPORT_RECEIPT_CHANGED_DURING_PROJECTION')
    metadata = response_metadata(metadata_raw)
    analysis_raw = source.read(report_directory / ANALYSIS)
    require(source.digest(analysis_raw) == audit['analysis_sha256'], 'ANALYSIS_CHANGED_AFTER_VERIFICATION')
    analysis = parse(analysis_raw)
    require(analysis['output_contract'] == STRICT and not audit['unverified_spans'], 'STRICT_RESPONSE_REQUIRED')
    ingress_raw = source.read(report_directory / 'ingress.json')
    require(source.digest(ingress_raw) == audit['manifest_sha256'], 'INGRESS_CHANGED_AFTER_VERIFICATION')
    original = parse(ingress_raw)
    association = {'first_response_sha256': audit['final_response_sha256'],
                   'analysis_sha256': source.digest(analysis_raw),
                   'report_receipt_sha256': source.digest(receipt_raw)}
    result = {'schema_version': 1, 'method': ENVELOPE_METHOD, 'case_id': metadata['case_id'],
        'candidate_version': analysis['candidate_version'], 'status': 'GENERATED_FROM_REPLAYED_SECTIONS',
        'output_contract': STRICT, 'input_hashes': {row['path']: row['sha256'] for row in original['sources']},
        'rows': analysis['sections'], 'limitations': analysis['limitations'],
        'runtime_model_metadata': metadata['runtime_model_metadata'],
        'execution_limitations': metadata.get('execution_limitations', []), 'evidence_paths': metadata.get('evidence_paths', []),
        'metadata_status': 'PARTICIPANT_DECLARATIONS_AND_EXTERNAL_REFERENCES_NOT_VERIFIED',
        'artifact_association': association, 'whole_report_semantic_pass': False,
        'source_authenticity_verified': False, 'request_completeness_verified': False, 'execution_authorized': False}
    raw = encoded(result)
    require(len(raw) <= source.MAX_FILE, 'STRUCTURED_RESPONSE_TOO_LARGE')
    envelope = {'method': ENVELOPE_METHOD, 'status': 'COMPLETED_CANONICAL_RESPONSE_EXPORT',
        'response_file': 'response.json', 'response_sha256': source.digest(raw), **association,
        'metadata_sha256': source.digest(metadata_raw), 'output_contract': STRICT,
        'whole_report_semantic_pass': False, 'source_authenticity_verified': False,
        'request_completeness_verified': False, 'execution_authorized': False}
    require(source.read(report_directory / 'receipt.json') == receipt_raw and
            source.file_inventory(report_directory) == parse(receipt_raw)['artifacts'],
            'REPORT_CHANGED_DURING_PROJECTION')
    return raw, envelope


def export_response(report_directory, metadata_path, output_directory):
    """Retain a portable report and generate response rows; never merge caller data."""
    report = source.safe(report_directory); metadata = source.safe(metadata_path); output = source.safe(output_directory)
    require(not output.exists() and not output.is_relative_to(source.ROOT) and not report.is_relative_to(output) and
            not output.is_relative_to(report) and not metadata.is_relative_to(output), 'NEW_PRIVATE_RESPONSE_OUTPUT_REQUIRED')
    output.mkdir(parents=True); stage = 'validate_report_and_metadata'
    try:
        raw_metadata = source.read(metadata); response_metadata(raw_metadata)
        source.write(output, 'original-metadata.json', raw_metadata)
        verify(report, expected_output_contract=STRICT)
        before = source.file_inventory(report) | {'receipt.json': source.digest(source.read(report / 'receipt.json'))}
        stage = 'retain_portable_report'
        for name, digest in before.items():
            source.relative(name); raw = source.read(report / name)
            require(source.digest(raw) == digest, 'REPORT_CHANGED_DURING_EXPORT')
            source.write(output, 'report/' + name, raw)
        require(before == source.file_inventory(report) | {'receipt.json': source.digest(source.read(report / 'receipt.json'))},
                'REPORT_CHANGED_DURING_EXPORT')
        stage = 'canonical_response_replay'
        raw, receipt = _response_projection(output / 'report', raw_metadata)
        source.write(output, 'response.json', raw)
        require(source.read(output / 'original-metadata.json') == raw_metadata and
                source.read(output / 'response.json') == raw, 'RESPONSE_CHANGED_DURING_EXPORT')
        receipt['artifacts'] = source.file_inventory(output)
        source.write(output, 'receipt.json', source.encode(receipt))
        require(source.read(output / 'receipt.json') == source.encode(receipt) and
                source.file_inventory(output) == receipt['artifacts'], 'RESPONSE_EXPORT_COMMIT_CHANGED')
        return receipt
    except Exception as exc:
        source.write(output, 'failure.json', source.encode({'method': ENVELOPE_METHOD, 'status': 'FAILED_RETAINED_PARTIAL',
            'stage': stage, 'error_type': type(exc).__name__, 'error': str(exc), 'whole_report_semantic_pass': False}))
        raise


def verify_response(directory, published_response_path=None):
    """Replay retained report and regenerate the exact structured response."""
    directory = source.safe(directory)
    receipt = parse(source.read(directory / 'receipt.json'))
    require(receipt.get('method') == ENVELOPE_METHOD and receipt.get('status') == 'COMPLETED_CANONICAL_RESPONSE_EXPORT' and
            receipt.get('whole_report_semantic_pass') is False and receipt.get('output_contract') == STRICT,
            'CANONICAL_RESPONSE_RECEIPT_REQUIRED')
    require(receipt['artifacts'] == source.file_inventory(directory), 'RESPONSE_ARTIFACT_SET_OR_BYTES_CHANGED')
    raw, expected = _response_projection(directory / 'report', source.read(directory / 'original-metadata.json'))
    require(source.read(directory / 'response.json') == raw, 'CANONICAL_RESPONSE_PROJECTION_MISMATCH')
    expected['artifacts'] = source.file_inventory(directory)
    require(source.encode(expected) == source.read(directory / 'receipt.json'), 'RESPONSE_RECEIPT_REPLAY_MISMATCH')
    if published_response_path is not None:
        require(source.read(published_response_path) == raw, 'PUBLISHED_STRUCTURED_RESPONSE_DIFFERS')
    return expected


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__); sub = parser.add_subparsers(dest='mode', required=True)
    for mode in ('compose', 'prepare'):
        p = sub.add_parser(mode); p.add_argument('plan'); p.add_argument('--manifest', required=True)
        p.add_argument('--manifest-sha256', required=True); p.add_argument('--source-root'); p.add_argument('--output', required=True)
    p = sub.add_parser('finalize'); p.add_argument('directory'); p.add_argument('--preparation-sha256', required=True)
    p = sub.add_parser('verify'); p.add_argument('directory'); p.add_argument('--final-response')
    p.add_argument('--structured-analysis'); p.add_argument('--require-output-contract', choices=(STRICT, LEGACY))
    p = sub.add_parser('response'); p.add_argument('report'); p.add_argument('--metadata', required=True); p.add_argument('--output', required=True)
    p = sub.add_parser('verify-response'); p.add_argument('directory'); p.add_argument('--published-response')
    args = parser.parse_args(argv)
    try:
        if args.mode == 'compose': result = compose(args.plan, args.output, args.manifest, args.manifest_sha256, args.source_root)
        elif args.mode == 'prepare': result = prepare(args.plan, args.output, args.manifest, args.manifest_sha256, args.source_root)
        elif args.mode == 'finalize': result = finalize(args.directory, args.preparation_sha256)
        elif args.mode == 'verify': result = verify(args.directory, args.final_response, args.structured_analysis, args.require_output_contract)
        elif args.mode == 'response': result = export_response(args.report, args.metadata, args.output)
        else: result = verify_response(args.directory, args.published_response)
        print(source.encode(result).decode(), end=''); return 0
    except (ValueError, OSError, KeyError, TypeError, ImportError) as exc:
        print(json.dumps({'status': 'FAILED', 'error': str(exc), 'whole_report_semantic_pass': False})); return 1


if __name__ == '__main__':
    sys.exit(main())
