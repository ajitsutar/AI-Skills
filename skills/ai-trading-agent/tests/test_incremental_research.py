"""Portable partial-fetch behavior with fictional retained sources; no network."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import incremental_research as incremental
import public_research_fetch as fetch
from research_memory import digest, file_hash, seal


class PartialFetchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.parent = self.root / 'parent'; self.parent.mkdir()
        self.current = self.root / 'current'; self.current.mkdir()
        self.output = self.root / 'output'; self.output.mkdir()
        (self.output / 'raw').mkdir()
        self.start = '2026-10-22T20:00:00Z'
        self.end = '2026-10-22T20:10:00Z'
        self.identity = {'symbol': 'DEMO', 'issuer_id': 'fictional:demo', 'name': 'Current name'}
        self.component = {'index': ['Revenue'], 'columns': ['2026-06-30', '2026-03-31'],
                          'data': [[100, 90]]}
        self.old_time = '2026-10-21T20:05:00Z'
        self.metadata = {'provider': 'yfinance-quarterly', 'currency': 'USD',
                         'units': 'currency_units', 'periodicity': 'quarterly',
                         'scope': 'consolidated', 'mapping_basis': 'fictional complete source mapping'}
        self.write(self.parent / 'index.json', {'latest': '2026-06-30', 'revision': 'v1'})
        self.write(self.current / 'index.json', {'latest': '2026-06-30', 'revision': 'v1'})
        old_check = self.check(self.parent, '2026-10-21T20:04:00Z')
        self.old_row = {**self.identity, 'provider_symbol': 'DEMO', 'errors': [],
                        'info': {'financialCurrency': 'USD'},
                        'component_retrieved_at': {k: self.old_time for k in incremental.STATEMENTS},
                        'component_source_checks': {k: copy.deepcopy(old_check) for k in incremental.STATEMENTS},
                        **{k: copy.deepcopy(self.component) for k in incremental.STATEMENTS}}
        self.old_snapshot = {'profile_sha256': 'profile',
                             'contract': {'decision_at': '2026-10-21T20:00:00Z'},
                             'completed_at': '2026-10-21T20:10:00Z', 'rows': [self.old_row]}
        self.write(self.parent / 'snapshot.json', self.old_snapshot)
        self.reseal()
        self.current_receipt = {'schema_version': 1, 'rows': [{**self.identity,
            'provider_symbol': 'DEMO', 'components': {k: self.check(self.current, '2026-10-22T20:01:00Z')
                                                    for k in incremental.STATEMENTS}}]}
        self.save_current()

    @staticmethod
    def write(path, data):
        path.write_text(json.dumps(data), encoding='utf-8')

    def check(self, root, checked_at):
        return {'component_sha256': digest(self.component), 'metadata': copy.deepcopy(self.metadata),
                'source_index': {'source_url': 'https://issuer.example/source-index',
                    'checked_at': checked_at, 'periods': self.component['columns'],
                    'latest_period': '2026-06-30',
                    'review_scope': 'latest_period_and_all_retained_revisions',
                    'releases': [{'period': p, 'release_id': 'filing:' + p,
                                  'revision_id': 'v1', 'amendment_status': 'none'}
                                 for p in self.component['columns']],
                    'evidence_path': 'index.json', 'evidence_sha256': file_hash(root / 'index.json')}}

    def reseal(self):
        manifest = seal(self.parent, {'run_id': 'fictional-parent',
            'as_of': '2026-10-21T20:10:00Z', 'hold': 'P1Y', 'universe': 'fictional',
            'artifacts': [{'path': p, 'kind': k, 'as_of': self.old_time}
                          for p, k in [('snapshot.json', 'snapshot'), ('index.json', 'filing')]]})
        self.write(self.parent / 'manifest.json', manifest)

    def save_current(self):
        self.write(self.current / 'checks.json', self.current_receipt)

    def context(self):
        return incremental.PartialFetch(self.parent, self.parent / 'manifest.json',
            self.current / 'checks.json', self.output, self.start)

    def choose(self, context=None, identity=None):
        return (context or self.context()).choose(identity or self.identity, 'profile', self.end)

    def test_explicit_unchanged_reuse_preserves_times_hashes_and_current_evidence(self):
        context = self.context()
        result = self.choose(context)
        self.assertEqual(set(result), set(incremental.STATEMENTS))
        retained = result['income']
        self.assertEqual(retained['retrieved_at'], self.old_time)
        self.assertEqual(retained['provenance']['component_sha256'], digest(self.component))
        self.assertEqual(retained['provenance']['parent_manifest_sha256'], context.parent_manifest_sha256)
        self.assertEqual(retained['provenance']['current_checked_at'], '2026-10-22T20:01:00Z')
        self.assertTrue((self.output / retained['source_check']['source_index']['evidence_path']).is_file())
        self.assertEqual(self.old_row['component_source_checks']['income']['source_index']['evidence_path'], 'index.json')

    def test_new_period_revision_amendment_or_metadata_forces_component_fresh(self):
        for mutation in ('period', 'revision', 'amendment', 'currency', 'units', 'provider', 'scope'):
            with self.subTest(mutation=mutation):
                saved = copy.deepcopy(self.current_receipt)
                check = self.current_receipt['rows'][0]['components']['income']
                if mutation == 'period':
                    check['source_index']['latest_period'] = '2026-09-30'
                elif mutation == 'revision':
                    check['source_index']['releases'][0]['revision_id'] = 'v2'
                elif mutation == 'amendment':
                    check['source_index']['releases'][0]['amendment_status'] = 'unknown'
                else:
                    check['metadata'][mutation] = 'changed'
                self.save_current()
                result = self.choose()
                self.assertNotIn('income', result)
                self.assertIn('cashflow', result)
                self.current_receipt = saved
                self.save_current()

    def test_corrupt_parent_or_current_source_bytes_falls_back(self):
        (self.parent / 'snapshot.json').write_text('{}', encoding='utf-8')
        context = self.context()
        self.assertEqual(context.status, 'FRESH_FETCH_FALLBACK')
        self.assertEqual(self.choose(context), {})
        self.write(self.parent / 'snapshot.json', self.old_snapshot)
        self.reseal()
        (self.current / 'index.json').write_text('changed', encoding='utf-8')
        self.assertEqual(self.choose(), {})

    def test_missing_cache_added_issuer_and_changed_mapping_fetch_fresh(self):
        missing = incremental.PartialFetch(None, None, None, self.output, self.start)
        self.assertEqual(self.choose(missing), {})
        self.assertEqual(self.choose(identity={'symbol': 'NEW', 'issuer_id': 'fictional:new'}), {})
        self.assertEqual(self.choose(identity={**self.identity, 'issuer_id': 'new-issuer'}), {})
        self.assertEqual(self.choose(identity={**self.identity, 'provider_symbol': 'CHANGED'}), {})

    def test_malformed_json_schemas_fall_back_instead_of_aborting_collection(self):
        for value in ([], None, 7, {'schema_version': 1, 'rows': 1},
                      {'schema_version': 1, 'rows': ['wrong']}):
            with self.subTest(receipt=value):
                self.write(self.current / 'checks.json', value)
                self.assertEqual(self.choose(), {})
        self.save_current()
        self.current_receipt['rows'][0]['components']['income']['source_index']['releases'] = [1, 2]
        self.save_current()
        self.assertNotIn('income', self.choose())
        self.write(self.parent / 'manifest.json', [])
        self.assertEqual(self.choose(), {})

    def test_old_future_or_incomplete_source_observation_is_not_fresh(self):
        for value in ('2026-10-21T20:01:00Z', '2026-10-23T20:00:00Z', '2026-10-22T20:01:00'):
            self.current_receipt['rows'][0]['components']['income']['source_index']['checked_at'] = value
            self.save_current()
            self.assertNotIn('income', self.choose())

    def test_unsealed_baseline_source_and_missing_retrieval_time_never_reuse(self):
        self.old_snapshot['rows'][0]['component_retrieved_at'].pop('income')
        self.write(self.parent / 'snapshot.json', self.old_snapshot)
        self.reseal()
        self.assertNotIn('income', self.choose())
        manifest = seal(self.parent, {'run_id': 'parent', 'as_of': '2026-10-21T20:10:00Z',
            'hold': 'P1Y', 'universe': 'fictional', 'artifacts': [
                {'path': 'snapshot.json', 'kind': 'snapshot', 'as_of': self.old_time}]})
        self.write(self.parent / 'manifest.json', manifest)
        self.assertEqual(self.choose(), {})

    def test_parent_retrieval_chronology_and_recursive_reuse_provenance(self):
        row = self.old_snapshot['rows'][0]
        row['component_retrieved_at']['income'] = '2026-10-22T19:00:00Z'
        self.write(self.parent / 'snapshot.json', self.old_snapshot); self.reseal()
        self.assertNotIn('income', self.choose())
        inherited_time = '2026-10-20T20:05:00Z'
        row['component_retrieved_at']['income'] = inherited_time
        self.write(self.parent / 'snapshot.json', self.old_snapshot); self.reseal()
        self.assertNotIn('income', self.choose())
        row['component_acquisition'] = {'income': {
            'acquisition': 'source_checked_reuse', 'original_retrieved_at': inherited_time,
            'component_sha256': digest(self.component), 'current_checked_at': '2026-10-21T20:04:00Z',
            'parent_manifest_sha256': 'fictional-earlier-manifest',
            'parent_snapshot_sha256': 'fictional-earlier-snapshot'}}
        self.write(self.parent / 'snapshot.json', self.old_snapshot); self.reseal()
        self.assertEqual(self.choose()['income']['retrieved_at'], inherited_time)

    def test_parent_manifest_and_snapshot_window_are_coherent(self):
        for changed in ('snapshot-start-after-end', 'snapshot-completes-after-seal', 'seal-after-new-decision'):
            with self.subTest(changed=changed):
                saved = copy.deepcopy(self.old_snapshot)
                if changed == 'snapshot-start-after-end':
                    self.old_snapshot['contract']['decision_at'] = '2026-10-21T20:11:00Z'
                elif changed == 'snapshot-completes-after-seal':
                    self.old_snapshot['completed_at'] = '2026-10-21T20:11:00Z'
                self.write(self.parent / 'snapshot.json', self.old_snapshot); self.reseal()
                if changed == 'seal-after-new-decision':
                    path = self.parent / 'manifest.json'
                    manifest = json.loads(path.read_text(encoding='utf-8'))
                    manifest['as_of'] = '2026-10-22T20:11:00Z'
                    manifest.pop('manifest_sha256')
                    manifest['manifest_sha256'] = digest(manifest)
                    self.write(path, manifest)
                self.assertEqual(self.choose(), {})
                self.old_snapshot = saved

    def provider(self, currency='USD'):
        ticker = Mock()
        ticker.get_info.return_value = {'sector': 'Industrials', 'financialCurrency': currency,
                                        'regularMarketPrice': 25}
        return ticker, types.SimpleNamespace(Ticker=Mock(return_value=ticker))

    def collect(self, reusable=None, checks=None, currency='USD'):
        ticker, provider = self.provider(currency)
        grid = [{'date': '2025-10-22'}, {'date': '2026-10-21'}]
        with patch.dict(sys.modules, {'yfinance': provider}), \
             patch.object(fetch, 'request_call', side_effect=lambda call: call()), \
             patch.object(fetch, 'frame', return_value=copy.deepcopy(self.component)), \
             patch.object(fetch, 'now', return_value=self.end):
            row = fetch.fetch_row(self.identity, grid, self.output,
                                  reusable=reusable, source_checks=checks)
        return ticker, row

    def test_fake_provider_partial_only_skips_unchanged_statements(self):
        context = self.context()
        ticker, row = self.collect(self.choose(context), context)
        ticker.get_info.assert_called_once()
        ticker.history.assert_called_once()
        ticker.get_income_stmt.assert_not_called()
        ticker.get_balance_sheet.assert_not_called()
        ticker.get_cash_flow.assert_not_called()
        self.assertFalse(ticker.history.call_args.kwargs['auto_adjust'])
        self.assertTrue(ticker.history.call_args.kwargs['actions'])
        self.assertEqual(row['name'], 'Current name')
        self.assertEqual(row['component_retrieved_at']['income'], self.old_time)
        self.assertEqual(row['component_retrieved_at']['info'], self.end)
        self.assertEqual(context.receipt([row])['reused_statement_components'], 3)
        self.assertEqual(context.receipt([row])['outside_collector'], ['estimates', 'news', 'events'])

    def test_full_fetch_default_downloads_every_component(self):
        ticker, row = self.collect()
        ticker.get_info.assert_called_once()
        ticker.history.assert_called_once()
        ticker.get_income_stmt.assert_called_once()
        ticker.get_balance_sheet.assert_called_once()
        ticker.get_cash_flow.assert_called_once()
        self.assertNotIn('component_source_checks', row)
        self.assertTrue(all(v['acquisition'] == 'fresh_network_pull'
                            for v in row['component_acquisition'].values()))

    def test_fresh_provider_currency_change_invalidates_reuse(self):
        context = self.context()
        ticker, row = self.collect(self.choose(context), context, currency='EUR')
        ticker.get_income_stmt.assert_called_once()
        ticker.get_balance_sheet.assert_called_once()
        ticker.get_cash_flow.assert_called_once()
        self.assertNotIn('component_source_checks', row)
        self.assertEqual(context.receipt([row])['reused_statement_components'], 0)

    def test_full_fetch_can_bind_checked_source_baseline_for_future_opt_in(self):
        context = incremental.PartialFetch(None, None, self.current / 'checks.json',
            self.output, self.start, baseline_only=True)
        ticker, row = self.collect(checks=context)
        ticker.get_income_stmt.assert_called_once()
        self.assertEqual(set(row['component_source_checks']), set(incremental.STATEMENTS))
        self.assertEqual(row['component_retrieved_at']['income'], self.end)
        self.assertEqual(context.receipt([row])['mode'], 'full_fetch_with_optional_source_checks')

    def test_cli_requires_explicit_opt_in_and_distinguishes_resume(self):
        parser = fetch.argument_parser()
        args = parser.parse_args(['--output', 'new', '--decision-at', self.start,
                                 '--hold', 'P1Y', '--prompt-file', 'prompt.txt'])
        self.assertFalse(args.partial_fetch)
        self.assertIsNone(args.reuse_from)
        args = parser.parse_args(['--output', 'new', '--decision-at', self.start,
            '--hold', 'P1Y', '--prompt-file', 'prompt.txt', '--partial-fetch'])
        self.assertTrue(args.partial_fetch)
        with patch.object(sys, 'argv', ['fetch', '--output', 'new', '--decision-at', self.start,
            '--hold', 'P1Y', '--prompt-file', 'prompt.txt', '--partial-fetch', '--resume']):
            with self.assertRaisesRegex(ValueError, 'RESUME_AND_NEW_RUN'):
                fetch.main()


if __name__ == '__main__':
    unittest.main()
