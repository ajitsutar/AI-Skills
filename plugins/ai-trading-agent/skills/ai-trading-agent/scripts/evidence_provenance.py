"""Classify explicit provenance without treating matching text as execution proof.

CLI: python scripts/evidence_provenance.py input.json
Input: {"operation":"compare_hashes", "left":{...}, "right":{...}} or
{"operation":"classify_evidence", "record":{...}}. Output is JSON, no writes.
Hash descriptors require algorithm (sha256/sha512), canonicalization (e.g.
raw-bytes or json-sort-keys-utf8-v1), scope (the precise artifact/object identity
AND projection, e.g. case/c205/request/contract), and hexadecimal digest.
Scopes and canonicalization identifiers are compared exactly, never inferred.

Evidence records are declarations, not self-authenticating attestations. The
caller must derive observations from retained execution evidence. These labels
do not authorize trades, prove financial correctness, or verify files themselves.
"""
import argparse
import json
import re
from pathlib import Path


def compare_hashes(left, right):
    """Compare digests only after algorithm, canonicalization and scope agree."""
    def result(status, reason):
        return {'status': status, 'equal': status == 'MATCH' if status in ('MATCH', 'MISMATCH') else None,
                'reason': reason}
    if not isinstance(left, dict) or not isinstance(right, dict):
        return result('INVALID', 'HASH_DESCRIPTOR_MUST_BE_OBJECT')
    required = ('algorithm', 'canonicalization', 'scope', 'digest')
    for descriptor in (left, right):
        if any(key not in descriptor or descriptor[key] is None or
               (isinstance(descriptor[key], str) and descriptor[key].strip().lower() in ('', 'unknown', 'unavailable'))
               for key in required):
            return result('UNKNOWN', 'HASH_METADATA_MISSING')
        if any(not isinstance(descriptor[key], str) for key in required):
            return result('INVALID', 'HASH_METADATA_MUST_BE_STRINGS')
        algorithm = descriptor['algorithm'].lower()
        length = {'sha256': 64, 'sha512': 128}.get(algorithm)
        if length is None:
            return result('INVALID', 'UNSUPPORTED_HASH_ALGORITHM')
        if not re.fullmatch('[0-9a-fA-F]{' + str(length) + '}', descriptor['digest']):
            return result('INVALID', 'INVALID_HASH_DIGEST')
    if left['algorithm'].lower() != right['algorithm'].lower():
        return result('NOT_COMPARABLE', 'HASH_ALGORITHM_DIFFERS')
    if left['canonicalization'] != right['canonicalization']:
        return result('NOT_COMPARABLE', 'HASH_CANONICALIZATION_DIFFERS')
    if left['scope'] != right['scope']:
        return result('NOT_COMPARABLE', 'HASH_SCOPE_DIFFERS')
    return result('MATCH' if left['digest'].lower() == right['digest'].lower() else 'MISMATCH',
                  'SAME_DECLARED_HASH_DOMAIN')


def classify_evidence(record):
    """Separate a retained/synthetic record from observed current execution."""
    def result(status, reason, complete=False):
        return {'status': status, 'reason': reason, 'completion_supported': complete,
                'limitation': 'Classification of supplied provenance; not independent execution or correctness verification.'}
    if not isinstance(record, dict):
        return result('INVALID', 'EVIDENCE_RECORD_MUST_BE_OBJECT')
    origin, kind = record.get('origin'), record.get('kind')
    if origin is None or kind is None:
        return result('UNKNOWN', 'EVIDENCE_ORIGIN_OR_KIND_MISSING')
    if origin not in ('retained', 'current') or kind not in ('synthetic_record', 'invocation', 'replay'):
        return result('INVALID', 'UNSUPPORTED_EVIDENCE_ORIGIN_OR_KIND')
    flags = ('execution_observed', 'artifacts_available', 'verification_passed')
    if any(key in record and type(record[key]) is not bool for key in flags):
        return result('INVALID', 'EVIDENCE_FLAGS_MUST_BE_BOOLEANS')
    if kind == 'synthetic_record':
        return result('RETAINED_SYNTHETIC_RECORD' if origin == 'retained' else 'SYNTHETIC_RECORD',
                      'SYNTHETIC_RECORD_IS_NOT_OBSERVED_INVOCATION')
    if origin == 'retained':
        return result('RETAINED_INVOCATION_RECORD' if kind == 'invocation' else 'RETAINED_REPLAY_RECORD',
                      'HISTORICAL_RECORD_IS_NOT_CURRENT_EXECUTION')
    if not record.get('execution_observed', False):
        return result('EXECUTION_UNVERIFIED', 'CURRENT_EXECUTION_NOT_OBSERVED')
    if not record.get('artifacts_available', False):
        return result('ARTIFACTS_UNAVAILABLE', 'ARTIFACT_CONTENT_UNAVAILABLE_OR_NOT_CONFIRMED')
    if not record.get('verification_passed', False):
        return result('EXECUTION_UNVERIFIED', 'CURRENT_OUTPUT_VERIFICATION_NOT_PASSED')
    return result('CURRENT_REPLAY_VERIFIED' if kind == 'replay' else 'CURRENT_EXECUTION_VERIFIED',
                  'OBSERVED_CURRENT_EXECUTION_WITH_AVAILABLE_VERIFIED_ARTIFACTS', True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input', type=Path)
    args = parser.parse_args()
    try:
        payload = json.loads(args.input.read_text(encoding='utf-8-sig'))
        if not isinstance(payload, dict):
            raise ValueError('Input must be a JSON object')
        if payload.get('operation') == 'compare_hashes':
            output = compare_hashes(payload.get('left'), payload.get('right'))
        elif payload.get('operation') == 'classify_evidence':
            output = classify_evidence(payload.get('record'))
        else:
            raise ValueError('Unsupported operation')
    except (OSError, ValueError) as exc:
        output = {'status': 'INVALID', 'reason': str(exc)}
    print(json.dumps(output, indent=2, sort_keys=True, allow_nan=False))


if __name__ == '__main__':
    main()
