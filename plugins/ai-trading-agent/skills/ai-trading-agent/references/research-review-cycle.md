# Assistant review and correction

The host assistant operates this workflow from the user's ordinary research request. Do not ask the user to write review JSON, find defects in the assistant's answer, or become the reviewer. This is an on-demand portable workflow: no local service, model API, subscription, credentials or background worker is required. Python, where available, retains evidence and checks bindings; the native host assistant performs the semantic review.

## Start the review without a supplied protocol

For a research route that adopts this cycle, the host assistant owns setup as
well as review. The original request and available source bytes are the starting
inputs, not a prewritten `answer_review` protocol. Before drafting, the assistant
identifies material review units and a whole-request coverage unit, locates their
actual request spans, and assigns the required source IDs. For original files,
use the pinned-file bootstrap below: it ingests the entire allowlisted manifest,
adds a whole-request coverage unit and writes the real protocol/head. Adopt any
additional native-authored material units before that call. Existing `create_run`
(or CLI `create`) remains available for already retained in-memory bytes and
units. Keep the returned protocol and head pins in the coordinating session.
The lower-level `answer_review.assess` consumes this protocol later; it does not
create it or dispatch the native review.

If an externally adopted protocol is supplied, preserve its scope and pins and
check applicability; do not silently replace it. If none is supplied, create the
assistant-owned protocol above. Neither a missing attachment nor the standalone
assessor's optional status makes an adopted review cycle optional. An unavailable
independent reviewer selects `self_native`; an unavailable Python helper selects
the native artifact fallback below. Neither condition removes the actual second
pass over the complete draft and original evidence. Record a real remaining
obstacle and incomplete disposition if that review cannot be completed; never
populate favorable findings merely to finish the record.

## Pinned-file bootstrap

The host can initialize the review directly from original files without writing
an intermediate JSON job that copies or normalizes their text:

```sh
python -B scripts/research_revision.py bootstrap --run PRIVATE_NEW_RUN --request ORIGINAL_REQUEST.txt --request-sha256 REQUEST_SHA256 --source-manifest SOURCE-INGRESS.json --manifest-sha256 MANIFEST_SHA256 --source-root ORIGINAL_SOURCE_ROOT --adopted-at ISO_TIMESTAMP
```

The assistant supplies actual paths, externally retained hashes and adoption time
using its permitted native tools. These are internal workflow inputs, not forms
the user must prepare. `PRIVATE_NEW_RUN` must not exist, its parent must exist,
and it must be outside the installed skill. There is no source-subset option.
The explicit manifest uses exactly this existing shape:

```json
{"schema_version":1,"sources":[{"id":"release","path":"release.txt","sha256":"ACTUAL_SOURCE_SHA256","format":"text"}]}
```

Every row is ingested; `format` is `text` or `json`, with nonempty readable UTF-8
bytes. JSON source bodies remain original evidence, not automatically interpreted
or certified facts. Source IDs and relative forward-slash paths must be unique
including case aliases; escape paths, reparse points, authentication-store names,
missing files, unexpected manifest fields and hash mismatches are rejected.
The externally retained manifest pin prevents silently substituting a subset.
Completeness is only relative to that explicit allowlist, not proof that it
contains every possible source. CRLF, non-ASCII characters and an optional UTF-8
BOM are retained byte-for-byte; request spans are UTF-8 byte offsets.

The deterministic `whole-request` unit spans the entire original request and
requires all original sources. It explicitly asks the native reviewer to identify
material omissions in both the draft and unit roster. It is a review obligation,
not an inferred semantic rubric or evidence that the request is fully understood.
To add material units identified by the host, pass `--units NATIVE_UNITS.json
--units-sha256 UNITS_SHA256` before initialization. The file is a list of the
existing unit objects (`id`, `requirement`, `request_spans`,
`required_source_ids`); it cannot override the whole-request unit or supply
review statuses. No favorable judgments, source dispositions or findings are
created. The host must review the complete original request even if it uses only
the minimum whole-request scaffold.

The output preserves `request.md`, every `sources/ID.bin`, the exact original
`bootstrap-manifest.json` with reversible original-path/ID mapping, `protocol.json`
and `run.json`. Optional bootstrap provenance is bound into the new run's hash;
legacy runs and their hashes are unchanged. Replay needs only the retained run,
not original machine paths. The input hashes are checked before writing and
again after staging; an observed concurrent source change raises and leaves the
failed run intact for inspection.

