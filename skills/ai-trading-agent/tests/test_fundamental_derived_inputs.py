from pathlib import Path
import copy
import hashlib
import json
import math
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import fundamental_toolkit as f
import quant_workbench as q
import research_workflow as workflow


def request(**fields):
    return dict(operation='ratios', currency='USD', amount_unit='USD', **fields)


class DerivedRatioInputTests(unittest.TestCase):
    def test_midpoints_are_executed_once_and_operands_retained(self):
        d = request(opening_assets=120, closing_assets=200, revenue=96,
                    opening_equity=40, closing_equity=60, net_income=10,
                    opening_invested_capital=70, closing_invested_capital=90,
                    ebit=20, tax_rate=.2)
        before = copy.deepcopy(d)
        r = f.run(d)
        self.assertEqual(d, before)
        self.assertEqual(r['ratios']['asset_turnover'], .6)
        self.assertEqual(r['ratios']['roe'], .2)
        self.assertEqual(r['ratios']['roic'], .2)
        self.assertAlmostEqual(r['ratios']['dupont_roe'], .2)
        self.assertEqual(r['input_derivations']['average_assets']['value'], 160)
        self.assertEqual(r['input_derivations']['average_assets']['operands'], {'opening_assets': 120, 'closing_assets': 200})
        self.assertEqual(r['input_derivations']['average_assets']['source_basis_status'], 'NOT_VERIFIED')

    def test_zero_is_an_operand_and_zero_average_is_not_a_denominator(self):
        r = f.run(request(opening_assets=0, closing_assets=40, revenue=30))
        self.assertEqual(r['ratios']['asset_turnover'], 1.5)
        r = f.run(request(opening_assets=0, closing_assets=0, revenue=30, cfo=9, capex=2))
        self.assertIsNone(r['ratios']['asset_turnover'])
        self.assertEqual(r['ratios']['fcf'], 7)

    def test_partial_pair_never_uses_legacy_fallback_and_other_ratios_survive(self):
        r = f.run(request(opening_assets=120, average_assets=160, revenue=96, cfo=9, capex=2))
        self.assertIsNone(r['ratios']['asset_turnover'])
        self.assertEqual(r['input_derivations']['average_assets']['status'], 'UNAVAILABLE')
        self.assertEqual(r['ratios']['fcf'], 7)

    def test_conflicts_reject_and_tolerance_matches_use_computed_value(self):
        for fields in [dict(opening_assets=120, closing_assets=200, average_assets=80),
                       dict(revenue=90, gross_profit=35, cogs=56)]:
            with self.subTest(fields=fields), self.assertRaisesRegex(ValueError, 'CONFLICTING_DERIVED_INPUT'):
                f.run(request(**fields))
        r = f.run(request(opening_assets=120, closing_assets=200, average_assets=160 + 1e-8, revenue=96))
        self.assertEqual(r['input_derivations']['average_assets']['value'], 160)
        self.assertEqual(r['ratios']['asset_turnover'], .6)

    def test_negative_equity_and_capital_follow_existing_positive_ratio_domains(self):
        r = f.run(request(opening_equity=-30, closing_equity=-10, net_income=5,
                          opening_invested_capital=-8, closing_invested_capital=2,
                          ebit=6, tax_rate=.2))
        self.assertEqual(r['input_derivations']['average_equity']['value'], -20)
        self.assertEqual(r['input_derivations']['average_invested_capital']['value'], -3)
        self.assertIsNone(r['ratios']['roe'])
        self.assertIsNone(r['ratios']['roic'])

    def test_malformed_or_negative_assets_do_not_create_a_numeric_average(self):
        for bad in [True, '120', None, math.inf, math.nan, -1]:
            with self.subTest(bad=bad):
                r = f.run(request(opening_assets=bad, closing_assets=200, revenue=96, cfo=9, capex=2))
                self.assertIsNone(r['ratios']['asset_turnover'])
                self.assertEqual(r['input_derivations']['average_assets']['status'], 'UNAVAILABLE')
                self.assertEqual(r['ratios']['fcf'], 7)
                json.dumps(r, allow_nan=False)

    def test_finite_large_midpoint_avoids_sum_overflow(self):
        r = f.run(request(opening_assets=1e308, closing_assets=1e308, revenue=1e307))
        self.assertEqual(r['input_derivations']['average_assets']['value'], 1e308)
        self.assertAlmostEqual(r['ratios']['asset_turnover'], .1)

    def test_gross_profit_derives_cogs_without_imputing_missing_or_negative_values(self):
        r = f.run(request(revenue=90, gross_profit=35))
        self.assertEqual(r['input_derivations']['cogs']['value'], 55)
        self.assertAlmostEqual(r['ratios']['gross_margin'], 35 / 90)
        self.assertEqual(f.run(request(revenue=90, gross_profit=-10))['input_derivations']['cogs']['value'], 100)
        for fields in [dict(gross_profit=35), dict(revenue=30, gross_profit=35)]:
            r = f.run(request(**fields))
            self.assertIsNone(r['ratios']['gross_margin'])
            self.assertEqual(r['input_derivations']['cogs']['status'], 'UNAVAILABLE')

    def test_legacy_average_remains_supported_with_disclosure(self):
        r = f.run(request(average_assets=160, revenue=96, cogs=60))
        self.assertEqual(r['ratios']['asset_turnover'], .6)
        self.assertEqual(r['input_derivations'], {})
        self.assertEqual(r['derived_input_basis']['average_assets'], 'supplied_value; derivation_not_verified')
        self.assertEqual(r['derived_input_basis']['cogs'], 'supplied_value; derivation_not_verified')

    def test_source_bindings_flow_through_real_workbench_without_hand_calculated_average(self):
        source = {'opening': {'assets': 120}, 'closing': {'assets': 200}, 'income': {'revenue': 96, 'gross_profit': 36}}
        raw = json.dumps(source).encode()
        source_meta = {'statements': {'role': 'supplied fictional observations', 'sha256': hashlib.sha256(raw).hexdigest()}}
        def ref(pointer):
            return {'$source': {'id': 'statements', 'pointer': pointer}}
        argument = {'d': {'operation': {'$assumption': 'ratios', 'reason': 'Selected operation'},
                          'currency': {'$assumption': 'USD', 'reason': 'Fixture currency'},
                          'amount_unit': {'$assumption': 'USD', 'reason': 'Fixture units'},
                          'opening_assets': ref('/opening/assets'), 'closing_assets': ref('/closing/assets'),
                          'revenue': ref('/income/revenue'), 'gross_profit': ref('/income/gross_profit')}}
        bindings = []
        resolved = workflow.bind(argument, {'statements': source}, source_meta, bindings=bindings)
        self.assertNotIn('average_assets', resolved['d'])
        self.assertNotIn('cogs', resolved['d'])
        self.assertEqual(len([b for b in bindings if b['kind'] == 'SOURCE']), 4)
        document = {'schema_version': 1, 'contract': {'prompt': 'Compute supplied ratios', 'purpose': 'test', 'base_currency': 'USD', 'horizon_id': 'fixture', 'as_of': '2026-01-01T00:00:00Z'}, 'jobs': [{'id': 'r', 'operation': 'fundamental.calculate', 'inputs': resolved}]}
        r = q.run(document)['results'][0]
        self.assertEqual(r['status'], 'COMPUTED')
        self.assertEqual(r['result']['ratios']['asset_turnover'], .6)
        self.assertEqual(r['result']['ratios']['gross_margin'], .375)
        self.assertEqual(r['result']['input_derivations']['average_assets']['value'], 160)
        self.assertFalse(r['result']['execution_authorized'])


if __name__ == '__main__':
    unittest.main()
