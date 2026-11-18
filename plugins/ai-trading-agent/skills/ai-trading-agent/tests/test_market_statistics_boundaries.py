"""Portable synthetic domain, schema and native-to-final projection controls."""
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import final_report
import market_flow
import market_sources
import market_sources_report
import portfolio_analytics
import test_market_flow as flow_fixture
import test_market_flow_report as report_fixture
import test_market_sources as sources_fixture

UNRESOLVED = [None, '', '  ', 'UNKNOWN', ' UnReSoLvEd ', 'N/A', 'unspecified', 0, False, [], {}]


def indexed(document):
    return {row['id']: row['payload'] for row in document['records']}


class BasisBoundaries(unittest.TestCase):
    def test_float_and_adv_unresolved_bases_independently(self):
        for value in UNRESOLVED:
            for targets, field in [(['float'], 'float'), (['d1', 'd2'], 'adv'),
                                   (['si', 'float', 'd1', 'd2'], 'both')]:
                document = flow_fixture.pressure_document()
                rows = indexed(document)
                for rid in targets:
                    rows[rid]['adjustment_basis'] = deepcopy(value)
                before = deepcopy(document)
                with self.subTest(value=value, targets=targets):
                    si = market_flow.positioning(document)['short_interest'][0]
                    if field in ('float', 'both'):
                        self.assertIsNone(si['short_interest_percent_float'])
                        self.assertEqual(si['float_adjustment_comparability'], 'UNKNOWN')
                        self.assertEqual(si['unreconciled_short_interest_percent_float'], 20)
                    else:
                        self.assertEqual(si['short_interest_percent_float'], 20)
                    if field in ('adv', 'both'):
                        self.assertIsNone(si['adv']['days_to_cover'])
                        self.assertIsNone(si['adv']['conditional_days_to_cover'])
                        self.assertEqual(si['adv']['share_adjustment_comparability'], 'UNKNOWN')
                        self.assertEqual(si['adv']['supplied_volume_arithmetic_mean'], 300)
                        self.assertEqual(si['adv']['unreconciled_share_count_quotient'], 4)
                    else:
                        self.assertEqual(si['adv']['days_to_cover'], 4)
                    self.assertEqual(market_flow.squeeze(document)['assessments'][0]['state'], 'INSUFFICIENT_EVIDENCE')
                    self.assertEqual(before, document)

    def test_own_benchmark_price_and_volume_are_independent(self):
        for value in UNRESOLVED:
            for targets, basis in [(['current'], 'price_basis'), (['benchmark'], 'price_basis'),
                                   (['current', 'benchmark'], 'price_basis'),
                                   (['b1', 'b2', 'current'], 'volume_basis')]:
                document = flow_fixture.pressure_document()
                rows = indexed(document)
                for rid in targets:
                    rows[rid][basis] = deepcopy(value)
                with self.subTest(value=value, targets=targets, basis=basis):
                    result = market_flow.analyze(document)
                    bar = next(row for row in result['cumulative_bars'] if row['record_id'] == 'current')
                    if basis == 'price_basis':
                        self.assertIsNone(bar['benchmark_relative_return_percent'])
                        self.assertEqual(bar['relative_volume'], 6)
                        if 'current' in targets:
                            self.assertIsNone(bar['return_percent'])
                            self.assertEqual(bar['unreconciled_price_return_percent'], 6)
                        else:
                            self.assertEqual(bar['return_percent'], 6)
                        self.assertEqual(bar['benchmark_price_comparability'], 'UNKNOWN')
                    else:
                        self.assertIsNone(bar['relative_volume'])
                        self.assertEqual(bar['benchmark_relative_return_percent'], 5)
                    self.assertNotEqual(market_flow.squeeze(document)['assessments'][0]['state'],
                                        'DEVELOPING_PRESSURE_HEURISTIC')

    def test_known_equal_and_mismatched_controls(self):
        document = flow_fixture.pressure_document()
        self.assertEqual(market_flow.squeeze(document)['assessments'][0]['state'], 'DEVELOPING_PRESSURE_HEURISTIC')
        rows = indexed(document)
        rows['float']['adjustment_basis'] = 'different_known_split_basis'
        rows['d1']['adjustment_basis'] = 'different_known_split_basis'
        rows['benchmark']['price_basis'] = 'different_known_price_basis'
        rows['b1']['volume_basis'] = 'different_known_volume_basis'
        position = market_flow.positioning(document)['short_interest'][0]
        self.assertEqual(position['float_adjustment_comparability'], 'MISMATCH')
        self.assertEqual(position['adv']['share_adjustment_comparability'], 'MISMATCH')
        current = next(row for row in market_flow.analyze(document)['cumulative_bars'] if row['record_id'] == 'current')
        self.assertEqual(current['benchmark_price_comparability'], 'MISMATCH')
        self.assertEqual(current['relative_volume'], 4.5)  # only matched b2 participates


