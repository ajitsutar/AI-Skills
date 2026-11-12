# Institutional event research pilot

Use this workflow for an explicitly configured, event-driven U.S.-equity paper
pilot, including unusual-flow and short-squeeze hypotheses. It implements a
repeatable research protocol, decision brief and evaluation record. It does not
claim that a real prospective pilot has elapsed, that the research is profitable,
or that a host, broker or data vendor has approved deployment.

The pure operations are `institutional.plan(document)`,
`institutional.brief(document)` and `institutional.evaluate(document)`. Their
implementation is `scripts/institutional_research.py`. They return
`execution_authorized: false`; findings are advisory and do not change execution
policy. The separate journal/capture CLI writes only when explicitly invoked.

## Configure and adopt a pilot

Start with `profiles/event-research-pilot.json`. It is an inactive example
template. Replace `as_of`, records, horizon, reviewer and study choices with the
actual request. Its discovery scope defaults to **all U.S.-listed equities**;
that is the requested search universe, not proof of a complete live feed. An
explicit symbol universe is supported when the user requests it. The bundled
`DEMO` example is fictional and explicitly restricted to its synthetic universe.
Its horizon, portfolio, costs, reviewer and dates are examples, not personal
preferences or mandatory trading rules.

`pilot` contains `id`, `research_question`, `universe`,
`horizon: {label, entry_policy, exit_policy}`, `reviewer: {id, role}` and
`study: {registered_at, start_at, end_at, usefulness_criterion,
workflow_baseline_id}`. `return_baseline_id` may also be supplied for the separate
return comparison. Keep the registered protocol and its exact hash before the
first decision; a later revised protocol gets a new retained ID and parent link.
Missing choices produce `CONFIGURATION_NEEDED`, not invented user preferences.
Registration and time declarations are not authenticated by a pure helper.

Adopt a criterion that a reviewer can actually judge: for example, whether the
brief identified a checkable gap relevant to the decision. Prespecify the manual
or without-tool workflow baseline, which cases belong in the roster, review
timing and how failures, abstentions and abandoned hypotheses are retained.
Prespecify a separate return baseline and cost/holding conventions if returns are
part of the study. Do not tune the criterion or baseline after seeing outcomes.

## Evidence, clocks and coverage

Use the shared envelope in [market sources](market-sources.md): `schema_version`,
`as_of`, `records`, explicit `available_at`, source clocks and unchanged payloads.
The helper calls `market_sources.normalize` and carries its eligibility and
limitations. Date-only availability is unresolved; retrieval now cannot establish
historical publication. Future or unavailable evidence stays retained but does
not enter the decision at that cutoff. Revisions and cancellations follow the
normalizer's cutoff rules. Limits are 10,000 records per document and 50 MiB per
CLI input; larger studies should use explicitly partitioned retained batches.

Free relevant sources are the default acquisition route. Existing paid access is
optional enrichment when it adds useful coverage or freshness. No paid adapter,
subscription or entitlement is created here. `intended_data_uses` and
`readiness_evidence.HF02` retain the actual intended use and review evidence.
Public access is not a commercial, redistribution, storage or AI/cloud license.
Verify the actual terms for those uses; source rights remain declarations here.

## Prepare a decision brief

Supply `event: {id, ticker, decision_at, review_at, horizon?}`. When supplied,
`decision_at` must equal the explicit document `as_of`. Catalyst records, supplied
`hypotheses`, `alternatives`, `invalidation_conditions`, `decision_rationale` and
`disposition` survive into the brief. With no supplied disposition the output is
`RESEARCH_ONLY`. The helper does not convert an unusual print into an order.

Set `include_flow_analysis: true` to compose the pure market-flow,
positioning and squeeze operations from [market flow](market-flow.md).
Explicitly linked eligible benchmark bars are retained as analytical dependencies
even when their ticker is outside the event discovery universe; unrelated
cross-ticker trades and positions are excluded. Retain those benchmarks'
revision ancestry and competing active feed identities, so normalization and
conflict handling cannot change merely because the brief narrowed its universe.
Inactive ancestors remain lifecycle context, not fresh observations. Missing
short-interest, float, borrow or matched volume evidence remains a gap. Prints
cannot identify actual investor intent; public proxies do not establish a
causal squeeze, a probability of profit or a borrow locate.

