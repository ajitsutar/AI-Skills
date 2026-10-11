import copy
from datetime import date, timedelta
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from public_research import calculate, compare, digest, make_bundle, profile, review_frontier, verify
from research_report_checks import pe_claim, revision, scenario_checks


def fixture():
    grid = [(date(2025, 10, 1) + timedelta(days=i)).isoformat() for i in range(253)]
    periods = ['2026-03-31', '2025-12-31', '2025-09-30', '2025-06-30']
    def tab(fields, dates):
        return {'index': list(fields), 'columns': dates, 'data': list(fields.values())}
    rows = []
    for i in range(10):
        rows.append({'symbol': 'DEMO' + str(i), 'issuer_id': 'fictional:' + str(i),
            'sector': 'Industrials', 'industry': 'Fictional Machinery',
            'info': {'currency': 'USD', 'financialCurrency': 'USD', 'marketCap': 100,
                     'regularMarketPrice': 10, 'enterpriseValue': 115},
            'income': tab({'NetIncome': [2 + i] * 4, 'OperatingIncome': [3 + i] * 4}, periods),
            'cashflow': tab({'OperatingCashFlow': [4 + i] * 4, 'CapitalExpenditure': [-1] * 4}, periods),
            'balance': tab({'TotalDebt': [20 - i, 20], 'TotalAssets': [200, 180],
                            'CashAndCashEquivalents': [5, 5]}, ['2026-03-31', '2025-03-31']),
            'history': {'columns': ['Close', 'Adj Close', 'Volume'], 'index': grid,
                        'data': [[10, 10 + j * (i + 1) / 10000, 100] for j in range(253)]}})
    return {'schema_version': 1, 'fictional': True, 'profile_sha256': digest(profile()),
        'price_date': grid[-1], 'session_dates': grid,
        'mandate': {'hold': 'P1Y', 'universe': 'FICTIONAL', 'prompt_sha256': 'fictional'},
        'universe_symbols': [r['symbol'] for r in rows], 'rows': rows}


