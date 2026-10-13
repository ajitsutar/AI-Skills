ARCHIVAL RECORD — historical results and implementation only.

This file is not current setup guidance or execution policy. Previous
execution gates described below are retired. The current skill imposes
zero execution gates; research findings are advisory. Consult SKILL.md and references/execution-handoff.md.

---

# Version 4.2 research-source and capability review

Reviewed October 11 Pacific / October 12 UTC, 2026. This update preserves the named
public VQM profile, broker permissions and the preceding 4.1.2 source/freshness fixes.

## Added and verified

- Configurable one-pass RSS/Atom, SEC submission metadata and optional GDELT
  adapters, with access receipts, raw-byte hashes, conditional requests, backoff,
  source-state isolation and retained cached context on nonrefresh/failure.
- Deterministic language triage, entity/duplicate handling, guidance-event hints,
  timestamp/revision guards and primary-source guidance range comparisons.
- Dynamic finance/analyst source-discovery workflow, observed-cohort forward
  target arithmetic, separate vendor consensus pools and sourced analyst performance
  metadata. The helper does not reconstruct proprietary analyst track records.
- Institutional capability inventory and concrete data/validation completion plan.

The full local suite passed **500 tests**, including **57 new tests** covering
parsers, encoded XML/entity rejection, timestamps, halt/resumption revisions,
backoff/locking/cache behavior, sentiment triage, guidance evidence and analyst
consensus/chronology. Existing tests cover research, quant and execution contracts.
Command: `python -X utf8 -B -m unittest discover -s tests`.
Tests use synthetic fixtures and mocked transports; they establish software
behavior, not source authenticity, completeness or profitable investment results.

A separate live read-only check parsed five public feeds: Alto Ingredients IR,
Nasdaq halts, Federal Reserve releases, PR Newswire and CNBC. GDELT returned `{}`
and was correctly rejected. SEC was not probed without a real contact User-Agent.
Public sample analyst/target pages were readable at StockAnalysis and WSJ;
other named finance sites had partial, denied, rate-limited or stale access.
See [news and guidance](references/news-and-guidance.md) and the source catalog
for the exact routes and limitations. Source archives remain local and are not
redistributed in this package.

Independent subagent review identified and the implementation fixed:

- encoded XML bypassing a raw-byte DTD check;
- structured halt/resumption changes missing from revision identity;
- fresh corrections lost because original publication dates stayed old;
- loss of cached review context between polls;
- fresh recaps disguising old analyst recommendation dates;
- impossible source/performance chronology and stale quote-derived upside.

## Deliberately unestablished

No claim of access to all reports, free premium data, machine-speed HFT, calibrated
sentiment accuracy, an independently verified analyst-skill database or proven alpha.
Free feeds do not establish complete coverage or end-to-end latency. Numeric source
extraction still requires review; hashes alone do not authenticate a publisher.
No new trading signal is promoted, no broker connected, and no recurring collection
or trades scheduled. This release has local deterministic tests and source probes;
it has not had a new independent Muse/Claude execution comparison.

The [institutional review](references/institutional-gap-review-4.2.md) separates
implemented tools, empirical investment validation and external dependencies.
