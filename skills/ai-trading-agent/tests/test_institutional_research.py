import contextlib
from copy import deepcopy
from decimal import Decimal
import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import institutional_research as research


def fixture():
    return {'schema_version': 1, 'as_of': '2026-10-01T14:31:00Z', 'synthetic': True,
            'records': [{'id': 'fictional-catalyst-v1', 'kind': 'catalyst', 'ticker': 'DEMO',
                         'available_at': '2026-10-01T14:30:00Z',
                         'source': {'id': 'fictional-source', 'url': 'https://example.org/fictional',
                                    'retrieved_at': '2026-10-01T14:30:00Z', 'published_at': '2026-10-01T14:00:00Z',
                                    'observed_at': '2026-10-01T14:30:00Z', 'availability_basis': 'first_observed_snapshot',
                                    'access': 'public', 'rights': 'synthetic_fixture_only'},
                         'payload': {'title': 'Fictional product event', 'event_type': 'fictional_product_event',
                                     'event_at': '2026-10-01T14:00:00Z', 'unmapped_metadata': {'retained': True}}}],
            'pilot': {'id': 'fictional-pilot', 'research_question': 'Does this fictional event brief help review?',
                      'universe': {'mode': 'explicit_symbols', 'symbols': ['DEMO'], 'synthetic': True},
                      'horizon': {'label': 'fictional-two-session-review', 'entry_policy': 'paper declaration only',
                                  'exit_policy': 'review at declared study end'},
                      'reviewer': {'id': 'fictional-reviewer', 'role': 'synthetic_operator'},
                      'study': {'registered_at': '2026-10-01T13:00:00Z', 'start_at': '2026-10-01T14:00:00Z',
                                'end_at': '2026-10-02T20:00:00Z', 'usefulness_criterion': 'Identifies one checkable decision-relevant gap',
                                'workflow_baseline_id': 'fictional-without-tool', 'return_baseline_id': 'fictional-cash'}},
            'event': {'id': 'fictional-event', 'ticker': 'DEMO', 'decision_at': '2026-10-01T14:31:00Z',
                      'review_at': '2026-10-01T15:00:00Z'},
            'portfolio': {'as_of': '2026-10-01T14:30:00Z', 'currency': 'USD', 'total_value': '10000',
                          'positions': [{'ticker': 'DEMO', 'market_value': '1000'}], 'cash': '9000', 'completeness': 'partial'},
            'proposed_trade': {'ticker': 'DEMO', 'side': 'buy', 'notional': '1000', 'currency': 'USD', 'role': 'hypothetical_scenario'},
            'cost_contract': {'currency': 'USD', 'role': 'user_assumption', 'side': 'buy', 'price': '10', 'quantity': '100',
                              'entry_orders': 1, 'exit_orders': 1, 'exit_price': '11',
                              'costs': [{'id': 'fictional-fee', 'unit': 'bps_notional', 'phase': 'each_side', 'amount': '10'}]},
            'liquidity': {'ticker': 'DEMO', 'available_at': '2026-10-01T14:30:00Z', 'currency': 'USD',
                          'average_daily_dollar_volume': '1000000', 'order_notional': '1000', 'spread_bps': '5',
                          'observed_window': 'fictional prior sessions', 'role': 'user_assumption'}}


def evaluated():
    document = fixture()
    document['as_of'] = '2026-10-06T20:00:00Z'
    text = 'Fictional first response: verify the catalyst and avoid inferring intent from prints.'
    document['evaluation'] = {
        'registered_at': '2026-10-01T13:00:00Z', 'study_start': '2026-10-01T14:00:00Z',
        'study_end': '2026-10-02T20:00:00Z', 'usefulness_criterion': 'Identifies one checkable decision-relevant gap',
        'workflow_baseline_id': 'fictional-without-tool', 'return_baseline_id': 'fictional-cash',
        'expected_case_ids': ['fictional-case'], 'cases': [{
            'id': 'fictional-case', 'decision_at': '2026-10-01T14:31:00Z',
            'first_response': {'text': text, 'sha256': hashlib.sha256(text.encode()).hexdigest(), 'captured_at': '2026-10-01T14:31:00Z'},
            'input_record_ids': ['fictional-catalyst-v1'],
            'usefulness': {'available_at': '2026-10-03T12:00:00Z', 'useful': True,
                          'criterion': 'Identifies one checkable decision-relevant gap', 'reviewer_id': 'fictional-reviewer',
                          'assisted_minutes': '12', 'baseline_minutes': '20', 'baseline_id': 'fictional-without-tool'},
            'paper_return': {'available_at': '2026-10-03T12:00:00Z', 'period_start': '2026-10-01T14:31:00Z',
                             'period_end': '2026-10-02T20:00:00Z', 'currency': 'USD',
                             'return_basis': 'simple_total_return_decimal', 'net_costs_included': True, 'return_decimal': '0.02',
                             'benchmark': {'id': 'fictional-cash', 'available_at': '2026-10-03T12:00:00Z',
                                           'period_start': '2026-10-01T14:31:00Z', 'period_end': '2026-10-02T20:00:00Z',
                                           'currency': 'USD', 'return_basis': 'simple_total_return_decimal',
                                           'net_costs_included': True, 'return_decimal': '0.001'}}}]}
    return document