class PublicResearchTests(unittest.TestCase):
    def test_replay_and_order_independence(self):
        data = fixture(); expected = calculate(data, 3)
        data['rows'].reverse(); data['universe_symbols'].reverse()
        actual = calculate(data, 3)
        self.assertEqual(expected['research_candidates'], actual['research_candidates'])
        self.assertEqual([r['symbol'] for r in actual['research_candidates']], ['DEMO9', 'DEMO8', 'DEMO7'])
        self.assertEqual(verify(make_bundle(data, 3))['status'], 'REPLAY_MATCH')

    def test_missing_cell_never_zero_filled(self):
        data = fixture(); data['rows'][9]['balance']['data'][0][0] = None
        result = calculate(data, 3)
        self.assertFalse(result['full_universe_scored'])
        self.assertTrue(any(r['symbol'] == 'DEMO9' and 'MISSING' in r['reason'] for r in result['exclusions']))

    def test_each_capex_sign_checked(self):
        data = fixture(); data['rows'][9]['cashflow']['data'][1] = [1, -2, -2, -2]
        result = calculate(data, 3)
        self.assertTrue(any('NEGATIVE:capex' in r['reason'] for r in result['exclusions']))

    def test_complete_universe_required(self):
        data = fixture(); data['rows'].pop()
        with self.assertRaisesRegex(ValueError, 'COVERAGE'):
            calculate(data, 3)

    def test_duplicate_issuer_liquidity_selects_once(self):
        data = fixture(); row = copy.deepcopy(data['rows'][9]); row['symbol'] = 'CLASSB'
        for price in row['history']['data']:
            price[2] *= 2
        data['rows'].append(row); data['universe_symbols'].append(row['symbol'])
        result = calculate(data, 3)
        self.assertEqual(result['research_candidates'][0]['symbol'], 'CLASSB')
        self.assertNotIn('DEMO9', [r['symbol'] for r in result['review_queue']])
        row['history']['data'].pop(); row['history']['index'].pop()
        result = calculate(data, 3)
        self.assertNotIn('CLASSB', [r['symbol'] for r in result['review_queue']])
        self.assertNotIn('DEMO9', [r['symbol'] for r in result['review_queue']])

    def test_short_lists_cannot_pass(self):
        bundle = make_bundle(fixture(), 11)
        self.assertEqual(compare(bundle, bundle)['status'], 'INCOMPLETE_LISTS')

    def test_rate_limited_data_cannot_pass(self):
        data = fixture()
        data['rows'][0]['errors'] = [{'component': 'history', 'error': 'YFRateLimitError'}]
        bundle = make_bundle(data, 3)
        self.assertEqual(compare(bundle, bundle)['status'], 'INCOMPLETE_ACQUISITION')

    def test_bundle_owns_immutable_copy(self):
        data = fixture(); bundle = make_bundle(data, 3)
        data['mandate']['hold'] = 'changed'
        self.assertEqual(verify(bundle)['status'], 'REPLAY_MATCH')

    def test_non_rate_limit_acquisition_failure_cannot_pass(self):
        data = fixture()
        data['rows'][0]['errors'] = [{'component': 'info', 'error': 'TimeoutError'}]
        bundle = make_bundle(data, 3)
        self.assertEqual(compare(bundle, bundle)['status'], 'INCOMPLETE_ACQUISITION')

    def test_swallowed_empty_provider_result_cannot_pass(self):
        data = fixture()
        data['rows'][0]['income'] = {'index': [], 'columns': [], 'data': []}
        bundle = make_bundle(data, 3)
        self.assertEqual(compare(bundle, bundle)['status'], 'INCOMPLETE_ACQUISITION')

    def test_history_ineligible_financial_failure_remains_disclosed(self):
        data = fixture(); row = data['rows'][0]
        row['history']['index'] = row['history']['index'][1:]
        row['history']['data'] = row['history']['data'][1:]
        row['cashflow'] = {'index': [], 'columns': [], 'data': []}
        bundle = make_bundle(data, 3)
        self.assertEqual(bundle['result']['acquisition_failure_securities'], 1)
        self.assertEqual(bundle['result']['ranking_relevant_acquisition_failures'], 0)
        self.assertEqual(compare(bundle, bundle)['status'], 'PASS')
        row['errors'] = [{'component': 'history', 'error': 'Timeout'}]
        bundle = make_bundle(data, 3)
        self.assertEqual(compare(bundle, bundle)['status'], 'INCOMPLETE_ACQUISITION')

    def test_same_picks_from_other_universe_not_comparable(self):
        data = fixture(); a = make_bundle(data, 3)
        data['universe_symbols'].pop(0); data['rows'].pop(0)
        b = make_bundle(data, 3)
        with self.assertRaisesRegex(ValueError, 'UNIVERSE'):
            compare(a, b)

    def test_tampered_output_rejected(self):
        bundle = make_bundle(fixture(), 3)
        bundle['result']['research_candidates'].reverse()
        bundle['result_sha256'] = digest(bundle['result'])
        with self.assertRaisesRegex(ValueError, 'REPLAY'):
            verify(bundle)

    def test_horizon_mismatch_rejected(self):
        data = fixture(); a = make_bundle(data, 3)
        data['mandate']['hold'] = 'P5Y'; b = make_bundle(data, 3)
        with self.assertRaisesRegex(ValueError, 'MANDATE'):
            compare(a, b)

    def test_review_omission_blocks_frontier(self):
        result = calculate(fixture(), 3)
        state = review_frontier(result, ['DEMO9', 'DEMO7'])
        self.assertFalse(state['candidate_review_complete'])
        self.assertEqual(state['next_to_review'], ['DEMO8'])
        self.assertEqual(state['out_of_order_reviews'], ['DEMO7'])

    def test_ratio_uses_explicit_operands(self):
        self.assertFalse(pe_claim(306.28, 19.81, 13.8, 'FY2028', 'vendor core EPS')['matches_display'])
        self.assertTrue(pe_claim(306.28, 19.81, 15.46, 'FY2028', 'vendor core EPS')['matches_display'])

    def test_revision_period_mismatch_and_negative_base(self):
        with self.assertRaisesRegex(ValueError, 'PERIOD'):
            revision(5, 4, 'FY2027', 'FY2026')
        self.assertIsNone(revision(1, -1, 'FY2027', 'FY2027')['fraction'])

    def test_positive_bear_not_accepted_as_downside(self):
        cases = {name: {'earnings_or_cashflow_per_share': eps, 'exit_parameter': yield_,
            'valuation_method': 'yield', 'period': 'CY2027', 'basis': 'AFFO',
            'multiple_or_yield_rationale': 'Fictional scenario assumption'}
            for name, eps, yield_ in [('bear', 2.4, .09), ('central', 2.6, .08), ('bull', 2.75, .07)]}
        result = scenario_checks(22.88, cases)
        self.assertFalse(result['complete'])
        self.assertTrue(any('NO_PRICE_DOWNSIDE' in i for i in result['issues']))


if __name__ == '__main__':
    unittest.main()
