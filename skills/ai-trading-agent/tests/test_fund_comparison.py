"""Synthetic binding, delivery and independent arithmetic checks."""
from copy import deepcopy
from pathlib import Path
import hashlib
import json
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import fund_comparison as fc
import portfolio_decision
import source_exposure
import quant_workbench


def source(value, sid, adapter, scope=None):
    text = json.dumps(value, separators=(',', ':')) if not isinstance(value, str) else value
    result = {'id': sid, 'text': text, 'sha256': hashlib.sha256(text.encode()).hexdigest(),
              'adapter': adapter, 'bindings': {'root': ''}, 'role': 'supplied_observation',
              'provenance': {'label': 'synthetic original'}}
    if scope is not None:
        result['scope'] = scope
    return result


def fixture():
    market = {'currency': 'CAD', 'identities': {
        'TREE.A': {'issuer_id': 'orchard', 'kind': 'common_stock', 'share_class': 'A'},
        'TREE.B': {'issuer_id': 'orchard', 'kind': 'common_stock', 'share_class': 'B'},
        'SHIP': {'issuer_id': 'harbor', 'kind': 'common_stock'}}, 'funds': [
        {'symbol': 'GROVE', 'holdings_coverage': '0.8', 'holdings_as_of': '2032-08-12',
         'bid_ask_spread_bps': '13.0000000000000000007',
         'holdings': [{'symbol': 'TREE.B', 'weight': '0.45'}, {'symbol': 'SHIP', 'weight': '0.35'}],
         'expense_ratio': '0.0014', 'benchmark': 'synthetic market', 'distribution_yield': '0.02'}]}
    context = {'schema_version': 1, 'role': 'capital for a planned purchase', 'horizon': 'eight months',
               'current_holdings': [{'symbol': 'TREE.A', 'quantity': '3'}, {'symbol': 'UNMAPPED'}],
               'future_positions': [{'symbol': 'TREE.B', 'quantity': '19'}]}
    return {'schema_version': 1, 'currency': 'CAD',
        'request': source(context, 'request', 'fund_report_context_v1', 'primary'),
        'exposure_sources': [source(market, 'facts', 'portfolio_context_v1')]}


def set_context(doc, change):
    value = json.loads(doc['request']['text']); change(value)
    doc['request'] = source(value, 'request', 'fund_report_context_v1', 'primary')


def set_market(doc, change):
    value = json.loads(doc['exposure_sources'][0]['text']); change(value)
    doc['exposure_sources'][0] = source(value, 'facts', 'portfolio_context_v1')