class BoundBasisProjection(unittest.TestCase):
    setUp = report_fixture.MarketFlowReportTests.setUp
    sources = report_fixture.MarketFlowReportTests.sources
    analyze = report_fixture.MarketFlowReportTests.analyze
    compose = report_fixture.MarketFlowReportTests.compose
    export = report_fixture.MarketFlowReportTests.export

    def test_unresolved_actual_native_report_and_canonical_export(self):
        document = flow_fixture.pressure_document()
        rows = indexed(document)
        for row in rows.values():
            for field in ('adjustment_basis', 'price_basis', 'volume_basis'):
                if field in row:
                    row[field] = 'UNKNOWN'
        self.sources(document)
        result = self.analyze()['rows'][0]['operations']
        self.assertIsNone(result['positioning']['result']['short_interest'][0]['adv']['days_to_cover'])
        output = self.export()
        final_report.verify_response(output)
        response = json.loads((output / 'response.json').read_bytes())
        native = response['rows'][0]['result']['rows'][0]['operations']
        si = native['positioning']['result']['short_interest'][0]
        self.assertIsNone(si['short_interest_percent_float'])
        self.assertIsNone(si['adv']['days_to_cover'])
        self.assertEqual(si['adv']['unreconciled_share_count_quotient'], 4)
        self.assertEqual(native['squeeze']['result']['assessments'][0]['state'], 'INSUFFICIENT_EVIDENCE')
        text = (self.root / 'report' / 'first-response.md').read_text(encoding='utf8')
        self.assertIn('"days_to_cover": null', text)
        self.assertIn('"state": "INSUFFICIENT_EVIDENCE"', text)
        self.assertNotIn('"state": "DEVELOPING_PRESSURE_HEURISTIC"', text)
        evidence = native['positioning']['result']['evidence']['records']
        self.assertEqual(next(row for row in evidence if row['id'] == 'si')['payload']['adjustment_basis'], 'UNKNOWN')

    def test_amendment_ambiguity_survives_native_and_canonical_projection(self):
        document = AmendmentGraph.document(fork=True)
        self.sources(document)
        output = self.export()
        final_report.verify_response(output)
        response = json.loads((output / 'response.json').read_bytes())
        native = response['rows'][0]['result']['rows'][0]['operations']
        positions = native['positioning']['result']['short_interest']
        self.assertEqual({row['record_id'] for row in positions}, {'b', 'c'})
        self.assertTrue(all(not row['active_positioning_eligible'] for row in positions))
        self.assertTrue(all(row['state'] == 'INSUFFICIENT_EVIDENCE'
                            for row in native['squeeze']['result']['assessments']))
        self.assertTrue(all(set(row['amendment_ambiguity']['record_ids']) == {'si', 'b', 'c'} for row in positions))
        text = (self.root / 'report' / 'first-response.md').read_text(encoding='utf8')
        self.assertNotIn('"state": "DEVELOPING_PRESSURE_HEURISTIC"', text)
        self.assertIn('"active_positioning_eligible": false', text)


