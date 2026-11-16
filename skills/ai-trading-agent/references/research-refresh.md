# “Update this research” on demand

When the user asks to update saved research, the assistant reopens the selected
research, collects permitted sources through the requested cutoff, reruns affected
calculations and delivers a complete revised answer explaining what changed.
The user does not prepare JSON, operate scripts or fill in technical review forms.
Use host-native collection and the existing [ordinary research workflow](ordinary-research-workflows.md)
and [review/correction cycle](research-review-cycle.md). This is an invoked,
self-contained workflow; it creates no monitoring, schedule, local server,
background worker or trading authority.

## Assistant workflow

1. Resolve which saved research the request means, its exact original request,
   mandate, horizon, method, source restrictions and previous delivered answer.
   Reopen only the explicitly selected private run outside the installed skill.
   Retain its externally saved session and final review-head pins. A refresh of a
   previous refresh additionally needs its refresh and completion pins. Do not
   reconstruct a trusted pin by hashing an edited manifest. If no usable pinned
   archive exists, explain that exact comparison/replay cannot be verified; do
   fresh research through the ordinary workflow, retaining the supplied prior
   answer as attributed historical context. Do not call that a verified refresh.
2. Retain the exact new request. Resolve a timezone-bearing cutoff and a separate
   check time. “Now” means the actual current host clock; if the host cannot
   establish it, state that limitation and obtain a concrete cutoff. Preserve a
   requested historical cutoff even when collection occurs later. A source's
   publication/information-availability clock must be through that cutoff; its
   later retrieval time does not make post-cutoff facts eligible. A cutoff before
   the previous run is a historical reconstruction, not this refresh operation.
3. Check the issuer/source indexes for new periods, revisions, amendments,
   withdrawals, restatements and missing documents using permitted native tools.
   Open and retain the actual documents and the source-index/check evidence.
   Keep original publication/availability and retrieval clocks separate from
   the new check time and the scope covered through the cutoff. Checks and
   attributed clocks are host declarations; retained hashes do not prove that
   a source is authentic or that a declared check was exhaustive.
4. Give every previous source an explicit disposition: `verified_unchanged`,
   `revised`, `retracted`, `unavailable` or `unchecked`. The first three need
   retained check bytes, a scope, coverage-through cutoff and check time.
   `verified_unchanged` retains the original bytes and original retrieval clock;
   the new check is separate evidence. `unchecked` means stale/currentness
   unknown, not verified unchanged. Unavailable, unchecked and retracted sources
   remain in the historical archive and are excluded from the current factual
   source roster. A missing dependency remains unsupported; do not relabel it
   unchanged or silently carry its old conclusion forward. For a retraction,
   explain which earlier facts, assumptions and conclusions lose support.
5. Explicitly select replacements and new sources. Preserve each source's own
   currency, period, basis, units, issuer identity, availability and retrieval
   clocks; do not copy metadata from a different operand. Normalized derived
   inputs require rebuilding with explicit `derived_from` source IDs and cannot
   predate their sources' availability. Rebuild source-bound job inputs with the
   new cutoff. Do not append an adjusted price tail without reconciling changed
   historical adjustments. Preserve full-universe and peer comparisons where
   the original mandate requires them; a previous winner is not the universe.
6. Call `research_refresh.begin_refresh`. It copies the complete selected prior
   research run into a bounded immutable-by-convention `parent-archive`, verifies
   its bytes with `research_memory`, retains the exact previous answer and source
   delta, and starts an ordinary session in `current`. Every material task also
   requires the previous answer and delta in review. Keep the returned refresh
   and session pins externally. The helper refuses unrelated top-level files,
   links/reparse paths, overlapping archives and outputs inside the skill.
7. Call `prepare_refresh` with the assistant-authored material-task dispositions,
   applicable filing jobs and existing source-bound workbench calculations.
   Account for **every previous calculation job** as recomputed or unsupported.
   A new cutoff always needs new job evaluation; matching old values are not a
   substitute. The existing `research_session.prepare_packet` executes supported
   producers. Actual computation status, full old/new typed results, transitive
   source dependencies and changed/unchanged-after-recomputation status are
   retained in `refresh-packet.json`. Missing runtime dependencies, unsupported
   producers and failed jobs remain explicit. Structural equality compares
   retained typed results; it does not establish financial equivalence, unchanged
   meaning or correctness of normalized input mapping.
8. Author the complete revised readable/structured answer. Lead with the current
   conclusion and whether the thesis strengthened, weakened, changed or remains
   unresolved. Explain source revisions/retractions, changed valuation and key
   assumptions, changes in risks or catalysts, what remains unchanged after
   actual checks and what could not be checked. Cite source/result evidence near
   the claims. Preserve mandate/method changes separately from like-for-like
   source changes. A price change and an EPS revision can both change a multiple;
   do not attribute the whole movement to one cause without supporting analysis.
   Identify what future evidence could change the conclusion. Deliver a useful
   limited answer when a complete refresh is impossible; source gaps belong in
   the main conclusion as well as the structured companion.
