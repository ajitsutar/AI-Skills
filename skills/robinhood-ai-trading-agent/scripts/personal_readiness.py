"""Mandatory v3 personal entry checks, rerun inside the durable claim transaction.

Inputs are retained broker/research evidence. Local JSON cannot authenticate its
author; Codex/broker permissions and actual human authorization remain necessary.
"""
from __future__ import annotations

from pathlib import Path

from broker_bridge import build_request
from portfolio_analytics import lookthrough, stress, covariance_risk
from risk_engine import canonical_hash, dec, timestamp
from screen_review import assess_candidate
from strategy_validation import evaluate_evidence
from supervised_session import SupervisedSession, actions_needed
from trading_calendar import event_gate, session_for
from signal_review import evaluate_signal


def projected_positions(snapshot, order):
    """Derive exposure from the reconciled snapshot; never trust supplied marks.

    Pending sales do not release exposure. Pending buys use reservation prices;
    new buys use the greater of the limit and observed ask. Aggregate by sleeve.
    """
    result = {}

    def add(record, quantity, mark):
        key = (record["symbol"], record["sleeve"])
        quantity, mark = dec(quantity), dec(mark)
        if quantity < 0 or mark <= 0:
            raise ValueError("Invalid projected exposure")
        if quantity == 0:
            return
        existing = result.get(key)
        if existing:
            if any(existing[field] != record[field] for field in ("sector", "asset_type")):
                raise ValueError("Inconsistent instrument metadata in broker snapshot")
            total = dec(existing["quantity"]) + quantity
            existing["mark"] = str((dec(existing["quantity"]) * dec(existing["mark"]) + quantity * mark) / total)
            existing["quantity"] = str(total)
        else:
            result[key] = {"symbol": record["symbol"], "sleeve": record["sleeve"],
                           "sector": record["sector"], "asset_type": record["asset_type"],
                           "quantity": str(quantity), "mark": str(mark),
                           'issuer_id': record.get('issuer_id',record['symbol'])}

    for position in snapshot["positions"]:
        add(position, position["quantity"], position["mark"])
    for pending in snapshot["open_orders"]:
        if pending["side"] == "buy":
            add(pending, pending["remaining_quantity"], pending["reservation_price"])
    quote = snapshot["quotes"][order["symbol"]]
    add(dict(order, sector=quote["sector"], issuer_id=quote.get('issuer_id',order['symbol'])), order["quantity"], max(dec(order["limit_price"]), dec(quote["ask"])))
    return list(result.values())