class AmendmentGraph(unittest.TestCase):
    @staticmethod
    def document(fork=False, cancel=False, equal_clock=False, future=False):
        document = flow_fixture.pressure_document()
        for row in document['records']:
            row['available_at'] = '2026-11-11T17:00:00Z'
            row['source'].update(observed_at=row['available_at'], retrieved_at=row['available_at'])
        a = document['records'][-1]
        a['available_at'] = '2026-11-11T18:00:00Z'
        a['source'].update(observed_at=a['available_at'], retrieved_at=a['available_at'])
        b = deepcopy(a)
        b.update(id='b', action='replace', supersedes='si', available_at='2026-11-11T19:00:00Z')
        if equal_clock:
            b['available_at'] = a['available_at']
        b['source'].update(observed_at=b['available_at'], retrieved_at=b['available_at'])
        c = deepcopy(b)
        c.update(id='c', supersedes='si' if fork else 'b',
                 action='cancel' if cancel else 'replace',
                 available_at='2026-11-12T20:00:00Z' if future else '2026-11-11T20:00:00Z')
        c['source'].update(observed_at=c['available_at'], retrieved_at=c['available_at'])
        document['records'].extend([b, c])
        return document

    def test_linear_fork_equal_clock_cancel_future_and_prior_cutoffs(self):
        linear = self.document()
        result = market_flow.squeeze(linear)
        self.assertEqual(result['assessments'][0]['short_interest_record_id'], 'c')
        self.assertEqual(result['assessments'][0]['state'], 'DEVELOPING_PRESSURE_HEURISTIC')
        for kwargs in ({'fork': True}, {'fork': True, 'cancel': True}, {'equal_clock': True}):
            document = self.document(**kwargs)
            original = deepcopy(document)
            with self.subTest(kwargs=kwargs):
                normalized = market_sources.normalize(document)
                self.assertEqual(len(normalized['records']), len(document['records']))
                self.assertTrue(any(row.get('amendment_ambiguity') for row in normalized['records']))
                positions = market_flow.positioning(document)['short_interest']
                self.assertTrue(positions)
                self.assertTrue(all(not row['active_positioning_eligible'] for row in positions))
                self.assertTrue(all(row['state'] == 'INSUFFICIENT_EVIDENCE'
                                    for row in market_flow.squeeze(document)['assessments']))
                self.assertEqual(document, original)
        # No inferred latest-wins resolution even when input order is reversed.
        fork = self.document(fork=True)
        fork['records'].reverse()
        self.assertTrue(all(row['state'] == 'INSUFFICIENT_EVIDENCE'
                            for row in market_flow.squeeze(fork)['assessments']))
        future = self.document(fork=True, future=True)
        active = market_flow.squeeze(future)['assessments']
        self.assertEqual(len(active), 1)
        self.assertEqual(active[0]['short_interest_record_id'], 'b')
        self.assertEqual(active[0]['state'], 'DEVELOPING_PRESSURE_HEURISTIC')
        prior = self.document(fork=True)
        prior['as_of'] = '2026-11-11T19:30:00Z'
        earlier = market_flow.squeeze(prior)['assessments']
        self.assertEqual(earlier[0]['short_interest_record_id'], 'b')
        self.assertEqual(earlier[0]['state'], 'DEVELOPING_PRESSURE_HEURISTIC')
        cancelled = self.document(cancel=True)
        self.assertEqual(market_flow.squeeze(cancelled)['assessments'], [])


class SecSchemaBoundaries(unittest.TestCase):
    def test_nested_shape_errors_are_controlled(self):
        for data in ([{'filings': value} for value in (None, [], 3, 'bad', False)]
                     + [{'filings': {'recent': value}} for value in (None, [], 3, 'bad', False)]
                     + [{'filings': {'recent': {'accessionNumber': ['one'], 'form': None}}}]):
            with self.subTest(data=data), self.assertRaises(ValueError):
                market_sources.parse(sources_fixture.parse_doc('sec_submissions', data=data))

    def test_multijob_report_retains_failure_order_and_independent_success(self):
        with tempfile.TemporaryDirectory(prefix='sec-schema-') as temp:
            root = Path(temp)
            jobs = []
            sources = []
            def retain(sid, name, value, fmt='json'):
                raw = json.dumps(value).encode() if fmt == 'json' else value
                (root / name).write_bytes(raw)
                sources.append({'id': sid, 'path': name, 'format': fmt, 'sha256': hashlib.sha256(raw).hexdigest()})
            malformed = ([None, [], 3, 'bad', False]
                         + [{'recent': value} for value in (None, [], 3, 'bad', False)]
                         + [{'recent': {'accessionNumber': ['one'], 'form': []}}])
            # Real valid native jobs before, between and after malformed jobs.
            for index, filings in enumerate([{'recent': {'accessionNumber': ['0000000001-26-000001'], 'form': ['8-K']}}, *malformed,
                                              {'recent': {'accessionNumber': ['0000000001-26-000001'],
                                                          'form': ['8-K']}}]):
                name = 'raw' + str(index) + '.json'
                retain('raw' + str(index), name, {'filings': filings}, 'json')
                jobs.append({'adapter': 'sec_submissions', 'source': deepcopy(sources_fixture.SOURCE),
                             'text_file': name, 'id_prefix': 'job' + str(index)})
            retain('jobs', 'jobs.json', {'jobs': jobs, 'cutoff': sources_fixture.NOW})
            manifest = root / 'ingress.json'
            manifest.write_text(json.dumps({'schema_version': 1, 'sources': sources}))
            pin = hashlib.sha256(manifest.read_bytes()).hexdigest()
            request = {'jobs_ref': {'source_id': 'jobs', 'pointer': '/jobs'},
                       'as_of_ref': {'source_id': 'jobs', 'pointer': '/cutoff'}}
            before = {path.name: path.read_bytes() for path in root.iterdir()}
            result = market_sources_report.analyze(request, manifest, pin, root)
            self.assertEqual(result['failed_operations'], len(malformed))
            self.assertEqual([row['job_index'] for row in result['rows']], list(range(len(jobs))))
            self.assertEqual([row['status'] for row in result['rows']], ['EXECUTED'] + ['FAILED'] * len(malformed) + ['EXECUTED'])
            self.assertEqual(len(result['rows'][-1]['result']['records']), 1)
            for row in result['rows'][1:-1]:
                self.assertEqual(row['original_job'], jobs[row['job_index']])
                self.assertEqual(row['error']['type'], 'ValueError')
                self.assertIn(row['error']['message'], ('SEC filings must be an object', 'Missing SEC recent array',
                                                      'SEC column lengths differ'))
                self.assertIn('raw_source_binding', row)
            self.assertEqual(before, {path.name: path.read_bytes() for path in root.iterdir()})
            for failure in (AttributeError('programmer error'), MemoryError('resource failure'), RuntimeError('unexpected')):
                with patch.object(market_sources, 'parse', side_effect=failure), self.assertRaises(type(failure)):
                    market_sources_report.analyze(request, manifest, pin, root)


