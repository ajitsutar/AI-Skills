import copy
import sys
import unittest
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from portfolio_follower import build_targets, rebalance

T0 = '2026-01-01T00:00:00Z'
T1 = '2026-01-02T00:00:00Z'
T2 = '2026-01-03T00:00:00Z'
T3 = '2026-01-04T00:00:00Z'


def event(key='a', security='AAA', action='BUY', **kwargs):
    return dict(subject_id='fictional', event_id=key, security_id=security, action=action,
                event_at=T0, published_at=T1, available_at=T1, revision=0, withdrawn=False,
                source_ref='fictional-fixture', qualifying=True, eligible_common=True,
                sale_scope='full', **kwargs)


def sleeve(mode='events', **kwargs):
    value = dict(id='one', subject_id='fictional', mode=mode, budget_weight=.5,
                 current_weights={}, source_status='verified', checked_at=T2, max_age_days=30,
                 allocation_policy='user_weights', user_weights={'AAA': .6, 'BBB': .4},
                 partial_sell_policy='hold', records=[])
    value.update(kwargs)
    return value


def target(*sleeves, **kwargs):
    value = dict(as_of=T2, currency='USD', max_position_weight=1, sleeves=list(sleeves))
    value.update(kwargs)
    return value


def quote(price):
    return dict(price=str(price), quantity_step='1', observed_at=T2, available_at=T2,
                source_ref='fictional-fixture', price_basis='unadjusted')


def account():
    # $1000 NAV = $200 settled + $100 receivable + 10 AAA at $50 + 10 OUT at $20.
    return dict(target_document=target(sleeve(current_weights={'AAA': 1},
                  user_weights={'BBB': 1}, records=[event(action='SELL'), event('b', 'BBB')])),
                currency='USD', open_orders=[], holdings_at=T2, max_holdings_age_seconds=60,
                max_quote_age_seconds=60, account_nav='1000', settled_cash='200',
                pending_receivables='100', cash_floor='50', reserved_cash='0',
                fixed_fee_per_trade='1', cost_bps='100', min_trade_notional='1',
                holdings=[dict(security_id='AAA', quantity='10', follower_quantity='6'),
                          dict(security_id='OUT', quantity='10', follower_quantity='0')],
                quotes={'AAA': quote(50), 'BBB': quote(25), 'OUT': quote(20)})


