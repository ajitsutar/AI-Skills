"""Read stored workbench hashes without executing jobs or requiring the producer.

The caller may supply the exact frozen input and a bundle-file digest from a
separately retained receipt. Internal agreement does not authenticate a receipt.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from quant_common import digest


def inspect_bundle(path, frozen_input=None, receipt_sha256=None):
    content = path.read_bytes()
    bundle = json.loads(content.decode('utf-8-sig'))
    document = bundle['input']
    result = bundle['result']
    file_sha256 = hashlib.sha256(content).hexdigest()
    checks = {}

    def compare(name, actual, recorded):
        if not isinstance(recorded, str) or len(recorded) != 64 or any(
                c not in '0123456789abcdefABCDEF' for c in recorded):
            status = 'MISSING_OR_INVALID_DIGEST'
        else:
            status = 'MATCH' if actual == recorded.lower() else 'MISMATCH'
        checks[name] = dict(actual=actual, recorded=recorded, status=status)

    compare('input', digest(document), result.get('input_sha256'))
    compare('contract', digest(document['contract']), result.get('contract_sha256'))
    compare('result', digest(result), bundle.get('result_sha256'))
    if receipt_sha256 is not None:
        compare('receipt_bundle_file', file_sha256, receipt_sha256)
    source_file_sha256 = None
    if frozen_input is not None:
        source_bytes = frozen_input.read_bytes()
        source_file_sha256 = hashlib.sha256(source_bytes).hexdigest()
        compare('separate_input_vs_embedded', digest(json.loads(source_bytes.decode('utf-8-sig'))),
                checks['input']['actual'])
    return {
        'status': 'DIGESTS_MATCH' if all(row['status'] == 'MATCH' for row in checks.values())
                  else 'DIGEST_CHECK_FAILED',
        'bundle_file_sha256': file_sha256,
        'separate_input_file_sha256': source_file_sha256,
        'recorded_skill_version': result.get('skill_version'),
        'recorded_implementation_sha256': result.get('implementation_sha256'),
        'checks': checks,
        'numerical_replay_performed': False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('bundle', type=Path)
    parser.add_argument('--frozen-input', type=Path,
                        help='Separate JSON file expected to equal the embedded input')
    parser.add_argument('--receipt-sha256', help='Expected SHA-256 of exact bundle file bytes')
    args = parser.parse_args()
    result = inspect_bundle(args.bundle, args.frozen_input, args.receipt_sha256)
    print(json.dumps(result, indent=2))
    return 0 if result['status'] == 'DIGESTS_MATCH' else 1


if __name__ == '__main__':
    raise SystemExit(main())
