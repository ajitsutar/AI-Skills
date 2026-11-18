import copy
from datetime import date, timedelta
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import report_facts as rf
import public_research as public
import quant_workbench as qw


def encoded(value):
    return json.dumps(value, allow_nan=False).encode()


def quant_document(jobs, horizon='P19M'):
    return {'schema_version': 1, 'contract': {'prompt': 'PRIVATE_PROMPT_SENTINEL',
        'purpose': 'fictional local comparison', 'base_currency': 'CAD',
        'horizon_id': horizon, 'as_of': '2026-10-13T16:00:00Z'}, 'jobs': jobs}


def synthetic_public():
    grid = [(date(2025, 4, 1) + timedelta(days=i)).isoformat() for i in range(253)]
    quarters = ['2025-09-30', '2025-06-30', '2025-03-31', '2024-12-31']
    def table(fields, dates):
        return {'index': list(fields), 'columns': dates, 'data': list(fields.values())}
    rows = []
    for i in range(8):
        # Intentional equal values: ordering must not manufacture strict superiority.
        rows.append({'symbol': f'TIED{i}', 'issuer_id': f'issuer{i}', 'sector': 'Industrials',
            'industry': 'Synthetic Equipment', 'info': {'currency': 'USD', 'financialCurrency': 'USD',
                'marketCap': 8400, 'regularMarketPrice': 37, 'enterpriseValue': 9000},
            'income': table({'NetIncome': [83] * 4, 'OperatingIncome': [109] * 4}, quarters),
            'cashflow': table({'OperatingCashFlow': [121] * 4, 'CapitalExpenditure': [-28] * 4}, quarters),
            'balance': table({'TotalDebt': [980, 1000], 'TotalAssets': [12300, 11700],
                'CashAndCashEquivalents': [315, 300]}, ['2025-09-30', '2024-09-30']),
            'history': {'columns': ['Close', 'Adj Close', 'Volume'], 'index': grid,
                'data': [[37, 37 + j / 100, 600] for j in range(253)]}})
    return {'schema_version': 1, 'fictional': True, 'profile_sha256': public.digest(public.profile()),
        'price_date': grid[-1], 'session_dates': grid,
        'mandate': {'hold': 'P29M', 'universe': 'SYNTHETIC', 'prompt_sha256': 'fixture'},
        'universe_symbols': [r['symbol'] for r in rows], 'rows': rows}


def facts(report, metric):
    return [f for f in report['facts'] if f['metric'] == metric]