9. Use `research_refresh.start_review`, which adds the pinned source/result delta
   to the ordinary whole-answer review. Then use the existing session
   `freeze_draft`, `record_review` and `select_final` against `current`, retaining
   every draft, finding and correction. Require actual host review of both old
   and new complete answers, not just a changed-number checklist. Use an available
   independent native reviewer, otherwise disclose self-review. The reviewer
   judgments remain declarations; no helper certifies arbitrary prose or source
   truth. Finally call `complete_refresh` to seal the exact new reviewed archive.
   Deliver its unchanged selected answer pair and delivery notice. Preserve open
   findings and stale/unsupported dependencies even if the answer is useful.

## Internal host API

These are assistant operations, never user-facing forms. Import the bundled
`scripts/research_refresh.py` in the host's permitted Python environment. It uses
only explicitly selected files and the existing bundled research producers.

| Operation | Internal inputs and output |
| --- | --- |
| `begin_refresh(root, request_bytes, parent_root=..., expected_parent_session_sha256=..., expected_parent_head_sha256=..., as_of=..., checked_at=..., decisions=..., additions=..., tasks=...)` | Fresh private root; parent must have a complete selected delivery. Exact source decisions and new specs create `current`, `parent-archive`, `lineage.json` and a pinned `refresh.json`. Returns `refresh_sha256` and `session_sha256`. For a previous refresh, provide `expected_parent_refresh_sha256` and `expected_parent_completion_sha256` too. |
| `prepare_refresh(root, expected_refresh_sha256=..., dispositions=..., dependencies=..., filings=..., calculation=...)` | Existing ordinary session dispositions/calculation format. Returns `refresh_packet_sha256`, `session_packet_sha256` and actual source/result delta. Every previous job requires a disposition. |
| `start_review(root, expected_refresh_sha256=..., expected_refresh_packet_sha256=..., adopted_at=...)` | Adds retained `extra-refresh-delta` to ordinary whole-answer review and returns the revision head/protocol. Draft/review/final use the ordinary session API at `root/current`. |
| `complete_refresh(root, expected_refresh_sha256=..., expected_refresh_packet_sha256=..., expected_head_sha256=...)` | Requires an actual complete selected reviewed delivery, seals the current archive and returns `completion_sha256`. It preserves limited-delivery status. |
| `verify_refresh(root, expected_refresh_sha256, expected_packet_sha256=..., expected_completion_sha256=...)` | Reopens with externally retained pins. Completed archives require their completion pin. Checks copied parent/current bytes and saved review bindings; does not acquire sources or assert currentness. |

Each source decision has `{id,status,reason}`. For checked decisions, add
`check:{path,scope,checked_at,coverage_through}` pointing to actual retained check
evidence. For `revised`, also add `replacement` using an ordinary source spec
with the same ID. New source specs belong in `additions`. Every selected current
factual source needs `metadata.available_at` and `metadata.retrieved_at`.
Derived inputs require `derived_from`; rebuilding does not by itself validate
their semantic mapping. All material tasks use unique literal excerpts from the
**new exact request** and explicitly address missing evidence. An unsupported
task can have an empty factual-source list; the helper still attaches prior
answer/delta review requirements. A calculation's `contract.prompt` must equal
the new exact request and its jobs use retained-source `inputs_source` bindings.

Each previous-job disposition has `{id,status,reason}` with status `recomputed`
or `unsupported`. `recomputed` also needs `new_job_id` naming an actual submitted
job. A declared recomputation cannot override a failed producer: inspect
`recomputation_verified` and the actual outcome. Results with source gaps or
nested diagnostics remain conditional even when arithmetic replay succeeds.

The archive bound is 1,024 entries and 128 MiB, with each explicit file at most
32 MiB; earlier refresh chains consume that same bound. If a run exceeds it,
retain the original archive and describe the limitation. Do not trim evidence to
make an unqualified verified-refresh claim. Importable helper APIs and normal
host-native tools are sufficient; no backend is installed or required.

## Fictional practical example and limits

The regression exercises a completed earnings answer with USD 2.00 adjusted
diluted EPS guidance and a USD 50 quote (25x). The next-day fictional release
revises guidance to USD 2.50 and the retained quote becomes USD 55. The assistant
rebuilds source-bound inputs, invokes the existing earnings-basis producer (22x),
reviews the complete old/new answers including unchanged revenue and supply
risks, and seals a separate linked archive. The original answer and every source
remain byte-for-byte unchanged. The result compares scenarios based on issuer
guidance; it does not establish fair value, actual future earnings or a trade.

Tests also cover unchecked/unavailable archival-only sources, source retractions,
missing/mutated files, rewritten manifests, cutoff leakage, inadequate check
coverage, impossible source chronology, stale derived inputs, unexecuted jobs,
completion pins and unrelated-folder rejection. They use fictional offline
sources and declared self-review. These are implementation regressions, not live
source validation, independent investment research or campaigncasepasses.