Optional portfolio context is `portfolio: {as_of, currency: "USD", total_value,
positions: [{ticker, market_value}], completeness, cash?}` and
`proposed_trade: {ticker, side: buy|sell|short|cover, notional, currency: "USD"}`.
Signed exposure before/after uses the full supplied NAV without renormalizing
partial holdings. Future portfolio snapshots are unusable. Cash accessibility,
settlement, margin, issuer overlap, correlations and risk reduction remain
unestablished; this arithmetic is not executable sizing. Supply the actual
portfolio when relevant instead of silently adopting the fictional example.

`cost_contract` is the existing explicit
[trade-cost contract](portfolio-decision-calculations.md); this module calls
`planning_alignment.trade_costs` unchanged. It retains its declared units and
phases. `liquidity` contains `ticker`, `available_at`, `currency: "USD"`,
`average_daily_dollar_volume`, `order_notional`, optional `spread_bps` and a
description of the observed window/basis. The notional/ADV ratio describes scale,
not feasible participation or capacity. Cost/liquidity notional mismatches with
the proposed position are exposed. Review spread, slippage, fees, taxes, halts,
partial fills and, for shorts, borrow fees/availability/recalls separately.

## Retain first responses and exact captures

Create a private directory outside the installed package. The CLI below is a
local recorder: `capture` reads the explicitly supplied file, not the network.
Public acquisition belongs to the separate market-sources command.

```text
python scripts/institutional_research.py plan --input examples/institutional-event-input.json
python scripts/institutional_research.py brief --input examples/institutional-event-input.json
python scripts/institutional_research.py capture --root PRIVATE_ROOT --entry-id source-v1 --input RETAINED_BYTES --available-at EXPLICIT_AWARE_TIMESTAMP --source-id DECLARED_SOURCE
python scripts/institutional_research.py journal --root PRIVATE_ROOT --entry-id case-first-v1 --kind first_response --input FIRST_RESPONSE_FILE
python scripts/institutional_research.py journal --root PRIVATE_ROOT --entry-id case-revision-v2 --parent-id case-first-v1 --kind brief --input REVISED_BRIEF_FILE
python scripts/institutional_research.py recover --root PRIVATE_ROOT --entry-id case-first-v1
```

Journal kinds are protocol, brief, evaluation, challenge, first_response and
failure. Never replace a first response with a cleaned-up later answer. Exact
bytes are SHA256-addressed objects; immutable transaction, entry and commit files
bind their hashes. Repeating an ID with identical stable input is idempotent;
changed content or metadata conflicts. Atomic same-directory hard-link
publication refuses an unsupported filesystem rather than exposing a partially
written final file. Files are fsynced; this does not promise durability through
every OS/filesystem/power failure. Hashes cannot authenticate the source or prove
that an unregistered earlier answer never existed.

A per-root exclusive lock prevents cooperating writers from overlapping. A
normal interruption releases its owned lock; a hard crash may leave it. No age
or PID heuristic automatically breaks locks. After independently confirming that
the owner is stopped, an operator may explicitly run `release-lock --root
PRIVATE_ROOT --expected-lock-sha256 EXACT_HASH --operator-confirmed-stopped`.
The exact old lock bytes are retained under `lock-releases`; a changed hash
refuses removal, including a recheck after archival. An exclusive
`.institutional-release.lock` serializes release operators and blocks cooperating
new journal writers during release. A hard crash during the release itself can
leave this guard; an operator must verify that every release owner is stopped
and retain its exact bytes/hash before manually clearing that guard. Neither
lock is broken automatically. Then `recover` validates the retained transaction/object and
finishes an absent entry/commit without rewriting an existing original. Missing
or corrupt objects and conflicting entries remain errors. Keep private research,
portfolio and response journals outside public releases; do not put credentials
in these records.

## Evaluate usefulness and returns separately

