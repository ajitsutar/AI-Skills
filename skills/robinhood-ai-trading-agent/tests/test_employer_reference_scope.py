"""Fixed employer references must bind their generated sales to the source baseline."""
from copy import deepcopy
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from employer_reference import employer_diversification_baseline
from portfolio_projection import source_projection


def source():
    return {'currency': 'USD', 'as_of': '2044-03-01T12:00:00Z',
            'baseline_rebalance': {'equity': '148', 'cash': '100', 'tax_reserve': '0',
                                  'holdings': {'SYNTH': '12'}, 'prices': {'SYNTH': '4'}},
            'identities': {'SYNTH': {'issuer_id': 'SYNTHETIC_ISSUER', 'kind': 'common_stock', 'sector': 'industrial'}},
            'funds': [], 'other_assets': [], 'liabilities': [],
            'employer': {'symbol': 'SYNTH', 'current_vested_quantity': '12', 'grant_records': [
                {'vest_date': '2044-03-20', 'gross_shares': '3', 'shares_withheld_for_tax': '1',
                 'shares_sold_for_tax': '0', 'status': 'future_scheduled', 'assumed_vest_price': '5'}]},
            'confirmed_cash_events': [{'id': 'obligation', 'available_at': '2044-03-10', 'amount': '-5',
                                       'kind': 'external_obligation', 'confirmed': True}],
            'withdrawal': {'spendable_by': '2044-03-15', 'amount': '10'},
            'cost_assumptions': {'fee_per_trade': '1', 'one_way_slippage_bps': '10'}}


def document(data=None):
    text = json.dumps(source() if data is None else data, sort_keys=True)
    return {'currency': 'USD', 'role': 'hypothetical_scenario', 'source_role': 'supplied_observation',
            'source_ref': 'public-synthetic#', 'source_utf8': text,
            'source_sha256': hashlib.sha256(text.encode('utf-8')).hexdigest()}


