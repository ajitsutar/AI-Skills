import copy
import sys
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from risk_engine import canonical_hash, timestamp
from trading_calendar import session_for, audit_timestamps, event_gate
from research_data import point_in_time_fact
from research_analytics import normalization_bridge, peer_comparisons, analyst_targets, valuation_scenarios, free_cash_flow, estimate_revisions
from portfolio_analytics import lookthrough, covariance_risk, stress
from accounting_tools import cash_reconciliation, time_weighted_return, select_lots, wash_sale_review
from broker_bridge import build_request, redact_request, receipt, OFFICIAL_ENDPOINT
from supervised_session import SupervisedSession, SessionClosed, actions_needed


class CalendarTests(unittest.TestCase):
    def test_holiday_and_early_close(self):
        self.assertFalse(session_for("2026-11-26T16:00:00Z")["is_trading_day"])
        self.assertEqual(timestamp(session_for("2026-11-27T16:00:00Z")["close"]).hour, 18)

    def test_dst_changes_utc_open(self):
        self.assertEqual(timestamp(session_for("2026-03-06T16:00:00Z")["open"]).hour, 14)
        self.assertEqual(timestamp(session_for("2026-03-09T16:00:00Z")["open"]).hour, 13)

    def test_missing_session_is_not_a_complete_history(self):
        result = audit_timestamps(["2026-03-06T21:00:00Z"], "2026-03-06", "2026-03-09")
        self.assertFalse(result["complete"])
        self.assertEqual(len(result["missing"]), 1)

    def test_intraday_checks_completed_bars_only(self):
        result = audit_timestamps(["2026-03-09T13:35:00Z", "2026-03-09T13:40:00Z"],
            "2026-03-09", "2026-03-09", 5, "2026-03-09T13:42:00Z")
        self.assertTrue(result["complete"])

    def test_event_blackout_uses_sessions_across_weekend(self):
        now = timestamp("2026-03-06T15:00:00Z")
        document = {"symbol": "DEMO", "source": "fictional calendar", "coverage_verified": True,
            "checked_at": now.isoformat(), "coverage_start": "2026-03-01T00:00:00Z",
            "coverage_end": "2026-03-31T23:59:00Z", "events": [{"kind": "earnings",
            "earliest_at": "2026-03-09T12:00:00Z", "latest_at": "2026-03-09T12:00:00Z", "evidence": ["fixture"]}]}
        policy = {"before_sessions": 1, "after_sessions": 0, "max_age_seconds": 3600,
                  "blocked_kinds": ["earnings"], "exchange": "XNYS"}
        self.assertFalse(event_gate(document, "DEMO", policy, now)["clear"])
        document["events"] = []
        self.assertTrue(event_gate(document, "DEMO", policy, now)["clear"])
        document["coverage_verified"] = False
        self.assertFalse(event_gate(document, "DEMO", policy, now)["clear"])

    def test_unknown_future_coverage_and_stale_calendar_block(self):
        now = timestamp("2026-10-07T16:00:00Z")
        document = {"symbol": "DEMO", "source": "fixture", "coverage_verified": True,
            "checked_at": "2026-10-06T12:00:00Z", "coverage_start": "2026-10-01T00:00:00Z",
            "coverage_end": now.isoformat(), "events": []}
        policy = {"before_sessions": 2, "after_sessions": 1, "max_age_seconds": 3600, "blocked_kinds": ["earnings"]}
        result = event_gate(document, "DEMO", policy, now)
        self.assertIn("EVENT_CALENDAR_STALE_OR_FUTURE", result["reasons"])
        self.assertIn("EVENT_COVERAGE_INCOMPLETE", result["reasons"])


