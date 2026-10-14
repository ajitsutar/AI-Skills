"""Independent arithmetic and invariance checks for local advisory helpers."""
from copy import deepcopy
from decimal import Decimal, ROUND_UP, localcontext
from fractions import Fraction
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import planning_alignment
import portfolio_decision as decision


def cost_document():
    return {'currency': 'USD', 'role': 'hypothetical_scenario', 'mode': 'alternatives',
            'budget': '97.40', 'quantity_scenarios': [
                {'id': 'integer-lots', 'quantity_basis': 'whole_shares', 'quantity_step': '1'},
                {'id': 'quarter-lots', 'quantity_basis': 'fractional_shares', 'quantity_step': '.25'}],
            'rows': [{'id': 'candidate-1', 'symbol': 'SYNTHETIC', 'price': '7.80', 'price_basis': 'last',
                      'entry_orders': 2, 'costs': [
                          {'id': 'ticket-fee', 'amount': '1.35', 'unit': 'per_order', 'phase': 'entry'},
                          {'id': 'share-fee', 'amount': '.19', 'unit': 'per_share', 'phase': 'each_side'},
                          {'id': 'value-fee', 'amount': '35', 'unit': 'bps_notional', 'phase': 'entry'},
                          {'id': 'exit-only-fee', 'amount': '400', 'unit': 'per_order', 'phase': 'exit'},
                          {'id': 'package', 'amount': '1.13', 'unit': 'per_round_trip',
                           'phase': 'round_trip', 'charged_at': 'entry'}]}]}


def context_document():
    return {'currency': 'USD', 'role': 'supplied_observation',
            'denominator': {'amount': '1000', 'basis': 'declared account equity',
                            'period': 'snapshot', 'provenance': {'source': 'account-value'}},
            'rows': [
                {'id': 'line-a', 'notional': '210', 'notional_basis': 'gross_notional',
                 'instrument_type': 'equity', 'issuer_id': 'issuer-a', 'sector': 'sector-p', 'industry': 'industry-r',
                 'period': 'snapshot', 'provenance': {'source': 'position-a'},
                 'dollar_volume': {'amount': '105000', 'unit': 'currency_per_day', 'currency': 'USD',
                                   'period': 'supplied 12-day average', 'provenance': {'source': 'volume-a'}}},
                {'id': 'line-b', 'notional': '40', 'notional_basis': 'gross_notional',
                 'instrument_type': 'equity', 'issuer_id': 'issuer-a', 'sector': 'sector-p', 'industry': 'industry-r'},
                {'id': 'fund-line', 'notional': '500', 'notional_basis': 'gross_notional',
                 'instrument_type': 'fund', 'issuer_id': 'fund-sponsor-is-not-underlying-exposure',
                 'lookthrough': {'period': 'holdings-date', 'provenance': {'source': 'fund-holdings'},
                                 'constituents': [
                     {'id': 'holding-a', 'weight': '.3', 'instrument_type': 'equity',
                      'issuer_id': 'issuer-a', 'sector': 'sector-p', 'industry': 'industry-r'},
                     {'id': 'nested-fund', 'weight': '.4', 'instrument_type': 'fund',
                      'lookthrough': {'period': 'different-date', 'provenance': 'nested-source', 'constituents': [
                          {'id': 'holding-c', 'weight': '.75', 'instrument_type': 'equity',
                           'issuer_id': 'issuer-c', 'sector': 'sector-q'},
                          {'id': 'nested-cash', 'weight': '.25', 'instrument_type': 'cash'}]}},
                     {'id': 'fund-cash', 'weight': '.1', 'instrument_type': 'cash'}]}},
                {'id': 'cash-line', 'notional': '100', 'notional_basis': 'gross_notional', 'instrument_type': 'cash'}]}


