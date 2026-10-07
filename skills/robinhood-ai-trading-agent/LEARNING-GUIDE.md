# Learning walkthrough

You can study and run everything below without a Robinhood account, an MCP
connection, authentication, installation into Codex, or a trading schedule.
All supplied market/account data are fictional.

## 1. Understand the architecture

    Investment policy and sleeve budgets
                  |
       Research / registered strategy
                  |
        Exact proposed order + fresh snapshot
                  |
       Deterministic risk gate + reasoning review
                  |
       Paper journal / simulated execution

The v3 personal workflow adds broker preview, human grant/mandate,
durable claim, one official submission and reconciliation. That branch is blocked
in this optional learning configuration. Personal Codex invokes connected broker tools after schema-bound local gates; see references/personal-setup.md.

The original ZIP largely told an LLM what to do. This version keeps that workflow
but makes several important invariants executable and testable. The distinction
matters: a sentence saying “avoid duplicate orders” is not a persistent record
that survives a crash.

## 2. Run the short demo

From the extracted package directory:

```powershell
python scripts/learning_demo.py
```

The demo does five things:

1. Evaluates a fictional 20-share limit proposal against a $100,000 fictional
   portfolio. Its planned loss includes stop distance and round-trip friction.
2. Changes only the quote timestamp: the gate blocks the stale quote.
3. Creates a paper claim, whose may_submit_once field is false.
4. Records five filled shares followed by cancellation: those five shares remain
   filled. Cancellation is not a reversal of earlier fills.
5. Attempts the duplicate intent and shows a rejection, then builds a cash-first
   core allocation proposal.

The journal lives in a temporary directory and is removed when the demo exits.
The fixed clock is intentionally historical. Running the fixture through the risk
CLI without --as-of later should reject stale information.

## 3. Explore portfolio management

Read examples/rebalance.json and run:

```powershell
python scripts/portfolio_manager.py examples/rebalance.json
```

Change cash, targets or the drift band in a copy of the example. Observe how the
planner prefers underweights, respects the cash floor and limits turnover. A trim
review never funds a buy before an actual sale settles.

The example sleeve split is illustrative: core 80%, swing 10%, intraday 5%, cash
5%. It is not a recommendation for your personal finances. Core and tactical
holdings have different objectives and cannot be relabeled to avoid a loss.

## 4. Study a signal versus a fill

```powershell
python scripts/strategy_lab.py examples/fictional-intraday.csv --strategy opening_range_breakout
python scripts/strategy_lab.py examples/fictional-intraday.csv --strategy opening_range_breakout --slippage-bps 10
```

A breakout detected at bar close cannot honestly fill at the earlier opening
price of that same bar. The replay enters on a subsequent open, adds friction,
and skips entries above the signal's price limit. If stop and target both occur
within a bar, it assumes the adverse stop came first. This is an explicit modeling
choice, not a claim about actual tick order.

Compare costs, skipped entries and residual positions, not just final profit.
Artificial prices were created to exercise behavior; their returns say nothing
about a tradable market edge.

## 5. Reproduce the numerical bug fix

With GARCH parameters omega=0.1, alpha=0.1, beta=0.8, last variance=1 and last
return=2, the correct next variances are 1.3, 1.27 and 1.243. Beyond the first step,
the expected squared future shock is the prior variance, not zero. The old helper
used zero and would incorrectly produce 1.3, 1.14 and 1.012.

For EGARCH the observed last shock also matters on the first step. Multi-step
EGARCH is explicitly rejected here because simply exponentiating expected log
variance is not the expected variance. A proper extension would use simulation.

After installing requirements in a local virtual environment, run:

```powershell
python scripts/garch_volatility.py examples/fictional-daily.csv --model auto --horizon 5
```

Study the holdout score, constant-variance baseline and caveat. Winning a model
selection comparison is not proof that a strategy makes money.

## 6. Read the tests as failure stories

```powershell
python -m unittest discover -s tests -v
```

Start with the stale quote, cancelled partial fill, timeout/restart, concurrent
claim, core-share ownership, deposit-not-profit, and GARCH recursion tests. Each
captures an observable failure a system must avoid. Numerical tests skip clearly
if dependencies are missing; the full validation report used all dependencies.

## 7. What would be needed on a personal account later?

A separate personal runtime would need an official MCP connection, real data and
calendar normalization, an approved capital/risk mandate, validated strategies,
complete stop/time-exit coverage, reliable monitoring and broker-state recovery.
No such deployment was performed here. See references/broker-integration.md for
the integration boundary and references/research-and-validation.md for the
evaluation ladder.
