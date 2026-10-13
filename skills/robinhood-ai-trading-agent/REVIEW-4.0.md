ARCHIVAL RECORD — historical results and implementation only.

This file is not current setup guidance or execution policy. Previous
execution gates described below are retired. The current skill imposes
zero execution gates; research findings are advisory. Consult SKILL.md and references/execution-handoff.md.

---

# Version 4.0 capability and gap review

Reviewed October 11, 2026. This release expands the investment-manager research
and operations workflow while preserving the v3.8 stock-discovery profile and
existing supervised equity execution boundaries. It is not a claim that all
investments or institutional fund functions have been implemented.

## Changes and checks

| Gap | Implemented change | Evidence/boundary |
|---|---|---|
| Model-written arithmetic and inconsistent quant inputs | Allowlisted workbench, frozen contracts, dependency/source hashes, original bundles and replay comparator | Same-input numeric tolerance 1e-8 absolute/1e-7 relative; decisions and keys exact |
| Portfolio construction beyond ticker ranking | Cost-aware constrained allocation, issuer/group/gross/net/cash/turnover/capacity/stress/volatility limits | Closed-form inverse-variance check, constraint/infeasibility tests; continuous research weights only |
| Temporal leakage and repeated trials | Prior-only purged folds, HAC, block bootstrap, Holm and qualified PSR/DSR diagnostics | Known statistical fixtures and rejection tests; no implied profitable strategy |
| Summary-only promotion evidence | New draft policies require aligned raw trial returns and recomputed statistical evidence | Existing promotion gate rejects absent quantitative evidence; approved policies are not migrated silently |
| Portfolio return accounting | Causal period simulation with costs, capacity, halts, cash and benchmark | Look-ahead, cash/cost and missing-return tests; not a fill or settlement simulator |
| Instrument risks reduced to equity volatility | Explicit spot/FX, futures, European option and fixed-bond scenarios | Parity/finite-difference/PV/negative-futures tests; unsupported styles fail explicitly |
| Funding and execution accounting | Currency cash ladder, reservation consumption, shortfall, conventional XIRR and Brinson attribution | Unsettled-credit, duplicate-release, sign and reconciliation tests |
| Missing financial fields treated as permanent exclusions | SEC candidate extractor and strict-normalization recovery backlog | Cutoff/amendment/entity/denial tests; bank/REIT source routes retain accounting scope |
| Drift and operational monitoring | Fixed-threshold freshness, coverage, realized-risk, cost and reconciliation monitor | Breaches block new risk in its output; supplementary to broker gates, not an order service |
| Overstated coverage and model-agreement claims | Instrument capability matrix, mandate/lifecycle workflow and separate validation claims | Research, supported calculation and supported live execution distinguished |

Local release regression: **419 tests passed**. These include 68 new quant and
integration tests beyond the 351-test v3.8 suite. The 27-job fictional campaign
covers every workbench operation plus adverse cases. It contains no real stock
recommendations and is kept distinct from real-market evidence. The
[actual Muse/Codex comparison](references/muse-codex-quant-validation-2026-10-11.md)
matched all 27 jobs, with a separately documented routing ambiguity and review
fixes. A local replay alone is not a substitute for running another model.

Research and original-method attribution are in
[quant-research.md](references/quant-research.md). New modules do not copy external
repository code. Existing dependency notices and original provenance remain.

## Remaining dependencies and deliberately unsupported capabilities

- **Investment performance:** no new strategy has demonstrated persistent net alpha,
  and no new live strategy is promoted. Statistical acceptance is not proof.
- **Full-universe primary evidence:** bank/REIT and other missing facts still need
  actual filing/supplement recovery and review. A recovery tool does not itself
  complete every issuer. Public vendor coverage remains explicitly reported.
- **Source authenticity:** hashes establish byte identity, not truth. Reviewed
  accounting records, causal signal records and complete trial registries require
  independent source review. The code cannot discover an omitted experiment.
- **Pricing breadth:** no American/exotic option, callable/prepayable bond, swap,
  private-asset valuation, default model, volatility surface or market-impact
  calibration is supplied. The supported formulas state their assumptions.
- **Execution breadth:** no new short, derivative, crypto or international broker
  adapter. Continuous research allocations are not executable share orders.
- **Simulation breadth:** no realistic queue/latency simulator, intraday settlement
  recycling, automatic tax-lot optimization, multi-period stochastic optimizer,
  PBO/CSCV, or estimated Ledoit-Wolf shrinkage is claimed.
- **Operational infrastructure:** custody, audited NAV, tax/legal decisions, fund
  administration, vendor entitlements and resilient unattended services remain
  external. The supported personal operating model stays a supervised session.
- **Cross-model scope:** shared-code/shared-input agreement is testable. Independently
  acquired data, discretionary evidence judgments and future investment returns
  cannot be guaranteed identical across models.

Use [the instrument matrix](references/multi-asset-playbook.md) and
[workbench contracts](references/quant-workbench.md) to determine the supported
route. A missing dependency returns a concrete research/operation limitation,
not an invented value or silently weakened constraint.
