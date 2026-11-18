# Reproducible sentiment calculations

Use `scripts/sentiment_toolkit.py` for numerical sentiment evidence, time trends,
supplied classifier diagnostics and historical replay. Keep `sentiment_review.py`
for the broader qualitative review across news, analysts, price/volume, positioning
and social. A numerical text score does not replace those coverage checks.

The six JSON CLI actions are `analyze`, `trend`, `fuse`, `calibrate`, `backtest`,
and `infer-local`. From the skill directory:

```text
python scripts/sentiment_toolkit.py analyze examples/sentiment-offline.json ../new-sentiment-output.json
python scripts/sentiment_toolkit.py trend examples/sentiment-trend.json ../new-trend-output.json
python scripts/sentiment_toolkit.py backtest examples/sentiment-backtest.json ../new-replay-output.json
python scripts/sentiment_toolkit.py calibrate examples/sentiment-calibration.json ../new-calibration-output.json
```

Outputs use exclusive creation: choose a new path rather than overwrite evidence.
Unknown action-level input fields are rejected to catch misspelled options rather
than silently reverting to defaults. Entity IDs are emitted in sorted order.
Examples are fictional. Expected analyze and replay output files are provided for
reproducibility, not evidence that a real investment strategy works.

## Frozen inputs and attribution

`analyze` takes:

- `as_of`: timezone-aware timestamp; optional `window_start` defaults to
  1900-01-01 UTC. Publication must be in that window and both publication and
  availability must be at or before the cutoff. `available_at` means when the
  evidence actually became available to this research process, not merely the
  publication label on a page.
- `entities`: canonical IDs mapped to explicit alias lists. Ambiguous aliases
  remain ambiguous; do not silently choose the desired company.
- `records`: unique `id`, exact `text`, `source`, `published_at`, `available_at`.
- Optional `half_life_hours`, positive, defaults to 72. `source_weights` map
  source IDs to nonnegative judgment weights, default 1. Record the reason for
  chosen weights outside the calculation; they are not learned source accuracy.
- Optional `required_aspects`, defaults to overall, revenue, earnings,
  balance_sheet, guidance, governance. Missing coverage is explicit.
- Optional record `annotations`: `{entity, aspect, start, end}`. Offsets are
  Python Unicode character offsets with an exclusive end; bind to the original
  exact text. Annotations are supplied reviewer attribution, not inferred fact.

Without annotations the baseline splits at sentence punctuation and semicolons,
scores only a clause with one recognized entity and at most one aspect, and
leaves ambiguous clauses missing. No company name is propagated through a
pronoun. Its small positive/negative rules include local negation and debt/leverage
direction. A balance-sheet span naming multiple targets (e.g. cash and debt) is
left unscored rather than applying one global direction to both. Debt and leverage
are one target class; declining debt is positive under the disclosed rule, while
negation reverses that evidence. Rule scores are signed hit averages in [-1,1],
**not probabilities**.
No rule hits is `null`, not neutral. Grammar, sarcasm, numeric comparisons,
long-range negation and unusual financial meanings can exceed these rules.

For precise multi-company or multi-aspect text, provide reviewed spans separately.
A general sequence classifier scores each supplied span; the adapter does not
pretend that FinBERT or another whole-text classifier learned target/aspect
attribution. Use narrow spans and retain their surrounding source evidence.

### Supplied classifier probabilities

An annotation can have `prediction` containing exact keys `negative`, `neutral`,
`positive` in `probabilities`, finite numbers in [0,1] summing to one; `model_id`,
immutable `model_revision`, `computed_at`, and `binding_sha256` are required.
Use the exported `binding(record, annotation)` helper to generate the binding.
It covers record ID, full-text UTF-8 SHA256, source, publication/availability,
entity, aspect, offsets and exact span. Editing any bound field invalidates the
prediction. Model revision `main`, `master` or `latest` is rejected.

Prediction time must be at or after evidence availability and no later than the
analysis cutoff. Supplied prediction polarity is `P(positive)-P(negative)` and
is labeled `supplied_probabilities_not_independently_inferred`, even when another
tool in this package produced the supplied file. Provenance binds bytes, not the
truth of a source, timestamp, model claim or attribution. Retain original input
and model inference output alongside the analysis.

### Deduplication, conflicts and aggregation

Exact normalized span text with the same publication timestamp is grouped within
each entity/aspect. Normalization lowercases and extracts word tokens. Different
dates are different events unless the caller supplies a reviewed event ID.
For paraphrased syndication set `reviewed_event_id` and an `event_review_note` on
each record. This is a reviewer judgment; never assign IDs from similarity alone.
Token Jaccard >=0.85 with >=6 distinct tokens flags possible duplicates but leaves
them separate. It is conservative candidate detection, not semantic verification.

Every original span remains in output. An event's polarity is the weighted mean
of its scored spans (same text, publication instant and polarity duplicates use
only their maximum weight), while its aggregate event weight is the maximum span weight
so syndicated repeats do not multiply its weight. Contradictory positive and
negative evidence remains flagged even if the net score is zero. A span's weight
is `source_weight * 2 ** (-age_hours / half_life_hours)` using publication age.
Each entity/aspect aggregate is the weighted mean of distinct events. No scored
positive-weight events yields missing. Zero can mean balanced conflict or neutral
model evidence; inspect the conflict flag. Very old numerical underflow can make
all weights zero; output remains missing rather than inventing a fresh score.

## Trends, feature fusion and validation

`trend`: takes `sentiment` input, `entity`, `aspect`, strictly increasing `cutoffs`.
Rebuilds every point using that cutoff. Reports expanding z-scores using only
prior nonmissing observations and sample standard deviation; fewer than two or
constant prior observations yields `null`. Overlapping news windows introduce
dependence; these z-scores are not significance tests.