class ResearchAnalyticsTests(unittest.TestCase):
    def test_fcf_does_not_call_sbc_a_cash_outflow(self):
        result=free_cash_flow(100,30,10,[], 'FY2026')
        self.assertEqual(result['reported_fcf'],70)
        self.assertEqual(result['sbc_adjusted_owner_earnings_sensitivity'],60)

    def test_negative_eps_revisions_use_absolute_change(self):
        rows=[dict(contributor='A',metric='EPS',fiscal_period='FY2027',unit='USD/share',
                   published_at=t,value=v,evidence=['fixture']) for t,v in
              [('2026-06-01T12:00:00Z',-2),('2026-10-01T12:00:00Z',-1)]]
        result=estimate_revisions(rows,'2026-10-07T16:00:00Z','EPS','FY2027','USD/share')
        self.assertEqual(result['matched_revisions'][0]['absolute_change'],1)
        self.assertIsNone(result['matched_revisions'][0]['percentage_change'])

    def test_peer_comparison_does_not_mix_fiscal_periods(self):
        rows=[dict(symbol=s,issuer_id=s,peer_group='same',evidence=['fixture'],
                   metrics={'pe':dict(value=v,basis='GAAP',period=p)})
              for s,v,p in [('A',10,'FY2026'),('B',20,'FY2027'),('C',30,'FY2027')]]
        self.assertIsNone(peer_comparisons(rows,minimum_peers=2)['rows'][0]['comparisons']['pe']['peer_median'])
    def test_normalization_keeps_realization_taxes_and_cash_costs_visible(self):
        result = normalization_bridge(100, [{"amount": 40, "tax_basis": "pre_tax", "tax_rate": .25,
            "realization_fraction": .5, "cash_effect_in_period": -8, "period": "FY2027",
            "reason": "fictional synergies", "evidence": ["fixture"]}], "FY2027")
        self.assertEqual(result["normalized_after_tax"], 115)
        self.assertEqual(result["separate_cash_effect"], -8)

    def test_dilution_reduces_per_share_scenario(self):
        s = {"name": "base", "years": 3, "annual_earnings_growth": .1,
             "annual_share_count_growth": 0, "discount_rate": .1, "exit_pe": 10}
        before = valuation_scenarios(10, 100, 100, [s])["scenarios"][0]["terminal_eps"]
        s["annual_share_count_growth"] = .1
        self.assertLess(valuation_scenarios(10, 100, 100, [s])["scenarios"][0]["terminal_eps"], before)

    def test_peers_do_not_mix_basis_or_double_count_share_classes(self):
        rows = []
        for symbol, issuer, value, basis in (("A", "1", 10, "GAAP"), ("A.B", "1", 11, "GAAP"),
            ("B", "2", 20, "GAAP"), ("C", "3", 30, "GAAP"), ("D", "4", 1, "adjusted")):
            rows.append({"symbol": symbol, "issuer_id": issuer, "peer_group": "same-industry",
                "evidence": ["fixture"], "metrics": {"pe": {"value": value, "basis": basis, "period": "TTM"}}})
        result = peer_comparisons(rows)["rows"]
        self.assertEqual(result[0]["comparisons"]["pe"]["peer_median"], 20)
        self.assertEqual(result[0]["comparisons"]["pe"]["peer_count"], 3)
        self.assertIsNone(result[-1]["comparisons"]["pe"]["peer_median"])

    def test_analysts_use_latest_per_firm_and_ignore_future(self):
        rows = [{"firm": f, "target": value, "published_at": when, "currency": "USD",
                 "horizon_months": 12, "evidence": ["fixture"]}
                for f, value, when in (("A", 100, "2026-06-01T12:00:00Z"), ("A", 120, "2026-10-01T12:00:00Z"),
                   ("B", 80, "2026-10-01T12:00:00Z"), ("C", 1000, "2026-12-01T12:00:00Z"))]
        result = analyst_targets(rows, "2026-10-07T16:00:00Z", "USD")
        self.assertEqual(result["count"], 2)
        self.assertEqual(result["median"], 100)
        self.assertAlmostEqual(result["same_firm_target_revisions"][0]["change"], .2)

    def test_sec_fact_cannot_use_later_restatement(self):
        body = {"facts": {"us-gaap": {"NetIncomeLoss": {"units": {"USD": [
            {"end": "2025-12-31", "filed": "2026-02-01", "val": 100},
            {"end": "2025-12-31", "filed": "2026-08-01", "val": 20}]}}}}}
        self.assertEqual(point_in_time_fact(body, "us-gaap", "NetIncomeLoss", "USD", "2026-03-01", end="2025-12-31")["val"], 100)


