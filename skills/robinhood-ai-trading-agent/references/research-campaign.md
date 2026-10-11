# Reproducible research campaign (v3.8)

Read this first for ranked fundamental stock requests, including “top N buys.”
Intraday retains its registered signal/bar workflow: a daily fundamental queue is
not a day-trade entry signal. The requested count and holding period are configurable.

## Two distinct outputs

**Official research candidates:** execute the public acquisition/scoring helpers
below. Publish `research_candidates` in its exact order with coverage, gaps and
the `VENDOR_APPROXIMATION_NOT_FILING_VERIFIED` label. Models cannot replace these
members with preferred, familiar or already-reviewed stocks. These are research
priorities, not Eligible, Strong Buy or validated investment recommendations.

**Investment eligibility:** use the existing primary, normalization, event,
exact-horizon and risk procedures in queue order. The strict `vqm-fundamental`
schema-2 route remains unchanged and is reported separately. Vendor facts cannot
satisfy primary evidence by relabeling. If none clears the bar, say so. A candidate
overlap pass is not agreement on ten recommended buys.

The public queue is a named, shipped strategy stage, not an improvised fallback.
It retains the corporate/financial Value/Quality/Momentum formulas and equal family
weights, with a distinct vendor accounting/taxonomy contract. Banks and equity
REITs without specialized capital/FFO inputs remain explicitly unranked. Attempt
every universe member, including missing-data cases; report the scored subset.
Do not claim a complete index-wide investment ranking when some members are missing.

## Executable workflow

Choose a unique output-directory path outside the skill, but do not create that
directory: the collector creates it and rejects an existing path. Create its
parent if needed and save the exact user prompt in a separate UTF-8 file outside
the output directory, without previous picks, scores or model output. Use the actual timezone-bearing
decision time. Both models must resolve to the same last completed XNYS close,
universe, horizon descriptor and exact prompt. The contract is saved before fetching.

```text
python scripts/research_preflight.py
python scripts/public_research_fetch.py --output /outside-skill/run-A --decision-at <timezone-bearing-now> --hold P1Y --prompt-file /outside-skill/prompt.txt
python scripts/public_research.py rank /outside-skill/run-A/snapshot.json /outside-skill/run-A/result.bundle.json --count <user-count>
python scripts/public_research.py verify /outside-skill/run-A/result.bundle.json
```

`P1Y` is an example, not a fixed default or a maximum. Resolve the actual holding
clock through `horizon_review.py`; the public helper only records the descriptor.
No output count is hard-coded. Other universes can use `--universe` with a dated
JSON object containing `universe_id`, `source`, and `rows` of `symbol`, `issuer_id`,
`name`. Read `profiles/public-vqm-discovery-v1.json` before using its results.

The adapter gets fresh constituents, an official SPY fund-proxy check, and each
member's Yahoo quarterly statements, quotes and history. Obtain estimates and
numeric EPS trends during the ordered candidate review; neither enters this score.
Review membership differences, fund residuals, provider errors and actions.
Raw Close is used for price/ADV, Adj Close for 252/21 momentum, with auto_adjust
and repair both false. Market cap/EV are explicitly vendor proxies. Publication
timing and restatements are not certified: this is not a historical backtest.
Use current internet acquisition, not an old Claude test or cached ranking.

If dependencies/provider access fail, retain the incomplete run and exact error.
Do not fabricate data, infer missing zeros or invent a replacement score. A source
or profile change requires a new disclosed contract. Shared-data replay remains
a different test from independently acquiring public data. The adapter spaces
requests and retries a rate limit once after a one-minute backoff. A repeated
limit pauses further requests. Resume this same run later with `--resume`, the
same prompt, hold and decision-close convention. It retries failed components
only and writes a new `retry-NNN/snapshot.json`, preserving the old snapshots.
Rank that new snapshot into a new result file. A pull with an unresolved acquisition
error that could affect ranking cannot pass the overlap test even if its partial
lists happen to match. Financial failures for a security already excluded by a
successful but insufficient price-history response are retained and disclosed but
do not block comparison: no financial value could make that security rankable.
Failed or empty history requests always block. A successfully acquired statement with missing accounting fields remains
an explicit scoring exclusion, distinct from a failed provider request.

## Common review coverage and definitions

Review the computed queue in order, beginning with the requested candidate count.
Keep a coverage register linking each issuer to latest filings/releases, normalized
earnings/cash flow, balance sheet, value traps, analyst evidence, numeric revisions,
events, horizon valuation and risk. Retain sources, periods, calculations and gaps.
`public_research.review_frontier` exposes skipped higher-ranked names. For a separate
eligible comparison, continue down the queue when a candidate fails an evidence
gate. Never silently backfill the official research list or equate unreviewed
companies with rejected investment theses.

Use `scripts/research_report_checks.py` on the report's numeric claims:

- Derive P/E from the displayed price and exact EPS period/basis. Do not call
  vendor forwardPE that quotient. Next fiscal year is not automatically NTM.
- Numeric EPS revisions compare the same fiscal bucket now and 90 days earlier.
  Analyst target changes, ratings and company guidance are separate measures.
  With a nonpositive base, retain the signed change and no percentage.
- Label revenue/EPS/FCF growth and EBITDA/operating/net margins separately.
- Confirm event dates against issuer announcements first, then regulatory sources;
  vendor estimates remain estimates. Retain URL, publication date and checked time.
  New primary confirmation supersedes an estimate for that event.
- For terminal scenarios declare the financial period, accounting basis and
  whether the exit multiple uses trailing/current/forward earnings at exit.
  A later earnings year is not automatically better. Checks validate arithmetic,
  not the economic merit of chosen multiples or cash-flow assumptions.
- If all valuation cases show gains, include a separately justified adverse price
  sensitivity. Lower AFFO/FCF yields mean multiple expansion, not a valuation
  stress. Keep distributions, dilution, leverage and costs explicit; no case is
  a guaranteed floor or an estimated probability without independent evidence.

Narrative discretion belongs in explanations and labeled alternative views. If
the user explicitly requests discretionary final stock selection, comply and
label it separately; it carries no 80% promise. Do not tune the scorer after seeing
either model's picks. “Maximum gain” and “strong recommendation” do not authorize
invented expected returns or unavailable Strong Buy confidence.

## Muse/Codex acceptance test

Give each model the complete skill, exact prompt and common cutoff convention.
Each independently acquires public inputs and executes these same helpers. Keep
the first model's picks hidden until the other has frozen its result. Obtain the
original bundle, acquisition receipts, command/exit evidence and model/version
when available. A repeated ticker list is not proof of execution.

```text
python scripts/public_research.py compare /outside-skill/codex/result.bundle.json /outside-skill/muse/result.bundle.json
```

Comparison replays both bundles, rejects different mandates/universes/profiles,
and requires two complete requested-length unique-issuer lists. Overlap is shared
issuers / requested count, with an acceptance target of 0.80. It reports scores,
exclusions, exact-order agreement and whether the input hashes are identical.
Actual execution/source receipts must establish independent acquisition; different
hashes alone do not. Short or empty lists cannot pass.

Report numerical candidate overlap, agreement on evidence/eligibility decisions,
and investment-performance validation separately. None of these implies the others.
A passing run proves its measured result for that date and contract, not future
80% agreement, predictive accuracy, or ten Strong Buy recommendations.
