import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import analyst_evidence
import analyst_report as ar
from report_facts import digest, pointer


class AnalystReportTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        data = b'Fictional analyst excerpt. Targets and performance are supplied test values.'
        (self.root / 'source.txt').write_bytes(data)
        self.source = {'path': 'source.txt', 'sha256': hashlib.sha256(data).hexdigest(),
                       'url': 'https://fiction.example/record', 'published_at': '2026-10-01T12:00:00Z',
                       'observed_at': '2026-10-01T12:00:00Z', 'locator': 'paragraph 1',
                       'verbatim_excerpt': 'Fictional analyst excerpt.'}
        self.request = {'as_of': '2026-10-12T15:00:00Z', 'issuer': 'EXAMPLE', 'currency': 'USD',
                        'price_basis': 'current_common_share', 'target_horizon': 'forward_12_months',
                        'individual_targets': [], 'provider_consensus': [], 'analyst_track_records': []}

    def target(self, firm, value, **extra):
        row = {key: self.request[key] for key in ('issuer', 'currency', 'price_basis', 'target_horizon')}
        row.update(record_id=firm, firm_id=firm, analyst_id=firm + '-analyst', target=value,
                   issued_at='2026-10-01T12:00:00Z', access='ATTRIBUTED_EXCERPT', source=copy.deepcopy(self.source))
        row.update(extra)
        return row

    def run_report(self, document=None):
        raw = json.dumps(self.request if document is None else document).encode()
        return ar.run(raw, self.root)

    def test_result_is_exact_existing_helper_output_and_every_present_fact_resolves(self):
        self.request['individual_targets'] = [self.target('a', 80), self.target('b', 130),
                                               self.target('denied', 900, access='PAYWALL')]
        expected = analyst_evidence.review(copy.deepcopy(self.request), self.root)
        report = self.run_report()
        self.assertEqual(report['artifact']['cohorts'][0]['result'], expected)
        self.assertEqual(report['artifact']['cohorts'][0]['result_sha256'], digest(expected))
        self.assertEqual(report['artifact']['input'], self.request)
        self.assertEqual(report['source_artifact_sha256'], hashlib.sha256(ar.canonical_bytes(report['artifact'])).hexdigest())
        for fact in report['facts']:
            self.assertEqual(fact['source']['artifact_sha256'], report['source_artifact_sha256'])
            if fact['missingness'] != 'absent':
                self.assertEqual(pointer(report['artifact'], fact['source']['pointer']), fact['value'])
        self.assertTrue(any(f['value'] == 'REPORT_NOT_ACCESSED' for f in report['facts']))
        self.assertTrue(any(f['value'] == 900 and f['semantic_mapping'] == 'SUPPLIED_RECORD' for f in report['facts']))

    def test_two_explicit_horizons_never_mix_and_provider_pool_stays_separate(self):
        self.request['individual_targets'] = [self.target('a', 91), self.target('b', 151, target_horizon='forward_52_weeks')]
        self.request['provider_consensus'] = [{'provider': 'pool', 'mean': 500, 'target_count': 30,
                                              'source': copy.deepcopy(self.source), 'target_horizon': 'unknown'}]
        other = copy.deepcopy(self.request)
        other['target_horizon'] = 'forward_52_weeks'
        envelope = {'cohorts': [{'cohort_id': 'months', 'request': self.request},
                                 {'cohort_id': 'weeks', 'request': other}]}
        report = self.run_report(envelope)
        results = [c['result'] for c in report['artifact']['cohorts']]
        self.assertEqual([r['consensus']['median'] for r in results], [91, 151])
        self.assertTrue(all(r['consensus']['independent_firms'] == 1 for r in results))
        self.assertTrue(all(r['provider_consensus'][0]['mean'] == 500 for r in results))
        medians = [f for f in report['facts'] if f['metric'] == 'Observed forward target median']
        self.assertEqual([f['horizon'] for f in medians], ['forward_12_months', 'forward_52_weeks'])
        provider = [f for f in report['facts'] if f['context']['evidence_role'] == 'separate_provider_pool']
        self.assertTrue(all(f['horizon'] == 'unknown' for f in provider))

    def test_fair_value_and_historical_range_are_explicit_supplied_context(self):
        self.request['individual_targets'] = [self.target('a', 122)]
        envelope = {'cohorts': [{'cohort_id': 'forward', 'request': self.request}], 'supplemental_evidence': [
            {'kind': 'fair_value', 'record': {'value': 11, 'source': self.source}, 'as_of': self.request['as_of']},
            {'kind': 'historical_range', 'record': {'low': 2, 'high': 400}}]}
        report = self.run_report(envelope)
        self.assertEqual(report['artifact']['cohorts'][0]['result']['consensus']['median'], 122)
        self.assertEqual([s['status'] for s in report['artifact']['supplemental_evidence']],
                         ['LOCAL_EVIDENCE_CONSISTENT', 'SUPPLIED_ONLY'])
        for fact in report['facts']:
            if fact['context']['evidence_role'] in ('fair_value', 'historical_range'):
                self.assertEqual(fact['semantic_mapping'], 'SUPPLIED_CONTEXT_NOT_TARGET_CONSENSUS')
                self.assertFalse(fact['context']['included_in_target_calculation'])
        missing = [f for f in report['facts'] if f['source']['pointer'].endswith('/period_start')]
        self.assertEqual(missing[0]['missingness'], 'absent')
        self.assertIsNone(missing[0]['value'])

    def test_empty_evidence_and_track_record_missingness_are_visible_without_invented_numbers(self):
        self.request['analyst_track_records'] = [{'source': self.source, 'analyst_id': 'a', 'success_rate_pct': 62}]
        report = self.run_report()
        median = next(f for f in report['facts'] if f['metric'] == 'Observed forward target median')
        self.assertIsNone(median['value'])
        self.assertEqual(median['missingness'], 'absent')
        missing_count = next(f for f in report['facts'] if f['source']['pointer'].endswith('/analyst_track_records/0/recommendation_count'))
        self.assertEqual(missing_count['missingness'], 'absent')
        stat = report['artifact']['cohorts'][0]['result']['analyst_track_records'][0]
        self.assertIsNone(stat['selection_weight'])
        self.assertFalse(stat['independently_reproduced'])

    def test_stale_quote_null_differs_from_absent_and_dates_survive(self):
        self.request['individual_targets'] = [self.target('a', 122)]
        self.request['quote'] = {'issuer': 'EXAMPLE', 'currency': 'USD', 'price_basis': 'current_common_share',
                                 'price': 100, 'source': self.source}
        report = self.run_report()
        implied = next(f for f in report['facts'] if f['metric'].startswith('Median target implied'))
        self.assertIsNone(implied['value'])
        self.assertEqual(implied['missingness'], 'null')
        published = [f for f in report['facts'] if f['source']['pointer'] == '/input/quote/source/published_at']
        self.assertEqual(len(published), 1)
        self.assertEqual(published[0]['value'], self.source['published_at'])

    def test_source_tamper_changes_helper_exclusion_without_loss_of_original_row(self):
        self.request['individual_targets'] = [self.target('a', 120)]
        (self.root / 'source.txt').write_text('Different bytes', encoding='utf-8')
        report = self.run_report()
        result = report['artifact']['cohorts'][0]['result']
        self.assertEqual(result['consensus']['status'], 'UNAVAILABLE')
        self.assertEqual(result['excluded'][0]['reason'], 'Evidence bytes/hash mismatch')
        self.assertEqual(report['artifact']['input']['individual_targets'][0]['target'], 120)

    def test_strict_input_and_ambiguous_cohort_identifiers_rejected(self):
        for raw in (b'{"cohorts":[],"cohorts":[]}', b'{"n":NaN}', b'{"n":1e999}', b'[]'):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                ar.run(raw, self.root)
        envelope = {'cohorts': [{'cohort_id': 'same', 'request': self.request}] * 2}
        with self.assertRaisesRegex(ValueError, 'DUPLICATE_COHORT_ID'):
            self.run_report(envelope)

    def test_private_cli_bundle_no_stdout_no_overwrite_and_escaped_source_text(self):
        self.request['source_discovery'] = [{'access': 'NOT_ATTEMPTED', 'reason': '<script>x</script> | [link](https://bad.example)'}]
        source, output = self.root / 'input.json', self.root / 'output'
        source.write_text(json.dumps(self.request), encoding='utf-8')
        cmd = [sys.executable, str(Path(ar.__file__)), str(source), str(self.root), '--private-output', str(output)]
        result = subprocess.run(cmd, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, '')
        report = json.loads((output / 'bundle.json').read_text(encoding='utf-8'))
        self.assertEqual(report['artifact']['input'], self.request)
        rendered = (output / 'report.md').read_text(encoding='utf-8')
        self.assertNotIn('<script>', rendered)
        self.assertNotIn('[link]', rendered)
        original = (output / 'bundle.json').read_bytes()
        retry = subprocess.run(cmd, capture_output=True, text=True)
        self.assertEqual(retry.returncode, 2)
        self.assertEqual(retry.stdout, '')
        self.assertNotIn('bad.example', retry.stderr)
        self.assertEqual((output / 'bundle.json').read_bytes(), original)
        with self.assertRaisesRegex(ValueError, 'OUTSIDE_SKILL'):
            ar.export(report, ar.ROOT / 'disallowed-output')

    def test_malformed_source_cli_fails_without_traceback_or_private_values(self):
        row = self.target('PRIVATE_RECORD_SENTINEL', 120)
        row['source']['url'] = None
        self.request['individual_targets'] = [row]
        source, output = self.root / 'input.json', self.root / 'invalid'
        source.write_text(json.dumps(self.request), encoding='utf-8')
        result = subprocess.run([sys.executable, str(Path(ar.__file__)), str(source), str(self.root),
                                 '--private-output', str(output)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, '')
        self.assertNotIn('Traceback', result.stderr)
        self.assertNotIn('PRIVATE_RECORD_SENTINEL', result.stderr)
        self.assertFalse(output.exists())


if __name__ == '__main__':
    unittest.main()
