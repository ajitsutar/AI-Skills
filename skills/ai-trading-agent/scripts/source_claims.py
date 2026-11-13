"""Offline source-presence, typed accounting and configured-corpus claim checks.

Identity, lexical presence and economic meaning are separate facts. The external
manifest pin is the trust boundary; no parser authenticates the source issuer.
"""
from __future__ import annotations

import argparse
from datetime import date
from decimal import Decimal
import hashlib
import json
import math
from pathlib import Path
import re

from source_lineage import at, load_manifest, parse


class ClaimError(ValueError):
    pass


def require(condition, code):
    if not condition:
        raise ClaimError(code)


def digest(value):
    return hashlib.sha256(value).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), default=str).encode()


def scalar_equal(first, second):
    if isinstance(first, bool) or isinstance(second, bool):
        return type(first) is type(second) and first == second
    if isinstance(first, (int, float, Decimal)) and isinstance(second, (int, float, Decimal)):
        return Decimal(str(first)) == Decimal(str(second))
    return type(first) is type(second) and first == second


def numeric(value):
    require(not isinstance(value, bool) and isinstance(value, (int, float, Decimal)),
            'SOURCE_NUMBER_REQUIRED')
    result = float(value)
    require(math.isfinite(result), 'FINITE_SOURCE_NUMBER_REQUIRED')
    return result


def analyst_numbers(value):
    """Adapt Decimal JSON tokens to the existing float-based analyst contract.

    Reject a conversion whose shortest decimal spelling changes the input value;
    do not silently drop a row or round its target to fit the downstream API.
    """
    if isinstance(value, Decimal):
        converted = float(value)
        require(math.isfinite(converted) and Decimal(str(converted)) == value,
                'ANALYST_NUMBER_PRECISION_UNSUPPORTED')
        return converted
    if isinstance(value, dict):
        return {key: analyst_numbers(child) for key, child in value.items()}
    if isinstance(value, list):
        return [analyst_numbers(child) for child in value]
    return value


def record_context(ref):
    """Identity of the structured object containing a scalar accounting field."""
    if not isinstance(ref, dict) or not isinstance(ref.get('pointer'), str) or not ref['pointer']:
        return None
    return (ref['source_id'], ref.get('start'), ref.get('end'), ref.get('excerpt'),
            ref['pointer'].rsplit('/', 1)[0])


def _walk(value, pointer=''):
    if isinstance(value, dict):
        for key, child in value.items():
            escaped = key.replace('~', '~0').replace('/', '~1')
            yield from _walk(child, pointer + '/' + escaped)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from _walk(child, pointer + '/' + str(index))
    else:
        yield pointer, value


def words(text):
    # Underscores and camel case are label separators, not accounting inference.
    text = re.sub(r'([a-z])([A-Z])', r'\1 \2', text)
    return re.findall(r'[^\W_]+', text.casefold(), re.UNICODE)


