# Sentiment example prompts

## Offline evidence replay

> Use the supplied sentiment-offline.json without fetching any new data. Run
> sentiment_toolkit analyze and compare the numerical output with
> sentiment-offline.expected.json. Explain ACME revenue and balance-sheet
> polarity separately, distinguish Beta's missing coverage from neutral, and
> report contradictory evidence. Preserve exact inputs and new output. Do not
> turn a text score into a predicted stock return.

Hand checks: at 14:00 UTC, ACME revenue positive evidence at 12:00 has weight
0.25 and negative evidence at 13:00 has weight 0.5; aggregate = -1/3. Debt rises
scores -1 under the disclosed simple debt-direction rule. Beta has no evidence.

## Real company review

> For [company/ticker], evaluate news and earnings-call sentiment as of [timestamp
> and time zone] for my [holding period]. Retain permitted source text and its
> publication and first-available timestamps. Separate revenue, margins, balance
> sheet, guidance and governance. Use entity/aspect-specific supporting spans;
> leave ambiguous text missing. Deduplicate reviewed economic events, retain
> conflicting evidence, and show source coverage. Run the reproducible numerical
> helper alongside the existing qualitative sentiment review. Report the method
> actually used and limitations; do not claim an unavailable model was run.

## Supplied prediction replay

> Replay sentiment-supplied-probabilities.json. Verify all span/text/model bindings
> before scoring. Keep supplied probabilities visibly separate from locally
> inferred results and from the rule baseline. These fixture probabilities are
> fictional; explain what evidence would be needed to validate an actual model.

## Historical validation

> Run sentiment-backtest.json with the frozen threshold and costs. Compare with
> sentiment-backtest.expected.json and buy-and-hold after both entry and exit
> costs. Identify any periods with missing evidence and ensure each decision uses
> only information available before its next return interval. Do not tune the
> threshold using the evaluation results. Then use sentiment-calibration.json
> to demonstrate Brier score, log loss and ECE, clearly noting the tiny fictional
> label sample does not validate generalization.

## Optional installed local model

> Check whether my supplied financial classifier is locally available and its
> actual software, weights and training-data terms permit [intended use]. Use my
> reviewed license metadata, immutable revision, complete SHA256 file manifest,
> exact package versions and verified label mapping to fill the local-model
> template. If missing or not permitted, report the limitation and use the
> explicitly labeled offline baseline. Do not install or download a model. If
> inference runs, retain raw outputs and bind each probability vector to the
> exact supplied entity/aspect evidence span before aggregation.

## Trends and transparent fusion

> Run sentiment-trend.json and explain the prior-only z-scores; do not fit using
> later observations. For my separately supplied normalized volatility and
> order-book features, use the fuse action with explicit fixed weights,
> availability timestamps and evidence hashes. Report unavailable feature weight
> and the change in interpretation when coverage is incomplete. This is a fixed
> composite, not a trained trading policy.
