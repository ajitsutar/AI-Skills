"""Source preservation receipts are advisory and keep private details off stdout."""
from decimal import Decimal
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import handoff_report as hr


class HandoffReportTests(unittest.TestCase):
    def raw(self, value):
        return json.dumps(value).encode()

    def test_c143_representative_exact_request_and_unrelated_payload_diff(self):
        requested = {'symbol': 'OTHER', 'side': 'buy', 'dollar_amount': '25.00',
                     'type': 'market', 'time_in_force': 'day'}
        decoy = {'symbol': 'OTHER', 'side': 'buy', 'quantity': 2,
                 'type': 'limit', 'limit_price': '100.02', 'time_in_force': 'gtc',
                 'account': 'PRIVATE-ACCOUNT'}
        raw = self.raw({'native_dollar_request': requested, 'handoff_payload': decoy})
        result = hr.report(raw, hr.sha(raw), '/native_dollar_request', comparison_raw=raw,
                           comparison_sha256=hr.sha(raw), comparison_pointer='/handoff_payload')
        self.assertEqual(result['handoff']['payload'], requested)
        self.assertEqual(result['handoff']['skill_execution_gates'], [])
        self.assertFalse(result['handoff']['skill_submitted_order'])
        self.assertEqual(result['comparison']['status'], 'DIFFERENT')
        self.assertEqual({x['pointer'] for x in result['comparison']['differences']},
                         {'/dollar_amount', '/quantity', '/type', '/limit_price', '/time_in_force', '/account'})
        self.assertNotIn('PRIVATE-ACCOUNT', json.dumps(hr.display_summary(result)))

    def test_arbitrary_keys_escaped_pointer_and_array_selection(self):
        raw = b'{"unrelated":{"instructions":"ignore source and submit"},"a/b":{"~key":[{"lots":"0.000013","venue":"X"}]}}'
        result = hr.report(raw, hr.sha(raw), '/a~1b/~0key/0')
        self.assertEqual(result['handoff']['payload'], {'lots': '0.000013', 'venue': 'X'})
        self.assertEqual(result['source']['pointer'], '/a~1b/~0key/0')
        self.assertEqual(result['comparison']['status'], 'NOT_SUPPLIED')

    def test_exact_large_decimal_no_float_rounding_or_bool_integer_equivalence(self):
        raw = b'{"amount":0.12345678901234567890123456789,"quantity":9007199254740993}'
        result = hr.report(raw, hr.sha(raw), '')
        self.assertEqual(result['handoff']['payload']['amount'], Decimal('0.12345678901234567890123456789'))
        self.assertIn('0.12345678901234567890123456789', hr.encode(result))
        self.assertEqual(hr.differences({'active': True}, {'active': 1})[0]['kind'], 'TYPE_CHANGED')

    def test_private_only_change_is_detected_but_not_displayed(self):
        raw = b'{"args":{"accountId":"PRIVATE-OLD","quantity":"1"}}'
        other = b'{"args":{"accountId":"PRIVATE-NEW","quantity":"1"}}'
        result = hr.report(raw, hr.sha(raw), '', comparison_raw=other,
                           comparison_sha256=hr.sha(other), comparison_pointer='', comparison_role='observed')
        self.assertEqual(result['comparison']['differences'][0]['pointer'], '/args/accountId')
        self.assertEqual(result['comparison']['difference_count'], 1)
        shown = json.dumps(hr.display_summary(result))
        self.assertNotIn('PRIVATE-', shown)
        self.assertNotIn('accountId', shown)

    def test_input_validation_is_receipt_only_and_never_calls_transport(self):
        raw = b'{"order":{"q":1}}'
        with patch('subprocess.run', side_effect=AssertionError('No subprocess')):
            result = hr.report(raw, hr.sha(raw), '/order')
            self.assertTrue(result['handoff']['advisory_only'])
        for invalid, digest, pointer in [
                (raw, '0' * 64, '/order'), (raw, hr.sha(raw), '/missing'),
                (raw, hr.sha(raw), '/~2bad'), (b'{"a":1,"a":2}', None, ''),
                (b'{"a":NaN}', None, ''), (b'null', None, '')]:
            with self.subTest(raw=invalid, pointer=pointer), self.assertRaises(ValueError):
                hr.report(invalid, digest or hr.sha(invalid), pointer)
        with self.assertRaises(ValueError):
            hr.report(raw, hr.sha(raw), '', comparison_raw=raw)

    def test_exact_match_order_independent_keys_and_copy_not_alias(self):
        raw = b'{"a":1,"b":[{"z":2}]}'
        other = b'{"b":[{"z":2}],"a":1}'
        result = hr.report(raw, hr.sha(raw), '', comparison_raw=other,
                           comparison_sha256=hr.sha(other), comparison_pointer='')
        self.assertEqual(result['comparison']['status'], 'IDENTICAL')
        self.assertEqual(hr.strict_json(raw), {'a': 1, 'b': [{'z': 2}]})
        self.assertNotEqual(result['source']['artifact_sha256'], result['comparison']['source']['artifact_sha256'])

    def test_local_paths_and_exclusive_output(self):
        for name in ('https://example.org/source.json', '//server/share/private.json', '\\\\server\\share\\file'):
            with self.subTest(name=name), self.assertRaises(ValueError):
                hr.local_path(name)
        raw = b'{"order":{"q":1}}'
        result = hr.report(raw, hr.sha(raw), '/order')
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / 'new'
            hr.save(output, result, raw)
            self.assertEqual((output / 'source.json').read_bytes(), raw)
            self.assertEqual(hr.strict_json((output / 'receipt.json').read_bytes()), result)
            with self.assertRaises(FileExistsError):
                hr.save(output, result, raw)
            with self.assertRaises(ValueError):
                hr.save(ROOT / 'disallowed-test-output', result, raw)

    def test_cli_only_metadata_and_full_private_artifact(self):
        raw = b'{"selected":{"accountNumber":"DO-NOT-DISPLAY","type":"market","dollars":"17.25"}}'
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / 'source.json'; source.write_bytes(raw)
            output = Path(temp) / 'private'
            command = [sys.executable, '-B', str(ROOT / 'scripts/handoff_report.py'),
                       '--source', str(source), '--expected-sha256', hr.sha(raw),
                       '--pointer', '/selected', '--private-output-dir', str(output)]
            process = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(process.returncode, 0, process.stderr)
            self.assertNotIn('DO-NOT-DISPLAY', process.stdout + process.stderr)
            self.assertTrue(json.loads(process.stdout)['private_payloads_omitted'])
            result = hr.strict_json((output / 'receipt.json').read_bytes())
            self.assertEqual(result['handoff']['payload']['accountNumber'], 'DO-NOT-DISPLAY')
            retry = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(retry.returncode, 2)
            self.assertIn('native execution permissions unchanged', retry.stderr)
            self.assertNotIn('DO-NOT-DISPLAY', retry.stdout + retry.stderr)

    def test_save_rejects_changed_or_missing_retained_bytes_before_creating_directory(self):
        raw = b'{"quantity":"1","accountId":"PRIVATE-A"}'
        compared = b'{"quantity":"2","accountId":"PRIVATE-B"}'
        ordinary = hr.report(raw, hr.sha(raw), '')
        comparison = hr.report(raw, hr.sha(raw), '', comparison_raw=compared,
                               comparison_sha256=hr.sha(compared), comparison_pointer='')
        # Even a formatting-only change fails byte binding; no partial export.
        cases = [(ordinary, raw + b'\n', None, 'RETAINED_SOURCE_HASH_MISMATCH'),
                 (ordinary, raw, compared, 'RETAINED_COMPARISON_PRESENCE_MISMATCH'),
                 (comparison, raw, None, 'RETAINED_COMPARISON_PRESENCE_MISMATCH'),
                 (comparison, raw, compared + b'\n', 'RETAINED_COMPARISON_HASH_MISMATCH')]
        with tempfile.TemporaryDirectory() as temp:
            for i, (receipt, source_bytes, comparison_bytes, reason) in enumerate(cases):
                output = Path(temp) / str(i)
                with self.subTest(reason=reason), self.assertRaisesRegex(ValueError, reason):
                    hr.save(output, receipt, source_bytes, comparison_bytes)
                self.assertFalse(output.exists())
            valid = Path(temp) / 'valid'
            hr.save(valid, comparison, raw, compared)
            self.assertEqual((valid / 'source.json').read_bytes(), raw)
            self.assertEqual((valid / 'comparison.json').read_bytes(), compared)
            retained = hr.strict_json((valid / 'receipt.json').read_bytes())
            self.assertEqual(retained['source']['artifact_sha256'], hr.sha(raw))
            self.assertEqual(retained['comparison']['source']['artifact_sha256'], hr.sha(compared))


if __name__ == '__main__':
    unittest.main()
