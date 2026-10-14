# Holding-period planning: intraday through decades

Use for any requested holding period or forced exit: minutes/hours, a same-session
day trade, overnight or multi-session swings, arbitrary days/weeks/months, or ten,
twenty or more years. No maximum investment horizon belongs in the skill. First
resolve the clock, then choose the intraday, swing or long-term research route.
A cheap business need not reprice before the exit;
a good short-term setup need not be intrinsically undervalued. Preserve which
question the user asked. There is no prescribed stock count, universal scoring
formula or universal earnings blackout.

All checks here classify research quality and describe risk. They neither permit
nor block an order. Native host and broker tools own execution; the optional
`execution_handoff.py` preserves the requested payload without submitting it.

## Set the clock before selecting names

Record the as-of time, proposed entry, latest acceptable entry, horizon units,
deadline mode, hard exit, early-exit policy and event policy. For an unspecified
"90 days," disclose the working assumption of 90 calendar days from proposed
entry, with risk exits allowed and a fixed end for that research run. Do not
silently equate 90 calendar days, 90 trading sessions and three calendar months.
Research can proceed under disclosed assumptions; identify material conflicts in
the recommendation and preserve the user's actual requested holding period.

Preserve a supplied, supported entry expiry. If none is supplied, record latest
acceptable entry as unknown; do not copy the proposed entry or invent an expiry
to satisfy a helper. In horizon schema version 1, omit `latest_entry_at` or set it
to null. The resolver returns null and `latest_entry_status: UNKNOWN`, while still
calculating the proposed entry's `exit_at`. A supplied timestamp returns
`latest_entry_status: SUPPLIED` and retains the session and chronology checks;
this status means supplied, not independently authenticated. With an unknown
latest entry, `latest_possible_exit_at` is the known fixed deadline for `fixed_end`
and null for `rolling_from_entry`. `calendar_scope: proposed_entry_only` then
limits calendar confirmation to the proposed plan in either mode; it does not
confirm an entry window. A supplied expiry uses `calendar_scope: entry_window`.
Neither unknown expiry nor a resolved clock grants execution authority.

"One day for a day trade" means entry and exit in the same exchange session,
not a 24-hour hold. Overnight one-calendar-day exposure belongs to swing trading.
Normalize fractional periods into exact smaller units (for example 1.5 years to
18 months); do not round away the user's intended deadline. A ten-year thesis
does not imply an order held unattended for ten years. If no hard exit is desired,
record a review horizon and thesis-driven exit rules instead; do not invent a
forced sale just because the user described themselves as a long-term investor.

- **Fixed end:** delaying entry shortens the remaining hold. Keep the original
  anchor/deadline. Reassess whether the thesis can still work before that date.
- **Rolling from fill:** each actual fill starts its own clock. This is a different
  mandate; it cannot satisfy an unchanged cash-needed date by moving that date.
- Count entry as day zero. Calendar months clamp a nonexistent end-of-month date
  to that month's last date. Resolve a nontrading hard deadline to the preceding
  exchange session. Use an explicit exit buffer before its actual close, including
  early closes. The buffer is a planning assumption, not a fill guarantee.
- Distinguish permission to exit early on invalidation from strict buy-and-hold.
  A stop and a strict-hold mandate conflict unless the user resolves the exception.
- If the money must be available for spending, work backward from settlement,
  withdrawals and holidays. Sale date is not cash-available date. If the principal
  must be intact, disclose that an equity allocation cannot assure that outcome
  and compare cash/cash-equivalent alternatives under their own risks and terms.

`scripts/horizon_review.py` resolves the proposed dates through the exchange
calendar, independently or through `screen_review.py`. It covers US equity
research, not a settlement engine or execution scheduler. Units are `same_session`
(value 1), `elapsed_minutes`, `elapsed_hours`, `calendar_days`, `calendar_weeks`,
`calendar_months`, `calendar_years` and `trading_sessions`, with positive integral
values. There is no strategy-specific maximum duration. Elapsed units additionally
require `anchor_at`; date-based units use `anchor_date`. An elapsed deadline outside
trading hours moves to the last available session boundary before it. The exit
buffer applies before that boundary. Python date/calendar-library limits are
technical limits, not investment rules: report an unsupported calculation, never
substitute a shorter hold or claim it ran.

Record `strategy_route` and the evidence-backed `calendar_confirmed_through` date.
Later session dates are explicitly PROVISIONAL and must be refreshed; future
holidays, closures and market rules can change. Recalculate around actual entry,
corporate actions and approaching deadlines. Calendar projections are suitable
for research scenarios, not a claim of verified distant executable dates.

| Route | Decision evidence and monitoring |
|---|---|
| Intraday | Completed-bar setup, current spread/liquidity, session/event checks, invalidation and same-session exit; use signal_review, not the seven-check fundamental screen |
| Swing / dated tactical hold | Within-window price/catalyst mechanism, appropriate fundamental risk review, event exposure, costs, overnight risk and exact exit |
| Long term, including decades | Durable competitive position, reinvestment/owner economics, capital allocation, normalized cash and valuation ranges, portfolio/tax fit, periodic thesis and valuation reviews |

