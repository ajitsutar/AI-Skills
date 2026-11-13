# Free public market evidence

Use scripts/market_sources.py to parse retained files and check when observations
were available. The normalize(document) and parse(document) operations are pure:
they never read paths or contact a service. A separate acquisition CLI downloads
one explicitly selected public file. All outputs set execution_authorized=false;
research evidence grants no order permission.

Relevant free sources come first. Every paid subscription is optional.
[The catalog](market-source-catalog.json) distinguishes implemented formats,
navigation links, supplied exports and unimplemented access. Unusual Whales is
SKIP_NOT_IMPLEMENTED: no REST/WebSocket adapter, API key lookup, feed entitlement,
trial or account enrollment is implemented.

## Clocks, provenance and revisions

Common synthetic input, not an observed market claim:

~~~json
{
  "schema_version": 1,
  "as_of": "2026-11-11T21:00:00Z",
  "records": [{
    "id": "fictional-vintage-1",
    "kind": "catalyst",
    "ticker": "DEMO",
    "available_at": "2026-11-11T20:00:00Z",
    "source": {
      "id": "fictional-source",
      "url": "https://example.org/retained-fixture",
      "retrieved_at": "2026-11-11T20:00:00Z",
      "published_at": null,
      "observed_at": "2026-11-11T20:00:00Z",
      "availability_basis": "first_observed_snapshot",
      "access": "public",
      "rights": "unknown"
    },
    "payload": {
      "title": "Fictional event",
      "event_type": "earnings",
      "event_at": "2026-11-12T21:00:00Z"
    }
  }]
}
~~~

Kinds: trade, bar, short_sale_volume, short_interest, float, borrow, catalyst,
social_lead, disclosure, ftd and venue_aggregate. Unknown envelope/payload fields
are retained. Each returned record has eligible and exclusion_reasons.
Eligibility checks identity, credential-free source URL (HTTPS or exact supported public FTP provenance), precise availability, source
clocks and revisions; it does not validate every payload measurement.
Downstream [flow analysis](market-flow.md) checks numerical comparability.

Unknown, date-only or future availability is unusable at the cutoff. First
observed retrieval may establish availability from that snapshot forward; it
cannot be backdated to a filing date, settlement date, filename, scheduled
posting time or reported acceptance timestamp. Published/source metadata and
rights are declarations, not authenticated point-in-time or licensing proof.
Keep unknown values unknown.

Optional envelope action=replace or action=cancel requires supersedes pointing
to an earlier record ID. A revision applies only when usable by cutoff and
strictly later than its target. Kind, ticker, source ID and source host must
match. Trade feed/trade ID, currency, units and issuer/share-class fields must
also match wherever either side declares them. Bar windows/session, feed,
currency, units, price/volume bases and issuer/class must remain compatible.
An invalid or future revision leaves the original usable. Equal timestamps are
unresolved order. Duplicate record IDs exclude every copy. Raw vintages remain
visible; generic revisions do not solve ambiguous amendment chains or implement
every exchange's correction protocol.

## Retained-source adapters

parse(document) accepts schema_version, as_of, source, adapter and text or data.
An explicit available_at is retained; otherwise a supplied precise retrieved_at
becomes first_observed_snapshot. Default IDs bind source URL/retrieval/content
vintage plus row number. Optional id_prefix explicitly names a retained vintage.
Optional security_context maps ticker to supplied issuer/class/adjustment
fields; those declarations are retained without inventing missing context.

