# Repair historical coverage before a backtest

Use this guide when retained data has historical symbol, membership, filing or
session gaps. Preserve the requested universe and original artifacts. Write
source-bound repairs and a new coverage report; do not erase failed requests or
replace the old report with an unexplained smaller denominator. These research
checks do not add broker permissions or execution gates.

## Classify the gap before downloading

A provider query is not a permanent security identifier. Distinguish:

- Missing sessions while the security was listed and eligible.
- Dates before listing, after a verified membership exit, or outside the request.
- A pure symbol change for the same issuer and same share class.
- A merger, exchange offer, spin-off, share-class conversion or reused ticker.
- A source returning a different instrument, including an ETF under an old symbol.
- An erroneous historical membership row, uncertain date, or missing identity link.
- A missing filing/accession, missing extracted concept, or unknown publication time.

Keep unknown listing or membership bounds unknown. An empty expected-session set
is outside the stated scope, not evidence of complete history. A current roster
cannot silently replace historical constituents. Count expected sessions per
security/era using the supplied exchange calendar and dated scope, rather than
requiring a full decade from a recent IPO.

## Resolve identity and effective dates

Start with retained sources. Search issuer announcements, exchange notices and
original filings for the old/new symbols, exact effective date, issuer identifier
and common/preferred/share-class terms. SEC submissions `formerNames` and dated
filing covers can help find a historical issuer; a current ticker map or fuzzy
company-name match is only a lead. A CIK identifies an issuer, not an equity class.
A name match or unchanged CIK alone cannot certify price continuity.

Record a dated relationship with both endpoints, type, source artifact/hash and
reviewed fields. Only a supported same-security rename can link an old symbol to
an existing successor-query series without corporate-event accounting. Verify
that the successor series actually contains the needed earlier dates. Preserve
its original price/adjustment vintage. Acquirer prices, a reused ticker, or a
common label such as `common stock` cannot substitute for an acquired security's
terminal return. A merger ratio does not establish its payment date, cash-in-lieu,
or the shareholder's complete proceeds.

Use completed-transaction terms when they differ from the initial announcement.
Keep cash per predecessor share, successor-share ratios, contingent rights and
separate distributions in distinct fields with exact decimal values and source
locators. A contingent maximum is not cash received or a known current value.
Legal conversion creates an entitlement; it does not establish the date cash
became available for reinvestment. Preserve unknown settlement and fractional-share
treatment. Check record/ex dates and provider adjustments before adding special or
stub dividends, so the same distribution is not counted twice. A termination after
the close leaves that day's regular session intact; an uncertain intraday halt
must remain uncertain. Index removal, trading cessation and payment are separate
clocks. Do not fill a nontradable session with a fabricated trade.

An issuer-requested or expected pre-open halt is not proof that the exchange executed it.
Retain that clock as conditional unless an exchange notice, an executed-stop
statement, or explicit evidence that common shares had already converted before
the open establishes the full session as nontradable. A completed conversion
known only by date supports the next full exchange session; it does not exclude
the completion day. Keep requested same-day exclusions separate from the strict
set, including when reviewing inherited exclusion records. The administrative
delisting date may follow the trading halt. Bind the common or ordinary class:
a surviving issuer's filing may describe cancellation of a different company's
shares. A report/filing date is not the transaction's completion date. Read the
body's dated definitions and preserve source typos or conflicts with independent
corroboration instead of silently correcting them. If a newly proven stop overlaps
previously recovered prices, reconcile those rows as out of scope rather than
crediting both recovery and denominator reduction.

Keep issuer-level financial mapping separate from price/share-class mapping.
A valid old-name-to-CIK link can recover existing financial observations without
proving that two price series can be joined. Report unresolved ticker-to-CIK
links separately from absent issuer source bodies.

A holding-company conversion, spin-off or regulator change can create a different
financial reporting entity while a ticker persists. Bind each issuer or bank
regulatory identifier to its supported era. Preserve predecessor filings, successor
filings and later comparative statements separately; current successor facts do
not become the predecessor's historically available information.

