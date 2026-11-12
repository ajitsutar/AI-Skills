# Market flow, positioning and squeeze evidence

`scripts/market_flow.py` exposes three pure functions: `analyze(document)`,
`positioning(document)` and `squeeze(document)`. They consume the common
[market-source envelope](market-sources.md), call `market_sources.normalize`,
and return JSON-compatible research diagnostics with `execution_authorized: false`.
They do not acquire data, read accounts, identify a trader, place orders or
implement a paid vendor connection. Use relevant free sources first; optional
user-provided paid access remains governed by [source access](source-access.md).

The synthetic input [market-flow-synthetic.json](../examples/market-flow-synthetic.json)
works for all three functions. Its prices, sources, issuers, volumes and thresholds
are fictional. Unit fixtures are software regressions, not campaign comparisons,
prospective performance or calibrated squeeze probabilities.

## Retain the information actually available

Each record needs an explicit availability timestamp, source declaration and
payload. Unknown availability cannot be used at a decision cutoff. A first
retrieval snapshot supports availability at retrieval, not proof of earlier
publication. Measurement dates and settlement dates remain date-only; do not
invent midnight. Trade, bar-end, quote and borrow observation times require
timezone-aware timestamps. Completed observations cannot be later than their
record's availability or the requested `as_of`.

Use common envelope `action: replace` or `action: cancel` plus `supersedes` for
revisions. Only a revision available by `as_of` can change the active evidence;
later corrections must not rewrite an earlier decision. Revision availability
must follow its target strictly; equal timestamps leave ordering unresolved.
Preserve the earlier
record and the correction trail. Convert feed-specific cancel/correction codes
explicitly before analysis. A trade marked `status: corrected` needs a replace
envelope; unsupported feed statuses are unusable. Identical repeated print IDs
are deduplicated only inside the same ticker/feed. Conflicting payloads for the
same active feed/print identity remain unusable until explicitly revised.

`comparison_group` declares an actual comparable filter, including relevant
session/market, trade conditions and adjustment conventions. It is not proof
that those choices are appropriate. Analyze feeds separately: an exchange feed,
consolidated tape, broker view and FINRA subset can overlap. The helpers never
sum those populations into a market total. Preserve missing and excluded data;
neither is zero activity. All original envelopes remain in `evidence`.

## Analyze actual prints and price/volume context

Trade payload fields:

| Field | Meaning |
|---|---|
| `feed_id`, `trade_id` | Declared feed and feed-local print identity |
| `event_at`, `quantity`, `price` | Exact event time, positive share quantity and positive price |
| `quantity_unit`, `currency` | `shares` and the stated price/notional currency |
| `role`, `comparison_group` | `current` or `baseline`, and comparable print filter |
| `issuer_id`, `share_class` | Stable declared identifiers; needed for cross-tool squeeze matching |
| `bid`, `ask`, `quote_at` | Optional complete quote context in the same currency/share units |

For each current print, quantity and notional percentiles use only retained
baseline prints with an earlier event time and the same ticker, issuer/class,
feed, currency, unit and comparison group. The inclusive empirical rank is
`100 * count(baseline value <= current value) / N`; ties are explicit. The output
retains all baseline IDs and `N`. No actual baseline means an unknown percentile.
The rank describes that supplied sample, not a population tail probability.

Spread is `ask - bid`, spread basis points are
`10000 * (ask - bid) / ((ask + bid) / 2)`, and quote age is trade time minus
quote time. Crossed or future quotes are unusable. `execution_location` can
describe a print relative to a quote, including a locked quote. It does not
establish the aggressor, investor identity, buy-to-open/sell-to-close intent or
whether separate prints were one order. Those fields remain `UNKNOWN`.

Optional `settings.print_percentile_threshold` (0–100) marks an uncalibrated
caller-selected quantity-rank flag. Optional `settings.max_quote_age_seconds`
marks quotes stale under that declared limit. There are no default size or
freshness cutoffs. Inspect quote age, source coverage and sample adequacy.

Cumulative bar payloads use:

