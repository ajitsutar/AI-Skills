"""Run the existing analyst evidence helper and export its local, pointer-bound report.

Accepts an analyst_evidence request, or {cohorts: [{cohort_id, request}],
supplemental_evidence: [{kind, record, as_of?}]}. Supplemental kinds are fair_value,
historical_range, source_discovery and information_coverage; they never enter a
target calculation. No source extraction, network access or publisher verification.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import analyst_evidence
from price_comparison import compare_prices
from news_analysis import evidence
from news_sources import stamp
from report_facts import (ROOT, Projector, code_hash, digest, escape, leaves,
                          local_path, markdown, pointer, strict_json)

VERSION = 'analyst-report-1'
SUPPLEMENTAL = {'fair_value', 'historical_range', 'source_discovery', 'information_coverage'}
CONSENSUS = {
    'status': ('Observed target cohort status', 'status'),
    'independent_firms': ('Observed distinct firm count; statistical independence unestablished', 'count'),
    'mean': ('Observed forward target mean', 'input_currency_per_share'),
    'median': ('Observed forward target median', 'input_currency_per_share'),
    'minimum': ('Observed forward target minimum', 'input_currency_per_share'),
    'maximum': ('Observed forward target maximum', 'input_currency_per_share'),
    'q1': ('Observed forward target first quartile', 'input_currency_per_share'),
    'q3': ('Observed forward target third quartile', 'input_currency_per_share'),
    'iqr_over_median': ('Forward target IQR divided by median', 'ratio'),
    'quote_status': ('Supporting quote age status', 'status'),
    'quote_published_at': ('Supporting quote publication time', 'timestamp'),
    'median_implied_price_change_formula': ('Median target price change formula', 'formula'),
    'median_implied_price_change_denominator': ('Median target price change denominator: quote', 'input_currency_per_share'),
    'median_implied_price_change_meaning': ('Median target price change meaning', 'definition'),
    'median_implied_price_change_pct': ('Median target implied price change; excludes dividends and costs', 'percent')}
TRACK_FIELDS = ('analyst_id', 'firm_id', 'provider', 'evaluation_start', 'evaluation_end',
                'holding_rule', 'benchmark', 'return_definition', 'success_definition',
                'methodology_url', 'recommendation_count', 'success_rate_pct', 'average_return_pct')


def canonical_bytes(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False,
                      allow_nan=False).encode('utf-8')


def _requests(document):
    if not isinstance(document, dict):
        raise ValueError('JSON_OBJECT_REQUIRED')
    if 'cohorts' not in document:
        return [('default', document, '/input')], []
    if set(document) - {'cohorts', 'supplemental_evidence', 'price_comparisons'}:
        raise ValueError('UNSUPPORTED_ENVELOPE_FIELD')
    cohorts = document['cohorts']
    supplemental = document.get('supplemental_evidence', [])
    if not isinstance(cohorts, list) or not isinstance(supplemental, list):
        raise ValueError('COHORT_AND_SUPPLEMENTAL_LISTS_REQUIRED')
    requests, identifiers = [], set()
    for i, cohort in enumerate(cohorts):
        if (not isinstance(cohort, dict) or set(cohort) != {'cohort_id', 'request'}
                or not isinstance(cohort['cohort_id'], str) or not cohort['cohort_id']
                or not isinstance(cohort['request'], dict)):
            raise ValueError('COHORT_ID_AND_REQUEST_REQUIRED')
        if cohort['cohort_id'] in identifiers:
            raise ValueError('DUPLICATE_COHORT_ID')
        identifiers.add(cohort['cohort_id'])
        requests.append((cohort['cohort_id'], cohort['request'], f'/input/cohorts/{i}/request'))
    return requests, supplemental


def run(raw, source_root):
    """Compute from explicit inputs, preserving the exact helper output unchanged."""
    document = strict_json(raw)
    requests, supplemental = _requests(document)
    source_root = local_path(source_root)
    artifact = {'input': document, 'cohorts': [], 'supplemental_evidence': []}
    for identifier, request, path in requests:
        for field in ('individual_targets', 'provider_consensus', 'analyst_track_records', 'source_discovery'):
            if field in request and (not isinstance(request[field], list) or
                                     any(not isinstance(row, dict) for row in request[field])):
                raise ValueError('RECORD_OBJECT_LIST_REQUIRED')
        result = analyst_evidence.review(request, source_root)
        artifact['cohorts'].append({'cohort_id': identifier, 'request_pointer': path,
                                    'request_sha256': digest(request),
                                    'result_sha256': digest(result), 'result': result})
    for i, item in enumerate(supplemental):
        if (not isinstance(item, dict) or set(item) - {'kind', 'record', 'as_of'}
                or item.get('kind') not in SUPPLEMENTAL or not isinstance(item.get('record'), dict)):
            raise ValueError('TYPED_SUPPLEMENTAL_RECORD_REQUIRED')
        checked = {'input_pointer': f'/input/supplemental_evidence/{i}', 'kind': item['kind'],
                   'status': 'SUPPLIED_ONLY', 'evidence_check': 'SOURCE_OR_CUTOFF_MISSING'}
        if item['record'].get('source') and item.get('as_of'):
            try:
                evidence(item['record']['source'], source_root, stamp(item['as_of']))
                checked.update(status='LOCAL_EVIDENCE_CONSISTENT', evidence_check=None)
            except (ValueError, KeyError, TypeError, AttributeError, OSError, OverflowError) as exc:
                checked.update(status='EVIDENCE_CHECK_FAILED', evidence_check=str(exc))
        artifact['supplemental_evidence'].append(checked)

    if 'price_comparisons' in document:
        comparisons = document['price_comparisons']
        if not isinstance(comparisons, list) or any(not isinstance(item, dict) or
            set(item) - {'quote', 'references', 'conditional_same_basis'} for item in comparisons):
            raise ValueError('EXPLICIT_PRICE_COMPARISON_ARGUMENT_LIST_REQUIRED')
        artifact['price_comparisons'] = [compare_prices(**item) for item in comparisons]

    projection = Projector(canonical_bytes(artifact), 'analyst', include_source_text=True)

    def add(path, label, *, role, context=None, horizon=None, unit=None, mapping='HELPER_RESULT',
            metadata=None, basis=None, denominator=None):
        fact = projection.fact(path, label, unit=unit, horizon=horizon, mapping=mapping, denominator=denominator,
                               metadata_sources=metadata, basis=basis,
                               context={'evidence_role': role, **(context or {})},
                               assumptions=['Supplied extraction and attribution are not authenticated.'])
        fact['horizon_role'] = ('explicit forward-target cohort contract' if role in
                                ('observed_forward_targets', 'included_target') else
                                'supplied record horizon; no conversion to expected return')
        return fact

    def fields(base, record, *, role, context, horizon=None, required=(), mapping='HELPER_RESULT'):
        seen = set()
        for path, value in leaves(record, base):
            if path.rsplit('/', 1)[-1] in ('execution_authorized', 'strong_buy_available'):
                continue
            seen.add(path)
            if role == 'typed_price_comparison' and path.endswith('/value') and any(
                    '/' + metric + '/value' in path for metric in
                    ('quote_discount_relative_to_reference_pct', 'price_change_from_quote_to_reference_pct')):
                parent = path.rsplit('/', 1)[0]
                add(path, role + ': ' + path[len(base) + 1:], role=role, context=context,
                    unit='percent', horizon=horizon, mapping=mapping,
                    denominator=pointer(artifact, parent + '/denominator_operand_id'),
                    basis=pointer(artifact, parent + '/meaning'),
                    metadata={'formula': parent + '/formula', 'denominator_value': parent + '/denominator_value'})
            else:
                add(path, role + ': ' + path[len(base) + 1:], role=role, context=context,
                    horizon=horizon, mapping=mapping)
        for key in required:
            path = base + '/' + '/'.join(escape(part) for part in key.split('/'))
            if not any(existing == path or existing.startswith(path + '/') for existing in seen):
                add(path, role + ': ' + key, role=role, context=context, horizon=horizon, mapping=mapping)

    for i, (identifier, request, input_base) in enumerate(requests):
        cohort = artifact['cohorts'][i]
        result, base = cohort['result'], f'/cohorts/{i}/result'
        context = {'cohort_id': identifier, 'as_of': result['as_of'],
                   'cohort_issuer': request['issuer'], 'cohort_currency': request['currency'],
                   'cohort_price_basis': request['price_basis'], 'input_pointer': input_base}
        horizon = result['target_horizon']
        for key in ('as_of', 'target_horizon', 'coverage', 'numeric_extraction'):
            add(base + '/' + key, 'Cohort ' + key, role='observed_forward_targets',
                context=context, horizon=horizon)
        add(base + '/consensus/firm_count_meaning', 'Firm identity count meaning',
            role='population_scoped_source_lineage', context={**context, 'source_population': 'individual_targets_used'},
            horizon=horizon)
        for key, (label, unit) in CONSENSUS.items():
            fact = add(base + '/consensus/' + key, label, role='observed_forward_targets',
                       context=context, horizon=horizon, unit=unit,
                       metadata={k: input_base + '/' + k for k in
                                 ('as_of', 'issuer', 'currency', 'price_basis', 'target_horizon')},
                       basis='latest admissible target per firm; observed sources only')
            if key == 'iqr_over_median':
                fact['denominator'] = 'median target'
            elif key == 'median_implied_price_change_pct':
                fact['denominator'] = 'same-basis supplied quote price'
            if fact['denominator'] is not None:
                fact['unknown_metadata'].remove('denominator')
        for name, role, required in (
                ('individual_targets_used', 'included_target', ()),
                ('excluded', 'excluded_target', ('record_id', 'reason')),
                ('provider_consensus', 'separate_provider_pool',
                 ('provider', 'as_of', 'target_horizon', 'mean', 'median', 'minimum', 'maximum', 'target_count', 'analyst_count')),
                ('source_population_provenance', 'population_scoped_source_lineage',
                 ('source_population', 'entity_identity_field', 'statistical_independence', 'shared_research_data_or_assumptions', 'other_population_provenance_inferred')),
                ('analyst_track_records', 'provider_reported_track_record', TRACK_FIELDS),
                ('source_discovery', 'supplied_source_discovery', ('access',))):
            for j, row in enumerate(result[name]):
                fields(f'{base}/{name}/{j}', row, role=role,
                       context={**context, 'row_index': j, 'source_population': row.get('source_population', name)},
                       horizon=row.get('target_horizon'), required=required,
                       mapping='SUPPLIED_DISCOVERY_RECORD' if name == 'source_discovery' else 'HELPER_RESULT')
        # The helper's exclusions reference IDs; retain every original row, including
        # missing or duplicate IDs, without guessing which record an ID identifies.
        for j, row in enumerate(request.get('individual_targets', [])):
            fields(f'{input_base}/individual_targets/{j}', row, role='supplied_target_before_filtering',
                   context={**context, 'row_index': j}, horizon=row.get('target_horizon'),
                   mapping='SUPPLIED_RECORD')
        fields(input_base + '/quote', request.get('quote') or {}, role='supplied_quote',
               context=context, required=('price', 'source/published_at'), mapping='SUPPLIED_RECORD')
    for i, item in enumerate(supplemental):
        context = {'supplemental_index': i, 'evidence_check_pointer': f'/supplemental_evidence/{i}',
                   'included_in_target_calculation': False}
        required = {'fair_value': ('value', 'currency', 'price_basis', 'share_basis', 'adjustment_basis', 'security_id', 'as_of', 'methodology'),
                    'historical_range': ('low', 'high', 'currency', 'price_basis', 'share_basis', 'adjustment_basis', 'security_id', 'period_start', 'period_end'),
                    'source_discovery': ('access', 'url', 'published_at', 'observed_at'),
                    'information_coverage': ('topic', 'status', 'source')}[item['kind']]
        fields(f'/input/supplemental_evidence/{i}/record', item['record'], role=item['kind'],
               context=context, horizon=item['record'].get('target_horizon'), required=required,
               mapping='SUPPLIED_CONTEXT_NOT_TARGET_CONSENSUS')
        fields(f'/supplemental_evidence/{i}', artifact['supplemental_evidence'][i],
               role='supplemental_evidence_check', context=context)
    for i, comparison in enumerate(artifact.get('price_comparisons', [])):
        fields(f'/price_comparisons/{i}', comparison, role='typed_price_comparison',
               context={'comparison_index': i, 'included_in_target_calculation': False},
               mapping='TYPED_PRICE_COMPARISON_RESULT')
    return {'schema_version': 1, 'adapter_version': VERSION, 'kind': 'analyst',
            'input_file_sha256': hashlib.sha256(raw).hexdigest(), 'artifact': artifact,
            'source_artifact_sha256': projection.hash, 'source_text_exported': True,
            'adapter_code_sha256': code_hash('analyst_report.py'),
            'semantics_code_sha256': {name: code_hash(name) for name in
                                     ('analyst_evidence.py', 'price_comparison.py', 'evidence_semantics.py', 'news_analysis.py', 'news_sources.py', 'report_facts.py')},
            'checks': [{'helper_executed': bool(requests), 'cohorts_computed': len(requests),
                        'source_authenticity_verified': False}], 'facts': projection.facts,
            'limits': ['Helper results were computed from explicit supplied records; no new extraction or research.',
                       'Fact pointers resolve inside bundle.json artifact; artifact hash uses canonical JSON UTF-8.',
                       'Local hashes/excerpts establish byte consistency, not publisher authenticity or correct extraction.',
                       'Observed forward targets, separate provider pools, fair value and historical ranges remain distinct.',
                       'Provider discrepancies remain unresolved; no constituent reconciliation or provider-pool averaging is performed.',
                       'Performance remains provider-reported; no reputation weight, expected return or analyst skill is inferred.',
                       'Missing evidence remains missing; this report neither searches sources nor validates a separate narrative.',
                       'The private bundle includes supplied source text. No publication, broker action or execution permission is implied.']}


def render(report):
    return markdown(report).replace(
        'Report facts (local projection; no computation or source authentication).',
        'Analyst evidence report (existing helper executed; no source authentication).', 1)


def export(report, output):
    output = local_path(output)
    if output.is_relative_to(ROOT):
        raise ValueError('OUTPUT_OUTSIDE_SKILL_REQUIRED')
    rendered = {'bundle.json': json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False) + '\n',
                'report.md': render(report)}
    output.mkdir()  # New directory only: never overwrite a prior evidence/report bundle.
    created = []
    try:
        for name, contents in rendered.items():
            path = output / name
            with path.open('x', encoding='utf-8', newline='\n') as handle:
                created.append(path)
                handle.write(contents)
    except OSError:
        for path in created:
            path.unlink(missing_ok=True)
        output.rmdir()
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input')
    parser.add_argument('source_root')
    parser.add_argument('--private-output', required=True, help='New local directory outside the skill; contains source text.')
    args = parser.parse_args()
    try:
        export(run(local_path(args.input).read_bytes(), args.source_root), args.private_output)
    except (ValueError, KeyError, TypeError, AttributeError, IndexError, OSError, OverflowError):
        parser.exit(2, 'Analyst report failed: invalid input/evidence/path or existing output. Source values were not printed.\n')


if __name__ == '__main__':
    main()
