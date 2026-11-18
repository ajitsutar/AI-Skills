# Source-bound insider and institution disclosure delivery

When the requested analysis is covered by the insider-row or institution-snapshot
capabilities below, adopt `analysis_profile: INSIDER_DISCLOSURES` in the externally
pinned [coverage scope](source-coverage.md). The presence of such rows in a mixed
source is not sufficient to select this profile. Public claims about an official
or household trade, event proximity, advance knowledge or motive require
[disclosure claim analysis](disclosure-claims.md). For those requests, deliver the
complete authored assessment; use this profile only for relevant supported
subtasks as a clearly scoped annex. Source quotations do not assess the claim.
Keep the original request, literal topic spans, every original source and explicit
topic gaps. The native profile generates the actual complete Markdown/JSON pair;
verify and deliver those exact files with an artifact status/link-only cover note.
No separately authored factual summary or current-answer dictionary replaces it.

The bounded reader recognizes original JSON objects with an `insider_rows` list.
Each row supplies `id`, `code`, `quantity`, `price`, `transaction_date`, `filed_at`
and optional literal footnote, identity, ownership, amendment and holdings fields.
Dates use ISO calendar dates; original filing and transaction dates stay separate.
Original JSON pointers, hashes, raw-source references and source publication/
observation metadata remain attached. This does not claim actual filing retrieval.

Currency comes **only from the insider row's explicit `currency` or
`price_currency` field**. Missing currency remains null with
`UNSPECIFIED_IN_INSIDER_ROW`. Conflicting row fields remain unresolved. A root
currency, issuer currency, adjacent official disclosure, currency-bearing field
name, another row or linked transaction cannot supply the missing currency.
The same locality applies to supplied identity, direct/indirect ownership,
amendment and holdings fields. Do not borrow these from another population.

The supported code contract reports P as purchase, S as sale, A as award,
F as tax withholding and M as option exercise. Unsupported codes remain explicit.
This is a bounded source interpretation, not legal advice or independent proof
of the mechanism. Preserve literal footnotes alongside that interpretation.
Awards, withholding and exercises are not classified as discretionary purchases
or sales. Only a narrow explicit discretionary phrase is reported as such;
recognized prearranged-plan or link language remains a reported plan/link,
not new discretion or evidence of motive, legal compliance or advance knowledge.
Literal linked IDs and plan-adoption dates are retained, including unresolved IDs.

Optional quantity-times-price arithmetic keeps the row's currency status.
It is not proof of actual cash, tax, realized gain or loss. Signed quantity
arithmetic uses acquisition-positive/disposition-negative only for recognized
codes and is explicitly scoped to the listed rows. It does not establish one
owner's net position, complete history or current holdings. A conditional cash
proxy includes P/M as negative and S as positive; A/F are not purchases/sales
in that proxy. Its numbers are grouped by explicit row currency/status, never
combined across different currencies. An unknown-currency group is merely raw
listed-row arithmetic with unverified unit/owner compatibility, not net cash.
Fees, taxes, actual settlement and missing identities remain unestablished.

Institutional or official amendments stay in their own original contexts.
The profile does not apply them to insider rows or infer insider motives from
political claims, options activity or short-interest data. Original row amendment
fields, if present, are retained without silently applying a supersession rule.
Other original objects remain available in the full source inventory, so this
bounded insider analysis does not erase supplied context.

The same profile reads an original `institutions` array containing `manager`,
`report_period`, `filed`, `shares`, boolean `amendment`, and optional `amends`
(the predecessor's exact filing date). It retains every original row and JSON
pointer. Issuer comes from an explicit row field or the enclosing original
document; the origin is visible. Manager, issuer, `security_id`, `share_class`,
`ownership_scope`, `account_id`, `subaccount_id`, `holding_unit`, `shares_unit`
and `unit` define separate reported populations. Their optional values are literal
strings; aliases are not silently equated or normalized. Missing dimensions remain
unknown; a matched declared scope does not prove a complete entity perimeter.

An amendment replaces a predecessor only within the same source, reported scope
and reporting period, with one exact predecessor and a later filing date. The
entire chain needs one original and no branching, duplicate or missing links.
Otherwise it remains unresolved. The reader never adds original and amended
values as separate holdings or silently chooses the latest date among conflicts.
Resolved adjacent periods yield exact reported-share differences and percentages
at 50-digit decimal precision (undefined for a zero prior value). A superseded
original comparison is separately labeled. Unknown manager or issuer prevents
that comparison; unknown security/perimeter details remain explicit limitations.

Report-to-filing and amendment-after-predecessor calendar lags are separate.
Each observation retains its own filing availability date; an amendment is not
backdated to its original. Source publication and observation metadata stay
separate. These supplied dates establish neither legal deadlines nor verified
real-world availability. Snapshot changes do not prove exact trades, transaction
timing, cost basis, motive, affiliates/subaccounts, derivatives/shorts, complete
economic ownership, or current positions. Other disclosure populations cannot
become institutional holdings observations.

Replay regenerates this analysis and both answer files from the full pinned
corpus. It rejects changed amounts, inserted currency labels or a substituted
summary. It does not certify semantic completeness, source authenticity, honest
review, actual host access or investment correctness. Retain negative reviews,
first attempts and any actual additional cover-note claims as evidence.