class FollowerTargetsTests(unittest.TestCase):
    def test_common_basket_overlap_cap_leaves_cash(self):
        snapshot = {k: v for k, v in event().items() if k not in ('security_id', 'action', 'sale_scope')}
        snapshot.update(currency='USD', complete_reported_basket=True, positions=[
            dict(security_id='AAA', asset_type='common_stock', eligible_common=True, market_value=60),
            dict(security_id='BBB', asset_type='common_stock', eligible_common=True, market_value=40),
            dict(security_id='OPT', asset_type='put', eligible_common=False, market_value=900)])
        first = sleeve('snapshot', budget_weight=.6, records=[snapshot])
        second = sleeve(id='two', budget_weight=.2, user_weights={'AAA': 1}, records=[event()])
        result = build_targets(target(first, second, max_position_weight=.4))
        self.assertEqual(result['target_weights'], {'AAA': .4, 'BBB': .24})
        self.assertAlmostEqual(result['target_cash_weight'], .36)
        self.assertAlmostEqual(result['cap_overflow_cash_weight'], .16)

    def test_publication_not_trade_date_and_no_future_revision(self):
        old = event()
        correction = dict(old, revision=1, action='SELL', published_at=T3, available_at=T3)
        result = build_targets(target(sleeve(records=[old, correction, old])))
        self.assertEqual(result['target_weights'], {'AAA': .3})
        before = target(sleeve(checked_at=T0, records=[old]), as_of=T0)
        self.assertEqual(build_targets(before)['target_weights'], {})

    def test_withdrawal_does_not_reuse_original(self):
        old = event()
        withdrawn = dict(old, revision=1, withdrawn=True, published_at=T2, available_at=T2)
        result = build_targets(target(sleeve(current_weights={'AAA': .2}, records=[old, withdrawn])))
        self.assertEqual(result['target_weights'], {'AAA': .1})
        self.assertEqual(result['frozen_security_ids'], ['AAA'])

    def test_latest_available_revision_supersedes_original(self):
        original = event()
        corrected = dict(original, action='SELL', revision=2, published_at=T2, available_at=T2)
        result = build_targets(target(sleeve(current_weights={'AAA': .6}, records=[corrected, original])))
        self.assertEqual(result['target_weights'], {})

    def test_conflicting_same_time_events_keep_baseline(self):
        result = build_targets(target(sleeve(current_weights={'AAA': .2}, records=[event(), event('b', action='SELL')])))
        self.assertEqual(result['target_weights'], {'AAA': .1})
        self.assertIn('AAA', result['frozen_security_ids'])

    def test_conflicting_duplicate_revision_freezes_sleeve(self):
        result = build_targets(target(sleeve(current_weights={'AAA': .2}, records=[event(), dict(event(), action='SELL')])))
        self.assertEqual(result['frozen_security_ids'], ['AAA'])

    def test_partial_sale_not_full_exit_unless_explicit_policy(self):
        sale = dict(event(action='SELL'), sale_scope='partial', amount_low=1000, amount_high=15000)
        hold = sleeve(current_weights={'AAA': .6}, records=[sale])
        self.assertEqual(build_targets(target(hold))['target_weights'], {'AAA': .3})
        hold['partial_sell_policy'] = 'exit'
        self.assertEqual(build_targets(target(hold))['target_weights'], {})

    def test_unknown_source_and_stale_snapshot_preserve_holdings(self):
        unknown = sleeve(source_status='unknown', current_weights={'AAA': .6})
        self.assertEqual(build_targets(target(unknown))['frozen_security_ids'], ['AAA'])
        stale = sleeve(checked_at=T0, max_age_days=1, current_weights={'AAA': .6}, records=[event(action='SELL')])
        self.assertEqual(build_targets(target(stale))['target_weights'], {'AAA': .3})

    def test_inverse_long_only_and_equal_active(self):
        inverse = sleeve('inverse', allocation_policy='active_equal', current_weights={'AAA': 1},
                         records=[event(action='BUY'), event('b', 'BBB', 'SELL'), event('c', 'CCC', 'BUY')])
        result = build_targets(target(inverse))
        self.assertEqual(result['target_weights'], {'BBB': .5})
        self.assertNotIn('CCC', result['target_weights'])

    def test_fresh_source_check_cannot_revive_expired_signal(self):
        old = sleeve('inverse', max_age_days=1, allocation_policy='active_equal',
                     records=[event(action='SELL')])
        result = build_targets(target(old))
        self.assertEqual(result['target_weights'], {})
        self.assertEqual(result['frozen_security_ids'], ['AAA'])

    def test_fresh_signal_can_supersede_expired_economic_event(self):
        old = event(action='SELL')
        fresh = dict(event('new', 'AAA', 'BUY'), event_at=T2, published_at=T2, available_at=T2)
        result = build_targets(target(sleeve(max_age_days=1, records=[old, fresh])))
        self.assertEqual(result['target_weights'], {'AAA': .3})

    def test_bad_clocks_weights_and_identity_rejected(self):
        for bad in [dict(event(), available_at=T0), dict(event(), subject_id='someone_else')]:
            with self.assertRaises(ValueError):
                build_targets(target(sleeve(records=[bad])))
        with self.assertRaises(ValueError):
            build_targets(target(sleeve(budget_weight=1), sleeve(id='two', budget_weight=.1)))

    def test_snapshot_unsupported_currency_rejected(self):
        snapshot = dict(event(), currency='EUR', complete_reported_basket=True, positions=[])
        with self.assertRaisesRegex(ValueError, 'SNAPSHOT_CURRENCY_MISMATCH'):
            build_targets(target(sleeve('snapshot', records=[snapshot])))

    def test_incomplete_snapshot_does_not_liquidate_omitted_holdings(self):
        snapshot = dict(event(), currency='USD', complete_reported_basket=False, positions=[])
        result = build_targets(target(sleeve('snapshot', current_weights={'AAA': 1}, records=[snapshot])))
        self.assertEqual(result['target_weights'], {'AAA': .5})
        self.assertEqual(result['frozen_security_ids'], ['AAA'])

    def test_newest_snapshot_withdrawal_does_not_reuse_older_snapshot(self):
        original = dict(event(), currency='USD', complete_reported_basket=True,
                        positions=[dict(security_id='AAA', asset_type='common_stock', eligible_common=True, market_value=100)])
        newest = dict(original, event_id='new', event_at=T2, published_at=T2, available_at=T2, withdrawn=True)
        result = build_targets(target(sleeve('snapshot', records=[original, newest])))
        self.assertEqual(result['target_weights'], {})

    def test_input_is_not_mutated(self):
        document = target(sleeve(records=[event()]))
        before = copy.deepcopy(document)
        build_targets(document)
        self.assertEqual(document, before)