Horizon alone does not validate a strategy. Preserve the user's objectives and
risk mandate. Long-term terminal values need justified growth, reinvestment,
dilution and terminal economics with discounting where comparing present value;
do not extrapolate one quarter or a one-day volatility model through a decade.
Widen uncertainty and use sensitivity analysis instead of spurious price precision.

## Research for the remaining window

Freeze a configurable universe and record the method using
[research-run-methodology.md](research-run-methodology.md). Unspecified ranked
fundamental requests start with [public-vqm-discovery](research-campaign.md),
then primary and horizon review. The [strict filing VQM route](shared-default-strategy.md)
is an explicitly requested alternative. Swing/intraday requests retain
their separate within-window price/catalyst or completed-bar profile. Arbitrary
horizon support does not imply a validated alpha model for every interval. Define any technical rule before choosing
names and retain its actual inputs; a hindsight chart narrative is not a tested
signal. Do not reuse the daily trend baseline as a validated live strategy.

For a fundamental stock shortlist, retain the sector-appropriate earnings/cash,
balance-sheet and value-trap review. The latest public earnings release may precede
the next 10-Q: review it alongside the latest available filing and reconciliation.
Confirm what was public at the run cutoff. A vendor's latest row is not proof that
it represents the latest announced quarter. If a period mismatch is found, refresh
all affected candidates and log the change. Do not bury it as an unimportant feed
difference. Separate GAAP, adjusted, pro-forma, discontinued-operation and merger
figures. Banks, REITs and cyclicals need their own suitable metrics.

Do useful primary research before concluding "all Watch." Attempt issuer IR/filings,
material reconciliation and balance-sheet checks for the leading candidates; keep
a record of sources attempted, findings and concrete access/evidence gaps. A
research stop rule is not a license to stop at ratios when the user asked for a
completed assessment. Conversely, missing material facts remain unresolved: never
fill a requested count by making unsupported pass judgments. Scale review depth
to the actual thesis; "full forensic audit" is not the default requirement.

Each finalist needs these five evidenced conclusions in addition to the ordinary
fundamental checks:

1. **Thesis timing:** why value or price could be realized before this exit. Separate
   a dated catalyst from its uncertain outcome and from what expectations already
   price in. A scheduled earnings report is not automatically bullish. A thesis
   without a dated event can qualify if its price/revision mechanism is supported;
   acknowledge that it may not occur on time. After-exit catalysts do not support
   this hold unless an evidenced earlier expectation change is the actual thesis.
2. **Terminal valuation:** downside/base/upside outcomes at this exact exit, with
   an earnings/cash/multiple or other suitable bridge. These are conditional
   scenarios, not today's intrinsic value or analyst price targets. Show sensitivity
   to expectations, revisions, multiple contraction, dilution and dividends.
3. **Downside and liquidity:** plausible gap/event/cycle losses, market/sector
   stress, spread/slippage and forced-sale liquidity. A stop does not cap losses
   through an overnight gap, halt or absent buyer. Do not annualize a short sample
   or infer profit probability from low beta or daily GARCH.
4. **Portfolio fit:** combined holdings and pending exposure, issuer/sector/theme
   concentration, correlated earnings dates and affordability. Several good
   candidates can form a poor combined portfolio. Compare no action and a suitable
   cash benchmark over the same interval, net of comparable costs.
5. **Exit plan:** entry validity/expiry, invalidation, allowed early exits, hard exit,
   event decisions, review triggers and who handles open positions when the chat
   is closed. Never extend a loser into a core holding or reset the clock silently.

Optional analysts and GARCH remain supplementary. Twelve-month targets cannot be
divided by four to estimate a three-month return. Historical win rates need their
sample, selection method and untouched evaluation; model probabilities need an
appropriate horizon, calibration evidence and uncertainty. Otherwise report
scenario ranges, not "maximum probability," "high confidence" or a synthetic
expected return. `horizon_review` deliberately does not validate probability fields.

## Events: entry and holding are separate decisions

Use issuer IR/release calendars first, then exchange/regulator/court sources as
appropriate. Retain source, retrieval/checked time, time zone, confirmed/estimated
status and the entire credible uncertainty window. Resolve conflicts explicitly.
An earnings release and its conference call can occur on different days. One does
not confirm the other's time. State when event information was last checked.

Define blackouts in exchange sessions, with start and release/review conditions:

- `entry_only`: identify proposed entries inside the research blackout and
  separately disclose events crossed while holding, including overnight risk.
- `entry_and_hold`: flag any overlap between the planned hold and the research
  blackout. Compare a later entry against the same deadline and updated thesis.
  These settings affect the research comparison, not native broker execution.

For `coverage_mode: full_hold`, cover the whole holding window plus the policy's
lookback/lookahead buffers.
Unknown event coverage is not clear; "no event found" is not evidence that none is
expected. Unknown dates require a credible range and later refresh. Do not impose
a blanket 30-day exclusion because another agent used it. A review flag is not an
automatic sell instruction or an execution prerequisite. Preserve the declared
research scope when comparing runs; no local policy activation or reapproval is
needed to pass a requested order to native host tools.

