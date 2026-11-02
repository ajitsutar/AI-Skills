# Portable backtest data storage and recovery

Use `scripts/research_data_store.py` when a research task needs durable compressed
source captures, bounded local storage, resumable processing, scope narrowing or
portable archive verification. Select the storage root from the user's task; never
choose a second drive, synced folder or hidden model cache automatically. A host's
local path is not a portable contract. Keep stores outside the installed skill and
release evidence. These tools do not discover a complete historical stock universe
or certify point-in-time financial data.

## Create and capture

The stdlib `Store` API requires an explicit root and owner. Creating a store requires
a new directory; opening one checks its ownership marker. No existing populated
directory is adopted. All store paths are relative, and absolute paths, traversal,
symlinks, Windows junctions/reparse points and alternate streams are rejected.
Ancestor checks have a finite bound. There is no recursive cleanup command.

```python
from research_data_store import Store

store = Store('/research/task/raw-store', 'task-owned-research', create=True,
              min_free_bytes=512*1024**2, max_capture_bytes=256*1024**2,
              max_active_captures=4)
request = {
    'provider': 'declared-provider', 'security_id': 'provider:permanent-security-id',
    'provider_symbol': 'DEMO', 'start': '2021-01-01', 'end': '2026-01-01',
    'adjustment': 'split-and-dividend', 'schema_version': 'provider-response-v1',
    'parser_version': 'adapter-v1', 'fields': ['daily-prices', 'corporate-actions'],
    'source_role': 'native_response', 'vintage': 'frozen-request-run-id'
}
# producer is an adapter that yields bounded byte chunks from the actual source.
record = store.capture(request, producer, resume=False)
```

The complete request, original retrieval time, raw and compressed hashes, byte
counts and raw chunk hashes accompany each immutable capture. Optional identity,
URL, units and publication metadata remain in the whole request; do not reduce away
material source fields. A complete capture means only that the producer finished.
It does not mean parsing, data coverage, security identity or recommendations passed.
Use the correct source role: native HTTP body, decoded provider representation and
normalized rows are different artifacts.

Capture checks free space before calling the producer, during writes and after
compression. Maximum bytes and simultaneous captures are explicit; it never switches
drives or retries indefinitely. Different requests can capture concurrently up to
the bound, while a same-request lock prevents duplicate work. Archive/prune operations
exclude active captures. A hard process kill can leave a lock: inspect ownership and
the prior process before explicitly removing a stale lock; the API never guesses.

Gzip responses are content-addressed and deduplicated by raw hash. Identity and
vintage records stay separate even if their bytes happen to match. GOOG and GOOGL,
unresolved CIK aliases, source providers and reporting vintages are not merged.

## Resume and optional refresh reuse

`capture(..., resume=True)` reopens and verifies a completed capture under the exact
same frozen request, then skips the producer. This permits offline normalization
after an interruption without another download. Interrupted transport bodies remain
compressed failed attempts and are not successful records. Resuming such an incomplete
body performs a new complete request; byte-range HTTP continuation is not implemented.
Provider retries/rate limits remain the adapter's responsibility and must be bounded.

For the public collector, add `--component-store` to its existing command. Each
successful yfinance component is gzip-checkpointed before downstream filtering or
the final row write. `--resume --component-store` can recover those components under
the saved contract. The store lives beneath the explicit `--output` root. Controls
`--min-free-bytes` and `--max-component-bytes` bound storage. yfinance still materializes
its result in memory: this adapter captures the decoded representation, not Yahoo HTTP
wire bytes. Ordinary snapshots and raw-row formats stay compatible. Full network
fetch remains the default for a new run; storage does not opt into cache reuse.

New-date reuse is a different decision. `Store.reuse_decision` defaults to
`FETCH_FRESH`; `partial_fetch=True` plus a current source-check receipt is required.
The receipt must bind the old request ID and new request digest, retained evidence
path/hash, timezone-bearing check timestamp, scope `entire_retained_representation`
and the unchanged provider revision identifier. The new request must have an explicit
`decision_at` or `observed_at`, and the check must be at or after it. Provider,
security/share class, fields, date range, adjustment, schema and parser must match.
Changed, absent or unverifiable revisions force fresh acquisition of affected history.
An arbitrary unchanged flag, TTL or local file hash does not establish provider freshness.

This generic reuse API checks declared contracts and evidence bytes; the adapter must
actually establish what the source revision index means. It never authenticates an
arbitrary receipt. It supports exact full-representation reuse, not merging old price
prefixes with new tails. Splits, dividends, financial restatements and price corrections
can revise old observations. Preserve both vintages and refetch when needed. The
public collector's narrower statement-only partial-fetch interface remains in
[partial-fetch.md](partial-fetch.md); it still reacquires price history.

## Verification, scope and archives

