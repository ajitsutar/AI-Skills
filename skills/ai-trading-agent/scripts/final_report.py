"""Compose fixed offline research reports and bind the exact final response.

Replay is local consistency, not source authenticity or arbitrary-prose grading.
Only new private directories are written; verify is read-only.
"""
from pathlib import Path
import argparse
import json
import sys

import handoff_report as exact_json
import supplied_research as source
from source_lineage import load_manifest, parse

METHOD = 'final-report-1'
RESPONSE = 'first-response.md'
MAX_SECTIONS = 8
MAX_PROSE = 128 * 1024
require = source.require


def encoded(value):
    """Retain Decimal numeric types in derived requests, not string metadata."""
    return (exact_json.encode(value) + '\n').encode('utf-8')


def fields(value, required, optional=()):
    require(isinstance(value, dict) and set(required) <= set(value) <= set(required) | set(optional),
            'EXACT_PLAN_OR_SECTION_FIELDS_REQUIRED')


def plan(raw):
    doc = parse(raw)
    fields(doc, {'sections'}, {'unverified_prose'})
    require(isinstance(doc['sections'], list) and 0 < len(doc['sections']) <= MAX_SECTIONS,
            'BOUNDED_NONEMPTY_SECTIONS_REQUIRED')
    for row in doc['sections']:
        require(isinstance(row, dict), 'SECTION_OBJECT_REQUIRED')
        kind = row.get('kind')
        if kind == 'source_report':
            fields(row, {'kind', 'producer', 'request'})
            require(row['producer'] in source.PRODUCERS and isinstance(row['request'], dict),
                    'SUPPORTED_SOURCE_PRODUCER_REQUIRED')
        else:
            raise ValueError('UNSUPPORTED_SECTION_KIND')
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
    return {'producer': section['producer'], 'producer_request': section['request']}




def make_section(section, directory, manifest, pin, originals):
    directory.mkdir()
    request = directory / 'request.json'
    source.write(directory, 'request.json', encoded(producer_request(section)))
    source.run(request, directory / 'producer', manifest, pin, originals)


def replay_section(section, directory, manifest, pin):
    expected = encoded(producer_request(section))
    require(source.read(directory / 'request.json') == expected and
            source.read(directory / 'producer/original-request.json') == expected,
            'SECTION_REQUEST_DIFFERS_FROM_PLAN')
    require(source.read(directory / 'producer/ingress.json') == source.read(manifest), 'SECTION_CORPUS_DIFFERS')
    audit = source.verify(directory / 'producer')
    result_raw = source.read(directory / 'producer/result.json')
    result = parse(result_raw)
    body = source.read(directory / 'producer/report.md', source.MAX_REPORT).decode('utf-8')
    # Keep the complete fixed producer report, not chosen sentences. The
    # link is deterministically rebased when embedded in the final file.
    prefix = directory.name
    body = body.replace('[Complete structured evidence](result.json)',
                        '[Complete structured evidence](sections/' + prefix + '/producer/result.json)')
    return body, {'kind': section['kind'], 'source_audit': audit,
                  'result_sha256': source.digest(result_raw)}


def replay(directory):
    context = parse(source.read(directory / 'context.json'))
    require(context['method'] == METHOD and context['implementation_sha256'] == source.implementations(),
            'FINAL_REPORT_IMPLEMENTATION_CHANGED')
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
    sections = []
    for index, section in enumerate(doc['sections']):
        body, checked = replay_section(section, directory / 'sections' / str(index).zfill(3), manifest, pin)
        pieces.append('## Section ' + str(index + 1) + '\n\n' + body.rstrip() + '\n\n')
        sections.append(checked)
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
    audit = {'method': METHOD, 'status': 'PARTIAL_UNAUDITED_PROSE' if spans else 'FINAL_REPORT_REPLAY_AND_BYTES_MATCH',
             'response_file': RESPONSE, 'final_response_sha256': source.digest(final),
             'plan_sha256': context['plan_sha256'], 'manifest_sha256': pin,
             'sections': sections, 'unverified_spans': spans, 'whole_report_semantic_pass': False,
             'source_authenticity_verified': False, 'request_completeness_verified': False, 'execution_authorized': False,
             'limits': ['Exact output consistency only; no independent authenticity, arbitrary prose grading or complete task coverage.',
                        'Partial, rejected and unknown producer findings remain partial, rejected and unknown.']}
    return final, audit


