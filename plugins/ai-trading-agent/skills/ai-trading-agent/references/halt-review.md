# Retained exchange-notice review

Use `scripts/halt_review.py` for an offline chronology of a complete retained JSON
exchange-message collection. It filters by the source-bound as-of time before
selecting the latest notice. A later supplied notice remains visible in
`all_notices` and the cutoff exclusions; its fields never populate an earlier view.

```text
python -B scripts/halt_review.py request.json source-root result.json
```

The output is created exclusively; an existing result is never overwritten.
The input is a small binding request, not manually prepared result rows:

```json
{
  "source": {"path": "notices.json", "sha256": "ACTUAL_SOURCE_SHA256"},
  "collection_pointer": "/messages",
  "as_of": {
    "source": {"path": "scope.json", "sha256": "ACTUAL_SCOPE_SHA256"},
    "pointer": "/as_of"
  }
}
```

The source is a JSON object with a nonempty `symbol`, optional `exchange`, and
the full array selected by `collection_pointer` directly under that same object.
The pointer must address a single root field, such as `/messages`; nested arrays
such as `/archive/messages` are rejected even when their identity appears to
match. This prevents notices from inheriting a root identity over a different
nested identity. A root field containing a literal slash uses the usual RFC6901
escape (`/notices~1current`). Do not rewrite original source bytes to bypass the
scope restriction; retain unsupported nested collections for separate review.
Each message has a distinct
nonempty `message_id`, `published_at`, `halt_event_time`, and nonempty `reason`.
Optional `feed_dateline`, `quote_resume_at` and `trade_resume_at` are timestamps
or null. Optional observation clocks are `observed_at`, `first_seen_at` and
`first_observed_at`. If a message supplies `symbol` or `exchange`, it must match
the enclosing source. The array must contain between one and 10,000 messages.

Clocks must be complete timezone-aware ISO timestamps. Missing publication or
halt-event timestamps, invalid supplied clocks, duplicate IDs, conflicting
identities, multiple halt episodes, or ambiguous latest publication ties fail
explicitly. Retain such sources for review; do not rewrite them to obtain a
successful output. The limited format describes one symbol and halt episode;
it does not silently merge unrelated notices. JSON duplicate keys, source hash
mismatches, unsafe paths and supplied override fields are rejected.

The cutoff comes from an actual `as_of` field in a separately hash-bound source
(which may be the same file). No caller value can replace it. Every array member
is visited, with its original pointer and content hash retained. This establishes
coverage of the declared collection, not completeness of the exchange's feed.

## Two distinct views

- `publication_view` is a publication-only reconstruction. It selects the latest
  source-stated publication at or before the cutoff. It does not establish that
  anyone observed the notice at that time.
- `observed_view` requires both publication and at least one retained observation
  clock at or before the cutoff. Every supplied observation clock is checked;
  unknown observations remain unknown. An observation before publication is an
  explicit chronology error. Late retrieval does not change publication order.

Each view contains its eligible IDs, exclusion reasons, selected source pointer,
and selected notice. Use the appropriate view and state its basis. A
publication-only result cannot be described as historically available or
tradable. A missing observed result does not erase the publication chronology.

`quote_resumption` and `trade_resumption` retain the selected notice's schedule
and whether that time is before, at or after the cutoff. A future resumption
schedule announced in an eligible notice is valid schedule evidence; it is not
a future publication. A null trade schedule stays unknown, even if a later
excluded notice supplies one. No earlier schedule is carried forward over an
explicit null in the selected notice.

The feed dateline is neither the halt event nor publication. Quote resumption
is not trade resumption. Reaching either scheduled time does not prove that
activity occurred. The helper never returns trading permission, live exchange
verification or broker clearance. Current exchange/broker restrictions are
external facts, not new skill thresholds, gates or repeat approvals.

Retain the original command, sources, output and exit record. Exact emitted
facts can be checked with `news_evidence.py audit`; lexical presence checks alone
do not establish cutoff eligibility. This helper is not a `final_report` producer
and does not certify source authenticity or arbitrary report prose. Existing
normalized news triage remains the route for acquired records with real
availability and observation timestamps; do not manufacture those clocks to
fit raw notices into that schema.
