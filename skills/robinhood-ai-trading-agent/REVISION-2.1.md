> Historical review/checkpoint. Current scope and controls are in [REVIEW-3.0.md](REVIEW-3.0.md); learning-only restrictions below describe earlier releases.

# Version 2.1.0 — GARCH discovery correction

Date: October 7, 2026.

The previous delivered ZIP included references/garch-volatility.md and
scripts/garch_volatility.py. Its main SKILL.md linked to both, but did not contain
an explicit GARCH section. That made it easy for a receiving agent reading only
the main file to miss the feature or misdescribe it as an outside addition.

This revision:

- Names GARCH in the discovery description and gives it an explicit main section.
- Requires assessment on stock-screen finalists and before tactical sizing, with
  a disclosed skip when unavailable or disabled rather than an invented result.
- Connects the $500 research flow, tactical reference and report templates to it.
- Documents evidence, model eligibility, units and actual training/holdout counts.
- Adds version 2.1.0 to the main file, README and VERSION for identifying stale copies.

The numerical helper and execution controls are unchanged. The prior numerical
test transcript remains in VALIDATION.txt. This revision adds packaging/document
checks recorded in REVISION-VALIDATION.txt; it does not claim new live validation.

## Use the complete package

Extract/provide the entire versioned ZIP. A lone SKILL.md can explain the GARCH
procedure but cannot supply absent scripts or references. Preserve any personal
runtime policy/state separately; this archive does not migrate or replace it.

Suggested message for the receiving Codex:

> Load the complete Robinhood AI Trading Agent v2.1.0 package. Confirm the version
> in SKILL.md and availability of references/garch-volatility.md and
> scripts/garch_volatility.py. Follow the explicit GARCH overlay section. Report
> the implementation and actual data/holdout counts for any computed result, or
> the specific reason it was skipped. Keep this run research/paper-only.

The default helper needs 291 price rows: 250 training returns and 40 holdout returns.
“Roughly one year” is not a count and typically does not meet that daily-data
default. This observation does not establish whether another implementation was
valid; inspect that run's actual data, settings and output before drawing a conclusion.
