"""Exact original-document leaf lineage under a caller-supplied manifest pin.

This offline identity check does not authenticate issuers or infer source scope.
The expected manifest hash must come from outside the analysis being checked.
No role label, path name, or unanchored request is evidence of original lineage.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import re


class LineageError(ValueError):
    pass


def require(condition, code):
    if not condition:
        raise LineageError(code)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _pairs(items):
    result = {}
    for key, value in items:
        require(key not in result, 'DUPLICATE_JSON_KEY')
        result[key] = value
    return result


def parse(raw):
    def invalid(_):
        raise LineageError('NONFINITE_JSON_NUMBER')
    try:
        return json.loads(raw, object_pairs_hook=_pairs, parse_float=Decimal,
                          parse_constant=invalid)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise LineageError('INVALID_JSON') from exc


def _tokens(pointer):
    require(isinstance(pointer, str) and (pointer == '' or pointer.startswith('/')),
            'INVALID_JSON_POINTER')
    if pointer == '':
        return []
    raw = pointer[1:].split('/')
    require(all(re.search(r'~(?![01])', part) is None for part in raw),
            'INVALID_JSON_POINTER_ESCAPE')
    return [part.replace('~1', '/').replace('~0', '~') for part in raw]


def at(document, pointer):
    value = document
    for token in _tokens(pointer):
        if isinstance(value, dict):
            require(token in value, 'SOURCE_OR_TARGET_POINTER_MISSING')
            value = value[token]
        elif isinstance(value, list):
            require(re.fullmatch(r'0|[1-9][0-9]*', token) is not None,
                    'INVALID_ARRAY_POINTER')
            index = int(token)
            require(index < len(value), 'SOURCE_OR_TARGET_POINTER_MISSING')
            value = value[index]
        else:
            raise LineageError('SOURCE_OR_TARGET_POINTER_MISSING')
    return value


def _leaf(value):
    return not isinstance(value, (dict, list))


def _same(first, second):
    # Never equate true with 1, or an integer with a decimal spelling.
    return type(first) is type(second) and first == second


def _value_hash(value):
    return sha((type(value).__name__ + ':' + repr(value)).encode('utf-8'))


def load_manifest(path, expected_sha256, source_root=None):
    """Read every original once, verify exact bytes, then use those retained bytes."""
    require(isinstance(expected_sha256, str)
            and re.fullmatch(r'[0-9a-f]{64}', expected_sha256) is not None,
            'EXTERNAL_MANIFEST_SHA256_REQUIRED')
    manifest_path = Path(path).resolve()
    raw = manifest_path.read_bytes()
    require(sha(raw) == expected_sha256, 'INGRESS_MANIFEST_HASH_MISMATCH')
    document = parse(raw)
    require(isinstance(document, dict) and set(document) == {'schema_version', 'sources'}
            and type(document['schema_version']) is int and document['schema_version'] == 1
            and isinstance(document['sources'], list) and bool(document['sources']), 'INVALID_INGRESS_MANIFEST')
    root = Path(source_root).resolve() if source_root is not None else manifest_path.parent
    entries, paths = {}, set()
    for item in document['sources']:
        require(isinstance(item, dict) and set(item) == {'id', 'path', 'sha256', 'format'},
                'INVALID_INGRESS_SOURCE')
        require(isinstance(item['id'], str) and bool(item['id'].strip())
                and item['id'] not in entries, 'DUPLICATE_OR_INVALID_SOURCE_ID')
        require(isinstance(item['path'], str) and bool(item['path'])
                and not Path(item['path']).is_absolute(), 'INVALID_INGRESS_SOURCE_PATH')
        # Reject Windows drive/UNC spelling even on non-Windows hosts.
        require('\\' not in item['path'] and ':' not in item['path'], 'INVALID_INGRESS_SOURCE_PATH')
        source_path = (root / item['path']).resolve()
        require(source_path.is_relative_to(root), 'INGRESS_SOURCE_PATH_ESCAPE')
        require(source_path not in paths, 'DUPLICATE_SOURCE_PATH')
        require(item['format'] in {'json', 'text', 'bytes'}, 'INVALID_SOURCE_FORMAT')
        require(isinstance(item['sha256'], str)
                and re.fullmatch(r'[0-9a-f]{64}', item['sha256']) is not None,
                'INVALID_SOURCE_SHA256')
        source_raw = source_path.read_bytes()
        require(sha(source_raw) == item['sha256'], 'INGRESS_SOURCE_HASH_MISMATCH')
        entries[item['id']] = {**item, 'document': parse(source_raw) if item['format'] == 'json' else None}
        paths.add(source_path)
    return entries


def audit(target, required_pointers, mappings, manifest_path, expected_sha256, source_root=None):
    """Audit all required leaf targets; extra or duplicate mappings are errors.

    A mapping is {target_pointer, source_id, source_pointer}. No role or authorship
    flag is accepted. The target may be a model-authored document; only mapped,
    exact original leaves receive identity lineage. This does not infer meaning.
    """
    require(isinstance(required_pointers, list) and bool(required_pointers)
            and all(isinstance(pointer, str) for pointer in required_pointers)
            and len(required_pointers) == len(set(required_pointers)), 'INVALID_REQUIRED_POINTERS')
    for pointer in required_pointers:
        _tokens(pointer)
    require(isinstance(mappings, list), 'MAPPINGS_LIST_REQUIRED')
    by_target = {}
    for mapping in mappings:
        require(isinstance(mapping, dict)
                and set(mapping) == {'target_pointer', 'source_id', 'source_pointer'}, 'INVALID_IDENTITY_MAPPING')
        pointer = mapping['target_pointer']
        require(isinstance(pointer, str) and pointer in required_pointers,
                'MAPPING_TARGET_NOT_REQUIRED')
        require(pointer not in by_target, 'DUPLICATE_TARGET_MAPPING')
        require(isinstance(mapping['source_id'], str), 'INVALID_SOURCE_ID')
        _tokens(mapping['source_pointer'])
        by_target[pointer] = mapping
    originals = load_manifest(manifest_path, expected_sha256, source_root)
    fields = []
    for pointer in required_pointers:
        row = {'target_pointer': pointer, 'status': 'UNKNOWN', 'eligible_as_original_leaf': False}
        try:
            value = at(target, pointer)
            require(_leaf(value), 'TARGET_MUST_BE_LEAF')
            row['target_value_sha256'] = _value_hash(value)
            mapping = by_target.get(pointer)
            if mapping is None:
                row['reason'] = 'NO_ORIGINAL_MAPPING'
            else:
                row['mapping'] = deepcopy(mapping)
                require(mapping['source_id'] in originals, 'SOURCE_NOT_IN_PINNED_INGRESS')
                source = originals[mapping['source_id']]
                require(source['format'] == 'json', 'JSON_LEAF_SOURCE_REQUIRED')
                original = at(source['document'], mapping['source_pointer'])
                require(_leaf(original), 'ORIGINAL_MUST_BE_LEAF')
                require(_same(value, original), 'ORIGINAL_VALUE_MISMATCH')
                row['source_sha256'] = source['sha256']
                if original is None:
                    row['reason'] = 'ORIGINAL_VALUE_NULL'
                else:
                    row['status'] = 'MATCHED_ORIGINAL_VALUE'
                    row['eligible_as_original_leaf'] = True
        except LineageError as exc:
            row['status'] = 'UNKNOWN' if (pointer not in by_target and
                str(exc) == 'SOURCE_OR_TARGET_POINTER_MISSING') else 'INVALID'
            row['reason'] = str(exc)
        fields.append(row)
    return {
        'schema_version': 1,
        'method': 'pinned-original-leaf-identity',
        'manifest_sha256': expected_sha256,
        'status': 'INVALID' if any(row['status'] == 'INVALID' for row in fields) else
                  'PARTIAL' if any(not row['eligible_as_original_leaf'] for row in fields) else 'IDENTITY_MATCHED',
        'fields': fields,
        'source_authenticity_verified': False,
        'semantic_scope_verified': False,
        'external_anchor_origin_verified': False,
        'limitations': [
            'Expected manifest hash must be anchored outside the participant before analysis; this tool cannot verify who supplied it or when.',
            'Exact original-leaf identity does not establish accounting scope, issuer truth, user intent, correct source selection or completeness.',
            'No text extraction, inferred inheritance, transformed lineage, source search or prose verification is performed.',
            'A caller who can replace both the manifest and trusted expected hash can change the trust root.'],
    }


def reit_metadata_audit(document, mappings, manifest_path, expected_sha256, source_root=None):
    """Companion metadata view, never a replacement for original arithmetic.

    Use the installed REIT helper to enumerate fields. The returned document may
    be passed to its normal reconciler; keep the declaration and audit alongside
    it. Identity matches still require review of relevant measurement scope.
    """
    from reit_provenance import metadata_paths
    target = {'document': deepcopy(document)}
    pointers = metadata_paths(document)
    report = audit(target, pointers, mappings, manifest_path, expected_sha256, source_root)
    masked = deepcopy(target)
    for row in report['fields']:
        if row['eligible_as_original_leaf']:
            continue
        tokens = _tokens(row['target_pointer'])
        parent = masked
        try:
            for token in tokens[:-1]:
                parent = parent[int(token)] if isinstance(parent, list) else parent[token]
            if isinstance(parent, dict) and tokens[-1] in parent:
                parent[tokens[-1]] = None
        except (KeyError, IndexError, TypeError, ValueError):
            pass  # Preserve absent/malformed input for the normal reconciler.
    report['original_lineage_document'] = masked['document']
    report['declared_document'] = deepcopy(document)
    report['declared_document_preserved'] = True
    report['scope_note'] = ('The filtered view removes unproven metadata; it does not resolve conflicting declarations. '
                            'Retain the declared reconciliation and do not reinterpret its INCOMPATIBLE basis as compatible.')
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', required=True)
    parser.add_argument('--manifest-sha256', required=True)
    parser.add_argument('--source-root')
    parser.add_argument('--target', required=True)
    parser.add_argument('--mappings', required=True)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--required-pointers')
    mode.add_argument('--reit-metadata', action='store_true')
    parser.add_argument('--output', required=True)
    parser.add_argument('--masked-document-output', help='Optional separate REIT input document; never overwrites.')
    args = parser.parse_args(argv)
    require(args.masked_document_output is None or args.reit_metadata,
            'MASKED_DOCUMENT_REQUIRES_REIT_MODE')
    target = parse(Path(args.target).read_bytes())
    mappings = parse(Path(args.mappings).read_bytes())
    if args.reit_metadata:
        report = reit_metadata_audit(target, mappings, args.manifest, args.manifest_sha256, args.source_root)
    else:
        report = audit(target, parse(Path(args.required_pointers).read_bytes()), mappings,
                       args.manifest, args.manifest_sha256, args.source_root)
    # Retain decimals exactly in original-lineage documents without dependencies.
    def encode(item):
        if isinstance(item, Decimal):
            return str(item)
        if isinstance(item, dict):
            return '{' + ','.join(json.dumps(k) + ':' + encode(v) for k, v in item.items()) + '}'
        if isinstance(item, list):
            return '[' + ','.join(map(encode, item)) + ']'
        return json.dumps(item, allow_nan=False)
    destinations = [Path(args.output)] + ([Path(args.masked_document_output)] if args.masked_document_output else [])
    require(len({path.resolve() for path in destinations}) == len(destinations), 'OUTPUT_PATHS_MUST_DIFFER')
    require(all(not path.exists() for path in destinations), 'OUTPUT_ALREADY_EXISTS')
    with Path(args.output).open('x', encoding='utf-8') as stream:
        stream.write(encode(report) + '\n')
    if args.masked_document_output:
        with Path(args.masked_document_output).open('x', encoding='utf-8') as stream:
            stream.write(encode(report['original_lineage_document']) + '\n')
    return 2 if report['status'] == 'INVALID' else 0


if __name__ == '__main__':
    raise SystemExit(main())
