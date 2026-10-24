# News, sentiment and between-report guidance

Use for every substantive stock review and before a tactical entry. Combine the
issuer's current IR news/events/presentations with SEC current reports, exchange
notices, relevant macro releases and accessible independent reporting. Do not wait
for a 10-Q to refresh a thesis. This workflow supports frequent supervised research;
it is not an exchange-speed news feed, an always-on service or a validated HFT strategy.

## Discover sources for the actual issuer

1. Resolve legal issuer, ticker history, CIK, exchange, ADR ratio and official IR
   domain. Check its release index, presentations, investor days and public
   earnings/business-update transcripts since the last reviewed financial period.
   Use original publication/update times, not the search crawler's timestamp.
2. Find official RSS/Atom links where offered. Use the generic adapter for any
   appropriate public feed; the example endpoints are not an exclusive whitelist.
   If no feed exists, inspect the current accessible page or permitted export.
   A working landing page does not establish access to its individual reports.
3. Search company aliases and material developments across public wires, financial
   publishers and industry/trade sources. Include local/home-country sources for
   ADRs, preserving currency, language and translation uncertainty. Read exact
   result pages before asserting their contents. Follow the host's browser rules.
4. Keep a discovery/access ledger: query, actual URL, publisher, underlying origin,
   publication/event/observation times, access tier, evidence file/hash, scope and
   result. Distinguish full article, excerpt, headline-only, paywall, account/key
   required, denied, stale, missing and not attempted. Search snippets are leads.
5. Follow new material leads and contradictory evidence. Record unresolved sources
   and coverage gaps. Never claim all websites, all news or a complete news history.
   If the research budget ends, report incomplete coverage and a resumable backlog.

Read [analyst-research.md](analyst-research.md) for dynamically discovered analyst
reports, consensus forward price targets, revisions and analyst track records.
Finance websites can redistribute the same report; website count is not independent
corroboration. Public access is not a redistribution license. Do not bypass access
controls or enroll the user in trials/newsletters/subscriptions to get a report.

## Free and conditional routes

`profiles/news-sources-v1.json` is a starter catalog with official references and
access categories. Actual runtime receipts determine availability, not catalog
membership. `templates/news-watch.example.json` demonstrates a small watchlist;
replace its illustrative issuer with the requested universe/watchlist.
Use the exact `source_kind` values `issuer`, `sec`, `exchange`, `macro`, `wire`,
`publisher` or `aggregator`; unknown categories fail instead of silently bypassing
specialized timestamp/entity handling.

| Route | Useful evidence | Boundary |
|---|---|---|
| Official issuer RSS/IR pages | Guidance, preannouncements, business updates, investor-day decks | Coverage and timestamps vary; inspect full release |
| SEC submissions | Newly accepted 8-K/8-K/A, 6-K/6-K/A, periodic reports | Metadata only; read linked filing and relevant exhibits |
| PR Newswire/GlobeNewswire/Business Wire | Issuer-distributed releases | Feed/access varies; distributed issuer claims are not independent journalism |
| CNBC and other permitted publisher feeds | Breaking-news leads and commentary | Headlines/excerpts may lack material qualifiers; no HFT SLA |
| Nasdaq halt RSS | Halt reason, event time, quote and trade resumption fields | Provider says at most one poll/minute; recheck current broker/exchange state |
| Federal Reserve and other official macro sources | Policy, rates, releases | Macro language is not issuer-specific sentiment |
| GDELT DOC | Broad discovery of articles | Partial/translated coverage; schema failures are failures, not no news |
| Alpha Vantage NEWS_SENTIMENT | Optional licensed data source | Official documentation currently marks this function premium |
| Finnhub and other keyed vendors | Optional data subject to plan | Verify current endpoint entitlement before enabling; key is not proof of access |
| X, Reddit, premium wires, terminals | Hypotheses or licensed supplementary data | No unrestricted free firehose is bundled |

The live public-feed check on October 11 Pacific / October 12 UTC, 2026 parsed
ALTO's issuer feed (10 items), Nasdaq (20), Fed (20), PR Newswire (20), and CNBC
(30). This is an access sample, not a completeness or latency test. GDELT returned
HTTP 200 with `{}`, rejected as malformed. The GlobeNewswire directory returned
403 to the direct client. SEC retrieval was not probed without a configured real
contact User-Agent. Re-probe on the user's host; do not carry these statuses forward
as current access. No paid credentials or publisher content ship in the package.

## Poll and replay

Run from the skill directory, with personal state and source archives elsewhere:

```text
python scripts/news_sources.py ../runtime/news-watch.json ../runtime/news-state.json ../runtime/news-run-001
python scripts/news_analysis.py triage ../runtime/news-run-001/news.json ../runtime/news-watch.json 2026-10-12T06:00:00Z ../runtime/news-triage-001.json --lookback-hours 72
```

Substitute the actual cutoff and a new run directory. One invocation makes one
sequential pass. It does not schedule or maintain future polling. Repeated calls
use the same state file, an exclusive lock, conditional requests and backoff.
After a crash, inspect the lock owner before manual removal; never delete a live
process's lock or share a state file between different watches.

