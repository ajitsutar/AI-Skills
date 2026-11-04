# Saved research and incremental updates

When the user asks to retain research, use a durable local research library outside
the installed skill and Git repository. Save the frozen input/result bundles,
acquisition receipts and failures, exact scorer/profile, original mandate, source
URLs and publication/checked times, normalized facts, candidate review register,
event calendar, risk outputs and final rationale. Keep private account details out
of public releases. Saving research does not schedule monitoring or authorize trades.

Use `scripts/research_memory.py` to seal an inventory, verify its files and produce
a refresh plan. The helper is offline: it does not fetch data, certify sources,
grant eligibility, or migrate old numerical results to new code. Its `verify` and
`plan` results explicitly separate `evidence_scope.archive_integrity=VERIFIED`
from `source_currentness=NOT_ASSESSED` and `primary_reuse_eligibility=UNKNOWN`.
Neither operation performs source checks or numerical replay; plan actions are
proposed work, not completed revalidation. This remains true when the inventory
contains only `snapshot` and `result` artifacts: primary facts inside them still
need source checks before reuse as current evidence. Embedded freshness labels,
unchanged snapshot fields and matching file hashes cannot supply those checks.

The inventory JSON contains `run_id`, timezone-bearing `as_of`, `hold`, `universe`,
and an `artifacts` list. Each artifact supplies a portable relative `path`, `kind`
and original timezone-bearing `as_of`; optionally record source URLs and notes.
Kinds: `filing`, `review`, `prices`, `estimates`, `events`, `universe`, `snapshot`,
`result`, `code`, `mandate`. Paths must stay inside the library run folder. A
compressed evidence bundle can be one artifact; retain its inner receipts too.

```text
python scripts/research_memory.py seal --root /research/run --input /research/run/catalog.json --output /research/run/manifest.json
python scripts/research_memory.py verify --root /research/run --input /research/run/manifest.json
python scripts/research_memory.py plan --root /research/run --input /research/run/manifest.json --as-of 2026-10-20T20:30:00Z --hold P1M --universe US_EXCHANGE_LISTED_STOCKS --output /research/refresh-plan.json
```

On the next research request, resolve the new mandate and default to full data
collection. If the user requests partial fetch or reuse, verify the explicitly
supplied inventory and create a new run linked to its parent manifest. Recheck SEC/issuer indexes for
new periods, amendments, restatements and material announcements. Reuse unchanged
primary facts and their calculation bridges after that check; retain original
retrieval/publication times and record the new check separately. Missing evidence
stays missing. A TTL or unchanged price does not prove financial facts are current.
Retain the actual source-index or release evidence, the issuer/period scope, its
coverage through the requested cutoff and the time it was checked. Without that
evidence, report primary-source currency as unknown and current reuse as
unestablished, including in the final summary and missing requirements. Historical
bytes remain usable for explicitly labeled diagnostic replay; do not call such
replay "unchanged primary evidence reused after revalidation". The offline helper
does not authenticate a separately supplied check or infer that no newer filing
exists from equality of archived snapshots.

Refresh membership, prices, actions, estimates, news and calendars through the new
cutoff. Price histories may be extended only after reconciling adjusted-history
revisions; do not append a split-adjusted tail to incompatible earlier prices.
For numerical refresh work, use the [source-bound workflow](source-bound-workflow.md)
to declare the requested subtasks, bind the original evidence, execute supported
jobs, verify results and obtain the summary. Direct scorer calls may supplement
that workflow but do not replace it. Refreshing an explicitly supplied campaign
preserves its bound scorer/profile and mandate unless the user changes them; a
new-cutoff run gets a new contract without silently switching to today's default
method. If migration is needed, identify it and distinguish like-for-like replay
from changed-method results. A separately supplied event window does not replace
the campaign's holding period; state any coverage gap for the retained horizon.

Rerun the entire eligible universe and peer ranks, then review changed/new frontier
names in order. Do not only refresh previous winners. Recompute horizon scenarios,
risk and eligibility; old conclusions are prior research, not standing buy orders.

An interrupted **same-contract** collection can use `public_research_fetch.py
--resume` to retry only failures. It is not a new-date refresh. The shipped public
collector downloads all provider components for a new run by default. Its explicit
`--partial-fetch` mode can reuse unchanged quarterly statements from a supplied
verified bundle only after current source-index checks. Follow
[partial-fetch.md](partial-fetch.md) for its receipt schema, baseline preparation
and fallbacks. Original times, source bytes, component hashes and parent hashes
remain attached to reused facts. Prices/actions still refresh in full because
safe adjusted-history tail reconciliation is not implemented. Shared reuse cannot
establish independent acquisition or a guaranteed speedup. A completely fresh
request takes precedence; model-native memory is not a portable cache.

A partial refresh can still be saved as a new linked archive. The archive's
`as_of` describes the new archive, not a new acquisition time for every enclosed
source. Preserve each artifact's original publication/retrieval time and link the
parent manifest; retain `PARTIAL` status and uncompleted checks in an accompanying
review artifact. Sealing those bytes does not complete the refresh or make a stale
source current.

Keep every old run immutable, show what changed and what could not be refreshed,
and retain a small local index pointing to the latest run. Never commit personal
library contents or generated stock recommendations with skill source code.
