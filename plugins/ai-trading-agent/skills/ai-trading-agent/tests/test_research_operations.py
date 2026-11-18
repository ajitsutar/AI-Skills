import copy
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import io
from contextlib import redirect_stdout
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import institutional_research as research
import market_sources
import research_operations as operations


AT = '2026-11-12T14:00:00+00:00'
URL = 'https://cdn.cboe.com/resources/us/equities/market-statistics/short-interest/example.csv'
CSV = b'Settlement Date,Symbol,Current Short,Avg Daily Volume,Days to Cover\n20261030,DEMO,100,50,2\n'


@contextmanager
def private_directory():
    temporary = tempfile.TemporaryDirectory()
    # Cleanup needs the same native spelling for deep Windows lock archives.
    temporary.name = str(operations._root(temporary.name))
    try:
        yield temporary.name
    finally:
        temporary.cleanup()


def config(sources=False):
    return {'schema_version': 1, 'workflow': {
        'id': 'fictional-research-workflow', 'research_question': 'Evaluate explicit supplied event evidence.',
        'universe': {'mode': 'explicit_symbols', 'symbols': ['DEMO']},
        'horizon': {'label': '1 to 5 trading days', 'entry_policy': 'Paper scenario only', 'exit_policy': 'Explicit later review'},
        'reviewer': {'id': 'human-reviewer', 'role': 'Human usefulness reviewer'},
        'study': {'registered_at': '2026-11-01T12:00:00+00:00', 'start_at': '2026-11-02T12:00:00+00:00',
                  'end_at': '2026-12-01T12:00:00+00:00', 'usefulness_criterion': 'Identify a traceable material evidence gap.',
                  'workflow_baseline_id': 'manual-review'}},
        'sources': [{'id': 'official-example', 'url': URL, 'adapter': 'finra_short_interest_csv',
                     'user_agent': 'ResearchTest https://example.org/contact', 'rights': 'fictional_test_only'}] if sources else [],
        'freshness': {'max_capture_age_seconds': 3600}}


def document():
    return {'schema_version': 1, 'as_of': AT, 'records': [{
        'id': 'supplied-1', 'kind': 'catalyst', 'ticker': 'DEMO', 'available_at': AT,
        'source': {'id': 'supplied-example', 'url': 'https://example.org/fictional-event',
                   'retrieved_at': AT, 'observed_at': AT, 'published_at': None,
                   'availability_basis': 'first_observed_snapshot', 'access': 'public', 'rights': 'synthetic_only'},
        'payload': {'title': 'Fictional event', 'event_type': 'earnings'}}],
        'event': {'id': 'fictional-event', 'ticker': 'DEMO', 'decision_at': AT,
                  'review_at': '2026-11-13T14:00:00+00:00'},
        'portfolio': {'as_of': AT, 'currency': 'USD', 'total_value': 100000,
                      'cash': 100000, 'positions': [], 'completeness': 'full'}}


def fake_acquire(url, output_dir, source_id, user_agent, rights, max_bytes, timeout, retries):
    target = Path(output_dir)
    target.mkdir()
    (target / 'attempt-01.raw').write_bytes(CSV)
    sha = hashlib.sha256(CSV).hexdigest()
    m = {'schema_version': 1, 'status': 'ACQUIRED', 'request_url': url, 'source_id': source_id,
         'raw_file': 'attempt-01.raw', 'raw_sha256': sha, 'available_at': AT, 'finished_at': AT,
         'source': {'id': source_id, 'url': url, 'retrieved_at': AT, 'observed_at': AT,
                    'published_at': None, 'availability_basis': 'first_observed_snapshot',
                    'access': 'public', 'rights': rights},
         'attempts': [{'http_status': 200, 'raw_complete': True, 'final_url': url,
                       'raw_file': 'attempt-01.raw', 'retained_bytes': len(CSV), 'raw_sha256': sha}]}
    (target / 'manifest.json').write_text(json.dumps(m), encoding='utf-8')
    return m


