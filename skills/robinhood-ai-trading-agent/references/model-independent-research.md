# Model-independent research and reproducible selection

The same prompt alone does not fix data access, cutoff, sector membership,
normalization judgments or strategy preferences. Aim for the same picks by sharing
those inputs and using deterministic selection. Do not force models to agree by
concealing evidence differences or lowering the research gates.

## Reuse a run contract

Resolve the prompt into a saved mandate: universe snapshot, actual hold, risk
preference, instruments, event exposure and requested output count (if any).
Choose the existing profile matching that mandate before fetching candidates.
Reuse its version, field definitions, numeric filters, score scales and weights,
source priority, freshness limits and tie-break rule. Do not tune these after
seeing names or inherit a prior chat's preferred stocks. An intentional change
creates a new profile version and a new run, with its reason recorded.

If no suitable profile exists, define one transparently from the user's mandate
and retain it for subsequent runs. Label that initial strategy choice provisional;
do not claim model-independent picks until the profile and common snapshot are
fixed. The bundled numeric example is a schema demonstration, not a recommended
or validated strategy. There is no universal top-N, score weighting or P/E filter.

Use the same dated security identifiers and constituent file, source precedence,
field basis (e.g. NTM versus company fiscal year), corporate-action treatment and
retrieval cutoff across models. Retain exact numeric observations and source
references, including URLs and publication/retrieval times. Never replace missing
facts with an LLM's estimated quality score. Preserve primary-source normalization
calculations and disagreements as explicit judgments. A changed data entitlement
or unsupported provider becomes a disclosed data gap, not a silent substitution.

## Deterministic selection

`screen_review.py` invokes `deterministic_rank.py` when `ranking_spec` and
`ranking_inputs` are present. Use this path for ranked stock-pick requests.
See [the complete fictional example](../examples/fictional-ranked-screen.json).

The numeric snapshot contains every declared-universe symbol exactly once,
including explicit missing-data rows. The helper excludes missing/stale/future
observations, applies declared numeric filters, clips each metric to its saved
low/high scale, reverses lower-is-better metrics and sums decimal-weighted scores.
Weights sum exactly to one. Sort is score descending then exact symbol ascending.
Optional group caps and the user's requested count are deterministic; never fill
a quota by promoting an ineligible name. Each selection/exclusion has a reason.

The returned `discovery_order` is the order for primary review. Persist the
`review_queue` and source attempts when work is incomplete. Do not let each model
choose a different convenient subset. Unreviewed contenders above the last selected
name keep a requested final report incomplete. If fewer than the requested count
qualify, remaining contenders need review or an explicit incomplete report.

Only evidenced candidates with clear event status and complete primary/horizon
declarations can be selected. Eligible is the default allowed status. Speculative
requires an explicitly selected aggressive profile and remains labeled Speculative;
Watch/Reject/Event-blocked never become buy picks through a high score. For a
speculative research comparison use `report.kind=screened_hypotheses`, not an
Eligible label. Final `report.ranked_symbols` must equal the computed list in order.
Scores are ranking preferences, not return predictions or probabilities.

Day trading keeps the existing registered signal parameters, exact bar snapshot,
strategy implementation hash, event/quote freshness and risk gates. Compare the
same signal implementation on the same bars; do not route an intraday request
through the fundamental ranking helper. A swing or decade-long thesis uses its
own saved profile and resolved horizon. Research reproducibility creates no live
execution or background-monitoring authority.

## Portable bundles and completion

From the skill directory, write outputs outside the installed skill:

```text
python scripts/screen_review.py path/to/input.json --strict-final
python scripts/research_bundle.py create path/to/input.json path/to/run.bundle.json --strict-final
python scripts/research_bundle.py verify path/to/run.bundle.json --strict-final
python scripts/research_bundle.py compare path/to/first.bundle.json path/to/second.bundle.json
```

Use `report.stage=final` for completed records and `draft` while collecting inputs.
Omit strict mode when deliberately saving a partial checkpoint. Completion is
for the declared scope, not evidence of investment merit. Even a complete record
may contain only Watch candidates. A deliberately partial universe cannot support
an index-wide ranking claim. Legacy records without a numeric profile are labeled
NOT_CONFIGURED for ranking and do not acquire a repeatability guarantee.

Bundles include all supplied candidate inputs, full derived results, canonical
input/result hashes, skill version, source hashes and relevant dependency versions.
Verification recomputes results and rejects mismatched inputs, altered output or a
different implementation environment. It never imports code from the bundle or
follows linked files. Save cited source snapshots/calculation workbooks separately
when needed to reproduce the upstream research; they are not automatically copied.
Keep account identifiers, credentials and private routing out of research inputs.
Hashes detect changed artifacts but cannot authenticate the author or truth of facts.

`compare` identifies differences in universe, horizon, methodology, numeric
profile/snapshot, candidate judgments, report and implementation. Record model,
settings and tool entitlements as run context, never as scoring features. Identical
frozen inputs/rules/judgments yield identical picks; fresh runs and unresolved
judgments can legitimately differ. Run `verify` separately: comparison alone does
not establish that either bundle's output actually replays.

## Holding-period cash benchmark

`horizon_review.terminal_scenarios.cash_benchmark` contains:

- `instrument`, `observed_at`, positive `max_age_seconds`, and `evidence`.
- Exact resolved `entry_at` and `exit_at`; `instrument_maturity_at` when applicable.
- `basis`: `holding_period_return`, `annual_effective` or `annual_simple`;
  `rate_or_return` is a decimal fraction, not a percentage-point number.
- Annual rates require `day_count`: `ACT/365F` or `ACT/360`.
- `methodology` describes the source's yield convention, costs and conversion.
- `horizon_adjustment_evidence` when maturity differs/is absent: explain rollover
  assumptions for shorter instruments, early-sale price risk for longer ones, or
  floating/no-interest cash. A quoted bill discount yield needs conversion before
  treating it as a simple/effective investment return. Do not extrapolate today's
  short rate for years without labeling that assumption; use alternative rate
  scenarios where material. No broker cash yield is implied.

The helper checks observation age against the research cutoff, not the replay
date. It calculates simple or effective accrual for the exact elapsed interval,
or retains an explicitly modeled holding-period return. Missing/stale/unsupported
benchmarks produce null excess-over-cash and an unresolved horizon review, while
preserving valid stock-scenario arithmetic. A legacy bare cash percentage cannot
certify a comparison. If both old and structured returns are supplied, they must
agree. `arithmetic_valid` never establishes valuation evidence quality: preserve
the EPS/FCF period and normalization bridge, terminal multiple or other numerical
model, distributions and costs in case inputs, assumptions and evidence.
