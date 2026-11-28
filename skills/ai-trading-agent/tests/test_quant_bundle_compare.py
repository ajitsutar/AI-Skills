"""Cross-version stored-output comparisons use synthetic jobs and perform no execution."""
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from quant_bundle_compare import compare
from quant_common import digest


def job(name, **result):
    return dict(id=name, operation='synthetic', status='COMPUTED', result=result)


class StoredComparisonTest(unittest.TestCase):
    def setUp(self):
        self.scratch = tempfile.TemporaryDirectory()
        self.addCleanup(self.scratch.cleanup)
        self.root = Path(self.scratch.name).resolve()

    def artifact(self, name, jobs, prompt='illustration'):
        document = dict(contract={'prompt': prompt}, jobs=[dict(id=k) for k in ('a', 'b')])
        result = dict(skill_version=name, implementation_sha256=digest(name),
                      input_sha256=digest(document), contract_sha256=digest(document['contract']),
                      results=jobs)
        content = json.dumps(dict(input=document, result=result, result_sha256=digest(result))).encode()
        path = self.root / (name + '.json')
        path.write_bytes(content)
        return path

    def test_nonzero_within_tolerance_is_still_maximum(self):
        left = self.artifact('stored', [job('a', cost=1.0), job('b', exposure=10.0)])
        right = self.artifact('current', [job('b', exposure=10.0000004), job('a', cost=1.00000002)])
        result = compare(left, right)
        self.assertTrue(result['same_input'] and result['same_contract'])
        self.assertEqual(result['nonzero_numeric_leaves'], 2)
        self.assertEqual(result['outside_tolerance'], 0)
        self.assertEqual(result['maximum_raw_delta']['job_id'], 'b')
        self.assertEqual(result['maximum_raw_delta']['path'], '/result/exposure')
        self.assertEqual(result['maximum_raw_delta']['absolute_delta'], abs(10.0000004 - 10))
        self.assertEqual(result['exact_mismatches'], 0)

    def test_max_based_rule_and_exact_outcomes(self):
        left = self.artifact('stored', [job('a', cost=1.0, tier=10_000_000, flag=True,
                                             reason='accepted', legacy=6), job('removed', x=1)])
        right = self.artifact('current', [job('a', cost=1.000000105, tier=10_000_001, flag=1,
                                               reason='changed', new=7), job('added', x=2)], prompt='different')
        result = compare(left, right, exact_fields=['tier'])
        row = result['common_jobs']['a']
        self.assertFalse(result['same_input'] or result['same_contract'])
        self.assertEqual(result['outside_tolerance'], 1)
        self.assertEqual(result['discrete_mismatches'], 3)
        self.assertEqual({r['path'] for r in row['exact_checks'] if not r['equal']},
                         {'/result/reason','/result/flag','/result/tier'})
        self.assertEqual(result['maximum_raw_delta']['path'], '/result/tier')
        self.assertTrue(result['maximum_raw_delta']['within_tolerance'])
        self.assertEqual({(r['path'],r['change']) for r in row['structure_changes']},
                         {('/result/new','added'),('/result/legacy','removed')})
        self.assertEqual([r['id'] for r in result['removed_jobs']], ['removed'])
        self.assertEqual([r['id'] for r in result['added_jobs']], ['added'])

    def test_artifact_lineage_and_no_common_numbers(self):
        left = self.artifact('predecessor', [job('a', decision='hold')])
        right = self.artifact('replacement', [job('a', decision='hold')])
        old_pin = hashlib.sha256(left.read_bytes()).hexdigest()
        new_pin = hashlib.sha256(right.read_bytes()).hexdigest()
        result = compare(left, right, stored_sha256=old_pin, current_sha256=new_pin)
        self.assertIsNone(result['maximum_raw_delta'])
        self.assertEqual(result['common_numeric_leaves'], 0)
        self.assertEqual(result['stored_artifact']['recorded_skill_version'], 'predecessor')
        self.assertEqual(result['current_artifact']['recorded_skill_version'], 'replacement')
        with self.assertRaises(ValueError):
            compare(left, right, current_sha256=old_pin)
        duplicate = self.artifact('duplicate', [job('a'), job('a')])
        with self.assertRaisesRegex(ValueError, 'distinct'):
            compare(left, duplicate)


if __name__ == '__main__':
    unittest.main()