class Corpus:
    """Retain and verify all externally indexed source bytes before querying."""

    def __init__(self, manifest, pin, root=None):
        self.root = Path(root).resolve() if root else Path(manifest).resolve().parent
        self.pin = pin
        self.sources = load_manifest(manifest, pin, self.root)
        for source in self.sources.values():
            raw = (self.root / source['path']).read_bytes()
            require(digest(raw) == source['sha256'], 'SOURCE_CHANGED_DURING_INGRESS')
            source['raw'] = raw
            if source['format'] in ('text', 'json'):
                try:
                    source['text'] = raw.decode('utf-8-sig')
                except UnicodeDecodeError as exc:
                    raise ClaimError('UTF8_SOURCE_REQUIRED') from exc

    def resolve(self, ref):
        """A JSON leaf or exact UTF-8 decoded character span; no fuzzy matches.

        For JSON embedded in a text file, provide start/end/excerpt plus pointer.
        The whole explicitly selected span must parse as JSON, with duplicate-key
        and nonfinite checks inherited from source_lineage.
        """
        require(isinstance(ref, dict) and ref.get('source_id') in self.sources,
                'REFERENCE_OUTSIDE_PINNED_CORPUS')
        source = self.sources[ref['source_id']]
        if set(ref) == {'source_id', 'pointer'}:
            require(source['format'] == 'json', 'JSON_REFERENCE_REQUIRES_JSON_SOURCE')
            value = at(source['document'], ref['pointer'])
        else:
            require(set(ref) in ({'source_id', 'start', 'end', 'excerpt'},
                                 {'source_id', 'start', 'end', 'excerpt', 'pointer'}),
                    'INVALID_SOURCE_REFERENCE')
            require(source['format'] in ('text', 'json'), 'TEXT_REFERENCE_REQUIRED')
            start, end = ref['start'], ref['end']
            require(type(start) is int and type(end) is int and 0 <= start < end <= len(source['text']),
                    'INVALID_SOURCE_SPAN')
            require(source['text'][start:end] == ref['excerpt'], 'SOURCE_SPAN_MISMATCH')
            value = at(parse(ref['excerpt']), ref['pointer']) if 'pointer' in ref else ref['excerpt']
        require(not isinstance(value, (list, dict)), 'SOURCE_LEAF_REQUIRED')
        return value

    def scan(self, terms, match='any'):
        require(isinstance(terms, list) and terms and all(isinstance(x, str) and words(x) for x in terms),
                'NONEMPTY_SEARCH_TERMS_REQUIRED')
        require(match in ('any', 'all'), 'INVALID_TERM_MATCH')
        phrases = [words(term) for term in terms]
        candidates, unsupported = [], []
        for sid, source in self.sources.items():
            if source['format'] == 'bytes':
                unsupported.append(sid)
                continue
            units = []
            if source['format'] == 'json':
                for pointer, value in _walk(source['document']):
                    units.append((pointer + ' ' + str(value), {'source_id': sid, 'pointer': pointer}, value))
            else:
                start = 0
                for line in source['text'].splitlines(keepends=True):
                    excerpt = line.rstrip('\r\n')
                    if excerpt:
                        units.append((excerpt, {'source_id': sid, 'start': start,
                                                'end': start + len(excerpt), 'excerpt': excerpt}, excerpt))
                    start += len(line)
            for text, ref, value in units:
                tokens = words(text)
                hits = [term for term, phrase in zip(terms, phrases)
                        if any(tokens[i:i+len(phrase)] == phrase for i in range(len(tokens)-len(phrase)+1))]
                if hits and (match == 'any' or len(hits) == len(terms)):
                    candidates.append({'candidate_id': digest(canonical(ref)), 'source_ref': ref,
                                       'source_sha256': source['sha256'], 'matched_terms': hits,
                                       'value': value, 'meaning_verified': False})
        return {'terms': terms, 'match': match, 'sources_scanned': list(self.sources),
                'unsupported_sources': unsupported, 'candidates': candidates,
                'scope': 'CONFIGURED_LEXICAL_SEARCH_OF_PINNED_CORPUS',
                'semantic_completeness_verified': False}


def presence(request, corpus):
    scan = corpus.scan(request['terms'], request.get('match', 'any'))
    binding = request.get('binding')
    binding_state, binding_reason = 'UNBOUND', 'NO_ADAPTER_BINDING_SUPPLIED'
    if binding is not None:
        require(isinstance(binding, dict) and set(binding) == {'value', 'source_ref'}, 'INVALID_BINDING')
        try:
            value = corpus.resolve(binding['source_ref'])
            require(scalar_equal(value, binding['value']), 'BINDING_VALUE_MISMATCH')
            binding_state = 'EXACT_SOURCE_VALUE' if value is not None else 'SOURCE_VALUE_NULL'
            binding_reason = None
        except (ValueError, KeyError, TypeError) as exc:
            binding_state, binding_reason = 'INVALID', str(exc)
    predicate = 'SOURCE_CANDIDATE_PRESENT' if scan['candidates'] else 'NO_CONFIGURED_LEXICAL_MATCH'
    if scan['unsupported_sources']:
        predicate += '_INCOMPLETE_SCAN'
    allowed = ['source_candidate_present'] if scan['candidates'] else []
    # An exact value identity match does not establish the meaning of a label.
    if binding_state == 'EXACT_SOURCE_VALUE':
        allowed.append('adapter_value_bound')
    return {'operation': 'presence', 'scan': scan, 'binding_state': binding_state,
            'binding_reason': binding_reason, 'predicate': predicate, 'allowed_claims': allowed,
            'source_absence_established': False,
            'facts': [{'predicate': predicate, 'binding_state': binding_state,
                       'semantic_scope_verified': False,
                       'source_refs': [x['source_ref'] for x in scan['candidates']]}]}