Index admission is not implied by a corporate rename or merger. Verify index
announcements separately. Convert an explicit after-close change to the next
session when modeling trading eligibility; preserve the original wording and
clock convention. Check purported effective dates against the exchange calendar.
If an announcement table conflicts with its narrative, preserve both and explain
the selected interpretation; do not silently repair every holiday date.

For suspicious community changes, inspect the actual revision and row, including
issuer name, industry and linked identifiers. A ticker typo later corrected in
the same row is not necessarily an addition followed by removal. Quarantine the
false event with evidence while retaining the source. A revision timestamp is an
observation bound, not the index's effective date.

Retained community citations can lead directly to original index announcements.
When a PDF URL fails, an issuer-published HTML release may remain accessible.
Publication date/title can suggest an alternate URL, but a constructed URL is only
a discovery hypothesis: verify the returned document's title and actual contents,
including soft-error or unrelated-page responses. A retrieval date is not a
publication date. Preserve table row/column spans and bind each event's index,
action, ticker, effective date and clock to its own row or explicit narrative
scope. A matching ticker somewhere on the page does not corroborate the event.
Report exactly corroborated events separately from unmatched rows and unresolved
table/narrative conflicts; do not automatically rewrite the whole universe.

## Recover sources efficiently

Reuse verified existing compressed bodies and archive-member pointers within the
same frozen acquisition contract. Do not copy a full old archive or rescan and
reparse every object for each new ticker. A bounded `os.scandir` size inventory,
explicit in-flight write reservations, checkpointed requests and periodic full
reconciliation can reduce repeated filesystem work. Keep response-size, total
retention and free-space bounds; a cached size estimate alone cannot enforce a
shared concurrent budget. Full fetch remains the default for a new research run;
[partial-fetch](partial-fetch.md) is opt-in across Codex, Muse and Claude.

A missing Yahoo query is not proof that no history exists. Try a verified current
symbol for a pure rename, retained source variants, or accessible alternative
providers. For a public ZIP archive, selective member retrieval can avoid a large
full download: pin the archive revision, validate every HTTP206 `Content-Range`,
read its ZIP directory, bound compressed and expanded member sizes, and verify
CRC/hash. Reject servers that ignore Range or archive versions that change during
retrieval. Keep the native member and its archive provenance. This is an adapter
procedure; the storage helper does not itself implement remote ZIP ranges.

Check a public dataset's file listing before downloading its complete archive.
A provider may expose a small per-file endpoint even when its advertised dataset
is many gigabytes. Pin the dataset version and exact listed member path; encode
URL path segments once, preserving separators required by that endpoint. Verify
the returned file's identity, schema, date range, size and content hash. Retain the
native per-file response (including a small wrapper ZIP if supplied), metadata and
failure attempts. A full-dataset size is not the selected file's size. These are
provider-adapter procedures, not a generic selective-download feature of the store.

A per-file 404 may reflect a changed directory prefix in that historical version.
Inspect its own file listing or bounded ZIP central directory before declaring the
symbol absent. Version numbers alone can be ambiguous; bind the actual object
generation or immutable revision, ETag, total size and member path. Detect a plain
CSV versus a wrapper ZIP from the response content, not its filename. Validate a
selected per-file response against the pinned directory's length and CRC when
available, and retain its SHA256. CRC corroborates archive membership; it is not a
cryptographic substitute or proof that the complete archive was downloaded.

When selective transfer is unavailable but a compressed bulk source fits the
budget, stream it without expanding the whole CSV onto disk. Preserve selected
native header/rows with physical ordinals and full archive/member hashes. Audit
the selected bytes against the original stream before deleting a task-owned bulk
temporary; retain the provenance and cleanup receipt. Retrospective histories can
extend before a legal issuer/share-class existed, so date coverage alone cannot
clear predecessor identity ambiguity.

