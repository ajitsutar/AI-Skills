import copy
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import quant_workbench as qw
import report_facts as rf

NOW = '2026-11-02T20:00:00Z'

def targets():
    return {'as_of': NOW, 'currency': 'USD', 'max_position_weight': .4,
            'sleeves': [{'id': 'fictional', 'subject_id': 'fictional-manager',
                'mode': 'snapshot', 'budget_weight': .8, 'current_weights': {},
                'source_status': 'verified', 'checked_at': NOW, 'max_age_days': 180,
                'records': [{'subject_id': 'fictional-manager', 'event_id': 'quarter-1',
                    'revision': 0, 'withdrawn': False, 'source_ref': 'fictional-source',
                    'event_at': '2026-09-30T23:00:00Z', 'published_at': NOW,
                    'available_at': NOW, 'currency': 'USD', 'complete_reported_basket': True,
                    'positions': [
                        {'security_id': 'ONE', 'asset_type': 'common_stock', 'eligible_common': True, 'market_value': 300},
                        {'security_id': 'TWO', 'asset_type': 'common_stock', 'eligible_common': True, 'market_value': 100}]}]}]}

def campaign(operation, payload):
    return {'schema_version': 1, 'contract': {'prompt': 'Fictional follower review',
            'purpose': 'offline integration', 'base_currency': 'USD', 'horizon_id': 'P1M', 'as_of': NOW},
            'jobs': [{'id': 'follower', 'operation': operation, 'inputs': {'document': payload}}]}

class FollowerIntegrationTests(unittest.TestCase):
    def test_frozen_targets_replay_and_export_economic_denominator(self):
        bundle = qw.freeze(campaign('follower.targets', targets()))
        result = bundle['result']['results'][0]
        self.assertEqual(result['status'], 'COMPUTED', result)
        self.assertEqual(result['result']['target_weights'], {'ONE': .4, 'TWO': .2})
        self.assertAlmostEqual(result['result']['target_cash_weight'], .4)
        self.assertEqual(qw.verify(json.loads(json.dumps(bundle)))['jobs_verified'], 1)
        projected = rf.project(json.dumps(bundle).encode(), 'quant')
        weight = [f for f in projected['facts'] if f['metric'] == 'Proposed follower security weight']
        self.assertEqual(sorted(f['value'] for f in weight), [.2, .4])
        self.assertTrue(all(f['denominator'] == 'total account NAV' for f in weight))
        self.assertEqual(qw.implementation_hash(), rf.quant_hash())

    def test_contract_cannot_admit_future_or_other_currency_targets(self):
        for key, value, reason in [('as_of', '2026-11-03T20:00:00Z', 'FUTURE_FOLLOWER_CUTOFF'),
                                   ('currency', 'CAD', 'FOLLOWER_CURRENCY_MISMATCH')]:
            payload = targets(); payload[key] = value
            result = qw.run(campaign('follower.targets', payload))['results'][0]
            self.assertEqual(result['status'], 'REJECTED_INPUT')
            self.assertIn(reason, result['reason'])

    def test_normalization_replay_preserves_transaction_range_unknown_weight(self):
        payload = {'as_of': NOW, 'kind': 'public_transactions', 'subject_id': 'fictional-family',
                   'events': [{'event_id': 'record-1', 'revision': 0, 'withdrawn': False,
                       'source_ref': 'fictional-disclosure', 'event_at': '2026-10-01T12:00:00Z',
                       'published_at': NOW, 'available_at': NOW, 'action': 'BUY',
                       'security_id': 'ONE', 'asset_type': 'common_stock', 'owner': 'spouse',
                       'source_reviewed': True, 'identity_reviewed': True,
                       'amount_range': {'lower': 1001, 'upper': 15000, 'currency': 'USD'}}]}
        bundle = qw.freeze(campaign('follower.normalize', payload))
        job = bundle['result']['results'][0]
        self.assertEqual(job['status'], 'COMPUTED', job)
        self.assertIsNone(job['result']['records'][0]['actual_portfolio_weight'])
        self.assertEqual(qw.verify(bundle)['jobs_verified'], 1)
        projected = rf.project(json.dumps(bundle).encode(), 'quant')
        lower = [f for f in projected['facts'] if f['metric'] == 'Disclosed transaction range lower bound']
        self.assertEqual(lower[0]['value'], '1001')
        self.assertIn('not quantity or holding weight', lower[0]['basis'])

    def test_rebalance_is_pure_and_replayable_without_spending_sale_proceeds(self):
        t = targets()
        quote = {'source_ref': 'fictional-quote', 'price_basis': 'unadjusted',
                 'observed_at': NOW, 'available_at': NOW, 'price': 10, 'quantity_step': 1}
        payload = {'target_document': t, 'currency': 'USD', 'open_orders': [],
                   'holdings_at': NOW, 'max_holdings_age_seconds': 60, 'max_quote_age_seconds': 60,
                   'settled_cash': 500, 'pending_receivables': 100, 'cash_floor': 200,
                   'reserved_cash': 0, 'fixed_fee_per_trade': 0, 'cost_bps': 0,
                   'min_trade_notional': 1, 'account_nav': 1000,
                   'holdings': [{'security_id': 'OTHER', 'quantity': 40, 'follower_quantity': 0}],
                   'quotes': {key: copy.deepcopy(quote) for key in ('ONE', 'TWO', 'OTHER')}}
        original = copy.deepcopy(payload)
        bundle = qw.freeze(campaign('follower.rebalance', payload))
        job = bundle['result']['results'][0]
        self.assertEqual(job['status'], 'COMPUTED', job)
        self.assertEqual(payload, original)
        self.assertEqual(qw.verify(bundle)['jobs_verified'], 1)
        self.assertLessEqual(float(job['result']['estimated_buy_cash_use']), 300)
        self.assertTrue(all(p['security_id'] != 'OTHER' for p in job['result']['proposals']))

if __name__ == '__main__':
    unittest.main()
