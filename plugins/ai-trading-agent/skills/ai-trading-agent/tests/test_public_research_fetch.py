"""Acquisition recovery tests: fake provider, no external network requests."""
from pathlib import Path
from datetime import date, timedelta
import contextlib
import io
import json
import os
import sys
import tempfile
import types
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import public_research_fetch as fetch


class YFRateLimitError(Exception):
    pass


class AdvancingClock:
    """A real wait-loop needs a clock that moves when fake sleep completes."""
    def __init__(self, start=1.0):
        self.value = start
        self.sleeps = []

    def monotonic(self):
        return self.value

    def sleep(self, delay):
        self.sleeps.append(delay)
        self.value += delay


class AcquisitionTests(unittest.TestCase):
    def test_checkpoint_recovery_after_interruption_and_identity_guard(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory); (folder / 'raw').mkdir()
            identity = {'symbol': 'DEMO', 'issuer_id': 'fictional:demo'}
            fetch.save(folder / 'raw' / 'DEMO.json', identity)
            (folder / 'raw' / 'interrupted.json').write_text('{')
            prior, corrupt = fetch.recover_checkpoints(folder, {'rows': [identity]})
            self.assertEqual(prior, {'DEMO': identity})
            self.assertEqual(len(corrupt), 1)
            self.assertTrue((folder / 'raw' / 'interrupted.json').exists())
            with self.assertRaisesRegex(ValueError, 'UNIVERSE_MISMATCH'):
                fetch.recover_checkpoints(folder, {'rows': []})

    def test_bare_company_name_can_receive_provider_equity_confirmation(self):
        ticker = Mock()
        ticker.get_info.return_value = {'quoteType': 'EQUITY', 'sector': 'Industrials'}
        provider = types.SimpleNamespace(Ticker=Mock(return_value=ticker))
        identity = {'symbol': 'DEMO', 'issuer_id': 'fictional:demo',
                    'provider_equity_resolution_allowed': True,
                    'security_type': 'unresolved_security_type', 'directory_source': 'fictional'}
        old = {**identity, 'info': {}, 'errors': []}
        for key in ('income', 'balance', 'cashflow', 'history'):
            old[key] = {'index': ['demo'], 'columns': ['demo'], 'data': [[1]]}
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory); (folder / 'raw').mkdir()
            with patch.dict(sys.modules, {'yfinance': provider}), patch.object(fetch, 'request_call', side_effect=lambda call: call()):
                result = fetch.fetch_row(identity, [], folder, old)
        self.assertEqual(result['security_type'], 'provider_confirmed_equity')
        self.assertEqual(result['directory_security_type'], 'unresolved_security_type')
        self.assertEqual(old['security_type'], 'unresolved_security_type')

    def setUp(self):
        self.network_environment = patch.dict(os.environ, {'AI_TRADING_NETWORK_MODE': 'online'})
        self.network_environment.start()
        self.addCleanup(self.network_environment.stop)
        fetch._provider_paused = False
        fetch._next_request = 0

    def tearDown(self):
        fetch._provider_paused = False
        fetch._next_request = 0

    def test_rate_limit_retries_once_then_pauses(self):
        call = Mock(side_effect=YFRateLimitError('Too Many Requests'))
        clock = AdvancingClock()
        with patch.object(fetch.time, 'sleep', side_effect=clock.sleep), \
             patch.object(fetch.time, 'monotonic', side_effect=clock.monotonic):
            with self.assertRaises(YFRateLimitError):
                fetch.request_call(call)
            with self.assertRaisesRegex(RuntimeError, 'PROVIDER_PAUSED'):
                fetch.request_call(call)
        self.assertEqual(call.call_count, 2)

    def test_transient_rate_limit_recovers_without_pausing(self):
        call = Mock(side_effect=[YFRateLimitError(), 'recovered'])
        clock = AdvancingClock()
        with patch.object(fetch.time, 'sleep', side_effect=clock.sleep) as sleep, \
             patch.object(fetch.time, 'monotonic', side_effect=clock.monotonic):
            self.assertEqual(fetch.request_call(call), 'recovered')
        self.assertEqual(call.call_count, 2)
        self.assertGreaterEqual(sleep.call_args[0][0], 60)
        self.assertFalse(fetch._provider_paused)

    def test_other_errors_are_not_silently_retried(self):
        call = Mock(side_effect=TimeoutError())
        with self.assertRaises(TimeoutError):
            fetch.request_call(call)
        self.assertEqual(call.call_count, 1)

    def test_resume_only_failed_component_preserves_original(self):
        old = {'symbol': 'DEMO', 'issuer_id': 'fictional:demo', 'info': {},
               'errors': [{'component': 'info', 'error': 'Timeout'}]}
        for key in ('income', 'balance', 'cashflow', 'history'):
            old[key] = {'index': ['demo'], 'columns': ['demo'], 'data': [[1]]}
        ticker = Mock()
        ticker.get_info.return_value = {'sector': 'Industrials', 'industry': 'Fictional'}
        provider = types.SimpleNamespace(Ticker=Mock(return_value=ticker))
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory); (folder / 'raw').mkdir()
            with patch.dict(sys.modules, {'yfinance': provider}), patch.object(fetch, 'request_call', side_effect=lambda call: call()):
                result = fetch.fetch_row({'symbol': 'DEMO'}, [], folder, old)
            self.assertTrue((folder / 'raw' / 'security-DEMO.json').exists())
        ticker.get_info.assert_called_once()
        ticker.get_income_stmt.assert_not_called()
        ticker.get_balance_sheet.assert_not_called()
        ticker.get_cash_flow.assert_not_called()
        ticker.history.assert_not_called()
        self.assertEqual(result['errors'], [])
        self.assertEqual(result['income'], old['income'])
        self.assertEqual(len(old['errors']), 1)