Public last-year tables can recover part of a delisted stock's history. Retain
original HTML, the exact table and an independent parser comparison, but label
its date limits. Partial rows, a successful request and full holding-period
coverage are different results. Honor rate limits and bounded retries. Do not
access premium history or bypass a browser/human check. Keep source histories
separate until adjustment basis, overlaps and corporate actions are reconciled;
a union of covered dates is not an approved return series.

For isolated daily gaps, inspect the issuer's public historical-quote widget.
An issuer Q4 `GetStockQuoteHistoricalList` response can expose dated Open, High,
Low, Last and Volume even when an aggregator's first-day close is wrong. Discover
the endpoint and parameters from the issuer's public page/widget, retain the
native response and receipt, and verify the requested date and security. A tax
basis computed from the day's high/low midpoint is not its closing price.

Map native field names explicitly, including case. For example, a supplied
`Volume` value must not disappear because an adapter reads only `volume`.
Retain the native field pointer, value, units and precision; reconcile duplicate
aliases rather than selecting one silently. Test absent, null, zero and positive
values separately. A mapping failure is not source unavailability, and a default
zero or null must not erase a reported small trade or clear its quality flags.

Public page JavaScript may expose a normal historical-price JSON request, such as
Quiver's `/stock/{ticker}/historical-prices/data/`. Treat this as a source adapter,
not a guaranteed service contract: verify its current schema, date frequency,
raw/adjusted columns, predecessor identity and neighboring observations. Do not
use authentication material or bypass premium access or human checks. When a
provider rate-limits parallel agents, coordinate a single retry queue and honor
the cooldown rather than multiplying requests.

A public Dolt archive can support small symbol/date queries without cloning the
whole repository. Retain the exact query, source commit, response and row locators;
split large date requests into bounded batches. A reused ticker may identify a
different issuer in an older date range. Reconcile that security episode and
overlapping native prices before joining it to any history. These methods are
optional targeted recovery paths, not new capabilities of the storage helper.

A chart payload may mix older weekly observations with recent daily observations.
Inspect the site's frequency semantics and date spacing; never expand weekly data
into fabricated daily rows. Preserve uncertain boundary dates as unqualified.
Do not manufacture open/high/low or zero volume from a close-only series.
Report daily close-only availability separately from OHLCV, exact volume and
certified adjusted total returns. A vendor label such as "adjusted" does not prove
dividend inclusion. Rounded displayed volume remains approximate, and visible
browser-table extraction remains distinct from a captured native HTTP body.
Independently check issuer identity and trading termination even when the source
has an apparently continuous tail; a provider may retain or splice unrelated
prices after acquisition. Keep invalid tail rows and their exclusion evidence.

Measure incremental recovery against the union of every retained source, including
source-bound rename pointers. Report new downloaded observations separately from
existing rows made reachable by a corrected identity link. Use security-era/session
keys when known; ticker/date-only counts remain explicitly conditional where ticker
reuse is unresolved. Do not add overlapping per-provider or rename gap counts.
Show eligibility corrections separately on both old and corrected denominators.

When deriving a new overlay from older normalized histories, recheck finite positive
prices, the OHLC envelope, duplicate dates, the session calendar and available
volume independently of stored flags. Inherited empty quality flags are not evidence that those checks passed.
Preserve rejected rows and their reasons in the new overlay without rewriting the
frozen source. If volume is absent, label that qualification separately; do not
present missing-volume evidence as positive-volume observations.

Public convenience panels can contain carried prices, synthetic no-trade rows,
modeled exit payments or spliced sources. Retain these flags and exclude them from
observed-price gap closure. Pin asset IDs, timestamps and content hashes; a mutable
release tag may point to code older than its refreshed data assets. Do not claim
producer-code reproducibility unless the asset-to-code binding is actually known.

## Store a compact daily research view