For long or otherwise unforecastable horizons, use `coverage_mode: rolling_review`
with `scope: entry_only`, an explicit sourced near-term event window,
`review_schedule.next_review_at`, a cadence and material-event triggers. Evaluate
known near-term events and recurring future earnings/regulatory/cycle exposure in
the risk scenarios. Future dates beyond that window remain UNASSESSED, not clear.
Do not demand a verified ten-year earnings calendar or mark an otherwise completed
long-term thesis Watch merely because those dates have not been announced. A
research mandate excluding certain events cannot be certified through a rolling
window without applicable coverage. Report that unresolved research conflict.
Record calendar refresh, quarterly
filing/thesis checks and periodic portfolio reviews; create automation only if asked.

## Output and offline validation

Lead with the assumed entry/exit and how many candidates actually qualify. Separate
Eligible comparisons from Watch research priorities, Speculative and Reject.
Show each finalist's decisive thesis, within-window driver, current primary period,
scenario range net of costs, event exposure, principal failure mode and next action.
Retain source links and the run record. An event warning must not hide a failed
fundamental thesis, and a complete schema must not be described as audited facts.

Use [holding-period-review.md](../templates/holding-period-review.md) and the runnable
[fictional-horizon-screen.json](../examples/fictional-horizon-screen.json):

```text
python scripts/screen_review.py examples/fictional-horizon-screen.json
python scripts/horizon_review.py examples/fictional-horizon-screen.json
```

Fundamental manifests with an explicit holding clock declare `decision_mode: fixed_horizon`, a versioned `horizon`, a
`run_spec`, and each candidate's `primary_review` and `horizon_review`. The helper
enforces proposed dates, source-period consistency, event scope and same-exit
scenario arithmetic. Evidence is supplied by the caller and is not fetched or
authenticated. A long-term review with no forced exit uses `decision_mode: long_term`.
Intraday research uses the standalone clock plus the registered signal workflow;
`screen_review` intentionally refuses to make intraday setups pass a fundamental
screen. The clock does not rank stocks or verify economics. Legacy manifests are
explicitly `legacy_unspecified`; they do not certify a fixed-horizon review.

When passing a flexible thesis-review request to `research_handoff`, use
`horizon_mode: flexible_review`, `forced_exit: false`, and an explicit
`comparison_at` for valuation scenarios. The helper retains the existing
fixed-horizon analytical checks; its internal `exit_at` comparison alias is not a
sell instruction. `horizon_mode: fixed_exit` is reserved for a user-specified hard
deadline. See [research-handoff.md](research-handoff.md) for the exact adapter.

## Execution boundary

This workflow prepares recommendations and analytical records for any holding
period. It does not submit orders, schedule exits, monitor positions after the
chat closes, or require strategy promotion. Research gaps, event warnings and
price changes are advisory findings. Native host and broker tools handle the
user's requested transaction with their own available capabilities and permissions.
The optional `execution_handoff.py` preserves that request; it supplies neither
execution permission nor an execution veto.

## Benchmark and scenario evidence

For structured terminal scenarios use the `cash_benchmark` contract in
[model-independent-research.md](model-independent-research.md). The helper computes
the cash return for the exact entry/exit interval, checks its observation date,
and requires explicit rollover/early-sale/floating-rate assumptions when maturity
differs. A legacy bare percentage is unverified; excess-over-cash is then null and
the horizon review cannot become Eligible. Scenario `arithmetic_valid` is separate
from `valuation_evidence_status=DECLARED_NOT_VERIFIED`; neither authenticates a
valuation. Preserve EPS/FCF period, GAAP/adjusted bridge, terminal multiple and
other model inputs alongside assumptions/evidence, including downside cases.
Use the resolved buffered `exit_at` for both equity scenarios and the cash
comparison, with the same proposed entry. A calculation through the session close
is a separately labeled sensitivity, with its own matching equity/cash interval;
it cannot replace the primary buffered-exit comparison. Preserve the original
timestamps and values of supplied terminal assumptions. If they refer to another
time, report the mismatch as unresolved, or explicitly label and justify a
conditional assumption that transfers them to the resolved exit while retaining
their source time. Changing a timestamp alone does not establish that an earnings,
multiple, dividend or terminal-price assumption applies at the new time.

Preserve year/month uncertainty for catalysts such as contract renewals. Use the
existing `evidence.event_window` operation to compare the entire supplied range
with the holding window. For example, a year-only renewal in the exit year can
overlap a January exit; it is neither definitely after exit nor confirmed before
exit. Do not replace the year with an invented day. Calendar-date comparisons
and exact timestamp comparisons have different precision; supply explicit
offsets only when supported, and retain unresolved mixed-precision diagnostics.
The shared event policy is validated even for an empty candidate list. Put cadence,
evidence and next_review_at under `horizon.review_schedule`, not event_policy.
