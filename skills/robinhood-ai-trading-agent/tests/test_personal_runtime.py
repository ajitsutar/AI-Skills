"""Fictional full-path integration tests; no broker connection or actual strategy evidence."""
import copy
import json
import sys
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from risk_engine import canonical_hash, timestamp, evaluate
from execution_ledger import ExecutionLedger, GateClosed
from supervised_session import SupervisedSession
from personal_runtime import initialize, doctor, dispatch
from personal_readiness import entry_readiness, projected_positions
from broker_bridge import build_request
from strategy_validation import evaluate_evidence
from signal_review import implementation_hash
from screen_review import REQUIRED_CHECKS
from test_personal_components import capability_fixture


def strategy_fixture():
    return dict(setup='opening_range_breakout', version='unvalidated-baseline-1', data_kind='market',
        input_hashes={'fixture': 'not-real-market-data'}, data_audit_passed=True,
        windows={name:dict(start=f'2025-0{i+1}-01T00:00:00Z', end=f'2025-0{i+1}-28T00:00:00Z')
                 for i,name in enumerate(['development','validation','test','forward_paper'])},
        test_was_used_for_selection=False, variants_tried=['fixture only'], costs_included=True,
        delisted_universe_handled=True, no_lookahead_audit=True, operational_failure_drills_passed=True,
        benchmark='fictional matched exposure', evidence_refs=['fictional-test-only'],
        test_metrics=dict(trades=120,max_drawdown=.02,net_expectancy_per_trade=.1,net_excess_return_vs_matched_benchmark=.01),
        forward_paper_metrics=dict(trades=60,max_drawdown=.02,net_expectancy_per_trade=.1,net_excess_return_vs_matched_benchmark=.01),
        stress_cost_multiplier=2, cost_stress_survived=True)


class PersonalIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.directory = Path(self.temp.name) / 'runtime'
        initialize(self.directory)
        self.policy = json.loads((self.directory/'policy.json').read_text())
        self.policy.update(mode='bounded_autonomous',configuration_status='approved',live_validated_setups=['opening_range_breakout'])
        # This fixture explicitly disables optional covariance; separate tests cover it.
        self.policy['requirements']['portfolio_covariance'] = False
        self.now = timestamp('2026-10-06T14:00:00Z')
        self.snapshot = json.loads((ROOT/'examples/snapshot.json').read_text())
        self.snapshot['quotes']['DEMO'].update(source='official_broker',real_time=True,leveraged_or_inverse=False)
        self.snapshot.update(session_activity_reconciled=True,external_session_order_count=0,external_session_turnover='0',external_setup_entry_counts={})
        self.order = json.loads((ROOT/'examples/order.json').read_text())
        self.order.update(target_price='105.00',setup_version='unvalidated-baseline-1',signal_at=self.now.isoformat())
        caps = capability_fixture()
        caps['checked_at'] = self.now.isoformat()
        caps['account_alias'] = self.order['account_alias']
        advanced = copy.deepcopy(caps['operations']['submit'])
        for field in ('stop_price','target_price'):
            advanced['bindings'][field] = dict(pointer='/order/'+field,type='number')
            advanced['input_schema']['properties'][field] = dict(type='number')
            advanced['input_schema']['required'].append(field)
        advanced['schema_hash'] = canonical_hash(advanced['input_schema'])
        advanced['protection_semantics'] = dict(atomic_with_entry=True,partial_fill_quantity_tracking=True,
                                               mutually_exclusive_exits=True,evidence=['fictional schema test'])
        caps['operations']['advanced_submit'] = advanced
        inputs = dict(order=copy.deepcopy(self.order), private_routing={'account':'fictional-local-route'})
        self.context = dict(snapshot_hash=canonical_hash(self.snapshot),order_hash=canonical_hash(self.order),
            capabilities=caps, session_owner='test-owner',broker_inputs=inputs,
            reviewed_request_hash=build_request(caps,'advanced_submit',inputs,self.now,self.order['account_alias'])['request_hash'],
            events=dict(symbol='DEMO',source='fictional-test-only',coverage_verified=True,checked_at=self.now.isoformat(),
                coverage_start='2026-09-01T00:00:00Z',coverage_end='2026-11-01T00:00:00Z',events=[]),
            protection=[],fund_holdings={},strategy_evidence=strategy_fixture(),
            issuer_mapping_verified=True,new_protection_valid_until='2026-10-06T20:00:00Z',new_protection_evidence=['fictional-test-only'],
            garch=dict(eligible_as_sizing_input=True, data_quality=dict(symbol='DEMO',status='REVIEWED_DECLARATION',bar_interval='1d'),
                last_timestamp='2026-10-05T20:00:00Z',forecast_period_volatility=.01,periods_per_year=252,
                run_specification=dict(horizon=1,csv_sha256='fictional',audit_sha256='fictional')))
        bars=[dict(timestamp=f'2026-10-06T{t}:00Z',open=99,high=99.9,low=98,close=99.8,volume=1000)
              for t in ['13:35','13:40','13:45','13:50','13:55','14:00']]
        bars[-1].update(high=100,close=100,volume=2000)
        self.context['signal_evidence']=dict(symbol='DEMO',data_kind='market',audit_passed=True,
            source='fictional-test-only',bars=bars,bars_hash=canonical_hash(bars))
        self.context['strategy_evidence'].update(implementation_sha256=implementation_hash(),
            parameters_hash=canonical_hash(self.policy['strategy_registry']['opening_range_breakout']['signal_parameters']))
        self.policy['strategy_registry']['opening_range_breakout']['approved_report_hash'] = canonical_hash(self.context['strategy_evidence'])
        self.ledger = ExecutionLedger(self.directory/'execution.db')
        self.session = SupervisedSession(self.directory/'supervised-session.db')
        self.session.start(self.order['account_alias'],'test-owner',canonical_hash(self.policy),
                           '2026-10-06T20:00:00Z','fictional-test-only',now=self.now)
        self.review = dict(order_hash=canonical_hash(self.order),snapshot_hash=canonical_hash(self.snapshot),official_mcp=True,
            accepted=True,supported_order=True,checked_at=self.now.isoformat(),trade_approvals_enabled=False,
            warnings=[],exit_plan_verified=True,readiness_inputs=self.context)

    def tearDown(self):
        self.ledger.close()
        self.session.close()
        self.temp.cleanup()

    def ready(self):
        return entry_readiness(self.policy,self.snapshot,self.order,self.context,self.directory,
                               evaluate(self.policy,self.snapshot,self.order,self.now),self.now)

    def authorize(self,permissions=None):
        self.ledger.authorize(dict(id='test-grant',kind='mandate',policy_hash=canonical_hash(self.policy),
            account_alias=self.order['account_alias'],starts_at='2026-10-06T13:00:00Z',expires_at='2026-10-06T20:00:00Z',
            human_authorization_ref='fictional-test-only',permissions=permissions or []))

    def cancellation(self,role='entry'):
        self.snapshot['open_orders']=[dict(local_ref='pending-demo',symbol='DEMO',sleeve='intraday',
            side='buy' if role=='entry' else 'sell',role=role,status='open',remaining_quantity='2')]
        caps=copy.deepcopy(self.context['capabilities'])
        schema=dict(type='object',properties={'account':{'type':'string'},'order_id':{'type':'string'}},
                    required=['account','order_id'],additionalProperties=False)
        caps['operations']['cancel']=dict(tool_name='fictional_cancel',input_schema=schema,schema_hash=canonical_hash(schema),
            bindings={'account':dict(pointer='/private_routing/account',type='string'),
                      'order_id':dict(pointer='/private_routing/broker_order_id',type='string')})
        inputs=dict(target_ref='pending-demo',private_routing=dict(account='fixture',broker_order_id='fixture-order'))
        action=dict(id='cancel-test',target_ref='pending-demo',symbol='DEMO',sleeve='intraday',role=role,
                    account_alias=self.order['account_alias'])
        review=dict(snapshot_hash=canonical_hash(self.snapshot),official_mcp=True,accepted=True,
            trade_approvals_enabled=False,checked_at=self.now.isoformat(),warnings=[],capabilities=caps,broker_inputs=inputs,
            session_owner='test-owner',target_identity_verified=True,
            reviewed_request_hash=build_request(caps,'cancel',inputs,self.now,action['account_alias'])['request_hash'])
        return action,review

    def test_cancel_requires_explicit_role_permission(self):
        self.authorize()
        action,review=self.cancellation()
        with self.assertRaisesRegex(GateClosed,'CANCELLATION_OUTSIDE_MANDATE'):
            self.ledger.claim_cancel(self.policy,self.snapshot,action,review,'test-grant',self.now)

    def test_cancel_ack_does_not_release_reservation_or_authorize_retry(self):
        self.authorize(['cancel_entries'])
        action,review=self.cancellation()
        self.assertTrue(self.ledger.claim_cancel(self.policy,self.snapshot,action,review,'test-grant',self.now)['may_submit_once'])
        self.ledger.reconcile_cancel(action['id'],'CANCEL_PENDING','fictional-evidence',self.now)
        self.assertEqual(len(self.ledger.unresolved_cancellations()),1)
        with self.assertRaisesRegex(GateClosed,'UNRESOLVED_PRIOR_CANCELLATION'):
            self.ledger.claim_cancel(self.policy,self.snapshot,action,review,'test-grant',self.now)
        self.ledger.reconcile_cancel(action['id'],'CANCELLED','fictional-evidence',self.now)
        self.assertFalse(self.ledger.unresolved_cancellations())
        self.snapshot['open_orders']=[]
        with self.assertRaisesRegex(GateClosed,'REFRESH_BROKER_SNAPSHOT_AFTER_CANCELLATION'):
            self.ledger.claim(self.policy,self.snapshot,self.order,self.review,'test-grant',self.now)

    def test_protection_cancel_needs_gap_handoff_plan(self):
        self.authorize(['cancel_protection_for_reduction'])
        action,review=self.cancellation('protection')
        review['reduction_plan']=dict(symbol='DEMO',sleeve='intraday',purpose='reduce_owned_position',
            human_handoff_ref='fictional-test-only',gap_risk_acknowledged=False)
        with self.assertRaisesRegex(GateClosed,'PROTECTION_CANCELLATION_NEEDS'):
            self.ledger.claim_cancel(self.policy,self.snapshot,action,review,'test-grant',self.now)

    def test_delayed_quote_and_unverified_product_block(self):
        self.snapshot['quotes']['DEMO'].update(real_time=False,leveraged_or_inverse=True)
        result=self.ready()
        self.assertIn('EXECUTION_QUOTE_SOURCE_OR_TIMELINESS_UNVERIFIED',result['reasons'])
        self.assertIn('LEVERAGED_INVERSE_OR_UNKNOWN_PRODUCT_EXPOSURE',result['reasons'])

    def test_full_claim_and_fill_path_uses_real_readiness_functions(self):
        self.authorize()
        result = self.ledger.claim(self.policy,self.snapshot,self.order,self.review,'test-grant',self.now)
        self.assertTrue(result['may_submit_once'])
        self.assertEqual(result['broker_request_hash'],self.context['reviewed_request_hash'])
        self.ledger.reconcile(self.order['id'],'PARTIALLY_FILLED',5,100,self.now)
        self.ledger.reconcile(self.order['id'],'FILLED',self.order['quantity'],100,self.now)
        self.assertFalse(self.ledger.unresolved())

    def test_missing_readiness_never_claims(self):
        self.authorize()
        del self.review['readiness_inputs']
        with self.assertRaisesRegex(GateClosed,'READINESS_INVALID_OR_MISSING'):
            self.ledger.claim(self.policy,self.snapshot,self.order,self.review,'test-grant',self.now)
        self.assertFalse(self.ledger.unresolved())

    def test_missing_atomic_protection_cannot_open_day_trade(self):
        del self.context['capabilities']['operations']['advanced_submit']
        self.authorize()
        with self.assertRaisesRegex(GateClosed,'READINESS_INVALID_OR_MISSING'):
            self.ledger.claim(self.policy,self.snapshot,self.order,self.review,'test-grant',self.now)

    def test_draft_policy_blocks_even_if_other_evidence_exists(self):
        self.policy['configuration_status']='draft'
        self.assertIn('PERSONAL_POLICY_NOT_APPROVED',self.ready()['reasons'])

    def test_lost_heartbeat_blocks_entry(self):
        self.now += timedelta(seconds=61)
        self.assertIn('HEARTBEAT_LOST',self.ready()['reasons'])

    def test_changed_broker_request_or_snapshot_blocks(self):
        self.context['reviewed_request_hash']='changed'
        self.context['snapshot_hash']='changed'
        reasons=self.ready()['reasons']
        self.assertIn('REVIEWED_BROKER_REQUEST_CHANGED',reasons)
        self.assertIn('READINESS_INPUTS_DO_NOT_MATCH_ORDER_AND_SNAPSHOT',reasons)

    def test_supplied_projected_prices_cannot_understate_risk(self):
        self.context['projected_positions']=[dict(symbol='DEMO',quantity=20,mark=.001)]
        expected=projected_positions(self.snapshot,self.order)
        self.assertEqual(expected[0]['mark'],self.snapshot['quotes']['DEMO']['ask'])

    def test_garch_frequency_mismatch_blocks(self):
        self.context['garch']['data_quality']['bar_interval']='5m'
        self.assertIn('GARCH_HORIZON_FREQUENCY_OR_PROVENANCE_MISMATCH',self.ready()['reasons'])

    def test_volatility_can_reduce_but_not_expand_risk_budget(self):
        self.context['garch']['forecast_period_volatility']=.10
        self.assertIn('GARCH_REDUCED_RISK_BUDGET_EXCEEDED',self.ready()['reasons'])

    def test_unaudited_required_garch_blocks(self):
        self.context['garch']['eligible_as_sizing_input']=False
        self.assertIn('REQUIRED_GARCH_NOT_ELIGIBLE',self.ready()['reasons'])

    def test_event_blackout_blocks_independently_of_quote_green_flag(self):
        self.context['events']['events']=[dict(kind='earnings',earliest_at='2026-10-06T21:00:00Z',
            latest_at='2026-10-06T21:00:00Z',evidence=['fictional-test-only'])]
        self.assertIn('EVENT_BLACKOUT_OVERLAPS_ENTRY_OR_HOLD',self.ready()['reasons'])

    def test_changed_strategy_evidence_requires_new_approval(self):
        self.context['strategy_evidence']['test_metrics']['trades']=121
        self.assertIn('STRATEGY_EVIDENCE_NOT_APPROVED_OR_CRITERIA_FAILED',self.ready()['reasons'])

    def test_supervisor_blocks_with_unprotected_existing_tactical_position(self):
        self.snapshot['positions']=[dict(symbol='OTHER',sleeve='intraday',quantity=1,mark=10,asset_type='equity',
            sector='technology',stop_price=9,exit_by='2026-10-06T19:50:00Z')]
        self.snapshot['cash']='99990'
        self.context['snapshot_hash']=canonical_hash(self.snapshot)
        self.assertIn('SUPERVISOR_HAS_UNRESOLVED_REQUIRED_ACTIONS',self.ready()['reasons'])

    def test_broker_fixed_semantics_cannot_change_time_in_force(self):
        self.context['broker_inputs']['order']['time_in_force']='gtc'
        with self.assertRaisesRegex(ValueError,'fixed semantics conflict'):
            self.ready()

    def test_doctor_reports_initial_paper_and_draft_and_preserves_existing(self):
        report=doctor(self.directory)
        self.assertIn('PAPER_MODE_NO_LIVE_AUTHORITY',report['failures'])
        with self.assertRaises(FileExistsError):
            initialize(self.directory)

    def test_personal_interface_rejects_fake_clock(self):
        with self.assertRaisesRegex(ValueError,'caller-supplied clock'):
            dispatch(self.directory,'claim',{'now':'2000-01-01T00:00:00Z'})

    def test_promotion_rejects_overlap_fictional_data_and_future(self):
        report=strategy_fixture()
        criteria=self.policy['strategy_registry']['opening_range_breakout']['criteria']
        report['data_kind']='fictional'
        report['windows']['forward_paper']['end']='2027-01-01T00:00:00Z'
        result=evaluate_evidence(report,criteria,report['setup'],report['version'],self.now)
        self.assertIn('REAL_MARKET_DATA_EVIDENCE_REQUIRED',result['reasons'])
        self.assertIn('STRATEGY_EVIDENCE_FROM_FUTURE',result['reasons'])

    def test_negative_strategy_criteria_cannot_pass(self):
        criteria=copy.deepcopy(self.policy['strategy_registry']['opening_range_breakout']['criteria'])
        criteria['test_min_trades']=-1
        with self.assertRaisesRegex(ValueError,'Positive integer'):
            evaluate_evidence(strategy_fixture(),criteria,'opening_range_breakout','unvalidated-baseline-1',self.now)

    def test_external_manual_activity_consumes_daily_budget(self):
        self.snapshot['external_session_order_count']=self.policy['limits']['max_orders_per_day']
        self.review['snapshot_hash']=canonical_hash(self.snapshot)
        self.context['snapshot_hash']=canonical_hash(self.snapshot)
        self.authorize()
        with self.assertRaisesRegex(GateClosed,'DAILY_ORDER_LIMIT'):
            self.ledger.claim(self.policy,self.snapshot,self.order,self.review,'test-grant',self.now)

    def test_fill_cannot_silently_violate_limit(self):
        self.authorize()
        self.ledger.claim(self.policy,self.snapshot,self.order,self.review,'test-grant',self.now)
        with self.assertRaisesRegex(GateClosed,'FILL_CONTRADICTS_LIMIT'):
            self.ledger.reconcile(self.order['id'],'FILLED',self.order['quantity'],101,self.now)
        self.assertTrue(self.ledger.unresolved())

    def test_protection_cannot_expire_before_time_exit(self):
        self.context['new_protection_valid_until']='2026-10-06T14:05:00Z'
        self.assertIn('NATIVE_PROTECTION_EXPIRES_BEFORE_PLANNED_EXIT',self.ready()['reasons'])

    def test_legacy_policy_cannot_bypass_personal_gate(self):
        self.policy['schema_version']=2
        self.authorize()
        with self.assertRaisesRegex(GateClosed,'PERSONAL_POLICY_V3_REQUIRED'):
            self.ledger.claim(self.policy,self.snapshot,self.order,self.review,'test-grant',self.now)

    def test_no_actual_breakout_blocks_strategy_named_order(self):
        self.context['signal_evidence']['bars'][-1]['close']=99.8
        self.context['signal_evidence']['bars_hash']=canonical_hash(self.context['signal_evidence']['bars'])
        self.assertIn('NO_CURRENT_REGISTERED_ENTRY_SIGNAL',self.ready()['reasons'])

    def test_signal_cannot_change_stop_to_pass_sizing(self):
        self.order['stop_price']='99.00'
        self.assertIn('ORDER_DIFFERS_FROM_REGISTERED_SIGNAL_ECONOMICS',self.ready()['reasons'])

    def test_signal_future_bar_and_gap_block(self):
        self.context['signal_evidence']['bars'][-1]['timestamp']='2026-10-06T14:05:00Z'
        with self.assertRaisesRegex(ValueError,'unfinished'):
            self.ready()

    def test_second_entry_does_not_reset_one_entry_rule(self):
        self.authorize()
        self.ledger.claim(self.policy,self.snapshot,self.order,self.review,'test-grant',self.now)
        prior=self.order['id']
        self.ledger.reconcile(prior,'CANCELLED',0,now=self.now)
        self.order.update(id='second-entry',signal_id='another-poll')
        self.snapshot['reconciled_through_intent']=prior
        self.context['order_hash']=canonical_hash(self.order)
        self.context['snapshot_hash']=canonical_hash(self.snapshot)
        self.context['broker_inputs']['order']=copy.deepcopy(self.order)
        self.review['order_hash']=canonical_hash(self.order)
        self.review['snapshot_hash']=canonical_hash(self.snapshot)
        with self.assertRaisesRegex(GateClosed,'STRATEGY_SESSION_ENTRY_LIMIT'):
            self.ledger.claim(self.policy,self.snapshot,self.order,self.review,'test-grant',self.now)

    def make_core(self,etf=False):
        self.order.update(sleeve='core',setup='core_rebalance',asset_type='etf' if etf else 'equity')
        self.snapshot['quotes']['DEMO']['asset_type']=self.order['asset_type']
        self.policy['core_targets']={'DEMO':'.10'}
        self.policy['live_validated_setups']=['core_rebalance']
        self.context.update(order_hash=canonical_hash(self.order),snapshot_hash=canonical_hash(self.snapshot),candidate_checked_at=self.now.isoformat())
        self.context['broker_inputs']['order']=copy.deepcopy(self.order)
        self.context['reviewed_request_hash']=build_request(self.context['capabilities'],'submit',self.context['broker_inputs'],
                                                          self.now,self.order['account_alias'])['request_hash']
        self.context['candidate']=dict(symbol='DEMO',checks={k:dict(status='pass',reason='fictional test',evidence=['fixture']) for k in REQUIRED_CHECKS})
        self.context['fund_review']=dict(symbol='DEMO',**{k:dict(status='pass',evidence=['fixture']) for k in
            ['mandate_fit','fees_tracking','structure_liquidity','holdings_concentration']})
        if etf:
            self.context['fund_holdings']={'DEMO':dict(as_of=self.now.isoformat(),evidence=['fixture'],holdings=[
                dict(symbol='UNDERLYING',asset_type='equity',sector='technology',fraction=1)])}
        self.review.update(order_hash=canonical_hash(self.order),snapshot_hash=canonical_hash(self.snapshot))
        self.session.stop(self.order['account_alias'],'test-owner',dict(disposition='flat',evidence_ref='fictional-test-only'),self.now)
        self.session.start(self.order['account_alias'],'test-owner',canonical_hash(self.policy),'2026-10-06T20:00:00Z',
                           'fictional-test-only',now=self.now)

    def test_core_stock_has_separate_fundamental_path(self):
        self.make_core()
        self.authorize()
        self.assertTrue(self.ledger.claim(self.policy,self.snapshot,self.order,self.review,'test-grant',self.now)['may_submit_once'])

    def test_core_etf_uses_fund_review_and_lookthrough(self):
        self.make_core(etf=True)
        del self.context['candidate']
        self.assertTrue(self.ready()['ready'],self.ready())
        self.context['fund_review']['fees_tracking']['status']='unresolved'
        self.assertIn('CORE_FUND_REVIEW_INCOMPLETE',self.ready()['reasons'])

    def test_live_core_unknown_fundamentals_block(self):
        self.make_core()
        self.context['candidate']['checks']['balance_sheet']['status']='unresolved'
        self.assertIn('CORE_FUNDAMENTAL_REVIEW_NOT_ELIGIBLE',self.ready()['reasons'])

    def test_personal_covariance_uses_projected_weights_and_caps_risk(self):
        self.policy['requirements']['portfolio_covariance']=True
        self.make_core()
        rows=[dict(timestamp=(self.now-timedelta(days=60-i)).isoformat(),return_value=(i%3-1)*.01) for i in range(60)]
        for row in rows: row['return']=row.pop('return_value')
        self.context['portfolio_returns']=dict(data_kind='market',audit_passed=True,input_hashes={'fixture':'fictional-only'},
            return_definition='daily_simple_total_return',returns={'DEMO':rows})
        result=self.ready()
        self.assertTrue(result['ready'],result)
        self.assertGreater(result['evidence']['covariance']['annualized_volatility'],0)
        self.policy['limits']['portfolio_annualized_volatility']='0.0001'
        self.assertIn('PORTFOLIO_VOLATILITY_CAP',self.ready()['reasons'])


if __name__=='__main__':
    unittest.main()
