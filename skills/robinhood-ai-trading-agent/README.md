# Robinhood quant research and portfolio agent

A self-contained skill for investment recommendations, reproducible stock research,
portfolio analysis and quantitative work across arbitrary holding periods. It
combines public evidence with replayable calculations and hands requested trades
to the host's available broker tools.

**The skill has no execution gates.** Research findings and risk diagnostics are
advisory. It does not require a local policy, grant, ticket, strategy promotion,
volatility/spread/funding test, supervised lease or repeated approval. Actual host,
platform and broker requirements remain external; existing user instructions carry
forward instead of triggering another skill approval.

Start with [example prompts](EXAMPLE-PROMPTS.md), [installation](INSTALL.md), or
[agent instructions](SKILL.md). Research is not restricted to Robinhood holdings or
Yahoo. The Robinhood name identifies the broker integration context, not the
research universe.

## Capabilities

| Workflow | What the skill provides | Guide |
|---|---|---|
| Stock recommendations | Whole-universe discovery, shared factor ranking, primary evidence, valuation, catalysts and downside | [Research campaign](references/research-campaign.md) |
| Holding-period decisions | Arbitrary dated and flexible horizons, matching events and scenarios, and cash comparisons on the same capital after entry costs | [Holding periods](references/holding-period-planning.md), [equity versus cash](references/equity-cash-comparison.md) |
| Financial diligence | Sector-relative valuation, normalized earnings/FCF, explicit raw-observation mapping, balance-sheet and value-trap analysis | [Investment review](references/screening-and-value-traps.md), [flow normalization](references/flow-normalization.md) |
| News and guidance | Dynamic source discovery, public feed polling, between-quarter projections and deterministic text triage | [News and guidance](references/news-and-guidance.md) |
| Analyst evidence | Accessible reports, forward target distributions, revisions, sourced track records and population-specific source lineage | [Analyst research](references/analyst-research.md) |
| Portfolio decisions | Contributions, fractional allocation, full-source ETF look-through and share-class joins, concentration, volume context, rebalance proposals, tax-lot review and explicit comparisons with missing allocations | [Portfolio management](references/portfolio-management.md), [source exposure](references/source-exposure.md), [allocation baseline](references/allocation-policy.md), [decision calculations](references/portfolio-decision-calculations.md), [input roles](references/planning-input-roles.md) |
| Dated portfolio scenarios | Net vests, withdrawals, tax earmarks versus payments, conditional tax treatments and consistent post-flow denominators | [Dated portfolio projections](references/portfolio-projection.md), [shared employer reference](references/employer-reference.md) |
| Planning tradeoffs | Preference-free conditional proposals; separate settlement, transfer and arrival dates, a shared timing reference and unresolved cutoff timing | [Planning comparisons](references/planning-comparison.md) |
| Tactical research | Completed-bar setups, catalysts, liquidity, cost assumptions, stops/targets and holding-period scenarios | [Short-term research](references/short-term-trading.md) |
| Volatility analysis | GARCH, GJR-GARCH, supported EGARCH and stock-relative interval-move diagnostics | [Volatility models](references/garch-volatility.md) |
| Quant construction | Constrained allocation, covariance sensitivity, empirical tail loss and multi-asset scenarios | [Quant workbench](references/quant-workbench.md) |
| Strategy evaluation | Causal splits, purging, HAC, block bootstrap, multiple-testing review and retained evidence | [Quant research](references/quant-research.md) |
| Performance accounting | Execution shortfall, cash ladders, TWR/XIRR, attribution and portfolio simulation | [Manager workflow](references/institutional-manager.md) |
| Reproducibility | Frozen contracts/data, explicit calculation defaults, runtime receipts, numerical replay and separate acquisition comparisons | [Model-independent research](references/model-independent-research.md) |
| Report facts | Private JSON facts and readable Markdown from retained quant/public-VQM results, with source pointers, supported units and denominators, explicit unknowns and separately declared custom labels | [Report facts](references/report-facts.md) |
| Run and report | Execute explicit quant jobs or analyst cohorts and retain their inputs, results and reports; inspect exact handoff payload differences without execution gates | [Run and report](references/run-and-report.md) |
| Research alignment | Bind request roles and records, distinguish unknown evidence, preserve flexible horizons and ranking methods, and reconcile cash, fees, valuation and causal strategies | [Research alignment](references/research-alignment.md) |
| Source-bound workflow | Prepare explicit requests without recopying their arguments, run source-bound tasks, retain assumptions, verify results and project exact claims and coverage | [Source-bound workflow](references/source-bound-workflow.md) |
| Evidence interpretation | Preserve partial event dates, check operand identities and share bases, and distinguish unknown facts from negative or equal facts | [Evidence semantics](references/evidence-semantics.md) |
| Execution handoff | Preserve the user's order instructions, surface findings as advisory and pass the payload to the host | [Execution handoff](references/execution-handoff.md) |