| Adapter | Material | Preserved meaning |
|---|---|---|
| sec_daily_index | Whole official daily master index | Original row queue, CIK/name/form/filing date and constructed filing links; an explicit form filter and source-bound symbol mapping remain separate coverage choices. |
| sec_submissions | SEC columnar submissions JSON, or older history JSON with explicit cik | Form, accession, filing/report dates and primary-document link. Additional-history filenames remain unvisited. 13D/G ownership percentages are not extracted. |
| sec_form4_xml | Raw ownershipDocument XML | Transaction code, acquired/disposed flag, shares/price, XML snippets; owners/footnotes in adapter_metadata. |
| sec_13f_xml | Raw information-table XML, namespaces supported | CUSIP/class, quantity type, original value, put/call. No automatic ticker mapping. |
| finra_short_volume | Current pipe file with header and numeric trailer | Fractional shares preserved; trailer count reconciled. |
| finra_short_interest_csv | Official export CSV/pipe with supported aliases | Dated reported short shares, supplied ADV and displayed days to cover. |
| sec_ftd | SEC pipe text | Outstanding fail balance and settlement date; dot price is unknown. |
| venue_csv | Permitted export with explicit columns mapping | Venue aggregate, never individual prints or owner identity. |
| social_leads | Supplied JSON list | Syntactic canonical X URL, author and retained text/date; lead-only. |

Malformed delimited rows retain raw_fields plus parse_error and are ineligible.
Missing/inconsistent FINRA trailer excludes parsed rows. Every supported alias
for a field is reconciled, including differently punctuated headings that
normalize to the same name. Conflicting values make the row ineligible with a
parse error and preserve all original columns in raw_fields; no alias has silent
priority. Redundant aliases are usable when their parsed numbers or dates agree
exactly (or their trimmed text agrees). Unknown optional numeric values remain
unknown; they do not reconcile with a reported number. Identical literal headers
fail before parsing because a dictionary could discard one value. Unsupported
structures fail explicitly. XML DTD/entity declarations are refused.
Retain the whole raw source alongside per-transaction XML snippets.

For `sec_daily_index`, supply the whole master-index text and its exact source
URL. Optional `form_filter` is a unique nonempty list of form names; no filter is
applied by default. Include amendment names explicitly when they are needed.
Bounded explicit names may include single internal ASCII spaces, such as
`SCHEDULE 13G/A`; spelling, case, whitespace and duplicates are not coerced.
Original source-line IDs remain stable across filters, and the whole retained
row queue and per-form counts stay visible in adapter metadata. Malformed rows
remain failures. More than 10,000 emitted records require explicit downstream
partitioning. A well-formed file or filtered queue does not certify upstream
completeness or full U.S.-listed event coverage.

Optional `cik_symbol_mapping` maps canonical or padded CIK keys to objects with
`ticker`, precise `available_at` and `source` provenance. Ambiguous normalized
keys are rejected. Missing, invalid or future mappings leave the ticker unknown
and the row ineligible. A usable row cannot precede the mapping's availability.
Index/filing dates remain dates, and links constructed from accession fields are
marked unvisited. `raw_complete` is a transport declaration, not a proof that an
upstream index contains every filing. Acquire a selected submission separately
before making claims about its business content.

Index chronology compares date-only index metadata with the UTC calendar dates
of original precise capture/availability declarations, before any later symbol
mapping advances a row's availability. A date beyond those clocks is retained
as a contradiction and excluded. This is a necessary conservative check; it does
not infer an exact publication time, certify an EDGAR local-date convention or
authenticate a source. Conflicting top-level and source-level `raw_complete`
Boolean declarations likewise remain a qualification failure. Unknown completion
does not become a successful transport assertion.

The index adapter accepts the observed `File Name` heading alongside `Filename`,
the SEC Daily Index and Master Index descriptions, full or abbreviated English
received-month names, and compact or ISO filing dates. Raw headings and date text
remain available. An absent terminal newline is usable only when transport is
explicitly and consistently complete and every data row is well formed. Its
`terminal_newline_qualification` remains visible; unknown/partial/conflicting
completion or a malformed tail keeps the capture unusable. These format checks
do not certify upstream completeness.

