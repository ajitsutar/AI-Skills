# Robinhood portfolio and trading agent

A self-contained skill for stock research, portfolio management, quantitative
analysis and supervised personal trading. It combines public evidence with
replayable calculations, separates long-term investing from swing and intraday
strategies, and keeps research decisions distinct from permission to trade.

Use it in Codex or another compatible Agent Skills host. Research is not restricted
to Robinhood holdings or Yahoo data. The broker-specific execution workflow uses
the connected official Robinhood Trading MCP and its actual capabilities.

Start with [example prompts, from first-time investors through quants](EXAMPLE-PROMPTS.md),
[installation](INSTALL.md), or the [agent instructions](SKILL.md).

## What you can do

| Workflow | Current capability | Guide |
|---|---|---|
| Find and compare stocks | Screen all U.S. exchange-listed stocks, including listed ADRs, or an explicitly selected universe; retain coverage and exclusion reasons | [Research campaign](references/research-campaign.md) |
| Evaluate an investment thesis | Review sector-relative valuation, normalized earnings/FCF, balance-sheet risks, business quality, catalysts and downside | [Screening and value traps](references/screening-and-value-traps.md) |
| Plan a holding period | Resolve same-session trades, dated exits or flexible long-term holds; compare evidence, events and net scenarios at the actual horizon | [Holding-period planning](references/holding-period-planning.md) |
| Follow news and guidance | Discover relevant issuer, SEC, exchange, macro and financial-publisher sources; poll configured public feeds; triage language and compare reviewed guidance ranges | [News and guidance](references/news-and-guidance.md) |
| Review analyst evidence | Discover accessible reports and attributed excerpts; compare forward targets, dispersion and revisions; retain provider-reported analyst performance with its methodology | [Analyst research](references/analyst-research.md) |
| Manage a portfolio | Review contributions, concentration, ETF look-through, rebalance proposals, covariance, stress exposure, tax lots and potential wash-sale interactions | [Portfolio management](references/portfolio-management.md) |
| Research swing/day trading | Build a liquid watchlist, review catalysts, evaluate supported completed-bar setups and model entries, stops, targets, costs and time exits | [Short-term trading](references/short-term-trading.md) |
| Estimate volatility | Run GARCH, GJR-GARCH and supported EGARCH forecasts with chronological baseline comparisons and retained model outputs | [Volatility models](references/garch-volatility.md) |
| Construct and stress allocations | Calculate cash/cost/risk-constrained weights and selected equity, FX, futures, European-option and fixed-bond scenarios | [Quant workbench](references/quant-workbench.md), [multi-asset scope](references/multi-asset-playbook.md) |
| Validate a quantitative strategy | Use causal splits, purging, HAC, block bootstrap, multiple-testing controls, factor attribution and retained promotion evidence | [Quant methods](references/quant-research.md) |
| Measure implementation and performance | Calculate execution shortfall, cash ladders, TWR, XIRR, period attribution and causal portfolio simulations | [Manager workflow](references/institutional-manager.md) |
| Reproduce and update research | Lock the mandate, preserve source files and calculations, compare replayed outputs, and refresh saved research without losing its audit trail | [Research handoff](references/research-handoff.md), [research library](references/research-memory.md) |
| Prepare controlled execution | Check settled cash, reserved funds, exposures, strategy evidence and exact requests; track authorizations, fills, cancellation and reconciliation | [Execution controls](references/approval-gated-execution.md) |

### Universe and horizon

When the user does not specify a universe, stock discovery starts with **all U.S.
exchange-listed stocks, including listed ADRs**. S&P 500 is an explicit preset.
Liquidity, security type, listing status, currency and missing-data checks still
determine suitability for the chosen workflow. Research membership does not broaden
an approved trading allowlist. Other instruments and foreign-only/OTC universes
require the appropriate configured route.

The skill accepts arbitrary holding periods, with no fixed maximum. Same-session
day trading is distinct from an overnight hold. Fixed exit dates, rolling thesis
reviews and future calendar uncertainty are handled explicitly. A model's validated
horizon remains narrower than the set of horizons the planner can describe.

There is no fixed number of picks. A requested list can remain incomplete when
evidence is missing, and the correct result can be no suitable trade.

### Evidence and reproducibility

Fundamental stock discovery uses the shared Value–Quality–Momentum research queue,
then primary-source, horizon and portfolio review. Saved code, data, assumptions
and evidence decisions make calculations replayable across models. The skill
distinguishes research candidates from reviewed selections and never treats a
factor score as an expected return.

SEC filings, issuer releases and appropriate accessible providers can supply or
cross-check facts. Yahoo is one acquisition adapter. New information between
quarterly reports matters: guidance changes, preannouncements, financing, investor
days and other material disclosures trigger renewed review. Source corrections
preserve the original snapshot and require a full reranking when relevant.

News and analyst research dynamically discover relevant websites and record actual
access. Full reports, attributed excerpts, headlines, paywalls and unavailable
sources remain distinct. Repeated coverage of one analyst's call is not independent
consensus. Forward price targets are separate from historical 52-week highs/lows
and intrinsic fair-value estimates. Provider-reported analyst success is not an
independently verified probability of future success.

The news helper supplies a small deterministic language rule set and event-review
hints. It is not a trained NLP model or calibrated sentiment-return strategy.
Public feeds support measured polling; complete news access and high-frequency
execution are not available merely because a feed can be read.

## Get started