For daily or monthly backtests, default to daily observations; hourly downloads
add storage and processing without serving that requested frequency. Retain
intraday data only when the scenario needs it. A compact task adapter can store
source-separated Parquet with date, open, close and adjusted close, plus source,
security-era and quality references needed to interpret each row. Keep absent
fields null. Keep daily price values as float64 without rounding. Do not reduce
numeric precision merely to shrink files, merge adjustment vintages, or duplicate
a close into missing OHLC fields. Weekly bars never become daily observations.

Retain the original compressed bodies/member references and hashes, corporate
action records, source flags, adjustment basis and row locators. Keep any
high/low/volume evidence needed for validation in retained source artifacts or a
sidecar; compact projection is not evidence that these checks passed. Preserve
source-separated conflicting rows rather than picking a value merely to fill a
gap. Reconcile row counts, nulls, numeric values, date bounds and provenance
against the source before accepting a projection. Record its schema, codec,
input hashes and verification receipt; measure compressed retained size and
temporary working space against the shared cap.

Reuse hash-verified files within the same frozen acquisition contract to resume
or derive this view. A new-date research run still requires the opt-in
[partial-fetch](partial-fetch.md) contract before cross-run reuse; do not assume
Codex, Muse or Claude shares a cache, or splice a new price tail onto an old
adjustment prefix. Preserve originals unless the user-authorized cleanup has
audited retained evidence, source-to-projection reconciliation and explicit
deletion targets. The Parquet projection described here is a task-adapter
procedure, not a new generic downloader, price reconciler or storage feature
implemented by the existing helpers.

## Recover financial publication evidence

Compare expected filing accessions with the retained financial observations and
SEC submission/filing metadata. A fresh identical companyfacts response can still
omit a known recent filing. Target the original filing or issuer source when
needed; retain its native bytes and accession before extracting missing fields.
Preserve units, periods, contexts/dimensions, amendments and comparative values.
Neither a downloaded filing nor an accession match proves every valuation field
was extracted correctly. Bind publication/acceptance evidence independently of
fiscal period-end, and leave unavailable timestamps unknown. Do not promote a
current restated observation into an earlier investor's information set.
Match exact issuer and accession pairs. Replacement-like records can retain an
old filing date while carrying a different accession and later acceptance time;
never borrow that later record's timestamp for the original accession.

A failed direct HTTP request is not proof that a filing is unavailable. Try
authorized issuer or browser alternatives while honoring the host's isolation,
fallback and stop rules. A loaded page is not a captured native filing. Label
manual transcription or tool-extracted text separately, preserving its source,
fields and verification limits; do not count it as full native-XBRL recovery.

Public filing mirrors or financial-site filing CDNs can retain a complete original
inline-XBRL document when the SEC-origin URL or companyfacts feed is unavailable.
Use the exact issuer, accession and primary-document filename from retained filing
metadata to discover that copy. Preserve the mirror's native response, source URL
and hash separately from the original SEC URL; it is not a verified SEC-origin
capture merely because its path contains an accession. Check document identity,
report period, context entity, unit, scale, sign, dimensions and duplicate facts
before normalizing. Unsupported inline transformations remain rejected. Join
acceptance only through the exact filing's metadata. Mirror retrieval time does
not establish historical public availability, and recovering a body does not
resolve a missing original acceptance timestamp.

Joint filings can describe a parent and separately registered subsidiaries.
The root context CIK alone may not identify the entity represented by a fact.
When native DEI facts explicitly bind a CIK to a legal-entity dimension, preserve
that binding, root identifier, exact axis/member, source context and ambiguity.
Reject conflicting or incomplete entity bindings. Keep extra dimensions
disaggregated; do not relabel parent totals as subsidiary totals or discard the
original context to make a ticker join succeed.
An explicit subsidiary reporting scope is not the listed parent equity.
Resolve the equity issuer's dated legal chain separately, particularly through
bankruptcy or holding-company changes. A PDF annual-report reproduction can fill
document availability without supplying native inline-XBRL or extracted facts;
verify its actual cover, report period and form because an annual-report link can
return a proxy or a different year. These are adapter/review procedures, not
features implemented by the generic metadata join helper.