Short-interest aliases include Settlement Date/settlementDate/Cycle Settlement Date,
Symbol/Issue Symbol/issueSymbolIdentifier/BATS-Symbol,
Current Short/currentShortPositionQuantity/Short Interest/# Shares Net Short Current Cycle,
Avg Daily Volume/averageDailyVolumeQuantity/Cycle Avg Daily Trade Vol and
Days to Cover/daysToCoverQuantity/Min # of Trade Days To Cover Shorts.
Issue Name/issueName/Security Name preserve the reported name. ISO and YYYYMMDD
settlement dates are accepted. Unknown headers are gaps. The separate
reported_days_to_cover field preserves the source's display convention.
Cboe cycle ADV and minimum trade-days display carry explicit source-reported
semantics; the minimum is never replaced by a newly divided ratio. Previous-cycle
shares, changes, split and manual-revision indicators remain intact in raw_fields.
Those indicators do not supply an adjustment basis, exact revision target or
ADV session window. Neither a settlement date nor a filename establishes when
the observation was published; retain unknown publication and actual retrieval.
No float, borrow inventory, share-class mapping or ADV-window compatibility is
manufactured. The flow module needs those inputs before comparable ratios.

For venue_csv, columns must map week_start, venue, shares and trades to exact
headers. Its symbol header must match a supported symbol alias. venue_scope
describes the supplied subset; it does not certify complete coverage or API
entitlement. Form 13F value_unit must be USD, USD_thousands or unknown; original
reported_value is never silently rescaled.

## Read the evidence correctly