def covariance_input(series):
    return {'returns': {symbol: [{'timestamp': '2026-01-%02dT21:00:00Z' % (index + 1), 'return': value}
                                for index, value in enumerate(values)] for symbol, values in series.items()},
            'weights': {symbol: 1 / len(series) for symbol in series},
            'min_observations': 3, 'periods_per_year': 252, 'shrinkage': 0}


class CovarianceBoundaries(unittest.TestCase):
    def test_nonconstant_covariance_underflow_or_overflow_is_explicitly_unavailable(self):
        for scale in (1e-200, 1e-160, 1e200):
            inputs = covariance_input({'A': [scale, 2*scale, 3*scale]})
            with self.subTest(scale=scale), self.assertRaisesRegex(ValueError, 'COVARIANCE_NUMERICAL_RANGE_UNAVAILABLE'):
                portfolio_analytics.covariance_risk(**inputs)
        # Annualization can overflow even when the sample covariance is finite.
        with self.assertRaisesRegex(ValueError, 'COVARIANCE_NUMERICAL_RANGE_UNAVAILABLE'):
            portfolio_analytics.covariance_risk(**covariance_input({'A': [0, 1e154, 2e154]}))

    def test_representable_small_and_large_correlation_and_constant_controls(self):
        for scale in (1e-150, .1, 1e150):
            values = {'CONST': [scale]*4, 'ORTHO': [scale, 0, 0, scale],
                      'VARY': [0, 0, scale, scale], 'IDENTICAL': [0, 0, scale, scale]}
            result = portfolio_analytics.covariance_risk(**covariance_input(values))
            index = {symbol: i for i, symbol in enumerate(result['symbols'])}
            with self.subTest(scale=scale):
                self.assertAlmostEqual(result['sample_correlation'][index['VARY']][index['VARY']], 1)
                self.assertAlmostEqual(result['sample_correlation'][index['VARY']][index['IDENTICAL']], 1)
                self.assertAlmostEqual(result['sample_correlation'][index['VARY']][index['ORTHO']], 0)
                self.assertIsNone(result['sample_correlation_reason'][index['VARY']][index['ORTHO']])
                self.assertTrue(all(cell is None for cell in result['sample_correlation'][index['CONST']]))
                self.assertEqual(result['constant_return_symbols'], ['CONST'])
        # Tiny constants are genuinely constant, even when their variance is zero.
        constant = portfolio_analytics.covariance_risk(**covariance_input({'A': [1e-200]*3}))
        self.assertEqual(constant['sample_correlation'], [[None]])
        self.assertEqual(constant['sample_correlation_reason'], [['CONSTANT_RETURN_SERIES']])

    def test_below_minus_one_rejected_with_symbol_timestamp_and_no_rounding_escape(self):
        for value in (-1.01, -2, '-1.00000000000000000001'):
            inputs = covariance_input({'SYNTH': [0, value, .3]})
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, 'SYNTH.*2026-01-02T21:00:00Z'):
                portfolio_analytics.covariance_risk(**inputs)

    def test_minus_one_large_positive_and_known_sample_covariance(self):
        result = portfolio_analytics.covariance_risk(**covariance_input({'SYNTH': [-1, 0, 10]}))
        # Mean is 3; unbiased sample variance is (16 + 9 + 49) / 2 = 37.
        self.assertAlmostEqual(result['covariance'][0][0], 37 * 252)
        self.assertEqual(result['constant_return_symbols'], [])

    def test_nullable_constant_mixed_orthogonal_identical_and_unchanged_covariance(self):
        values = {'CONSTANT': [.1] * 4, 'ORTHO': [.1, -.1, -.1, .1],
                  'VARY': [-.1, -.1, .1, .1], 'VARY_COPY': [-.1, -.1, .1, .1]}
        result = portfolio_analytics.covariance_risk(**covariance_input(values))
        index = {symbol: i for i, symbol in enumerate(result['symbols'])}
        constant = index['CONSTANT']
        self.assertTrue(all(cell is None for cell in result['sample_correlation'][constant]))
        self.assertTrue(all(row[constant] is None for row in result['sample_correlation']))
        self.assertTrue(all(reason == 'CONSTANT_RETURN_SERIES' for reason in result['sample_correlation_reason'][constant]))
        self.assertEqual(result['constant_return_symbols'], ['CONSTANT'])
        self.assertAlmostEqual(result['sample_correlation'][index['ORTHO']][index['VARY']], 0)
        self.assertIsNone(result['sample_correlation_reason'][index['ORTHO']][index['VARY']])
        self.assertAlmostEqual(result['sample_correlation'][index['VARY']][index['VARY_COPY']], 1)
        self.assertAlmostEqual(result['covariance'][index['VARY']][index['VARY']], (4 * .01 / 3) * 252)
        self.assertTrue(all(cell == 0 for cell in result['sample_correlation_legacy_zero_filled'][constant]))
        all_constant = portfolio_analytics.covariance_risk(**covariance_input({'A': [0, 0, 0]}))
        self.assertEqual(all_constant['sample_correlation'], [[None]])
        self.assertEqual(all_constant['annualized_volatility'], 0)

    def test_supported_standalone_json_route_serializes_nulls_and_rejects_invalid_domain(self):
        with tempfile.TemporaryDirectory(prefix='covariance-json-') as temp:
            path = Path(temp) / 'request.json'
            path.write_text(json.dumps({'operation': 'covariance', 'inputs': covariance_input({'A': [.1] * 4,
                                                                                           'B': [-.1, -.1, .1, .1]})}))
            script = Path(portfolio_analytics.__file__)
            result = subprocess.run([sys.executable, '-X', 'utf8', '-B', str(script), str(path)],
                                    capture_output=True, text=True, env=os.environ.copy())
            self.assertEqual(result.returncode, 0, result.stderr)
            parsed = json.loads(result.stdout)
            self.assertEqual(parsed['sample_correlation'][0], [None, None])
            self.assertIn('CONSTANT_RETURN_SERIES', result.stdout)
            path.write_text(json.dumps({'operation': 'covariance', 'inputs': covariance_input({'BAD': [0, -1.1, .1]})}))
            failed = subprocess.run([sys.executable, '-X', 'utf8', '-B', str(script), str(path)], capture_output=True, text=True)
            self.assertNotEqual(failed.returncode, 0)
            self.assertIn('BAD timestamp=2026-01-02T21:00:00Z', failed.stderr)
            self.assertEqual(failed.stdout, '')
            path.write_text(json.dumps({'operation': 'covariance', 'inputs': covariance_input({'RANGE': [1e-200, 2e-200, 3e-200]})}))
            unavailable = subprocess.run([sys.executable, '-X', 'utf8', '-B', str(script), str(path)], capture_output=True, text=True)
            self.assertNotEqual(unavailable.returncode, 0)
            self.assertIn('COVARIANCE_NUMERICAL_RANGE_UNAVAILABLE', unavailable.stderr)
            self.assertIn('symbols=RANGE', unavailable.stderr)
            self.assertEqual(unavailable.stdout, '')


if __name__ == '__main__':
    unittest.main()