def compose(plan_path, output_dir, manifest_path, expected_manifest_sha256, source_root=None):
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
                   'implementation_sha256': source.implementations()}
        source.write(output, 'context.json', source.encode(context)); (output / 'sections').mkdir()
        for index, section in enumerate(doc['sections']):
            stage = 'section_' + str(index)
            make_section(section, output / 'sections' / str(index).zfill(3), output / 'ingress.json',
                         expected_manifest_sha256, output / 'originals')
        stage = 'source_calculation_and_final_report_replay'
        final, audit = replay(output)
        source.write(output, RESPONSE, final); source.write(output, 'audit.json', source.encode(audit))
        require(source.read(output / RESPONSE, source.MAX_REPORT) == final, 'FINAL_RESPONSE_CHANGED_DURING_WRITE')
        receipt = {**audit, 'implementation_sha256': context['implementation_sha256'],
                   'context_sha256': source.digest(source.read(output / 'context.json')),
                   'audit_sha256': source.digest(source.read(output / 'audit.json')),
                   'artifacts': source.file_inventory(output)}
        source.write(output, 'receipt.json', source.encode(receipt)); return receipt
    except Exception as exc:
        source.write(output, 'failure.json', source.encode({'method': METHOD, 'status': 'FAILED_RETAINED_PARTIAL',
                     'stage': stage, 'error_type': type(exc).__name__, 'error': str(exc), 'whole_report_semantic_pass': False}))
        raise


def verify(directory, final_response_path=None):
    directory = source.safe(directory); receipt = parse(source.read(directory / 'receipt.json'))
    require(receipt['method'] == METHOD and receipt['status'] in ('FINAL_REPORT_REPLAY_AND_BYTES_MATCH', 'PARTIAL_UNAUDITED_PROSE')
            and receipt['response_file'] == RESPONSE and receipt['whole_report_semantic_pass'] is False, 'FINAL_RECEIPT_REQUIRED')
    require(receipt['artifacts'] == source.file_inventory(directory), 'FINAL_ARTIFACT_SET_OR_BYTES_CHANGED')
    final, audit = replay(directory)
    require(source.read(directory / RESPONSE, source.MAX_REPORT) == final, 'FINAL_RESPONSE_BYTES_MISMATCH')
    require(source.encode(audit) == source.read(directory / 'audit.json'), 'FINAL_AUDIT_CHANGED')
    context = parse(source.read(directory / 'context.json'))
    expected = {**audit, 'implementation_sha256': context['implementation_sha256'],
                'context_sha256': source.digest(source.read(directory / 'context.json')),
                'audit_sha256': source.digest(source.read(directory / 'audit.json')), 'artifacts': source.file_inventory(directory)}
    require(source.encode(expected) == source.read(directory / 'receipt.json'), 'FINAL_RECEIPT_REPLAY_MISMATCH')
    if final_response_path is not None:
        require(source.read(final_response_path, source.MAX_REPORT) == final, 'PUBLISHED_RESPONSE_DIFFERS')
    return audit


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__); sub = parser.add_subparsers(dest='mode', required=True)
    p = sub.add_parser('compose'); p.add_argument('plan'); p.add_argument('--manifest', required=True)
    p.add_argument('--manifest-sha256', required=True); p.add_argument('--source-root'); p.add_argument('--output', required=True)
    p = sub.add_parser('verify'); p.add_argument('directory'); p.add_argument('--final-response')
    args = parser.parse_args(argv)
    try:
        result = (compose(args.plan, args.output, args.manifest, args.manifest_sha256, args.source_root)
                  if args.mode == 'compose' else verify(args.directory, args.final_response))
        print(source.encode(result).decode(), end=''); return 0
    except (ValueError, OSError, KeyError, TypeError, ImportError) as exc:
        print(json.dumps({'status': 'FAILED', 'error': str(exc), 'whole_report_semantic_pass': False})); return 1


if __name__ == '__main__':
    sys.exit(main())