class FundComparisonTests(unittest.TestCase):
    def test_exact_quote_no_cost_and_independent_weight_overlap(self):
        delivery = fc.fund_comparison_report(fixture()); report = delivery['report']; fund = report['funds'][0]
        self.assertEqual(fund['quote']['value'], '13.0000000000000000007')
        self.assertIsNone(fund['friction']['applied_costs'])
        self.assertFalse(fund['friction']['quoted_spread_added_to_costs'])
        self.assertEqual(fund['composition']['issuer_total_fund_weight_fractions'], {'orchard': '9/20', 'harbor': '7/20'})
        self.assertEqual(fund['composition']['gaps'][0]['total_fund_weight_fraction'], '1/5')
        rows = fund['assessment_by_scope']['primary']['current_holdings_overlap']['rows']
        self.assertEqual(len(rows), 2); self.assertEqual(rows[0]['fund_total_weight_fraction'], '9/20')
        self.assertEqual(rows[1]['status'], 'ISSUER_IDENTITY_UNKNOWN')
        self.assertEqual(rows[0]['share_class'], 'A')
        self.assertEqual(report['status'], 'COMPLETE_FOR_BOUND_SCOPE')
        self.assertEqual(fc.verify_delivery(fixture(), delivery)['status'], 'VERIFIED_GENERATED_PROJECTIONS')
        for name in ('markdown', 'summary'):
            self.assertIn('eight months', delivery['artifacts'][name])
            self.assertIn('capital for a planned purchase', delivery['artifacts'][name])
            self.assertIn('Losses can persist', delivery['artifacts'][name])
            self.assertIn('UNMAPPED', delivery['artifacts'][name])
            self.assertIn('13.0000000000000000007', delivery['artifacts'][name])

    def test_explicit_native_model_and_unresolved_reference(self):
        doc = fixture(); doc['friction_models'] = {'GROVE': {'scenario_name': 'declared midpoint model', 'input': {
            'currency': 'CAD', 'role': 'hypothetical_scenario', 'price_basis': 'midpoint',
            'costs': [{'id': 'commission', 'amount': '0.85', 'unit': 'per_order', 'phase': 'entry'}],
            'modeled_slippage': {'id': 'slippage', 'amount': '3', 'unit': 'bps_notional', 'phase': 'entry',
                'convention': 'one_way', 'reference_price_basis': 'midpoint', 'overlap': 'independent'}}}}
        native = fc.build_report(doc)['funds'][0]['friction']
        self.assertEqual(native['status'], 'EXPLICIT_COST_MODEL')
        self.assertEqual([x['amount'] for x in native['applied_costs']], ['0.85', '3'])
        self.assertEqual(len(native['applied_costs']), 2)  # quote is never a third cost
        self.assertEqual(native, portfolio_decision.friction_context(native['retained_input']))
        doc['friction_models']['GROVE']['input']['price_basis'] = 'unknown'
        result = fc.fund_comparison_report(doc)
        self.assertIsNone(result['report']['funds'][0]['friction']['applied_costs'])
        self.assertIn('Native applied costs (only explicit model; no quote conversion): null', result['artifacts']['summary'])

    def test_quote_zero_missing_invalid_large_and_duplicates(self):
        for value, expected in [('0', 'SOURCE_BOUND_OBSERVATION'), (None, 'UNRESOLVED'),
                                ('-2', 'UNRESOLVED'), (True, 'UNRESOLVED'), ('NaN', 'UNRESOLVED'),
                                ('1e9999', 'UNRESOLVED')]:
            with self.subTest(value=value):
                doc = fixture(); set_market(doc, lambda x: x['funds'][0].update(bid_ask_spread_bps=value))
                fund = fc.build_report(doc)['funds'][0]
                self.assertEqual(fund['quote']['status'], expected)
                self.assertIsNone(fund['friction']['applied_costs'])
        doc = fixture(); other = deepcopy(doc['exposure_sources'][0]); other['id'] = 'duplicate'
        doc['exposure_sources'].append(other)
        self.assertEqual(len(fc.build_report(doc)['funds'][0]['quote']['observations']), 2)
        parsed = json.loads(other['text']); parsed['funds'][0]['bid_ask_spread_bps'] = '17'
        doc['exposure_sources'][1] = source(parsed, 'duplicate', 'portfolio_context_v1')
        self.assertEqual(fc.build_report(doc)['funds'][0]['quote']['status'], 'UNRESOLVED')

    def test_exact_json_numeric_lexeme_and_quote_time(self):
        doc = fixture(); s = doc['exposure_sources'][0]
        s['text'] = s['text'].replace('"13.0000000000000000007"', '13.0000000000000000007')
        s['sha256'] = hashlib.sha256(s['text'].encode()).hexdigest()
        quote = fc.build_report(doc)['funds'][0]['quote']
        self.assertEqual(quote['value'], '13.0000000000000000007')
        self.assertIsNone(quote['observations'][0]['quote_time'])
        self.assertNotEqual(quote['observations'][0]['quote_time'], '2032-08-12')

    def test_missing_null_and_empty_holdings_are_distinct(self):
        for kind, expected in [('absent', 'NOT_SUPPLIED'), ('null', 'UNKNOWN_FROM_SOURCE'), ('empty', 'EMPTY_SUPPLIED_COLLECTION')]:
            doc = fixture()
            if kind == 'absent': set_context(doc, lambda x: x.pop('current_holdings'))
            else: set_context(doc, lambda x: x.update(current_holdings=None if kind == 'null' else []))
            report = fc.build_report(doc)
            self.assertEqual(report['contexts']['primary']['current_holdings']['state'], expected)
            self.assertEqual(report['funds'][0]['assessment_by_scope']['primary']['current_holdings_overlap']['status'], expected)

    def test_context_conflict_duplicate_and_multiple_accounts(self):
        doc = fixture(); other = deepcopy(doc['request']); other['id'] = 'second'
        doc['context_sources'] = [other]
        self.assertEqual(len(fc.build_report(doc)['contexts']['primary']['role']['provenance']), 2)
        value = json.loads(other['text']); value['horizon'] = 'nine years'
        doc['context_sources'][0] = source(value, 'second', 'fund_report_context_v1', 'primary')
        with self.assertRaisesRegex(ValueError, 'CONFLICTING_CONTEXT'): fc.build_report(doc)
        doc['context_sources'][0]['scope'] = 'separate account'
        self.assertEqual(len(fc.build_report(doc)['contexts']), 2)

    def test_byte_bound_prose_preserved_but_semantic_mapping_partial(self):
        doc = fixture(); text = 'Compare for a flexible equity sleeve over nine years.'
        req = source(text, 'request', 'text_spans_v1', 'primary'); req['bindings'] = {}
        for key, phrase in [('role', 'flexible equity sleeve'), ('horizon', 'nine years')]:
            start = text.encode().index(phrase.encode()); raw = phrase.encode()
            req['bindings'][key] = {'start': start, 'end': start + len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}
        doc['request'] = req
        result = fc.fund_comparison_report(doc)
        self.assertEqual(result['report']['status'], 'PARTIAL_BOUND_REPORT')
        self.assertEqual(result['report']['contexts']['primary']['role']['value'], 'flexible equity sleeve')
        self.assertIn('nine years', result['artifacts']['summary'])
        self.assertIn('Losses can persist', result['artifacts']['markdown'])
        req['bindings']['horizon']['sha256'] = '0' * 64
        with self.assertRaisesRegex(ValueError, 'SPAN_BYTES'): fc.build_report(doc)

    def test_omitted_mapping_and_unsupported_request_cannot_complete(self):
        doc = fixture(); doc['request']['adapter'] = 'unsupported'
        report = fc.build_report(doc)
        self.assertEqual(report['status'], 'PARTIAL_BOUND_REPORT')
        self.assertEqual(report['contexts']['primary']['horizon']['state'], 'MAPPING_REQUIRED')
        doc = fixture(); doc['request']['adapter'] = 'json_pointers_v1'
        doc['request']['bindings'] = {'role': '/role'}
        self.assertEqual(fc.build_report(doc)['status'], 'PARTIAL_BOUND_REPORT')

    def test_unknown_override_and_missing_position_tamper_rejected(self):
        doc = fixture(); report = fc.build_report(doc)
        report['contexts']['primary']['horizon']['state'] = 'UNKNOWN_FROM_SOURCE'
        with self.assertRaisesRegex(ValueError, 'CANONICAL_REPORT'): fc.render_report(report)
        report = fc.build_report(doc); report['contexts']['primary']['current_holdings']['value'].pop()
        with self.assertRaisesRegex(ValueError, 'CANONICAL_REPORT'): fc.render_report(report)
        doc['complete'] = True
        with self.assertRaisesRegex(ValueError, 'UNSUPPORTED_REPORT_INPUT'): fc.build_report(doc)

    def test_all_three_projection_tampering_rejected(self):
        for key in ('markdown', 'structured_json', 'summary'):
            doc = fixture(); result = fc.fund_comparison_report(doc)
            result['artifacts'][key] += 'invented result'
            with self.assertRaisesRegex(ValueError, 'DELIVERY_DOES_NOT_MATCH'): fc.verify_delivery(doc, result)

    def test_unknown_classification_no_equity_inference_and_no_ranking(self):
        doc = fixture(); set_market(doc, lambda x: [v.pop('kind') for v in x['identities'].values()])
        result = fc.fund_comparison_report(doc)
        fund = result['report']['funds'][0]
        self.assertFalse(fund['composition']['known_equity_exposure'])
        self.assertIsNone(fund['assessment_by_scope']['primary']['ranking'])
        self.assertIn('does not establish equity exposure', result['artifacts']['summary'])

    def test_future_and_alternative_never_added_to_current_holdings(self):
        doc = fixture(); set_market(doc, lambda x: x['funds'].append({'symbol': 'UNHELD', 'holdings': [{'symbol': 'SHIP', 'weight': '1'}]}))
        report = fc.build_report(doc)
        self.assertEqual(len(report['funds']), 2)
        for fund in report['funds']:
            rows = fund['assessment_by_scope']['primary']['current_holdings_overlap']['rows']
            self.assertEqual([r['holding']['symbol'] for r in rows], ['TREE.A', 'UNMAPPED'])
        self.assertEqual(report['source_exposure']['normalized_allocation_input']['rows'], [])

    def test_source_hash_and_native_exposure_preservation(self):
        doc = fixture(); report = fc.build_report(doc)
        self.assertEqual(report['source_exposure'], source_exposure.source_allocation_context(report['source_exposure']['retained_input']))
        doc['request']['text'] += ' '
        with self.assertRaisesRegex(ValueError, 'SOURCE_BYTES_HASH'): fc.build_report(doc)

    def test_dispatch_freezes_and_replays_generated_artifacts(self):
        packet = {'schema_version': 1, 'contract': {'prompt': 'Synthetic fund fit comparison',
            'purpose': 'offline regression', 'base_currency': 'CAD', 'horizon_id': 'P8M',
            'as_of': '2032-08-13T09:00:00Z'}, 'jobs': [{'id': 'fund-report',
            'operation': 'planning.fund_comparison_report', 'inputs': {'document': fixture()}}]}
        bundle = quant_workbench.freeze(packet)
        self.assertEqual(bundle['result']['results'][0]['status'], 'COMPUTED')
        self.assertIn('markdown', bundle['result']['results'][0]['result']['artifacts'])
        self.assertEqual(quant_workbench.verify(json.loads(json.dumps(bundle)))['jobs_verified'], 1)

    def test_context_numeric_lexemes_conflict_before_any_rounding(self):
        doc = fixture(); first = json.loads(doc['request']['text'])
        first['current_holdings'] = [{'symbol': 'TREE.A', 'quantity': 'PRECISE'}]
        text = json.dumps(first).replace('"PRECISE"', '1.0000000000000001')
        doc['request'] = source(text, 'request', 'fund_report_context_v1', 'primary')
        report = fc.build_report(doc)
        self.assertEqual(report['contexts']['primary']['current_holdings']['value'][0]['quantity'], '1.0000000000000001')
        second = text.replace('1.0000000000000001', '1.00000000000000001')
        doc['context_sources'] = [source(second, 'second', 'fund_report_context_v1', 'primary')]
        with self.assertRaisesRegex(ValueError, 'CONFLICTING_CONTEXT'): fc.build_report(doc)

    def test_whole_holdings_mapping_retained_without_valuation(self):
        doc = fixture(); set_context(doc, lambda x: x.update(current_holdings={'TREE.A': '4.75', 'UNMAPPED': '9'}))
        report = fc.build_report(doc); rows = report['funds'][0]['assessment_by_scope']['primary']['current_holdings_overlap']['rows']
        self.assertEqual([x['holding']['symbol'] for x in rows], ['TREE.A', 'UNMAPPED'])
        self.assertEqual(rows[0]['holding']['source_position_value'], '4.75')
        self.assertEqual(report['contexts']['primary']['current_holdings']['value'], {'TREE.A': '4.75', 'UNMAPPED': '9'})
        self.assertEqual(report['source_exposure']['normalized_allocation_input']['rows'], [])

    def test_sector_aggregation_stays_total_fund_and_partial(self):
        doc = fixture()
        def add_sectors(x):
            x['identities']['TREE.A']['sector'] = 'agriculture'
            x['identities']['SHIP']['sector'] = 'transport'
        set_market(doc, add_sectors)
        composition = fc.build_report(doc)['funds'][0]['composition']
        self.assertEqual(composition['sector_total_fund_weight_fractions'], {'agriculture': '9/20', 'transport': '7/20'})
        self.assertEqual(composition['gaps'][0]['total_fund_weight_fraction'], '1/5')

    def metric_fixture(self):
        doc = fixture()
        def metrics(x):
            x['as_of'] = '2032-08-13T09:00:00Z'
            x['funds'][0].update(annual_expense_ratio='0.0017', average_daily_dollar_volume='7000000',
                tracking_difference_last_year='-0.0008', distribution_yield='0.013', benchmark='Market basket')
            x['funds'].append({'symbol': 'NEST', 'annual_expense_ratio': '0.0042',
                'average_daily_dollar_volume': '350000', 'tracking_difference_last_year': '-0.0019',
                'distribution_yield': '0.032', 'benchmark': 'Sector basket', 'bid_ask_spread_bps': '21.4',
                'holdings': [{'symbol': 'SHIP', 'weight': '1'}]})
        set_market(doc, metrics)
        return doc

    def test_substantive_metric_comparisons_without_overall_winner(self):
        result = fc.fund_comparison_report(self.metric_fixture()); pair = result['report']['criterion_comparisons'][0]
        criteria = pair['criteria']; self.assertIsNone(pair['overall_ranking'])
        self.assertEqual(criteria['annual_expense_ratio']['numeric_relation'], 'left_lower')
        self.assertEqual(criteria['annual_expense_ratio']['right_minus_left_basis_points'], '25.0000')
        self.assertEqual(criteria['average_daily_dollar_volume']['numeric_relation'], 'left_larger')
        self.assertEqual(criteria['tracking_difference_last_year']['status'], 'DIFFERENT_BENCHMARKS_NO_TRACKING_QUALITY_RANK')
        self.assertIsNone(criteria['tracking_difference_last_year']['numeric_relation'])
        self.assertEqual(criteria['distribution_yield']['status'], 'UNKNOWN_COMPARABILITY')
        self.assertEqual(criteria['quoted_full_bid_ask_spread']['numeric_relation'], 'left_narrower')
        for name in ('markdown', 'summary'):
            self.assertIn('not tracking-error volatility', result['artifacts'][name])
            self.assertIn('not total return', result['artifacts'][name])
            self.assertIn('Tax suitability depends', result['artifacts'][name])
            self.assertIn('25.0000', result['artifacts'][name])

    def test_signed_tracking_lexeme_and_expense_conversion_exact(self):
        doc = self.metric_fixture(); src = doc['exposure_sources'][0]
        src['text'] = src['text'].replace('"-0.0008"', '-0.0008000000000000000001')
        src['sha256'] = hashlib.sha256(src['text'].encode()).hexdigest()
        report = fc.build_report(doc)
        self.assertEqual(report['funds'][0]['source_record']['tracking_difference_last_year'], '-0.0008000000000000000001')
        fact = report['funds'][0]['separate_observations']['metrics']['tracking_difference_last_year']['fact']
        self.assertEqual(fact['value'], '-0.0008000000000000000001')
        self.assertEqual(fact['basis_points'], '-8.0000000000000000010000')
        self.assertEqual(fact['benchmark'], 'Market basket')

    def test_volume_currency_mismatch_and_missing_dates_no_invented_fx(self):
        doc = self.metric_fixture(); value = json.loads(doc['exposure_sources'][0]['text'])
        second = deepcopy(value); second['currency'] = 'EUR'; second['funds'] = [second['funds'].pop()]
        value['funds'] = value['funds'][:1]
        doc['exposure_sources'] = [source(value, 'facts', 'portfolio_context_v1'), source(second, 'other', 'portfolio_context_v1')]
        pair = fc.build_report(doc)['criterion_comparisons'][0]['criteria']['average_daily_dollar_volume']
        self.assertEqual(pair['status'], 'UNKNOWN_COMPARABILITY'); self.assertIsNone(pair['numeric_relation'])
        doc = self.metric_fixture(); set_market(doc, lambda x: x.pop('as_of'))
        self.assertEqual(fc.build_report(doc)['criterion_comparisons'][0]['criteria']['average_daily_dollar_volume']['status'], 'UNKNOWN_COMPARABILITY')

    def test_implementation_fingerprints_bind_new_module(self):
        from unittest.mock import patch
        import report_facts
        original = Path.read_text
        before = quant_workbench.implementation_hash()
        self.assertEqual(before, report_facts.quant_hash())
        def changed(path, *args, **kwargs):
            value = original(path, *args, **kwargs)
            return value + '\n# isolated fingerprint probe\n' if path.name == 'fund_comparison.py' else value
        with patch.object(Path, 'read_text', changed):
            after = quant_workbench.implementation_hash()
            self.assertNotEqual(after, before)
            self.assertEqual(after, report_facts.quant_hash())

    def test_known_cash_is_not_unknown_issuer_or_equity(self):
        doc = fixture(); set_context(doc, lambda x: x.update(current_holdings=[{'symbol': 'RESERVE'}]))
        set_market(doc, lambda x: x['identities'].update(RESERVE={'kind': 'cash'}))
        row = fc.build_report(doc)['funds'][0]['assessment_by_scope']['primary']['current_holdings_overlap']['rows'][0]
        self.assertEqual(row['status'], 'CASH_NOT_DIRECT_ISSUER_EXPOSURE')
        self.assertIsNone(row['fund_total_weight_fraction'])

    def test_mapping_position_role_and_nested_symbol_cannot_promote_future(self):
        for role in ('future', 'proposed'):
            doc = fixture(); set_context(doc, lambda x: x.update(current_holdings={'TREE.A': {'quantity': '3', 'position_role': role}}))
            row = fc.build_report(doc)['funds'][0]['assessment_by_scope']['primary']['current_holdings_overlap']['rows'][0]
            self.assertEqual(row['status'], 'NONCURRENT_RECORD_IN_CURRENT_COLLECTION')
            self.assertIsNone(row['fund_total_weight_fraction'])
            self.assertEqual(row['holding']['source_position_value']['position_role'], role)
        doc = fixture(); set_context(doc, lambda x: x.update(current_holdings={'TREE.A': {'quantity': '3', 'symbol': 'SHIP'}}))
        row = fc.build_report(doc)['funds'][0]['assessment_by_scope']['primary']['current_holdings_overlap']['rows'][0]
        self.assertEqual(row['status'], 'HOLDING_MAPPING_SYMBOL_CONFLICT')
        self.assertIsNone(row['fund_total_weight_fraction'])


if __name__ == '__main__':
    unittest.main()