SEC's [submissions API](https://www.sec.gov/search-filings/edgar-application-programming-interfaces)
needs no API key and updates as filings are disseminated. Recent history is
bounded. Retrieve older files or filing contents only when separately selected.
Filer CIK/tickers need not identify each transaction's issuer. Follow
[SEC developer guidance](https://www.sec.gov/about/webmaster-frequently-asked-questions)
and coordinate aggregate request rates across clients.

[Form 13F guidance](https://www.sec.gov/rules-regulations/staff-guidance/frequently-asked-questions-about-form-13f)
describes reporting lag and omitted short positions. A disclosed put is not proof
of net short stock exposure. [Format notes](https://www.sec.gov/files/form_13f_readme.pdf)
describe the January 2023 value-unit change. Keep the original filing/version
and units. For Form 4, transaction codes, footnotes, derivative terms and ownership
capacity matter; a disposal is not automatically a discretionary sale.

FINRA's [daily file](https://www.finra.org/finra-data/browse-catalog/short-sale-volume-data/daily-short-sale-volume-files)
is a defined trading subset. ShortVolume already includes exempt short volume.
Do not add that column again or combine overlapping facility/consolidated files.
Later revisions are possible; scheduled posting is not actual availability.
The observed November 11, 2026 file includes fractional quantities despite the
older integer-only layout text.
[Short interest](https://www.finra.org/finra-data/browse-catalog/equity-short-interest)
is a different twice-monthly position snapshot. Its
[glossary](https://www.finra.org/finra-data/browse-catalog/equity-short-interest/glossary)
also describes displayed days-to-cover conventions.

[SEC FTD files](https://www.sec.gov/data-research/sec-markets-data/fails-deliver-data)
contain outstanding balances with publication lag. Do not sum dates as daily
new failures, infer their age or treat them as proof of abusive short selling.
Missing rows are not filled with zero. Reported price can be unavailable and is
not a same-day execution price.

[FINRA venue totals](https://www.finra.org/finra-data/browse-catalog/otc-transparency)
are delayed summaries, not a real-time dark-pool tape. This module uses supplied
permitted exports and implements no authenticated FINRA API.
[Cboe's free listing](https://www.cboe.com/markets/us/equities/market-statistics/short-interest/)
covers Cboe-listed securities. Its observed cycle CSV headings are supported by
the short-interest adapter; an observed file verifies only that retained vintage,
not continuous availability or complete coverage of other listings.
Public readability does not establish commercial redistribution rights.

For X, use on-demand isolated browser access or supplied canonical posts. The
user's existing signed-in session may be needed. Anonymous access, complete
timelines, full text and continuous monitoring are not promised. Cards can be
truncated: retain the exact visible scope, URL, author, stated post date and
observation time, including unknown values. Verify claims against primary
filings/releases before treating them as catalysts. A supplied primary_verified
flag does not override NOT_ESTABLISHED_BY_SOCIAL_PARSER.

## Explicit bounded acquisition

Only acquire() and its CLI contact the network. Example PowerShell using an
already configured research-client contact string:

~~~powershell
python -B scripts/market_sources.py acquire --url "https://cdn.finra.org/equity/regsho/daily/CNMSshvol20261111.txt" --output-dir "$env:MARKET_RESEARCH_OUTPUT/capture-unique" --source-id "finra-cnms-20261111" --user-agent "$env:MARKET_DATA_USER_AGENT" --retries 1 --max-bytes 8388608
~~~

MARKET_RESEARCH_OUTPUT must be an explicitly configured absolute private research
directory outside the installed/public skill tree. Keep captures, manifests,
metadata and parsed results there. Its parent directory must exist; the unique
capture directory must not. Do not
invent a contact or discover/reuse the user's personal email. Missing configured
User-Agent is an acquisition gap; continue with supported browser access or
supplied files. No cookie, credential or authorization-header input exists.

Requests are credential-free HTTPS GETs to supported SEC submissions/filing/FTD,
FINRA daily-file and Cboe short-interest file families. Queries, fragments,
unsupported paths, nonstandard ports and redirects are refused. Landing pages
are navigation references, not download inputs. No automatic symbol/history crawl
or continuous polling occurs.

manifest.json retains returned bytes, SHA256, selected headers including ETag
and Last-Modified, statuses, attempt errors and actual retrieval clocks. Failed
reads retain returned prefixes; raw_complete=false is not a full response.
Denials, missing files and rate limits stop without retry/bypass. Only transient
errors get bounded retries. Defaults: 8 MiB, 15-second timeout, one retry.
Hard caps: 32 MiB, 30 seconds, two retries. These per-call limits do not coordinate
other clients or prove source completeness.

Use parse --input metadata.json --raw-file capture/attempt-01.raw --output parsed.json.
metadata.json declares the adapter, cutoff and exact source metadata copied from
the acquisition manifest. For ZIP add --zip-member selected-file.txt; no archive
paths are extracted. Raw and decoded-content hashes stay separate; expanded
member size is capped at 32 MiB. Never substitute an earlier date for observation.

Run python -B -m unittest discover -s tests -p test_market_sources.py -v.
Synthetic fixtures and mocked HTTP establish parser/error/eligibility behavior.
They do not prove live connectivity, rights, coverage, source truth, profitability
or completed participant cases.

## Configure sources for the intended deployment

Use relevant free sources whose terms cover the intended retrieval, retention
and processing. FINRA's [general website terms](https://www.finra.org/terms-of-use)
restrict AI use and bulk extraction; establish any applicable source-specific
permission or exception before configuring those materials as an automated AI
feed. Source parsers accept retained inputs without authenticating their license.
Cboe and other providers likewise require an intended-use review. Keep the exact
source agreement or unresolved qualification in private deployment records.
Existing user-provided licensed exports remain optional; no paid subscription
is required by the operating software.

The [operating commands](research-operations.md) retain configured source choices,
failed acquisitions and explicit freshness. An empty source configuration exposes
a coverage gap; it does not mean no market events occurred.


## Current SEC issuer identity

`sec_company_tickers` parses either official `company_tickers_exchange.json`
(fields/data table) or `company_tickers.json` (numeric-key object). Exact HTTPS
file acquisition is supported under `/files/` on `www.sec.gov`, with the same
privately configured SEC client contact. Preserve raw bytes/hash, the actual
retrieval clock and an explicit `raw_complete: true` declaration. Duplicate JSON
keys, malformed rows and conflicting completion flags cannot silently select an
identity. Plain ticker data do not invent an exchange or security classification.

To build a mapping, supply `schema_version`, `as_of`, parsed `records` and an
explicit unique `allowed_exchanges` list to:

```text
python scripts/market_sources.py identity-map --input MAPPING-INPUT.json --output MAPPING.json
```

`sec_identity.identity_map(document)` consumes one hash-bound source snapshot.
It emits `cik_symbol_mapping` only for unique usable CIK/symbol declarations in
the declared exchange scope. Multi-class CIKs, duplicate rows, shared symbols,
unknown/out-of-scope exchanges and unavailable vintages remain unresolved.
Exchange labels are supplied scope, not a closed built-in whitelist. A newly
observed exchange is retained rather than dropped by a historical list. The
mapping does not prove common-stock classification, complete U.S. listings or
historical membership. For `sec_daily_index`, include the resulting mapping in
`cik_symbol_mapping`; later mapping availability moves an index record's
availability forward. Never backdate it to a filing or measurement date.

## Explicit OHLCV exports

`daily_bars_csv` accepts permitted retained exports or separately retained
provider-decoded data. It creates no new price-provider entitlement or hidden
network request. Supply exact `columns` for `date`, `open`, `high`, `low`, `close`
and `volume`; optional `adjusted_close` remains a separate field. Supply the
explicit `ticker`, source clocks/hash and complete-capture declaration.

`bar_context` requires `feed_id`, `currency`, `price_basis`, `volume_basis`,
`adjustment_basis`, `comparison_group`, `volume_unit: "shares"`, an explicit
`role` (`current`, `baseline` or `benchmark`) and `sessions`, an object keyed by
ISO session date with exact aware `start_at`/`end_at`. Optional
`role_by_session` overrides only declared dates. Carry issuer/share-class
identity as supplied evidence. Use the actual exchange calendar, including early
closes; no normal open/close or currency is invented. Unknown share-adjustment
basis remains unknown; `auto_adjust=False` alone does not establish volume basis.

Each retained source row has two distinct facets: `cumulative` for interval flow
and `daily_volume` for ADV. Their common source-line pointer is explicit. Never
sum both facets or treat them as independent observations. Raw open/close price
context never substitutes adjusted close, and these daily bars are not execution
quotes or complete corporate-action history. Malformed quoting, invalid OHLC,
nonfinite values, duplicate dates, partial captures and unfinished/future
sessions cannot become eligible bars. Explicit supplied calendar declarations
are checked for consistency, not authenticated as exchange truth.

## Shared-public indicative borrow

`ibkr_shortstock` supports the documented retained `usa.txt` pipe format. The
configured research driver can perform one bounded request to the exact public
provenance URL `ftp://ftp2.interactivebrokers.com/usa.txt`, using IBKR's published
shared read-only access instructions. It never uses a personal account, broker
order interface or a password from the user. See the
[official public instructions](https://www.interactivebrokers.com/support/faq/content/monitoring-stock-loan-availability-1163250499).

Use a source entry with `adapter: "ibkr_shortstock"`, that exact `url`, explicit
`rights`, bounded `max_bytes`/`timeout` and `retries: 0`. No SEC User-Agent is
needed for this FTP route. Acquisition requires one RETR, actual FTP 226 transfer
completion, explicit SIZE handling and owned-client cleanup. Failed prefixes
and manifests remain retained; no HTTP success code is invented for FTP.
FTP is plaintext public transport and does not authenticate the supplied content.
The generic HTTPS acquisition command remains HTTPS-only.

The parser retains original rows, header, BOF clock, trailer and count. Exact
`AVAILABLE` digits become `shares_available`; `>digits` is a strict lower bound
with exact availability unknown. Provider fees/rebates remain raw with unknown
units, so no annualized fee is inferred. The BOF timezone remains unknown and
actual retrieval is the snapshot-observation clock. Currencies, masked ISINs and
missing FIGIs stay explicit. This describes one provider's indicative inventory,
not official short interest, utilization, a market-wide supply measure or a
borrow locate. Public access does not grant unrestricted redistribution or
commercial rights. More than 10,000 downstream records need explicit partitioning
or a source-bound selected event view; raw rows must never be silently truncated.

## Source-bound original parse jobs

`market_sources_report.analyze(request, manifest_path, manifest_sha256, source_root)`
is a pure local report producer for retained plain UTF-8 text/JSON. Through
`supplied_research.py` or a `final_report.py` source-report section, use:

```json
{"jobs_ref":{"source_id":"original-jobs","pointer":"/jobs"},
 "as_of_ref":{"source_id":"original-context","pointer":"/as_of"}}
```

Bind the complete original job list (up to64 jobs), not a literal reconstructed
subset. Each job retains its adapter, source declarations and other parser
configuration. Its `text_file` resolves relative to the original job JSON file
and must match exactly one pinned manifest path. The full manifest is verified,
including unselected context. No path search, external file import, acquisition,
archive extraction or inferred source metadata occurs.

An omitted `schema_version` is constructed as `1`, the installed parser interface
contract; it is not a source observation. An omitted `as_of` requires the explicit
original `as_of_ref`; otherwise the original aware job clock is used. When both
are present they must identify the same instant. A date-only cutoff, unsupported
version, conflicting inline text/data or raw hash, unsafe/missing raw path, or
literal request override cannot silently replace original evidence. Raw hashes
follow the native plain-file CLI convention. The `sec_submissions` and
`social_leads` adapters decode the bound JSON with the native numeric convention
after rejecting duplicate/nonfinite JSON values.

Every selected-list job appears in order with the original job, clock/envelope
construction, raw-source binding and complete native result or retained error.
`EXECUTED` means the parser returned: rows can still be ineligible with parse
errors, including conflicting aliases. Inspect those flags and retained raw
fields. Failed jobs remain `FAILED` while the remaining jobs run. This does not
certify source authenticity, whole-request completeness, separately authored
cross-checks, capture completeness or investment correctness.

### Automatic bound-context metadata fitness

With the existing `as_of_ref`, the producer also audits the whole original JSON
document containing that clock. `metadata_fitness` and its complete rendered
report section carry source hashes, JSON pointers, field states and qualified
findings. No new flag, reconstructed request or additional source selector is
needed. Without a clock reference it returns `NO_BOUND_CONTEXT`; unrelated corpus
sources are not searched. This does not replace analysis of the full request.

The single `HISTORICAL_DESCRIPTOR_V1` profile recognizes objects containing
`history_range` and either `roster_snapshot_at` or `revised_download_at`, regardless
of enclosing names or field validity. There are no aliases. `history_range` means
two ordered ISO calendar dates; snapshot and revised-download fields require
timezone-aware instants. `constituents` means nonempty unique declared strings,
not authenticated identities. `row_first_available_at`, `historical_membership`
and `revision_vintages` retain declarations without verifying rows or versions.
Absent, null, empty, boolean, malformed and insufficient-precision values stay
distinct. Nonempty evidence objects/lists remain `PRESENT_UNVERIFIED`; global
timestamps never establish per-row knowledge. Extra fields are unassessed.

The findings explain that a supplied roster does not establish historical
membership, download time does not establish earlier row availability, and this
metadata audit does not reconstruct earlier versions. Even complete declarations
remain unverified. No positive point-in-time, historical-universe, no-look-ahead,
authenticity or whole-request certification is emitted; no measured bias or
actual revisions are inferred. A generic `downloaded_at` is not treated as a
revised-download event.

Original values have `original_value_kind` and
`encoding: EXACT_ORIGINAL_JSON_TEXT`. Their `original_json` string contains JSON
text preserving exact original number tokens, including underflow, overflow,
large integers and signed zero. It is an explicit representation of the source
value, not a coerced numeric string or rounded `original_value`. Parse it
losslessly when inspecting numbers. Missing pointers have no invented value.

Traversal is limited to depth 8, 4096 encountered nodes and 32 descriptors;
displayed scope and extra-field inventories retain at most 64 entries, and a
field's JSON-text projection at most 16384 bytes. Limits report partial status,
counts, pointers and reasons; the complete source remains hash-bound. A field
projection exceeding its bound is omitted explicitly, never rounded. No matching
profile means `NO_SUPPORTED_DESCRIPTOR`, not evidence absence or complete coverage.