class OfflineContractTests(unittest.TestCase):
    def setUp(self):
        self.environment = patch.dict(os.environ, {'AI_TRADING_NETWORK_MODE': 'offline'})
        self.environment.start()
        self.addCleanup(self.environment.stop)

    def cli_args(self, output, *extra):
        return ['public_research_fetch.py', '--output', str(output),
                '--decision-at', '2026-11-06T20:00:00+00:00', '--hold', 'P3Y',
                '--prompt-file', str(output.parent / 'prompt.txt'), *extra]

    def test_offline_presets_and_full_custom_cli_fail_before_outputs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for extra in (['--universe-only', '--universe-preset', 'sp500'],
                          ['--universe-only'],
                          ['--universe', str(root / 'custom.json')]):
                with self.subTest(extra=extra), patch.object(sys, 'argv', self.cli_args(root / 'out', *extra)), \
                     patch.object(fetch, 'sessions') as calendar, patch.object(fetch, 'network_get') as http:
                    with self.assertRaisesRegex(fetch.NetworkPolicyError, 'NETWORK_DISABLED_BY_RUN_CONTRACT'):
                        fetch.main()
                    calendar.assert_not_called()
                    http.assert_not_called()
                    self.assertFalse((root / 'out').exists())

    def test_imported_entrypoints_deny_before_transport_or_provider(self):
        provider = types.SimpleNamespace(Ticker=Mock())
        callback = Mock()
        with patch.dict(sys.modules, {'yfinance': provider}), patch('requests.get') as http:
            for call in (lambda: fetch.acquire_universe(Path('unused'), preset='sp500'),
                         lambda: fetch.acquire_universe(Path('unused'), price_date='2026-11-06'),
                         lambda: fetch.fetch_row({'symbol': 'DEMO'}, [], Path('unused')),
                         lambda: fetch.request_call(callback),
                         lambda: fetch.network_get('https://example.invalid/')):
                with self.assertRaisesRegex(fetch.NetworkPolicyError, 'NETWORK_DISABLED_BY_RUN_CONTRACT'):
                    call()
            provider.Ticker.assert_not_called()
            callback.assert_not_called()
            http.assert_not_called()

    def test_invalid_environment_fails_closed_even_for_local_cli(self):
        for value in ('', 'OFFLINE', 'false', 'offine'):
            with self.subTest(value=value), patch.dict(os.environ, {'AI_TRADING_NETWORK_MODE': value}), \
                 patch.object(sys, 'argv', self.cli_args(Path('unused'), '--universe-only', '--universe', 'local.json')), \
                 patch.object(fetch, 'sessions') as calendar:
                with self.assertRaisesRegex(fetch.NetworkPolicyError, 'INVALID_NETWORK_MODE'):
                    fetch.main()
                with self.assertRaisesRegex(fetch.NetworkPolicyError, 'INVALID_NETWORK_MODE'):
                    fetch.acquire_universe(Path('unused'), supplied=Path('local.json'))
                calendar.assert_not_called()

    def test_offline_local_universe_cli_and_membership_resume(self):
        grid = [{'date': (date(2025, 11, 1) + timedelta(days=i)).isoformat(),
                 'close': (date(2025, 11, 1) + timedelta(days=i)).isoformat() + 'T20:00:00+00:00'}
                for i in range(253)]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); output = root / 'out'; supplied = root / 'custom.json'
            (root / 'prompt.txt').write_text('Retain supplied fictional membership', encoding='utf-8')
            supplied.write_text(json.dumps({'universe_id': 'fictional', 'source': 'supplied exercise',
                'rows': [{'symbol': 'DEMO', 'issuer_id': 'fictional:demo', 'name': 'Demo'}]}), encoding='utf-8')
            with patch.object(fetch, 'sessions', return_value=grid), patch('requests.get') as http, \
                 patch.object(fetch, 'fetch_row') as row, contextlib.redirect_stdout(io.StringIO()):
                with patch.object(sys, 'argv', self.cli_args(output, '--universe-only', '--universe', str(supplied))):
                    fetch.main()
                contract = json.loads((output / 'contract-before-fetch.json').read_text())
                self.assertEqual(contract['network_mode'], 'offline')
                self.assertEqual(contract['acquisition'], 'supplied_local_universe_only')
                self.assertEqual(json.loads((output / 'universe.json').read_text())['rows'][0]['symbol'], 'DEMO')
                with patch.object(sys, 'argv', self.cli_args(output, '--universe-only', '--resume')):
                    fetch.main()
                http.assert_not_called()
                row.assert_not_called()

    def test_online_and_unset_preserve_mocked_transport(self):
        for mode in ('online', None):
            with self.subTest(mode=mode), patch.dict(os.environ), patch('requests.get', return_value='http-result') as http:
                if mode is None:
                    os.environ.pop('AI_TRADING_NETWORK_MODE', None)
                else:
                    os.environ['AI_TRADING_NETWORK_MODE'] = mode
                self.assertEqual(fetch.network_get('https://example.invalid/', timeout=1), 'http-result')
                http.assert_called_once_with('https://example.invalid/', timeout=1)
                callback = Mock(return_value='provider-result')
                with patch.object(fetch, '_next_request', 0), patch.object(fetch, '_provider_paused', False):
                    self.assertEqual(fetch.request_call(callback), 'provider-result')
                callback.assert_called_once()

    def exercise_resume_transition(self, initial_mode, membership_first, resumed_mode, membership_resume):
        grid = [{'date': (date(2025, 11, 1) + timedelta(days=i)).isoformat(),
                 'close': (date(2025, 11, 1) + timedelta(days=i)).isoformat() + 'T20:00:00+00:00'}
                for i in range(253)]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); output = root / 'out'; supplied = root / 'custom.json'
            (root / 'prompt.txt').write_text('Fictional resume provenance test', encoding='utf-8')
            supplied.write_text(json.dumps({'universe_id': 'fictional', 'source': 'supplied exercise',
                'rows': [{'symbol': 'DEMO', 'issuer_id': 'fictional:demo', 'name': 'Demo'}]}), encoding='utf-8')
            with patch.object(fetch, 'sessions', return_value=grid), patch('requests.get') as http, \
                 patch.object(fetch, 'fetch_row', return_value={'symbol': 'DEMO', 'errors': []}) as row, \
                 contextlib.redirect_stdout(io.StringIO()):
                initial = self.cli_args(output, '--universe', str(supplied))
                if membership_first:
                    initial.append('--universe-only')
                with patch.dict(os.environ, {'AI_TRADING_NETWORK_MODE': initial_mode}), patch.object(sys, 'argv', initial):
                    fetch.main()
                original_bytes = (output / 'contract-before-fetch.json').read_bytes()
                original = json.loads(original_bytes)
                calls_before_resume = row.call_count
                resumed = self.cli_args(output, '--resume')
                if membership_resume:
                    resumed.append('--universe-only')
                with patch.dict(os.environ, {'AI_TRADING_NETWORK_MODE': resumed_mode}), patch.object(sys, 'argv', resumed):
                    fetch.main()
                self.assertEqual((output / 'contract-before-fetch.json').read_bytes(), original_bytes)
                receipt = json.loads((output / 'retry-001/resume-receipt.json').read_text())
                attempt = receipt['attempt']
                self.assertEqual(attempt['network_mode'], resumed_mode)
                self.assertEqual(attempt['original_contract_sha256'], fetch.digest(original))
                self.assertEqual(receipt['contract_sha256'], fetch.digest(original))
                self.assertTrue(attempt['scope_is_request_not_proof_of_network_calls'])
                if membership_resume:
                    self.assertEqual(attempt['requested_scope'], 'membership_only')
                    self.assertEqual(attempt['acquisition'], 'retained_membership_only')
                    self.assertEqual(row.call_count, calls_before_resume)
                    self.assertFalse((output / 'retry-001/snapshot.json').exists())
                else:
                    self.assertEqual(attempt['requested_scope'], 'prices_and_financials')
                    self.assertEqual(attempt['acquisition'], 'resume_missing_price_financial_components')
                    self.assertEqual(row.call_count, calls_before_resume + 1)
                    snapshot = json.loads((output / 'retry-001/snapshot.json').read_text())
                    self.assertEqual(snapshot['contract'], original)
                    self.assertEqual(snapshot['contract_role'], 'frozen_original_research_contract')
                    actual = snapshot['acquisition_attempt']
                    self.assertEqual({k: actual[k] for k in attempt}, attempt)
                    self.assertEqual(actual['provider_jobs_submitted'], 1)
                    self.assertEqual(actual['complete_checkpoints_reused'], 0)
                http.assert_not_called()

    def test_offline_membership_to_online_full_resume_records_actual_attempt(self):
        self.exercise_resume_transition('offline', True, 'online', False)

    def test_online_full_to_offline_membership_resume_records_actual_attempt(self):
        self.exercise_resume_transition('online', False, 'offline', True)

    def test_policy_change_during_wait_blocks_callback(self):
        callback = Mock()
        def disable(_):
            os.environ['AI_TRADING_NETWORK_MODE'] = 'offline'
        with patch.dict(os.environ, {'AI_TRADING_NETWORK_MODE': 'online'}), \
             patch.object(fetch, '_provider_paused', False), patch.object(fetch, '_next_request', 2), \
             patch.object(fetch.time, 'monotonic', side_effect=[1, 3]), patch.object(fetch.time, 'sleep', side_effect=disable):
            with self.assertRaisesRegex(fetch.NetworkPolicyError, 'NETWORK_DISABLED_BY_RUN_CONTRACT'):
                fetch.request_call(callback)
        callback.assert_not_called()

    def test_provider_policy_error_is_not_swallowed_as_component_failure(self):
        provider = types.SimpleNamespace(Ticker=Mock(return_value=Mock()))
        with patch.dict(os.environ, {'AI_TRADING_NETWORK_MODE': 'online'}), \
             patch.dict(sys.modules, {'yfinance': provider}), \
             patch.object(fetch, 'request_call', side_effect=fetch.NetworkPolicyError('NETWORK_DISABLED_BY_RUN_CONTRACT')), \
             patch.object(fetch, 'save') as save:
            with self.assertRaisesRegex(fetch.NetworkPolicyError, 'NETWORK_DISABLED_BY_RUN_CONTRACT'):
                fetch.fetch_row({'symbol': 'DEMO'}, [], Path('unused'))
            save.assert_not_called()

    def test_fund_proxy_policy_error_is_not_swallowed_as_unavailable(self):
        table = Mock()
        table.columns = ['Symbol', 'Company Name']
        table.to_dict.return_value = [{'Symbol': 'D' + str(i), 'Company Name': 'Demo ' + str(i)} for i in range(450)]
        response = Mock(content=b'fictional table', text='fictional table')
        with tempfile.TemporaryDirectory() as directory, \
             patch.dict(os.environ, {'AI_TRADING_NETWORK_MODE': 'online'}), \
             patch('pandas.read_html', return_value=[table]), \
             patch.object(fetch, 'network_get', side_effect=[response, fetch.NetworkPolicyError('NETWORK_DISABLED_BY_RUN_CONTRACT')]):
            with self.assertRaisesRegex(fetch.NetworkPolicyError, 'NETWORK_DISABLED_BY_RUN_CONTRACT'):
                fetch.acquire_universe(Path(directory), preset='sp500')
            self.assertFalse((Path(directory) / 'universe.json').exists())


if __name__ == '__main__':
    unittest.main()
