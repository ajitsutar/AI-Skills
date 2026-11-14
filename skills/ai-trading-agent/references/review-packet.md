# Offline review-packet preflight

Use `scripts/review_packet.py` before an authorized automated source-only versus
brief-assisted evidence review. It prepares retained local files and checks
criterion support. It runs no participant, model API, network acquisition,
scheduler or study observation. All paid subscriptions remain optional.

Keep the complete packet private. Give each participant **only its own directory
under `participants/`**, never the packet root, request, ingress manifest or
`sealed/` originals. Those retain evaluator-only evidence. Source-only receives
identical source and neutral-request bytes to the assisted arm. Assisted also
receives the exact retained original brief and any explicitly permitted
`provenance_metadata`. Neither participant receives evaluator criteria, other-arm
answers or future outcomes. A separate evaluator reviews the retained rubric and
original evidence. Fresh contexts and any unavoidable context limits still need
actual host evidence; file identity cannot establish model independence.

## Source and request contract

Create an explicit source root and the existing [original-source manifest](original-source-lineage.md)
with `schema_version: 1`, `sources: [{id,path,format,sha256}]`. Each path is a
relative whole file under that root; formats are `json`, `text` or `bytes`.
Supply the manifest's independently retained SHA256. The tool composes the
existing `Corpus`/lineage byte checks and retains every indexed original.
An exact whole-file binding is intentional: construct a reviewed, minimal source
file before adoption if a larger source contains disallowed material. Labeling
a mixed document `source_inputs` does not remove its private or future content.

The JSON request has these fields:

```json
{
  "schema_version": 1,
  "packet_id": "review-a",
  "revision": 1,
  "case_id": "case-a",
  "review_at": "2026-10-02T15:00:00Z",
  "adopted_protocol_sha256": "EXACT_RAW_PROTOCOL_FILE_SHA256",
  "evidence": [
    {"id":"original-input","role":"source_inputs","source_id":"source-a",
     "allowed_arms":["source_only","brief_assisted"],"available_at":"2026-10-01T13:00:00Z"}
  ]
}
```

The abbreviated example omits required roles and will be `UNASSESSED` until they
are supplied. Evidence IDs are safe filename identifiers; each indexed source
has one declared role. All times need timezones. No clock is invented from a date,
missing duration or filesystem modification time. A source ID or role does not
authenticate its content.

| Evidence role | Exact participant policy | Required evidence |
| --- | --- | --- |
| `adopted_protocol` | `[]` | JSON with `id`, `adopted_at`, `case_ids` and `criteria`; retain the actual adopted revision and original protocol evidence. |
| `registered_roster` | `[]` | JSON `{protocol_sha256,case_ids}`; membership must match the adopted protocol and include `case_id`. |
| `selection_coverage` | `[]` | JSON with matching `case_id`, nonempty `scope`, `selection_method`, `source_ids`, and `status` `COMPLETE_DECLARED_SCOPE` or `PARTIAL_DECLARED_SCOPE`; partial coverage also needs explicit `gaps`. Every participant source-input ID must be selected. This is declared scope, not certified market-wide discovery. |
| `identity_coverage` | `[]` | JSON with matching `case_id`, nonempty `scope`, pinned `source_ids`, and `status: MATCHED_DECLARED_IDENTITY`; unresolved identity stays unassessed. |
| `source_cutoff` | `[]` | JSON `{source_cutoff_at}`. |
| `original_response_capture` | `[]` | JSON mapping `entry_source_id`, `transaction_source_id`, `commit_source_id`, `object_source_id` to pinned original journal files. |
| `decision_clocks` | `[]` | JSON `{decision_at}` for the actual declared decision clock, distinct from source cutoff and journal capture. |
| `scoring_criteria` | `[]` | JSON `{protocol_sha256,criteria}`; criteria must equal those in the adopted protocol. |
| `source_inputs` | `["source_only","brief_assisted"]` | One or more exact original source files; available by the source cutoff. |
| `neutral_instructions` | `["source_only","brief_assisted"]` | One nonempty common participant request, available by the source cutoff. Keep evaluator expectations separate. |
| `brief` | `["brief_assisted"]` | Exact original response bytes, matching the journal object hash, available by journal capture. |
| `provenance_metadata` (optional) | `["brief_assisted"]` | Explicitly permitted provenance only, available by capture. Review its content before dispatch. |
| `machine_review_timing` (optional) | `[]` | JSON `measurement: actual_machine_duration`, with `source_only` and `brief_assisted` objects each containing actual `started_at`, `finished_at`. Required for a timing criterion; never substitute zero. |
| `source_only_answer`, `brief_assisted_answer`, `future_outcomes` (optional) | `[]` | Evaluator-only retained material, never participant inputs. Exact known-byte inclusion in participant files is flagged. |

Explicit `private_contact`, `private_contact_configuration`, `runtime_config`,
`runtime_configuration` and `credentials` roles are refused **before source
files are opened**. Do not point a review manifest at private contact or runtime
configurations. No personal configuration discovery or credential inspection is
performed. These role and known-byte checks are not semantic classification,
redaction or host DLP; independently review participant content.

