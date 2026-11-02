# Semantic analyst extraction and earnings basis

Use `analyst.extract_table` (`analyst_adapter.extract(document)`) on retained HTML
or Markdown table text. Columns are found by their labels, not web-output line
numbers. Reordered columns and extra surrounding text do not drop the first analyst.
Navigation rows are excluded; malformed or ambiguous rows remain in `excluded`.
Conflicting same-analyst/firm/date targets remain conflicts, not a chosen average.

Supply `as_of`, `issuer_id`, `currency`, `share_basis`, `target_horizon`, `format`
(`html` or `markdown`), `text` and `source` with `id`, `url`, `available_at`, `access`.
Access is `aggregate_table`, `attributed_excerpt` or `full_report`; it is retained,
never inferred from an aggregate table. The supported header labels identify
analyst, firm/broker, target, date, optional rating and action. Supported dates are
ISO dates or English month/day/year. Targets are a single number or old-to-new pair.
Other publisher formats need an explicit adapter; do not force them through this one.

`reported_date` remains provider-attributed. The adapter does not invent the original
report's issue time, authenticate firm identity or turn an unknown target horizon
into twelve months. It returns no consensus average. Use the existing source-bound
analyst evidence review to assess properly comparable records and keep publisher
aggregates separate. Original text and source-row references bind the extraction.

Use `analyst.earnings_basis` (`analyst_adapter.earnings_basis(document)`) for a quote
and individually identified EPS estimates. Supply each estimate's period start/end,
fiscal or rolling period type, accounting basis, currency, share basis, availability
and source. Compatible positive EPS produces a separately labeled multiple.
Missing basis, nonpositive EPS or quote incompatibility stays unresolved. The helper
does not blend fiscal-year adjusted EPS with rolling GAAP EPS or infer that a low
multiple establishes undervaluation.

Sentiment remains separate: a current named call, an old report, a provider mean and
representative measured investor sentiment are different evidence. Use
[news and guidance](news-and-guidance.md) and [analyst research](analyst-research.md)
for substantive contrary evidence, source access, revision dates and model limits.