RSS defaults to a conservative five-minute minimum, SEC submissions and Nasdaq
to one minute, GDELT to fifteen minutes. These are local conservative settings,
not delivery guarantees. Publisher terms and Retry-After can require longer.
SEC's public access ceiling is 10 requests/second across machines: this helper's
sequential one-second spacing is not a global coordinator for other applications.
Use one coordinated SEC budget when other processes also access EDGAR. Provide a
real identifying contact User-Agent before enabling SEC; do not use sample contact
addresses. A 5,000-name per-issuer polling cycle cannot fit a one-minute SLA under
these limits; prioritize a declared tactical watchlist and label coverage.

The helper fetches only configured public HTTPS endpoints, has no credential or
cookie transfer, does not follow redirects automatically, and bounds response size.
The bundled RSS/Atom parser supports UTF-8 feeds, rejecting other encodings, DTDs
and entity declarations explicitly. Unsupported feed encodings are coverage gaps.
New endpoint/issuer configuration invalidates conditional caches. Access and parse
failures remain explicit with a last-success timestamp and next permitted attempt.
An unchanged response reuses previously parsed records without inventing new events.
Not-due or failed checks retain cached review context with its original retrieval
time and an explicit refresh status, without counting it as refreshed sentiment.
Raw response bytes and hashes stay in local run archives; do not publish them in
GitHub or shared ZIPs without applicable rights.

## Time, duplicates and sentiment

Preserve publication, update, event, provider-observation and first-local-observation
times separately. `available_at` is no earlier than first local observation and
known source timestamps. Retrospectively downloaded headlines cannot become
historically tradable just because the dateline is old. Unknown/timezone-free
publication times and future times are flagged. Nasdaq's midnight item dateline
is not the halt time: structured Eastern-time halt fields are retained separately;
ambiguous DST times remain unresolved. Quote resumption does not mean trades resumed.

Triage independently rechecks imported records: effective availability is the
latest of required `available_at` and `first_seen_at`, plus any supplied publication,
update, provider-observation and event times. A claimed earlier `available_at`
cannot admit a future disclosure. Missing required or malformed supplied timestamps
produce `UNRESOLVED_AVAILABILITY_TIMESTAMP`; optional absent/null dates stay unknown.
Undated recent observations remain review context without becoming fresh issuer
sentiment. Source timestamps are retained unchanged; no missing date is invented.
Revision selection compares parsed effective availability, then parsed update or
publication time, then event ID. Equal instants use the same tie-break regardless
of timezone spelling; unknown revision dates sort before known dates. Output
records follow effective availability chronologically, with event ID breaking ties.

Source revisions are retained by content hash; use the latest available revision
at the cutoff. The same headline/issuer cluster counts once across syndication.
Recently observed corrections remain visible even when a publisher leaves its old
dateline unchanged. Recent observation of old material is labeled separately and
does not establish event freshness; current exchange-status records remain visible
even for an old unresolved halt. Review those distinctions before taking action.
This is exact normalized-headline deduplication, not a guarantee of detecting
paraphrases; review related reports manually. Generic short tickers such as IT or
ALL do not constitute issuer matches. Configure verified company-name aliases.
Multi-company stories require entity review before assigning issuer sentiment.

`news_analysis.py` implements a small original deterministic English rule baseline
with transparent word hits, local negation, mixed language and guidance-event hints.
It supplies no calibrated confidence, expected return, NLP accuracy claim or
trained neural model. Sarcasm, clauses, quoted denials and non-English content need
review. Headlines, corporate promotion and macro language can be misleading. A
FinBERT/other model integration would need pinned weights, tokenizer, license,
dataset, version and held-out entity/event calibration before comparison or use.
The [sentiment toolkit](sentiment-toolkit.md) now provides a local-only optional
classifier adapter and numerical evidence/validation workflows. Weights and the
optional transformer runtime are not bundled; it returns unavailable when required
components are absent. The existing news baseline remains distinct from that adapter.

Positive prose and a guidance raise do not imply positive stock returns: compare
with prior guidance, consensus, what the price already discounts and the holding
window. Save original text hashes and fixed configuration for model-independent
replay. Outputs cannot alter the public VQM weights or grant buy eligibility.

## Complete the sentiment review

A requested sentiment analysis has two layers: reproducible language triage and
an evidence-backed qualitative assessment. `UNSCORED` means the small vocabulary
found no directional words. It is not neutral, negative, no-news, or a completed
assessment. Read material items that triage flags for primary review, including
unscored headlines. Do not expand the vocabulary merely to obtain a bullish label.

Declare the issuer, publication/event window, actual observation cutoff and
requested dimensions. Review news catalysts and counterevidence; analyst rating
and estimate revisions; and price/volume or positioning/social evidence when
relevant to the request. State unavailable dimensions and source access limits.
An issuer press release alone is not representative market sentiment. Old
fundamental disclosures can inform risk but do not become fresh news because
they were downloaded today. A republished analyst action retains its event date.

