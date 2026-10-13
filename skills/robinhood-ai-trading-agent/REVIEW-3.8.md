ARCHIVAL RECORD — historical results and implementation only.

This file is not current setup guidance or execution policy. Previous
execution gates described below are retired. The current skill imposes
zero execution gates; research findings are advisory. Consult SKILL.md and references/execution-handoff.md.

---

# Version 3.8 review

The earlier 20% overlap compared discretionary selections with different deep-review
coverage. It did not test replay of the deterministic VQM engine. Version 3.8 adds
a named public-data discovery stage and a fixed research queue before primary
investment review. It does not lower the strict filing or live execution gates.

## Changes

- Fresh full-universe acquisition, dated membership evidence and an SPY cross-check.
- Explicit vendor accounting fields, fiscal periods, prices and peer definitions.
- Deterministic Value/Quality/Momentum weights, share-class selection and tie-breaks.
- Hashed raw-input bundles, replay verification and an 80% candidate-overlap comparator.
- Coverage tracking that exposes skipped higher-ranked candidates.
- Bounded provider backoff, same-run recovery and incomplete-acquisition rejection.
- Arithmetic checks for displayed P/E, same-period EPS revisions and downside cases.

## Limits

The discovery stage uses public vendor approximations. It cannot establish filing
eligibility, expected returns or Strong Buy confidence. Missing accounting fields
and unsupported specialized bank/REIT metrics remain exclusions. All securities
must be attempted; the scored subset must be disclosed. Prior-period publication
timing is not certified for a point-in-time backtest.

The [independent Muse/Codex test](references/muse-codex-validation-2026-10-11.md)
passed with 10/10 candidate overlap and eight matching rank positions. Both full
bundles replayed locally. Scores and exclusions differed: 401 versus 414 issuers
were scorable from independently collected vendor inputs. The test does not
establish buy eligibility or guarantee future agreement. No calculation was tuned
after seeing Muse's picks. An output-directory instruction was clarified after
Muse's recovered startup error; software behavior was unchanged.
