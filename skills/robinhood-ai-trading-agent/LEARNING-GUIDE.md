# Learning walkthrough

These exercises use fictional market and account data. They run locally without
a Robinhood connection, authentication or a trading schedule. Install the Python
dependencies described in [INSTALL.md](INSTALL.md) before numerical exercises.

## 1. Understand the workflow

The skill turns the user's research question and supplied inputs into evidence,
calculations, recommendations and an optional broker handoff. Research diagnostics
are advisory. The skill imposes no execution gates, policies, grants or journals
that must be completed before an order. Actual broker and platform requirements
remain external. A local handoff is a proposed payload, not a submission or fill.

## 2. Run the short demo

From the extracted skill folder:

```text
python scripts/learning_demo.py
```

The demo prints three outputs: fictional risk diagnostics, core rebalance
candidates and a native execution handoff. It uses a fixed historical clock and
the supplied order, snapshot and planning parameters. It does not call a broker,
create a durable order journal, submit a trade or simulate broker acknowledgments.
Read the output's status and assumptions; a risk observation is not a permission.

## 3. Explore portfolio planning

```text
python scripts/portfolio_manager.py examples/rebalance.json
```

Change cash, targets or drift bands in a private copy of the example. Compare
underweight candidates, modeled cash usage and turnover. The supplied sleeve
weights and reserve are exercise inputs, not defaults for personal finances or
execution requirements. Broker-reported settled cash and estimated sale proceeds
are different observations; see [cash planning](references/settled-cash-planning.md).

## 4. Study a signal versus a modeled fill

```text
python scripts/strategy_lab.py examples/fictional-intraday.csv --strategy opening_range_breakout
python scripts/strategy_lab.py examples/fictional-intraday.csv --strategy opening_range_breakout --slippage-bps 10
```

Compare the completed-bar signal, subsequent modeled entry, friction, skipped
entries and residual positions. If a stop and target both occur within one bar,
the replay uses the adverse ordering. This is a modeling assumption, not proof
of the actual tick sequence. Returns from invented prices establish no market edge.

## 5. Examine conditional volatility

```text
python scripts/garch_volatility.py examples/fictional-daily.csv --model auto --horizon 5
```

Review the fitted model, observation frequency, forecast horizon, holdout score
and constant-variance comparison. GARCH and GJR-GARCH multi-step forecasts use
expected future squared shocks; substituting zero produces a different forecast.
The supported EGARCH path is one-step only: exponentiating expected log variance
is not a valid substitute for an implemented multi-step simulation. A failed or
unsupported fit limits the analysis, not trading authority. See
[volatility models](references/garch-volatility.md).

## 6. Inspect repeatability and reporting

Follow the [quant workbench](references/quant-workbench.md) to inspect available
operations, retain explicit inputs and defaults, compute a bundle and verify it.
Use [report facts](references/report-facts.md) to project supported output values
into a private JSON or Markdown table. Preserve units, denominators, unknown
metadata and rejected outcomes; matching numbers do not establish authentic data
or investment effectiveness.

The software tests can be run locally:

```text
python -m unittest discover -s tests -v
```

Tests cover implemented calculations, input handling, accounting, source timing,
handoff payloads and reporting behavior. A passing suite is software evidence,
not audited live broker behavior or validated strategy performance.

## 7. Apply the workflow to personal research

Replace fictional observations with appropriately dated evidence, preserve the
research objective and horizon, and disclose missing coverage. When the user asks
to trade, pass their existing instructions to the host's available broker tools
and report its actual response. Empty responses do not establish a fill. Read
[personal setup](references/personal-setup.md) and
[broker integration](references/broker-integration.md) for the current boundary.