`evaluation` has `registered_at`, `study_start`, `study_end`,
`usefulness_criterion`, `workflow_baseline_id`, optional `return_baseline_id`,
`expected_case_ids` and `cases`. Each case retains `id`, `decision_at`,
`input_record_ids`, and `first_response: {text, sha256, captured_at}`. The helper
checks exact UTF-8 response bytes/hash, declared pre-decision capture and input
eligibility at that decision. For a real prospective study, also reconcile those
declarations to the actual immutable journal and timestamps. Pure evaluation
cannot independently verify an external journal, an honest system clock or an
unseen original answer.

`usefulness` contains `available_at`, `reviewer_id`, `criterion`, `useful` boolean,
`assisted_minutes`, `baseline_minutes` and the prespecified `baseline_id`.
Included reviewer judgments and declared time differences are descriptive;
they are not causal proof that the tool saved time.

Optional `paper_return` contains `period_start`, `period_end`, `available_at`,
`currency: "USD"`, `return_basis: "simple_total_return_decimal"`,
`net_costs_included: true`, `return_decimal`, and `benchmark` with the same fields
plus its prespecified `id`. Only available matched-period, matched-basis net
comparisons enter descriptive excess return. Future outcomes, gross returns,
post-hoc baselines, late inputs and broken first-response retention remain
excluded with their declared originals retained. Overlapping event returns are
not compounded or annualized; no significance, profitability or calibrated
probability is emitted. Missing/extra roster cases remain visible.

`challenge: {reviewer_id, reviewed_at, independence_basis, findings}` retains
objections and their dispositions. Different reviewer labels do not prove
independence. `host` may declare required/available capabilities and acceptance
evidence; missing declared capabilities are shown, without granting rights.
`deployment` retains owner, runbook, monitoring, rollback, data handling and
credential-handling declarations; missing operations remain pending.

## Replay an explicit event scenario after costs

[market-event-workbench.json](../examples/market-event-workbench.json) composes
the fictional flow fixture into an event brief, including its explicitly linked
cross-ticker benchmark, then reuses `backtest.costed_bars` for a separate declared
long-only signal. The signal is supplied as a scenario; the squeeze heuristic
never creates it. The brief cutoff is November 11 and the outer replay cutoff
November 13. Both dates, all inputs and the returns are fictional.

```text
python scripts/research_workflow.py execute examples/market-event-workbench.json --request-role "Fictional event and declared paper signal" --private-output-dir NEW_PRIVATE_DIRECTORY
python scripts/research_workflow.py verify NEW_PRIVATE_DIRECTORY/run
python scripts/institutional_research.py journal --root EXISTING_PRIVATE_JOURNAL --entry-id fictional-event-first-v1 --kind first_response --input NEW_PRIVATE_DIRECTORY/run/result.json
```

Run the commands from the package root or use absolute paths from another working
directory. Output and journal roots must be private and outside the package.
Inspect the retained first response and reports, costs, partial fills, inventory
and pending quantities. Replay uses already available prior-bar volume as a
capacity proxy and strictly later opens; it is not actual event liquidity, a
short/borrow simulator or observed execution. See [costed bar replay](costed-bar-replay.md)
for its settlement, cost, rounding and long-only limits. Full research verification
checks source/result consistency; it does not certify a profitable strategy.

## What HF01–HF10 mean here

The software supports pilot definition, source/rights review, decision briefs,
portfolio impact, prospective usefulness/return review, cost/liquidity context,
durable recovery, host acceptance tracking, methodology challenge and deployment
readiness respectively. All ten retain `real_world_acceptance:
NOT_ESTABLISHED`. Supplied evidence remains a declaration. Implemented helpers
and synthetic tests do not complete an elapsed pilot, qualify commercial data
rights, certify another host or operate an unattended live deployment.

Run the explicit end-to-end software demo from an unrelated working directory:

```text
python PATH_TO_SKILL/examples/institutional-paper-demo.py --output-root EXISTING_PRIVATE_DIRECTORY
```

It composes flow/squeeze diagnostics, creates a brief, retains its exact first
response, evaluates fictional October outcomes, journals and recovers the result.
Actual journal timestamps expose its later retrospective execution. It reports
`real_prospective_pilot_completed: false`; it is not a participant campaign case,
live forward test, trading result or instruction to start recurring monitoring.