class InstitutionalPureTests(unittest.TestCase):
    def test_default_discovery_scope_does_not_claim_full_coverage(self):
        document = fixture(); document.pop('pilot')
        result = research.plan(document)
        self.assertEqual(result['requested_discovery_universe'], {'mode': 'us_listed_full'})
        self.assertFalse(result['exhaustive_us_universe_verified'])
        self.assertEqual(result['actual_coverage'], 'SUPPLIED_RECORDS_ONLY')
        self.assertEqual(result['status'], 'CONFIGURATION_NEEDED')
        self.assertEqual({r['id'] for r in result['readiness']}, set(research.HF))
        self.assertTrue(all(r['real_world_acceptance'] == 'NOT_ESTABLISHED' for r in result['readiness']))

    def test_plan_preserves_supplied_choices_and_unknown_record_payload(self):
        document = fixture(); before = deepcopy(document)
        result = research.plan(document)
        self.assertEqual(document, before)
        self.assertEqual(result['pilot'], document['pilot'])
        self.assertTrue(result['evidence']['records'][0]['payload']['unmapped_metadata']['retained'])
        self.assertEqual(result['status'], 'DECLARED_PROTOCOL_READY_FOR_REVIEW')
        self.assertFalse(result['execution_authorized'])

    def test_missing_nested_pilot_choice_is_not_ready(self):
        document = fixture(); document['pilot']['study']['start_at'] = None
        self.assertIn('study.start_at', research.plan(document)['missing_configuration'])

    def test_brief_cutoff_and_explicit_scope_exclude_evidence(self):
        document = fixture(); document['records'][0]['available_at'] = '2026-10-01T14:32:00Z'
        self.assertEqual(research.brief(document)['evidence_record_ids'], [])
        document = fixture(); document['pilot']['universe']['symbols'] = ['OTHER']
        self.assertFalse(research.brief(document)['event_in_declared_scope'])
        document = fixture(); document['event']['decision_at'] = '2026-10-01T14:30:00Z'
        with self.assertRaisesRegex(ValueError, 'CUTOFF'):
            research.brief(document)

    def test_portfolio_uses_full_nav_and_costs_reuse_existing_contract(self):
        document = fixture(); result = research.brief(document)
        portfolio = result['portfolio_impact']; costs = result['cost_liquidity_review']
        self.assertEqual(portfolio['before_nav_fraction'], '0.1')
        self.assertEqual(portfolio['after_nav_fraction'], '0.2')
        self.assertEqual(portfolio['coverage'], 'partial')
        self.assertFalse(portfolio['actual_available_cash_verified'])
        self.assertEqual(Decimal(costs['costs']['entry_cost']), Decimal('1'))
        self.assertEqual(Decimal(costs['costs']['exit_cost']), Decimal('1.1'))
        self.assertEqual(costs['order_to_declared_adv'], '0.001')
        self.assertFalse(costs['executable_capacity_established'])

    def test_future_portfolio_and_liquidity_do_not_enter_computation(self):
        document = fixture()
        document['portfolio']['as_of'] = document['liquidity']['available_at'] = '2026-10-01T15:00:00Z'
        result = research.brief(document)
        self.assertEqual(result['portfolio_impact']['status'], 'PORTFOLIO_CLOCK_UNUSABLE')
        self.assertNotIn('after_nav_fraction', result['portfolio_impact'])
        self.assertEqual(result['cost_liquidity_review']['liquidity_status'], 'CLOCK_UNUSABLE')
        self.assertNotIn('order_to_declared_adv', result['cost_liquidity_review'])

    def test_optional_flow_composes_real_modules_without_squeeze_certification(self):
        document = fixture(); document['include_flow_analysis'] = True
        result = research.brief(document)
        self.assertEqual(result['flow']['kind'], 'MARKET_FLOW')
        self.assertEqual(result['positioning']['kind'], 'MARKET_POSITIONING')
        self.assertEqual(result['squeeze']['kind'], 'SQUEEZE_EVIDENCE')
        self.assertFalse(result['squeeze']['execution_authorized'])

    def test_linked_cross_ticker_benchmark_is_retained_without_unrelated_positions(self):
        import market_flow
        package = Path(__file__).resolve().parents[1]
        document = json.loads((package / 'examples/market-flow-synthetic.json').read_text())
        current = next(r for r in document['records'] if r['kind'] == 'bar' and r['payload'].get('role') == 'current')
        benchmark_id = current['payload']['benchmark_record_id']
        document.update(pilot=fixture()['pilot'], event={'ticker': current['ticker'], 'decision_at': document['as_of']}, include_flow_analysis=True)
        document['pilot']['universe']['symbols'] = [current['ticker']]
        unrelated = deepcopy(next(r for r in document['records'] if r['kind'] == 'short_interest'))
        unrelated.update(id='unrelated-si', ticker='UNRELATED')
        document['records'].append(unrelated)
        direct = market_flow.squeeze(document)
        composed = research.brief(document)
        self.assertIn(benchmark_id, composed['flow_dependency_record_ids'])
        self.assertNotIn('unrelated-si', [r['id'] for r in composed['flow']['evidence']['records']])
        self.assertEqual(composed['squeeze']['assessments'][0]['state'], direct['assessments'][0]['state'])
        self.assertEqual(composed['squeeze']['assessments'][0]['state'], 'DEVELOPING_PRESSURE_HEURISTIC')
        linked = next(b for b in composed['flow']['cumulative_bars'] if b['record_id'] == current['id'])
        self.assertEqual(linked['benchmark_relative_return_percent'], 5.0)

    def test_no_fx_or_nonfinite_assumption_is_invented(self):
        document = fixture(); document['portfolio']['currency'] = 'EUR'
        with self.assertRaisesRegex(ValueError, 'USD_ONLY'):
            research.brief(document)
        document = fixture(); document['proposed_trade']['notional'] = 'NaN'
        with self.assertRaisesRegex(ValueError, 'FINITE'):
            research.brief(document)
        document = fixture(); document['portfolio']['positions'][0]['currency'] = 'EUR'
        with self.assertRaisesRegex(ValueError, 'POSITION_CURRENCY_MISMATCH'):
            research.brief(document)

    def test_benchmark_revision_ancestry_and_conflicts_remain_visible(self):
        import market_flow
        package = Path(__file__).resolve().parents[1]
        document = json.loads((package / 'examples/market-flow-synthetic.json').read_text())
        current = next(r for r in document['records'] if r['kind'] == 'bar' and r['payload'].get('role') == 'current')
        benchmark = next(r for r in document['records'] if r['id'] == current['payload']['benchmark_record_id'])
        benchmark['available_at'] = '2026-11-11T18:00:00Z'
        benchmark['source'].update(retrieved_at=benchmark['available_at'], observed_at=benchmark['available_at'])
        revised = deepcopy(benchmark)
        revised.update(id='benchmark-revision', available_at='2026-11-11T20:00:00Z', action='replace', supersedes=benchmark['id'])
        revised['source'].update(retrieved_at=revised['available_at'], observed_at=revised['available_at'])
        revised['payload']['end_price'] = '102'
        current['payload']['benchmark_record_id'] = revised['id']
        document['records'].append(revised)
        document.update(pilot=fixture()['pilot'], event={'ticker': current['ticker'], 'decision_at': document['as_of']}, include_flow_analysis=True)
        document['pilot']['universe']['symbols'] = [current['ticker']]
        direct = market_flow.analyze(document)
        composed = research.brief(document)
        linked = lambda output: next(b for b in output['cumulative_bars'] if b['record_id'] == current['id'])
        self.assertIn(benchmark['id'], composed['flow_dependency_record_ids'])
        self.assertEqual(linked(composed['flow'])['benchmark_relative_return_percent'], linked(direct)['benchmark_relative_return_percent'])
        self.assertEqual(linked(composed['flow'])['benchmark_relative_return_percent'], 4.0)
        conflict = deepcopy(revised); conflict.update(id='benchmark-conflict', action='new'); conflict.pop('supersedes')
        conflict['payload']['end_price'] = '103'; document['records'].append(conflict)
        self.assertIsNone(linked(market_flow.analyze(document))['benchmark_relative_return_percent'])
        conflicting = research.brief(document)
        self.assertIn(conflict['id'], conflicting['flow_dependency_record_ids'])
        self.assertIsNone(linked(conflicting['flow'])['benchmark_relative_return_percent'])
    def test_missing_partial_position_and_short_crossing_stay_declared(self):
        document = fixture(); document['portfolio']['positions'][0]['ticker'] = 'OTHER'
        self.assertEqual(research.brief(document)['portfolio_impact']['status'], 'BEFORE_POSITION_UNKNOWN_PARTIAL_PORTFOLIO')
        document = fixture(); document['proposed_trade'].update(side='short', notional='2000')
        result = research.brief(document)['portfolio_impact']
        self.assertTrue(result['crosses_zero_inventory'])
        self.assertEqual(result['after_signed_market_value'], '-1000')
        self.assertIn('scenario only', result['short_cover_interpretation'])

    def test_evaluation_separates_usefulness_from_net_paper_baseline(self):
        document = evaluated(); before = deepcopy(document)
        result = research.evaluate(document)
        self.assertEqual(document, before)
        self.assertEqual(result['usefulness']['mean_declared_minutes_saved'], '8')
        self.assertEqual(result['returns']['mean_descriptive_excess_return_decimal'], '0.019')
        self.assertEqual(result['roster']['status'], 'MATCHED')
        self.assertFalse(result['profitability_established'])
        self.assertFalse(result['actual_elapsed_operation_verified'])
        self.assertFalse(result['returns']['annualization_or_significance_computed'])

    def test_future_outcomes_retained_but_not_counted(self):
        document = evaluated(); document['as_of'] = '2026-10-01T15:00:00Z'
        result = research.evaluate(document)
        self.assertEqual(result['usefulness']['included_cases'], 0)
        self.assertEqual(result['returns']['included_cases'], 0)
        self.assertEqual(result['status'], 'PROSPECTIVE_PILOT_IN_PROGRESS')
        self.assertIn('paper_return', result['cases'][0]['declared_case'])

    def test_first_response_hash_clock_and_decision_input_lookahead_excluded(self):
        for mutation in ('hash', 'capture', 'input'):
            document = evaluated(); case = document['evaluation']['cases'][0]
            if mutation == 'hash': case['first_response']['text'] += ' later feedback'
            if mutation == 'capture': case['first_response']['captured_at'] = '2026-10-01T15:00:00Z'
            if mutation == 'input': document['records'][0]['available_at'] = '2026-10-01T14:32:00Z'
            result = research.evaluate(document)
            self.assertTrue(result['cases'][0]['prospective_exclusion_reasons'])
            self.assertEqual(result['usefulness']['included_cases'], 0)
            self.assertEqual(result['returns']['included_cases'], 0)

    def test_posthoc_baseline_gross_returns_and_mismatched_period_not_accepted(self):
        for mutation in ('workflow', 'gross', 'period'):
            document = evaluated(); case = document['evaluation']['cases'][0]
            if mutation == 'workflow': case['usefulness']['baseline_id'] = 'new-posthoc-baseline'
            if mutation == 'gross': case['paper_return']['net_costs_included'] = False
            if mutation == 'period': case['paper_return']['benchmark']['period_end'] = '2026-10-01T20:00:00Z'
            result = research.evaluate(document)
            if mutation == 'workflow': self.assertEqual(result['usefulness']['included_cases'], 0)
            else: self.assertEqual(result['returns']['included_cases'], 0)

    def test_roster_missing_failures_and_challenge_independence_stay_visible(self):
        document = evaluated(); document['evaluation']['expected_case_ids'].append('abstained-case')
        document['challenge'] = {'reviewer_id': 'claimed-independent', 'reviewed_at': '2026-10-04T12:00:00Z',
                                 'independence_basis': 'operator declaration', 'findings': [{'issue': 'Selection bias', 'disposition': 'unresolved'}]}
        result = research.evaluate(document)
        self.assertEqual(result['roster']['missing'], ['abstained-case'])
        self.assertFalse(result['challenge']['independence_verified'])
        self.assertEqual(result['challenge']['findings'][0]['disposition'], 'unresolved')

    def test_matching_protocol_and_standalone_evaluation_remain_descriptive(self):
        document = evaluated()
        result = research.evaluate(document)
        protocol = result['protocol_reconciliation']
        self.assertEqual(protocol['status'], 'MATCHED_DECLARED_PROTOCOL')
        self.assertEqual(protocol['declared_pilot'], document['pilot'])
        self.assertEqual(protocol['pilot_sha256'], research._digest(document['pilot']))
        self.assertFalse(protocol['registration_authenticated'])
        self.assertEqual(result['usefulness']['included_cases'], 1)
        self.assertEqual(result['returns']['included_cases'], 1)
        document.pop('pilot')
        standalone = research.evaluate(document)
        self.assertEqual(standalone['protocol_reconciliation']['status'], 'DECLARATION_ONLY_NO_PILOT')
        self.assertEqual(standalone['returns']['mean_descriptive_excess_return_decimal'], '0.019')
        self.assertFalse(standalone['actual_elapsed_operation_verified'])

    def test_shipped_demo_protocol_matches_its_evaluation_declaration(self):
        package = Path(__file__).resolve().parents[1]
        brief_input = json.loads((package / 'examples/institutional-event-input.json').read_text(encoding='utf-8'))
        evaluation_input = json.loads((package / 'examples/institutional-evaluation-input.json').read_text(encoding='utf-8'))
        protocol = research.plan(brief_input)
        result = research.evaluate(evaluation_input)
        self.assertEqual(brief_input['pilot'], evaluation_input['pilot'])
        self.assertEqual(protocol['pilot_sha256'], result['protocol_reconciliation']['pilot_sha256'])
        self.assertEqual(result['protocol_reconciliation']['status'], 'MATCHED_DECLARED_PROTOCOL')
        self.assertEqual(result['usefulness']['included_cases'], 1)
        self.assertEqual(result['returns']['included_cases'], 1)

    def test_supplied_post_outcome_pilot_registration_is_not_ignored(self):
        document = evaluated()
        document['pilot']['study'].update(registered_at='2026-10-04T13:00:00Z',
                                           start_at='2026-10-04T14:00:00Z', end_at='2026-10-05T20:00:00Z')
        before = deepcopy(document)
        result = research.evaluate(document)
        self.assertEqual(document, before)
        self.assertEqual(result['evaluation_contract'], document['evaluation'])
        self.assertEqual(result['protocol_reconciliation']['declared_pilot'], document['pilot'])
        self.assertEqual(result['protocol_reconciliation']['status'], 'PROTOCOL_CONFLICT')
        self.assertEqual(result['usefulness']['included_cases'], 0)
        self.assertEqual(result['returns']['included_cases'], 0)
        self.assertIn('PILOT_EVALUATION_PROTOCOL_CONFLICT:study.registered_at',
                      result['cases'][0]['prospective_exclusion_reasons'])

    def test_matching_rewritten_evaluation_and_outcome_cannot_override_pilot(self):
        for field, replacement in (('usefulness_criterion', 'post-outcome criterion'),
                                   ('workflow_baseline_id', 'post-outcome baseline')):
            with self.subTest(field=field):
                document = evaluated()
                document['evaluation'][field] = replacement
                outcome = document['evaluation']['cases'][0]['usefulness']
                outcome['criterion' if field == 'usefulness_criterion' else 'baseline_id'] = replacement
                result = research.evaluate(document)
                self.assertEqual(result['usefulness']['included_cases'], 0)
                self.assertEqual(result['returns']['included_cases'], 0)
                self.assertEqual(result['protocol_reconciliation']['conflicts'][0]['field'], 'study.' + field)

    def test_return_baseline_and_reviewer_conflicts_affect_their_own_metrics(self):
        document = evaluated()
        document['evaluation']['return_baseline_id'] = 'easier-posthoc-baseline'
        document['evaluation']['cases'][0]['paper_return']['benchmark']['id'] = 'easier-posthoc-baseline'
        result = research.evaluate(document)
        self.assertEqual(result['usefulness']['included_cases'], 1)
        self.assertEqual(result['returns']['included_cases'], 0)
        self.assertIn('PILOT_EVALUATION_PROTOCOL_CONFLICT:study.return_baseline_id',
                      result['cases'][0]['return_exclusion_reasons'])
        document = evaluated()
        document['evaluation']['cases'][0]['usefulness']['reviewer_id'] = 'unadopted-reviewer'
        result = research.evaluate(document)
        self.assertEqual(result['usefulness']['included_cases'], 0)
        self.assertEqual(result['returns']['included_cases'], 1)
        self.assertEqual(result['cases'][0]['usefulness_exclusion_reasons'], ['PILOT_REVIEWER_MISMATCH'])
        document = evaluated()
        document['pilot']['study'].pop('return_baseline_id')
        result = research.evaluate(document)
        self.assertEqual(result['usefulness']['included_cases'], 1)
        self.assertEqual(result['returns']['included_cases'], 0)
        self.assertEqual(result['protocol_reconciliation']['status'], 'PROTOCOL_CONFIGURATION_INCOMPLETE')

    def test_declared_case_universe_checked_without_rejecting_dependency_tickers(self):
        document = evaluated()
        document['pilot']['universe']['symbols'] = ['OTHER']
        result = research.evaluate(document)
        self.assertEqual(result['cases'][0]['scope_review']['ticker'], 'DEMO')
        self.assertIn('TARGET_OUTSIDE_DECLARED_SCOPE', result['cases'][0]['prospective_exclusion_reasons'])
        self.assertEqual(result['returns']['included_cases'], 0)
        document = evaluated()
        # Explicit target identity is separate from cross-ticker evidence.
        document['evaluation']['cases'][0]['ticker'] = 'DEMO'
        related = deepcopy(document['records'][0]); related.update(id='related-issuer', ticker='RELATED')
        document['records'].append(related)
        document['evaluation']['cases'][0]['input_record_ids'].append('related-issuer')
        result = research.evaluate(document)
        self.assertEqual(result['usefulness']['included_cases'], 1)
        self.assertEqual(result['returns']['included_cases'], 1)

    def test_optional_protocol_identity_and_roster_bindings_check_retained_values(self):
        document = evaluated()
        document['evaluation']['pilot_sha256'] = '0' * 64
        self.assertEqual(research.evaluate(document)['returns']['included_cases'], 0)
        document = evaluated()
        document['pilot']['study']['expected_case_ids'] = ['fictional-case', 'retained-failure']
        result = research.evaluate(document)
        self.assertEqual(result['returns']['included_cases'], 0)
        self.assertIn('PILOT_EVALUATION_PROTOCOL_CONFLICT:study.expected_case_ids',
                      result['cases'][0]['prospective_exclusion_reasons'])
        document = evaluated()
        document['pilot']['study']['registered_at'] = '2026-10-01T06:00:00-07:00'
        self.assertEqual(research.evaluate(document)['returns']['included_cases'], 1)

    def test_scope_inference_ignores_unusable_event_and_unrelated_malformed_payload(self):
        document = evaluated()
        document['event'] = None
        malformed = deepcopy(document['records'][0]); malformed.update(id='malformed-unrelated', ticker='OTHER', payload=None)
        document['records'].append(malformed)
        before = deepcopy(document)
        result = research.evaluate(document)
        self.assertEqual(document, before)
        self.assertEqual(result['cases'][0]['scope_review']['ticker'], 'DEMO')
        self.assertEqual(result['cases'][0]['scope_review']['basis'], 'UNIQUE_NONBENCHMARK_INPUT_TICKER')
        self.assertEqual(result['returns']['included_cases'], 1)

    def test_first_response_cannot_use_later_input_even_if_decision_can(self):
        document = evaluated()
        document['evaluation']['cases'][0]['first_response']['captured_at'] = '2026-10-01T13:01:00Z'
        result = research.evaluate(document)
        row = result['cases'][0]
        self.assertIn('FIRST_RESPONSE_INPUTS_MISSING_OR_UNAVAILABLE_AT_CAPTURE', row['prospective_exclusion_reasons'])
        self.assertEqual(row['response_input_review']['unavailable_response_input_record_ids'], ['fictional-catalyst-v1'])
        self.assertEqual(result['usefulness']['included_cases'], 0)
        self.assertEqual(result['returns']['included_cases'], 0)

    def test_explicit_response_inputs_distinguish_later_decision_inputs(self):
        document = evaluated()
        case = document['evaluation']['cases'][0]
        case['decision_at'] = '2026-10-01T14:35:00Z'
        case['paper_return']['period_start'] = case['paper_return']['benchmark']['period_start'] = case['decision_at']
        late = deepcopy(document['records'][0]); late.update(id='later-decision-input', available_at='2026-10-01T14:33:00Z')
        late['source'].update(published_at='2026-10-01T14:32:00Z', retrieved_at='2026-10-01T14:33:00Z',
                              observed_at='2026-10-01T14:33:00Z')
        document['records'].append(late)
        case['input_record_ids'].append(late['id'])
        case['first_response']['input_record_ids'] = ['fictional-catalyst-v1']
        before = deepcopy(document)
        result = research.evaluate(document)
        self.assertEqual(document, before)
        row = result['cases'][0]
        self.assertEqual(row['response_input_review']['binding_mode'], 'EXPLICIT_RESPONSE_INPUTS')
        self.assertEqual(row['response_input_review']['later_decision_input_record_ids'], [late['id']])
        self.assertEqual(result['usefulness']['included_cases'], 1)
        self.assertEqual(result['returns']['included_cases'], 1)
        # Omitting the explicit response set means common inputs, all checked at capture.
        case['first_response'].pop('input_record_ids')
        legacy = research.evaluate(document)
        self.assertEqual(legacy['returns']['included_cases'], 0)
        self.assertEqual(legacy['cases'][0]['response_input_review']['binding_mode'], 'LEGACY_COMMON_INPUTS_CHECKED_AT_CAPTURE')

    def test_response_and_decision_can_bind_different_revision_vintages(self):
        document = evaluated()
        case = document['evaluation']['cases'][0]
        revised = deepcopy(document['records'][0])
        revised.update(id='catalyst-revision', supersedes='fictional-catalyst-v1', available_at='2026-10-01T14:33:00Z')
        revised['source'].update(published_at='2026-10-01T14:32:00Z', retrieved_at='2026-10-01T14:33:00Z',
                                 observed_at='2026-10-01T14:33:00Z')
        document['records'].append(revised)
        case['first_response']['input_record_ids'] = ['fictional-catalyst-v1']
        case['input_record_ids'] = ['catalyst-revision']
        case['decision_at'] = '2026-10-01T14:35:00Z'
        case['paper_return']['period_start'] = case['paper_return']['benchmark']['period_start'] = case['decision_at']
        result = research.evaluate(document)
        self.assertEqual(result['returns']['included_cases'], 1)
        hashes = result['cases'][0]['response_input_review']['response_record_sha256']
        self.assertEqual(hashes, {'fictional-catalyst-v1': research._digest(document['records'][0])})

    def test_no_pure_operation_writes_files(self):
        with patch.object(Path, 'open', side_effect=AssertionError('pure operation attempted file IO')):
            research.plan(fixture()); research.brief(fixture()); research.evaluate(evaluated())