Line numbers in combined web extracts are local to each source document.
Bind each derived fact to the original document URL, its block within the retained
extract, the local line/table/row and a unique numeric cell. The combined extract
hash alone cannot distinguish repeated line numbers from different filings.
Reconcile the issuer, accession, period, units, sign and scale within that same
document before joining filing metadata. Reject ambiguous or duplicate cell
matches. Preserve failed extractions and their reviews; add a corrected version
and an adversarial regression with colliding line numbers across two documents.
This is a source-adapter validation procedure, not an automatic repair performed
by the generic financial metadata helper.

For a retained metadata join, use the helper's `--mode filings` with JSON fields
`facts` and `filings`. Facts provide `issuer_id`, `accession` and optional `filed`;
filings provide the same identity pair, `acceptance_at` with timezone, optional
`filing_date`, and `source: {ref, sha256}`. The output preserves exact matches,
missing pairs and conflicting dates/times. It reports acceptance as acceptance,
not certified public availability. The Python API is `join_filing_metadata`.

## Portable date-coverage audit

`scripts/historical_coverage.py` audits explicit, source-referenced declarations.
It does not fetch data, authenticate a review, infer aliases, normalize prices,
stitch returns, or certify a complete point-in-time dataset.

```text
python scripts/historical_coverage.py --input contract.json.gz --output coverage.json.gz
```

The input schema is demonstrated by
[fictional-historical-coverage.json](../examples/fictional-historical-coverage.json).
Use a sorted unique session grid; requested securities with explicit issuer/class
IDs and membership/listing intervals; source series with original source refs and
SHA256; and dated typed mappings with evidence and review status. Intervals are
start-inclusive/end-exclusive. Explicit `quality_excluded_dates`, duplicate dates
and missing/nonpositive/nonfinite adjusted prices are not counted as usable.
For each observation, adapters must map source flags to `observation_role`:
only `observed` can contribute usable dates. Other roles (including unknown,
carried, synthetic and modeled terminal values) are excluded and reported under
`non_observed`. An omitted role defaults to the caller's observed declaration;
it is not source authentication. Preserve uncertain flags rather than omitting them.
A native source reference is mandatory for a qualified mapping. Evidence fields
are checked for structure only; the caller must verify the underlying sources.
Bind the calendar with `calendar_evidence` witnesses and `calendar_reviewed`;
without that declaration, even fully covered listed dates remain conditional.

Only reviewed `same_security` and `same_security_rename` declarations with matching
nonempty issuer/class IDs can contribute identity-qualified dates. Merger,
spin-off, class-change and ticker-reuse mappings remain rejected for this operation.
Unknown eligibility bounds produce conditional/unassessed coverage. The output
keeps missing sessions, rejected mappings, source segments and source quality
separate; it explicitly flags when only a multi-source union covers the dates.
Never describe its `DECLARED_REVIEWED_DATE_COVERAGE` result as verified returns,
complete corporate actions or certified point-in-time data. Terminal proceeds and
financial timing are separate review dimensions even when all dates are present.
The CLI accepts bounded JSON/gzip input and refuses to overwrite an output.

## Close out with evidence

After the scoped collectors are idle, reconcile the exact final identity/query
sets and source hashes across membership, prices and financials. Validate native
to normalized values, not just file presence. Bind final audits to that snapshot.
Distinguish no pending requests from no missing data. Write a successful final
status only after archive/manifest, coverage and storage checks succeed; preserve
a failed finalization as such. Count preserved archives and every new partition
under the user's retained-data cap. Report before/after gaps on the same stated
denominator, separating changed eligibility, corrected identity links, recovered
observations and unresolved historical uncertainty.


## Reconcile returns separately from price coverage

