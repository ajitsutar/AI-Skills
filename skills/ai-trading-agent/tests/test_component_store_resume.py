"""Collector resume through the native CLI with retained fictional checkpoints."""
import contextlib
import copy
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import types
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import public_research as rank
import public_research_fetch as fetch
from test_gap15_store_recovery import child_collector, request, validate_request
from test_public_research import fixture


class CollectorStoreRecoveryTests(unittest.TestCase):
    def setUp(self):
        owned = tempfile.TemporaryDirectory()
        self.addCleanup(owned.cleanup)
        root = Path(owned.name).resolve()
        self.run_dir = root / 'run'
        self.source = fixture()
        self.rows = self.source['rows']
        self.grid = [{'date': day, 'close': day + 'T20:00:00Z'} for day in self.source['session_dates']]
        ids = [{key: row[key] for key in ('symbol', 'issuer_id')} for row in self.rows]
        supplied = root / 'universe.json'
        fetch.save(supplied, {'universe_id': 'FICTIONAL', 'source': 'fictional fixture', 'rows': ids})
        prompt = root / 'prompt.txt'
        prompt.write_text('Rank the supplied fictional universe.', encoding='utf-8')
        self.args = ['collect', '--output', str(self.run_dir), '--component-store', '--workers', '1',
                     '--hold', 'P1Y', '--decision-at', self.grid[-1]['close'], '--prompt-file', str(prompt)]
        self.ticker = Mock()
        self.ticker.history.return_value = self.rows[-1]['history']
        self.enter = contextlib.ExitStack()
        self.addCleanup(self.enter.close)
        self.enter.enter_context(patch.dict(os.environ, {'AI_TRADING_NETWORK_MODE': 'online'}))
        self.enter.enter_context(patch.object(fetch, 'sessions', return_value=self.grid))
        if 'yfinance' in sys.modules:
            self.addCleanup(sys.modules.__setitem__, 'yfinance', sys.modules['yfinance'])
        else:
            self.addCleanup(sys.modules.pop, 'yfinance', None)
        sys.modules['yfinance'] = types.SimpleNamespace(Ticker=lambda symbol: self.ticker)
        self.enter.enter_context(patch.object(fetch, 'frame', side_effect=lambda table, **kwargs: table))
        self.enter.enter_context(patch.object(fetch, 'request_call', side_effect=lambda provider: provider()))
        self.call('--universe', str(supplied), '--universe-only')

    def call(self, *extra):
        output = io.StringIO()
        with patch.object(sys, 'argv', self.args + list(extra)), contextlib.redirect_stdout(output):
            fetch.main()
        return output.getvalue()

    def legacy_checkpoint(self, *, poisoned=True):
        contract_path = self.run_dir / 'contract-before-fetch.json'
        original = json.loads(contract_path.read_bytes())
        original['acquisition_code_sha256'] = {
            'incremental_research.py': 'e212824f793f985ac8f970b31eda62d5b88dfe179c1209c8eb9acd2a026591cd',
            'listed_universe.py': '77bda29382d8f7e252cbc9ddc7c05fdb8751ceda258cd6e53e6a60dbd6f8ec09',
            'public_research_fetch.py': '8de8a128d43ac4a7682115ca03ce4d4cc0e4dc4205c29fb4accf51089a2b69c1',
            'research_data_store.py': '3f7252c02dd0d040566055bc373dafd703892ea41d2e40602b53965db4392a25'}
        original['acquisition'] = 'independent_fresh_network_pull'
        contract_path.write_text(json.dumps(original), encoding='utf-8')
        store = fetch.Store(self.run_dir / 'component-store', 'public-research-fetch:' + fetch.digest(original),
                            create=True, min_free_bytes=0)
        for row in self.rows[:-1]:
            fetch.save(self.run_dir / 'raw' / ('security-' + row['symbol'] + '.json'), dict(row, errors=[]))
        broken = dict(self.rows[-1], errors=[{'component': 'history', 'error': 'ValueError:ACTIVE_CAPTURE_LIMIT'}],
                      history={'columns': [], 'index': [], 'data': []})
        frozen = self.run_dir / 'retry-001/raw/security-DEMO9.json'
        frozen.parent.mkdir(parents=True)
        fetch.save(frozen, broken if poisoned else dict(self.rows[-1], errors=[]))
        return store, frozen

    def test_old_retry_preserved_and_resumed_on_reviewed_code(self):
        store, frozen = self.legacy_checkpoint()
        original_contract = (self.run_dir / 'contract-before-fetch.json').read_bytes()
        original_row = frozen.read_bytes()
        keys = [format(i, '064x') for i in range(4)]
        for key in keys:
            directory = store.path('locks/' + key + '.lock')
            directory.mkdir()
            old = time.time() - 3 * 86400
            os.utime(directory, (old, old))
        with self.assertRaisesRegex(fetch.StoreLockError, 'ACTIVE_CAPTURE_LIMIT'):
            self.call('--resume')
        self.assertFalse((self.run_dir / 'retry-002/snapshot.json').exists())
        incident = json.loads((self.run_dir / 'retry-002/component-store-blocked.json').read_bytes())
        self.assertIn('ACTIVE_CAPTURE_LIMIT', incident['reason'])
        self.ticker.history.assert_not_called()

        output = self.call('--resume', '--legacy-writers-stopped')
        retry = self.run_dir / 'retry-003'
        recovered = json.loads((retry / 'snapshot.json').read_bytes())
        receipt = json.loads((retry / 'component-store-lock-recovery.json').read_bytes())
        self.assertEqual(set(receipt['keys']), set(keys))
        self.assertEqual(receipt['count'], 4)
        self.assertIn('Component store locks reclaimed: 4', output)
        attempt = recovered['acquisition_attempt']
        self.assertEqual(attempt['prior_store_lock_failure_securities'], 1)
        self.assertEqual(attempt['complete_checkpoints_reused'], 9)
        self.assertEqual(attempt['collector_code_transition']['from'], recovered['contract']['acquisition_code_sha256'])
        self.assertEqual((self.run_dir / 'contract-before-fetch.json').read_bytes(), original_contract)
        self.assertEqual(frozen.read_bytes(), original_row)
        self.assertEqual(recovered['essential_acquisition_errors'], 0)
        self.ticker.history.assert_called_once()
        with patch('trading_calendar.sessions', return_value=self.grid):
            ranked = rank.make_bundle(recovered, 3)['result']
        self.assertEqual(ranked['scored_issuers'], 10)
        self.assertEqual(ranked['research_candidates'][0]['symbol'], 'DEMO9')
        self.assertEqual(receipt, attempt['component_store_lock_recovery'])

    def test_killed_collector_reclaims_four_owned_locks_then_completes_rank(self):
        store, prior = self.legacy_checkpoint()
        original = prior.read_bytes()
        symbols = ['ONE', 'TWO', 'THREE', 'FOUR']
        with child_collector(store.root, self.run_dir, symbols) as child:
            child.kill()
            child.wait(timeout=10)
        output = self.call('--resume')
        self.assertIn('Component store locks reclaimed: 4', output)
        snapshot = json.loads((self.run_dir / 'retry-002/snapshot.json').read_bytes())
        evidence = snapshot['acquisition_attempt']['component_store_lock_recovery']
        self.assertCountEqual(evidence['keys'], [validate_request(request(symbol)) for symbol in symbols])
        self.assertEqual({record['pid'] for record in evidence['records']}, {child.pid})
        self.assertEqual(snapshot['essential_acquisition_errors'], 0)
        self.assertEqual(prior.read_bytes(), original)
        self.ticker.history.assert_called_once()
        with patch('trading_calendar.sessions', return_value=self.grid):
            result = rank.make_bundle(snapshot, 3)['result']
        self.assertEqual(result['scored_issuers'], 10)

    def test_unpoisoned_checkpoint_reuses_complete_rows_without_provider_calls(self):
        self.legacy_checkpoint(poisoned=False)
        self.call('--resume')
        recovered = json.loads((self.run_dir / 'retry-002/snapshot.json').read_bytes())
        attempt = recovered['acquisition_attempt']
        self.assertEqual(attempt['component_store_lock_recovery']['count'], 0)
        self.assertEqual(attempt['complete_checkpoints_reused'], 10)
        self.assertEqual(attempt['prior_store_lock_failure_securities'], 0)
        self.ticker.history.assert_not_called()

    def test_unreviewed_source_pin_cannot_resume(self):
        self.legacy_checkpoint()
        path = self.run_dir / 'contract-before-fetch.json'
        original = json.loads(path.read_bytes())
        original['acquisition_code_sha256']['listed_universe.py'] = '0' * 64
        path.write_text(json.dumps(original), encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'RESUME_ACQUISITION_CODE_MISMATCH'):
            self.call('--resume', '--legacy-writers-stopped')
        self.assertFalse((self.run_dir / 'retry-002').exists())
        self.ticker.history.assert_not_called()

    def test_provider_failure_stays_a_component_gap(self):
        self.legacy_checkpoint()
        self.ticker.history.side_effect = RuntimeError('FICTIONAL_PROVIDER_TIMEOUT')
        self.call('--resume')
        snapshot = json.loads((self.run_dir / 'retry-002/snapshot.json').read_bytes())
        self.assertEqual(snapshot['essential_acquisition_errors'], 1)
        self.assertEqual(snapshot['rows'][-1]['errors'],
                         [{'component': 'history', 'error': 'RuntimeError:FICTIONAL_PROVIDER_TIMEOUT'}])
        with patch('trading_calendar.sessions', return_value=self.grid):
            ranked = rank.make_bundle(snapshot, 3)['result']
        self.assertEqual(ranked['ranking_relevant_acquisition_failures'], 1)
        contaminated = copy.deepcopy(snapshot)
        contaminated['rows'][-1]['errors'][0]['error'] = 'ValueError:ACTIVE_CAPTURE_LIMIT'
        with patch('trading_calendar.sessions', return_value=self.grid):
            with self.assertRaisesRegex(ValueError, 'STORE_LOCK_FAILURE_IN_SNAPSHOT: DEMO9 history'):
                rank.make_bundle(contaminated, 3)