def accounting(request, corpus):
    """Classify source-bound operands; diagnostic arithmetic is never named EPS.

    Metadata is resolved from original scalar leaves, not accepted as free-form
    declarations. Unknown labels are not upgraded through synonyms/inheritance.
    """
    facts, missing = {}, []
    groups = {'income': ('value', 'attribution', 'period_start', 'period_end', 'issuer', 'currency', 'unit_scale'),
              'shares': ('value', 'basis', 'period_start', 'period_end', 'issuer', 'unit_scale')}
    for group, fields in groups.items():
        require(isinstance(request.get(group), dict), 'ACCOUNTING_OPERAND_REQUIRED:' + group)
        facts[group] = {}
        for field in fields:
            ref = request[group].get(field)
            if ref is None:
                missing.append(group + '.' + field)
                continue
            value = corpus.resolve(ref)
            facts[group][field] = {'value': value, 'source_ref': ref}
            if value is None:
                missing.append(group + '.' + field)
    get = lambda group, field: facts[group].get(field, {}).get('value')
    diagnostic = None
    if get('income', 'value') is not None and get('shares', 'value') is not None:
        income, shares = numeric(get('income', 'value')), numeric(get('shares', 'value'))
        require(shares > 0, 'POSITIVE_SHARES_REQUIRED')
        diagnostic = income / shares
        require(math.isfinite(diagnostic), 'NONFINITE_RATIO')
    reasons = ['UNBOUND_OR_NULL_METADATA:' + field for field in missing]
    for group in groups:
        context = record_context(request[group].get('value'))
        if context is None:
            reasons.append('STRUCTURED_ACCOUNTING_VALUE_REQUIRED:' + group)
        for field, bound in facts[group].items():
            if context is None or record_context(bound['source_ref']) != context:
                reasons.append('CROSS_RECORD_METADATA_BINDING:' + group + '.' + field)
            # Canonical typed operand records bind each role to its namesake
            # original key. Parent equality alone could borrow another amount
            # or classification in the same object.
            if bound['source_ref'].get('pointer', '').rsplit('/', 1)[-1] != field:
                reasons.append('ACCOUNTING_FIELD_ROLE_MISMATCH:' + group + '.' + field)
    basis = get('shares', 'basis')
    expected_attr = {'weighted_average_basic': 'income_available_to_common',
                     'weighted_average_diluted': 'diluted_income_available_to_common'}
    if basis not in expected_attr:
        reasons.append('PERIOD_WEIGHTED_SHARE_BASIS_NOT_ESTABLISHED')
    elif get('income', 'attribution') != expected_attr[basis]:
        reasons.append('MATCHING_COMMON_INCOME_ATTRIBUTION_NOT_ESTABLISHED')
    for field in ('period_start', 'period_end', 'issuer'):
        if get('income', field) != get('shares', field) or not get('income', field):
            reasons.append('ACCOUNTING_DIMENSION_MISMATCH:' + field)
    for group in groups:
        if not isinstance(get(group, 'issuer'), str) or not get(group, 'issuer').strip():
            reasons.append('ISSUER_IDENTITY_NOT_ESTABLISHED:' + group)
    for group in groups:
        start, end = get(group, 'period_start'), get(group, 'period_end')
        if start is not None and end is not None:
            try:
                require(date.fromisoformat(start) <= date.fromisoformat(end), 'REVERSED_ACCOUNTING_PERIOD')
            except (TypeError, ValueError) as exc:
                reasons.append('INVALID_ACCOUNTING_PERIOD:' + group + ':' + str(exc))
    scales = []
    for group in groups:
        scale = get(group, 'unit_scale')
        if scale is not None:
            scale = numeric(scale)
            require(scale > 0, 'POSITIVE_UNIT_SCALE_REQUIRED')
        scales.append(scale)
    if not isinstance(get('income', 'currency'), str) or not re.fullmatch(r'[A-Z]{3}', get('income', 'currency')):
        reasons.append('INCOME_CURRENCY_NOT_ESTABLISHED')
    eps = diagnostic * scales[0] / scales[1] if not reasons and diagnostic is not None else None
    require(eps is None or math.isfinite(eps), 'NONFINITE_EPS')
    label = ('BASIC_EPS_SOURCE_BOUND' if basis == 'weighted_average_basic' else 'DILUTED_EPS_SOURCE_BOUND') if eps is not None else 'DIAGNOSTIC_RATIO_ONLY'
    allowed = ['basic_eps' if basis == 'weighted_average_basic' else 'diluted_eps'] if eps is not None else []
    return {'operation': 'accounting', 'classification': label, 'raw_operand_ratio': diagnostic,
            'raw_operand_ratio_unit_scale_applied': False, 'eps': eps, 'pe': None,
            'reasons': reasons, 'bound_fields': facts, 'allowed_claims': allowed,
            'facts': [{'predicate': label, 'value': eps, 'diagnostic_raw_operand_ratio': diagnostic}],
            'limits': ['Source identity and explicit type compatibility, not issuer authentication or independent GAAP verification.',
                       'P/E requires a separately bound comparable price and is not inferred from diagnostic arithmetic.']}