Never join independently adjusted price endpoints across sources. Bind both ends
of a consecutive-session return to one source vintage, share class and dated
security era. Require a deliberate whole-edge choice when sources overlap; a
matching close does not establish that their opens, adjustment factors or
dividend conventions are interchangeable. Missing edges remain missing.

A column named Close does not by itself establish raw, as-traded prices.
Check the native source's field and adjustment basis before using an overlap as
an identity fingerprint. A basis mismatch is not automatically an issuer or
share-class mismatch. Predeclare the comparable reference source family, field
and selection rule before inspecting which values match; retain failed original
comparisons. Do not choose a reference, rescale prices or change tolerances merely
to obtain a passing match. Agreement on one close basis does not qualify adjusted
returns or authorize mixing fields across sources.

Distinguish split-adjusted closes, raw closes, provider distribution-adjusted
returns, and cash-inclusive ex-date reinvestment. For split-adjusted closes,
cash return is `(close + distribution) / prior_close`; applying the split ratio
again double-counts the split. Raw-price calculations also require an explicit
split and distribution share basis. A simultaneous split/dividend needs that
unit check before calculation. Ex-date reinvestment is an analytical convention,
not evidence that cash was available in the account on the ex-date.

Test the source's adjustment convention against retained actions. A backward
distribution factor `1 / (1 - dividend / prior_close)` differs from cash
reinvestment `1 + dividend / current_close`; do not force all archives to match
one formula. Treat an empirically observed convention as source-scoped unless
provider documentation establishes broader scope. Preserve the tolerance and
failed hypotheses. Do not fit implied dividends or loosen tolerance to make
an unexplained factor pass.

When an archive has unexplained adjustment-factor discontinuities,
screen the other symbols and dates from that source family instead of treating the first
examples as an exhaustive exception list. Native Adj Close ratios are not
cash-return evidence merely because the field is populated or nearby Close
values match another source. Keep unexplained boundary returns missing until
source-scoped action and basis evidence resolves them; do not promote the whole
adjusted series on the strength of unrelated valid observations. This requires
an explicit source-adapter audit, not a capability implied by the generic
coverage helper.

Flag distributions dated on exchange holidays/weekends, duplicate cash events,
and unexplained factor changes. Inspect adjacent session edges as well as the
event row. A source-bound event correction may reconstruct cash returns from
independently documented amounts/dates and valid same-source closes while
quarantining the provider's inconsistent adjusted returns. Keep original rows,
actions, failed attempts and corrections separate; do not add the dividend to
an already dividend-adjusted return. Vendor ex-date evidence and issuer
declaration/record/payment evidence have different roles and must be labeled.

After a merger, inspect ordinary dividends as well as special payments. A vendor
can attach both predecessors' cash schedules to one predecessor's price history.
Reconcile issuer identity, exact quarterly amounts and annual payment totals;
retain the vendor ex-date separately from issuer record/payment evidence. Correct
rounded cash amounts only from documented values. Tax classifications such as
capital gains or return of capital are components of a payment, not extra cash.

A distributed share entitlement can exist before its first quoted market. Keep
the parent and child share counts explicit, but leave whole-position NAV unknown
until an observed when-issued or regular-way price is available. Reinvesting a
parent cash dividend changes parent units, not the already fixed child entitlement.
An endpoint bridge can support an annual calculation while daily valuations remain
missing. Do not fill that interval with zero, a later child price or a tax-basis
estimate presented as an observed trade.

## Integrate quote and return repairs

### Keep observed prices, reference marks and estimates distinct

Zero numerical valuation gaps do not establish verified market-price coverage.
When the user requests a complete valuation scenario, add an explicitly selected
layer alongside the strict reader. Preserve observed closes, source-reported
reference marks, halt carries and retrospective estimates as separate roles with
their own source or method, dates, precision and uncertainty. Retain precise native
marks when a rounded second source corroborates them; preserve conflicting marks
without silently replacing either. A completed valuation layer does not upgrade
strict coverage or establish execution availability. Do not manufacture opens,
highs, lows or trading volume from a close/reference value.

