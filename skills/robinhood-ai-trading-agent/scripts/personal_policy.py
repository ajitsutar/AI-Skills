"""Validate personal runtime policy fields without silently supplying defaults."""
from risk_engine import dec, positive, nonnegative


def validate_personal_fields(policy):
    if policy["configuration_status"] not in {"draft", "approved"}:
        raise ValueError("Unknown configuration status")
    requirements = policy["requirements"]
    for field in ("core_fundamental_review", "portfolio_lookthrough", "portfolio_covariance"):
        if type(requirements[field]) is not bool:
            raise ValueError("Policy requirement must be Boolean: " + field)
    if not requirements["core_fundamental_review"] or not requirements["portfolio_lookthrough"]:
        raise ValueError("Personal entries require core research and portfolio look-through")
    for field in ("fund_holdings_max_age_days", "candidate_max_age_days", "garch_max_age_hours",
                  "garch_target_period_volatility", "garch_periods_per_year"):
        positive(requirements[field])
    if set(requirements["garch_by_sleeve"]) != set(policy["sleeves"]) or any(
            type(v) is not bool for v in requirements["garch_by_sleeve"].values()):
        raise ValueError("GARCH requirement must be explicit for each sleeve")
    if set(requirements["strategy_validation_required_modes"]) != {"approval", "bounded_autonomous"}:
        raise ValueError("Live tactical modes require retained strategy validation")
    for field in ("stress_loss_fraction", "portfolio_annualized_volatility"):
        if not 0 < dec(policy["limits"][field]) <= 1:
            raise ValueError("Invalid personal portfolio risk cap")
    if not policy["stress_scenarios"]:
        raise ValueError("Explicit portfolio stress scenarios required")
    for scenario in policy["stress_scenarios"]:
        if not scenario["name"] or not -1 <= dec(scenario["default_shock"]) <= 0:
            raise ValueError("A downside default stress shock is required")
        for shock in list(scenario.get("symbols", {}).values()) + list(scenario.get("sectors", {}).values()):
            if not -1 <= dec(shock) <= 0:
                raise ValueError("Stress overrides must be downside shocks")
    if set(policy["event_policies"]) != set(policy["sleeves"]):
        raise ValueError("Explicit event policy required for every sleeve")
    for sleeve, events in policy["event_policies"].items():
        if events["scope"] not in {"entry_only", "holding_window"}:
            raise ValueError("Unknown event policy scope")
        if sleeve != "core" and events["scope"] != "holding_window":
            raise ValueError("Tactical events must cover the holding window")
        if not events["blocked_kinds"] or events["exchange"] != "XNYS":
            raise ValueError("Explicit event types and supported US session calendar required")
        positive(events["max_age_seconds"])
        for field in ("before_sessions", "after_sessions"):
            if type(events[field]) is not int or not 0 <= events[field] <= 60:
                raise ValueError("Invalid event session window")
    if not isinstance(policy["strategy_registry"], dict):
        raise ValueError("Strategy registry required")
    if set(policy["live_validated_setups"]) - set(policy["allowed_setups"]):
        raise ValueError("Promoted setups must be in the allowlist")
    if set(policy["autonomous_sleeves"]) - set(policy["sleeves"]):
        raise ValueError("Unknown autonomous sleeve")
