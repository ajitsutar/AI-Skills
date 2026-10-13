ARCHIVAL RECORD — historical results and implementation only.

This file is not current setup guidance or execution policy. Previous
execution gates described below are retired. The current skill imposes
zero execution gates; research findings are advisory. Consult ../SKILL.md and ../references/execution-handoff.md.

---

# Muse/Codex quant compatibility — October 11, 2026

**Measured: 27/27 shared-input jobs match**, including rejection and infeasibility
outcomes. Codex downloaded Muse's original private JSON attachments, checked byte
hashes, replayed each bundle and used the shipped comparator. This is calculation
and workflow compatibility, not a new stock-pick comparison or performance test.

## Protocol

Both models received the complete v4 package and the exact shipped
`examples/fictional-quant-campaign.json`, with pinned NumPy 2.4.6/SciPy 1.17.1.
Each invoked the shipped Python engine itself. Codex's numeric outputs were
withheld until Muse froze its results. The engine intentionally owns arithmetic;
this tests model orchestration of shared code, not two independent implementations
of the formulas. The 27 jobs exercise all 20 allowlisted operations.

The comparator requires identical input/code contracts and exact decisions/keys;
numeric tolerance was fixed at absolute 1e-8 and relative 1e-7. Floating-point
differences across environments explain different result-byte hashes; this is
not a bit-for-bit result claim. Both original final bundles independently replay.

| Final calculation evidence | SHA-256 |
|---|---|
| Canonical input | `d8bd10d23b1a0d33720892c915cc235d45ddb489eace597b35d2941f186720b1` |
| Contract | `307bfc74203d1baab6290c63cd6a2fbace69ac5aefd44d6c132575bb7f18ad45` |
| Workbench implementation/dependencies | `4bf743de2c8aab026736424aa3cb7c468e1bab7283451f4008736fa4c1475245` |
| Codex original JSON bytes | `a952493fea8b0bd399854d35d184ed1d28616dba6e05cdd2e9174c22e7212e8d` |
| Muse original JSON bytes | `5d0d5882162ee2307a163f1d0e3a3dbf9cfb1e4f91a213a420f93f5c80bb68ae` |
| Codex canonical result | `53521383470740882fddf94edf835c5095f98afcac08c0f1d2f7b2e71168ef3e` |
| Muse canonical result | `ce652e827756a477331a6856f647d8bfd559e689bb218cbc10ed024a5986751d` |

Muse's final JSON was 347,701 bytes. The workbench implementation hash covers its
transitive calculation modules and financial-normalization profile; it is not a
hash of every document or the separate strategy-promotion wrapper. The package
manifest separately binds the entire release.

## Outcomes and review corrections

- 24 jobs returned computed outcomes; three rejected American-option pricing,
  a same-interval backtest decision, and an incomplete trial registry.
- Computed outcomes included an infeasible allocation, a cash shortfall, ambiguous
  XIRR, missing bank/REIT evidence and a monitor that blocked new risk. Those are
  correct guards, not successful investments or cleared orders.
- Initial and revised campaigns each matched 27/27. The 416-test initial suite and
  418-test reviewed suite each passed on Codex and Muse. The release adds one more
  regression for malformed strategy reports.
- Muse's independent review found an unhandled linear-algebra failure. The revised
  engine records `CALCULATION_FAILED` per affected job without fabricating a result;
  an injected numerical-failure regression verifies independent jobs continue.
- Codex's integration review added strategy/version, raw-data hash and complete
  trial-ID bindings, plus transitive preflight checks. Muse reviewed those changes.
- Muse then found a pre-existing malformed-report path that raised on a missing
  `windows` key. The release wrapper returns an explicit non-eligible result for
  malformed report/criteria structure, with a regression covering missing windows,
  missing metrics and a non-object report.

## Narrative routing is a separate test

A prespecified eight-scenario rubric covered unsupported American options,
selected-winner/serial-dependence evidence, settled cash and reservations,
infeasible mandates, incomplete S&P evidence, performance claims, a 17-year-and-
3-month horizon, and instructions embedded in filings.

Seven initial answers were consistent. The American-option answer ambiguously
suggested a European research price before acknowledging the unsupported model.
The instructions were made explicit: never substitute exercise style for the
actual position, even under a research label. Muse corrected the answer and
confirmed the other seven. This is **seven clear initial responses plus one
resolved ambiguity**, not a pristine blind 8/8 result. More unseen prompts and
future model versions still require evaluation.

## Stock results and remaining limits

The public VQM scorer/profile are unchanged. Codex replayed both retained real-stock
bundles; Muse replayed its own. The earlier [independent public-data test](muse-codex-validation-2026-10-11.md)
remains 10/10 candidate overlap with eight exact rank positions, different scores
and 401 versus 414 scorable issuers. Replaying it here is a historical regression,
not fresh v4 data acquisition or filing-verified buy eligibility.

This campaign cannot establish persistent alpha, full instrument coverage,
authenticity/completeness of externally supplied evidence, independent data
agreement, or equal future investment results. No trades, broker connections,
paid service purchases or public dataset uploads were performed. See
[the capability review](../REVIEW-4.0.md) for concrete unsupported dependencies.