class PortfolioAnalyticsTests(unittest.TestCase):
    def test_fund_cash_is_explicit_and_share_classes_share_issuer_cap(self):
        positions=[dict(symbol='A',issuer_id='same-company',quantity=1,mark=100,asset_type='equity',sector='tech'),
                   dict(symbol='ETF',quantity=1,mark=100,asset_type='etf',sector='fund')]
        funds={'ETF':dict(as_of='2026-10-07T12:00:00Z',evidence=['fixture'],holdings=[
            dict(symbol='A.B',issuer_id='same-company',fraction=.9,sector='tech',asset_type='equity'),
            dict(symbol='USD',fraction=.1,asset_type='cash')])}
        result=lookthrough(positions,250,funds)
        self.assertEqual(result['issuer_exposure']['same-company'],190)
        self.assertEqual(result['embedded_fund_cash'],10)
        self.assertTrue(result['complete_fund_coverage'])

    def test_negative_quantity_and_mark_cannot_create_positive_stress_value(self):
        with self.assertRaisesRegex(ValueError,'Long-only'):
            stress([dict(symbol='A',quantity=-1,mark=-100,sector='tech')],1000,[dict(name='shock',default_shock=-.2)])
    def test_lookthrough_aggregates_direct_and_fund_exposure(self):
        positions = [{"symbol": "A", "quantity": 1, "mark": 100, "asset_type": "equity", "sector": "tech"},
                     {"symbol": "ETF", "quantity": 1, "mark": 100, "asset_type": "etf", "sector": "fund"}]
        funds = {"ETF": {"as_of": "2026-10-07T12:00:00Z", "evidence": ["fixture"],
                 "holdings": [{"symbol": "A", "fraction": .5, "sector": "tech", "asset_type": "equity"}]}}
        result = lookthrough(positions, 250, funds)
        self.assertEqual(result["issuer_exposure"]["A"], 150)
        self.assertEqual(result["unknown_fund_value"], 50)
        self.assertFalse(result["complete_fund_coverage"])

    def test_covariance_catches_date_misalignment_and_reports_components(self):
        rows = [{"timestamp": f"2026-10-0{i+1}T20:00:00Z", "return": r} for i, r in enumerate([.01, -.02, .03])]
        result = covariance_risk({"A": rows, "B": rows}, {"A": .4, "B": .4}, min_observations=3)
        self.assertAlmostEqual(sum(result["component_volatility"].values()), result["annualized_volatility"])
        shifted = copy.deepcopy(rows)
        shifted[-1]["timestamp"] = "2026-10-04T20:00:00Z"
        with self.assertRaisesRegex(ValueError, "Unaligned"):
            covariance_risk({"A": rows, "B": shifted}, {"A": .4, "B": .4}, min_observations=3)

    def test_stress_does_not_assume_stop_limits_loss(self):
        p = [{"symbol": "A", "quantity": 10, "mark": 100, "sector": "tech", "stop_price": 98}]
        result = stress(p, 2000, [{"name": "gap", "default_shock": -.4}])
        self.assertEqual(result["scenarios"][0]["pnl"], -400)

    def test_flow_time_return_removes_large_midperiod_deposit(self):
        result = time_weighted_return(100, "2026-10-01T12:00:00Z", [{"at": "2026-10-02T12:00:00Z",
            "pre_flow_equity": 110, "external_flow": 100, "post_flow_equity": 210}], 231, "2026-10-03T12:00:00Z")
        self.assertAlmostEqual(float(result["time_weighted_return"]), .21)

    def test_cash_duplicate_cannot_inflate_balance(self):
        row = {"id": "deposit", "posted_at": "2026-10-01T12:00:00Z", "amount": 100, "kind": "deposit"}
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            cash_reconciliation(100, [row, row], 300, "2026-10-02T12:00:00Z")

    def test_lot_methods_are_explicit_and_quantity_conserved(self):
        lots = [{"lot_ref": str(i), "symbol": "A", "quantity": 2, "cost_per_share": cost,
                 "acquired_at": f"2026-01-0{i+1}T16:00:00Z"} for i, cost in enumerate([10, 20])]
        self.assertEqual(select_lots(lots, 3, "HIFO")["lots"][0]["lot_ref"], "1")
        with self.assertRaisesRegex(ValueError, "Insufficient"):
            select_lots(lots, 5)

    def test_wash_review_flags_reinvestment_and_never_certifies_tax(self):
        result = wash_sale_review("A", "2026-10-07T16:00:00Z", True, [{"side": "buy", "symbol": "A",
            "at": "2026-09-20T16:00:00Z", "quantity": .1, "local_ref": "dividend-reinvestment"}])
        self.assertEqual(len(result["potential_replacements"]), 1)
        self.assertFalse(result["tax_clearance"])


def capability_fixture():
    schema = {"type": "object", "properties": {"symbol": {"type": "string"}, "side": {"enum": ["buy", "sell"]},
              "quantity": {"type": "integer"}, "price": {"type": "number"}, "account": {"type": "string"}},
              "required": ["symbol", "side", "quantity", "price", "account"], "additionalProperties": False}
    bindings = {"symbol": {"pointer": "/order/symbol", "type": "string"}, "side": {"pointer": "/order/side", "type": "string"},
        "quantity": {"pointer": "/order/quantity", "type": "integer"}, "price": {"pointer": "/order/limit_price", "type": "number"},
        "account": {"pointer": "/private_routing/account", "type": "string"}}
    return {"endpoint": OFFICIAL_ENDPOINT, "account_alias": "demo", "account_routing_verified": True,
        "source": "connected_official_mcp_schema_observation",
        "checked_at": "2026-10-07T16:00:00Z", "operations": {"submit": {"tool_name": "fictional_broker_tool",
        "input_schema": schema, "schema_hash": canonical_hash(schema), "bindings": bindings,
        "fixed_semantics": {k: {"value": v, "evidence": ["fictional fixed-semantics test"]}
                            for k, v in {"order_type": "limit", "time_in_force": "day", "extended_hours": False}.items()}}}}