def coverage(request, corpus):
    scan = corpus.scan(request['terms'], request.get('match', 'any'))
    candidates = {row['candidate_id']: row for row in scan['candidates']}
    dispositions = {}
    require(isinstance(request.get('dispositions', []), list), 'DISPOSITIONS_LIST_REQUIRED')
    records = request.get('records', [])
    require(isinstance(records, list), 'RECORDS_LIST_REQUIRED')
    by_id = {}
    for record in records:
        require(isinstance(record, dict) and set(record) == {'record_id', 'source_refs'}, 'INVALID_COVERAGE_RECORD')
        rid = record['record_id']
        require(isinstance(rid, str) and rid and rid not in by_id, 'DUPLICATE_OR_INVALID_RECORD_ID')
        require(isinstance(record['source_refs'], list) and record['source_refs'], 'RECORD_SOURCE_REFS_REQUIRED')
        for ref in record['source_refs']:
            corpus.resolve(ref)
        by_id[rid] = record
    linked = set()
    for item in request.get('dispositions', []):
        require(isinstance(item, dict) and set(item) == {'candidate_id', 'status', 'record_ids', 'reason'},
                'INVALID_CANDIDATE_DISPOSITION')
        cid = item['candidate_id']
        require(cid in candidates and cid not in dispositions, 'UNKNOWN_OR_DUPLICATE_CANDIDATE')
        require(item['status'] in ('extracted', 'reviewed_not_relevant', 'unresolved'), 'INVALID_DISPOSITION_STATUS')
        require(isinstance(item['reason'], str) and bool(item['reason'].strip()), 'DISPOSITION_REASON_REQUIRED')
        require(isinstance(item['record_ids'], list) and len(item['record_ids']) == len(set(item['record_ids'])),
                'INVALID_DISPOSITION_RECORD_IDS')
        if item['status'] == 'extracted':
            require(item['record_ids'], 'EXTRACTED_RECORD_REQUIRED')
            for rid in item['record_ids']:
                require(rid in by_id, 'DISPOSITION_RECORD_NOT_SUPPLIED')
                require(candidates[cid]['source_ref'] in by_id[rid]['source_refs'], 'RECORD_DOES_NOT_COVER_SOURCE_CANDIDATE')
                linked.add(rid)
        else:
            require(not item['record_ids'], 'NONEXTRACTED_DISPOSITION_HAS_RECORDS')
        dispositions[cid] = item
    missing = [cid for cid in candidates if cid not in dispositions or dispositions[cid]['status'] == 'unresolved']
    orphaned = sorted(set(by_id) - linked)
    complete = not (missing or orphaned or scan['unsupported_sources'])
    return {'operation': 'coverage', 'scan': scan, 'dispositions': list(dispositions.values()),
            'unresolved_candidate_ids': missing, 'unlinked_record_ids': orphaned,
            'record_ids': sorted(by_id), 'status': 'CONFIGURED_SCAN_RECONCILED' if complete else 'INCOMPLETE',
            'allowed_claims': ['configured_scan_reconciled'] if complete else [],
            'facts': [{'predicate': 'CONFIGURED_SCAN_RECONCILED' if complete else 'CORPUS_COVERAGE_INCOMPLETE',
                       'unresolved_candidate_ids': missing, 'unsupported_sources': scan['unsupported_sources']}],
            'semantic_relevance_judgments': 'REVIEWER_SUPPLIED_NOT_AUTOMATICALLY_VERIFIED',
            'whole_source_semantic_completeness': False}