```json
{
  "bar_type": "cumulative", "feed_id": "declared-feed",
  "start_at": "2026-11-11T14:30:00Z", "end_at": "2026-11-11T15:30:00Z",
  "session_id": "2026-11-11", "role": "current",
  "volume": 900, "volume_unit": "shares", "volume_basis": "unadjusted",
  "currency": "USD", "comparison_group": "regular_first_hour",
  "issuer_id": "fictional-issuer-1", "share_class": "A",
  "start_price": 100, "end_price": 106,
  "price_basis": "unadjusted_close", "benchmark_record_id": "benchmark"
}
```

Baseline bars use `role: baseline`, a different session ID, and a prior
nonoverlapping interval. Relative volume is current cumulative shares divided
by the arithmetic mean of supplied prior-session cumulative shares at exactly
the same elapsed interval and supplied start/end time-of-day including offset,
with the same feed, identity, currency, volume unit,
volume basis and comparison group. Keep baseline IDs/session count. Ambiguous
duplicate sessions are not pooled. A zero baseline denominator leaves the ratio
unknown; no full-day volume is extrapolated from an intraday interval.
Supply cumulative intervals from the actual declared session origin, not rolling
windows. Matching duration alone is insufficient. Across timezone/DST changes,
unmatched clock representations stay outside the baseline; this helper does not
invent an exchange-calendar conversion or assume a rolling hour is opening volume.

A linked `role: benchmark` bar supplies positive `start_price`/`end_price` over
the identical timestamp interval, same currency and declared `price_basis`.
Its share volume can be absent. Own return is `100 * (end/start - 1)`;
benchmark-relative return subtracts benchmark return, in percentage points.
Different windows or price bases do not yield a relative return. This difference
does not establish causality, risk adjustment or strategy alpha.

## Separate positions from daily short-sale flow