class EmployerReferenceScopeTests(unittest.TestCase):
    def test_public_wrapper_binds_all_references_and_retains_source_flows(self):
        doc = document(); original = deepcopy(doc)
        result = employer_diversification_baseline(doc)
        self.assertEqual(doc, original)
        self.assertEqual(result['source_sha256_checked'], original['source_sha256'])
        self.assertEqual(result['retained_input']['source_utf8'], original['source_utf8'])
        self.assertIsNone(result['selected_alternative'])
        self.assertEqual(result['status'], 'DATED_ALTERNATIVES_COMPARED')
        self.assertEqual(result['target_date'], '2044-03-20')
        primary = result['primary_result']['alternatives']
        self.assertEqual([r['id'] for r in primary], ['retain', 'sell_all_net_vests', 'sell_all_direct_and_net'])
        projections = [r['projection_receipt']['projection'] for r in primary]
        self.assertEqual([p['cash'] for p in projections], ['85', '91.992', '138.944'])
        self.assertEqual([p['position_values'][0]['quantity'] for p in projections], ['14', '12', '0'])
        self.assertEqual([p['net_equity'] for p in projections], ['141', '139.992', '138.944'])
        # Both denominator sensitivities and the separate source-vest-price path
        # use the same opening/event scope, not just the primary sale branch.
        comparisons = [result['primary_result'], result['source_vest_price_sensitivity'],
                       result['denominator_sensitivity']['comparison'],
                       result['source_vest_price_denominator_sensitivity']['comparison']]
        receipts = [r['projection_receipt'] for c in comparisons for r in c['alternatives']]
        receipts.append(result['retained_projection'])
        for receipt in receipts:
            scope = receipt['projection_scope_receipt']
            self.assertTrue(scope['explicit'])
            self.assertEqual(scope['mode'], 'baseline_continuation')
            self.assertEqual(receipt['source_flow_count'], 3)
            self.assertEqual(len(scope['source_event_audit']), 3)
            self.assertTrue(all(r['passed_to_projection'] for r in scope['source_event_audit']))
        source_price = result['source_vest_price_sensitivity']['alternatives'][1]['projection_receipt']['projection']
        self.assertEqual(source_price['cash'], '93.990')

    def test_equity_includes_cash_and_residual_is_not_spendable_cash(self):
        data = source(); data['baseline_rebalance']['equity'] = '160'
        data.pop('other_assets')
        result = employer_diversification_baseline(document(data))
        primary = result['primary_result']['alternatives'][0]['projection_receipt']['projection']
        self.assertIsNone(primary['other_assets_value'])
        sensitivity = result['denominator_sensitivity']['comparison']['alternatives'][0]['projection_receipt']
        # Opening NAV160 includes100 cash and48 marked shares, leaving12 unknown.
        self.assertEqual(sensitivity['opening_residual'], '12')
        self.assertEqual(sensitivity['projection']['cash'], '85')
        self.assertEqual(sensitivity['projection']['other_assets_value'], '12')
        self.assertEqual(sensitivity['projection']['identified_assets'], '141')
        self.assertEqual(sensitivity['projection']['net_equity'], '153')

    def test_unknown_balances_are_not_filled_in_primary(self):
        data = source(); data['baseline_rebalance'].pop('tax_reserve')
        data.pop('other_assets'); data.pop('liabilities')
        result = employer_diversification_baseline(document(data))
        for row in result['primary_result']['alternatives']:
            projection = row['projection_receipt']['projection']
            self.assertIsNone(projection['net_equity'])
            self.assertIsNone(projection['other_assets_value'])
        self.assertFalse(result['denominator_sensitivity']['primary'])

    def test_no_included_future_vest_invents_no_sale(self):
        doc = document(); doc['included_states'] = ['confirmed', 'scenario']
        result = employer_diversification_baseline(doc)
        self.assertEqual(result['status'], 'NO_INCLUDED_FUTURE_VEST_DATE')
        self.assertIsNone(result['primary_result'])
        self.assertEqual(result['baseline_sale_receipts'], [])
        self.assertEqual(result['target_date'], '2044-03-01')
        receipt = result['retained_projection']
        self.assertTrue(receipt['projection_scope_receipt']['explicit'])
        self.assertEqual(receipt['projection']['position_values'][0]['quantity'], '12')
        self.assertEqual(receipt['source_flow_count'], 3)

    def test_explicit_opening_date_keeps_original_binding_and_event_boundaries(self):
        doc = document(); doc.update(opening_date='2044-03-02', opening_date_role='user_assumption',
                                     opening_date_basis='Carry the same balances one day forward for this reference.')
        result = employer_diversification_baseline(doc)
        self.assertEqual(result['opening_binding']['date'], '2044-03-02')
        self.assertEqual(result['retained_input']['source_utf8'], doc['source_utf8'])
        self.assertEqual(result['primary_result']['alternatives'][0]['projection_receipt']['projection']['cash'], '85')
        doc['opening_date'] = '2044-03-11'
        with self.assertRaisesRegex(ValueError, 'FLOW_NOT_AFTER_OPENING'):
            employer_diversification_baseline(doc)
        doc['opening_date'] = '2044-03-21'
        with self.assertRaisesRegex(ValueError, 'SOURCE_GRANTS_ALREADY_IN_OPENING'):
            employer_diversification_baseline(doc)
        doc.pop('opening_date_basis')
        with self.assertRaisesRegex(ValueError, 'EXPLICIT_OPENING_DATE_ASSUMPTION_REQUIRED'):
            employer_diversification_baseline(doc)

    def test_incompatible_caller_scope_cannot_redefine_fixed_references(self):
        doc = document(); doc['projection_scope'] = {'mode': 'baseline_continuation'}
        self.assertEqual(employer_diversification_baseline(doc)['status'], 'DATED_ALTERNATIVES_COMPARED')
        for scope in ({'mode': 'independent_scenario'}, {'mode': 'baseline_continuation', 'opening': {}}, None):
            doc['projection_scope'] = scope
            with self.assertRaisesRegex(ValueError, 'EMPLOYER_REFERENCE_REQUIRES_BASELINE_CONTINUATION'):
                employer_diversification_baseline(doc)

    def test_direct_scenario_flow_still_requires_explicit_scope(self):
        data = source()
        doc = {'currency': 'USD', 'role': 'hypothetical_scenario', 'source': data,
               'source_ref': 'public-synthetic#', 'source_role': 'supplied_observation',
               'date_basis': 'source_calendar_label', 'target_date': '2044-03-20',
               'included_states': ['confirmed', 'planned', 'scenario'], 'mark_policy': 'carry_forward_supplied',
               'opening_tax_reserve': '0', 'other_assets': [], 'liabilities': [],
               'scenario_flows': [{'id': 'sale', 'date': '2044-03-20', 'currency': 'USD',
                    'source_ref': 'scenario:sale', 'source_role': 'user_assumption', 'state': 'scenario',
                    'kind': 'trade', 'asset_id': 'SYNTH', 'included_in_opening': False,
                    'trade': {'side': 'sell', 'quantity': '2', 'price': '4', 'entry_orders': 1,
                              'transaction_phase': 'exit', 'costs': []}}]}
        with self.assertRaisesRegex(ValueError, 'EXPLICIT_PROJECTION_SCOPE_REQUIRED_FOR_SCENARIO_FLOWS'):
            source_projection(doc)
        doc['projection_scope'] = {'mode': 'baseline_continuation'}
        self.assertEqual(Decimal(source_projection(doc)['projection']['cash']), Decimal('93'))


if __name__ == '__main__':
    unittest.main()