class ReportFactsTests(unittest.TestCase):
    def test_reproducible_projection_and_exact_pointers(self):
        bundle = qw.freeze(quant_document([{'id': 'odd-scale', 'operation': 'ops.shortfall',
            'inputs': {'side': 'sell', 'intended_quantity': 17, 'decision_price': 83,
                'arrival_price': 82.8, 'terminal_price': 79, 'fills': [{'id': 'partial-1', 'quantity': 11, 'price': 82.4}], 'fees': 2.73}}]))
        raw = encoded(bundle)
        a = rf.project(raw, 'quant'); b = rf.project(raw, 'quant')
        self.assertEqual(a, b)
        self.assertEqual(rf.markdown(a), rf.markdown(b))
        self.assertEqual(facts(a, 'Explicit fees')[0]['value'], 2.73)
        for f in a['facts']:
            self.assertEqual(f['source']['artifact_sha256'], hashlib.sha256(raw).hexdigest())
            if f['missingness'] is None:
                self.assertEqual(f['value'], rf.pointer(bundle, f['source']['pointer']))
        self.assertNotIn('PRIVATE_PROMPT_SENTINEL', json.dumps(a))
        self.assertNotIn('execution_authorized', json.dumps(a))
        self.assertEqual(facts(a, 'Total implementation shortfall')[0]['horizon'], 'P19M')

    def test_return_series_does_not_become_account_drawdown(self):
        bundle = qw.freeze(quant_document([{'id': 'trade-capital', 'operation': 'validation.tail',
            'inputs': {'returns': [.17, -.22, .06, -.09], 'confidence': .91}}], 'four trades'))
        f = facts(rf.project(encoded(bundle), 'quant'), 'Input-series maximum drawdown')[0]
        self.assertIn('account/trade capital base unknown', f['basis'])
        self.assertEqual(f['denominator'], 'running peak synthetic wealth')
        self.assertEqual(f['horizon'], 'four trades')

    def test_portfolio_cost_and_drawdown_have_model_equity_basis(self):
        doc = {'symbols': ['Z'], 'initial_equity': 7300, 'initial_weights': [.2], 'cash_floor': .1,
            'return_basis': 'total_return_decimal', 'universe_evidence': 'synthetic', 'corporate_action_evidence': 'synthetic',
            'periods': [{'start': '2024-02-01T00:00:00Z', 'end': '2024-02-02T00:00:00Z',
                'returns': {'Z': -.13}, 'tradable': {'Z': True}, 'cash_return': .0007,
                'benchmark_return': -.03, 'decision': {'known_at': '2024-01-31T23:00:00Z', 'weights': [.67], 'evidence_hash': 'synthetic'},
                'one_way_costs': [.013], 'impact_coefficients': [0], 'max_trade_values': [5000]}]}
        bundle = qw.freeze(quant_document([{'id': 'book', 'operation': 'backtest.portfolio', 'inputs': {'document': doc}}]))
        r = rf.project(encoded(bundle), 'quant')
        f = facts(r, 'Modeled portfolio maximum drawdown')[0]
        self.assertEqual(f['denominator'], 'running peak modeled portfolio equity')
        self.assertIn('not trade-capital', f['basis'])
        self.assertGreater(facts(r, 'Modeled total costs')[0]['value'], 0)
        self.assertEqual(f['metadata_sources']['helper_inputs'], '/input/jobs/0/inputs')

    def test_rejection_never_exports_stale_numeric_result(self):
        bundle = qw.freeze(quant_document([{'id': 'bad', 'operation': 'risk.option',
            'inputs': {'spot': 71, 'strike': 80, 'years': 2, 'volatility': .31, 'rate': .03, 'exercise_style': 'american'}}]))
        job = bundle['result']['results'][0]
        self.assertEqual(job['status'], 'REJECTED_INPUT')
        job['result'] = {'price': 9999, 'execution_authorized': False}
        raw = encoded(bundle)
        r = rf.project(raw, 'quant')
        self.assertEqual(facts(r, 'Helper job status')[0]['value'], 'REJECTED_INPUT')
        self.assertNotIn(9999, [f['value'] for f in r['facts']])
        self.assertEqual(facts(r, 'Reported non-computation reason')[0]['missingness'], 'source_text_withheld')
        included = rf.project(raw, 'quant', include_source_text=True)
        self.assertEqual(facts(included, 'Reported non-computation reason')[0]['value'], job['reason'])

    def test_missing_and_mismatched_metadata_not_imputed(self):
        bundle = qw.freeze(quant_document([{'id': 'x', 'operation': 'validation.tail', 'inputs': {'returns': [.04, -.07, .02]}}]))
        bundle['input']['contract']['horizon_id'] = 'P100Y'
        r = rf.project(encoded(bundle), 'quant')
        self.assertFalse(r['checks'][0]['embedded_input_hash_matches'])
        self.assertIsNone(facts(r, 'Input-series maximum drawdown')[0]['horizon'])
        bare = rf.project(encoded(bundle['result']), 'quant')
        self.assertIsNone(facts(bare, 'Input-series maximum drawdown')[0]['horizon'])
        bundle['input']['jobs'] = [7]
        with self.assertRaisesRegex(ValueError, 'INVALID_EMBEDDED_INPUT_SCHEMA'):
            rf.project(encoded(bundle), 'quant')

    def test_public_factor_labels_ties_and_literal_decimal_values(self):
        bundle = public.make_bundle(synthetic_public(), 4)
        r = rf.project(encoded(bundle), 'public-vqm')
        roa = facts(r, 'Return on average assets')
        self.assertEqual(len(roa), 8)
        self.assertEqual(len({f['value'] for f in roa}), 1)
        self.assertEqual(roa[0]['value'], bundle['result']['scores'][0]['quality_raw'][0])
        self.assertIsInstance(roa[0]['value'], str)
        self.assertIn('not ROE', roa[0]['basis'])
        self.assertEqual(roa[0]['horizon'], 'P29M')
        self.assertEqual(len({f['value'] for f in facts(r, 'Equal-weight VQM score')}), 1)
        self.assertNotIn('rank', {f['unit'] for f in r['facts']})

    def test_incompatible_scorer_cannot_supply_known_factor_labels(self):
        bundle = public.make_bundle(synthetic_public(), 4)
        bundle['scorer_sha256'] = '0' * 64
        r = rf.project(encoded(bundle), 'public-vqm')
        self.assertEqual(facts(r, 'Return on average assets'), [])
        self.assertTrue(facts(r, 'Unmapped VQM component'))

    def test_public_rejected_or_unknown_status_preserves_reason_without_stale_scores(self):
        bundle = public.make_bundle(synthetic_public(), 4)
        for status in ('REJECTED_INPUT', 'FUTURE_UNRECOGNIZED_STATUS', None):
            with self.subTest(status=status):
                changed = copy.deepcopy(bundle)
                if status is None:
                    del changed['result']['status']
                else:
                    changed['result']['status'] = status
                changed['result']['reason'] = 'Supplied rejection explanation'
                report = rf.project(encoded(changed), 'public-vqm', include_source_text=True)
                self.assertEqual(facts(report, 'Reported non-scoring reason')[0]['value'], changed['result']['reason'])
                self.assertFalse(any('/scores/' in f['source']['pointer'] for f in report['facts']))
                self.assertEqual(facts(report, 'Public research result status')[0]['value'], status)
        bare = rf.project(encoded({'status': 'REJECTED_INPUT', 'reason': 'bad'}), 'public-vqm')
        self.assertEqual(facts(bare, 'Public research result status')[0]['value'], 'REJECTED_INPUT')

    def test_financial_adapter_uses_equity_not_assets_definition(self):
        data = synthetic_public()
        for row in data['rows']:
            row['sector'] = 'Financial Services'
            row['industry'] = 'Insurance - Specialty'
            row['income']['index'].append('NetIncomeCommonStockholders')
            row['income']['data'].append([71] * 4)
            row['balance']['index'].append('CommonStockEquity')
            row['balance']['data'].append([4300, 4100])
        bundle = public.make_bundle(data, 2)
        r = rf.project(encoded(bundle), 'public-vqm')
        self.assertEqual(facts(r, 'Return on average assets'), [])
        roe = facts(r, 'Return on average common equity')
        self.assertEqual(len(roe), 8)
        self.assertEqual(roe[0]['value'], bundle['result']['scores'][0]['quality_raw'][0])
        self.assertIn('common equity', roe[0]['denominator'])

    def test_unknown_adapter_and_missing_component_stay_unknown(self):
        bundle = public.make_bundle(synthetic_public(), 4)
        bundle['result']['scores'][0]['adapter'] = 'future_new_adapter'
        bundle['result']['scores'][1]['quality_raw'][0] = None
        r = rf.project(encoded(bundle), 'public-vqm')
        self.assertTrue(facts(r, 'Unmapped VQM component'))
        nulls = [f for f in facts(r, 'Return on average assets') if f['value'] is None]
        self.assertEqual(nulls[0]['missingness'], 'null')

    def test_custom_binding_is_selection_not_expression_or_authentication(self):
        bundle = qw.freeze(quant_document([{'id': 'x', 'operation': 'validation.tail', 'inputs': {'returns': [.04, -.07, .02]}}]))
        bundle['extra'] = {'a/b~c': 412.5}
        custom = encoded({'facts': [{'pointer': '/extra/a~1b~0c', 'metric': 'Declared measure',
            'denominator': 'asserted capital', 'unit': 'USD', 'horizon': 'P8D'},
            {'pointer': '/missing', 'metric': 'Absent observation'}]})
        r = rf.project(encoded(bundle), 'quant', custom)
        f = facts(r, 'Declared measure')[0]
        self.assertEqual(f['value'], 412.5)
        self.assertEqual(f['semantic_mapping'], 'CUSTOM_DECLARED_UNVERIFIED')
        self.assertEqual(facts(r, 'Absent observation')[0]['missingness'], 'absent')
        with self.assertRaises(ValueError):
            rf.project(encoded(bundle), 'quant', encoded({'facts': [{'pointer': '/extra', 'metric': 'Bad', 'expression': '1+2'}]}))
        with self.assertRaises(ValueError):
            rf.pointer(bundle, "__import__('os')")
        with self.assertRaisesRegex(ValueError, 'EXECUTION_METADATA_NOT_A_REPORT_FACT'):
            rf.project(encoded(bundle), 'quant', encoded({'facts': [{'pointer': '/result/execution_authorized', 'metric': 'Permission'}]}))

    def test_strict_json_and_markdown_escape(self):
        for bad in [b'{"x":NaN}', b'{"x":1e999}', b'{"x":1,"x":2}']:
            with self.assertRaises(ValueError):
                rf.project(bad, 'quant')
        r = rf.project(encoded({'results': []}), 'quant', encoded({'facts': [{'pointer': '/missing', 'metric': '<script>|`bad`![private](https://host.invalid/pixel)'}]}))
        md = rf.markdown(r)
        self.assertNotIn('<script>', md)
        self.assertIn('&#124;', md)
        self.assertNotIn('![private]', md)
        self.assertIn('!&#91;private&#93;', md)

    def test_nested_status_and_warning_preserved_with_unknown_value(self):
        bundle = qw.freeze(quant_document([{'id': 'nonconventional', 'operation': 'ops.xirr',
            'inputs': {'cashflows': [{'at': '2023-01-01T00:00:00Z', 'amount': -375},
                {'at': '2024-01-01T00:00:00Z', 'amount': 501}, {'at': '2025-01-01T00:00:00Z', 'amount': -180}]}},
            {'id': 'short-series', 'operation': 'validation.tail', 'inputs': {'returns': [.03, -.04, .06]}}]))
        r = rf.project(encoded(bundle), 'quant')
        self.assertEqual(facts(r, 'Helper result status')[0]['value'], 'AMBIGUOUS_OR_NONCONVENTIONAL_CASHFLOWS')
        self.assertEqual(facts(r, 'Annualized XIRR')[0]['missingness'], 'null')
        self.assertEqual(facts(r, 'Helper result warning')[0]['missingness'], 'source_text_withheld')
        text = rf.project(encoded(bundle), 'quant', include_source_text=True)
        self.assertEqual(facts(text, 'Helper result warning')[0]['value'], 'Sparse empirical tail')

    def test_cli_explicit_private_export_and_no_overwrite_or_stdout_data(self):
        with tempfile.TemporaryDirectory() as folder:
            source, dest = Path(folder) / 'source.json', Path(folder) / 'facts.json'
            source.write_bytes(encoded({'results': [], 'authorization': 'SECRET_SENTINEL'}))
            command = [sys.executable, '-B', str(ROOT / 'scripts/report_facts.py'), 'quant', str(source), '--private-output', str(dest)]
            done = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(done.returncode, 0, done.stderr)
            self.assertEqual(done.stdout, '')
            self.assertNotIn('SECRET_SENTINEL', dest.read_text())
            old = dest.read_bytes()
            again = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(again.returncode, 2)
            self.assertEqual(old, dest.read_bytes())
            self.assertNotIn(str(source), again.stderr)
        with self.assertRaises(ValueError):
            rf.local_path('https://example.invalid/a.json')
        with self.assertRaises(ValueError):
            rf.local_path('\\\\server\\share\\a.json')


if __name__ == '__main__':
    unittest.main()
