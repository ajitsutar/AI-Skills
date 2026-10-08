"""Fictional cash-account scenarios; no broker calls or performance claims."""
import copy
import tempfile
import unittest
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

from test_risk_and_execution import Fixture
from execution_ledger import ExecutionLedger, GateClosed


class SettledCashReserveTests(Fixture):
    def setUp(self):
        super().setUp()
        self.cost = (Decimal(self.order['quantity']) *
                     (Decimal(self.order['limit_price']) + Decimal(self.policy['limits']['fee_per_share'])))
        self.floor = Decimal('5000')

    def test_unsettled_proceeds_cannot_satisfy_reserve(self):
        self.policy['limits'].pop('intraday_settled_cash_floor_fraction', None)
        self.policy['limits'].pop('intraday_settled_cash_floor_amount', None)
        self.snapshot['settled_cash'] = str(self.cost + self.floor - Decimal('.01'))
        result = self.result()
        self.assertFalse(result['allowed'])
        self.assertEqual(result['reasons'], ['INTRADAY_SETTLED_CASH_RESERVE'])
        self.assertEqual(result['entry_disposition'], 'WAIT_FOR_CASH_BUDGET')
        self.assertEqual(Decimal(result['metrics']['cash_budget_shortfall']), Decimal('.01'))

    def test_exact_floor_after_fees_is_allowed(self):
        self.snapshot['settled_cash'] = str(self.cost + self.floor)
        self.assertTrue(self.result()['allowed'], self.result())

    def test_dollar_floor_can_be_configured_without_fraction(self):
        self.policy['limits'].update(intraday_settled_cash_floor_fraction='0',
                                     intraday_settled_cash_floor_amount='8000')
        self.snapshot['settled_cash'] = str(self.cost + 7999)
        self.blocked('INTRADAY_SETTLED_CASH_RESERVE')
        self.snapshot['settled_cash'] = str(self.cost + 8000)
        self.assertTrue(self.result()['allowed'], self.result())

    def test_larger_of_fraction_and_amount_is_used(self):
        for amount, expected in [('1000', '6000'), ('7000', '7000')]:
            with self.subTest(amount=amount):
                self.policy['limits'].update(intraday_settled_cash_floor_fraction='.06',
                                             intraday_settled_cash_floor_amount=amount)
                self.assertEqual(Decimal(self.result()['metrics']['intraday_settled_cash_floor']), Decimal(expected))

    def test_explicit_zero_disables_only_extra_intraday_reserve(self):
        self.policy['limits'].update(intraday_settled_cash_floor_fraction='0',
                                     intraday_settled_cash_floor_amount='0')
        self.snapshot['settled_cash'] = str(self.cost)
        self.assertTrue(self.result()['allowed'], self.result())
        self.snapshot['settled_cash'] = str(self.cost - 1)
        self.blocked('INSUFFICIENT_UNRESERVED_SETTLED_CASH')

    def test_invalid_configuration_blocks(self):
        for key, values in [('intraday_settled_cash_floor_fraction', ['-.1', '1.01', 'NaN', True, None]),
                            ('intraday_settled_cash_floor_amount', ['-1', 'Infinity', False, None])]:
            for value in values:
                with self.subTest(key=key, value=value):
                    self.policy['limits'][key] = value
                    self.blocked('INVALID_OR_MISSING_INPUT')
            del self.policy['limits'][key]

    def test_all_sleeve_pending_buys_including_cancel_pending_reserve_cash(self):
        self.snapshot['settled_cash'] = str(self.cost + self.floor + 500)
        for status in ['open', 'partially_filled', 'cancel_pending']:
            with self.subTest(status=status):
                self.snapshot['open_orders'] = [{'local_ref': 'pending-core', 'status': status,
                    'symbol': 'CORE_A', 'side': 'buy', 'sleeve': 'core', 'remaining_quantity': '10',
                    'reservation_price': '100', 'sector': 'technology'}]
                self.blocked('INTRADAY_SETTLED_CASH_RESERVE')
        self.snapshot['open_orders'] = []  # Only after broker confirms terminal and reconciliation.
        self.assertTrue(self.result()['allowed'], self.result())

    def test_round_trips_consume_cash_across_symbols_until_broker_settles(self):
        self.snapshot['settled_cash'] = str(self.floor + 2 * self.cost)
        self.assertTrue(self.result()['allowed'], self.result())
        # A buy and break-even sale restore ledger cash, but not settled cash.
        self.snapshot['settled_cash'] = str(self.floor + self.cost)
        self.policy['allowed_symbols'].append('OTHER')
        self.snapshot['quotes']['OTHER'] = copy.deepcopy(self.snapshot['quotes']['DEMO'])
        self.order['symbol'] = 'OTHER'
        self.assertTrue(self.result()['allowed'], self.result())
        self.snapshot['settled_cash'] = str(self.floor)
        self.blocked('INTRADAY_SETTLED_CASH_RESERVE')
        self.order['symbol'] = 'DEMO'
        self.blocked('INTRADAY_SETTLED_CASH_RESERVE')
        self.snapshot['settled_cash'] = str(self.floor + 2 * self.cost)  # Actual broker confirmation.
        self.assertTrue(self.result()['allowed'], self.result())

    def test_next_day_does_not_release_cash_without_broker_confirmation(self):
        self.snapshot['settled_cash'] = str(self.floor)
        self.now += timedelta(days=1)
        for record, fields in [(self.snapshot, ['as_of']), (self.snapshot['session'], ['open', 'close']),
                               (self.snapshot['quotes']['DEMO'], ['as_of']),
                               (self.order, ['created_at', 'expires_at', 'exit_by'])]:
            from risk_engine import timestamp
            for field in fields:
                record[field] = (timestamp(record[field]) + timedelta(days=1)).isoformat()
        self.blocked('INTRADAY_SETTLED_CASH_RESERVE')

    def test_settlement_does_not_revive_expired_signal(self):
        self.order['expires_at'] = (self.now - timedelta(seconds=1)).isoformat()
        self.snapshot['settled_cash'] = '100000'
        self.blocked('PROPOSAL_EXPIRED')
        self.assertEqual(self.result()['entry_disposition'], 'BLOCKED')

    def test_core_and_swing_do_not_inherit_intraday_reserve(self):
        self.policy['limits']['intraday_settled_cash_floor_amount'] = '99000'
        self.snapshot['settled_cash'] = str(self.cost)
        for sleeve, setup in [('core', 'core_rebalance'), ('swing', 'sma_trend')]:
            with self.subTest(sleeve=sleeve):
                self.order.update(sleeve=sleeve, setup=setup)
                self.policy['core_targets'] = {'DEMO': '.05'}
                self.assertTrue(self.result()['allowed'], self.result())

    def test_reserve_never_blocks_sale_of_owned_tactical_shares(self):
        self.snapshot['settled_cash'] = '0'
        self.snapshot['positions'] = [{'symbol': 'DEMO', 'quantity': '20', 'mark': '100',
                                      'sleeve': 'intraday', 'stop_price': '98', 'sector': 'technology'}]
        self.snapshot['cash'] = '98000'
        self.order['side'] = 'sell'
        self.snapshot['kill_switch'] = True
        self.assertTrue(self.result()['allowed'], self.result())
        self.assertEqual(self.result()['entry_disposition'], 'NOT_AN_ENTRY')

    def test_failed_cash_gate_never_creates_executable_journal_intent(self):
        self.snapshot['settled_cash'] = str(self.floor)
        with tempfile.TemporaryDirectory() as directory:
            ledger = ExecutionLedger(Path(directory) / 'execution.db')
            try:
                with self.assertRaisesRegex(GateClosed, 'INTRADAY_SETTLED_CASH_RESERVE'):
                    ledger.claim(self.policy, self.snapshot, self.order, {}, now=self.now)
                self.assertEqual(ledger.db.execute('SELECT COUNT(*) FROM orders').fetchone()[0], 0)
                self.assertEqual(ledger.unresolved(), [])
            finally:
                ledger.close()


if __name__ == '__main__':
    unittest.main()