Stock discovery defaults to **all U.S. exchange-listed stocks including listed
ADRs**. S&P 500, custom lists and other universes are explicit choices. Report
actual membership, coverage, exclusions and unresolved data; do not call a subset
a full-market screen. There is no fixed number of picks or maximum holding period.
Instrument-specific calculations remain limited by their implemented models.

For supplied-data numerical work, start with `scripts/research_workflow.py`.
Its `prepare` command retains an explicit request and source bytes without changing
arguments; `run`, `verify` and `summary` produce and check the calculation and its
reported claims together. Report verification catches altered or incomplete
projections, including type changes in literal claims. Free-form business
judgment and source selection still require review. Matching calculations alone
does not establish matching recommendations or universal model independence.

Source-aware portfolio helpers carry the original obligations, withdrawals,
vesting events and unknowns into dated projections and comparable alternatives.
Source-bound budget sizing keeps the entire supplied fee/slippage model together
and separates unresolved quote bases from named full-cost sensitivities.
The settlement/transfer sweep evaluates every supplied sale date. Typed price
comparisons retain both the reference-price discount and the quote-based upside
with their formulas. Financial pointer bindings preserve absent reporting
precision. Final recommendation context joins the selected names and amounts to
their supplied concentration, monetary volume and fixed-exit risks. Use these
operations when the linked input schema fits; other schemas require an explicit
mapping with the same source facts preserved.

## Recommendations and evidence

The shared Value–Quality–Momentum profile produces a reproducible research queue,
followed by primary-source, horizon and portfolio review. Keep numerical rank,
valuation evidence and recommendation confidence distinct. A relative factor score
is not an expected return. Research labels describe the evidence; they do not
approve, deny or restrict a broker order.

When an ordered candidate set is supplied without weights or supported optimizer
inputs, the allocation fallback divides the notional budget equally across the
selected set. It preserves explicit user selections, weights and counts; it does
not invent a portfolio size or turn scores into expected returns. Alternatives
that each use the full budget remain separate scenarios. This is a reproducible
baseline, not a return-maximizing strategy. Fees, all-in debit and suitability
require their own evidence and calculations.

Cash-budget comparisons calculate quantities, entry costs, total debit and residual
together for each supplied whole-share or fractional increment. Quoted bid-ask
spread stays separate from an explicit one-way slippage assumption. Allocation
context retains the stated denominator, issuer/sector/industry exposure, supplied
fund holdings and monetary-volume units, including unknown coverage. These are
planning estimates and source disclosures, not broker permissions or guarantees
of the amount a market order will spend.

Use SEC filings, issuer releases and appropriate accessible finance providers.
Yahoo is one acquisition adapter. Record source dates, accounting basis and
changes between quarterly filings. Analyst targets and track records are sourced
opinions/statistics, not guaranteed outcomes. News headlines, accessible reports,
paywalls and missing sources have different evidentiary value.

The package has no demonstrated universal alpha or calibrated Strong Buy
classifier. Make recommendations proportional to the evidence and state material
uncertainty. A completed calculation or matching model output establishes neither
investment performance nor professional-manager equivalence.