class BrokerAndSessionTests(unittest.TestCase):
    def test_nested_actual_schema_mapping_and_redaction(self):
        caps=capability_fixture()
        tool=caps['operations']['submit']
        schema=copy.deepcopy(tool['input_schema'])
        bindings=copy.deepcopy(tool['bindings'])
        tool['input_schema']=dict(type='object',properties={'payload':schema},required=['payload'],additionalProperties=False)
        tool['schema_hash']=canonical_hash(tool['input_schema'])
        tool['bindings']={'payload':{'object':bindings}}
        data=dict(order=dict(symbol='DEMO',side='buy',quantity=1,limit_price=100,account_alias='demo',
                             order_type='limit',time_in_force='day',extended_hours=False),private_routing={'account':'private-test-route'})
        prepared=build_request(caps,'submit',data,timestamp(caps['checked_at']),'demo')
        self.assertEqual(prepared['request']['arguments']['payload']['quantity'],1)
        self.assertNotIn('private-test-route',str(redact_request(prepared,caps)))

    def test_schema_failure_does_not_echo_private_account(self):
        caps=capability_fixture()
        caps['operations']['submit']['input_schema']['properties']['account']={'type':'integer'}
        caps['operations']['submit']['schema_hash']=canonical_hash(caps['operations']['submit']['input_schema'])
        data=dict(order=dict(symbol='DEMO',side='buy',quantity=1,limit_price=100,account_alias='demo',
                             order_type='limit',time_in_force='day',extended_hours=False),private_routing={'account':'private-test-route'})
        try:
            build_request(caps,'submit',data,timestamp(caps['checked_at']),'demo')
            self.fail('Schema should reject string account')
        except ValueError as exc:
            self.assertNotIn('private-test-route',str(exc))

    def test_schema_bound_request_keeps_private_routing_out_of_report(self):
        caps = capability_fixture()
        data = {"order": {"symbol": "DEMO", "side": "buy", "quantity": "2", "limit_price": "100.02", "account_alias": "demo",
                          "order_type": "limit", "time_in_force": "day", "extended_hours": False},
                "private_routing": {"account": "fictional-private-route"}}
        result = build_request(caps, "submit", data, timestamp(caps["checked_at"]), "demo")
        self.assertNotIn("fictional-private-route", str(redact_request(result, caps)))
        self.assertFalse(result["execution_authorized"])
        data["order"]["quantity"] = "2.5"
        with self.assertRaisesRegex(ValueError, "Noninteger"):
            build_request(caps, "submit", data, timestamp(caps["checked_at"]), "demo")

    def test_session_cannot_be_stolen_or_silently_revived(self):
        now = timestamp("2026-10-07T16:00:00Z")
        with tempfile.TemporaryDirectory() as folder:
            session = SupervisedSession(Path(folder) / "session.db")
            try:
                session.start("demo", "owner1", "policy", "2026-10-07T19:00:00Z", "fictional human ref", now=now)
                with self.assertRaises(SessionClosed):
                    session.start("demo", "owner2", "policy", "2026-10-07T19:00:00Z", "other", now=now)
                with self.assertRaisesRegex(SessionClosed, "HEARTBEAT_LOST"):
                    session.heartbeat("demo", "owner1", "policy", now + timedelta(seconds=61))
                session.stop("demo", "owner1", {"disposition": "flat", "evidence_ref": "fixture"}, now)
                self.assertFalse(session.status("demo", "owner1", "policy", now)["ready"])
            finally:
                session.close()

    def test_supervisor_flags_time_exit_even_with_protection(self):
        now = timestamp("2026-10-07T19:50:00Z")
        snapshot = {"reconciled": True, "session": {"close": "2026-10-07T20:00:00Z"}}
        position = {"symbol": "A", "sleeve": "intraday", "quantity": 2, "exit_by": now.isoformat(), 'stop_price': 98}
        protection = {"symbol": "A", "sleeve": "intraday", "covered_quantity": 2, "state": "working",
            "native_broker": True, "as_of": now.isoformat(), "protection_ref": "fixture-stop", 'side':'sell',
            'stop_price':98,'expires_at':'2026-10-07T20:00:00Z'}
        result = actions_needed(snapshot, [position], [protection], now)
        self.assertIn("TIME_EXIT_DUE", result["required_actions"][0]["action"])
        self.assertFalse(result["new_entries_permitted_by_supervisor"])


if __name__ == "__main__":
    unittest.main()