class BudgetSizingTests(unittest.TestCase):
    def test_all_cost_units_against_independent_fraction_enumeration(self):
        document = cost_document()
        result = decision.budget_sizing(document)
        fixed = Fraction('1.35') * 2 + Fraction('1.13')
        variable = Fraction('.19') + Fraction('7.80') * Fraction(35, 10000)
        for scenario in result['scenarios']:
            row = scenario['rows'][0]
            step = Fraction(scenario['quantity_step'])
            budget = Fraction(document['budget'])
            price = Fraction(document['rows'][0]['price'])
            def debit(q):
                return q * (price + variable) + (fixed if q else 0)
            candidates = [i * step for i in range(100) if debit(i * step) <= budget]
            expected = max(candidates)
            self.assertEqual(Fraction(row['quantity']), expected)
            self.assertEqual(Fraction(row['gross_notional']), expected * price)
            self.assertEqual(Fraction(row['modeled_entry_cost']), fixed + variable * expected)
            self.assertEqual(Fraction(row['modeled_cash_debit']), debit(expected))
            self.assertEqual(Fraction(row['budget_remainder']), budget - debit(expected))
            self.assertGreater(debit(expected + step), budget)

    def test_delegates_both_sizing_and_quote_to_existing_helper(self):
        document = cost_document()
        with patch.object(planning_alignment, 'trade_costs', wraps=planning_alignment.trade_costs) as helper:
            decision.budget_sizing(document)
        self.assertEqual(helper.call_count, 2 * len(document['quantity_scenarios']))
        for first, second in zip(helper.call_args_list[::2], helper.call_args_list[1::2]):
            # A copied snapshot is unnecessary: all calls retain the same explicit
            # budget, increment and complete cost list, including exit-only rows.
            self.assertEqual(first.args[0]['costs'], document['rows'][0]['costs'])
            self.assertEqual(first.args[0]['budget'], second.args[0]['budget'])

    def test_zero_size_has_zero_fees_and_entire_residual(self):
        document = cost_document()
        document['budget'] = '2'
        result = decision.budget_sizing(document)
        for scenario in result['scenarios']:
            row = scenario['rows'][0]
            self.assertEqual(Decimal(row['quantity']), 0)
            self.assertEqual(Decimal(row['modeled_entry_cost']), 0)
            self.assertEqual(Decimal(row['modeled_cash_debit']), 0)
            self.assertEqual(Decimal(row['budget_remainder']), 2)

    def test_portfolio_and_alternatives_do_not_share_total_semantics(self):
        document = cost_document()
        second = deepcopy(document['rows'][0]); second.update(id='candidate-2', price='11')
        document['rows'].append(second)
        alternatives = decision.budget_sizing(document)
        self.assertTrue(alternatives['alternatives_are_mutually_exclusive'])
        self.assertIsNone(alternatives['scenarios'][0]['portfolio_totals'])
        self.assertEqual([r['requested_cash_budget'] for r in alternatives['scenarios'][0]['rows']], ['97.40', '97.40'])
        document['mode'] = 'portfolio'
        document['rows'][0]['budget'] = '42'; document['rows'][1]['budget'] = '39'
        portfolio = decision.budget_sizing(document)
        for scenario in portfolio['scenarios']:
            totals = scenario['portfolio_totals']
            debit = sum(Decimal(r['modeled_cash_debit']) for r in scenario['rows'])
            self.assertEqual(Decimal(totals['modeled_cash_debit']), debit)
            self.assertEqual(Decimal(totals['budget_remainder']), Decimal('97.40') - debit)
            self.assertEqual(Decimal(totals['unassigned_cash_budget']), Decimal('16.40'))

    def test_unknown_costs_increment_order_count_or_budget_stays_unknown(self):
        for field in ('costs', 'entry_orders', 'price'):
            with self.subTest(field=field):
                document = cost_document(); document['rows'][0][field] = None
                result = decision.budget_sizing(document)['scenarios'][0]['rows'][0]
                self.assertIsNone(result['quantity'])
                self.assertIsNone(result['modeled_cash_debit'])
        document = cost_document(); document['quantity_scenarios'][0]['quantity_step'] = None
        result = decision.budget_sizing(document)
        self.assertIsNone(result['scenarios'][0]['rows'][0]['quantity'])
        self.assertIsNotNone(result['scenarios'][1]['rows'][0]['quantity'])
        document['mode'] = 'portfolio'
        self.assertIsNone(decision.budget_sizing(document)['scenarios'][1]['portfolio_totals']['modeled_cash_debit'])

    def test_unknown_cost_amount_is_not_zero(self):
        document = cost_document(); document['rows'][0]['costs'][0]['amount'] = None
        self.assertIsNone(decision.budget_sizing(document)['scenarios'][0]['rows'][0]['quantity'])

    def test_name_changes_and_external_decimal_context_do_not_change_math(self):
        original = cost_document(); expected = decision.budget_sizing(original)
        document = deepcopy(original); document['rows'][0].update(id='unrelated-id', symbol='OTHER-SYNTHETIC')
        with localcontext() as context:
            context.prec = 3; context.rounding = ROUND_UP
            changed = decision.budget_sizing(document)
        for left, right in zip(expected['scenarios'], changed['scenarios']):
            for key in ('quantity', 'gross_notional', 'modeled_entry_cost', 'modeled_cash_debit', 'budget_remainder'):
                self.assertEqual(left['rows'][0][key], right['rows'][0][key])
        self.assertEqual(original, cost_document())

    def test_incoherent_inputs_raise(self):
        document = cost_document(); document['quantity_scenarios'][0]['quantity_step'] = '.5'
        with self.assertRaises(ValueError): decision.budget_sizing(document)
        document = cost_document(); document['mode'] = 'portfolio'; document['rows'][0]['budget'] = '100'
        with self.assertRaises(ValueError): decision.budget_sizing(document)
        document = cost_document(); document['rows'][0]['costs'][0]['amount'] = '-1'
        with self.assertRaises(ValueError): decision.budget_sizing(document)


