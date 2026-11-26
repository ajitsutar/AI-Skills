import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from vendor_observations import LABEL, contract_check, normalize


class VendorTests(unittest.TestCase):
    def test_optional_live_capture_via_mocked_provider_and_replay(self):
        from research_data import vendor_finalist
        import pandas as pd
        class ProviderDataError(Exception):
            pass
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp).resolve() / 'out'
            provider = MagicMock()
            provider.__version__ = 'test'
            ticker = provider.Ticker.return_value
            ticker.get_info.return_value = {'debtToEquity': 25, 'regularMarketPrice': None}
            ticker.get_growth_estimates.return_value = pd.DataFrame({'stock': ['0.1']}, index=['+1y'])
            ticker.get_recommendations.side_effect = ProviderDataError('data unavailable')
            with patch.dict(sys.modules, {'yfinance': provider}), patch.dict(os.environ, {'AI_TRADING_NETWORK_MODE': 'online'}), \
                 patch('public_research_fetch.request_call', side_effect=lambda f: f()):
                result = vendor_finalist('FICT', out)
            self.assertEqual(result['fields']['debt_to_equity']['value'], .25)
            self.assertEqual(result['fields']['next_year_earnings_growth']['value'], .1)
            self.assertEqual(result['component_errors'], {'recommendations': 'ProviderDataError'})
            self.assertEqual(normalize(json.loads((out / 'vendor-input.json').read_text())), result)

    def test_retained_schema_contract(self):
        self.assertEqual(contract_check()['status'], 'PASS')
        raw = json.loads((ROOT / 'examples/fictional-vendor-observations.json').read_text())
        obs = normalize(raw)
        self.assertEqual(obs['basis'], LABEL)
        self.assertEqual(obs['fields']['debt_to_equity']['reported_unit'], 'percent')
        self.assertTrue(obs['ttm_growth_evidence'].startswith('TWO_COMPARABLE_TTM_PERIODS_NOT_ESTABLISHED'))
        self.assertEqual(obs['recommendations']['counts']['hold'], 0)
        self.assertEqual(obs['revenue_trend_proxy']['status'], 'NO_PROXY_AUTHORIZED')
        unavailable = normalize(raw, 'revenueQuarterlyGrowth')['revenue_trend_proxy']
        self.assertIsNone(unavailable['value'])
        general = normalize(raw, 'revenueGrowth')['revenue_trend_proxy']
        self.assertEqual(general['value'], .08)
        self.assertFalse(general['strict_ttm_gate_satisfied'])

    def test_missing_wrong_period_and_nonfinite_give_no_substitution(self):
        r = normalize({'info': {'earningsGrowth': 4, 'regularMarketPrice': 0, 'marketCap': 5000,
                    'revenueQuarterlyGrowth': 'nan'}, 'growth_estimates': [{'period': '0q', 'growth': .8}]})
        self.assertIsNone(r['fields']['next_year_earnings_growth']['value'])
        self.assertIsNone(r['fields']['quarterly_revenue_growth']['value'])
        self.assertEqual(r['market_cap_rescaling'], 'UNAVAILABLE_MISSING_PRICE_OR_CAP')
        self.assertEqual(r['recommendations']['status'], 'MISSING_OR_INVALID')

    def test_split_zero_and_invalid_analyst_counts(self):
        raw = {'growth_estimates': {'index': ['0q', '+1y'], 'columns': ['stock'], 'data': [[.8], [0]]},
               'recommendations': [{'period': '0m', 'strongBuy': 1, 'buy': -1, 'hold': 3, 'sell': 1, 'strongSell': 0}]}
        r = normalize(raw)
        self.assertEqual(r['fields']['next_year_earnings_growth']['value'], 0)
        self.assertEqual(r['recommendations']['status'], 'MISSING_OR_INVALID')
        self.assertIsNone(r['recommendations']['counts']['buy'])
        raw['growth_estimates']['index'] = ['+1y', '+1y']
        with self.assertRaisesRegex(ValueError, 'AMBIGUOUS'):
            normalize(raw)
