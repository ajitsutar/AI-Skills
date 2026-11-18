import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import evidence_provenance as ep


class HashScopeTests(unittest.TestCase):
    def setUp(self):
        self.hash = dict(algorithm='sha256', canonicalization='json-sort-keys-utf8-v1',
                         scope='case/c205/request/contract', digest='a' * 64)

    def test_identical_digests_for_different_objects_are_not_equality(self):
        other = dict(self.hash, scope='case/c205/request/inputs')
        result = ep.compare_hashes(self.hash, other)
        self.assertEqual(result['status'], 'NOT_COMPARABLE')
        self.assertEqual(result['reason'], 'HASH_SCOPE_DIFFERS')
        self.assertIsNone(result['equal'])

    def test_matching_domains_and_uppercase_hex(self):
        self.assertTrue(ep.compare_hashes(self.hash, dict(self.hash, digest='A' * 64))['equal'])
        self.assertFalse(ep.compare_hashes(self.hash, dict(self.hash, digest='b' * 64))['equal'])

    def test_different_canonicalization_is_not_mismatch(self):
        result = ep.compare_hashes(self.hash, dict(self.hash, canonicalization='raw-bytes'))
        self.assertEqual(result['status'], 'NOT_COMPARABLE')

    def test_different_algorithms_are_not_comparable(self):
        result = ep.compare_hashes(self.hash, dict(self.hash, algorithm='sha512', digest='b' * 128))
        self.assertEqual(result['reason'], 'HASH_ALGORITHM_DIFFERS')

    def test_missing_fields_and_malformed_digest_fail_closed(self):
        for key in self.hash:
            other = dict(self.hash)
            del other[key]
            self.assertEqual(ep.compare_hashes(self.hash, other)['status'], 'UNKNOWN')
        for digest in ('not-a-hash', 'a' * 63, ['a']):
            result = ep.compare_hashes(self.hash, dict(self.hash, digest=digest))
            self.assertEqual(result['status'], 'INVALID')
            self.assertIsNone(result['equal'])


class ExecutionProvenanceTests(unittest.TestCase):
    def setUp(self):
        self.observed = dict(origin='current', kind='invocation', execution_observed=True,
                             artifacts_available=True, verification_passed=True)

    def test_synthetic_record_does_not_become_actual_execution(self):
        for origin in ('retained', 'current'):
            result = ep.classify_evidence(dict(self.observed, origin=origin, kind='synthetic_record'))
            self.assertFalse(result['completion_supported'])
            self.assertIn('SYNTHETIC_RECORD', result['status'])

    def test_historical_success_is_not_current_success(self):
        for kind in ('invocation', 'replay'):
            result = ep.classify_evidence(dict(self.observed, origin='retained', kind=kind))
            self.assertFalse(result['completion_supported'])
            self.assertTrue(result['status'].startswith('RETAINED_'))

    def test_filenames_are_not_artifacts(self):
        result = ep.classify_evidence(dict(origin='current', kind='invocation',
             execution_observed=True, verification_passed=True, files=['result.json']))
        self.assertEqual(result['status'], 'ARTIFACTS_UNAVAILABLE')
        self.assertFalse(result['completion_supported'])

    def test_only_explicit_observed_available_verified_current_execution_completes(self):
        self.assertEqual(ep.classify_evidence(self.observed)['status'], 'CURRENT_EXECUTION_VERIFIED')
        self.assertEqual(ep.classify_evidence(dict(self.observed, kind='replay'))['status'], 'CURRENT_REPLAY_VERIFIED')
        for key in ('execution_observed', 'artifacts_available', 'verification_passed'):
            for value in (False, None, 'true', 1):
                self.assertFalse(ep.classify_evidence(dict(self.observed, **{key: value}))['completion_supported'])
            missing = dict(self.observed)
            del missing[key]
            self.assertFalse(ep.classify_evidence(missing)['completion_supported'])

    def test_unknown_record_is_not_completion(self):
        for record in ({}, None, 'COMPUTED', {'origin': 'current', 'kind': 'filename'}):
            self.assertFalse(ep.classify_evidence(record)['completion_supported'])

    def test_cli_uses_same_semantics(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'input.json'
            path.write_text(json.dumps({'operation': 'classify_evidence', 'record': self.observed}), encoding='utf-8')
            result = subprocess.run([sys.executable, ep.__file__, str(path)], capture_output=True, text=True, check=True)
            self.assertEqual(json.loads(result.stdout), ep.classify_evidence(self.observed))


if __name__ == '__main__':
    unittest.main()