`store.verify()` streams gzip CRC, raw SHA and chunk checks for every completed
capture. Supplying a prior verification receipt allows unchanged records to reuse
their prior raw seals **after rehashing the compressed bytes**. New/changed objects
receive full verification. A supplied seal is explicit local evidence; this faster
verification is not a new source-freshness check or independent audit.

`scope_keys(records, security_ids, former_member_ids=..., benchmark_ids=...)` selects
every matching capture and reports missing identities. Supply historical membership
and benchmarks explicitly when narrowing all-US to S&P; current membership alone
loses former members. The helper does not infer historical identity from tickers.
The returned keys may span several providers/vintages; keep them separate in analysis.

`store.archive('archives/scoped.zip', keys)` writes selected records, their objects,
the ownership marker and a portable SHA/size manifest, then reads every archive member
back. `store.prune_to(keys, 'archives/scoped.zip')` is a preview. Its explicit
`delete=True` variant requires the retained subset to match that verified archive
before removing only unwanted owned records and unreferenced owned objects. Skill
files, release evidence, unrelated files, failed-attempt evidence, archives and the
root marker are never deletion targets. A partial prune failure must be reconciled
from retained files and receipts; do not assume atomic rollback.

`restore_archive(path, new_root, owner)` verifies the whole archive and restores into
a new explicit destination, rejecting overwrites and escaped paths. Record/object
paths remain relative, so relocation does not require changing source hashes.

CLI examples (substitute the task's authorized root and actual JSON inputs):

```text
python scripts/research_data_store.py --root /research/task/store --owner task-id init
python scripts/research_data_store.py --root /research/task/store --owner task-id capture-file --request request.json --input captured-response.bin
python scripts/research_data_store.py --root /research/task/store --owner task-id verify
python scripts/research_data_store.py --root /research/task/store --owner task-id archive --name selected.zip --keys selected-request-ids.json
python scripts/research_data_store.py --root /research/task/store --owner task-id prune --retain-keys selected-request-ids.json --archive archives/selected.zip
```

## Normalized data and coverage

### Measure physical storage without changing evidence

Distinguish logical path bytes from unique stored file-data bytes. File lengths
count every retained path; hardlinks can share one file, and transparent filesystem
compression can reduce its stored bytes without changing the bytes a reader sees.
Report the filesystem method, measurement time, unique file identities and whether
metadata/allocation overhead is excluded. Count archives, repairs and temporary
write reservations under the stated cap; do not subtract shared bytes twice or
describe already compressed files as newly compressed without measuring savings.

Where the authorized filesystem supports it, transparent compression such as NTFS
compression can preserve existing paths and content hashes. Verify readable bytes
and the affected readers afterward. Deduplicate only immutable, byte-identical
source bodies after hash and byte comparison. Preserve every acquisition receipt
and source-vintage identity. If hardlinks are used, all linked names share writes:
future updates must write a new file and atomically replace the intended path,
never modify a shared inode/file identity in place. Verify link identities, hashes
and reader behavior before retiring the redundant body. Keep rollback evidence.
Do not deduplicate mutable checkpoints, databases or merely equivalent normalized
data. These are reviewed host-filesystem procedures, not features implemented by
the portable Store API; its existing path and ownership checks still apply.

Optional `write_parquet_batches` and `read_parquet_batches` use installed PyArrow and
ZSTD. They accept bounded Arrow batches, check schema, maximum batch bytes, disk reserve
and output paths, and leave a partial file on failure rather than a success marker.
The reader uses an explicit row batch size and rejects oversized returned batches;
these bounds do not cap Arrow's internal decoder allocations. They do not install dependencies or silently
pretend another format is Parquet. Without PyArrow, retain gzip captures and use a
declared gzip CSV/JSON adapter or report Parquet as unavailable. An adapter must preserve
field metadata, source IDs and normalization provenance; Parquet alone is not an audit.

`coverage(requested, observations, required_sessions, decision_at)` separates requested
security identities, provider query strings, artifacts, usable sessions, missing
sessions and unknown historical identities. For financial availability it uses the
later supplied publication/availability timestamp when both exist, never fiscal
period-end. An explicit availability timestamp alone is usable; if neither timestamp
is supplied, availability remains unknown. With no requested session grid, session
coverage is `NOT_ASSESSED`, even when financial artifacts exist. These are checks of adapter declarations, not proof
of source correctness, corporate actions, delisting returns, historical membership or
point-in-time completeness. Keep acquisition gaps visible rather than silently shrinking
the requested universe or substituting another share class.

For missing histories, identity conflicts or filing gaps, follow
[historical coverage recovery](historical-coverage-recovery.md). Its date-coverage
audit supplements this generic store coverage API with per-security intervals,
issuer/class checks, typed relationships and source-separated qualified dates.