class ResearchOperationsTests(unittest.TestCase):
    def root(self, folder, sources=False):
        root = Path(folder) / 'private'
        root.mkdir()
        operations.register(root, config(sources))
        return root

    def test_competing_benchmark_context_survives_process_selection(self):
        package = Path(__file__).resolve().parents[1]
        fixture = json.loads((package / 'examples/market-flow-synthetic.json').read_text(encoding='utf8'))
        fixture.update(event={'ticker': 'DEMO', 'decision_at': fixture['as_of']}, include_flow_analysis=True)
        benchmark = next(r for r in fixture['records'] if r['id'] == 'benchmark')
        for variant in ('conflicting-active', 'identical-active', 'future-conflict'):
            with self.subTest(variant=variant), private_directory() as folder:
                root = self.root(folder)
                operations.collect(root, variant)
                value = copy.deepcopy(fixture)
                competitor = copy.deepcopy(benchmark)
                competitor['id'] = 'second-benchmark'
                if variant != 'identical-active':
                    competitor['payload']['end_price'] = '110'
                if variant == 'future-conflict':
                    competitor['available_at'] = '2026-11-12T21:00:00Z'
                    competitor['source'].update(observed_at=competitor['available_at'], retrieved_at=competitor['available_at'])
                value['records'].append(competitor)
                direct = research.brief(dict(value, workflow=config()['workflow']))
                operations.process(root, variant, operations._bytes(value))
                saved = json.loads((root / 'runs' / variant / 'process/brief-first.json').read_text(encoding='utf8'))
                linked = lambda result: next(row for row in result['flow']['cumulative_bars'] if row['record_id'] == 'current')
                self.assertEqual(linked(saved)['benchmark_relative_return_percent'], linked(direct)['benchmark_relative_return_percent'])
                if variant == 'conflicting-active':
                    self.assertIsNone(linked(saved)['benchmark_relative_return_percent'])
                    self.assertTrue(any(issue['code'] == 'CONFLICTING_FEED_IDENTITY_REQUIRES_REVISION' for issue in saved['flow']['issues']))
                else:
                    self.assertEqual(linked(saved)['benchmark_relative_return_percent'], 5.0)
                self.assertEqual(operations.verify(root, variant)['status'], 'RETAINED_RESEARCH_RUN_VERIFIED')

    def test_transitive_implementation_change_requires_new_registered_root(self):
        with private_directory() as folder:
            package = Path(folder) / 'implementation'
            scripts = package / 'scripts'
            scripts.mkdir(parents=True)
            (package / 'PACKAGE-MANIFEST.json').write_text('{}', encoding='utf8')
            dependency = scripts / 'market_flow.py'
            dependency.write_text('version = 1\n', encoding='utf8')
            with patch.object(operations, 'ROOT', package):
                root = self.root(folder)
                registered = json.loads((root / 'registration.json').read_text(encoding='utf8'))
                self.assertIn('scripts/market_flow.py', registered['software_sha256'])
                dependency.write_text('version = 2\n', encoding='utf8')
                with self.assertRaisesRegex(ValueError, 'SOFTWARE_BINDING_CHANGED'):
                    operations.collect(root, 'changed-implementation')

    def test_retained_parse_failure_stays_visible_after_raw_only_resume(self):
        with private_directory() as folder:
            root = self.root(folder, True)
            parser = market_sources.parse
            def transient_then_success(document):
                if not getattr(transient_then_success, 'failed', False):
                    transient_then_success.failed = True
                    raise ValueError('temporary parser dependency unavailable')
                return parser(document)
            with patch.object(market_sources, 'acquire', side_effect=fake_acquire) as fetch:
                with patch.object(market_sources, 'parse', side_effect=transient_then_success):
                    failed = operations.collect(root, 'parse-resume')
                    self.assertEqual(failed['status'], 'COLLECTED_WITH_GAPS')
                    recovered = operations.collect(root, 'parse-resume')
                self.assertEqual(fetch.call_count, 1)
            self.assertEqual(recovered['status'], 'COLLECTED')
            self.assertTrue(any(f['status'] == 'RETAINED_PARSE_FAILURE' for f in recovered['failures']))
            observed = operations.status(root, AT)
            self.assertIsNotNone(observed['last_failure'])
            self.assertIn('temporary parser dependency unavailable', observed['last_failure']['error'])
            self.assertTrue(observed['failures'])

    def test_registration_is_immutable_and_has_no_execution_authority(self):
        with private_directory() as folder:
            root = self.root(folder)
            first = (root / 'registration.json').read_bytes()
            self.assertFalse(operations.register(root, config())['execution_authorized'])
            self.assertEqual(first, (root / 'registration.json').read_bytes())
            changed = config(); changed['workflow']['horizon']['label'] = 'Different declared horizon'
            with self.assertRaisesRegex(ValueError, 'IMMUTABLE_CONFIG'):
                operations.register(root, changed)
            self.assertEqual(first, (root / 'registration.json').read_bytes())
            self.assertTrue(list((root / 'failures').glob('*.json')))

    def test_boolean_schema_and_typed_configuration_changes_are_not_equal(self):
        with private_directory() as folder:
            root = Path(folder) / 'typed'; root.mkdir()
            bad = config(); bad['schema_version'] = True
            with self.assertRaisesRegex(ValueError, 'CONFIG_SCHEMA'):
                operations.register(root, bad)
            value = config(); value['workflow']['typed_declaration'] = 1
            operations.register(root, value)
            changed = copy.deepcopy(value); changed['workflow']['typed_declaration'] = True
            with self.assertRaisesRegex(ValueError, 'IMMUTABLE_CONFIG'):
                operations.register(root, changed)
            operations.collect(root, 'typed')
            envelope = document(); envelope['workflow'] = changed['workflow']
            with self.assertRaisesRegex(ValueError, 'REGISTERED_WORKFLOW_CONFLICT'):
                operations.process(root, 'typed', operations._bytes(envelope))

    def test_package_root_refused_with_normal_or_native_windows_spelling(self):
        package = Path(operations.__file__).resolve().parents[1]
        with self.assertRaisesRegex(ValueError, 'PRIVATE_ROOT_OUTSIDE_PACKAGE'):
            operations._root(package)
        if os.name == 'nt':
            native = '\\\\?\\' + str(package)
            with self.assertRaisesRegex(ValueError, 'PRIVATE_ROOT_OUTSIDE_PACKAGE'):
                operations._root(native)

    def test_typed_selected_payload_change_is_not_incremental_equality(self):
        full = document(); full['records'][0]['payload']['typed_value'] = 1
        changed = copy.deepcopy(full); changed['records'][0]['payload']['typed_value'] = True
        result = operations.compare_selected_records(full, changed, {'tickers': ['DEMO'], 'record_ids': []})
        self.assertFalse(result['equal'])

    def test_zero_eligible_parse_is_a_coverage_gap_with_counts(self):
        with private_directory() as folder:
            root = self.root(folder, True)
            for run_id, raw, eligible in [('unmapped', CSV.replace(b',DEMO,', b',,'), 1),
                                          ('invalid', CSV.replace(b',100,50,2', b',invalid,50,2'), 0)]:
                with self.subTest(run_id=run_id), patch(__name__ + '.CSV', raw):
                    with patch.object(market_sources, 'acquire', side_effect=fake_acquire):
                        result = operations.collect(root, run_id)
                    source = result['sources'][0]
                    self.assertEqual(source['status'], 'PARSED_WITH_GAPS')
                    self.assertEqual(source['eligible_records'], eligible)
                    self.assertEqual(source['ineligible_records'], 1 - eligible)
                    self.assertEqual(source['mapped_eligible_records'], 0)
                    self.assertIn('NO_MAPPED_TARGET_IDENTITIES', source['qualifications'])

    def test_cli_coverage_exit_is_distinct_from_disposition_and_integrity_success(self):
        with private_directory() as folder:
            root = self.root(folder)
            with redirect_stdout(io.StringIO()):
                self.assertEqual(operations.main(['collect', '--root', str(root), '--run-id', 'slot']), 2)
                value = {'schema_version': 1, 'as_of': AT, 'records': [],
                         'run_outcome': {'disposition': 'SOURCE_GAP', 'reason': 'No configured source.',
                                         'coverage': {'status': 'SOURCE_GAP', 'scope': 'Workflow', 'checked_at': AT}}}
                source = Path(folder) / 'disposition.json'; source.write_bytes(operations._bytes(value))
                self.assertEqual(operations.main(['process', '--root', str(root), '--run-id', 'slot', '--input', str(source)]), 0)
                self.assertEqual(operations.main(['verify', '--root', str(root), '--run-id', 'slot']), 0)

    def test_boolean_cannot_replace_a_retained_numeric_source_measurement(self):
        with private_directory() as folder:
            root = self.root(folder, True)
            with patch(__name__ + '.CSV', CSV.replace(b',100,50,2', b',1,50,2')):
                with patch.object(market_sources, 'acquire', side_effect=fake_acquire):
                    operations.collect(root, 'typed-source')
            row = operations._load(root / 'runs/typed-source/captures/official-example/attempt-0001/parsed.json')['records'][0]
            self.assertEqual(row['payload']['short_interest_shares'], 1)
            row['payload']['short_interest_shares'] = True
            value = document(); value['records'] = [row]
            with self.assertRaisesRegex(ValueError, 'NOT_BOUND_TO_RETAINED_PARSE'):
                operations.process(root, 'typed-source', operations._bytes(value))

    def test_sec_request_pacing_uses_bounded_sleep_and_retains_root_state(self):
        with private_directory() as folder:
            root = Path(folder)
            source = {'url': 'https://data.sec.gov/submissions/CIK0000000001.json'}
            clocks = ['2026-11-12T14:00:00+00:00', '2026-11-12T14:00:00.100000+00:00',
                      '2026-11-12T14:00:01+00:00']
            with patch.object(operations, '_now', side_effect=clocks), patch.object(operations.time, 'sleep') as sleep:
                operations._pace_public_request(root, source)
                operations._pace_public_request(root, source)
                sleep.assert_called_once_with(0.9)
            self.assertEqual(operations._load(root / 'sec-request-start.json')['started_at'], '2026-11-12T14:00:01+00:00')
            with patch.object(operations, '_now', return_value='2026-11-12T13:59:59+00:00'):
                with self.assertRaisesRegex(ValueError, 'CLOCK_BEFORE_LAST_REQUEST'):
                    operations._pace_public_request(root, source)

    def test_missing_user_agent_unsafe_url_and_incomplete_workflow_are_rejected(self):
        with private_directory() as folder:
            root = Path(folder)
            for alteration in ('ua', 'url', 'workflow'):
                value = config(True)
                if alteration == 'ua': value['sources'][0].pop('user_agent')
                if alteration == 'url': value['sources'][0]['url'] = 'https://example.org/not-allowlisted'
                if alteration == 'workflow': value['workflow']['reviewer'] = None
                with self.subTest(alteration=alteration), self.assertRaises(ValueError):
                    operations.register(root, value)
            self.assertFalse((root / 'registration.json').exists())

    def test_empty_sources_are_a_coverage_gap_not_a_green_feed(self):
        with private_directory() as folder:
            root = self.root(folder)
            with patch.object(market_sources, 'acquire', side_effect=AssertionError('Unexpected network')):
                self.assertEqual(operations.collect(root, 'empty')['status'], 'NO_CONFIGURED_SOURCES')
                result = operations.process(root, 'empty', operations._bytes(document()))
            self.assertEqual(result['status'], 'PROCESSED_SUPPLIED_ONLY_WITH_COVERAGE_GAPS')
            self.assertEqual(result['supplied_unacquired_record_ids'], ['supplied-1'])
            self.assertTrue(result['coverage_gaps'])
            self.assertEqual(operations.status(root, AT)['status'], 'NO_CONFIGURED_SOURCES')

    def test_explicit_source_gap_without_a_ticker_is_journaled_without_a_brief(self):
        with private_directory() as folder:
            root = self.root(folder); operations.collect(root, 'source-gap')
            value = {'schema_version': 1, 'as_of': AT, 'records': [],
                     'run_outcome': {'disposition': 'SOURCE_GAP', 'reason': 'No qualified automatic source.',
                                     'coverage': {'status': 'SOURCE_GAP', 'scope': 'Declared workflow', 'checked_at': AT}}}
            with patch.object(research, 'brief', side_effect=AssertionError('No investment brief for a source gap')):
                result = operations.process(root, 'source-gap', operations._bytes(value))
                self.assertEqual(operations.verify(root, 'source-gap')['status'], 'RETAINED_RESEARCH_RUN_VERIFIED')
            self.assertEqual(result['status'], 'RECORDED_SOURCE_GAP')
            self.assertEqual(result['selected_records'], 0)
            self.assertTrue((root / 'runs/source-gap/journal/entries/first-response-v1.json').exists())

    def test_empty_sources_or_undeclared_observation_cannot_become_no_event(self):
        with private_directory() as folder:
            root = self.root(folder); operations.collect(root, 'no-event')
            value = {'schema_version': 1, 'as_of': AT, 'records': [],
                     'run_outcome': {'disposition': 'NO_EVENT', 'reason': 'Claimed empty queue.',
                                     'observed_no_event': True,
                                     'coverage': {'status': 'COMPLETE_DECLARED_SCOPE', 'scope': 'Declared workflow',
                                                  'checked_at': AT, 'observed_source_ids': ['missing-source']}}}
            with self.assertRaisesRegex(ValueError, 'COMPLETE_SOURCE_OBSERVATION'):
                operations.process(root, 'no-event', operations._bytes(value))

    def test_successful_collection_is_reused_without_duplicate_get(self):
        with private_directory() as folder:
            root = self.root(folder, True)
            with patch.object(market_sources, 'acquire', side_effect=fake_acquire) as acquire:
                first = operations.collect(root, 'capture')
                second = operations.collect(root, 'capture')
                self.assertEqual(first, second)
                self.assertEqual(acquire.call_count, 1)
            self.assertEqual(first['status'], 'COLLECTED')

    def test_completed_download_resumes_parsing_without_another_get(self):
        with private_directory() as folder:
            root = self.root(folder, True)
            with patch.object(market_sources, 'acquire', side_effect=fake_acquire):
                operations.collect(root, 'resume')
            parsed = root / 'runs/resume/captures/official-example/attempt-0001/parsed.json'
            original = parsed.read_bytes(); parsed.unlink()
            with patch.object(market_sources, 'acquire', side_effect=AssertionError('Duplicate GET')):
                self.assertEqual(operations.collect(root, 'resume')['status'], 'COLLECTED')
            self.assertEqual(parsed.read_bytes(), original)

    def test_partial_http_body_never_becomes_usable_or_auto_retried(self):
        class Response:
            code = 200
            headers = {'Content-Length': '99999'}
            def __init__(self): self.done = False
            def geturl(self): return URL
            def read(self, size):
                if not self.done: self.done = True; return CSV
                return b''
            def close(self): pass
        class Opener:
            def open(self, request, timeout): return Response()
        with private_directory() as folder:
            root = self.root(folder, True)
            with patch.object(market_sources, 'build_opener', return_value=Opener()) as opener:
                first = operations.collect(root, 'partial')
                again = operations.collect(root, 'partial')
                self.assertEqual(opener.call_count, 1)
            self.assertEqual(first, again)
            self.assertEqual(first['sources'][0]['status'], 'ACQUISITION_FAILED')
            self.assertFalse((root / 'runs/partial/captures/official-example/attempt-0001/parsed.json').exists())
            source_doc = document(); source_doc['records'] = []
            self.assertEqual(operations.process(root, 'partial', operations._bytes(source_doc))['status'], 'ABSTENTION_NO_ELIGIBLE_EVIDENCE')
            with patch.object(market_sources, 'acquire', side_effect=fake_acquire) as acquire:
                good = operations.collect(root, 'partial', retry_failed=True)
                self.assertEqual(acquire.call_count, 1)
            self.assertEqual(good['status'], 'COLLECTED')
            self.assertEqual(len(good['sources'][0]['attempt_history']), 2)
            self.assertTrue(good['failures'])

    def test_incomplete_attempt_requires_explicit_retry_and_preserves_original(self):
        with private_directory() as folder:
            root = self.root(folder, True)
            with patch.object(market_sources, 'acquire', side_effect=OSError('Interrupted before manifest')) as acquire:
                failed = operations.collect(root, 'interrupted')
                operations.collect(root, 'interrupted')
                self.assertEqual(acquire.call_count, 1)
            self.assertEqual(failed['sources'][0]['status'], 'ACQUISITION_FAILED')
            with patch.object(market_sources, 'acquire', side_effect=fake_acquire):
                operations.collect(root, 'interrupted', True)
            self.assertTrue((root / 'runs/interrupted/captures/official-example/attempt-0001/call-error.json').exists())

    def test_configured_source_row_must_match_actual_retained_parse(self):
        with private_directory() as folder:
            root = self.root(folder, True)
            with patch.object(market_sources, 'acquire', side_effect=fake_acquire):
                operations.collect(root, 'bound')
            row = operations._load(root / 'runs/bound/captures/official-example/attempt-0001/parsed.json')['records'][0]
            value = document(); value['records'] = [row]
            row['payload']['short_interest_shares'] = 999999
            with self.assertRaisesRegex(ValueError, 'NOT_BOUND_TO_RETAINED_PARSE'):
                operations.process(root, 'bound', operations._bytes(value))
            self.assertFalse((root / 'runs/bound/process/brief-first.json').exists())

    def test_retained_raw_tamper_is_visible_and_never_falls_back_to_earlier_success(self):
        with private_directory() as folder:
            root = self.root(folder, True)
            with patch.object(market_sources, 'acquire', side_effect=fake_acquire):
                operations.collect(root, 'tamper')
            raw = root / 'runs/tamper/captures/official-example/attempt-0001/download/attempt-01.raw'
            raw.write_bytes(b'changed')
            with patch.object(market_sources, 'acquire', side_effect=AssertionError('Automatic retry')):
                result = operations.collect(root, 'tamper')
            self.assertEqual(result['sources'][0]['status'], 'INTEGRITY_ERROR')
            self.assertEqual(result['status'], 'COLLECTED_WITH_GAPS')
            self.assertEqual(operations.status(root, AT)['last_failure']['status'], 'INTEGRITY_ERROR')

    def test_latest_failed_attempt_does_not_get_masked_by_first_success(self):
        with private_directory() as folder:
            root = self.root(folder, True)
            with patch.object(market_sources, 'acquire', side_effect=fake_acquire): operations.collect(root, 'latest')
            attempt = root / 'runs/latest/captures/official-example/attempt-0002'
            attempt.mkdir(); (attempt / 'download').mkdir()
            operations._publish(attempt / 'planned.json', {'source_id': 'official-example', 'url': URL,
                                                          'started_at': AT, 'explicit_retry_failed': True})
            operations._publish(attempt / 'download/manifest.json', {'status': 'FAILED', 'request_url': URL,
                                'source_id': 'official-example', 'finished_at': AT, 'attempts': [{'error': 'HTTP_503'}]})
            with patch.object(market_sources, 'acquire', side_effect=AssertionError('Implicit GET')):
                result = operations.collect(root, 'latest')
            self.assertEqual(result['sources'][0]['status'], 'ACQUISITION_FAILED')
            self.assertEqual(result['sources'][0]['error'], 'HTTP_503')

    def test_process_restart_recovers_after_partial_artifact_publication(self):
        with private_directory() as folder:
            root = self.root(folder); operations.collect(root, 'recover')
            original = operations._publish
            fired = []
            def fail_after_plan(path, value):
                original(path, value)
                if path.name == 'plan.json' and not fired:
                    fired.append(True); raise OSError('Injected interruption after durable plan')
            with patch.object(operations, '_publish', side_effect=fail_after_plan):
                with self.assertRaisesRegex(OSError, 'Injected interruption'):
                    operations.process(root, 'recover', operations._bytes(document()))
            result = operations.process(root, 'recover', operations._bytes(document()))
            again = operations.process(root, 'recover', operations._bytes(document()))
            self.assertEqual(result, again)
            self.assertEqual(operations.verify(root, 'recover')['status'], 'RETAINED_RESEARCH_RUN_VERIFIED')
            self.assertTrue(operations.status(root, AT)['last_failure'])

    def test_registered_workflow_conflict_does_not_silently_override_input(self):
        with private_directory() as folder:
            root = self.root(folder); operations.collect(root, 'conflict')
            value = document(); value['workflow'] = config()['workflow']; value['workflow']['id'] = 'different'
            with self.assertRaisesRegex(ValueError, 'REGISTERED_WORKFLOW_CONFLICT'):
                operations.process(root, 'conflict', operations._bytes(value))

    def test_full_incremental_equality_checks_selected_eligible_payloads_and_cutoff(self):
        with private_directory() as folder:
            root = self.root(folder); operations.collect(root, 'compare')
            operations.process(root, 'compare', operations._bytes(document()))
            full = operations._load(root / 'runs/compare/process/assembled-input.json')
            equal = operations.verify(root, 'compare', copy.deepcopy(full))
            self.assertTrue(equal['incremental_comparison']['equal'])
            changed = copy.deepcopy(full); changed['records'][0]['payload']['title'] = 'Changed content'
            different = operations.verify(root, 'compare', changed)
            self.assertEqual(different['status'], 'INCREMENTAL_SELECTED_EVIDENCE_MISMATCH')
            late = copy.deepcopy(full); late['as_of'] = '2026-11-12T15:00:00+00:00'
            with self.assertRaisesRegex(ValueError, 'CUTOFF_MISMATCH'):
                operations.verify(root, 'compare', late)

    def test_newer_revision_cannot_disappear_from_incremental_selected_view(self):
        first = document(); first['records'][0]['available_at'] = '2026-11-12T13:00:00+00:00'
        first['records'][0]['source']['retrieved_at'] = '2026-11-12T13:00:00+00:00'
        first['records'][0]['source']['observed_at'] = '2026-11-12T13:00:00+00:00'
        revision = copy.deepcopy(first['records'][0]); revision.update(id='revision', action='replace', supersedes='supplied-1', available_at=AT)
        revision['source'].update(retrieved_at=AT, observed_at=AT); revision['payload']['title'] = 'New revision'
        full = copy.deepcopy(first); full['records'].append(revision)
        result = operations.compare_selected_records(full, first, {'tickers': ['DEMO'], 'record_ids': []})
        self.assertFalse(result['equal'])
        self.assertEqual(result['full_selected_eligible'][0]['id'], 'revision')

    def test_record_selection_does_not_pull_unrelated_tickers_through_missing_parent(self):
        full = document()
        unrelated = copy.deepcopy(full['records'][0]); unrelated.update(id='other', ticker='OTHER')
        full['records'].append(unrelated)
        result = operations.compare_selected_records(full, document(), {'tickers': ['DEMO'], 'record_ids': []})
        self.assertTrue(result['equal'])
        self.assertEqual([r['id'] for r in result['full_selected_eligible']], ['supplied-1'])

    def test_actual_abrupt_driver_exit_recovers_both_whole_run_and_child_journal(self):
        with private_directory() as folder:
            root = self.root(folder); operations.collect(root, 'crash')
            source = Path(folder) / 'input.json'; source.write_bytes(operations._bytes(document()))
            code = ('import os,sys;from pathlib import Path;sys.path.insert(0,sys.argv[1]);'
                    'import research_operations as o;import institutional_research as r;'
                    'r._complete=lambda root,transaction:os._exit(72);'
                    'o.process(sys.argv[2],"crash",Path(sys.argv[3]).read_bytes())')
            result = subprocess.run([sys.executable, '-X', 'utf8', '-B', '-c', code,
                                     str(Path(operations.__file__).parent), str(root), str(source)],
                                    capture_output=True, text=True, timeout=15,
                                    env=dict(os.environ, PYTHONDONTWRITEBYTECODE='1'))
            self.assertEqual(result.returncode, 72)
            child_root = root / 'runs/crash/journal'
            for locked_root in (root, child_root):
                self.assertTrue((locked_root / '.institutional.lock').exists())
            with self.assertRaisesRegex(ValueError, 'LOCK_HELD'):
                operations.process(root, 'crash', source.read_bytes())
            for locked_root in (child_root, root):
                token = (locked_root / '.institutional.lock').read_bytes()
                research._release_lock(operations._root(locked_root), hashlib.sha256(token).hexdigest(), True)
            operations.process(root, 'crash', source.read_bytes())
            self.assertEqual(operations.verify(root, 'crash')['status'], 'RETAINED_RESEARCH_RUN_VERIFIED')

    def test_capture_freshness_does_not_backdate_or_assert_market_measurement_freshness(self):
        with private_directory() as folder:
            root = self.root(folder, True)
            with patch.object(market_sources, 'acquire', side_effect=fake_acquire): operations.collect(root, 'fresh')
            old = operations.status(root, '2026-11-12T16:00:01+00:00')['runs'][0]['sources'][0]
            self.assertEqual(old['freshness'], 'STALE_CAPTURE')
            future = operations.status(root, '2026-11-12T13:59:59+00:00')['runs'][0]['sources'][0]
            self.assertEqual(future['freshness'], 'NOT_AVAILABLE_AT_CUTOFF')

    def test_actual_competing_process_is_refused_then_resumes_after_owner_exit(self):
        with private_directory() as folder:
            root = self.root(folder)
            ready = Path(folder) / 'ready'
            code = ('import sys;from pathlib import Path;sys.path.insert(0,sys.argv[1]);'
                    'import institutional_research as r\n'
                    'with r._lock(Path(sys.argv[2])):\n'
                    ' Path(sys.argv[3]).write_text("ready",encoding="utf-8")\n'
                    ' sys.stdin.readline()\n')
            env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1')
            child = subprocess.Popen([sys.executable, '-X', 'utf8', '-B', '-c', code,
                                      str(Path(operations.__file__).parent), str(root), str(ready)],
                                     stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                     text=True, env=env)
            try:
                deadline = time.monotonic() + 10
                while not ready.exists() and child.poll() is None and time.monotonic() < deadline: time.sleep(0.02)
                self.assertTrue(ready.exists())
                before = (root / '.institutional.lock').read_bytes()
                with self.assertRaisesRegex(ValueError, 'LOCK_HELD'):
                    operations.collect(root, 'overlap')
                self.assertEqual(before, (root / '.institutional.lock').read_bytes())
                self.assertFalse((root / 'runs').exists())
                child.communicate('\n', timeout=10)
                self.assertEqual(child.returncode, 0)
            finally:
                if child.poll() is None: child.kill(); child.communicate(timeout=10)
            self.assertEqual(operations.collect(root, 'overlap')['status'], 'NO_CONFIGURED_SOURCES')


if __name__ == '__main__':
    unittest.main()