`positioning` returns separate `short_interest`, `borrow`, `short_sale_volume`
and `failures_to_deliver` lists. It does not merge them into a synthetic short
position. [FINRA's explanation](https://www.finra.org/investors/insights/short-interest)
distinguishes short positions measured at reporting snapshots from daily short
transactions. Measurement/settlement, publication and actual first availability
are separate clocks. A dated reported position is not a live position.

Short-interest payloads use `short_interest_shares`, `settlement_date` for
official snapshots (or `measurement_date` for an estimate), `measure_basis`
(`official_reported` or `vendor_estimate`), `measurement_scope`, `issuer_id`,
`share_class` and `adjustment_basis`. Basis labels are source declarations.
Do not relabel estimates as official. Provider-supplied `average_daily_volume`
and parser field `reported_days_to_cover` (legacy supplied alias `days_to_cover`)
remain separately labeled reported fields; conflicting alias values are retained
and the headline stays unknown rather than choosing one. The helper does
not pretend to reproduce their unprovided definitions or windows.

For a mechanical percent-float calculation, explicitly link `float_record_id`
to an eligible float record with `float_shares > 0`, `share_basis: float`,
`effective_date`, `measure_basis`, identical issuer/class and identical nonempty
`adjustment_basis`. Effective date must not follow the SI measurement date.
The formula is `100 * short shares / float shares`. A later diluted float cannot
be backfilled into the earlier position. Review float age, float definition,
estimate status, offerings, conversions, stock loans and corporate actions.

For a recomputed ADV, link `adv_record_ids` to eligible daily bars with
`bar_type: daily_volume`, `session_date`, `volume`, `volume_unit: shares`,
`feed_id`, an explicit `adjustment_basis` matching the SI share basis, and the
same issuer/class. Missing or mismatched share bases retain only the supplied
volume arithmetic mean and an explicitly unreconciled share-count quotient;
comparable ADV and both days-to-cover fields remain unknown. No split adjustment
is guessed. Supply `adv_window.start_date` and
`adv_window.end_date`; the window must end by the SI measurement date. A single
feed and one bar per session are required. ADV is the arithmetic mean over the
supplied sessions; days to cover is short shares divided by that ADV. The
window, record IDs, sample count and coverage remain explicit.

`adv_window.expected_sessions`, when supplied, declares the expected unique
calendar dates. Only an exact match produces `days_to_cover`; absent/incomplete
coverage leaves that headline unknown and retains the computable
`conditional_days_to_cover` over supplied sessions. A supplied expected calendar
is not independently verified. Zero ADV cannot produce a finite days-to-cover
ratio. This ratio is a historical liquidity comparison, not a deadline,
compulsory covering schedule or guarantee of available execution liquidity.

Borrow payloads use an exact `observed_at`, `provider` and `provider_scope`, with
optional `fee_rate_annual_percent`, `shares_available` and `utilization_percent`.
Zero availability and zero utilization are valid observations; absent fields
stay unknown. An annual fee/rebate may be signed; utilization is 0–100 and
share availability nonnegative. Fees, utilization and availability are not
averaged across providers or converted into market-wide scarcity. A screen
does not supply a locate, borrow approval or executable lending quote.

Short-sale-volume payloads use `trade_date`, `short_volume`,
`short_exempt_volume` (optional), `total_volume`, `volume_unit: shares`, `market`
and `coverage`. Fractional share volumes remain fractional. The reported ratio
is `short_volume / total_volume`; short-exempt volume is already inside short
volume and is never added a second time. [FINRA's data page](https://www.finra.org/finra-data/browse-catalog/short-sale-volume-data)
describes the reporting-facility coverage. A subset ratio is not a market-wide
ratio, open short interest, investor intent or net change in bearish positions.

FTD records retain `settlement_date`, `quantity` and `balance_semantics`.
[SEC's data explanation](https://www.sec.gov/data/foiadocsfailsdatahtm) describes
outstanding aggregate balances rather than daily new failures. Do not add balances
across dates, infer their age, attribute them wholly to short sales, claim naked
shorting or start an automatic buy-in countdown. Publication delay matters.

## Triage squeeze evidence without claiming confirmation

`squeeze` combines the two diagnostics only under explicit
`settings.squeeze_criteria`:

```json
{
  "min_short_interest_percent_float": 20,
  "min_days_to_cover": 4,
  "min_relative_volume": 3,
  "min_benchmark_relative_return_percent": 2
}
```

These are fictional demonstration thresholds, not recommendations or calibrated
rules. No criteria are installed by default. Unknown metrics cannot satisfy a
criterion. At least one positioning rule, positive short shares, complete
issuer/class and a declared official/estimate basis are required for
`DATED_POSITIONING_CANDIDATE`. If multiple positioning rules are supplied, all
must be met; incomplete ADV cannot satisfy a days-to-cover rule.

`DEVELOPING_PRESSURE_HEURISTIC` additionally requires both declared flow rules,
same-issuer/class current-bar evidence dated no earlier than the SI measurement,
actual relative volume above one and
actual positive benchmark-relative return. Each feed's context stays separate.
Inspect the retained dates, measurement age, sample coverage and borrow/catalyst
evidence. Without this support the result remains a dated candidate or
`INSUFFICIENT_EVIDENCE`. No state means an observed or inevitable short squeeze.

Retrospective SI changes require the same issuer/class, source/provider,
official/estimate basis, measurement scope and adjustment basis. A decline is
`REPORTED_NET_SHORT_REDUCTION`, not observed gross buy-to-cover volume or proof
that covering caused a price increase. Corporate actions, changes in the reporting
population, new shorts and offsetting closures remain possible explanations.

Only a separately supplied `disclosure` with
`event_type: short_covering_disclosure`, exact `event_at`, positive
`covered_shares`, explicit `position_scope`, `issuer_id`, `share_class` and
nonempty `text_evidence` is retained as `RETROSPECTIVE_SOURCE_REPORTED_COVERING`.
This typed input is a caller/source assertion, not authenticated disclosure or
verified trader identity. It never establishes market-wide covering, forced
covering or the cause of a price move. Preserve the actual accessible document
and its scope for analyst review; a headline, price rally or SI decrease cannot
substitute for it.

Public tape alone cannot determine counterparty positions, dealer inventory,
options opening versus closing, or a gamma squeeze. Options volume and open
interest are not a direct dealer-position ledger. No squeeze probabilities,
automatic trade triggers or return promises are produced. Use the diagnostics
to identify evidence to inspect and to design source-bound paper studies, with
spread, slippage, borrow, dilution and gap risk explicitly retained.
