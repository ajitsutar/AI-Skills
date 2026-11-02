# Saved research and incremental updates

When the user asks to retain research, use a durable local research library outside
the installed skill and Git repository. Save the frozen input/result bundles,
acquisition receipts and failures, exact scorer/profile, original mandate, source
URLs and publication/checked times, normalized facts, candidate review register,
event calendar, risk outputs and final rationale. Keep private account details out
of public releases. Saving research does not schedule monitoring or authorize trades.

Use `scripts/research_memory.py` to seal an inventory, verify its files and produce
a refresh plan. The helper is offline: it does not fetch data, certify sources,
grant eligibility, or migrate old numerical results to new code.

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

Refresh membership, prices, actions, estimates, news and calendars through the new
cutoff. Price histories may be extended only after reconciling adjusted-history
revisions; do not append a split-adjusted tail to incompatible earlier prices.
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

Keep every old run immutable, show what changed and what could not be refreshed,
and retain a small local index pointing to the latest run. Never commit personal
library contents or generated stock recommendations with skill source code.