`fuse`: takes `as_of` and `features`, each with unique `name`, nonnegative `weight`
and `value` in [-1,1] or null. Nonmissing features also require `observed_at`,
`available_at`, `normalization` and `evidence_sha256`. Future features are excluded.
The composite is the weighted mean over available features; `weight_coverage`
discloses missing/future input weights. Normalization and feature values are
supplied, not inferred. This can combine sentiment with permitted volatility or
order-book summaries; it neither acquires those data nor implements learned RL.

`calibrate`: takes `rows` and optional integer `bins` (default 10). Each row needs
unique `id`, one of the three `label` values, `probabilities`, one pinned
`model_id/model_revision`, `predicted_at` and later `label_available_at`. Reports
mean three-class sum-of-squares Brier score (not divided by three), negative log
likelihood (floor 1e-15), accuracy and equal-width maximum-confidence ECE. Exact
probability ties choose negative, neutral, positive in that order, disclosed in
output. These are descriptive diagnostics on supplied labels, not automatic
model fitting, proof of a clean holdout, or a profitability test. Keep the label
source, adjudication and train/validation/holdout split in the research evidence.

`backtest`: takes `sentiment`, `entity`, `aspect`, optional `threshold` [0,1]
(default 0), `cost_bps_per_unit_turnover` (default 0; disclose when unknown),
`signal_policy` (only `long_cash`), and nonoverlapping `periods`. Each period has
`decision_at < start < end`, supplied fractional `asset_return` and optional
`cash_return` (default 0). Scores strictly above threshold allocate 100% to the
asset for the next period; other/missing scores allocate to cash. Costs apply to
changes in exposure before the period, and final liquidation after the last
period. Wealth factor is `(1-turnover*cost)*(1+portfolio_return)` and terminal
liquidation multiplies by `(1-exposure*cost)`. Buy-and-hold comparison includes
its entry and final exit costs. Returns are decimals, e.g. .01 means 1%.

An event available during a return interval cannot affect that interval's earlier
decision. Historical supplied classifier outputs computed after the decision
cannot be replayed as contemporaneous predictions. Freeze thresholds, weights,
model/version and historical data before held-out evaluation. Source timestamp
verification, pretrained-model look-ahead, survivorship, impact and strategy
selection bias require separate research checks. This is an exploratory replay,
not a strategy promotion or claim of independent cross-model agreement.

Numeric output uses Python double precision without presentation rounding.
Display rounding is separate; compare numeric replays within a stated tolerance
(1e-12 for these small deterministic fixtures). `input_sha256` hashes canonical
sorted-key compact JSON with Unicode preserved and NaN disallowed, encoded UTF-8.
The algorithm version is `sentiment-toolkit/1`, implementation version 1.0.0.
The inputs, model files/runtime versions and output must travel together.

## Optional local classifier and licensing

`infer-local` uses a **user-supplied existing model directory**; no weights, data
or third-party code are bundled/downloaded by this helper. The template is
`examples/sentiment-local-model.template.json`. It deliberately requires real
values and permission attestation before use; it is not an executable claim that
a model is installed. Supply:

- Model ID and immutable revision, explicit label-index mapping, and SHA256
  manifest for every file in the directory (configuration, tokenizer, weights).
- Exact installed versions of `torch`, `transformers`, `tokenizers`,
  `safetensors`. Mismatch or missing dependency returns `UNAVAILABLE`; no install
  or upgrade is attempted. Only safetensors weights, CPU execution, local files,
  disabled remote custom code, deterministic Torch algorithms and no silent
  input truncation are allowed. Missing, unexpected or mismatched model weights
  fail rather than silently initializing a new classifier head. Explicit label
  mapping must agree with semantic labels in the model configuration when present.
- `license`: identifier, source URL, actual intended use, weights terms,
  training-data terms review and `use_permitted_attestation: true`. Review each
  selected model's actual license; software licensing does not grant weight or
  training-data permissions. Do not fill this from a generic example or assume
  an investment use is noncommercial. Missing permission fails before loading.

The model adapter is implemented, but model inference is **unvalidated until an
appropriate installed model/runtime is actually exercised**. Missing-directory
and permission handling are tested without model weights. A three-class local
financial classifier can be used; choice of architecture is not an accuracy
guarantee. Quantum sentiment, unsupervised RL trading and forced transformer
downloads are intentionally not included.

Local inference records actual UTC completion time for each prediction; this receipt is deliberately
not deterministic or backdated. `portable_contract_sha256` excludes the model
directory path and includes model content hashes, runtime versions, mapping,
license metadata and input items, allowing different host paths. The general
input hash still covers the full submitted request for local audit. Inference is
excluded from the deterministic workbench operations; freeze and review its
resulting supplied probability packet before replaying analysis.

### Sources and provenance

The implementation is original Python code written for this package, without
copying upstream implementation code. No additional dependency is required for
the offline paths. The optional adapter uses documented APIs:

- [Hugging Face model loading API](https://huggingface.co/docs/transformers/v4.52.2/main_classes/model):
  local-only loading and safetensors configuration.
- [ProsusAI FinBERT model card](https://huggingface.co/ProsusAI/finbert): an example
  financial sentiment classifier whose current weights carry CC BY-NC-SA 4.0
  and whose cited Financial PhraseBank data carry CC BY-NC-SA 3.0. The card also
  identifies Reuters TRC2 access terms. Inspect the actual selected revision's
  terms; this example is not unrestricted-use permission and no weights or
  training data are redistributed here.

See [sentiment prompt examples](../examples/sentiment-prompts.md) for exact replay,
new research and optional model requests.
