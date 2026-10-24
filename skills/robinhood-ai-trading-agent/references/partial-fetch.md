# Optional partial fetch from a portable research bundle

**Full fetch is the default.** Partial fetch requires an explicit user request
and an explicitly supplied portable bundle. This applies identically to Codex,
Muse, Claude and other hosts. Never assume their internal caches persist, inspect
hidden model memory, discover unrelated archives, or treat a prior recommendation
as current evidence. A host without the files, Python runtime or source adapter
must fetch fresh with its available tools and disclose the limitation. The skill
does not configure another product's cache or guarantee a speedup.

This collector can skip unchanged quarterly `income`, `balance` and `cashflow`
components. It always reacquires current membership, quote/company `info`, and the
entire requested price history with corporate actions. Adjusted-history revision
reconciliation for tail-only downloads is not implemented, so price tails cannot
be safely reused by this route. Estimates/revisions, news, guidance and calendars
still require current collection through the research cutoff in the normal
candidate review; this helper does not collect them or certify their freshness.
Rerank the full current universe and peer groups, including newly added names.
Old conclusions and score orders are not reusable current recommendations.

## Commands

An ordinary call remains a full fetch:

```text
python scripts/public_research_fetch.py --output /research/new-run --decision-at 2026-10-22T20:00:00Z --hold P1Y --prompt-file /research/prompt.txt --universe-preset sp500
```

After explicit opt-in, supply a parent library root, its sealed manifest and
current source checks:

```text
python scripts/public_research_fetch.py --output /research/new-run --decision-at 2026-10-22T20:00:00Z --hold P1Y --prompt-file /research/prompt.txt --universe-preset sp500 --partial-fetch --reuse-from /research/parent --reuse-manifest /research/parent/manifest.json --freshness-receipt /research/current-checks/checks.json
```

The preset here illustrates an explicitly scoped S&P request. Unspecified stock
discovery still uses the mandatory U.S.-listed default. Every output is a new
directory; no parent bytes are edited. Missing flags/files, incompatible profiles
or mappings, corrupt archives, absent component provenance and inadequate current
checks cause fresh acquisition for the affected scope. They do not permit stale
substitution if fresh acquisition fails. Inspect `partial-fetch-receipt.json` and
`snapshot.json` for actual reuse counts, reasons, original retrieval times and
parent/component/receipt hashes. An enabled mode does not mean any cache was reused.

`--resume` retries failures of the same frozen collection. It is not a new-date
refresh and cannot be combined with partial-fetch/source-check flags. A new
collector version cannot resume an older collector's bound code contract; use the
saved collector for that run or start a new run.

## Establish a usable baseline

Ordinary older snapshots lack complete source-index provenance. They remain
valid research archives but cannot qualify for statement reuse solely by adding
a new timestamp or manifest. A source adapter or reviewed extraction must retain
the actual SEC/issuer/provider index evidence that maps to **all** retained periods
and the provider statement representation. It must check newer periods, revisions,
amendments and restatements, including revised comparative periods. A generic
issuer homepage, unchanged quote, TTL, file age or an asserted `unchanged` flag is
insufficient. If the source cannot establish the provider representation is
unchanged, omit the check and download that statement again.

During a full acquisition, `--freshness-receipt` alone can bind qualifying source
checks to newly downloaded statement bytes. It skips no downloads. Checks whose
component hashes or source metadata differ from the fresh data are not attached.
The receipt mode is `full_fetch_with_optional_source_checks`.

Seal the resulting snapshot and every referenced `incremental-evidence/*.source`
file with `research_memory.py seal`; use artifact kind `snapshot` for exactly one
snapshot and `filing` for its source-index evidence. Retain the mandate, source
mapping and other evidence in the library too. The manifest must verify every
listed file before reuse; preserve the resulting library immutably outside the
skill and public repository. See [research memory](research-memory.md).

## Current source-check receipt

The source adapter supplies UTF-8 JSON with `schema_version: 1` and `rows`. Every
row has the current `symbol`, exact `issuer_id`, exact `provider_symbol` and a
`components` object with any eligible statement checks. Do not write fictitious
source checks to enable reuse. This fictional abbreviated example shows `income`:

```json
{
  "schema_version": 1,
  "rows": [{
    "symbol": "DEMO",
    "issuer_id": "fictional:demo",
    "provider_symbol": "DEMO",
    "components": {
      "income": {
        "component_sha256": "CANONICAL_COMPONENT_DIGEST",
        "metadata": {
          "provider": "yfinance-quarterly",
          "currency": "USD",
          "units": "currency_units",
          "periodicity": "quarterly",
          "scope": "consolidated",
          "mapping_basis": "Describe the retained source-to-provider period and revision mapping"
        },
        "source_index": {
          "source_url": "https://issuer.example/filings",
          "checked_at": "2026-10-22T20:01:00Z",
          "periods": ["2026-06-30", "2026-03-31"],
          "latest_period": "2026-06-30",
          "review_scope": "latest_period_and_all_retained_revisions",
          "releases": [
            {"period": "2026-06-30", "release_id": "filing-id-2", "revision_id": "document-hash-2", "amendment_status": "none"},
            {"period": "2026-03-31", "release_id": "filing-id-1", "revision_id": "document-hash-1", "amendment_status": "none"}
          ],
          "evidence_path": "captured-index.html",
          "evidence_sha256": "SHA256_OF_RETAINED_INDEX_BYTES"
        }
      }
    }
  }]
}
```

`component_sha256` uses `research_memory.digest(component)` (canonical JSON),
not the hash of a formatted JSON file. Source evidence hashes use raw file bytes.
Paths are portable relative paths under the receipt's parent directory; parent
evidence paths are under the sealed library root. Escapes and symlink escapes are
rejected. Every statement column needs a unique matching source period. Release
and revision IDs must be meaningful source identifiers/hashes, not a guessed
constant. Amendment status is `none` or `incorporated`; unknown/incomplete checks
force fresh collection. A newly incorporated amendment changes the release/revision
contract and therefore forces fresh collection too.

The parent snapshot must already bind the prior source check under
`component_source_checks`, the original `component_retrieved_at`, and the same
component bytes. The current check must match the parent release/revision history,
period coverage, provider, currency, units, scope and source mapping. Current
`checked_at` must have a timezone and lie between the new `--decision-at` and the
actual collection check time. Set a truthful current decision timestamp and capture
checks within this research run; do not backdate observations. Parent checks must
fall inside the retained parent collection window. Current company info reporting
a changed financial currency also invalidates statement reuse.

This is an interface for retained source observations, **not an automatic filing
index extractor**. The helper verifies source-file bytes, declared mappings,
timestamps and matching release/revision contracts; it cannot prove an arbitrary
HTML document supports an adapter's extraction or that a publisher is correct.
Review those mappings before supplying checks and retain uncertainties. An issuer
index alone may not establish that Yahoo corrected an extraction; absent a reliable
mapping of such revisions, fetch fresh. A source-check hash is not independent
source validation or point-in-time certification.

## Reporting and cross-model use

Label any actual reuse as shared/incremental acquisition. Keep the original
component retrieval time distinct from the new check time, and distinguish full
network collection, mixed collection, same-contract resume and frozen replay.
Shared bytes cannot establish independently acquired agreement. Full fetch also
does not by itself establish independent model research if inputs or judgments
were shared. Never send another participant's picks or correctness feedback to
force agreement. See [model-independent research](model-independent-research.md).
