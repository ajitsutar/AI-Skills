# Local production research operations

`scripts/research_operations.py` coordinates a local Windows supervised PAPER
research workflow. It registers an immutable adopted configuration, captures
explicit public files, reconciles retained sources, produces a source-bound
plan/brief, and retains exact first-response bytes. It creates no scheduler,
paid account, source entitlement, execution policy or order permission.

## Adopt the configuration

Create an existing private directory outside the package. Supply a JSON object
with `schema_version: 1`, `workflow`, `sources` and `freshness`. `workflow` uses
the configured research question, universe, horizon, reviewer and study fields
described in [institutional research](institutional-research.md). Choices must be
complete; a template is not adoption. A new root is required for changed adopted
configuration, package manifest or Python implementation bytes. The binding
covers transitive calculation modules as well as the operating driver. Preserve
the earlier root and its original results.
Optional `hypothetical_portfolio`, `source_configuration_status`,
`intended_data_uses` and `deployment` declarations are retained in the same
immutable configuration. A registered hypothetical book supplies missing
portfolio context only; it is never a live broker account.

Each source explicitly declares `id`, exact allowlisted `url`, supported
`adapter` and `rights`. HTTPS sources also declare a configured research-contact
`user_agent`; the exact shared-public IBKR FTP route can omit that HTTP field. Optional
`parse_options` retain supported parser declarations, including an explicit ZIP
member. Optional `max_bytes`, `timeout` and `retries` stay within existing public
acquisition limits; absent retry count means zero automatic retries. No URL/date
template, personal contact lookup, credential, browser session or subscription
is inferred. Source terms and intended retrieval, retention and AI/host use must
be reviewed for the actual deployment; a declared rights string grants no rights.

`sources: []` supports supplied-data work while reporting
`NO_CONFIGURED_SOURCES` and a coverage gap. It is not a qualified live feed or
evidence of zero market activity. `freshness.max_capture_age_seconds` is an
explicit nonnegative capture-age criterion. A recent retrieval does not make an
old position, filing or price a current market observation.

```text
python scripts/research_operations.py register --root PRIVATE_ROOT --config CONFIG.json
python scripts/research_operations.py collect --root PRIVATE_ROOT --run-id RUN_ID
python scripts/research_operations.py status --root PRIVATE_ROOT --as-of AWARE_TIMESTAMP
```

All mutations use the existing journal's exclusive whole-root lock. Per-run
journal entries use a separate child root, so capture/processing and journal
publication do not acquire the same lock recursively. The lock coordinates
cooperating local processes; it is not a distributed service or OS access-control
boundary. Different private roots do not share an overlap lock or rate budget.
Within one root the driver spaces SEC request starts by at least one second,
retaining its last start clock and using sleeps of at most one second. Existing
transient retry backoff still applies. Other roots, applications and clients need
separate aggregate rate coordination; this local pacing does not control them.
On Windows the driver uses native extended-length spellings for the same
explicitly selected private root, including nested journal lock archives. It
does not change system long-path settings, permissions or access controls.

## Collect, reconcile and resume

Each acquisition attempt has a retained pre-request record and a fresh directory.
Returned bytes, actual retrieval clocks, failure manifests and earlier attempts
remain private. A complete existing capture is verified and reused rather than
downloaded again. A complete download interrupted before parsing can be parsed
on `collect` without another GET. Partial, failed, corrupt or uncertain captures
never become usable observations or silently fall back to an earlier success.
The latest source attempt controls current source status; the failure history
remains visible after recovery.
Retained parse failures stay visible after the same raw capture is successfully
parsed on restart, including their original clocks where known. Legacy failure
records without a precise error clock remain explicitly undated.
Zero eligible rows and unresolved target mappings are reported with explicit
counts/qualifications; syntactically successful parsing is not usable coverage.
The CLI returns exit 2 for `NO_CONFIGURED_SOURCES`, `COLLECTED_WITH_GAPS` and
selected-evidence mismatches. Explicit source-gap disposition recording can
return exit 0, and integrity verification can pass while coverage remains
unqualified. Read those statuses separately from byte-integrity success.

Failed or uncertain acquisition is not automatically repeated. After inspecting
the retained error and ensuring the old owner is stopped, an operator may run
`collect --retry-failed` once to authorize a new attempt, preserving the old one.
This flag does not bypass a provider denial or human check. Provider failures and
source terms may require a different explicit configuration or supplied records;
there is no automatic source substitution.

The parser binds source identity, exact complete bytes/hash and first-observed
retrieval clocks to the acquisition manifest. It preserves unknown publication
and measurement dates separately. Original parsed rows are replayed and compared
before reuse. A source ID alone cannot authenticate a supplied row.

## Process a declared event

Supply the complete common envelope with exact `as_of`, `records` and an explicit
`event.ticker`. The adopted `workflow` is applied only when absent; a conflicting
supplied workflow is rejected. The default record selection is that explicitly
declared event ticker. Optional `selection: {tickers: [...], record_ids: [...]}`
must include it. Linked benchmarks, competing active benchmark feed identities
and revision ancestry are retained; no ticker,
signal, trade, missing observation or investment preference is invented.

