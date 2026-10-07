# Reproducible stock discovery and comparisons

Read for a broad long-term screen, a ranked investment shortlist, or comparison
with another agent's results. The goal is to explain why a name was selected and
which assumptions could change that decision. It does not require identical
judgments from independent analysts or prescribe a universal stock-scoring formula.
Intraday selection follows the registered strategy card and completed-bar signal
workflow instead; do not apply this fundamental screen to every day-trade signal.

## Record the method before choosing the shortlist

For a new run, retain the following in the run record. Choose reasonable details
from the request and disclose assumptions; do not add a permission step for research.
If the method changes during investigation, record the change and re-evaluate all
affected candidates. When documenting an older run, label it retrospective rather
than inventing an earlier rule-setting timestamp.

- **Mandate:** horizon, risk tolerance, desired business durability, exclusions and
  the requested decision (discovery, comparison or investment proposal). A requested
  count is a presentation preference, never permission to weaken the evidence bar.
- **Input snapshot:** dated universe and membership basis, issuer/share-class map,
  raw observations, source/retrieval times, code/config versions and file hashes.
  Distinguish an official roster from a tracking-fund proxy and reconcile residual
  holdings, pending index changes and renamed securities before claiming coverage.
- **Field definitions:** numerator/denominator, units, period, accounting basis and
  forecast vintage for each filtering/ranking metric. Record missing-data and
  invalid-denominator handling. A provider field name alone is not a definition.
- **Peer construction:** business-model/industry membership, benchmark formation,
  sample size, issuer deduplication, exclusions and fallback rules. Save the actual
  peer members and observations, not just the median. A broad industry may still
  mix materially different businesses; label such comparisons provisional.
- **Discovery rules:** explicit filters and thresholds, or a documented qualitative
  selection rule. Distinguish user requirements, skill requirements and rules the
  agent chose for this run. Do not silently add a positive-EPS or PEG requirement.
- **Deeper-review selection:** order or priority rule, tie handling, how many names
  were actually examined and why work stopped. Log every security's disposition.
  A time/access constraint is not evidence that unexamined names are inferior.
- **Ranking and valuation rules:** qualitative, quantitative or hybrid; explain
  decisive criteria. For a numerical score retain inputs, transformations, missing
  values, weights and tie breaks. For qualitative order record the decisive
  tradeoff between close alternatives. Avoid decorative precision.

Do not claim the strongest opportunities in an entire index merely because its
quotes were retrieved. State the breadth of the initial screen, the depth of the
final reviews and the scope of the comparison separately. If there is no robust
ordering, group candidates or describe ties instead of inventing ranks.

## Make economic assumptions inspectable

Sector-relative cheapness is a discovery signal. It is not sufficient evidence
of intrinsic undervaluation. Use the appropriate business model and retain the
normalization, cash, capital and value-trap checks in the screening procedure.

For PEG, identify which P/E, earnings-growth period, annualized growth convention
and estimate source were used. Growth in percentage points and a decimal fraction
produce different numerical ratios. Reject incompatible or nonmeaningful inputs
from that comparison; do not silently substitute a differently defined vendor
field. An unusually low PEG warrants a denominator review for rebound/base effects,
acquisitions or estimate changes. It does not establish durable growth.

State whether a valuation is today's estimated intrinsic value, an undiscounted
future price scenario or a rough multiple sensitivity. Justify growth, margins,
reinvestment, dilution, terminal multiple/discount assumptions and any margin of
safety. A chosen earnings multiple times modeled EPS is an assumption-driven
scenario until its economic basis is supported. Management guidance, adjusted EPS,
analyst targets and the agent's modeled normalized earnings remain distinct.
Show which plausible assumption changes would reverse the apparent discount or
the order of close candidates. Keep GARCH in risk/sizing, outside the value score.

## Report suitability and uncertainty accurately

Classify before presenting a ranked comparison. For a moderate-risk core mandate,
keep material turnaround, solvency, binary-event and commodity-cycle dependence
in a separate speculative group when the evidence warrants that classification.
A low ratio cannot override suitability. Ordinary sector exposure alone is not
an automatic Speculative label; assess its materiality to the particular thesis.

An unresolved material earnings, liquidity, valuation or event question remains
Watch. State what evidence would resolve it. Missing optional analyst observations
are not an automatic veto: a completed analyst-evidence assessment can pass when
it documents the limitation, relies on adequate primary evidence and explains why
no material disagreement remains unresolved. Never fill missing observations with
invented targets or treat absent analyst coverage as a favorable signal.

Rank Eligible candidates as a comparison for further portfolio consideration.
Watch candidates can have a separate **research priority**, explicitly labeled as
such. If none qualifies, lead with that result and provide useful hypotheses and
next checks. Do not title a Watch list "stocks you should buy" or imply that a
numbered shortlist is a validated investment recommendation. Eligible is still
not an authorization or a guarantee of undervaluation.

For competing screens, compare snapshots, membership, field definitions, peers,
filters, deeper-review scope, normalization and risk mandate before disputing
individual picks. Reconcile shared tickers and explain why excluded names differ.
If using a combined candidate set for follow-up, apply the same declared review
to all of it. Do not retroactively tune rules to reproduce either agent's list.

## Offline manifest fields

The existing `screen_review.py` accepts these additions. See the runnable
[fictional-screen.json](../examples/fictional-screen.json) for the complete format.
The Markdown [run record](../templates/screen-review.md) remains usable without JSON.

- `screening[].outcome`: `retained`, `excluded`, `not_advanced` or `missing_data`.
  Use `excluded` for an evidenced discovery-criterion failure; use `not_advanced`
  when initial observations exist but a name was not chosen for deeper work.
  Neither outcome is a fundamental Reject without the relevant candidate review.
  An unexamined row belongs in missing/absent coverage, not `not_advanced`.
- `run_spec`: schema_version `1`; `run_id`, `methodology_version`, timezone-aware
  `defined_at`, `mandate`, nonempty `input_snapshot` evidence-reference list,
  `field_definitions` mapping, `peer_policy`, `discovery_policy`,
  `deep_review_policy`, `ranking_policy`, `valuation_policy`, and a `changes` list.
  Policy fields contain the actual rules or an explicit reference to the retained
  detailed rule record. `changes` explains revisions/overrides, affected names and
  re-evaluation; an empty list explicitly means none. Do not use generic filler.
- `report`: `kind` is `screened_hypotheses` or `eligible_comparison`;
  `ranked_symbols` is an ordered list, possibly empty; `selection_rationale` maps
  exactly those symbols to the reason each occupies its position or group.
  Only candidates whose final display status is Eligible may appear in an
  `eligible_comparison`. Other reviews remain visible in the candidate records.

Legacy manifests still work, with missing methodology/report labeled NOT_RECORDED.
The helper returns the declared specification and its canonical JSON SHA-256 for
comparison. The hash does not authenticate referenced inputs or prove that rules
were chosen beforehand. The helper checks schema, coverage and declared statuses;
it does not execute a stock-ranking model, audit filings, test economic assumptions
or certify that a prose report follows these instructions.
