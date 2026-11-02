"""Behavioral acquisition/rate-limit regressions. Fake provider; no network."""
import copy
from datetime import date, timedelta
import json
from pathlib import Path
import sys
import tempfile
import threading
import types
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import public_research_fetch as fetch
from test_public_research import fixture
from public_research import calculate
from test_public_research_fetch import AdvancingClock


class YFRateLimitError(Exception):
    pass


class ControlledClock:
    def __init__(self):
        self.value = 0.0
        self.lock = threading.Lock()

    def monotonic(self):
        with self.lock:
            return self.value

    def set(self, value):
        with self.lock:
            self.value = value

    def advance(self, value):
        with self.lock:
            self.value += value


class CooldownConcurrencyTests(unittest.TestCase):
    def setUp(self):
        self.original = fetch._provider_paused, fetch._next_request
        fetch._provider_paused, fetch._next_request = False, 0.0

    def tearDown(self):
        fetch._provider_paused, fetch._next_request = self.original

    def exercise_waiting_request(self, repeated_failure=False):
        clock = ControlledClock()
        a_entered, a_fail = threading.Event(), threading.Event()
        a_sleeping, a_release = threading.Event(), threading.Event()
        b_sleeping, b_release = threading.Event(), threading.Event()
        b_resleeping, b_late_release = threading.Event(), threading.Event()
        a_done, b_done = threading.Event(), threading.Event()
        calls, errors, sleeps = [], [], []
        attempts = {'A': 0, 'B_sleep': 0, 'A_sleep': 0}

        def fake_sleep(delay):
            who = threading.current_thread().name
            sleeps.append((who, delay, clock.monotonic()))
            if who == 'cooldown_A':
                attempts['A_sleep'] += 1
                if attempts['A_sleep'] == 1:
                    a_sleeping.set()
                    if not a_release.wait(3):
                        raise TimeoutError('A coordination timeout')
                else:
                    clock.advance(delay)
            else:
                attempts['B_sleep'] += 1
                if attempts['B_sleep'] == 1:
                    b_sleeping.set()
                    if not b_release.wait(3):
                        raise TimeoutError('B coordination timeout')
                elif attempts['B_sleep'] == 2:
                    b_resleeping.set()
                    if not b_late_release.wait(3):
                        raise TimeoutError('B cooldown coordination timeout')
                else:
                    clock.advance(delay)

        def provider_a():
            attempts['A'] += 1
            calls.append(('A', clock.monotonic()))
            if attempts['A'] == 1:
                a_entered.set()
                if not a_fail.wait(3):
                    raise TimeoutError('A provider timeout')
                raise YFRateLimitError('Too Many Requests')
            if repeated_failure:
                raise YFRateLimitError('Too Many Requests')
            return 'A recovered'

        def provider_b():
            calls.append(('B', clock.monotonic()))
            return 'B ran'

        def worker(label, call, done):
            try:
                fetch.request_call(call)
            except Exception as exc:
                errors.append((label, type(exc).__name__, str(exc)))
            finally:
                done.set()

        threads = []
        try:
            with patch.object(fetch.time, 'monotonic', side_effect=clock.monotonic), \
                 patch.object(fetch.time, 'sleep', side_effect=fake_sleep):
                ta = threading.Thread(target=worker, args=('A', provider_a, a_done), name='cooldown_A')
                tb = threading.Thread(target=worker, args=('B', provider_b, b_done), name='cooldown_B')
                threads = [ta, tb]
                ta.start()
                self.assertTrue(a_entered.wait(2))
                tb.start()
                self.assertTrue(b_sleeping.wait(2))
                a_fail.set()
                self.assertTrue(a_sleeping.wait(2))
                if repeated_failure:
                    clock.set(60.2)
                    a_release.set()
                    self.assertTrue(a_done.wait(2))
                    b_release.set()
                    self.assertTrue(b_done.wait(2))
                else:
                    clock.set(0.2)
                    b_release.set()
                    # A correct limiter parks B again; old code completes B early.
                    b_resleeping.wait(0.2)
                    clock.set(60.2)
                    a_release.set()
                    b_late_release.set()
                    self.assertTrue(a_done.wait(2))
                    self.assertTrue(b_done.wait(2))
        finally:
            a_fail.set(); a_release.set(); b_release.set(); b_late_release.set()
            for thread in threads:
                if thread.ident is not None:
                    thread.join(2)
            self.assertFalse(any(t.is_alive() for t in threads))
        return calls, errors, sleeps

    def test_waiter_rechecks_new_rate_limit_cooldown(self):
        calls, errors, sleeps = self.exercise_waiting_request()
        self.assertEqual(errors, [])
        self.assertGreaterEqual(len([row for row in sleeps if row[0] == 'cooldown_B']), 2)
        b_calls = [at for who, at in calls if who == 'B']
        self.assertEqual(len(b_calls), 1)
        self.assertGreaterEqual(b_calls[0], 60.0)

    def test_repeated_rate_limit_pauses_already_waiting_request(self):
        calls, errors, _ = self.exercise_waiting_request(repeated_failure=True)
        self.assertEqual([who for who, _ in calls].count('A'), 2)
        self.assertNotIn('B', [who for who, _ in calls])
        self.assertTrue(any(who == 'B' and kind == 'RuntimeError'
                            and 'PROVIDER_PAUSED' in message for who, kind, message in errors))
        self.assertTrue(fetch._provider_paused)

    def test_normal_admissions_keep_existing_component_spacing(self):
        clock = AdvancingClock()
        starts = []
        with patch.object(fetch.time, 'monotonic', side_effect=clock.monotonic), \
             patch.object(fetch.time, 'sleep', side_effect=clock.sleep):
            for _ in range(4):
                fetch.request_call(lambda: starts.append(clock.monotonic()))
        self.assertEqual(len(starts), 4)
        self.assertTrue(all(right - left >= 0.199999999
                            for left, right in zip(starts, starts[1:])))