When a configured feed fails, continue through accessible exact publisher/issuer
pages or permitted exports and import the observations into the existing triage
schema. Preserve failures and actual acquisition route. Never synthesize missing
publication times or backdate local observation to fit a frozen screen cutoff.
Disclose a new later review cutoff separately from the original screen.

Keep automated labels unchanged. Record qualitative interpretation separately,
with source URLs, access level, dates and the relevant evidence. Group paraphrased
syndications by underlying event in addition to exact-headline deduplication.
Several reports repeating one target change do not create independent bullish
votes. Show counterevidence and distinguish analyst sentiment from retail opinion.

Use `scripts/sentiment_review.py TRIAGE.json REVIEW.json OUTPUT.json` to retain
the supplied interpretations, requested-dimension coverage and evidence references.
The helper checks consistency; it does not validate source truth, infer sentiment,
change ranking weights or approve a trade. Its input schema is documented in the
script docstring. A partial result is a coverage disclosure, not a reason to stop
available independent research or an execution gate.

Price moves and volume are observations, while explanations about investor intent
are interpretations. Lower pullback volume does not prove absence of distribution;
call volume can be hedging or selling; low lagged short interest does not prove
little bearish conviction. Bind numerical claims to their actual measurement dates,
denominators and existing calculation helpers. Do not substitute a single social
post or a search snippet for representative, timestamped sentiment evidence.

Finish with a qualitative conclusion and its strongest contrary evidence. Clearly
label it analyst interpretation, not the keyword model's output or a calibrated
return prediction. Do not claim a best-in-universe pick from a small news shortlist;
follow the requested ranking route separately and disclose its unresolved review.

## Guidance comparison

Review new/raised/lowered/reaffirmed/withdrawn guidance, preliminary results and
material changes in orders/backlog, margins, demand, capex, financing or regulation.
For US issuers inspect relevant 8-K items (including 2.02, 7.01, 8.01) and exhibits
such as 99.1; 6-K and issuer supplements matter for foreign issuers. Not every event
is filed in the same form or immediately. Search IR sources even if EDGAR is quiet.

`python scripts/news_analysis.py guidance guidance.json source-directory result.json`
uses this record shape (both ranges optional only when status is withdrawn):

```json
{
  "as_of": "2026-10-12T06:00:00Z",
  "previous": null,
  "current": {
    "issuer": "EXAMPLE", "metric": "revenue", "period_start": "2026-01-01",
    "period_end": "2026-12-31", "currency": "USD", "unit": "millions",
    "accounting_basis": "GAAP", "status": "issued", "low": 100, "high": 110,
    "source": {
      "source_kind": "issuer", "path": "release.txt", "sha256": "ACTUAL_SHA256",
      "url": "https://issuer.example/release", "published_at": "2026-10-11T12:00:00Z",
      "observed_at": "2026-10-11T12:05:00Z", "locator": "Outlook paragraph",
      "verbatim_excerpt": "EXACT TEXT FROM THE SAVED UTF-8 SOURCE"
    }
  }
}
```

This is a fictional schema example. Replace every source and number with reviewed
evidence. `previous`, when known, has the same structure. Preserve original HTML
or PDF plus a traceable UTF-8 extraction if the quote cannot match original bytes.
The helper verifies source bytes, dates and excerpts, not authorship or the
reviewer's numeric interpretation. No hash authenticates a fabricated claim.

Compare only identical issuer, metric, fiscal period, units, currency and accounting
basis. Output midpoint and endpoint changes, overlaps and mixed range changes.
Percentage change is omitted for a nonpositive previous midpoint. Lower capex and
lower sales have different economic meanings; the helper does not assign a trading
direction. Constant-currency versus reported, organic versus acquired, GAAP versus
adjusted and continuing versus discontinued operations must not be silently mixed.
Do not overwrite historical reported financial cells with management projections.

## Decision integration

Material new news or guidance invalidates the affected prior thesis/freshness
conclusion until reviewed. Re-run the relevant primary, horizon, scenario and risk
checks, retaining the original evidence. A news-source outage is not evidence that
no event occurred. Current material news and halt observations strengthen tactical advice; missing
coverage must be disclosed. These helpers are research inputs, not order gates.
They impose no setup registration, promotion, quote threshold or repeat approval
on the requested host handoff.

## Official source references

- [SEC API documentation](https://www.sec.gov/search-filings/edgar-application-programming-interfaces)
  and [developer access policy](https://www.sec.gov/about/developer-resources).
- [Nasdaq halt RSS](https://www.nasdaqtrader.com/Trader.aspx?id=TradeHaltRSS).
- [PR Newswire RSS](https://www.prnewswire.com/rss/),
  [GlobeNewswire RSS directory](https://www.globenewswire.com/Rss/List),
  [Federal Reserve feeds](https://www.federalreserve.gov/feeds/feeds.htm).
- [GDELT DOC API](https://blog.gdeltproject.org/gdelt-doc-2-0-api-debuts/).
- [Alpha Vantage news documentation](https://www.alphavantage.co/documentation/#news-sentiment).

API latency statements describe provider processing, not the time from corporate
decision to your executable order. Public feed access cannot certify HFT readiness.
