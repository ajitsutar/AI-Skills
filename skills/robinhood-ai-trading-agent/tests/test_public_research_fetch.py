"""Acquisition recovery tests: fake provider, no external network requests."""
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import public_research_fetch as fetch


class YFRateLimitError(Exception):
    pass


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
        fetch._provider_paused = False
        fetch._next_request = 0

    def tearDown(self):
        fetch._provider_paused = False
        fetch._next_request = 0

    def test_rate_limit_retries_once_then_pauses(self):
        call = Mock(side_effect=YFRateLimitError('Too Many Requests'))
        with patch.object(fetch.time, 'sleep'), patch.object(fetch.time, 'monotonic', return_value=1):
            with self.assertRaises(YFRateLimitError):
                fetch.request_call(call)
            with self.assertRaisesRegex(RuntimeError, 'PROVIDER_PAUSED'):
                fetch.request_call(call)
        self.assertEqual(call.call_count, 2)

    def test_transient_rate_limit_recovers_without_pausing(self):
        call = Mock(side_effect=[YFRateLimitError(), 'recovered'])
        with patch.object(fetch.time, 'sleep') as sleep, patch.object(fetch.time, 'monotonic', return_value=1):
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


if __name__ == '__main__':
    unittest.main()