def analyst_corpus(request, corpus):
    """Run existing latest-target review only after source-candidate reconciliation."""
    audited = coverage(request['coverage'], corpus)
    analysis = analyst_numbers(request['analysis'])
    rows = analysis.get('individual_targets', [])
    ids = [row.get('record_id') for row in rows]
    require(len(ids) == len(set(ids)) and set(ids) == set(audited['record_ids']), 'ANALYSIS_COVERAGE_RECORD_SET_MISMATCH')
    records = {row['record_id']: row for row in request['coverage'].get('records', [])}
    for row in rows:
        source = row['source']
        matches = [entry for entry in corpus.sources.values()
                   if entry['path'] == source.get('path') and entry['sha256'] == source.get('sha256')]
        require(len(matches) == 1, 'ANALYST_SOURCE_NOT_IN_PINNED_CORPUS')
        sid = matches[0]['id']
        refs = records[row['record_id']]['source_refs']
        require(any(ref['source_id'] == sid for ref in refs), 'ANALYST_RECORD_SOURCE_MISMATCH')
        # Existing analyst helper retains extraction judgments. Require its cited
        # excerpt to cover the exact text candidate linked by this audit too.
        for ref in refs:
            if ref['source_id'] == sid and 'excerpt' in ref and 'pointer' not in ref:
                require(ref['excerpt'] in source.get('verbatim_excerpt', ''), 'ANALYST_EXCERPT_OMITS_LINKED_CANDIDATE')
    output = None
    if audited['status'] == 'CONFIGURED_SCAN_RECONCILED':
        from analyst_evidence import review
        output = review(analysis, corpus.root)
    return {'operation': 'analyst_corpus', 'coverage': audited, 'analysis': output,
            'status': 'REVIEWED_WITH_CONFIGURED_CORPUS_COVERAGE' if output is not None else 'BLOCKED_INCOMPLETE_CORPUS',
            'allowed_claims': audited['allowed_claims'], 'facts': audited['facts'],
            'analysis_numeric_conversion': 'FINITE_FLOAT_WITH_DECIMAL_TEXT_ROUNDTRIP',
            'latest_selection_scope': 'Only source-bound extracted records surviving analyst helper eligibility; no claim of all real-world analysts.'}


def audit(request, manifest, pin, root=None):
    corpus = Corpus(manifest, pin, root)
    operations = {'presence': presence, 'accounting': accounting, 'coverage': coverage, 'analyst_corpus': analyst_corpus}
    require(request.get('operation') in operations, 'UNKNOWN_CLAIM_OPERATION')
    result = operations[request['operation']](request, corpus)
    claimed = request.get('assert_claims', [])
    require(isinstance(claimed, list) and all(isinstance(x, str) for x in claimed), 'INVALID_ASSERTED_CLAIMS')
    unsupported = [claim for claim in claimed if claim not in result['allowed_claims']]
    result.update(schema_version=1, method='source-claims-1.0.0', manifest_sha256=pin,
                  claim_verdict='REJECTED' if unsupported else 'WITHIN_DECLARED_CONTRACT',
                  unsupported_claims=unsupported, source_authenticity_verified=False,
                  execution_authorized=False, implementation_sha256=digest(Path(__file__).read_bytes()),
                  input_sha256=digest(canonical(request)))
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', required=True)
    parser.add_argument('--manifest-sha256', required=True)
    parser.add_argument('--source-root')
    parser.add_argument('--input', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args(argv)
    request = parse(Path(args.input).read_bytes())
    result = audit(request, args.manifest, args.manifest_sha256, args.source_root)
    with Path(args.output).open('x', encoding='utf-8') as stream:
        json.dump(result, stream, indent=2, default=str)
        stream.write('\n')
    return 2 if result['claim_verdict'] == 'REJECTED' else 0


if __name__ == '__main__':
    raise SystemExit(main())
