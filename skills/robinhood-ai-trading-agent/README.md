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
| Holding-period decisions | Same-session, dated and flexible long-term research with matching event and scenario analysis | [Holding periods](references/holding-period-planning.md) |
| Financial diligence | Sector-relative valuation, normalized earnings/FCF, balance-sheet and value-trap analysis | [Investment review](references/screening-and-value-traps.md) |
| News and guidance | Dynamic source discovery, public feed polling, between-quarter projections and deterministic text triage | [News and guidance](references/news-and-guidance.md) |
| Analyst evidence | Accessible reports, forward target distributions, revisions and sourced analyst track records | [Analyst research](references/analyst-research.md) |
| Portfolio decisions | Contributions, fractional allocation, rebalance proposals, ETF look-through, concentration, scenarios and tax-lot review | [Portfolio management](references/portfolio-management.md) |
| Tactical research | Completed-bar setups, catalysts, liquidity, cost assumptions, stops/targets and holding-period scenarios | [Short-term research](references/short-term-trading.md) |
| Volatility analysis | GARCH, GJR-GARCH, supported EGARCH and stock-relative interval-move diagnostics | [Volatility models](references/garch-volatility.md) |
| Quant construction | Constrained allocation, covariance sensitivity, empirical tail loss and multi-asset scenarios | [Quant workbench](references/quant-workbench.md) |
| Strategy evaluation | Causal splits, purging, HAC, block bootstrap, multiple-testing review and retained evidence | [Quant research](references/quant-research.md) |
| Performance accounting | Execution shortfall, cash ladders, TWR/XIRR, attribution and portfolio simulation | [Manager workflow](references/institutional-manager.md) |
| Reproducibility | Frozen research contracts/data, numerical replay, cross-model comparison and incremental refresh | [Research handoff](references/research-handoff.md) |
| Execution handoff | Preserve the user's order instructions, surface findings as advisory and pass the payload to the host | [Execution handoff](references/execution-handoff.md) |

Stock discovery defaults to **all U.S. exchange-listed stocks including listed
ADRs**. S&P 500, custom lists and other universes are explicit choices. Report
actual membership, coverage, exclusions and unresolved data; do not call a subset
a full-market screen. There is no fixed number of picks or maximum holding period.
Instrument-specific calculations remain limited by their implemented models.

## Recommendations and evidence

The shared Value–Quality–Momentum profile produces a reproducible research queue,
followed by primary-source, horizon and portfolio review. Keep numerical rank,
valuation evidence and recommendation confidence distinct. A relative factor score
is not an expected return. Research labels describe the evidence; they do not
approve, deny or restrict a broker order.

Use SEC filings, issuer releases and appropriate accessible finance providers.
Yahoo is one acquisition adapter. Record source dates, accounting basis and
changes between quarterly filings. Analyst targets and track records are sourced
opinions/statistics, not guaranteed outcomes. News headlines, accessible reports,
paywalls and missing sources have different evidentiary value.

The package has no demonstrated universal alpha or calibrated Strong Buy
classifier. Make recommendations proportional to the evidence and state material
uncertainty. A completed calculation or matching model output establishes neither
investment performance nor professional-manager equivalence.

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
python scripts/quant_workbench.py run examples/fictional-quant-campaign.json --output <research-folder>/quant.bundle.json
python scripts/quant_workbench.py verify <research-folder>/quant.bundle.json
```

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
The skill does not manage authentication, custody, transport retries, background
execution or broker order-state transitions.

## Quant and operational limits

Public news polling is not guaranteed high-frequency data. Sentiment triage is a
deterministic research helper, not a calibrated return model. Historical validation
needs appropriate vintages, realistic costs and untouched evaluation data.
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
