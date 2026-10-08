# Robinhood portfolio and trading agent

Version **3.4.0 — October 8, 2026**. A portable skill for **personal Codex**, with
a long-term core and separately budgeted swing/day trading in an active supervised
session. It starts in paper mode and supports exact-order approval or a bounded
mandate through the connected official Robinhood Trading MCP.

Explore [50 example prompts, from beginner to advanced](EXAMPLE-PROMPTS.md) for
getting started, stock research, portfolio management, swing/day trading,
quantitative analysis, and execution controls. Choose and adapt the examples;
they do not change the skill's operating policy or grant trading authorization.

Provide/extract the **entire ZIP**, not only SKILL.md. Ask the personal agent to
identify version 3.4.0 and verify its supporting files before use. GARCH is
explicitly part of this skill and has an executable, audited helper.

Version 3.4 adds a configurable dollar/percentage reserve held in usable settled
cash before new day-trade buys. It prevents unsettled sale proceeds from satisfying
that reserve, accounts for pending buys and leaves necessary exits available.
Read [the settlement review](REVIEW-3.4.md) and
[configuration and waiting behavior](references/settled-cash-planning.md).

Version 3.3 adds holding-period planning from intraday to decades, explicit entry
and hold-event policies, latest-financial-period checks and dated net scenario
comparisons. It retains the separate day-trading signal and live-execution gates.
Read [the current review](REVIEW-3.3.md) and
[holding-period planning](references/holding-period-planning.md).

Version 3.2 restores historical source credits and uses the licensed arch backend
for volatility estimation. Read the [release review](REVIEW-3.2.md),
[provenance](PROVENANCE.md), [acknowledgments](SOURCES.md), and
[dependency notices](THIRD-PARTY-NOTICES.md). The repository has not selected a
license for its own material. Revalidate saved volatility results after upgrading.

Version 3.1 adds a declared research method, distinct discovery dispositions and
report checks that keep Watch names out of an Eligible comparison. See the
[research update](REVIEW-3.1.md) and [run methodology](references/research-run-methodology.md).

Start with [personal setup](references/personal-setup.md). Read the
[complete review](REVIEW-3.0.md) for implemented controls, test results and the
account-specific checks still needed before activation. This build did not connect
to a brokerage, place trades, install a skill or create a schedule.

## Research and trading routes

- **Any requested hold:** exact units and entry/exit clock, same-session versus
  overnight exposure, fixed versus rolling deadline, and provisional future
  calendars. Supports ten years and longer without a skill-imposed maximum.
- **Swing / dated hold:** within-window thesis, latest primary evidence, event
  exposure, net terminal scenarios, portfolio fit and an explicit exit plan.
- **Long term:** configurable universe → suitable sector/industry valuation →
  earnings/FCF normalization → balance-sheet/value-trap review → analysts,
  dispersion and revisions → events → GARCH risk overlay → portfolio fit.
- **Day trading:** independent liquid watchlist → session/catalyst/liquidity checks
  → validated completed-bar setup → entry/stop/target/time exit → costs and sizing
  → live readiness → authorization → orders, partial fills and exit reconciliation.

S&P 500 is an editable starting universe. There is **no fixed number of picks**.
The answer may be no suitable trade. See [screening](references/screening-and-value-traps.md),
[day trading](references/short-term-trading.md) and
[the $500 research example](references/small-account-research.md).

## Local setup

Python 3.11+; run from the extracted package directory. Commands below create only
an isolated environment and a draft paper runtime. Choose a new runtime directory.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-tested.txt
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe scripts/personal_runtime.py init ..\robinhood-runtime
.\.venv\Scripts\python.exe scripts/personal_runtime.py doctor ..\robinhood-runtime
```

Doctor intentionally reports **draft/paper**, not live readiness. Configure the
policy with the personal agent using actual account data and investor preferences.
`requirements-tested.txt` pins the direct libraries and statsmodels used for this release;
`requirements.txt` contains compatible ranges. Neither is a complete transitive
lockfile. Use an isolated environment and rerun tests after dependency updates.

## Components

| Component | Implemented behavior |
|---|---|
| Skill and references | Separate portfolio, value-screening and tactical workflows; source discipline |
| research_data / research_analytics | SEC exact-context facts; public daily history; configurable provider; peers, earnings/FCF bridges, scenarios, targets and estimate revisions |
| screen_review / price_audit | Coverage, declared-method hashes, hypothesis/Eligible report checks, candidate classifications and corporate-action/jump/session declarations bound to exact price files |
| horizon_review | Same-session/elapsed/calendar/session clocks through multi-decade holds, latest-period consistency, event scope, rolling reviews and same-exit net scenarios; research only |
| garch_volatility | GARCH/GJR/one-step EGARCH; prefix-only holdout versus baseline; reproducible model outputs |
| portfolio_manager / portfolio_analytics | Cash-first rebalance, ETF look-through, aligned covariance, stress scenarios |
| accounting_tools | Cash reconciliation, flow-timed returns, lot-selection proposals and wash-sale review flags |
| risk_engine / personal_readiness | Cash, reservations, exposure, loss breakers, event windows, sources, model/strategy evidence and exact request checks |
| broker_bridge | Actual-schema mappings, including nested legs, enum translations, fixed semantics and private-routing redaction |
| execution_ledger | Durable authorization, deduplication, cumulative fills, cancellation reservations and conflict recovery |
| supervised_session / personal_runtime | Owner lease, heartbeat, protection/time-exit action planning, init/doctor and local command interface |
| strategy_lab | Causal example OHLC replays and chronological forward windows; research baselines remain unvalidated |

## Try the offline examples

```powershell
.\.venv\Scripts\python.exe scripts/learning_demo.py
.\.venv\Scripts\python.exe scripts/screen_review.py examples/fictional-screen.json
.\.venv\Scripts\python.exe scripts/screen_review.py examples/fictional-horizon-screen.json
.\.venv\Scripts\python.exe scripts/garch_volatility.py examples/fictional-daily.csv --data-audit examples/fictional-daily.audit.json --model garch --horizon 1
.\.venv\Scripts\python.exe scripts/strategy_lab.py examples/fictional-intraday.csv --strategy opening_range_breakout
```

All bundled accounts, grants and prices are fictional. Offline test grants do not
create real permissions. The learning guide remains an optional introductory lab.

## Personal execution prerequisites

The Python helpers do not contain a credential client or submit network orders.
The **personal Codex host** discovers and invokes actual authenticated broker tools
after a durable claim. No actual MCP schemas/account were available in this review;
schema tests use clearly fictional tools. The template has no assumed capabilities.

Live tactical entries require verified native atomic protection, partial-fill
coverage and exclusive exits, plus a tested supervised time-exit/handoff procedure.
If the connected broker cannot supply this, tactical operation remains research,
paper or human execution. A running chat has no guaranteed latency and does not
monitor after it closes. Code tests do not establish a profitable strategy.

Whole-share, unlevered, long-only US stocks/nonleveraged ETFs and regular-session
DAY limit parent/reduction orders are supported. Options, short selling, fractional
orders and extended hours need additional adapters. A small budget may size to zero.

Optional installation copies the skill only to an **explicit new destination**;
it never overwrites an existing skill or installs credentials. Keep policy, journal,
evidence and personal account state outside the installed skill. See the setup guide.

The current live tactical signal adapter recomputes opening-range breakout from
completed bars and binds code, parameters and order economics; it is unpromoted
until actual market/forward-paper validation succeeds. The daily SMA example is
research-only. Supported ETF look-through covers equities and explicit USD cash;
other underlying instruments require additional exposure mapping before entry.
