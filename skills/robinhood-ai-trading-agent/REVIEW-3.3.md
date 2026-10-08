# Version 3.3: arbitrary holding periods and research consistency

October 8, 2026. Skill 3.3.0; repository plugin 1.3.0.

The previous routes left a dated hold underspecified: a long-term value screen
could be presented for a forced short exit, while different agents applied
inconsistent event and financial-period assumptions. This release resolves the
holding clock first and then routes to the appropriate decision process. It
supports intraday through ten years and longer, with no skill-imposed maximum.

## Changes and gap review

| Area | Result |
|---|---|
| Holding units | Same-session, elapsed minutes/hours, calendar days/weeks/months/years and trading sessions; fractional requests normalize into smaller exact units |
| Deadline semantics | Fixed end versus rolling from actual entry, latest entry, early exits, preceding-session adjustment, early-close-aware buffer; delayed entries cannot silently extend fixed deadlines |
| Distant dates | Confirmed-through evidence and provisional future calendars; refresh before execution, rather than claiming decades of known exchange schedules |
| Route selection | Intraday uses registered completed-bar signals; swings require a within-window thesis; long-term work assesses durability and economics with periodic reviews |
| Event policy | Entry-only versus entry-and-hold scope; holding events remain visible; full-window versus explicit rolling review coverage; no blanket 30-day exclusion |
| Live compatibility | Existing holding_window policy spelling remains accepted; tactical personal policies remain strict; no authorization, strategy promotion or broker capability is created |
| Primary evidence | Latest-public-period versus actually reviewed period, publication/cutoff consistency and current latest-report lookup; issuer release versus conference call and filing dates remain distinct |
| Valuation and uncertainty | Same-exit downside/base/upside outcomes after costs and distributions, comparison with cash; unsupported probabilities rejected by the helper; targets and GARCH remain separate |
| Research completeness | Attempt primary work on leading candidates before an all-Watch response; disclose actual coverage and unresolved material issues without filling a quota |
| Comparisons | Skill/model/settings/tool/context/snapshot differences recorded; shared candidates reviewed consistently; one pair of lists is not a model-performance test |
| Portfolio and operations | Existing cash, exposure, ownership, stress/covariance, durable execution, reconciliation, protection and session-health gates retained and regression-tested |
| Portability and provenance | New fictional example, review template, updated 50 prompts, matching plugin versions and package hashes; existing source credits, arch license and notices retained |

## Validation and migration

The complete offline trading suite passes **218 tests**, including **33 new
holding-period tests**. Cases cover 90 days versus three months, same-session and
elapsed clocks, early closes, month/leap-year boundaries, 18-month/10-year/20-year
and 500-session holds, delayed fixed versus rolling entries, event scopes,
unknown/stale calendars, latest-quarter consistency, net scenario arithmetic and
separation of research status from order authorization. Existing personal-runtime,
intraday replay, risk/ledger and GARCH tests also pass. Export-scanner tests,
portability, skill schema, examples and package checks are recorded in
[VALIDATION-3.3.txt](VALIDATION-3.3.txt).

New fundamental manifests declare long_term with research_as_of, or fixed_horizon
with a versioned holding contract. Both require run_spec and primary_review.
Legacy manifests still run but identify themselves as legacy_unspecified; their
old Eligible status does not establish completion of the new holding-period checks.
The standalone horizon_review command supports the intraday clock; screen_review
does not force a fundamental screen onto intraday setups. Existing personal-policy
files and approval hashes need no automatic migration. Never overwrite user policy.

## Remaining boundaries

Offline checks validate declarations and arithmetic, not the authenticity or
economic merit of evidence. Future exchange dates and multi-year outcomes remain
uncertain. Long holds need rolling reviews; no distant-event clearance is implied.
Calendar/date-library limits must be reported rather than silently shortening a
request. The helper is US-equity specific and does not calculate cash settlement.

No live swing adapter, unattended service, guaranteed exit or profitable strategy
is introduced. Live tactical support remains the existing, unpromoted
opening-range-breakout adapter with broker-native protection and supervised exit
requirements. Research supports arbitrary holds; actual execution depends on the
supported broker/strategy path and applicable authorization. No account was
connected, order submitted, schedule created or user skill installation overwritten.

This is a targeted code, workflow, packaging and regression review, not a claim
that software tests prove every possible defect absent or establish investment edge.
