"""Audit literal publication/original-link declarations against a final JSON ledger.

This offline, bounded English-label adapter is not an origin classifier. Exact
bytes, observed label spans, URL alternatives and final fields remain separate.
The original-source manifest pin must be anchored outside the analysis being
checked. No selected role, hostname or caller-supplied expected URL proves origin.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path, PureWindowsPath
import re
from urllib.parse import urlsplit

from source_lineage import at, load_manifest

ADAPTER = 'explicit-link-declarations-v1'
LABELS = re.compile(r'(?<!\w)(Canonical identifier|Publication identifier|Publication URL|Original source URL|Original source)\s*:', re.I)
PUBLICATION_LABELS = {'canonical identifier', 'publication identifier', 'publication url'}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def parse(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, 'DUPLICATE_JSON_KEY')
            result[key] = value
        return result

    def number(value):
        parsed = float(value)
        require(math.isfinite(parsed), 'NONFINITE_JSON_NUMBER')
        return parsed

    def invalid(value):
        raise ValueError('NONFINITE_JSON_NUMBER:' + value)

    return json.loads(raw, object_pairs_hook=pairs, parse_float=number, parse_constant=invalid)


def contained(root, name):
    require(isinstance(name, str) and bool(name.strip()), 'RELATIVE_PATH_REQUIRED')
    path = Path(name)
    require(not path.is_absolute() and not PureWindowsPath(name).drive and not PureWindowsPath(name).root,
            'RELATIVE_PATH_REQUIRED')
    result = (root / path).resolve()
    require(result.is_relative_to(root) and result != root, 'PATH_OUTSIDE_ROOT')
    return result


def valid_url(value):
    if not isinstance(value, str) or not value or re.search(r'[\s<>"\\\x00-\x1f]', value):
        return False
    try:
        parts = urlsplit(value)
        _ = parts.port  # urlsplit defers malformed/out-of-range port validation.
        return parts.scheme in {'https', 'http'} and bool(parts.hostname) and parts.username is None and parts.password is None
    except ValueError:
        return False


def declarations(text):
    """Observe all recognized labels, without caller selection or semantic grades.

    Offsets are zero-based Unicode code-point offsets in strict decoded UTF-8.
    Plain terminal punctuation produces alternatives, never silent normalization.
    Quoted or unrecognized prefixes are context limits, not validated declarations.
    """
    # Preserve offsets while excluding literal URL tokens from prose-only checks.
    # A domain/path/query containing "example", "quoted" or "template" is not
    # a statement that the surrounding declaration is an example or quotation.
    prose = re.sub(r'https?://[^\s<>"\u201c\u201d`]+', lambda match: ' ' * len(match.group()), text, flags=re.I)
    roles = {'publication_identifier': [], 'declared_original_link': []}
    for marker in LABELS.finditer(text):
        role = 'publication_identifier' if marker.group(1).lower() in PUBLICATION_LABELS else 'declared_original_link'
        line_start = text.rfind('\n', 0, marker.start()) + 1
        line_end = text.find('\n', marker.end())
        if line_end < 0:
            line_end = len(text)
        line = prose[line_start:line_end]
        prefix = prose[line_start:marker.start()]
        after = text[marker.end():line_end]
        trimmed = after.lstrip(' \t')
        token_start = marker.end() + len(after) - len(trimmed)
        token_end, token, alternatives, reasons = token_start, '', [], []
        # These are deliberately restrictive grammar checks, not an NLP claim.
        # Unrelated negation in another sentence is not classified as this label's negation.
        preceding_clause = re.split(r'[.!?;]\s+', prefix)[-1]
        if preceding_clause.strip():
            reasons.append('LABEL_NOT_AT_LINE_OR_SENTENCE_START')
        if re.search(r'["\u201c\u201d\u2018\u2019`]', line) or line.lstrip().startswith(('>', "'")):
            reasons.append('QUOTED_OR_CODE_CONTEXT')
        earlier = prose[:line_start]
        if (earlier.count('"') % 2 or earlier.count('\u201c') > earlier.count('\u201d') or
                len(re.findall(r'(?m)^\s*(?:```|~~~)', earlier)) % 2 or
                len(re.findall(r'<blockquote\b', earlier, re.I)) > len(re.findall(r'</blockquote\s*>', earlier, re.I))):
            reasons.append('MULTILINE_QUOTED_OR_CODE_CONTEXT')
        previous_line = earlier.rstrip('\r\n').rsplit('\n', 1)[-1]
        if re.fullmatch(r'\s*(?:example|hypothetical|illustration|quotation)\s*:\s*', previous_line, re.I):
            reasons.append('EXAMPLE_OR_QUOTATION_INTRODUCTION')
        if re.search(r'\b(example|hypothetical|illustrative|template|quoted|quotation|negated|incorrect)\b', line, re.I):
            reasons.append('EXAMPLE_OR_QUALIFIED_CONTEXT')
        if trimmed.startswith('<'):
            close = trimmed.find('>')
            if close > 1:
                token = trimmed[1:close]
                token_end = token_start + close + 1
                if valid_url(token):
                    alternatives = [{'url': token, 'interpretation': 'ANGLE_BRACKET_DELIMITED'}]
                else:
                    reasons.append('INVALID_URL_TOKEN')
            else:
                reasons.append('UNTERMINATED_URL_DELIMITER')
        else:
            matched = re.match(r'[^\s<>"\u201c\u201d`]+', trimmed)
            if matched:
                token = matched.group()
                token_end = token_start + len(token)
                if valid_url(token):
                    alternatives.append({'url': token, 'interpretation': 'LITERAL_TOKEN'})
                if token.endswith(('.', ',', ';', ':', '!', '?', ')', ']', "'")):
                    shortened = token[:-1]
                    if valid_url(shortened):
                        alternatives.append({'url': shortened, 'interpretation': 'ONE_TERMINAL_CHARACTER_AS_DELIMITER'})
                    reasons.append('AMBIGUOUS_URL_BOUNDARY')
                if not alternatives:
                    reasons.append('INVALID_URL_TOKEN')
            else:
                reasons.append('MISSING_URL_TOKEN')
        suffix_clause = re.split(r'[.!?;]', prose[token_end:line_end], maxsplit=1)[0]
        if re.search(r'\b(?:is|was|should|must)\s+(?:not|never)\b|\bnot\s+(?:the\s+)?(?:actual\s+)?(?:original|origin|source|correct)\b', suffix_clause, re.I):
            reasons.append('EXPLICIT_NEGATING_SUFFIX')
        excerpt = text[marker.start():token_end]
        roles[role].append({'label': marker.group(1), 'start': marker.start(), 'end': token_end,
                            'excerpt': excerpt, 'excerpt_sha256': digest(excerpt.encode('utf-8')),
                            'raw_url_token': token, 'candidates': alternatives,
                            'context_diagnostics': reasons})
    return roles


def role_status(observations):
    if not observations:
        return 'UNRESOLVED_NO_DECLARATION'
    if len(observations) > 1:
        return 'UNRESOLVED_MULTIPLE_DECLARATIONS'
    reasons = observations[0]['context_diagnostics']
    if any(reason != 'AMBIGUOUS_URL_BOUNDARY' for reason in reasons):
        return 'UNRESOLVED_CONTEXT'
    if reasons:
        return 'UNRESOLVED_URL_BOUNDARY'
    return 'UNIQUE_LITERAL_DECLARATION'


def field_check(row, relative_pointer, absolute_pointer, role, observations, binding_status):
    item = {'pointer': absolute_pointer, 'role': role, 'source_authenticity_verified': False,
            'semantic_relation_verified': False, 'literal_comparison': 'UNAVAILABLE'}
    try:
        actual = at(row, relative_pointer)
        item['actual_value'] = deepcopy(actual)
        require(actual is None or isinstance(actual, str), 'FINAL_FIELD_NOT_STRING_OR_NULL')
    except (ValueError, KeyError, TypeError) as error:
        item.update(status='UNAUDITED_FIELD', diagnostic=str(error))
        return item
    if binding_status != 'VERIFIED_ORIGINAL_BYTES':
        item['status'] = 'UNAUDITED_FIELD' if binding_status == 'UNAUDITED' else 'INVALID_PROVENANCE'
        return item
    candidates = sorted({candidate['url'] for observation in observations for candidate in observation['candidates']})
    item['literal_url_candidates'] = candidates
    declaration_status = role_status(observations)
    item['declaration_status'] = declaration_status
    if isinstance(actual, str) and candidates:
        item['literal_comparison'] = ('MATCHES_ONE_LITERAL_CANDIDATE' if actual in candidates
                                      else 'DIFFERS_FROM_ALL_LITERAL_CANDIDATES')
    if declaration_status == 'UNIQUE_LITERAL_DECLARATION':
        item['status'] = ('MATCHES_SELECTED_DECLARATION' if actual == candidates[0]
                          else 'DIFFERS_FROM_SELECTED_DECLARATION')
    else:
        item['status'] = declaration_status
    return item


def audit(request, artifact_root, source_root, ingress_manifest, ingress_sha256):
    require(isinstance(request, dict) and set(request) == {'schema_version', 'final_ledger', 'bindings'}, 'INVALID_REQUEST_SCHEMA')
    require(type(request['schema_version']) is int and request['schema_version'] == 1, 'SCHEMA_VERSION_1_REQUIRED')
    declaration = request['final_ledger']
    require(isinstance(declaration, dict) and set(declaration) ==
            {'path', 'sha256', 'rows_pointer', 'id_pointer', 'publication_pointer', 'origin_pointer'}, 'INVALID_FINAL_LEDGER_SCHEMA')
    for key in ('rows_pointer', 'id_pointer', 'publication_pointer', 'origin_pointer'):
        require(isinstance(declaration[key], str) and (declaration[key] == '' or declaration[key].startswith('/')), 'INVALID_LEDGER_POINTER')
        require(re.search(r'~(?![01])', declaration[key]) is None, 'INVALID_POINTER_ESCAPE')
    require(declaration['publication_pointer'] != declaration['origin_pointer'], 'PUBLICATION_ORIGIN_POINTER_COLLISION')
    require(declaration['publication_pointer'] and declaration['origin_pointer'] and declaration['id_pointer'], 'ROW_FIELD_POINTER_REQUIRED')
    artifact_root, source_root = Path(artifact_root).resolve(), Path(source_root).resolve()
    path = contained(artifact_root, declaration['path'])
    require(isinstance(declaration['sha256'], str) and re.fullmatch('[0-9a-f]{64}', declaration['sha256']), 'FINAL_LEDGER_SHA256_REQUIRED')
    raw = path.read_bytes()
    require(digest(raw) == declaration['sha256'], 'FINAL_LEDGER_HASH_MISMATCH')
    document = parse(raw)
    rows = at(document, declaration['rows_pointer'])
    require(isinstance(rows, list) and bool(rows), 'NONEMPTY_FINAL_ROW_COLLECTION_REQUIRED')
    sources = load_manifest(ingress_manifest, ingress_sha256, source_root)
    require(isinstance(request['bindings'], list), 'BINDINGS_LIST_REQUIRED')
    bindings = {}
    for binding in request['bindings']:
        require(isinstance(binding, dict) and set(binding) == {'row_id', 'source_id', 'adapter'}, 'INVALID_BINDING_SCHEMA')
        require(all(isinstance(binding[key], str) and binding[key].strip() for key in binding), 'NONEMPTY_BINDING_VALUES_REQUIRED')
        require(binding['adapter'] == ADAPTER, 'UNSUPPORTED_DECLARATION_ADAPTER')
        bindings.setdefault(binding['row_id'], []).append(binding)
    row_ids, counts = [], {}
    for row in rows:
        try:
            identity = at(row, declaration['id_pointer'])
            require(isinstance(identity, str) and bool(identity.strip()), 'INVALID_ROW_ID')
        except (ValueError, KeyError, TypeError):
            identity = None
        row_ids.append(identity)
        if identity is not None:
            counts[identity] = counts.get(identity, 0) + 1
    results = []
    for index, (row, identity) in enumerate(zip(rows, row_ids)):
        pointer = declaration['rows_pointer'] + '/' + str(index)
        binding_status, diagnostic = 'UNAUDITED', None
        evidence, roles = None, {'publication_identifier': [], 'declared_original_link': []}
        selected = bindings.get(identity, [])
        if identity is None or counts.get(identity, 0) != 1:
            binding_status, diagnostic = 'INVALID', 'MISSING_OR_DUPLICATE_FINAL_ROW_ID'
        elif len(selected) > 1:
            binding_status, diagnostic = 'INVALID', 'DUPLICATE_SOURCE_BINDING'
        elif selected:
            binding = selected[0]
            try:
                require(binding['source_id'] in sources, 'SOURCE_NOT_IN_PINNED_INGRESS')
                entry = sources[binding['source_id']]
                evidence = {'source_id': binding['source_id'], 'path': entry['path'], 'sha256': entry['sha256'],
                            'format': entry['format'], 'adapter': ADAPTER}
                require(entry['format'] in {'text', 'bytes'}, 'TEXT_OR_UTF8_BYTES_SOURCE_REQUIRED')
                source_bytes = contained(source_root, entry['path']).read_bytes()
                require(digest(source_bytes) == entry['sha256'], 'SOURCE_CHANGED_AFTER_MANIFEST_CHECK')
                # Strict decode and no newline normalization: offsets and spans
                # refer to the actual retained text. BOM remains part of offsets.
                try:
                    text = source_bytes.decode('utf-8')
                except UnicodeDecodeError as error:
                    raise ValueError('UNSUPPORTED_SOURCE_ENCODING_UTF8') from error
                roles = declarations(text)
                evidence.update(offset_unit='UNICODE_CODE_POINTS', full_document_scanned=True,
                                observations=roles)
                binding_status = 'VERIFIED_ORIGINAL_BYTES'
            except (ValueError, OSError, UnicodeError) as error:
                binding_status, diagnostic = 'INVALID', str(error)
        fields = [field_check(row, declaration['publication_pointer'], pointer + declaration['publication_pointer'],
                              'publication_identifier', roles['publication_identifier'], binding_status),
                  field_check(row, declaration['origin_pointer'], pointer + declaration['origin_pointer'],
                              'declared_original_link', roles['declared_original_link'], binding_status)]
        results.append({'row_pointer': pointer, 'row_id': identity, 'binding_status': binding_status,
                        'diagnostic': diagnostic, 'source': evidence, 'fields': fields})
    extras = sorted(set(bindings) - set(counts))
    diagnostics = bool(extras) or any(row['binding_status'] != 'VERIFIED_ORIGINAL_BYTES' or
        any(field['status'] != 'MATCHES_SELECTED_DECLARATION' for field in row['fields']) for row in results)
    return {'schema_version': 1, 'method': 'final-ledger-origin-audit-1.0.0',
            'status': 'DIAGNOSTICS_PRESENT' if diagnostics else 'REVIEW_REQUIRED',
            'declared_input': deepcopy(request), 'final_ledger': deepcopy(declaration),
            'ingress_manifest_sha256': ingress_sha256, 'records': results,
            'unmatched_binding_row_ids': extras,
            'coverage': {'rows_in_selected_collection': len(rows), 'fields_in_scope': 2 * len(rows),
                         'fields_compared_to_unique_declaration': sum(field['status'] in
                            {'MATCHES_SELECTED_DECLARATION', 'DIFFERS_FROM_SELECTED_DECLARATION'}
                            for row in results for field in row['fields']),
                         'all_selected_rows_bound': all(row['binding_status'] == 'VERIFIED_ORIGINAL_BYTES' for row in results)},
            'source_authenticity_verified': False, 'semantic_relation_verified': False,
            'implementation_sha256': digest(Path(__file__).read_bytes()),
            'limitations': [
                'The ingress pin must be anchored outside this analysis; this tool cannot authenticate that anchoring or any publisher.',
                'Labels and URL candidates are literal observations, not proof of true origin, event identity or independence.',
                'The adapter recognizes a small English-label grammar. Its context diagnostics are conservative and incomplete, not robust natural-language interpretation.',
                'Punctuation alternatives are retained. Matching one ambiguous candidate never establishes a unique declaration.',
                'Final fields with no declared link remain unresolved; publication is never substituted for missing origin.',
                'Only the selected collection and configured fields are inventoried. Additional ledger fields and uncaptured prose remain outside this audit.',
                'Later final-artifact edits invalidate its hash; audit the actual cited artifact again after changes.'],
            'execution_authorized': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=['audit'])
    parser.add_argument('request'); parser.add_argument('artifact_root'); parser.add_argument('output')
    parser.add_argument('--source-root', required=True)
    parser.add_argument('--ingress-manifest', required=True)
    parser.add_argument('--ingress-sha256', required=True)
    args = parser.parse_args()
    # Output must not replace the source ledger, request, manifest, or originals.
    request_path = Path(args.request).resolve()
    request = parse(request_path.read_bytes())
    output = Path(args.output).resolve()
    final_path = contained(Path(args.artifact_root).resolve(), request['final_ledger']['path'])
    require(output not in {request_path, final_path, Path(args.ingress_manifest).resolve()}, 'OUTPUT_OVERWRITES_INPUT')
    sources = load_manifest(args.ingress_manifest, args.ingress_sha256, args.source_root)
    require(output not in {contained(Path(args.source_root).resolve(), source['path']) for source in sources.values()}, 'OUTPUT_OVERWRITES_SOURCE')
    result = audit(request, args.artifact_root, args.source_root, args.ingress_manifest, args.ingress_sha256)
    with output.open('x', encoding='utf-8', newline='\n') as handle:
        handle.write(json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False) + '\n')
    print(json.dumps({'status': result['status'], 'coverage': result['coverage'],
                      'final_ledger_sha256': result['final_ledger']['sha256']}))


if __name__ == '__main__':
    main()