Keep the entire skill folder together, including scripts, references, profiles,
templates and tests. Uploading only `SKILL.md` omits required components. No files
from another skill or the repository root are needed. See [INSTALL.md](INSTALL.md)
for standalone Codex/Agent Skills, Claude Code and ZIP installation paths.

Use Python 3.11 or newer. From the extracted skill directory, the following
PowerShell commands create an isolated environment and a new draft paper runtime
beside the package:

```powershell
python -m venv ..\trading-env
..\trading-env\Scripts\python.exe -m pip install -r requirements-tested.txt
..\trading-env\Scripts\python.exe scripts/research_preflight.py
..\trading-env\Scripts\python.exe -m unittest discover -s tests -v
..\trading-env\Scripts\python.exe scripts/personal_runtime.py init ..\robinhood-runtime
..\trading-env\Scripts\python.exe scripts/personal_runtime.py doctor ..\robinhood-runtime
```

Choose unused environment/runtime directories. On macOS/Linux use `python3` and
the environment's `bin/python`. Preflight checks package integrity and research
dependencies. Doctor intentionally reports draft/paper findings before personal
configuration; these are not proof of live readiness.

`requirements-tested.txt` pins tested direct dependencies;
`requirements.txt` provides compatible ranges. Neither is a complete transitive
lockfile. Retest after dependency changes. An installation copies the skill, not
credentials, authenticated tools or a ready brokerage connection.

The [personal setup guide](references/personal-setup.md) covers policy, account
discovery, runtime commands and session operation. Keep personal policy, research
archives, evidence and durable account journals outside the installed skill and
public repository. Use an explicit new installation destination and avoid
duplicate installed copies; preserve existing runtime state during upgrades.

## Try the offline workflows

After creating the runtime above, run examples with fictional data:

```powershell
..\trading-env\Scripts\python.exe scripts/learning_demo.py
..\trading-env\Scripts\python.exe scripts/screen_review.py examples/fictional-horizon-screen.json
..\trading-env\Scripts\python.exe scripts/quant_workbench.py run examples/fictional-quant-campaign.json --output ..\robinhood-runtime\reports\quant.bundle.json
..\trading-env\Scripts\python.exe scripts/quant_workbench.py verify ..\robinhood-runtime\reports\quant.bundle.json
```

Use a new result path for each run. Bundled prices, accounts and grants are
fictional; examples do not create real permissions or demonstrate investment
performance. The [prompt catalog](EXAMPLE-PROMPTS.md) covers practical research,
portfolio, tactical and quantitative requests beyond these software examples.

For actual news polling, guidance comparison and analyst arithmetic, follow their
linked guides and supply the requested sources, timestamps and evidence files.
One news-poll invocation makes one pass; it does not create a background monitor.

## Personal execution

The runtime starts in **paper mode**. Exact-order approval and bounded autonomous
operation require a current, explicitly authorized policy, verified broker tools,
strategy evidence and an active supervised session. Installing the package or
requesting research does not activate live trading.

The Python helpers prepare and validate local records; they contain no broker
credential client or network order path. The host invokes actual authenticated
broker tools only after the applicable request and authorization checks. Unknown
submission outcomes require reconciliation before any retry.

The execution adapter is limited to whole-share, unlevered, long-only U.S. stocks
and nonleveraged ETFs, with supported regular-session DAY limit parent/reduction
orders. Fractional orders, options, short selling and extended-hours execution
require additional adapters. A small budget can therefore produce no executable
whole-share order even when the security is useful for research.

Live tactical entries require verified native atomic protection, partial-fill
coverage, exclusive exits and a tested time-exit/handoff procedure. The registered
opening-range-breakout adapter recomputes completed-bar signals; its presence does
not promote the strategy for live use. Broker support, forward evidence and
authorization must independently pass. Configure the
[settled-cash reserve](references/settled-cash-planning.md) before day-trade entries;
unsettled proceeds cannot satisfy it.

A supervised chat has no guaranteed response latency and stops observing when it
closes. If required broker protection or supervision is unavailable, retain
research/paper mode or use human execution. Read
[broker integration](references/broker-integration.md) for exact capability and
reconciliation requirements.

## Limits and responsible interpretation

The package implements analytical and operational tools, not a demonstrated source
of alpha. **Strong Buy is unavailable without a separately validated classifier.**
Unit tests establish selected software behavior; calculation agreement between
models does not establish profitable investment performance or identical judgments
when models acquire different evidence.

Historical validation requires suitable point-in-time data, complete trial records,
realistic costs and untouched evaluation. The allocator uses continuous weights;
multi-period tax optimization, comprehensive margin modeling and unsupported
derivatives remain outside its implemented scope. Source availability, licenses,
broker entitlements, custody, audited administration and resilient always-on
infrastructure are external dependencies.

See the [capability and remaining-gap review](references/institutional-gap-review-4.2.md)
and [strategy validation requirements](references/shared-strategy-validation.md).
The skill can support an investment manager's research process; equivalent
professional performance and replacement of a hedge-fund manager are unestablished.

## Provenance and licensing

Read [PROVENANCE.md](PROVENANCE.md), [SOURCES.md](SOURCES.md) and
[THIRD-PARTY-NOTICES.md](THIRD-PARTY-NOTICES.md) for origin, influences and dependency
notices. The repository has not selected a license for its own material. The
upstream [arch notice](ARCH-LICENSE.txt) applies to that dependency, not to the
entire skill. Public availability of code or research does not itself grant
redistribution rights over publisher reports or retrieved market data.