Initialization returns `DRAFT_REQUIRED`; freezing the complete pair returns
`REVIEW_REQUIRED`. Perform a real second-pass native review and record it through
`review` with the actual protocol and current head. `self_native` is available
when an independent native reviewer is unavailable. `REVIEW_RECORDED` is not a
semantic pass: retain adverse and incomplete findings, correct within the budget,
and select the exact latest reviewed pair with its notice. `final` without a
review is rejected. `verify` replays these states and the original inventory;
none proves source authenticity, reviewer honesty or whole-answer correctness.

## Native workflow

1. Retain the exact original request. Interpret its material subtasks, including requested alternatives, valuation/period/currency assumptions, source freshness and remaining unknowns. Obtain permitted sources using the host's actual tools; preserve the evidence corpus. Generated numerical annexes can be distinct supporting sources. Before drafting, freeze explicit review units with request byte spans and required source IDs. Include a whole-request coverage unit: the reviewer must read the original request and identify any material requirement missing from the draft or from the unit roster. Never silently narrow the request to what the calculator supports.
2. Create one scoped run outside the installed skill. The helper rejects resolved paths inside its package before creating run artifacts and refuses to resume runs relocated into that package. Freeze the original request, exact sources, review protocol, zero material-error tolerance and a practical correction limit (default two; supported zero through five). Store the returned run, protocol and latest head hashes in the coordinating host/session evidence. Those external pins are needed to detect later truncation or rewritten limits. Treat unavailable evidence as a gap. Do not replace source bytes or revise the original request midway through a correction.
3. Write and freeze the **complete** answer in Markdown and its complete structured companion. The companion is an assistant-authored research result, not a numerical annex substituted for the whole answer. Keep qualifications, alternatives, missing subtasks and source gaps in the answer itself. Preserve the initial pair even when wrong.
4. If native independent agents are available and authorized, give an independent reviewer the exact original request, fixed sources/protocol and complete current draft. Ask it to review every material unit against actual source passages; check calculations with available deterministic helpers; inspect the whole request for omissions; check attribution, currency, period, unsupported inferences and contradictions between Markdown and structured response. Do not provide another reviewer's answers or a desired pass. Request concrete findings, precise UTF-8 byte spans and the actual unit/source review dispositions. Use `independent_native` only when this actually occurred. If no independent native reviewer is available, perform an explicit second native assistant self-review and declare `self_native`. Do not fabricate an independent agent, invent a model run, or call a local model backend. Reviewer mode and identity remain declarations, not authenticated independence.
5. The assistant converts that actual review into the existing `answer_review` document and records it. Each material unit has a status, declared materiality, rationale, answer locators and dispositions for every required source. `SUPPLIED_UNREVIEWED`, missing rows and unknown materiality remain incomplete; `OMITTED` and `UNSUPPORTED` remain open findings. Preserve the review and real `answer_review.assess` result even when adverse. The file checker cannot discover omitted semantic units, verify financial prose or prove that the reviewer read a passage. The native reviewer owns those judgments.
6. Correct every fixable material error, contradiction and omitted requirement within the frozen attempt budget. Normally remove or qualify unsupported assertions in the actual answer. Do not simply change an adverse review to `SATISFIED`. Freeze a new **complete** pair with the prior draft as parent, then obtain a fresh review of that entire pair. Prior review records never transfer to changed bytes. Even a one-line edit requires the new draft/review path. One review is retained per draft; a changed judgment requires a preserved next attempt, not replacement of the earlier record.
7. Select only the latest complete reviewed pair. Deliver its exact retained Markdown **together with** the generated `delivery-notice.md`, and retain the structured companion as supporting output. The notice is separate deterministic material, not a silently edited answer pretending to inherit an old review. Show its unresolved findings to the user. If an error genuinely cannot be resolved, the notice identifies the affected claims as unreliable/unresolved; do not present them as established conclusions. Do not hide an omission in a JSON receipt. A new human approval is not required to deliver useful limited research.

Final labels are `REVIEWED_DELIVERY` when the real binding assessor reports a complete within-policy declared review; `DELIVERED_WITH_LIMITATIONS` when the review is complete with open findings; and `REVIEW_INCOMPLETE` when material units or sources remain unreviewed. These are evidence dispositions, not whole-answer correctness certificates or broker execution permissions. A missing requirement must not become a favorable zero. After the correction limit, deliver an explicit limited/incomplete answer and all open findings; do not restart a directory to erase attempts. New evidence or a materially changed request needs a separately identified continuation that preserves the prior run and budget history.

