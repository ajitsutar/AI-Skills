# Research reproducibility update — version 3.1.0

The comparison between two S&P 500 screens exposed a reporting and selection gap:
different peer groups, filters, discretionary shortlists and risk mandates could
produce different names without a sufficiently clear account of why. The earlier
package already required normalized earnings, cash support, value-trap checks,
analyst evidence, events and GARCH. This update makes the selection decisions
inspectable and keeps incomplete hypotheses distinct from eligible comparisons.

## Changes

- Record a dated research specification: mandate, input snapshot, metric/peer
  definitions, discovery filters, deeper-review priority, ranking, valuation and
  later judgment overrides. Quantitative weights are required only when a numerical
  score is actually used; qualitative and hybrid methods remain supported.
- Distinguish discovery exclusions from names not advanced to deeper review.
  Report broad screening coverage separately from candidate review depth. Neither
  nonselection nor complete quote retrieval establishes a fundamental conclusion.
- Clarify PEG period/unit consistency, peer comparability and sensitivity to
  assumptions. Label multiple-based scenarios and future price scenarios accurately.
  Analyst targets and GARCH do not establish intrinsic value.
- Apply the requested risk mandate to selection. Keep Watch research priorities
  and speculative ideas distinct from an Eligible comparison. Missing optional
  analyst observations need an explicit assessment, not an automatic veto.
- Extend `screen_review.py` with optional `run_spec` and `report` records. It emits
  the declared specification and a canonical SHA-256 for comparison, validates
  ranked symbols/rationales, and rejects non-Eligible candidates included in a
  declared Eligible comparison. It never supplies an investment ranking itself.
- Retain legacy manifest compatibility, explicitly labeling unrecorded methodology
  and report purpose. Update the runnable fictional example and research templates.

S&P 500 remains a configurable starting universe. There is no fixed number of
picks and no mandatory PE/PEG filter. The separate day-trading route, registered
setups, completed-bar signals, risk limits, GARCH role, broker capabilities,
supervision and authorization mechanics remain in place. The fundamental-screen
specification is not required for every intraday signal.

## Verification and limits

Ten added regression tests cover deferred-review accounting, missing evidence,
legacy compatibility, stable/change-sensitive specification hashes, malformed
specifications, incomplete candidate reports, ranking rationale, duplicate or
unreviewed symbols, and empty/one-name results without implied authorization.
The complete regression suite and offline command examples are exercised by the
release verification; its receipt is [VALIDATION-3.1.txt](VALIDATION-3.1.txt).

These checks validate code behavior and declared report consistency. They do not
authenticate filings, verify referenced file contents, prove rules were chosen
before selection, validate investment judgment or force independent agents to
agree. An agent can still write a misleading prose report; the instructions
explicitly forbid describing Watch hypotheses as stocks to buy. The specification
hash covers its JSON declarations, not the files those declarations reference.

This release does not rerun, upgrade or certify either earlier stock shortlist.
No brokerage connection, account action, installation, trade or schedule is part
of this update. For existing operational controls and activation prerequisites,
see [REVIEW-3.0.md](REVIEW-3.0.md).
