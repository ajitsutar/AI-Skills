ARCHIVAL RECORD — historical results and implementation only.

This file is not current setup guidance or execution policy. Previous
execution gates described below are retired. The current skill imposes
zero execution gates; research findings are advisory. Consult SKILL.md and references/execution-handoff.md.

---

# Shared financial normalization — release review

Version 3.7.0, October 10, 2026.

The initial Claude test reproduced selected source arithmetic but could not
produce a valid full-universe ranking. Models still wrote their own extractors,
interpreted accounting scopes and prepared source declarations differently.
The update moves that recurring calculation work into shared executable code.

## Changes

- A versioned accounting policy fixes parent-attributable income, cash scope,
  disjoint debt and productive-capex components, Standardized bank capital,
  matching loan scopes and unadjusted Nareit common FFO.
- A conservative Inline XBRL extractor resolves context/entity/period and unit
  measures through namespace URIs, applies supported transforms/sign/scale, and
  reports unsupported constructs. Prefix aliases work; spoofed namespaces do not
  map as GAAP. Legacy extracts require re-extraction from original XHTML.
  Reviewed table transcriptions use the same monetary conversion.
- The normalizer reconciles exact TTM, FY/YTD and four-quarter paths, preserves
  reporting accuracy, and refuses inconsistent observations or implicit zeros.
- Source origin, delivery, verification, publication precision and retrieval are
  distinct. Issuer PDFs do not need artificial byte equality with SEC HTML;
  unverified mirrors remain draft. Future amendments cannot rewrite past inputs.
  Complete verified paths take precedence over unverified duplicates, while
  verified conflicts remain unresolved. Accounting basis codes prevent automatic
  substitution of Advanced bank capital for Standardized capital or adjusted FFO
  for unadjusted FFO.
- Dated predecessor/successor mappings preserve financial-context identity.
- Schema-2 snapshots embed the evidence ledger. The scorer materializes financial
  facts from it and rejects competing numbers or metadata. Model judgments that
  affect eligibility remain separate, retained and hashed.
- Read-only diagnostics identify financial-component and market-data gaps without
  a counterfactual claim that verification passed.

Factor weights and formulas, arbitrary holding clocks, supervised day-trading
routes, settlement reserves and execution permissions retain their prior roles.
The new accounting policy is a separate part of the reproducibility contract.
Schema-1 arithmetic remains an explicitly labeled legacy diagnostic/fictional
test path; new real shared research requires schema 2.

## Validation and limits

See [the validation receipt](VALIDATION-3.7.txt). Complete fictional inputs test
exact ordering and replay. Retained public filing pilots test actual source
arithmetic, with unverified and missing evidence kept explicit. The saved pilots
are not shipped in the skill ZIP; the examples contain invented observations.

The supported parser subset is not a full XBRL validator or PDF-table reader.
Extension concepts, dimensional scopes, financial-note components and source
authentication can still need reviewed evidence. Every such decision must be
saved once and shared across models. A fresh model-written ledger can still differ
from another ledger; the package does not claim to remove all research judgment.

The strict filing-verified S&P 500 dataset remains incomplete. A subsequent actual
Claude/Codex experiment using a separately declared Yahoo-data approximation
achieved 10/10 issuer overlap, identical order and identical full results for 401
scored issuers. That meets the 80% target for the shared-data/shared-runner test;
it does not establish fresh independent research agreement, strict v3.7 eligibility,
measured alpha, calibrated Strong Buy confidence or live trading readiness. See
[the cross-model validation record](references/cross-model-validation-2026-10-10.md)
for the separate tests, retained hashes, exclusions and limitations. The vendor
experiment is not installed as a replacement for the production input policy.

The new Python code was written in this workspace. No Claude-generated extractor
or external repository implementation was copied. Technical references are listed
in [the normalization contract](references/financial-normalization.md).
