import copy
from decimal import Decimal, localcontext
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import allocation_policy as allocation


def request(symbols=('C', 'A', 'B'), **changes):
    result = {'schema_version': 1, 'currency': 'USD', 'role': 'hypothetical_scenario',
              'budget': '500.00', 'budget_basis': 'notional',
              'candidate_set': {
                  'kind': 'diagnostic_queue', 'source_id': 'retained-example-queue',
                  'declared_count': len(symbols),
                  'rows': [{'symbol': s, 'issuer_id': 'issuer-' + s, 'currency': 'USD'} for s in symbols]}}
    result.update(changes)
    return result


def amounts(result, name='advisory_cash_amount'):
    return {r['symbol']: r[name] for r in result['rows']}


class AllocationPolicyTests(unittest.TestCase):
    def test_no_invented_count_or_score_threshold_and_full_budget(self):
        document = request(tuple('ZABCDEFG'))
        for i, row in enumerate(document['candidate_set']['rows']):
            row['score'] = -100 * i
        result = allocation.allocate(document)
        self.assertEqual(result['selected_symbols'], list('ZABCDEFG'))
        self.assertEqual(result['selected_count'], 8)
        self.assertIsNone(result['requested_count'])
        self.assertEqual(set(amounts(result).values()), {'62.50'})
        self.assertEqual(result['totals']['allocated_notional_total'], '500.00')
        self.assertIsNone(result['expected_return'])
        self.assertFalse(result['optimization_performed'])

    def test_count_selects_prefix_and_never_fills_shortfall_with_new_names(self):
        document = request(requested_count=2)
        self.assertEqual(allocation.allocate(document)['selected_symbols'], ['C', 'A'])
        document['requested_count'] = 10
        result = allocation.allocate(document)
        self.assertEqual(result['selected_symbols'], ['C', 'A', 'B'])
        self.assertEqual(result['count_shortfall'], 7)
        self.assertFalse(result['requested_count_met'])
        self.assertFalse(result['count_conflict'])

    def test_equal_remainder_follows_explicit_order_without_alphabetic_rerank(self):
        first = allocation.allocate(request())
        second = allocation.allocate(request(('B', 'C', 'A')))
        self.assertEqual(amounts(first), {'C': '166.67', 'A': '166.67', 'B': '166.66'})
        self.assertEqual(amounts(second), {'B': '166.67', 'C': '166.67', 'A': '166.66'})
        self.assertEqual(first['totals']['allocated_notional_total'], '500.00')
        self.assertEqual(second['totals']['allocated_notional_total'], '500.00')

    def test_no_remainder_permutation_preserves_symbol_allocations(self):
        a = allocation.allocate(request(budget='600.00'))
        b = allocation.allocate(request(('B', 'C', 'A'), budget='600.00'))
        self.assertEqual(amounts(a), amounts(b))
        self.assertNotEqual(a['input_sha256'], b['input_sha256'])

    def test_tiny_budget_keeps_every_name_instead_of_inventing_a_minimum(self):
        result = allocation.allocate(request(budget='0.02'))
        self.assertEqual(result['selected_symbols'], ['C', 'A', 'B'])
        self.assertEqual(amounts(result), {'C': '0.01', 'A': '0.01', 'B': '0.00'})
        self.assertFalse(result['broker_rules_applied'])

    def test_primary_review_missing_remains_conditional_with_no_certification(self):
        result = allocation.allocate(request())
        self.assertEqual(result['status'], 'CONDITIONAL_RESEARCH_BASELINE')
        self.assertEqual(result['missing_primary_review_symbols'], ['C', 'A', 'B'])
        self.assertTrue(all(r['primary_review_status'] is None for r in result['rows']))
        self.assertFalse(result['recommendation_validated'])
        self.assertFalse(result['source_authenticity_verified'])
        self.assertFalse(result['execution_permission_evaluated'])
        self.assertFalse(result['orders_submitted'])

    def test_reviewed_exact_set_preserved_even_with_conflicting_count(self):
        document = request(requested_count=1)
        document['candidate_set']['kind'] = 'reviewed_selection'
        for row in document['candidate_set']['rows']:
            row['primary_review_status'] = 'complete'
        result = allocation.allocate(document)
        self.assertEqual(result['selected_symbols'], ['C', 'A', 'B'])
        self.assertEqual(result['selection_basis'], 'reviewed_selection')
        self.assertTrue(result['count_conflict'])
        self.assertEqual(result['status'], 'ADVISORY_ALLOCATION_BASELINE')
        self.assertFalse(result['recommendation_validated'])

    def test_reviewed_source_label_cannot_fill_missing_row_review(self):
        document = request()
        document['candidate_set']['kind'] = 'reviewed_selection'
        result = allocation.allocate(document)
        self.assertEqual(result['status'], 'CONDITIONAL_RESEARCH_BASELINE')
        self.assertEqual(result['selected_count'], 3)

    def test_diagnostic_queue_cannot_promote_itself_with_complete_flags(self):
        document = request()
        for row in document['candidate_set']['rows']:
            row['primary_review_status'] = 'complete'
        self.assertEqual(allocation.allocate(document)['status'], 'CONDITIONAL_RESEARCH_BASELINE')

    def test_explicit_user_selection_overrides_count_and_reviewed_set(self):
        document = request(user_selection=['B', 'C'], requested_count=1)
        document['candidate_set']['kind'] = 'reviewed_selection'
        result = allocation.allocate(document)
        self.assertEqual(result['selected_symbols'], ['B', 'C'])
        self.assertEqual(amounts(result), {'B': '250.00', 'C': '250.00'})
        self.assertTrue(result['count_conflict'])
        self.assertEqual(result['selection_basis'], 'user_selection')

    def test_explicit_weight_set_and_partial_cash_preserved_without_normalization(self):
        document = request(user_weights=[{'symbol': 'B', 'weight': '0.3000'},
                                         {'symbol': 'C', 'weight': '0.2000'}])
        result = allocation.allocate(document)
        self.assertEqual(result['selected_symbols'], ['B', 'C'])
        self.assertEqual(amounts(result), {'B': '150.00', 'C': '100.00'})
        self.assertEqual(result['rows'][0]['requested_weight'], '0.3000')
        self.assertEqual(result['totals']['reference_unallocated_notional_budget'], '250.00')
        self.assertEqual(result['retained_input']['user_weights'], document['user_weights'])

    def test_weight_largest_remainders_and_explicit_order_break_ties(self):
        document = request(budget='0.05', user_selection=['C', 'B', 'A'], user_weights=[
            {'symbol': 'A', 'weight': '.4'}, {'symbol': 'B', 'weight': '.3'},
            {'symbol': 'C', 'weight': '.3'}])
        result = allocation.allocate(document)
        self.assertEqual(amounts(result), {'C': '0.02', 'B': '0.01', 'A': '0.02'})
        self.assertEqual(result['totals']['reference_unallocated_notional_budget'], '0.00')

    def test_zero_weights_kept_and_remaining_cash_unallocated(self):
        result = allocation.allocate(request(user_weights=[{'symbol': 'A', 'weight': '0'}]))
        self.assertEqual(result['selected_symbols'], ['A'])
        self.assertEqual(amounts(result), {'A': '0.00'})
        self.assertEqual(result['totals']['reference_unallocated_notional_budget'], '500.00')

    def test_selection_weight_set_conflict_never_rewritten(self):
        document = request(user_selection=['A'], user_weights=[{'symbol': 'C', 'weight': '1'}])
        with self.assertRaisesRegex(ValueError, 'SELECTION_WEIGHT_SET_CONFLICT'):
            allocation.allocate(document)

    def test_invalid_counts_weights_money_and_schema_rejected(self):
        changes = [({'requested_count': True}, 'INVALID_REQUESTED_COUNT'),
                   ({'requested_count': 0}, 'INVALID_REQUESTED_COUNT'),
                   ({'budget': '1.001'}, 'WHOLE_CENTS'),
                   ({'budget': 500.0}, 'DECIMAL_STRING_OR_INTEGER'),
                   ({'budget': 'NaN'}, 'FINITE_NONNEGATIVE'),
                   ({'budget': 0}, 'POSITIVE_BUDGET'),
                   ({'schema_version': True}, 'ALLOCATION_INPUT_SCHEMA'),
                   ({'budget_basis': 'cash'}, 'BUDGET_BASIS'),
                   ({'user_weights': [{'symbol': 'A', 'weight': '1.01'}]}, 'EXCEED_FULL_BUDGET'),
                   ({'user_weights': [{'symbol': 'A', 'weight': '-.2'}]}, 'FINITE_NONNEGATIVE'),
                   ({'user_weigths': []}, 'UNKNOWN_DOCUMENT_FIELDS')]
        for values, message in changes:
            with self.subTest(values=values), self.assertRaisesRegex(ValueError, message):
                allocation.allocate(request(**values))

    def test_currency_identity_and_source_counts_are_checked(self):
        tests = [('currency', 'CAD', 'CURRENCY_MISMATCH'),
                 ('symbol', 'c', 'DUPLICATE_SECURITY_IDENTITY'),
                 ('issuer_id', 'ISSUER-C', 'DUPLICATE_ISSUER_IDENTITY')]
        for field, value, message in tests:
            document = request()
            document['candidate_set']['rows'][1][field] = value
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, message):
                allocation.allocate(document)
        for fields, message in [({'declared_count': 8}, 'SOURCE_COUNT'),
                                ({'universe_count': 2}, 'UNIVERSE_COUNT'),
                                ({'coverage_complete': True}, 'UPSTREAM_COVERAGE_UNIVERSE_COUNT')]:
            document = request()
            document['candidate_set'].update(fields)
            with self.subTest(fields=fields), self.assertRaisesRegex(ValueError, message):
                allocation.allocate(document)

    def test_upstream_coverage_does_not_require_selecting_entire_universe(self):
        document = request()
        document['candidate_set'].update(kind='reviewed_selection', universe_count=100,
                                         coverage_complete=True)
        result = allocation.allocate(document)
        self.assertEqual(result['selected_symbols'], ['C', 'A', 'B'])
        self.assertTrue(result['upstream_coverage_declared'])
        self.assertFalse(result['coverage_verified'])
        self.assertIn('UPSTREAM_COVERAGE_DECLARATION_NOT_VERIFIED', result['unresolved'])
        self.assertEqual(result['status'], 'CONDITIONAL_RESEARCH_BASELINE')

    def test_nested_fee_currency_and_hash_mismatch_rejected(self):
        document = request(fees=[{'amount': '1', 'currency': 'EUR'}])
        with self.assertRaisesRegex(ValueError, 'CURRENCY_MISMATCH'):
            allocation.allocate(document)
        document = request()
        document['candidate_set']['rows_sha256'] = allocation.digest(document['candidate_set']['rows'])
        allocation.allocate(document)
        document['candidate_set']['rows'][0]['score'] = 100
        with self.assertRaisesRegex(ValueError, 'ROWS_HASH_MISMATCH'):
            allocation.allocate(document)

    def test_alternatives_get_one_full_budget_each_without_portfolio_total(self):
        result = allocation.allocate(request(mode='alternative_single_stock'))
        self.assertEqual(set(amounts(result).values()), {'500.00'})
        self.assertEqual(result['totals']['budget_per_alternative'], '500.00')
        self.assertIsNone(result['totals']['allocated_notional_total'])
        self.assertIsNone(result['totals']['reference_portfolio_notional'])
        self.assertTrue(result['totals']['alternatives_are_mutually_exclusive'])
        self.assertTrue(result['totals']['alternative_notionals_must_not_be_summed'])
        self.assertEqual(len({r['scenario_id'] for r in result['rows']}), 3)
        document = request(mode='alternative_single_stock', user_weights=[{'symbol': 'A', 'weight': '1'}])
        with self.assertRaisesRegex(ValueError, 'WEIGHTS_CONFLICT'):
            allocation.allocate(document)

    def test_fee_inclusive_is_unresolved_without_invented_feasibility(self):
        result = allocation.allocate(request(budget_basis='fee_inclusive', fees=[{'unit': 'per_order', 'amount': '2'}]))
        self.assertEqual(result['sizing_status'], 'SIZING_UNRESOLVED')
        self.assertTrue(all(v is None for v in amounts(result).values()))
        self.assertEqual(sum(Decimal(v) for v in amounts(result, 'reference_notional_before_fees').values()), Decimal(500))
        self.assertIsNone(result['totals']['allocated_notional_total'])
        self.assertIsNone(result['totals']['all_in_cash_debit'])
        self.assertIsNone(result['totals']['cash_affordable'])
        self.assertIn('FEE_INCLUSIVE_NOTIONAL_SIZING_UNRESOLVED', result['unresolved'])

    def test_constraints_preserved_but_not_claimed_satisfied(self):
        constraints = {'max_name_weight': '.10', 'whole_shares_only': True}
        result = allocation.allocate(request(constraints=constraints))
        self.assertEqual(result['retained_input']['constraints'], constraints)
        self.assertEqual(result['sizing_status'], 'SIZING_UNRESOLVED')
        self.assertIsNone(result['totals']['allocated_notional_total'])
        self.assertIn('SUPPLIED_CONSTRAINTS_RETAINED_NOT_SOLVED', result['unresolved'])

    def test_optimizer_inputs_route_out_without_fabricating_forecast_weights(self):
        document = request(optimizer_inputs={'forecast': ['.1', '.2', '.3'], 'covariance': 'retained-source'})
        result = allocation.allocate(document)
        self.assertEqual(result['status'], 'OPTIMIZER_INPUTS_REQUIRE_SEPARATE_OPERATION')
        self.assertTrue(all(r['reference_notional_before_fees'] is None for r in result['rows']))
        self.assertTrue(all(r['target_weight'] is None for r in result['rows']))
        document['user_weights'] = [{'symbol': 'A', 'weight': '.75'}]
        result = allocation.allocate(document)
        self.assertEqual(amounts(result), {'A': '375.00'})
        self.assertFalse(result['optimization_performed'])

    def test_arbitrary_horizon_native_dollar_and_order_details_preserved(self):
        horizon = {'value': '27.5', 'unit': 'years', 'mode': 'flexible_review'}
        order = {'order_basis': 'native_dollar', 'order_type': 'market', 'session': 'regular'}
        document = request(horizon=horizon, order_details=order)
        document['candidate_set']['rows'][0]['order_details'] = {'limit_price': '51.25', 'order_type': 'limit'}
        result = allocation.allocate(document)
        self.assertEqual(result['horizon'], horizon)
        self.assertEqual(result['order_details'], order)
        self.assertEqual(result['rows'][0]['order_details'], document['candidate_set']['rows'][0]['order_details'])
        self.assertTrue(all(r['share_quantity'] is None for r in result['rows']))
        self.assertFalse(result['quantity_conversion_performed'])

    def test_replay_hashes_input_preservation_and_caller_precision_independence(self):
        document = request(budget='100000000000000000000.01', user_weights=[
            {'symbol': 'A', 'weight': '.12345678901234567890123456789'},
            {'symbol': 'C', 'weight': '.87654321098765432109876543211'}])
        before = copy.deepcopy(document)
        first = allocation.allocate(document)
        with localcontext() as context:
            context.prec = 4
            second = allocation.allocate(document)
        self.assertEqual(first, second)
        self.assertEqual(document, before)
        self.assertEqual(first['totals']['allocated_notional_total'], '100000000000000000000.01')
        self.assertEqual(first['input_sha256'], allocation.digest(document))
        checksum = first.pop('result_sha256')
        self.assertEqual(checksum, allocation.digest(first))
        self.assertEqual(first['policy_sha256'], allocation.digest(allocation.POLICY))

    def test_optional_null_weight_and_count_fields_do_not_invent_values(self):
        result = allocation.allocate(request(user_weights=None, user_selection=None, requested_count=None))
        self.assertEqual(result['selected_count'], 3)
        self.assertTrue(all(r['requested_weight'] is None for r in result['rows']))


if __name__ == '__main__':
    unittest.main()
