ARCHIVAL RECORD — historical results and implementation only.

This file is not current setup guidance or execution policy. Previous
execution gates described below are retired. The current skill imposes
zero execution gates; research findings are advisory. Consult ../SKILL.md and ../references/execution-handoff.md.

---

# Actual cross-model validation — October 10, 2026

Two separate experiments tested the actual signed-in Claude browser, whose model
selector displayed Sonnet 5.5 High, against saved Codex execution results. Codex
used Python 3.11.3 on Windows; Claude used Python 3.12.3 on Linux. These measure
shared-code execution and evidence replay, not an independent stock-picking skill
of either language model. Expected results were withheld until Claude returned
its output. No broker was connected and no trades were placed.

## Production v3.7 conformance

- All 18 normalized financial fields, statuses and derivation trails matched.
- All nine original XHTML extraction objects and their digests matched.
- All eight fictional factor results and their order matched; the fictional
  strict-final bundle replayed successfully with two fictional eligible issuers.
- Claude passed all 27 normalization tests. All 64 entries in the corrected
  returned artifact manifest verified. Its packaging correction changed only
  metadata, preserving all 60 calculation/evidence files.

Only one real pilot field was READY; the other 17 were DRAFT_UNVERIFIED. These
pilots did not form a complete real-stock ranking. Unverified source delivery
remains unverified even when arithmetic agrees.

## Separately declared Yahoo reproducibility experiment

Contract: `vqm-yahoo-reproducibility-1.0.0`. Frozen October 8 close prices and
October 9 vendor pulls. This experiment reused VQM formulas, family weights,
peer fallback, minimum peer size, midranks, Decimal precision and tie-breaking,
but declared a different accounting/market-data input policy in advance.

| Measure | Observed result |
| --- | --- |
| Complete lists | Ten unique issuers from each host |
| Issuer overlap | 10/10, 100%; acceptance target at least 80% |
| Order | Identical |
| Full results | All 401 scores, raw factors, peers, exclusions and field audits identical |
| Retained universe | 503 securities representing 500 issuers |
| Exclusions | 99 unscorable issuers, plus three duplicate share classes |
| Returned manifest | All 15 entries verified; runner bytes and input hashes unchanged |
| Independent rank arithmetic | All 1,604 checked cells matched the shipped VQM midrank implementation |

Common research-test order: NEM, APA, CF, INCY, SNDK, MU, VLO, DLTR, EXPE, ALB.
These are historical test outputs, not current buy recommendations or a required
top-ten universe. The skill's requested count and starting universe remain configurable.

Claude's successful command exited zero with empty stderr. An initial shell-wrapper
attempt failed because `time` was unavailable, before the ranking program ran;
that attempt was retained in the audit. Neither the runner nor inputs were changed
after seeing the results.

## Material limits

The Yahoo experiment is a partial-universe research ranking, not a completed strict
v3.7 primary-filing eligibility test. It uses vendor accounting scopes, total capex,
calendarized fiscal dates, price-bridged market capitalization/enterprise value and
adjusted closes without an independent corporate-action audit. Historical information
availability was not certified. Membership and GICS were reconciled from secondary
sources. Missing data was not replaced with zero.

Forty-one bank/equity-REIT issuers lacked the exact adapter components. Other
exclusions included date-column gaps, null statement cells, stale periods, missing
fields and invalid denominators. Alphabet, Fox and News Corp have class-dependent
vendor capitalization rather than an audited aggregation across classes. Although
none is in the top ten, their peer-rank effect was not ruled out. Some exclusions
contain opaque date errors that need better diagnostics in a future experiment.

The 80% goal passed for this shared-data/shared-runner experiment. It does not prove
80% agreement when models independently fetch and interpret fresh evidence, validate
undervaluation or investment performance, or enable Strong Buy or live trading.
The experimental runner/data are retained separately and are not production defaults.

## Retained artifact identifiers

The full datasets, browser conversations and local runtime logs are not distributed
with this source release. Hashes identify the retained test artifacts; they are not
data-authentication signatures or a claim of public independent reproducibility.

| Artifact | SHA-256 |
| --- | --- |
| v3.7 Claude corrected conformance ZIP | `26f03ff04886577c2ce2333620d17c096f49c09c507463b5601531cb1aae354e` |
| Financial normalization policy | `95daa21befb014a1bcc9a4a51bdde42b58d05883d18e522ece22b3e140c320b1` |
| Normalization implementation digest | `30a10c0afebd8cefea075d06afeb0746fdc2342d156c7d51293dcf1ac61ced6d` |
| Yahoo input ZIP | `6d67001c8aebb44d16001c933ed48126691d27fea04f33b2d9895b87515d8200` |
| Yahoo canonical input | `9fe84a92fdfa8d665b445dfbf9dd7cf8730a237f23188877b38da638614630c6` |
| Yahoo experiment runner | `d612370d69a88c3bab9de25c068153967b0387be29d3042735d4aee59ba2fdff` |
| Actual Claude Yahoo output ZIP | `9e8625c898adde693ec35fa9f263fb2d929fca8f938da30fde9f7bbf03cb027a` |
| Claude Yahoo original result ZIP member | `c4f934c44d2cde478f00e119b82c47b42587cd76b4c441947cdd57741a810f39` |
| Same Claude result, locally reformatted JSON | `7c0ed2347b9d8f16cdc48f2700cef4a3a1db265f4c6b8b0fe4936cd2ff8e32a6` |