def entry_readiness(policy, snapshot, order, context, runtime_directory, risk_verdict, now):
    reasons, evidence = [], {}
    if policy.get("configuration_status") != "approved":
        reasons.append("PERSONAL_POLICY_NOT_APPROVED")
    if context.get("snapshot_hash") != canonical_hash(snapshot) or context.get("order_hash") != canonical_hash(order):
        reasons.append("READINESS_INPUTS_DO_NOT_MATCH_ORDER_AND_SNAPSHOT")
    if context["capabilities"].get("account_routing_verified") is not True:
        reasons.append("ACCOUNT_ROUTING_NOT_VERIFIED")
    session_path = Path(runtime_directory) / "supervised-session.db"
    if not session_path.is_file():
        reasons.append("NO_SUPERVISED_SESSION_DATABASE")
    else:
        manager = SupervisedSession(session_path)
        try:
            session = manager.status(order["account_alias"], context["session_owner"], canonical_hash(policy), now)
            evidence["session"] = session
            reasons.extend(session["reasons"])
        finally:
            manager.close()
    actual_session = session_for(now)
    if (actual_session.get("is_trading_day") is not True
            or timestamp(actual_session["open"]) != timestamp(snapshot["session"]["open"])
            or timestamp(actual_session["close"]) != timestamp(snapshot["session"]["close"])):
        reasons.append("BROKER_AND_CALENDAR_SESSION_MISMATCH")
    operation = "advanced_submit" if order["side"] == "buy" and order["sleeve"] != "core" else "submit"
    prepared = build_request(context["capabilities"], operation, context["broker_inputs"], now, order["account_alias"])
    if canonical_hash(context["broker_inputs"]["order"]) != canonical_hash(order):
        reasons.append("BROKER_ARGUMENTS_DO_NOT_BIND_EXACT_ORDER")
    if prepared["request_hash"] != context["reviewed_request_hash"]:
        reasons.append("REVIEWED_BROKER_REQUEST_CHANGED")
    evidence["request_hash"] = prepared["request_hash"]
    evidence["capability_hash"] = prepared["capability_hash"]
    evidence["operation"] = operation
    quote = snapshot['quotes'][order['symbol']]
    if quote.get('source') != 'official_broker' or quote.get('real_time') is not True:
        reasons.append('EXECUTION_QUOTE_SOURCE_OR_TIMELINESS_UNVERIFIED')
    if order["side"] == "sell":
        # Reductions do not require bullish research, event clearance or volatility.
        return {"ready": not reasons, "reasons": sorted(set(reasons)), "evidence": evidence}
    if quote.get('leveraged_or_inverse') is not False:
        reasons.append('LEVERAGED_INVERSE_OR_UNKNOWN_PRODUCT_EXPOSURE')
    if order['sleeve'] != 'core':
        if (not context.get('new_protection_evidence')
                or timestamp(context['new_protection_valid_until']) < timestamp(order['exit_by'])):
            reasons.append('NATIVE_PROTECTION_EXPIRES_BEFORE_PLANNED_EXIT')
    event_policy = policy["event_policies"][order["sleeve"]]
    event_end = now if event_policy["scope"] == "entry_only" else timestamp(order["exit_by"])
    events = event_gate(context["events"], order["symbol"], event_policy, now, event_end)
    evidence["events"] = events
    reasons.extend(events["reasons"])
    supervisor = actions_needed(snapshot, snapshot["positions"], context["protection"], now)
    if not supervisor["new_entries_permitted_by_supervisor"]:
        reasons.append("SUPERVISOR_HAS_UNRESOLVED_REQUIRED_ACTIONS")
    evidence["supervisor"] = supervisor
    if order["sleeve"] == "core" and policy["requirements"]["core_fundamental_review"]:
        if order['asset_type'] == 'etf':
            fund_review = context['fund_review']
            if fund_review['symbol'] != order['symbol'] or any(
                fund_review[field].get('status') != 'pass' or not fund_review[field].get('evidence')
                for field in ('mandate_fit','fees_tracking','structure_liquidity','holdings_concentration')):
                reasons.append('CORE_FUND_REVIEW_INCOMPLETE')
            evidence['fund_review'] = fund_review
        else:
            candidate = assess_candidate(context["candidate"])
            if candidate["symbol"] != order["symbol"] or candidate["fundamental_status"] != "Eligible":
                reasons.append("CORE_FUNDAMENTAL_REVIEW_NOT_ELIGIBLE")
            evidence["candidate"] = candidate
        if not 0 <= (now - timestamp(context["candidate_checked_at"])).total_seconds() <= policy["requirements"]["candidate_max_age_days"] * 86400:
            reasons.append("CORE_RESEARCH_STALE_OR_FUTURE")
    if policy["requirements"]["portfolio_lookthrough"]:
        if context.get('issuer_mapping_verified') is not True:
            reasons.append('ISSUER_AND_SHARE_CLASS_MAPPING_UNVERIFIED')
        projected = projected_positions(snapshot, order)
        look = lookthrough(projected, snapshot["equity"], context["fund_holdings"])
        if not look["complete_fund_coverage"] or look["unknown_sector_value"] > 0:
            reasons.append("INCOMPLETE_PORTFOLIO_LOOKTHROUGH")
        for fund in look["fund_sources"].values():
            if not 0 <= (now - timestamp(fund["as_of"])).total_seconds() <= policy["requirements"]["fund_holdings_max_age_days"] * 86400:
                reasons.append("STALE_OR_FUTURE_FUND_HOLDINGS")
        if any(dec(value) / dec(snapshot["equity"]) > dec(policy["limits"]["single_stock"])
               for name, value in look["issuer_exposure"].items() if not name.startswith("UNKNOWN:")):
            reasons.append("LOOKTHROUGH_ISSUER_CAP")
        if any(dec(value) / dec(snapshot["equity"]) > dec(policy["limits"]["sector"])
               for value in look["sector_exposure"].values()):
            reasons.append("LOOKTHROUGH_SECTOR_CAP")
        evidence["lookthrough"] = look
        scenarios = stress(projected, snapshot["equity"], policy["stress_scenarios"])
        if any(-dec(row["equity_fraction"]) > dec(policy["limits"]["stress_loss_fraction"]) for row in scenarios["scenarios"]):
            reasons.append("STRESS_LOSS_LIMIT")
        evidence["stress"] = scenarios
        if policy["requirements"]["portfolio_covariance"]:
            weights = {}
            for position in projected:
                name = position["symbol"]
                weights[name] = str(dec(weights.get(name, 0)) + dec(position["quantity"]) * dec(position["mark"]) / dec(snapshot["equity"]))
            history = context["portfolio_returns"]
            if history["data_kind"] != "market" or history["audit_passed"] is not True or not history["input_hashes"]:
                reasons.append("PORTFOLIO_RETURNS_NOT_AUDITED")
            for series in history["returns"].values():
                if not 0 <= (now - timestamp(series[-1]["timestamp"])).total_seconds() <= policy["requirements"]["garch_max_age_hours"] * 3600:
                    reasons.append("PORTFOLIO_RETURNS_STALE_OR_FUTURE")
            if history["return_definition"] != "daily_simple_total_return":
                reasons.append("PORTFOLIO_RETURN_BASIS_MISMATCH")
            covariance = covariance_risk(history["returns"], weights, periods_per_year=252)
            if covariance["constant_return_symbols"]:
                reasons.append("CONSTANT_PORTFOLIO_RETURN_SERIES")
            if dec(covariance["annualized_volatility"]) > dec(policy["limits"]["portfolio_annualized_volatility"]):
                reasons.append("PORTFOLIO_VOLATILITY_CAP")
            evidence["covariance"] = covariance
    required_garch = policy["requirements"]["garch_by_sleeve"][order["sleeve"]]
    volatility = context.get("garch")
    if required_garch and (not volatility or volatility.get("eligible_as_sizing_input") is not True):
        reasons.append("REQUIRED_GARCH_NOT_ELIGIBLE")
    if volatility and volatility.get("eligible_as_sizing_input") is True:
        specification = volatility["run_specification"]
        if (dec(volatility["periods_per_year"]) != dec(policy["requirements"]["garch_periods_per_year"])
                or specification["horizon"] != 1 or not specification["csv_sha256"]
                or not specification["audit_sha256"]
                or volatility["data_quality"]["bar_interval"] != policy["requirements"]["garch_bar_interval"]):
            reasons.append("GARCH_HORIZON_FREQUENCY_OR_PROVENANCE_MISMATCH")
        if (volatility["data_quality"].get("symbol") != order["symbol"]
                or volatility["data_quality"].get("status") != "REVIEWED_DECLARATION"):
            reasons.append("GARCH_SECURITY_OR_DATA_AUDIT_MISMATCH")
        if not 0 <= (now - timestamp(volatility["last_timestamp"])).total_seconds() <= policy["requirements"]["garch_max_age_hours"] * 3600:
            reasons.append("GARCH_DATA_STALE_OR_FUTURE")
        if order["sleeve"] != "core":
            target = dec(policy["requirements"]["garch_target_period_volatility"])
            forecast = dec(volatility["forecast_period_volatility"])
            if target <= 0 or forecast <= 0:
                raise ValueError("Positive GARCH sizing volatility required")
            factor = min(dec(1), target / forecast)
            if dec(risk_verdict["metrics"]["planned_loss"]) > dec(snapshot["equity"]) * dec(policy["limits"]["risk_per_trade"]) * factor:
                reasons.append("GARCH_REDUCED_RISK_BUDGET_EXCEEDED")
            evidence["volatility_risk_multiplier"] = str(factor)
    if policy["mode"] in policy["requirements"]["strategy_validation_required_modes"] and order["sleeve"] != "core":
        registered = policy["strategy_registry"][order["setup"]]
        signal_check = evaluate_signal(order,context['signal_evidence'],registered,snapshot,now)
        reasons.extend(signal_check['reasons'])
        if (context['strategy_evidence']['implementation_sha256'] != signal_check['implementation_sha256']
                or context['strategy_evidence']['parameters_hash'] != signal_check['parameters_hash']):
            reasons.append('STRATEGY_VALIDATION_DOES_NOT_MATCH_RUNNING_CODE_AND_PARAMETERS')
        evidence['signal'] = signal_check
        promotion = evaluate_evidence(context["strategy_evidence"], registered["criteria"], order["setup"], registered["version"], now)
        if (not promotion["eligible_for_promotion_review"]
                or promotion["report_hash"] != registered["approved_report_hash"]):
            reasons.append("STRATEGY_EVIDENCE_NOT_APPROVED_OR_CRITERIA_FAILED")
        evidence["promotion"] = promotion
    return {"ready": not reasons, "reasons": sorted(set(reasons)), "evidence": evidence}