Try bounded exact-source recovery before an authorized last-resort estimate.
Retain the verified listing/eligibility start even if a provider's first quote is
later. Bind each estimate to its anchors, method and affected dates/return edges;
do not extrapolate across an unsupported security or corporate-action boundary.
A plot's exact tooltip/data point may be source evidence, while a pixel reading
or interpolated line remains an estimate with stated precision. Future-anchor
backcasts and interpolation are retrospective valuation assumptions, prohibited
as historical decision features or executable prices. A model cannot create
an observed trade during a verified full-session halt. Report the modeled count
and the remaining strict observations/return gaps separately, including unresolved
entitlement values. Recompute both adjacent edges in the selected valuation
scenario without overwriting strict unknowns or corporate-action wealth paths.

### SEC settlement-failure reference prices

SEC fails-to-deliver (FTD) PRICE is the reported previous-day closing reference,
not the settlement-date close or the price of the originating failed trade.
Bind the exact common-share CUSIP and historical symbol, retain the settlement
date, and review the prior-session mapping against the exchange calendar and
nearby known prices; do not subtract the trade-settlement cycle mechanically.
FTD quantity is an outstanding settlement-failure balance, not daily trading volume.
Missing rows do not prove missing trading, and reference prices do not establish
an executable open/close bar. Preserve source precision and disagreements with
other providers; the SEC does not guarantee price agreement or overall accuracy.

Keep publication separate from reference and settlement dates. The SEC publishes
half-month files later; its schedule is approximate, not an observed availability
timestamp. An FTD reference recovered later can corroborate a retrospective
valuation, but must not become a same-day historical strategy feature. For a
public mirror, retain its revision, native bytes or validated byte ranges, exact
row locators, hashes and transformations. Label it as a mirror unless original
SEC bytes are independently reconciled; an SEC attribution or matching row count
does not verify the original archive. These are source-review procedures, not an
FTD downloader or a new capability of the generic coverage helper.

A corrected quote affects both adjacent return edges. Check compatible price
units, cash events and simultaneous corporate actions before recalculating them.
Keep explicit distribution or predecessor wealth paths ahead of naive close
ratios, and flag any later quote correction that requires those paths to be
regenerated. A quote-only predecessor prefix does not extend a return file:
construct its edges from a supported cash/split model or report them missing.
Never assume missing event metadata means zero distributions.

Use dated exchange halt records and venue-transition evidence to distinguish an
unobserved quote from a session without execution. An exchange suspension can
coexist with OTC trading; zero vendor volume alone proves neither outcome. Keep
nonexecution and stale-valuation policy separate, with null returns unless a
specific valuation convention is declared. Do not splice cancelled pre-bankruptcy
common shares into newly issued common merely because a ticker history is continuous.

Hash-check nested source bodies, event records and receipts referenced by an
overlay, not only the overlay file itself. Bind those dependencies in the reader
manifest or require the separate recursive audit explicitly. Validate finite
positive prices and the supplied OHLC/volume qualifications before admitting a
repair; do not clear inherited flags merely because an overlay row exists. Test
quote coverage and return-edge coverage separately against each security lifetime.

## Enforce financial availability and extraction boundaries

SEC acceptance is not automatically the public dissemination time. Bind facts
to the exact issuer, accession, form, filed date and available acceptance record.
Keep date-only or conflicting metadata explicit. Where publication precision
is unavailable, a documented next-session rule after the later relevant filed
date is a conservative simulation assumption, not proof of an exact timestamp.
Do not use an earlier acceptance proxy to bypass a later filing/dissemination
date. A later amended or comparative filing cannot lend facts or its corrected
content to an earlier accession's availability time.

Before reading an empty financial Parquet file through a table/dataset API,
inspect its metadata. A valid zero-row file represents no observations; retain
that state rather than crashing, fabricating facts, or silently counting the
issuer as covered. In joint filings, parse requested-issuer contexts explicitly:
another entity's valid inline facts do not close the requested issuer's gap.
Measure required feature availability at actual rebalance dates, including
lookback, units and period type; a large aggregate fact count is not readiness.