Configured-source records supplied in the input must match actual retained
parsed rows, including their payload and source metadata. Independently supplied
records remain separately identified as unacquired declarations. All original
input bytes are retained. The assembled envelope, plan, brief, protocol and
first response are immutable; changed input, collection state or cutoff requires
a new run ID. Missing eligible evidence yields an explicit abstention, and
incomplete sources remain coverage gaps while independent supported work runs.

For an explicit no-recommendation slot, supply `run_outcome` with `disposition`
`SOURCE_GAP`, `ABSTAIN` or `NO_EVENT`, a nonempty `reason`, and dated `coverage`
with `scope` and `checked_at`. This branch needs no fabricated ticker and skips
the investment brief while retaining its disposition as the first response.
`NO_EVENT` additionally requires `observed_no_event: true`, coverage status
`COMPLETE_DECLARED_SCOPE`, and nonempty `observed_source_ids` bound to successful
configured captures available by the cutoff. That remains an operator coverage
declaration, not certified all-market absence. Empty inputs or no configured
sources cannot establish no events.

```text
python scripts/research_operations.py process --root PRIVATE_ROOT --run-id RUN_ID --input ENVELOPE.json
python scripts/research_operations.py recover --root PRIVATE_ROOT --run-id RUN_ID --input SAME_ENVELOPE.json
python scripts/research_operations.py verify --root PRIVATE_ROOT --run-id RUN_ID
python scripts/research_operations.py verify --root PRIVATE_ROOT --run-id RUN_ID --incremental-input INCREMENTAL_ENVELOPE.json
```

`recover` repeats the same idempotent processing operation. It reconciles partial
artifact/journal publication; it does not rewrite an original first response.
Verification checks retained bytes, source parsing, replay and journal
transaction/entry/commit/object bindings. Optional full/incremental comparison
normalizes both selected views at the identical cutoff and compares the eligible
record bodies and payloads. A changed payload, omitted active revision or changed
cutoff cannot pass merely because some raw hashes match. This checks retained
selected evidence, not an unobserved provider history or a complete market feed.

Information cutoff, actual journal capture and eventual human decision are
different clocks. The driver does not attest response consumption, an honest
system clock, prospective usefulness, actual human review or an elapsed return.
Human usefulness and return evaluation remain separate workflows.

## Lock recovery, retention and deployment

Normal exit releases only its matching owner token. A hard crash may leave the
lock. Never delete it based on age or a guessed PID. Independently confirm the
owner stopped, retain its bytes/hash, then use the existing explicit release:

```text
python scripts/research_operations.py release-lock --root PRIVATE_ROOT --expected-lock-sha256 EXACT_HASH --operator-confirmed-stopped
```

The old lock bytes are archived and changed tokens are refused. A release-guard
lock left by a release-process crash needs separate operator investigation.
An abrupt exit during journal publication can leave both the whole-root lock
and the per-run journal lock. Confirm their owner is stopped, retain both tokens,
and explicitly release each matching lock, including the child journal root,
before resuming the same processing input. Releasing the outer lock alone does
not clear a child journal lock.
Power loss, unsupported filesystems and arbitrary external writers remain outside
the atomicity guarantee; publication relies on local fsync and same-directory
hard links. Test the target filesystem rather than assuming it supports them.

Assign a human workflow owner, usefulness reviewer and local operations owner.
Keep configurations, captures, input documents, journals, failures and review
records private under their actual source-retention terms. Exclude them from
Git, public packages and unapproved cloud/sync locations. Preserve failed attempts
and original responses through study review; deletion, backup, incident handling
and restoration need a deployment-specific owner and tested procedure. The tool
does not install ACLs, encrypt a disk, back up data, configure a scheduler or
promise unattended continuous operation. A Windows recovery/overlap exercise
does not establish another OS/host or dependable recurring acquisition.


## Source adapters and delegated technical review

The source list can include `sec_company_tickers` and exact shared-public
`ibkr_shortstock` acquisition; see [market sources](market-sources.md). FTP uses
its own explicit protocol, zero automatic retries and completed-transfer proof;
it cannot make an unrelated host/path or an HTTPS failure a valid capture.
`bar_context` is retained as an explicit parse option for permitted OHLCV files.
External price-adapter captures retain their provider-decoded versus HTTP-wire
scope. Do not claim a live or licensed feed merely because an export parses.

When the user delegates research and technical review, deliver completed readable
reports. Do not turn the user into a source-selection, calculation or technical
rating stage. Configure an explicitly automated reviewer and fixed criterion
before included observations; preserve any earlier human-review protocol as a
prior revision. Independent source-only and source-plus-brief contexts receive
frozen permitted inputs, no other review answers or future outcomes, and retain
actual model/context and clock limitations. Automated review is a quality proxy,
separate from human usefulness and descriptive paper returns. Missing runtime
measurements are absent, never zero minutes or human time savings.

Scheduling requires the user's authorization and the host's supported scheduler;
these scripts create no recurring task. A ready report can contain qualified
partial evidence, explicit gaps or an abstention. Publishing a report does not
create a fill, human rating or future return.
