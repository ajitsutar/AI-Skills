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
Eligibility checks identity, source HTTPS URL, precise availability, source
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