class FrictionTests(unittest.TestCase):
    def document(self):
        return {'currency': 'USD', 'role': 'user_assumption', 'price_basis': 'last', 'costs': [],
                'quoted_spread': {'amount': '38', 'unit': 'bps', 'reference_price_basis': 'unknown', 'provenance': 'quote-source'},
                'modeled_slippage': {'id': 'assumed-one-way', 'amount': '12', 'unit': 'bps_notional',
                                     'phase': 'entry', 'convention': 'one_way', 'reference_price_basis': 'last',
                                     'overlap': 'independent', 'provenance': 'explicit sensitivity'}}

    def test_unknown_quote_basis_does_not_veto_explicit_sensitivity(self):
        document = self.document(); result = decision.friction_context(document)
        self.assertEqual(result['applied_costs'], [{'id': 'assumed-one-way', 'amount': '12',
                                                  'unit': 'bps_notional', 'phase': 'entry'}])
        budget = cost_document(); budget['rows'][0].update({k: v for k, v in document.items() if k not in {'currency', 'role'}})
        result = decision.budget_sizing(budget)['scenarios'][0]['rows'][0]
        expected = Fraction(result['gross_notional']) * Fraction(12, 10000)
        self.assertEqual(Fraction(result['modeled_entry_cost']), expected)

    def test_observed_spread_cannot_change_sized_quantity_or_debit(self):
        budget = cost_document(); before = decision.budget_sizing(budget)
        budget['rows'][0]['quoted_spread'] = self.document()['quoted_spread']
        after = decision.budget_sizing(budget)
        for left, right in zip(before['scenarios'], after['scenarios']):
            for key in ('quantity', 'gross_notional', 'modeled_cash_debit'):
                self.assertEqual(left['rows'][0][key], right['rows'][0][key])

    def test_unknown_overlap_and_reference_do_not_silently_choose_cost(self):
        for key, value in [('overlap', 'unknown'), ('reference_price_basis', 'unknown'),
                           ('reference_price_basis', 'midpoint')]:
            document = self.document(); document['modeled_slippage'][key] = value
            self.assertIsNone(decision.friction_context(document)['applied_costs'])

    def test_included_slippage_is_not_added_twice(self):
        document = self.document()
        document['costs'] = [{'id': 'combined-friction', 'amount': '20', 'unit': 'bps_notional', 'phase': 'entry'}]
        document['modeled_slippage'].update(overlap='included_in_costs', overlapping_cost_ids=['combined-friction'])
        result = decision.friction_context(document)
        self.assertEqual(result['applied_costs'], document['costs'])
        document['modeled_slippage']['overlapping_cost_ids'] = ['absent-fee']
        with self.assertRaises(ValueError): decision.friction_context(document)


