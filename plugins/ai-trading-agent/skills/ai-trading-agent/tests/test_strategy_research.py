"""Strategy identity, causality, pending-fill and wealth conservation tests."""
import copy
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import strategy_lab
import strategy_research as research

AS_OF = '2026-10-13T16:00:00Z'


def daily(closes):
    rows = []
    for i, close in enumerate(closes):
        start = datetime(2025, 1, 1, 14, 30, tzinfo=timezone.utc) + timedelta(days=i)
        opened = closes[i-1] if i else close
        rows.append({'timestamp': (start + timedelta(hours=6)).isoformat(),
                     'session_open': start.isoformat(), 'session_close': (start + timedelta(hours=6)).isoformat(),
                     'open': opened, 'high': max(opened, close) + 1, 'low': min(opened, close) - 1,
                     'close': close, 'volume': 1000})
    return rows


def intraday():
    start = datetime(2025, 1, 1, 14, 30, tzinfo=timezone.utc)
    rows = []
    for i in range(7):
        o, h, low, c, v = (10, 11, 9, 10, 1000) if i < 3 else (10, 13, 9, 12, 2000)
        if i >= 4:
            o, h, low, c, v = 12, 25, 8, 12, 2000  # Both stop and target touched.
        rows.append({'timestamp': (start + timedelta(minutes=5*(i+1))).isoformat(),
                     'session_open': start.isoformat(), 'session_close': (start + timedelta(hours=6, minutes=30)).isoformat(),
                     'open': o, 'high': h, 'low': low, 'close': c, 'volume': v})
    return rows