class FollowerRebalanceTests(unittest.TestCase):
    def test_golden_cash_fees_rounding_scope_and_settlement(self):
        result = rebalance(account())
        self.assertEqual(result['targets']['target_weights'], {'BBB': .5})
        trades = {row['action']: row for row in result['proposals']}
        # Sell only follower's 6 of 10 AAA, $300 minus $1 + 1% cost = $296.
        self.assertEqual(Decimal(trades['SELL']['quantity']), 6)
        self.assertEqual(Decimal(trades['SELL']['estimated_unsettled_proceeds']), 296)
        # $150 spendable, each BBB costs $25.25, plus $1: 5 shares, $127.25.
        self.assertEqual(Decimal(trades['BUY']['quantity']), 5)
        self.assertEqual(Decimal(result['estimated_buy_cash_use']), Decimal('127.25'))
        self.assertEqual(Decimal(result['settled_cash_if_buys_fill']), Decimal('72.75'))
        self.assertEqual(Decimal(result['estimated_new_unsettled_sale_proceeds']), 296)
        self.assertFalse(any(row['security_id'] == 'OUT' for row in result['proposals']))

    def test_no_settled_cash_never_spends_sales_or_receivable(self):
        document = account()
        document.update(settled_cash='0', account_nav='800', cash_floor='0')
        result = rebalance(document)
        self.assertEqual([row['action'] for row in result['proposals']], ['SELL'])
        self.assertEqual(Decimal(result['estimated_buy_cash_use']), 0)

    def test_frozen_security_prevents_drift_rebalance(self):
        document = account()
        document['target_document']['sleeves'][0]['source_status'] = 'unknown'
        result = rebalance(document)
        self.assertEqual(result['proposals'], [])

    def test_missing_profile_does_not_liquidate_dormant_follower_position(self):
        document = account()
        document['target_document'] = target(sleeve(records=[]))
        result = rebalance(document)
        self.assertEqual(result['proposals'], [])
        self.assertIn({'security_id': 'AAA', 'reason': 'NO_CURRENT_FOLLOWER_SCOPE_KEEP_EXISTING'}, result['deferred'])

    def test_pending_orders_nav_quote_and_holding_reconciliation(self):
        variants = [dict(open_orders=[{'id': 'pending'}]), dict(account_nav='1001'), dict(holdings_at=T0)]
        for change in variants:
            document = account()
            document.update(change)
            with self.assertRaises(ValueError):
                rebalance(document)
        document = account()
        document['quotes']['AAA']['observed_at'] = T0
        with self.assertRaises(ValueError):
            rebalance(document)

    def test_pro_rata_buy_funding_preserves_floor_with_two_fees(self):
        document = account()
        document['holdings'][0]['follower_quantity'] = '0'
        document['target_document'] = target(sleeve(current_weights={}, records=[event(), event('b', 'BBB')]))
        result = rebalance(document)
        buys = {row['security_id']: Decimal(row['quantity']) for row in result['proposals'] if row['action'] == 'BUY'}
        # Reserve two $1 fees; scale $505 variable cost to $148: 1 AAA and 2 BBB.
        self.assertEqual(buys, {'AAA': Decimal(1), 'BBB': Decimal(2)})
        self.assertEqual(Decimal(result['settled_cash_if_buys_fill']), 97)


if __name__ == '__main__':
    unittest.main()