class InstitutionalJournalTests(unittest.TestCase):
    def test_immutable_first_response_idempotence_and_conflict(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); raw = b'Original first response\r\n'
            first = research._record(root, 'case-first', 'first_response', raw, {'parent_id': None})
            original = (root / 'entries/case-first.json').read_bytes()
            again = research._record(root, 'case-first', 'first_response', raw, {'parent_id': None})
            self.assertEqual(first, again)
            self.assertEqual(original, (root / 'entries/case-first.json').read_bytes())
            self.assertEqual((root / ('objects/' + hashlib.sha256(raw).hexdigest() + '.bin')).read_bytes(), raw)
            with self.assertRaisesRegex(ValueError, 'ENTRY_ID_CONFLICT'):
                research._record(root, 'case-first', 'first_response', b'rewritten', {'parent_id': None})
            self.assertEqual(original, (root / 'entries/case-first.json').read_bytes())

    def test_pending_transaction_recovers_after_interruption(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            with patch.object(research, '_complete', side_effect=OSError('simulated interruption')):
                with self.assertRaises(OSError): research._record(root, 'pending', 'brief', b'{}', {})
            self.assertTrue((root / 'transactions/pending.json').is_file())
            self.assertFalse((root / 'entries/pending.json').exists())
            self.assertFalse((root / '.institutional.lock').exists())
            result = research._recover(root, 'pending')
            self.assertEqual(result['status'], 'COMMITTED')
            self.assertEqual(research._recover(root, 'pending'), result)

    def test_recovery_detects_corruption_and_preserves_original_entry(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); result = research._record(root, 'first', 'brief', b'original', {})
            original = (root / 'entries/first.json').read_bytes()
            (root / ('objects/' + result['object_sha256'] + '.bin')).write_bytes(b'tampered')
            with self.assertRaisesRegex(ValueError, 'CAPTURE_HASH_MISMATCH'): research._recover(root, 'first')
            self.assertEqual(original, (root / 'entries/first.json').read_bytes())

    def test_busy_lock_never_auto_breaks_and_explicit_release_is_hash_bound(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); lock = root / '.institutional.lock'; raw = b'operator-must-check-owner'
            lock.write_bytes(raw); digest = hashlib.sha256(raw).hexdigest()
            with self.assertRaisesRegex(ValueError, 'LOCK_HELD'): research._record(root, 'blocked', 'failure', b'{}', {})
            with self.assertRaisesRegex(ValueError, 'CONFIRM'): research._release_lock(root, digest)
            with self.assertRaisesRegex(ValueError, 'LOCK_HASH'): research._release_lock(root, '0' * 64, True)
            self.assertEqual(lock.read_bytes(), raw)
            research._release_lock(root, digest, True)
            self.assertFalse(lock.exists())
            self.assertEqual((root / ('lock-releases/' + digest + '.json')).read_bytes(), raw)

    def test_path_traversal_and_wrong_expected_capture_hash_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); source = root / 'input.txt'; source.write_text('exact input')
            with self.assertRaisesRegex(ValueError, 'SAFE_ID'): research._record(root, '../escape', 'brief', b'{}', {})
            with self.assertRaisesRegex(ValueError, 'EXPECTED_CAPTURE_HASH'):
                research.main(['capture', '--root', str(root), '--entry-id', 'capture', '--input', str(source),
                               '--available-at', '2026-10-01T14:30:00Z', '--source-id', 'declared', '--expected-sha256', '0' * 64])
            self.assertFalse((root / 'transactions').exists())

    def test_competing_release_is_serialized_and_replacement_lock_survives(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); path = root / '.institutional.lock'; raw = b'old-stopped-owner'; path.write_bytes(raw)
            digest = hashlib.sha256(raw).hexdigest(); publish = research._publish
            def interleaved_publish(target, data):
                with self.assertRaisesRegex(ValueError, 'LOCK_HELD'):
                    research._release_lock(root, digest, True)
                with self.assertRaisesRegex(ValueError, 'RELEASE_IN_PROGRESS'):
                    research._record(root, 'blocked-writer', 'brief', b'{}', {})
                result = publish(target, data)
                # An unexpected external replacement is detected after archival;
                # it must not be unlinked even though initial hash checks passed.
                path.write_bytes(b'new-owner-token')
                return result
            with patch.object(research, '_publish', side_effect=interleaved_publish):
                with self.assertRaisesRegex(ValueError, 'LOCK_HASH_CHANGED_DURING_RELEASE'):
                    research._release_lock(root, digest, True)
            self.assertEqual(path.read_bytes(), b'new-owner-token')
            self.assertEqual((root / ('lock-releases/' + digest + '.json')).read_bytes(), raw)
            self.assertFalse((root / '.institutional-release.lock').exists())

    def test_cli_capture_and_journal_preserve_exact_bytes(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); source = root / 'response.txt'; raw = b'first\r\nresponse'; source.write_bytes(raw)
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                research.main(['capture', '--root', str(root), '--entry-id', 'source-v1', '--input', str(source),
                               '--available-at', '2026-10-01T14:30:00Z', '--source-id', 'synthetic'])
                research.main(['journal', '--root', str(root), '--entry-id', 'response-v1', '--kind', 'first_response', '--input', str(source)])
            entry = json.loads((root / 'entries/response-v1.json').read_text())
            self.assertEqual((root / ('objects/' + entry['object_sha256'] + '.bin')).read_bytes(), raw)
            self.assertEqual(json.loads((root / 'entries/source-v1.json').read_text())['metadata']['rights'], 'unknown')


if __name__ == '__main__':
    unittest.main()