class StrategyResearchTests(unittest.TestCase):
    def test_dual_sma_is_long_cash_and_two_sided_fees_reconcile(self):
        rows = daily([10, 10, 10, 12, 10, 8, 8])
        result = research.dual_sma(rows, AS_OF, fast=2, slow=3, cost_per_side_bps=10)
        self.assertEqual(result['strategy_id'], 'dual-sma-long-cash-1')
        self.assertEqual([f['action'] for f in result['fills']], ['enter', 'exit'])
        entry, exit_fill = result['fills']
        expected_quantity = 1 / (12 * 1.001)
        expected_wealth = expected_quantity * 8 * .999
        self.assertAlmostEqual(entry['quantity'], expected_quantity)
        self.assertEqual(entry['signal_index'], 3)
        self.assertEqual(entry['bar_index'], 4)
        self.assertEqual(entry['at'], rows[4]['session_open'])
        self.assertEqual(exit_fill['signal_index'], 5)
        self.assertEqual(exit_fill['bar_index'], 6)
        self.assertAlmostEqual(result['final_equity'], expected_wealth)
        self.assertAlmostEqual(result['total_fees'], entry['fee'] + exit_fill['fee'])
        self.assertAlmostEqual(result['accounting_residual'], 0)
        self.assertTrue(all(r['quantity'] >= 0 and r['cash'] >= -1e-14 for r in result['equity_curve']))

    def test_terminal_fee_adjusts_final_equity_curve_and_total_return(self):
        rows = daily([10, 10, 10, 12, 14])
        marked = research.dual_sma(rows, AS_OF, fast=2, slow=3, cost_per_side_bps=100)
        closed = research.dual_sma(rows, AS_OF, fast=2, slow=3, cost_per_side_bps=100,
                                   terminal_policy='liquidate_last_close')
        self.assertGreater(marked['open_quantity'], 0)
        self.assertEqual(closed['open_quantity'], 0)
        self.assertAlmostEqual(closed['final_equity'], marked['final_equity'] * .99)
        self.assertEqual(closed['final_equity'], closed['equity_curve'][-1]['equity'])
        self.assertEqual(closed['total_return'], closed['final_equity'] - 1)
        self.assertEqual(closed['fills'][-1]['reason'], 'predeclared_terminal_close')
        self.assertAlmostEqual(closed['realized_pnl'], closed['final_equity'] - 1)

    def test_marked_drawdown_exists_inside_an_unclosed_trade(self):
        result = research.dual_sma(daily([10]*5 + [20, 20, 19, 18, 30]), AS_OF,
                                   fast=2, slow=5, cost_per_side_bps=0)
        self.assertEqual(len([f for f in result['fills'] if f['action'] == 'exit']), 0)
        self.assertGreater(result['open_quantity'], 0)
        self.assertAlmostEqual(result['max_drawdown'], .1)

    def test_future_bar_perturbation_cannot_change_earlier_decisions_or_fills(self):
        rows = daily([10]*5 + [20, 20, 19, 18, 30, 15, 10])
        changed = copy.deepcopy(rows)
        for row in changed[9:]:
            for field in ('open', 'high', 'low', 'close'):
                row[field] *= 10
        a = research.dual_sma(rows, AS_OF, fast=2, slow=5)
        b = research.dual_sma(changed, AS_OF, fast=2, slow=5)
        self.assertEqual([r for r in a['signals'] if r['bar_index'] < 9],
                         [r for r in b['signals'] if r['bar_index'] < 9])
        self.assertEqual([r for r in a['fills'] if r['bar_index'] < 9],
                         [r for r in b['fills'] if r['bar_index'] < 9])
        self.assertEqual(a['equity_curve'][:9], b['equity_curve'][:9])

    def test_delayed_order_past_last_bar_is_never_clamped_to_last_bar(self):
        result = research.dual_sma(daily([10, 10, 10, 12, 14]), AS_OF,
                                   fast=2, slow=3, delay_bars=5,
                                   terminal_policy='liquidate_last_close')
        self.assertEqual(result['fills'], [])
        self.assertEqual(result['final_equity'], 1)
        self.assertEqual(result['orders'][0]['due_index'], 9)
        self.assertEqual(result['orders'][0]['status'], 'UNFILLED_BEYOND_DATA')

    def test_missed_entry_and_illiquid_due_bar_are_not_later_fills(self):
        rows = daily([10, 10, 10, 12, 14, 16])
        missed = research.dual_sma(rows, AS_OF, fast=2, slow=3, missed_entry_signal_indices=[3])
        self.assertEqual(missed['fills'], [])
        self.assertEqual(missed['orders'][0]['status'], 'MISSED_ENTRY_SCENARIO')
        rows[4]['volume'] = 0
        illiquid = research.dual_sma(rows, AS_OF, fast=2, slow=3)
        self.assertEqual(illiquid['fills'], [])
        self.assertEqual(illiquid['orders'][0]['status'], 'UNFILLED_NO_VOLUME')

    def test_variants_preserve_all_outputs_and_expose_confounding(self):
        rows = daily([10]*8 + [20, 12, 8, 20, 25, 10])
        variants = [{'id': 'base', 'fast': 2, 'slow': 5, 'cost_per_side_bps': 10},
                    {'id': 'one', 'fast': 3, 'slow': 5, 'cost_per_side_bps': 10},
                    {'id': 'joint', 'fast': 4, 'slow': 5, 'cost_per_side_bps': 20, 'delay_bars': 1}]
        result = research.dual_sma_variants(rows, AS_OF, variants)
        self.assertEqual([r['id'] for r in result['runs']], ['base', 'one', 'joint'])
        self.assertEqual(result['runs'][1]['comparison'], 'ONE_PARAMETER_CHANGED')
        self.assertEqual(result['runs'][2]['comparison'], 'MULTIPLE_PARAMETERS_CHANGED')
        self.assertEqual(set(result['runs'][2]['changed_parameters']), {'fast', 'cost_per_side_bps', 'delay_bars'})
        self.assertEqual(len({r['result']['bars_sha256'] for r in result['runs']}), 1)
        self.assertEqual(result['selection'], 'ALL_DECLARED_VARIANTS_RETAINED_NO_OPTIMIZATION')

    def test_invalid_variant_is_retained_without_losing_supported_runs(self):
        result = research.dual_sma_variants(daily([10, 10, 10, 12, 10, 8]), AS_OF,
                  [{'id': 'valid', 'fast': 2, 'slow': 3}, {'id': 'invalid', 'fast': 5, 'slow': 3},
                   {'id': 'other', 'fast': 2, 'slow': 4}])
        self.assertEqual(result['status'], 'PARTIAL_ANALYSIS')
        self.assertEqual(result['computed_variants'], 2)
        self.assertEqual([r['result']['status'] for r in result['runs']], ['SIMULATED', 'REJECTED_INPUT', 'SIMULATED'])
        self.assertEqual(result['runs'][1]['parameters']['fast'], 5)
        self.assertNotIn('final_equity', result['runs'][1]['result'])

    def test_terminal_illiquid_bar_retains_position_and_never_fabricates_sale(self):
        rows = daily([10, 10, 10, 12, 14, 16])
        rows[-1]['volume'] = 0
        result = research.dual_sma(rows, AS_OF, fast=2, slow=3, terminal_policy='liquidate_last_close')
        self.assertGreater(result['open_quantity'], 0)
        self.assertEqual([r['action'] for r in result['fills']], ['enter'])
        self.assertEqual(result['orders'][-1]['status'], 'UNFILLED_NO_VOLUME')

    def test_opening_range_is_exact_existing_baseline_and_adverse_barrier_order(self):
        rows = intraday()
        result = research.opening_range(rows, AS_OF)
        expected = strategy_lab.replay(research.checked_bars(rows, AS_OF), 'opening_range_breakout')
        self.assertEqual(result['result'], expected)
        self.assertEqual(result['strategy_id'], 'strategy-lab-opening-range-breakout-1')
        self.assertEqual(result['parameters']['opening_bars'], 3)
        self.assertEqual(result['parameters']['bar_minutes'], 5)
        self.assertEqual(len(result['result']['trades']), 1)
        self.assertEqual(result['result']['trades'][0]['reason'], 'stop_or_gap')
        self.assertGreater(result['result']['trades'][0]['quantity'], 0)

    def test_explicit_parameter_and_bar_errors_do_not_switch_strategies(self):
        rows = daily([10]*8)
        for kwargs in ({'fast': 5, 'slow': 5}, {'delay_bars': -1}, {'terminal_policy': 'pretend_sold'},
                       {'cost_per_side_bps': 10000}, {'fast': True}, {'initial_cash': 0}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                research.dual_sma(rows, AS_OF, **kwargs)
        with self.assertRaisesRegex(ValueError, 'BAR_TIME_OR_CUTOFF'):
            research.dual_sma(rows, '2024-01-01T00:00:00Z')
        rows[3]['timestamp'] = rows[2]['timestamp']
        with self.assertRaises(ValueError):
            research.dual_sma(rows, AS_OF)

    def test_opening_range_rejects_overlapping_bar_intervals(self):
        rows = intraday()
        rows[1]['timestamp'] = '2025-01-01T14:37:00+00:00'
        with self.assertRaisesRegex(ValueError, 'OVERLAPPING_BAR_INTERVALS'):
            research.opening_range(rows, AS_OF)
        with self.assertRaises(ValueError):
            research.opening_range(intraday(), AS_OF, slippage_bps=10000)

    def test_csv_cli_retains_identity_and_exact_input_hash_without_overwrite(self):
        import csv
        import hashlib
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rows = daily([10, 10, 10, 12, 10, 8])
            csv_path = root / 'bars.csv'
            with csv_path.open('w', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=list(rows[0]))
                writer.writeheader(); writer.writerows(rows)
            params = root / 'params.json'
            params.write_text(json.dumps({'as_of': AS_OF, 'fast': 2, 'slow': 3}))
            output = root / 'result.json'
            args = [sys.executable, '-B', str(ROOT / 'scripts/strategy_research.py'),
                    'dual-sma', str(csv_path), str(params), '--private-output', str(output)]
            proc = subprocess.run(args, capture_output=True, text=True)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertEqual(proc.stdout, '')
            result = json.loads(output.read_text())
            self.assertEqual(result['source_csv_sha256'], hashlib.sha256(csv_path.read_bytes()).hexdigest())
            self.assertEqual(result['result']['strategy_id'], 'dual-sma-long-cash-1')
            prior = output.read_bytes()
            self.assertEqual(subprocess.run(args, capture_output=True).returncode, 2)
            self.assertEqual(output.read_bytes(), prior)


if __name__ == '__main__':
    unittest.main()