class HistoryFirstTests(unittest.TestCase):
    def collect(self, source, history_first=False, prior=None, reusable=None,
                history_error=None):
        ticker = Mock()
        info = {**source['info'], 'sector': source['sector'], 'industry': source['industry']}
        ticker.get_info.return_value = info
        ticker.get_income_stmt.return_value = source['income']
        ticker.get_balance_sheet.return_value = source['balance']
        ticker.get_cash_flow.return_value = source['cashflow']
        ticker.history.return_value = source['history']
        if history_error:
            ticker.history.side_effect = history_error
        provider = types.SimpleNamespace(Ticker=Mock(return_value=ticker))
        identity = {'symbol': source['symbol'], 'issuer_id': source['issuer_id']}
        grid = [{'date': d} for d in self.grid]
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory); (folder / 'raw').mkdir()
            with patch.dict(sys.modules, {'yfinance': provider}), \
                 patch.object(fetch, 'request_call', side_effect=lambda call: call()), \
                 patch.object(fetch, 'frame', side_effect=lambda value, price=False: copy.deepcopy(value)):
                result = fetch.fetch_row(identity, grid, folder, prior=prior,
                                         reusable=reusable, history_first=history_first)
            saved = json.loads((folder / 'raw' / ('security-' + source['symbol'] + '.json')).read_text())
        self.assertEqual(saved, result)
        return result, ticker

    def setUp(self):
        self.snapshot = fixture()
        self.grid = self.snapshot['session_dates']

    def assert_all_components_called(self, ticker):
        ticker.get_info.assert_called_once()
        ticker.history.assert_called_once()
        ticker.get_income_stmt.assert_called_once()
        ticker.get_balance_sheet.assert_called_once()
        ticker.get_cash_flow.assert_called_once()

    def short_source(self):
        source = copy.deepcopy(self.snapshot['rows'][0])
        source['history']['index'] = source['history']['index'][1:]
        source['history']['data'] = source['history']['data'][1:]
        return source

    def test_default_full_fetch_keeps_all_five_calls_even_for_short_history(self):
        result, ticker = self.collect(self.short_source())
        self.assert_all_components_called(ticker)
        self.assertNotIn('history_ineligibility', result)
        self.assertTrue(all(v['acquisition'] == 'fresh_network_pull'
                            for v in result['component_acquisition'].values()))

    def test_successful_short_history_saves_exactly_three_statement_calls(self):
        result, ticker = self.collect(self.short_source(), history_first=True)
        ticker.get_info.assert_called_once(); ticker.history.assert_called_once()
        ticker.get_income_stmt.assert_not_called()
        ticker.get_balance_sheet.assert_not_called()
        ticker.get_cash_flow.assert_not_called()
        self.assertEqual(result['errors'], [])
        self.assertEqual(result['history_ineligibility']['reason'], 'MISSING_HISTORY_SESSIONS')
        self.assertEqual(result['history_ineligibility']['required_session_dates'], self.grid)
        for component in ('income', 'balance', 'cashflow'):
            self.assertEqual(result['component_acquisition'][component]['acquisition'], 'not_requested')
            self.assertEqual(result['component_acquisition'][component]['reason'], 'HISTORY_INELIGIBLE')
            self.assertNotIn(component, result['component_retrieved_at'])

    def test_eligible_history_still_fetches_five_components_and_full_price_window(self):
        result, ticker = self.collect(self.snapshot['rows'][0], history_first=True)
        self.assert_all_components_called(ticker)
        self.assertNotIn('history_ineligibility', result)
        self.assertEqual(ticker.history.call_args.kwargs['start'], self.grid[0])
        self.assertEqual(ticker.history.call_args.kwargs['end'],
                         (date.fromisoformat(self.grid[-1]) + timedelta(days=1)).isoformat())
        self.assertFalse(ticker.history.call_args.kwargs['auto_adjust'])
        self.assertFalse(ticker.history.call_args.kwargs['repair'])
        self.assertTrue(ticker.history.call_args.kwargs['actions'])

    def test_new_date_does_not_reuse_quotes_or_price_tails(self):
        first, first_ticker = self.collect(self.snapshot['rows'][0], history_first=True)
        new_source = copy.deepcopy(self.snapshot['rows'][0])
        new_dates = [(date.fromisoformat(d) + timedelta(days=1)).isoformat() for d in self.grid]
        new_source['history']['index'] = new_dates
        self.grid = new_dates
        second, second_ticker = self.collect(new_source, history_first=True)
        self.assert_all_components_called(first_ticker)
        self.assert_all_components_called(second_ticker)
        self.assertEqual(second_ticker.history.call_args.kwargs['start'], new_dates[0])
        self.assertEqual(second['component_acquisition']['info']['acquisition'], 'fresh_network_pull')
        self.assertEqual(second['component_acquisition']['history']['acquisition'], 'fresh_network_pull')
        self.assertNotEqual(first['history']['index'], second['history']['index'])

    def test_failed_or_empty_history_never_skips_financial_requests(self):
        for case in ('failed', 'empty'):
            with self.subTest(case=case):
                source = copy.deepcopy(self.snapshot['rows'][0])
                error = TimeoutError('history unavailable') if case == 'failed' else None
                if case == 'empty':
                    source['history'] = {'index': [], 'columns': [], 'data': []}
                result, ticker = self.collect(source, history_first=True, history_error=error)
                self.assert_all_components_called(ticker)
                self.assertNotIn('history_ineligibility', result)
                self.assertTrue(any(e['component'] == 'history' for e in result['errors']))

    def test_malformed_or_nonterminal_history_error_never_skips_financials(self):
        for case in ('duplicate_date', 'duplicate_column', 'ragged', 'missing_named_price_column'):
            with self.subTest(case=case):
                source = copy.deepcopy(self.snapshot['rows'][0])
                history = source['history']
                if case == 'duplicate_date':
                    history['index'][-1] = history['index'][-2]
                elif case == 'duplicate_column':
                    history['columns'][-1] = history['columns'][0]
                elif case == 'ragged':
                    history['data'][0].pop()
                else:
                    history['columns'][1] = 'Not Adjusted Close'
                result, ticker = self.collect(source, history_first=True)
                self.assert_all_components_called(ticker)
                self.assertNotIn('history_ineligibility', result)

    def test_malformed_short_price_frame_does_not_hide_missing_financial_coverage(self):
        for case in ('missing_close', 'missing_adjusted', 'missing_volume', 'null_close',
                     'nan_adjusted', 'zero_close', 'negative_adjusted', 'negative_volume'):
            with self.subTest(case=case):
                source = self.short_source()
                history = source['history']
                if case.startswith('missing_'):
                    index = {'missing_close': 0, 'missing_adjusted': 1, 'missing_volume': 2}[case]
                    history['columns'][index] = 'Unsupported column'
                elif case == 'null_close':
                    history['data'][0][0] = None
                elif case == 'nan_adjusted':
                    # Provider JSON represents a missing/nonfinite cell as null.
                    # Direct helper proof is also checked against actual NaN below.
                    history['data'][0][1] = None
                elif case == 'zero_close':
                    history['data'][0][0] = 0
                elif case == 'negative_adjusted':
                    history['data'][0][1] = -1
                else:
                    history['data'][0][2] = -1
                result, ticker = self.collect(source, history_first=True)
                self.assert_all_components_called(ticker)
                self.assertNotIn('history_ineligibility', result)
        direct = self.short_source()
        direct['history']['data'][0][1] = float('nan')
        self.assertIsNone(fetch.history_ineligibility(direct, [{'date': d} for d in self.grid]))

    def test_native_scores_order_exclusions_and_membership_match_full_fetch(self):
        sources = copy.deepcopy(self.snapshot['rows'])
        sources[0] = self.short_source()
        full = copy.deepcopy(self.snapshot); fast = copy.deepcopy(self.snapshot)
        full['rows'] = [self.collect(row)[0] for row in sources]
        fast['rows'] = [self.collect(row, history_first=True)[0] for row in sources]
        before, after = calculate(full, 9), calculate(fast, 9)
        for field in ('universe_securities', 'unique_issuers', 'scored_issuers',
                      'review_queue', 'scores', 'exclusions', 'research_candidates'):
            self.assertEqual(before[field], after[field], field)
        self.assertEqual(full['universe_symbols'], fast['universe_symbols'])
        self.assertEqual(after['ranking_relevant_acquisition_failures'], 0)
        self.assertTrue(any(r['symbol'] == sources[0]['symbol']
                            and r['reason'] == 'CLASS_SELECTION:MISSING_HISTORY_SESSIONS'
                            for r in after['exclusions']))
        # Intentional unrequested statements remain visible as incomplete fields;
        # they must not be mislabeled as provider transport failures.
        self.assertEqual(after['provider_limited_issuers'], 0)

    def test_completed_resume_components_are_preserved_without_provider_calls(self):
        old = copy.deepcopy(self.snapshot['rows'][0]); old['errors'] = []
        result, ticker = self.collect(old, history_first=True, prior=old)
        ticker.get_info.assert_not_called(); ticker.history.assert_not_called()
        ticker.get_income_stmt.assert_not_called(); ticker.get_balance_sheet.assert_not_called()
        ticker.get_cash_flow.assert_not_called()
        for field in ('info', 'income', 'balance', 'cashflow', 'history'):
            self.assertEqual(result[field], old[field])
        self.assertNotIn('history_ineligibility', result)

    def test_existing_successful_resume_statements_not_erased_for_short_history(self):
        old = self.short_source(); old['errors'] = []
        result, ticker = self.collect(old, history_first=True, prior=old)
        ticker.get_income_stmt.assert_not_called(); ticker.get_balance_sheet.assert_not_called()
        ticker.get_cash_flow.assert_not_called(); ticker.history.assert_not_called()
        for component in ('income', 'balance', 'cashflow'):
            self.assertEqual(result[component], old[component])

    def test_explicit_reusable_statements_keep_info_and_history_fresh(self):
        source = self.snapshot['rows'][0]
        reusable = {key: {'value': copy.deepcopy(source[key]), 'retrieved_at': '2025-01-01T00:00:00Z',
                         'source_check': {'metadata': {'currency': 'USD'}},
                         'provenance': {'acquisition': 'verified_explicit_reuse'}}
                    for key in ('income', 'balance', 'cashflow')}
        result, ticker = self.collect(source, history_first=True, reusable=reusable)
        ticker.get_info.assert_called_once(); ticker.history.assert_called_once()
        ticker.get_income_stmt.assert_not_called(); ticker.get_balance_sheet.assert_not_called()
        ticker.get_cash_flow.assert_not_called()
        self.assertEqual(result['component_retrieved_at']['income'], '2025-01-01T00:00:00Z')
        self.assertEqual(result['component_acquisition']['history']['acquisition'], 'fresh_network_pull')
        changed = copy.deepcopy(source); changed['info']['financialCurrency'] = 'EUR'
        result, ticker = self.collect(changed, history_first=True, reusable=reusable)
        self.assert_all_components_called(ticker)
        self.assertNotIn('income', result.get('component_source_checks', {}))


