# Robinhood quant research and portfolio agent

For unspecified stock-discovery requests, use the full U.S. exchange-listed
stock universe. An applicable explicit user scope overrides this default;
analyst-news shortlists and incomplete acquisition do not. See
[the universe rule](SKILL.md#mandatory-default-stock-universe).

The skill includes a retained qualitative sentiment review alongside
the existing deterministic news triage. It distinguishes unscored language from
missing research, preserves contrary and stale evidence, and records coverage
across news, analysts, price/volume, positioning and social sources. It does not
add a trained sentiment model or change the discovery score. See
[sentiment review](references/news-and-guidance.md#complete-the-sentiment-review).

Full fetch remains the default. [Optional partial fetch](references/partial-fetch.md)
can reuse unchanged quarterly statements from an explicitly supplied, sealed
portable bundle after current source-index and revision checks. It refreshes
membership, quotes and full price/action history; estimates, news and events still
need current review. Codex, Muse and Claude use the same opt-in interface and
fall back to fresh acquisition when the bundle or required checks are unavailable.
Hidden model caches are neither assumed nor inspected; no speedup is guaranteed.

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

Source-bound workflows retain decimal-valued evidence as JSON numbers through
export and replay. Portfolio comparisons require a separate final review of
goal/loss implications, applicable source metadata and actual cost-sized
exposures; successful numerical replay alone does not establish recommendation
coverage or comparative diversification.

Allocation results explicitly count distinct known issuers, merge share classes,
and separate cash from unresolved issuer exposure. A total count remains unknown
when identity coverage is incomplete. These counts do not establish correlation
or a diversification ranking; conclusions must retain that distinction.
Unspecified fractional increments use a labeled shared analytical sensitivity,
while actual broker precision stays unknown. Comparison checks retain each
operand's provenance rather than turning matching declarations into source facts.
Affordability retains dated close-price semantics, computes per-contribution
sensitivities separately from forecasts, and refreshes exposure after final sizing.
Budget and allocation outputs include scoped, evidence-linked conclusion facts:
gross exposure, fees and cash remain distinct, and unknown comparative evidence
stays unknown when assembling a recommendation.
Settlement summaries preserve every conditional arrival path, and funding sizing
distinguishes exact rational thresholds from displayed decimal approximations.
Final reporting retains source and scenario checks for factual claims.

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
| Optional partial collection | Explicit sealed research bundle, source-checked unchanged statements, original times and parent hashes; full fetch by default | [Partial fetch](references/partial-fetch.md) |
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
Source preservation and report inventories are distinct from helper processing.
Claims that a helper retained or excluded an item require the actual input and
result pointers; omitted bindings remain calculation omissions. See
[evidence semantics](references/evidence-semantics.md#source-preservation-and-helper-processing).

Small-account comparisons address the supplied goal, loss scenarios and recurring
contributions alongside initial affordability. They distinguish pre-cost targets
from cost-sized exposures and identify omitted assumptions. Narrative coverage
requires review even when the numerical artifacts replay successfully; see
[small-account research](references/small-account-research.md).

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

Conditional proposal summaries retain an explicit comparator for target-distance
direction and reconcile each final branch with the complete timing paths and
scenario assumptions. Numerical replay alone does not validate recommendation prose.

Funding comparison coverage distinguishes the held-asset universe from sampled
quantities, and optional scenarios retain separate source opening conventions.

Source-context evidence distinguishes supplied analytical marks and cost
assumptions from unverified actual execution terms.

## Expanded analysis toolkit (5.0)

The [analysis contracts](references/analysis-contracts.md) route reproducible offline calculations:

- [Technical](references/technical-toolkit.md): explicit OHLCV indicators, sessions, chart geometry,
  SVG charts and costed next-bar replay. Supplied market-depth snapshots are not a live feed.
- [Fundamental](references/fundamental-toolkit.md): ratios and accounting screens, reconciled
  simplified forecasts, FCFF/FCFE DCF, reverse DCF, DDM, residual income, SOTP and seeded scenarios.
- [Sentiment](references/sentiment-toolkit.md): entity/aspect evidence, weighted time decay,
  duplicate review, polarity trends, calibration and causal costed replay. An optional pinned
  local transformer adapter requires separately permitted model weights and dependencies.
- [Factors](references/factor-toolkit.md): sector winsorization/z-scores, FF3/FF5 attribution,
  generic exposure risk and neutralization, training-only PCA and seeded clustering.

All four expose versioned calculations through `quant_workbench.py`. Formula conventions,
missing-data treatment and full input packets are retained for cross-model replay. Independent
language-model agreement and profitable trading are not established by software tests.
Quantum sentiment, proprietary Barra replication and unvalidated RL/recurrent forecasting are
not bundled. Earlier news/sentiment review and all prior workflows remain available.

## Multi-asset research and paper platform (5.0)

Read [platform scope](references/multiasset-platform.md) for the supported instrument conventions,
[derivatives](references/derivatives-toolkit.md) for explicit valuation models,
[paper ledger](references/paper-exchange.md) for hypothetical event accounting and
[platform evidence](references/platform-readiness.md) for scoped host qualification evidence.
The package supports bounded research across equities/ETFs, options, futures, FX, bonds and
spot crypto; live capability and production readiness must be established on the actual host.
It does not bundle a live order service or claim that every modeled asset is tradable there.

The [time-series research tools](references/time-series-toolkit.md) add seeded
GBM scenarios, timestamp-aware backward trend derivatives and fixed-pair train-only
OLS spread normalization. Their [examples](EXAMPLE-PROMPTS.md) require explicit
units, model assumptions and cutoffs. They do not establish ARMA support,
cointegration, calibrated forecasts or an executable arbitrage strategy.

## Portable research extensions

The skill is self-contained: no dedicated backend, server, service or separate
client is required. New bundled scripts provide revision-aware as-of snapshots
and a costed next-open bar simulation using the Python standard library.
Optional local libraries provide ARIMA/cointegration, QuantLib European pricing
and a named VADER baseline. See [portable methods](references/portable-quant.md)
and [bar replay](references/costed-bar-replay.md). The optional dependency file is
`requirements-optional-quant.txt`; installing it is not necessary for the original
workflows. Report missing host capabilities explicitly. No package upload alone
proves those calculations work in Muse or Claude.

## Checked numerical answers

Use the [single-command offline workflow](references/model-alignment-hardening.md)
for explicit requests. It retains execution and verification evidence and renders
supported numeric fields with fixed metric and scenario labels. Concentration
bounds and hash comparisons retain their scope and assumptions. Export availability
is reported separately from calculations; no backend or additional service is needed.
