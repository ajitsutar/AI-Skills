# Analysis contracts and cross-model replay

The 5.0 expansion adds practical technical, fundamental, sentiment and factor calculations.
Read the relevant [technical](technical-toolkit.md), [fundamental](fundamental-toolkit.md),
[sentiment](sentiment-toolkit.md) or [factor](factor-toolkit.md) schema before constructing inputs.
These helpers calculate on declared inputs. They do not authenticate a source, select an
optimal investment, or establish predictive performance by themselves.

## Shared workbench route

Use the existing `scripts/quant_workbench.py operations` catalog. New operation names:

- `technical.analyze`, inputs `request` (technical JSON packet) and `data_available_at`
  (timezone-aware instant when all completed bars/snapshot data were available). This is
  a supplied evidence assertion, not an inference from bar-open labels or a date-only row.
- `fundamental.calculate`, input `d`: fundamental JSON packet including its operation,
  currency and amount unit.
- `sentiment.analyze`, `.trend`, `.fuse`, `.calibrate`, `.backtest`, input `document`:
  corresponding sentiment JSON packet. Optional live local-model inference is deliberately
  separate; retain its prediction receipt before freezing a calculation.
- `factor.normalize`, `.fama_french`, `.style_risk`, `.neutralize`, `.pca`, `.kmeans`:
  named parameters shown by `operations` and the factor reference.
- `derivatives.calculate`, `paper.replay`, `platform.assess` and `timeseries.run`:
  exact explicit `document` schemas linked from [multi-asset platform scope](multiasset-platform.md).
  Their information cutoffs cannot exceed the frozen workbench cutoff. Research
  projections and hypothetical paper fills retain their distinct evidence status.

A workbench document has `schema_version: 1`, `contract` with `prompt`, `purpose`,
`base_currency`, `horizon_id` and timezone-aware `as_of`, and `jobs` with unique `id`,
`operation` and `inputs`. See `examples/analysis-workbench.json` for a complete fictional
packet. Materialize defaults before sharing inputs:

```
python scripts/quant_workbench.py prepare examples/analysis-workbench.json --output ../prepared.json
python scripts/quant_workbench.py run ../prepared.json --output ../result.json
python scripts/quant_workbench.py verify ../result.json
```

Output files must be fresh paths outside the installed skill. Freeze the prepared input for
both participants; do not share one participant's result with the other. `run` records package,
implementation, inputs, contract and runtime versions; `verify` recomputes and compares values.
A matching replay checks calculation compatibility, including compatible rejections. It does
not validate a model's narrative, independently selected sources or a strategy's future returns.

## Reduce interpretation drift

1. Retain the original request and the source facts, dates and units separately from derived
   assumptions. Confirm price adjustment/session basis and annual-versus-quarterly accounting
   periods. Missing evidence remains missing; do not let a participant fill it silently.
2. Record formula variants, rate units, denominators, terminal-value convention, costs, seed,
   indicator lookbacks and warmup treatment explicitly. For optional ML, pin weights by hashes,
   software versions, label mapping and exact text spans. Licenses must permit the intended use.
3. Use `prepare` to expose argument defaults and the technical/sentiment nested defaults.
   Fundamental models require their material assumptions explicitly. Statistical train/test
   arrays must already reflect the declared cutoff; the helpers cannot discover when an
   unlabelled number became public. Fit all preprocessing on training data only.
4. Run the packaged code. Cite output paths and named fields in the report, retain unrounded
   values, and state display rounding. Do not reproduce arithmetic from memory or turn a
   missing/partial result into a definitive conclusion. Describe independent interpretation
   separately from computed fields.
5. Compare the same prepared input, package, formula variants and model weights. Default replay
   tolerances are absolute 1e-8 and relative 1e-7; do not treat equivalent PCA basis rotations as
   investment disagreement. Exact byte identity across CPU/BLAS/model runtimes is not promised.

Reproducibility is conditional on identical evidence and assumptions. This package adds no
requirement to repeat approvals or change a user's broker instruction. No live broker capability
is supplied by these calculation helpers.

## Explicit limits

Intraday feed access, order-book history, commercial analyst databases and permitted local
transformer weights are not bundled. Supplied depth is a snapshot; OHLCV volume profiles are
approximations. The accounting forecast covers the documented simplified nonfinancial model,
not every GAAP/IFRS line item. Piotroski/Altman/Beneish are screens with applicability limits,
not fraud/default predictions. Factor risk is generic, not proprietary Barra. Quantum sentiment,
unvalidated reinforcement learning and recurrent forecasts are excluded from this expansion.
Software tests and golden arithmetic fixtures do not claim Muse/Claude/GPT agreement.