## Recover grouped historical index announcements

Older official index tables may group several additions/deletions beneath one
date cell. Carry a date only within the table's demonstrated grouping; do not
carry it across a new heading or another announcement. Preserve row locators
and corroborate company-name rows against exact ticker witnesses in the same
release. A corrected URL or recovered table is useful only after its body
confirms the index, effective date, action and security. Keep uncorroborated
community dates and revision timestamps explicitly separate from primary
effective-date evidence.


## Follow-up audit boundaries and efficient repair

A physical HTML table can contain several index/date subsections. Reset inherited
index, date and action at every internal heading, including an out-of-scope index.
Bind each credited row to its nearest applicable heading. Cross-check explicit
index-effective clauses separately from deal completion or spin-off dates in the
same paragraph. A table/narrative conflict remains a conflict; do not resolve it
by finding the proposed date anywhere in the release. Where the publisher
explicitly names the correct session and a market closure, a separately reviewed
narrative-supported correction may be used while retaining the contradictory
table. Never round a non-session table date forward without that evidence.

An upstream vendor tag is not sufficient action or identity provenance. A public
redistributor may infer dividends from adjusted prices or returns, carve a new
label out of another series, rescale historical prices, or insert synthetic
no-trade carries while retaining the original vendor tag. Bind its correction,
carve, splice and non-trade ledgers as well as the data snapshot. Quarantine
declared patch dates and adjacent edges until reviewed, even when a patch may
not have been applied. Finite-price arithmetic alone does not establish a valid
trading observation; keep unavailable/nonfinite volume distinct from actual
zero volume and require an explicit source policy before either is admitted.
Publisher self-consistency tests do not constitute independent source validation.

Measure missing financial features before downloading again. Total operating
cash flow and continuing-operations cash flow are different reported measures;
retain separate names, periods and provenance. Sector-specific revenue and cash
flow definitions require a declared strategy policy, not silent substitution.
An absent comparable feature can be a reporting-scope limitation even when the
filing is retained. Missing-feature exclusions must be disclosed and tested for
coverage-selection bias, especially near the beginning of a long backtest.

For an incremental repair, verify frozen input hashes once per immutable input
within the run, reuse unchanged hash-verified partitions, and rebuild affected
partitions only. Do not repeatedly hash a large native archive for every ticker
or row. Invalidate the cache after any mutation or changed input identity; do not
reuse an unverified hash merely because a path is unchanged. Keep full-fetch mode
available when no trusted cache exists. Deduplicate byte-identical archives only
after verifying the retained canonical copy and migrating active references;
preserve source-vintage receipts and an explicit old-to-retained hash mapping.


When projecting SEC Financial Statement Data Sets into issuer aggregates, inspect
all available dimension fields. An empty `coreg` does not establish an aggregate:
a newer `num` file can still have a nonempty `segments` field. Require the source
format's explicit nondimensional aggregate conditions, preserve excluded segment
facts separately, and test a unique segment-only value as well as aggregate/segment
duplicates. Do not turn an excluded segment value into a missing aggregate filler.


SEC FSDS NUM.ddate is rounded to the nearest month end. NUM.qtrs is rounded
to a whole-quarter count; zero denotes an instant, not an exact duration. Keep
these source fields and their precision separately from exact XBRL context dates.
Do not infer an exact start by subtracting quarters, treat a rounded end as the
actual fiscal date, or merge such rows into an exact-period series on that basis.
Prefer the original filing context when exact period comparison is required.
If a replay requires an end-date eligibility bound before exact context recovery,
use a documented conservative upper bound supported by the source rounding rule
and retain its uncertainty; a policy bound is not an observed reporting date.
Keep reporting-period eligibility separate from filing acceptance/publication
availability, and label any approximate-period comparisons explicitly.
