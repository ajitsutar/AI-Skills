"""Offline, advisory receipt binding an explicit source selection to a handoff.

This does not infer user intent, authenticate a source, submit an order, or grant
or refuse native execution. Validation concerns this research receipt only.
Full artifacts contain private values; choose access-controlled local storage.
"""
from __future__ import annotations

import argparse
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import re
import sys

from execution_handoff import handoff

ROOT = Path(__file__).resolve().parents[1]


def encode(value):
    """Canonical JSON retaining finite decimal values without binary rounding."""
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise ValueError('NONFINITE_NUMBER')
        return str(value)
    if isinstance(value, dict):
        return '{' + ','.join(json.dumps(k, ensure_ascii=False) + ':' + encode(value[k])
                              for k in sorted(value)) + '}'
    if isinstance(value, list):
        return '[' + ','.join(encode(v) for v in value) + ']'
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(',', ':'))


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def strict_json(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError('DUPLICATE_JSON_KEY')
            result[key] = value
        return result

    def invalid_number(_):
        raise ValueError('NONFINITE_NUMBER')

    return json.loads(raw.decode('utf-8-sig'), object_pairs_hook=pairs,
                      parse_float=Decimal, parse_constant=invalid_number)


def select(document, pointer):
    """Select using RFC6901; strings in the selected data are never instructions."""
    if not isinstance(pointer, str) or (pointer and not pointer.startswith('/')):
        raise ValueError('JSON_POINTER_REQUIRED')
    value = document
    for token in pointer[1:].split('/') if pointer else []:
        if re.search(r'~(?![01])', token):
            raise ValueError('INVALID_POINTER_ESCAPE')
        key = token.replace('~1', '/').replace('~0', '~')
        if isinstance(value, dict):
            if key not in value:
                raise ValueError('POINTER_NOT_FOUND')
            value = value[key]
        elif isinstance(value, list) and re.fullmatch(r'0|[1-9][0-9]*', key):
            index = int(key)
            if index >= len(value):
                raise ValueError('POINTER_NOT_FOUND')
            value = value[index]
        else:
            raise ValueError('POINTER_NOT_FOUND')
    # The existing handoff treats None as an omitted payload; avoid falsely
    # describing that transformation as exact preservation of selected null.
    if value is None:
        raise ValueError('NULL_SELECTION_NOT_PRESERVABLE_BY_HANDOFF')
    return value


def bind(raw, expected_sha256, pointer):
    if not isinstance(expected_sha256, str) or not re.fullmatch('[0-9a-fA-F]{64}', expected_sha256):
        raise ValueError('EXPECTED_SHA256_REQUIRED')
    actual = sha(raw)
    if actual != expected_sha256.lower():
        raise ValueError('SOURCE_BYTES_HASH_MISMATCH')
    selected = select(strict_json(raw), pointer)
    return selected, {'artifact_sha256': actual, 'pointer': pointer,
                      'selected_value_sha256': sha(encode(selected).encode('utf-8')),
                      'selection_basis': 'CALLER_EXPLICIT_NOT_INFERRED'}


def differences(expected, compared, path=''):
    """Exact structure/value comparison; no aliases or economic equivalence guessed."""
    if type(expected) is not type(compared):
        return [{'pointer': path, 'kind': 'TYPE_CHANGED', 'expected': expected, 'compared': compared}]
    if isinstance(expected, dict):
        result = []
        for key in sorted(set(expected) | set(compared)):
            child = path + '/' + key.replace('~', '~0').replace('/', '~1')
            if key not in expected:
                result.append({'pointer': child, 'kind': 'ADDED', 'compared': compared[key]})
            elif key not in compared:
                result.append({'pointer': child, 'kind': 'REMOVED', 'expected': expected[key]})
            else:
                result.extend(differences(expected[key], compared[key], child))
        return result
    if isinstance(expected, list):
        result = []
        for i in range(max(len(expected), len(compared))):
            child = path + '/' + str(i)
            if i >= len(expected):
                result.append({'pointer': child, 'kind': 'ADDED', 'compared': compared[i]})
            elif i >= len(compared):
                result.append({'pointer': child, 'kind': 'REMOVED', 'expected': expected[i]})
            else:
                result.extend(differences(expected[i], compared[i], child))
        return result
    return [] if expected == compared else [
        {'pointer': path, 'kind': 'VALUE_CHANGED', 'expected': expected, 'compared': compared}]


def report(source_raw, expected_sha256, pointer, *, comparison_raw=None,
           comparison_sha256=None, comparison_pointer=None, comparison_role='proposed'):
    selected, provenance = bind(source_raw, expected_sha256, pointer)
    result = handoff(selected, source='handoff_report')
    if differences(selected, result['payload']):
        raise ValueError('HANDOFF_COPY_MISMATCH')
    comparison = {'status': 'NOT_SUPPLIED'}
    if comparison_role not in ('observed', 'proposed'):
        raise ValueError('COMPARISON_ROLE_REQUIRED')
    supplied = (comparison_raw is not None, comparison_sha256 is not None, comparison_pointer is not None)
    if any(supplied) and not all(supplied):
        raise ValueError('COMPLETE_COMPARISON_BINDING_REQUIRED')
    if all(supplied):
        other, bound = bind(comparison_raw, comparison_sha256, comparison_pointer)
        diff = differences(selected, other)
        comparison = {'status': 'IDENTICAL' if not diff else 'DIFFERENT',
                      'role': comparison_role, 'source': bound, 'differences': diff,
                      'difference_count': len(diff)}
    return {'schema_version': 1, 'kind': 'ADVISORY_HANDOFF_PRESERVATION_RECEIPT',
            'source': provenance, 'handoff': result, 'comparison': comparison,
            'handoff_payload_preserved': True,
            'implementation_sha256': {name: sha((ROOT / 'scripts' / name).read_bytes())
                                      for name in ('handoff_report.py', 'execution_handoff.py')},
            'limits': ['Caller chooses the source pointer; this receipt does not infer the intended instruction.',
                       'Hashes bind retained bytes; they do not authenticate source facts or user authorization.',
                       'Differences are advisory observations, never execution approval or refusal.',
                       'No broker, network, human-approval gate or native execution restriction.',
                       'Full artifacts include private routing and selected data; no access-control guarantee.']}


def local_path(value):
    text = str(value)
    if '://' in text or text.startswith(('\\\\', '//')):
        raise ValueError('LOCAL_PATH_REQUIRED')
    path = Path(value).resolve()
    if str(path).startswith(('\\\\', '//')):
        raise ValueError('LOCAL_PATH_REQUIRED')
    return path


def save(directory, receipt, source_raw, comparison_raw=None):
    # The library API can be called separately from report(); bind the bytes
    # actually retained, not merely those a caller previously computed against.
    if not isinstance(receipt, dict) or not isinstance(receipt.get('source'), dict):
        raise ValueError('RECEIPT_SOURCE_BINDING_REQUIRED')
    if sha(source_raw) != receipt['source'].get('artifact_sha256'):
        raise ValueError('RETAINED_SOURCE_HASH_MISMATCH')
    comparison = receipt.get('comparison')
    if not isinstance(comparison, dict) or comparison.get('status') not in ('NOT_SUPPLIED', 'IDENTICAL', 'DIFFERENT'):
        raise ValueError('RECEIPT_COMPARISON_STATUS_REQUIRED')
    if (comparison_raw is not None) != (comparison['status'] != 'NOT_SUPPLIED'):
        raise ValueError('RETAINED_COMPARISON_PRESENCE_MISMATCH')
    if comparison_raw is not None:
        bound = comparison.get('source')
        if not isinstance(bound, dict) or sha(comparison_raw) != bound.get('artifact_sha256'):
            raise ValueError('RETAINED_COMPARISON_HASH_MISMATCH')
    folder = local_path(directory)
    if folder.is_relative_to(ROOT):
        raise ValueError('PRIVATE_OUTPUT_OUTSIDE_SKILL_REQUIRED')
    # Exclusive directory creation prevents overwriting an earlier receipt.
    # Windows storage ACLs are inherited; callers choose a private location.
    folder.mkdir(mode=0o700, exist_ok=False)
    artifacts = {'source.json': source_raw,
                 'receipt.json': (encode(receipt) + '\n').encode('utf-8')}
    if comparison_raw is not None:
        artifacts['comparison.json'] = comparison_raw
    for name, raw in artifacts.items():
        with (folder / name).open('xb') as stream:
            stream.write(raw)
    return folder


def display_summary(receipt):
    # Neither values nor pointer paths are displayed: diff values can contain
    # private routing even when stored under generic expected/compared keys.
    return {'kind': receipt['kind'], 'receipt_written': True,
            'handoff_payload_preserved': receipt['handoff_payload_preserved'],
            'comparison_status': receipt['comparison']['status'],
            'difference_count': receipt['comparison'].get('difference_count'),
            'advisory_only': True, 'skill_submitted_order': False,
            'private_payloads_omitted': True}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source', required=True)
    p.add_argument('--expected-sha256', required=True)
    p.add_argument('--pointer', required=True)
    p.add_argument('--private-output-dir', required=True)
    p.add_argument('--comparison')
    p.add_argument('--comparison-sha256')
    p.add_argument('--comparison-pointer')
    p.add_argument('--comparison-role', choices=('observed', 'proposed'), default='proposed')
    args = p.parse_args(argv)
    try:
        raw = local_path(args.source).read_bytes()
        compared = local_path(args.comparison).read_bytes() if args.comparison else None
        receipt = report(raw, args.expected_sha256, args.pointer, comparison_raw=compared,
                         comparison_sha256=args.comparison_sha256,
                         comparison_pointer=args.comparison_pointer, comparison_role=args.comparison_role)
        save(args.private_output_dir, receipt, raw, compared)
    except (ValueError, OSError, TypeError, RecursionError) as exc:
        # Do not echo parser excerpts, paths, source values, or routing on errors.
        print(json.dumps({'receipt_written': False, 'error_type': type(exc).__name__,
                          'meaning': 'Receipt could not be produced; native execution permissions unchanged.'}), file=sys.stderr)
        return 2
    print(json.dumps(display_summary(receipt), sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