class AllocationContextTests(unittest.TestCase):
    def test_issuer_sector_industry_and_nested_fund_conservation(self):
        result = decision.allocation_context(context_document())
        self.assertEqual(Decimal(result['known_gross_notional']), 850)
        self.assertEqual(Decimal(result['denominator_difference']), 150)
        issuer = result['exposures']['issuer_id']
        self.assertEqual(Decimal(issuer['groups']['issuer-a']['notional']), 400)
        self.assertEqual(Decimal(issuer['groups']['issuer-a']['fraction_of_denominator']), Decimal('.4'))
        self.assertEqual(Decimal(issuer['groups']['issuer-c']['notional']), 150)
        self.assertEqual(Decimal(issuer['unknown_notional']), 100)
        self.assertEqual(Decimal(issuer['non_applicable_cash_notional']), 200)
        self.assertNotIn('fund-sponsor-is-not-underlying-exposure', issuer['groups'])
        self.assertEqual(Decimal(result['exposures']['sector']['unknown_notional']), 100)
        self.assertEqual(Decimal(result['exposures']['industry']['unknown_notional']), 250)
        for dimension in result['exposures'].values():
            self.assertEqual(Decimal(dimension['conservation_residual']), 0)
        fund = result['fund_lookthrough']
        self.assertEqual(Decimal(fund['terminal_nonfund_notional']), 300)
        self.assertEqual(Decimal(fund['embedded_cash_notional']), 100)
        self.assertEqual(Decimal(fund['opaque_or_uncovered_fund_notional']), 100)
        self.assertEqual(Decimal(fund['terminal_coverage_fraction']), Decimal('.8'))
        self.assertEqual(Decimal(fund['conservation_residual']), 0)

    def test_source_period_units_and_notional_volume_ratio_preserved(self):
        document = context_document(); result = decision.allocation_context(document)
        volume = result['rows'][0]['dollar_volume_context']
        self.assertEqual(Decimal(volume['notional_to_supplied_dollar_volume']), Decimal('.002'))
        self.assertEqual(volume['ratio_unit'], 'days')
        self.assertEqual(volume['observation'], document['rows'][0]['dollar_volume'])
        sources = result['exposures']['issuer_id']['groups']['issuer-a']['contributors']
        self.assertEqual(sources[0]['provenance'], document['rows'][0]['provenance'])
        self.assertEqual(sources[2]['lookthrough_source_chain'][1]['provenance'], {'source': 'fund-holdings'})
        self.assertEqual(sources[2]['lookthrough_source_chain'][0]['source_role'], 'top_level_notional')

    def test_wrong_currency_share_volume_unknown_or_zero_volume_not_used(self):
        for update in ({'currency': None}, {'currency': 'EUR'}, {'unit': 'shares_per_day'}, {'amount': None}, {'amount': '0'}):
            document = context_document(); document['rows'][0]['dollar_volume'].update(update)
            ratio = decision.allocation_context(document)['rows'][0]['dollar_volume_context']
            self.assertIsNone(ratio['notional_to_supplied_dollar_volume'])
            self.assertTrue(ratio['unresolved'])

    def test_missing_period_is_unknown_metadata_and_not_a_freshness_claim(self):
        document = context_document(); document['rows'][0]['dollar_volume'].pop('period')
        result = decision.allocation_context(document)['rows'][0]['dollar_volume_context']
        self.assertEqual(Decimal(result['notional_to_supplied_dollar_volume']), Decimal('.002'))
        self.assertFalse(result['period_known'])
        self.assertFalse(result['source_freshness_verified'])
        self.assertIsNone(result['feasible_participation_rate'])

    def test_unknown_notional_or_cash_debit_never_becomes_exposure_zero(self):
        for update in ({'notional': None}, {'notional_basis': 'cash_debit'}, {'currency': 'EUR'}):
            document = context_document(); document['rows'][0].update(update)
            result = decision.allocation_context(document)
            self.assertIsNone(result['total_gross_notional'])
            self.assertIsNone(result['denominator_difference'])
            self.assertIsNone(result['rows'][0]['gross_notional'])
            self.assertEqual(result['exposures']['issuer_id']['unquantified_row_ids'], ['line-a'])

    def test_unknown_issuer_is_not_symbol_and_unknown_sector_keeps_denominator(self):
        document = context_document(); document['rows'][0].update(issuer_id=None, sector=None, symbol='EXPLICIT-SECURITY')
        result = decision.allocation_context(document)
        self.assertNotIn('EXPLICIT-SECURITY', result['exposures']['issuer_id']['groups'])
        self.assertEqual(Decimal(result['exposures']['sector']['unknown_notional']), 310)
        self.assertEqual(Decimal(result['exposures']['sector']['groups']['sector-p']['fraction_of_denominator']), Decimal('.19'))

    def test_missing_denominator_never_uses_identified_assets_instead(self):
        document = context_document(); document['denominator']['amount'] = None
        result = decision.allocation_context(document)
        self.assertIsNone(result['exposures']['issuer_id']['groups']['issuer-a']['fraction_of_denominator'])
        self.assertEqual(Decimal(result['exposures']['issuer_id']['groups']['issuer-a']['notional']), 400)

    def test_rescaling_every_dollar_preserves_weights_and_volume_ratios(self):
        original = context_document(); scaled = deepcopy(original)
        scaled['denominator']['amount'] = str(Decimal(scaled['denominator']['amount']) * 7)
        for row in scaled['rows']:
            row['notional'] = str(Decimal(row['notional']) * 7)
            if row.get('dollar_volume'):
                row['dollar_volume']['amount'] = str(Decimal(row['dollar_volume']['amount']) * 7)
        first, second = decision.allocation_context(original), decision.allocation_context(scaled)
        for key in decision.DIMENSIONS:
            for label, group in first['exposures'][key]['groups'].items():
                self.assertEqual(Decimal(group['fraction_of_denominator']), Decimal(second['exposures'][key]['groups'][label]['fraction_of_denominator']))
        self.assertEqual(first['rows'][0]['dollar_volume_context']['notional_to_supplied_dollar_volume'],
                         second['rows'][0]['dollar_volume_context']['notional_to_supplied_dollar_volume'])
        self.assertEqual(original, context_document())

    def test_fund_missing_weights_or_holdings_are_explicit(self):
        document = context_document(); document['rows'][2]['lookthrough'] = None
        result = decision.allocation_context(document)
        self.assertEqual(Decimal(result['fund_lookthrough']['opaque_or_uncovered_fund_notional']), 500)
        document = context_document(); document['rows'][2]['lookthrough']['constituents'][0]['weight'] = None
        result = decision.allocation_context(document)
        self.assertEqual(Decimal(result['fund_lookthrough']['opaque_or_uncovered_fund_notional']), 250)
        self.assertEqual(result['fund_lookthrough']['fund_records'][-1]['unknown_weight_constituent_ids'], ['holding-a'])
        self.assertIsNone(result['fund_lookthrough']['terminal_coverage_fraction'])

    def test_unknown_constituent_type_and_unknown_fund_notional_cannot_claim_full_coverage(self):
        document = context_document()
        document['rows'][2]['lookthrough']['constituents'][0]['instrument_type'] = 'unknown'
        result = decision.allocation_context(document)
        self.assertEqual(Decimal(result['fund_lookthrough']['opaque_or_uncovered_fund_notional']), 250)
        self.assertEqual(Decimal(result['fund_lookthrough']['terminal_coverage_fraction']), Decimal('.5'))
        document['rows'].append({'id': 'unvalued-fund', 'notional': None, 'notional_basis': 'gross_notional',
                                 'instrument_type': 'fund'})
        result = decision.allocation_context(document)
        self.assertIsNone(result['fund_lookthrough']['terminal_coverage_fraction'])
        self.assertEqual(result['fund_lookthrough']['unquantified_fund_row_ids'], ['unvalued-fund'])

    def test_unknown_weight_after_known_full_weight_does_not_assert_complete_coverage(self):
        document = context_document()
        document['rows'][2]['lookthrough']['constituents'] = [
            {'id': 'known', 'weight': '1', 'instrument_type': 'equity', 'issuer_id': 'issuer-a'},
            {'id': 'weight-missing', 'weight': None, 'instrument_type': 'equity', 'issuer_id': 'issuer-z'}]
        result = decision.allocation_context(document)
        self.assertIsNone(result['fund_lookthrough']['terminal_coverage_fraction'])
        self.assertTrue(result['fund_lookthrough']['unknown_weight_fund_paths'])

    def test_fund_overcoverage_and_negative_notionals_rejected(self):
        document = context_document(); document['rows'][2]['lookthrough']['constituents'][0]['weight'] = '.9'
        with self.assertRaises(ValueError): decision.allocation_context(document)
        document = context_document(); document['rows'][0]['notional'] = '-1'
        with self.assertRaises(ValueError): decision.allocation_context(document)


if __name__ == '__main__':
    unittest.main()
