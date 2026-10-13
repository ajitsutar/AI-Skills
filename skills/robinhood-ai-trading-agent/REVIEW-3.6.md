ARCHIVAL RECORD — historical results and implementation only.

This file is not current setup guidance or execution policy. Previous
execution gates described below are retired. The current skill imposes
zero execution gates; research findings are advisory. Consult SKILL.md and references/execution-handoff.md.

---

# Shared strategy release review

Version 3.6.0, October 9, 2026.

## Problem and implemented behavior

The previous version could replay an already supplied profile, but allowed each
model to invent a provisional strategy for a fresh prompt. Different screens
therefore returned different lists even with the same skill. The new default for
fundamental rankings is **vqm-fundamental 1.0.0**, with equal Value, Quality and
Momentum families and fixed accounting, peer, cutoff and missing-data conventions.
S&P 500 remains configurable; the output count comes from the request.

- A shared snapshot contains point-in-time primary facts, provider and taxonomy
  identifiers, issuer/class mappings, source hashes and audited return history.
- Factors and ranking are derived in code. Score overrides and alternate default
  weights are rejected; selected names retain the existing evidence/event gates.
- Bank, insurer, other-financial and equity-REIT adapters avoid applying ordinary
  enterprise-value ratios to incompatible balance sheets. Signed yields preserve
  loss makers where denominators remain meaningful.
- Strong Buy is unavailable. Eligible, numeric rank, valuation assumptions and
  calibrated forecast confidence remain separate. No measured alpha is claimed.
- Benchmark-aware long-only allocation requires separately supplied calibration,
  aligned covariance and explicit issuer/sector/theme/turnover/liquidity limits.
  An infeasible allocation does not relax constraints or submit trades.
- Fixed-hold cohorts and monthly rebalancing have separate preregistered validation
  requirements. Arbitrary holding clocks remain supported; fundamental, swing and
  intraday routes retain separate alpha and operational validation requirements.

## Review findings fixed

Independent forward testing found three boundary errors: a rolling intraday latest
entry could exceed its buffered exit; a candidate could certify a newer primary
financial quarter than the factors actually used; and a financial source could
claim publication before the asserted period ended. All now reject inconsistent
inputs and have regressions. Follow-up review fixed prior-balance publication
chronology and preflight dependency reporting, including separation of optional
volatility tooling from the default research path.

Research retrieval time is now distinguished from the information cutoff. Archived
primary/event reconstruction requires explicit as-of evidence, and future source
publication is rejected. Live event-gate freshness is unchanged. Exported bundles
also copy their inputs, preventing later caller mutation from corrupting the
saved record. Profile files join implementation hashes and bundle comparisons.

Cross-model report review highlighted additional requirements: do not replace an
index screen with a convenient analyst list or rank names by checks completed;
keep all scenario entry prices on the same close; review distributions for every
issuer; and reject stale cash comparisons. Common shocks stay stress tests rather
than company-specific terminal valuations. A research preflight reports missing
components without requiring an account or silently replacing the strategy.

## Validation and practical limits

See [the validation record](VALIDATION-3.6.txt). Fictional tests establish software
behavior and input parity, not returns or recommendation quality. The independent
review exercised research, cross-model replay and one-, seven- and 37-year clocks.

No historical point-in-time database, live provider entitlement, alpha calibration
or Strong Buy classifier is shipped. Source hashes do not authenticate data.
Accounting extraction and research judgments still require reviewed evidence;
identical fresh prose prompts do not guarantee identical data. Share the frozen
snapshot and evidence register to reproduce picks, and inspect differences before
claiming model agreement. Floating-point optimizer weights have numeric tolerance;
the Decimal stock ranking has deterministic order.

No brokerage was connected, trade placed, account policy promoted or schedule
created for this release. Existing settlement reserves, execution approvals,
protected exits and supervised-session requirements remain in force.