## Small helper API

Import `scripts/research_revision.py` using the chosen host's available Python environment. The assistant supplies these artifacts internally; the user does not need to author forms.

```python
bootstrap_run(root, request_path, request_sha256, source_manifest_path,
              manifest_sha256, source_root, adopted_at, *, material_units=None,
              max_corrections=2)
create_run(root, request_bytes, sources, units, adopted_at, max_corrections=2)
freeze_draft(root, markdown_bytes, response_bytes, captured_at,
             *, expected_head_sha256, parent_draft_id=None)
record_review(root, review_document, *, reviewer_mode, expected_head_sha256)
select_final(root, draft_id, *, expected_head_sha256)
verify(root, expected_head_sha256=None)
```

`root` is a new directory under an existing, authorized output parent. `sources` maps stable IDs to exact bytes (maximum 128). `units` use the existing `answer_review` schema: `id`, `requirement`, `request_spans` and `required_source_ids`. Offsets are UTF-8 bytes with hashes. Freeze readable UTF-8 source passages for native review; retain binary originals through the source/filing workflow with their extraction provenance instead of inventing text offsets into a binary PDF. Every source declared required by a unit needs an explicit source-review disposition. The frozen `protocol.json` uses `request.md` and `sources/<id>.bin` paths. Use its exact reference from the creation receipt.

Every mutation returns `head_sha256`; supply the previous externally retained head on the next mutation. Draft receipts include `draft_id` and the exact `authored_pair` `delivery`. A review document uses that exact delivery and protocol, `reviewer.kind = "automated"`, the native reviewer's declared ID, actual `reviewed_at`, and the existing per-unit review rows. `record_review` returns the full document and real assessor result. `select_final` returns the selected pair, review event pin, `disposition`, and exact `delivery_notice` reference. `verify` replays the entire chain through the real assessor and returns drafts, reviews and final selection. Inspection without an external head cannot detect a maliciously truncated and completely rewritten history.

Retained layout: immutable `run.json`, `protocol.json`, `request.md`, `sources/`; sequential complete `drafts/000/first-response.md` and `response.json`; append-only `events/000001.json` records; and final `delivery-notice.md`. Writes are exclusive. Stale heads, changed inputs/protocol, reused/missing parents, an unreviewed latest draft, annex substitution, reviewed-byte changes, attempt-limit edits, unknown files and edited final notices are rejected. Use a single writer. Preserve partial/failed directories; a crashed write can leave an invalid, untracked artifact and must be reconciled explicitly rather than erased. This is integrity checking under retained external pins, not an operating-system immutability or global cross-directory attempt guarantee.

## CLI for host adapters

```text
python scripts/research_revision.py create --run RUN --job CREATE.json
python scripts/research_revision.py freeze --run RUN --job DRAFT.json --expected-head-sha256 HEAD
python scripts/research_revision.py review --run RUN --job REVIEW.json --expected-head-sha256 HEAD
python scripts/research_revision.py final --run RUN --job SELECT.json --expected-head-sha256 HEAD
python scripts/research_revision.py verify --run RUN --expected-head-sha256 HEAD
```

Explicit job files are bounded and parsed without duplicate JSON keys. Create fields: `request` (UTF-8 text), `sources` (ID-to-UTF-8-text map), `units`, `adopted_at`, `max_corrections`. Draft fields: `markdown`, `response` (complete JSON text), `captured_at`, `parent_draft_id` (null for the initial draft). Review fields: `review_document`, `reviewer_mode`. Selection fields: `draft_id`. Receipts print to stdout; invalid evidence exits 2. A successful CLI call means the requested retention/check operation succeeded, not that its declared review passed. Inspect the final disposition.

If a host cannot execute the helper, carry out the same bounded assistant review/correction process with its native artifact tools and disclose that exact-byte chain replay was unavailable. Do not claim helper verification, launch a service, or require the user to repair the host merely to receive supported research.

## Ordinary prompts

- “Review the latest earnings and guidance for this U.S. stock. Check your answer, fix errors, and show the important evidence gaps.”
- “Assess the event and the filings behind it, including alternatives. Have an independent native reviewer check the complete answer if one is available, then correct it.”

The assistant handles source selection, artifact construction, review and corrections; the response remains understandable research with citations and visible limits.