Known exact evaluator-only bytes are protected regardless of a second source ID
or filename: this includes the adopted protocol (which can contain the rubric),
roster, selection/identity coverage, clocks, capture bindings, scoring criteria,
timing evidence, answers and outcomes. The native journal entry, transaction and
commit bytes are protected transitively. An entire protected byte sequence inside
a larger participant file is also detected. A detected copy makes the packet
`UNASSESSED`, records `blocked_participant_evidence_ids`, and omits that file from
both participant directories when it was a common input. The exact original stays
under evaluator-only `sealed/` for inspection. The original response object is
permitted as the assisted brief but is blocked from source-only. These exact-byte
rules do not recognize paraphrases, re-encodings, extracted fragments or an
untruthful role label; content review remains necessary.

Each adopted criterion has exactly `id`, nonempty `criterion` text,
`assessment_kind` and nonempty unique `required_roles`. `evidence_review` checks
declared support for a later evaluator; `machine_duration` additionally requires
the measured-clock role. Other kinds, including investment efficacy or causal
usefulness claims, remain `UNASSESSED`. Every criterion also requires all core
roles in the table. A supported row is **not a passing score**: `score` remains
null, and no semantic criterion verdict is produced. A generic evidence-review
label does not prove that its rubric is sensible or its conclusion true.

The native journal format comes from `institutional_research.py journal` and
`research_operations.py process`. Bind the actual entry, transaction, commit and
object files through the ingress manifest. Entry/object/commit hashes and the
native idempotency key are replayed. The entry must be `first_response`; its
capture must be at or after source cutoff and at or before the actual declared
decision. The protocol must be adopted by cutoff. Source inputs, neutral request,
roster, selection, identity and rubric must be available by cutoff. Evidence later
than the review cutoff is unsupported. Local journal consistency does not prove
an honest machine clock, actual participant consumption or a prospective study.

## Prepare, verify and revise

```text
python scripts/review_packet.py prepare --request REQUEST.json --manifest INGRESS.json --manifest-sha256 EXACT_HASH --source-root EXPLICIT_SOURCE_ROOT --private-output-root EXISTING_PRIVATE_OUTPUT_ROOT
python scripts/review_packet.py verify --packet-directory PRIVATE_OUTPUT_ROOT/review-a-r1 --packet-sha256 EXACT_PACKET_JSON_HASH
```

Only the explicit existing private output root is written. It must be outside
the skill package and cannot contain the source root. Symlinks and Windows reparse
points in paths or ancestors are refused. Relative source paths cannot escape
the source root; 128 indexed files and 50 MiB total original bytes bound intake.
The explicit request and manifest are each capped at 50 MiB. This is a local
cooperating-filesystem contract, not a defense against arbitrary concurrent
external writers or an access-control installation.

Atomic publication uses a create-only 23-character temporary basename containing
the same random UUID payload as its longer hexadecimal spelling. Before writing
the first packet artifact, prepare creates any needed owned directories and
probes the pending destination lengths with create-only random files, then removes
those probes. A real unsupported path produces `OUTPUT_PUBLICATION_PATH_UNAVAILABLE`
with the destination and guidance to choose a shorter existing private output
root or a supporting host/filesystem. There is no blanket path-length limit and
no OS/ACL setting is changed; explicitly supported extended Windows paths remain
usable. Empty owned directories may remain after rejection, but no packet artifact
is published by a failed path preflight. Later I/O failure, power loss or external
writers can still require recovery; a successful probe is not a durability promise.

The immutable directory contains exact request/manifest bytes, complete indexed
originals under `sealed/`, the two participant directories and `packet.json`.
Repeated identical prepare calls return the same hash. Changed bytes never
overwrite existing artifacts. Verify requires the externally retained
`packet.json` hash, checks the exact file inventory, replays all source checks and
compares participant bytes/hashes with their role declarations. An extra answer
file or changed common input fails verification. Byte verification can pass for
an `UNASSESSED` packet: integrity and evidence support are distinct.

Later evidence needs a new `revision` (1–100) and `parent_packet_sha256`; preserve
the earlier sibling directory. Preparation and verification check its hash and
ancestry. Changed protocols also declare `predecessor_protocol_sha256` in the
new adopted protocol and retain their own adoption clock. A new revision never
updates original participant answers or scores, and post-capture evidence stays
flagged in the revised support matrix. Do not backfill an incomplete historical
review as a new passing original observation or restart a cancelled study.

The Python status interface is `analyze(request, manifest_path, pin, source_root)`
for read-only preflight, `prepare(request_path, manifest_path, pin, source_root,
private_output_root)`, and `verify(packet_directory, expected_packet_sha256)`.
Results include `status: READY_FOR_OFFLINE_REVIEW | UNASSESSED`, `dispatch_ready`,
`criterion_coverage`, `issues`, `bound_evidence: [{id,role,source_id,sha256}]` and
the retained `review_at`, `adopted_protocol_sha256` and `registered_case_ids`, with
explicit false authenticity/independence/clock-verification fields. Prepare and
verify also return `packet_sha256` and `integrity_status: VERIFIED`. CLI exit 2
means unsupported coverage or a controlled error; no command dispatches a review.
