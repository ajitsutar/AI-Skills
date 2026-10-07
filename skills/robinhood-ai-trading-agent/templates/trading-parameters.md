# Trading parameters worksheet

This is an unapproved worksheet. personal-policy.example.json initializes personal context in draft/paper mode. Its example values and symbols are not permission.

## Policy mapping

- Objective, horizon, liquidity requirements and benchmark:
- Core/swing/intraday capital caps and cash floor:
- Core target weights and drift bands:
- Allowed symbols/assets and excluded exposures:
- Allowed research/paper setups:
- Strategy versions with completed live-promotion evidence (empty until promotion):
- Per-trade planned loss and total open stop risk:
- Per-stock/ETF/sector limits and broader correlation review:
- Daily/weekly loss and drawdown breakers:
- Maximum positions, orders per session and gross daily turnover:
- Quote/account freshness, spread, liquidity and price-deviation limits:
- Round-trip slippage and fees:
- GARCH overlay: assess by default; record any explicit user disablement, baseline
  model, price basis/frequency, training/holdout sizes and annualization factor.
  Specify whether a valid overlay is required before a tactical proposal may proceed:
- Entry cutoff, stop/invalidation, target and time exit:
- Earnings/macro event exclusions:
- Tax/lot/wash-sale constraints:
- Actual session calendar and settled-cash source:

## Execution design

- Deployment context: personal; optional learning interlock for offline labs.
- Current mode: paper.
- Personal live mode, if explicitly approved: approval or bounded_autonomous.
- Per-order mode binds each exact order and review.
- Bounded mode binds the full policy and mandate until expiry; compliant orders do
  not need repetitive approval. Broker-mandated approvals still apply.
- Native atomic protection, partial-fill coverage and supervised time-exit procedure:
- Host failure/heartbeat procedure and human handoff:
- Permitted cancellations/risk reductions:
- Mandate start/expiry, revocation and human authorization reference:

Normalize approved values into policy.json before any personal live execution.
The supplied risk engine supports unlevered long-only whole-share equities/ETFs.
Do not enable unsupported instruments by changing prose or a Boolean.

See autonomous-mandate.md for the concrete approval worksheet. Follow references/personal-setup.md for personal connection, capability discovery and activation. Installation alone creates no authority.
