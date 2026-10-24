"""Independent arithmetic and causal/adversarial cases, using fictional bars."""
import copy
from decimal import Decimal, Inexact, ROUND_UP, localcontext
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from costed_bar_replay import simulate, _load_json


def fixture():
    bars = [dict(open_at=f'2026-01-0{i}T09:30:00Z', close_at=f'2026-01-0{i}T16:00:00Z',
                 available_at=f'2026-01-0{i}T16:00:00Z', open='10', close='11', volume='100')
            for i in range(1, 5)]
    return dict(schema_version=1, as_of='2026-01-04T17:00:00Z', currency='USD',
                asset_class='equity', initial_cash='1000', bars=bars,
                signals=[dict(timestamp=bars[0]['close_at'], available_at=bars[0]['available_at'],
                              side='buy', quantity='20')],
                costs=dict(spread_bps='0', slippage_bps='0', fee_bps='0', fixed_fee='0'),
                max_participation='0.1', time_in_force='carry', quantity_step='1')


class CostedBarReplayTests(unittest.TestCase):
    def test_next_open_partial_carry_accounting(self):
        result = simulate(fixture())
        self.assertEqual([f['quantity'] for f in result['fills']], ['10', '10'])
        self.assertEqual(result['fills'][0]['at'], '2026-01-02T09:30:00Z')
        self.assertEqual((result['cash'], result['position'], result['equity']), ('800', '20', '1020'))
        self.assertIsNone(result['pending_order'])
        self.assertFalse(result['production_qualified'])

    def test_current_bar_volume_and_close_do_not_price_its_open_fill(self):
        data = fixture()
        base = simulate(data)['fills'][0]
        data['bars'][1].update(close='100000', volume='0')
        self.assertEqual(simulate(data)['fills'][0], base)

    def test_signal_availability_delays_fill(self):
        data = fixture()
        data['signals'][0]['available_at'] = '2026-01-02T12:00:00Z'
        self.assertEqual(simulate(data)['fills'][0]['at'], '2026-01-03T09:30:00Z')

    def test_same_timestamp_source_close_cannot_fill(self):
        data = fixture()
        data['bars'][1]['open_at'] = data['bars'][0]['close_at']
        self.assertEqual(simulate(data)['fills'][0]['at'], '2026-01-03T09:30:00Z')

    def test_exact_open_arrival_waits_for_later_open(self):
        data = fixture()
        data['signals'][0]['available_at'] = data['bars'][1]['open_at']
        self.assertEqual(simulate(data)['fills'][0]['at'], '2026-01-03T09:30:00Z')

    def test_costs_and_fee_inclusive_affordability(self):
        data = fixture()
        data['initial_cash'] = '103'
        data['costs'] = dict(spread_bps='100', slippage_bps='50', fee_bps='100', fixed_fee='1')
        result = simulate(data)
        fill = result['fills'][0]
        self.assertEqual((fill['quantity'], fill['price'], fill['fee']), ('9', '10.1', '1.909'))
        self.assertEqual(result['cash'], '10.191')
        self.assertEqual(result['pending_order']['remaining'], '11')

    def test_zero_cash_or_zero_volume_does_not_fill(self):
        for modify in ('cash', 'volume'):
            data = fixture()
            if modify == 'cash':
                data['initial_cash'] = '0'
            else:
                for bar in data['bars']:
                    bar['volume'] = '0'
            result = simulate(data)
            self.assertEqual(result['fills'], [])
            self.assertEqual(result['pending_order']['remaining'], '20')

    def test_cancel_after_first_attempt_partial_or_zero(self):
        data = fixture()
        data['time_in_force'] = 'cancel'
        self.assertEqual(simulate(data)['position'], '10')
        self.assertIsNone(simulate(data)['pending_order'])
        data['bars'][0]['volume'] = '0'
        self.assertEqual(simulate(data)['fills'], [])
        self.assertEqual(simulate(data)['journal'][-1]['remaining'], '20')

    def test_replace_remainder_and_cannot_short(self):
        data = fixture()
        data['signals'].append(dict(timestamp=data['bars'][1]['close_at'],
                                    available_at=data['bars'][1]['available_at'], side='sell', quantity='30'))
        result = simulate(data)
        self.assertEqual([f['side'] for f in result['fills']], ['buy', 'sell'])
        self.assertEqual((result['cash'], result['position']), ('1000', '0'))
        self.assertEqual(result['pending_order']['remaining'], '20')
        self.assertEqual([e for e in result['journal'] if e['event'] == 'cancel'][0]['remaining'], '10')

    def test_sell_fee_cannot_make_cash_negative(self):
        data = fixture()
        data['initial_cash'] = '101'
        data['costs']['fixed_fee'] = '1'
        data['signals'][0]['quantity'] = '10'
        data['signals'].append(dict(timestamp=data['bars'][1]['close_at'],
                                    available_at=data['bars'][1]['available_at'], side='sell', quantity='10'))
        data['bars'][2]['open'] = data['bars'][3]['open'] = '0.01'
        result = simulate(data)
        self.assertEqual(len(result['fills']), 1)
        self.assertEqual((result['cash'], result['position']), ('0', '10'))

    def test_final_signal_is_pending_without_forced_liquidation(self):
        data = fixture()
        data['signals'][0].update(timestamp=data['bars'][-1]['close_at'],
                                   available_at=data['bars'][-1]['available_at'])
        result = simulate(data)
        self.assertEqual(result['fills'], [])
        self.assertEqual(result['pending_order']['remaining'], '20')

    def test_late_older_volume_does_not_replace_new_observation(self):
        data = fixture()
        data['bars'][0].update(available_at='2026-01-02T17:00:00Z', volume='10000')
        data['signals'][0]['available_at'] = '2026-01-02T17:00:00Z'
        self.assertEqual(simulate(data)['fills'][0]['quantity'], '10')

    def test_fractional_steps_and_immutable_input(self):
        data = fixture()
        data.update(asset_class='spot_crypto', quantity_step='0.01')
        data['signals'][0]['quantity'] = '1.23'
        before = copy.deepcopy(data)
        self.assertEqual(simulate(data), simulate(data))
        self.assertEqual(data, before)
        self.assertEqual(simulate(data)['position'], '1.23')

    def test_cutoff_binds_bars_and_signals(self):
        for change in ('cutoff', 'bar_available', 'signal_available'):
            data = fixture()
            if change == 'cutoff':
                data['as_of'] = '2026-01-03T17:00:00Z'
            elif change == 'bar_available':
                data['bars'][-1]['available_at'] = '2026-01-05T00:00:00Z'
            else:
                data['signals'][0]['available_at'] = '2026-01-05T00:00:00Z'
            with self.subTest(change=change), self.assertRaises(ValueError):
                simulate(data)
        data = fixture()
        data['as_of'] = data['bars'][-1]['available_at']
        self.assertEqual(simulate(data)['position'], '20')

    def test_closed_finite_schema(self):
        mutations = [lambda d:d.update(schema_version=True), lambda d:d.update(currency='usd'),
            lambda d:d.update(currency='USDT'), lambda d:d.update(asset_class='future'),
            lambda d:d.update(initial_cash='-1'), lambda d:d.update(initial_cash='NaN'),
            lambda d:d.update(initial_cash=1000), lambda d:d.update(max_participation='1.1'),
            lambda d:d.update(quantity_step='0'), lambda d:d.update(extra='silent assumption'),
            lambda d:d['bars'][0].update(open='0'), lambda d:d['bars'][0].update(volume='Infinity'),
            lambda d:d['bars'][0].update(open_at='2026-01-01T09:30:00'),
            lambda d:d['bars'][0].update(available_at='2026-01-01T10:00:00Z'),
            lambda d:d['bars'].__setitem__(1,copy.deepcopy(d['bars'][0])),
            lambda d:d['signals'].append(copy.deepcopy(d['signals'][0])),
            lambda d:d['signals'][0].update(available_at='2026-01-01T15:00:00Z'),
            lambda d:d['signals'][0].update(quantity='1.5'),
            lambda d:d['signals'][0].update(side='short'),
            lambda d:d['costs'].update(slippage_bps='10000')]
        for mutate in mutations:
            data = fixture()
            mutate(data)
            with self.subTest(data=data), self.assertRaises(ValueError):
                simulate(data)

    def test_each_fill_preserves_accounting(self):
        data = fixture()
        data['costs'] = dict(spread_bps='12', slippage_bps='9', fee_bps='5', fixed_fee='0.07')
        cash, position = Decimal(data['initial_cash']), Decimal(0)
        for fill in simulate(data)['fills']:
            quantity, price, fee = map(Decimal, (fill['quantity'], fill['price'], fill['fee']))
            cash += (-quantity * price if fill['side'] == 'buy' else quantity * price) - fee
            position += quantity if fill['side'] == 'buy' else -quantity
            self.assertEqual(cash, Decimal(fill['cash']))
            self.assertEqual(position, Decimal(fill['position']))
            self.assertGreaterEqual(cash, 0)
            self.assertGreaterEqual(position, 0)

    def test_hostile_ambient_decimal_context_is_isolated(self):
        data = fixture()
        data['initial_cash'] = '103'
        data['costs'] = dict(spread_bps='100', slippage_bps='50', fee_bps='100', fixed_fee='1')
        expected = simulate(data)
        with localcontext() as context:
            context.prec, context.rounding = 3, ROUND_UP
            context.Emax, context.Emin = 2, -2
            context.traps[Inexact] = True
            self.assertEqual(simulate(data), expected)
            self.assertEqual(context.prec, 3)
            self.assertTrue(context.traps[Inexact])

    def test_cli_loader_rejects_duplicate_and_nonfinite_json(self):
        for text in ('{"a":1,"a":2}', '{"a":NaN}', '{"a":Infinity}'):
            with self.assertRaises(ValueError):
                _load_json(text)


if __name__ == '__main__':
    unittest.main()