For calculations, retain material values from the current request and its context
alongside file inputs, with their units and provenance. A value is not missing
merely because it is absent from a JSON file. Distinguish declared assumptions
from source observations and disclose conflicts; apply helper defaults only to
unresolved optional fields. See [input provenance](references/model-independent-research.md#reconcile-request-and-file-inputs).

## Installation and research setup

Keep the entire folder together: scripts, references, profiles, templates and tests
are self-contained. No repository-root files or other skills are required. See
[INSTALL.md](INSTALL.md) for Codex, Agent Skills and Claude Code locations.

Use Python 3.11 or newer. From the extracted skill directory:

```powershell
python -m venv ..\trading-env
..\trading-env\Scripts\python.exe -m pip install -r requirements-tested.txt
..\trading-env\Scripts\python.exe scripts/research_preflight.py
..\trading-env\Scripts\python.exe -m unittest discover -s tests -v
```

Choose an unused environment directory; on macOS/Linux use `python3` and
`bin/python`. Dependency and integrity findings describe research availability,
not execution permission. The requirements file pins direct dependencies, not a
complete transitive environment; retest after changes. Missing optional research
models should be disclosed without inventing substitute results.

Keep personal source archives, reports and existing broker/runtime records outside
the installed skill. Installing or upgrading the package does not change an
account or erase old execution state. Optional local runtime helpers organize
research; they do not activate, approve or gate trading.

## Examples and handoff

Run fictional research examples:

```text
python scripts/screen_review.py examples/fictional-horizon-screen.json
python scripts/quant_workbench.py operations
python scripts/quant_workbench.py prepare examples/fictional-quant-campaign.json --output <research-folder>/quant.inputs.json
python scripts/quant_workbench.py run <research-folder>/quant.inputs.json --output <research-folder>/quant.bundle.json
python scripts/quant_workbench.py verify <research-folder>/quant.bundle.json
```

For a source-bound calculation and report, use:

```text
python scripts/research_workflow.py prepare REQUEST.json --private-output-dir <research-folder>/prepared --request-role "supplied research request"
python scripts/research_workflow.py run <research-folder>/prepared/plan.json --private-output-dir <research-folder>/run
python scripts/research_workflow.py summary <research-folder>/run
```

The request supplies its own contract, jobs, requested-work checklist and claims.
External source files need explicit roles; see the [workflow guide](references/source-bound-workflow.md).
The summary verifies the complete retained run before projecting exact values.
For an already bound request, `quant_report.py run` and `verify` remain available.
`analyst_report.py` renders separate analyst cohorts without pooling provider
consensus, fair value or historical ranges. See [run and report](references/run-and-report.md)
for the input contracts, private artifacts and limitations. These helpers preserve
selected inputs; they do not infer which source or strategy the user intended.

For supplied-data analysis, `research_contracts.py` records selected/unused inputs,
source roles, evidence availability, horizon mode and ranking-method identity.
The workbench also covers explicit trade costs and affordability, dated cash,
vesting shares, portfolio denominators, session P&L, cash/valuation bridges,
corporate actions, dual-SMA/opening-range simulations and forward-study evidence.
These contracts reduce silent model substitutions. They do not guarantee identical
interpretation, independent data acquisition, arbitrary prose or future stock picks.

The [prompt catalog](EXAMPLE-PROMPTS.md) covers novice investing through advanced
quant research, diagnostics, accounting and host handoff. Example values are not
personal recommendations or default constraints on the user's orders.

`scripts/execution_handoff.py` preserves a supplied instruction/payload and advisory
findings for the host. It performs no broker call and requires no local approval
record or risk clearance. The host uses its real broker tools and existing user
instructions. A recommendation-only request is still a recommendation-only request.
Market execution is the default handoff preference when the user requests a buy
without specifying an order type; preserve explicit limit instructions.

Fractional/native-dollar support depends on the actual broker. A dollar input can
be converted to shares at a recent price and therefore need not guarantee exact
spending or a hard final debit. Report actual responses and outcomes, including
uncertainty. Do not turn an empty tool result into a claimed fill or rejection.
Recurring calculations preserve requested per-symbol dollar amounts separately
from rounded quantity and reference-price debit estimates, including when a local
cash/reserve assumption leaves no candidates. These estimates do not establish a
guaranteed market debit, submission or fill, and do not impose a host execution gate.
See [fractional planning](references/fractional-shares.md) for the output fields.

The skill does not manage authentication, custody, transport retries, background
execution or broker order-state transitions.

## Quant and operational limits

Public news polling is not guaranteed high-frequency data. Sentiment triage is a
deterministic research helper, not a calibrated return model. Historical validation
needs appropriate vintages, realistic costs and untouched evaluation data.
News triage rechecks disclosure and observation timestamps in imported reports so
an earlier availability claim cannot admit information from after the cutoff.
Continuous-weight allocation is not comprehensive multi-period tax/margin
optimization; unsupported derivatives and pricing assumptions remain explicit.

Host tools, data rights, entitlements, accounts and reliable infrastructure are
external. The skill helps with investment-manager analysis but does not establish
hedge-fund-manager replacement.

## Provenance and license

Read [PROVENANCE.md](PROVENANCE.md), [SOURCES.md](SOURCES.md) and
[THIRD-PARTY-NOTICES.md](THIRD-PARTY-NOTICES.md). Repository-authored code and
prose use the [MIT License](LICENSE); keep it and the notices with standalone
copies. Dependencies retain their terms, including [arch](ARCH-LICENSE.txt).
Publisher reports and market data retain their own permissions.

Execution-time price changes, quote age and research-to-market price drift do not
trigger a skill threshold, pause or repeat approval. Preserve the user's accepted
market-price uncertainty; state the research as-of time without making it a
condition for the host handoff.