class CollectionContractTests(unittest.TestCase):
    def setUp(self):
        self.data = fixture()
        self.grid = [{'date': d, 'close': d + 'T20:00:00+00:00'}
                     for d in self.data['session_dates']]

    def freeze(self, root, history_first):
        prompt = root / 'prompt.txt'; prompt.write_text('Fictional full-universe parity test')
        folder = root / 'run'
        universe = {'rows': [{'symbol': 'DEMO0', 'issuer_id': 'fictional:0'}],
                    'evidence': {'universe_id': 'FICTIONAL'}}
        args = ['fetch', '--output', str(folder), '--decision-at', self.grid[-1]['date'] + 'T21:00:00Z',
                '--hold', 'P2Y', '--prompt-file', str(prompt), '--universe-only']
        if history_first:
            args.append('--history-first')
        def acquire(target, *unused):
            fetch.save(target / 'universe.json', universe)
            return universe
        with patch.object(sys, 'argv', args), patch.object(fetch, 'sessions', return_value=self.grid), \
             patch.object(fetch, 'acquire_universe', side_effect=acquire):
            fetch.main()
        return args, folder

    def test_cli_default_is_full_and_history_first_requires_opt_in(self):
        args = fetch.argument_parser().parse_args(['--output', 'unused', '--decision-at', '2026-01-01T00:00:00Z',
                                                   '--hold', 'P2Y', '--prompt-file', 'unused'])
        self.assertFalse(args.history_first)
        self.assertFalse(args.partial_fetch)

    def test_resume_rejects_collection_mode_change_in_both_directions(self):
        for initially_fast in (False, True):
            with self.subTest(initially_fast=initially_fast), tempfile.TemporaryDirectory() as directory:
                args, _ = self.freeze(Path(directory), initially_fast)
                resumed = [a for a in args if a != '--history-first'] + ['--resume']
                if not initially_fast:
                    resumed.append('--history-first')
                with patch.object(sys, 'argv', resumed), patch.object(fetch, 'sessions', return_value=self.grid):
                    with self.assertRaisesRegex(ValueError, 'RESUME_CONTRACT_MISMATCH:collection_mode'):
                        fetch.main()

    def test_resume_rejects_changed_collector_code_contract(self):
        with tempfile.TemporaryDirectory() as directory:
            args, folder = self.freeze(Path(directory), False)
            path = folder / 'contract-before-fetch.json'
            contract = json.loads(path.read_text())
            contract['acquisition_code_sha256']['public_research_fetch.py'] = '0' * 64
            path.write_text(json.dumps(contract))
            with patch.object(sys, 'argv', args + ['--resume']), \
                 patch.object(fetch, 'sessions', return_value=self.grid):
                with self.assertRaisesRegex(ValueError, 'ACQUISITION_CODE_MISMATCH'):
                    fetch.main()

    def test_same_contract_resume_uses_successful_checkpoints_without_new_fetch(self):
        with tempfile.TemporaryDirectory() as directory:
            args, folder = self.freeze(Path(directory), True)
            old = copy.deepcopy(self.data['rows'][0]); old['errors'] = []
            fetch.save(folder / 'raw' / 'security-DEMO0.json', old)
            resumed = [a for a in args if a != '--universe-only'] + ['--resume']
            with patch.object(sys, 'argv', resumed), patch.object(fetch, 'sessions', return_value=self.grid), \
                 patch.object(fetch, 'fetch_row', side_effect=AssertionError('Successful checkpoint refetched')):
                fetch.main()
            snapshot = json.loads((folder / 'retry-001' / 'snapshot.json').read_text())
            self.assertEqual(snapshot['rows'], [old])
            self.assertEqual(snapshot['contract']['collection_mode'], 'history_first')


if __name__ == '__main__':
    unittest.main()
