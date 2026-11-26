# Filing and exhibit content

Use `scripts/filing_documents.py` when earnings/guidance or event research needs
the filing's actual language, the attached release, or selected Schedule 13D/G
ownership fields. The host assistant selects documents, interprets passages,
checks source identity and clocks, and writes the answer. The helper supplies
source evidence; it does not certify prose, infer investment conclusions, or
decide whether guidance increased, decreased, was withdrawn, or remains current.

## Assistant-operated route

For multi-issuer screens, use the [batch filing workflow](financial-normalization.md#research-a-set-of-finalists).
It accepts nightly archives, resolves the original documents for each CIK and
records verified and unverified outcomes across the complete request.

1. Resolve the issuer and accession with available native sources or the existing
   SEC research helpers. Open the specific filing and its exhibit index. Record
   filing acceptance, report/event period and retrieval time separately. A filing
   date is not its public-release or event time.
2. Acquire the individually selected primary document and relevant exhibits with
   the host's authorized native tools, or the optional explicit fetch below.
   Keep original bytes and source URLs in an external run directory. Neither
   search snippets nor an exhibit link alone are exhibit content. An unavailable
   exhibit stays an unresolved source need.
3. Extract the acquired bytes. Review the complete passages and adjoining tables,
   footnotes and definitions. Headings and lexical matches are navigation aids.
   When boundaries are ambiguous, read the retained document through native tools
   and provide source locators rather than inventing a supported parse.
4. For earnings/guidance, distinguish actual results from forecasts, current from
   withdrawn or superseded ranges, and GAAP from adjusted measures. Establish
   fiscal period, currency, unit, share basis and reconciliation. A phrase match
   never establishes these facts. Pass selected observations into existing
   source/numerical workflows only after this reading.
5. For 13D/G, retain each reporting person's stated class, shares, percent, powers,
   exclusions and comments. Missing means unknown. Shared/deemed holdings can
   overlap: never sum persons to invent a group position. Do not infer purchases,
   activism, control intent or a change in ownership from the form name or one
   amendment. Read the relevant narrative and earlier filings when needed.

Ordinary requests require no user-written JSON. The assistant prepares any helper
metadata and performs review/correction through the research workflow.

## API and locators

```python
from filing_documents import extract_document, ingest_document, fetch_document

report = extract_document(
    raw_bytes, source_id="issuer-8k-release", form_type="EX-99.1",
    source_url=selected_document_url, accession=selected_accession,
    accepted_at=acceptance_time, retrieved_at=retrieval_time,
    content_type="text/html; charset=utf-8", passage_terms=["revenue", "EPS"])
```

`extract_document` is pure and never fetches URLs. `ingest_document(input_path,
run_dir, **metadata)` reads only the named file, creates a new external directory,
and writes `original.bin`, `acquisition.json`, and `extraction.json`. It refuses an
existing directory or output inside the installed skill. Bytes and their SHA256
receipt survive extraction failure. These are application-level no-overwrite
artifacts, not a filesystem immutability guarantee.

The schema-1 report has `identity` with explicitly caller-supplied identity and
clock fields, `raw_sha256`, `raw_byte_length`, `normalized_text`, `item_passages`,
`exhibit_links`, `candidate_passages`, `ownership_facts`, `ownership_metadata`,
`amendment_status`, and `limitations`. Supplied identity is not independently
verified merely by parsing or downloading a page.

- `passage` contains `text`, zero-based half-open `start`/`end`, and coordinate
  system `normalized_text_unicode_codepoints`. Slice the report's exact
  `normalized_text[start:end]` to reconstruct it. These are **not raw-file byte
  offsets**. Normalization changes whitespace and removes selected HTML blocks.
- Ownership fields contain `value_as_reported`, including original numeric
  strings, and `status` (`as_reported` or `missing_unknown`). Their locators give
  an absolute element `path` plus `namespace`; apply that namespace to every
  path component when resolving against `original.bin`. The person index selects
  that specific repeating person element. Comments and issuer share-class/unit
  context are retained; numerical validity is not certified.
- `exhibit_links` retain `href_as_reported`. A resolved HTTPS link includes `url`,
  `resolution_status: resolved_https`, and the existing
  `discovered_not_fetched_or_verified` status. Supplied relative links without an
  HTTPS base remain discoverable with `unresolved_without_https_base` and
  `discovered_unresolved_not_fetchable`; they have no `url` field. The assistant
  must resolve them from the actual filing index or independently select the
  exhibit. This never reads a neighboring local file or fetches automatically.
  Unsafe explicit schemes are excluded with a limitation warning. Every selected
  exhibit still requires its own acquisition and source ID.
- `candidate_passages` are `lexical_candidate_requires_semantic_review`; at most
  100 context ranges are returned and full normalized text is retained. Missing
  matches do not prove absence of guidance. Up to 30 optional search terms can
  supplement the default navigation terms.

## Optional explicit acquisition

```text
python scripts/filing_documents.py selected-release.htm /external/run/release --source-id issuer-release --form-type EX-99.1 --source-url SELECTED_URL
python scripts/filing_documents.py EXACT_SEC_ARCHIVES_DOCUMENT_URL /external/run/sec-release --source-id issuer-release --form-type EX-99.1 --fetch
```

`fetch_document(url, run_dir, *, source_id, form_type, user_agent=None,
**metadata)` needs an identifying User-Agent supplied privately by the caller or
the caller's `AI_TRADING_SEC_USER_AGENT` environment variable. Do not ask the user
to paste private contact into a chat or inspect unrelated contact configuration.
No contact/header/environment values are written to receipts or error messages.
Without an authorized contact or network capability, use host-acquired files.

The optional fetcher accepts only exact HTTPS `sec.gov`/`www.sec.gov`
`/Archives/edgar/data/CIK/18_DIGIT_ACCESSION/document.{htm,html,txt,xml,pdf}` URLs.
It rejects query/fragment URLs, traversal, encoded paths, alternate ports, viewer
links and redirects. Select the final archive document explicitly; no redirect
or denial workaround occurs. It makes one request, uses a 30-second socket
timeout and checks elapsed time between reads, caps the body at 10 MiB, and does
no automatic retries or exhibit crawling. Coordinate all SEC tools in the host
to respect aggregate fair-access limits. `AI_TRADING_NETWORK_MODE=offline` stops
the request before network/output creation. A recognized standalone denial or
human-check page shell is retained as bytes but is not extracted as filing
evidence. Merely quoting an error such as “Access Denied” inside an incident
disclosure does not discard its text. Browser acquisition,
if used by the host, retains that host's isolation/authentication policy.

## Supported subset and limits

- HTML/plain-text 8-K and 8-K/A: recognizable line-start item headings, actual
  bounded section text and exhibit-link discovery. Repeated item codes (including
  a duplicated contents page) and recognized combined item headings explicitly
  withhold automatic item boundaries while retaining full normalized text for
  host reading. Other markup may also need host reading. Table presentation is not a
  financial-table parser. Hidden/style/script filtering is not full browser
  rendering, CSS computation or an XBRL numeric transformation.
- Individual HTML/plain-text releases: full normalized text and candidate
  passages, including withdrawal and cautionary language when present in the
  selected range. All surrounding qualifications still require reading.
- SEC Schedule 13D and 13G XML: source-bound cover-page person fields with the
  two distinct schema layouts, issuer class/CUSIPs, event-date field, amendment
  number and previous accession when reported. This is a selected-field
  projection, not full XSD validation. Unknown namespaces, duplicate scalar
  fields, XML entities/DTD, malformed XML and declared/XML form mismatch fail.
- Legacy/rendered ownership HTML is retained as text without automatically mapped
  ownership facts. PDFs/binary documents and complete-submission SGML require
  host extraction or explicit constituent-document selection. There is no OCR,
  amendment-chain reconstruction, automatic restatement, signature verification,
  complete 13D narrative analysis or schema-wide validation.

Bounds, parser failures and missing content must remain visible in the final
research limitations. A partial extraction is usable evidence only for the parts
actually inspected; it is not proof of complete source coverage.

## Official format references

The SEC's [Form 8-K](https://www.sec.gov/info/edgar/forms/form8-k.pdf) distinguishes
the reporting items and attached announcement/release content. Its
[Schedule 13D/G technical specifications](https://www.sec.gov/submit-filings/technical-specifications)
include the 2026 multiple-CUSIP change and current XML specification links.
Observed public [13D XML structure](https://www.sec.gov/Archives/edgar/data/1418226/000119312526389485/primary_doc.xml)
and [13G XML structure](https://www.sec.gov/Archives/edgar/data/2031321/000121390026090032/primary_doc.xml)
show distinct namespaces, person containers and date fields; the helper uses a
small supported subset. The SEC's [developer resources](https://www.sec.gov/about/developer-resources)
describe fair access and aggregate request limits. Format research was performed
November 15, 2026; no live fetch with a user's private contact was exercised.
