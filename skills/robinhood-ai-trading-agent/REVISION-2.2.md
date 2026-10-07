> Historical review/checkpoint. Current scope and controls are in [REVIEW-3.0.md](REVIEW-3.0.md); learning-only restrictions below describe earlier releases.

# Version 2.2.0 — October 7, 2026

The personal-agent and Muse feedback improves the research process. This revision
adopts the useful methods while treating their named stocks, quotes, multiples,
event dates and performance assertions as unverified source material. No stock
recommendation from that exchange was copied into the skill.

## Research changes

- S&P 500 is a configurable starting universe. The user can choose another index,
  market, industry or watchlist. Freeze a dated security list; do not hard-code a
  constituent count. Research membership is separate from execution authorization.
- There is no top-N or fixed shortlist count. Report evidence-supported candidates,
  including none, with actual coverage and exclusions. A partial data pull cannot
  be presented as a completed universe-wide analysis.
- Long-term flow: suitable peer valuation, earnings/cash-flow normalization,
  balance-sheet/value-trap checks, analyst dispersion and revisions, event review,
  GARCH risk overlay, classification/ranking, then portfolio sizing/proposal.
- Sector medians are context, not universal comparables. Add bank, REIT, commodity
  and loss-making growth treatment. Synergies need a cash/tax/timing bridge and
  downside cases; low implied forward EPS multiples alone do not validate them.
- Analyst target distributions require dated comparable observations; target,
  rating and earnings-estimate revisions remain separate. Missing data stay visible.
- Insider context uses transaction type, plans and the insider's holdings/history;
  sale value divided by company market cap cannot establish irrelevance. Beta cannot
  substitute for commodity or business-risk analysis.
- Candidate statuses preserve fundamental and event conclusions separately. An
  event flag cannot obscure a rejected thesis. The screen_review helper enforces
  coverage/status reporting on supplied evidence; it does not perform financial
  modeling or automatically retrieve all constituents.

## Day trading remains a separate workflow

Intraday discovery uses its own configurable liquid watchlist, session/catalyst
checks, registered completed-bar setup, stop/target/time exit, net costs, fresh
quotes and risk gates. It does not require long-term undervaluation or a fixed
number of daily picks. The existing breakout replay remains an unvalidated example.

Daily GARCH supplies background risk context. An intraday model requires separate
data/seasonality/horizon validation. Neither a NORMAL label nor positive synthetic
results promotes a setup. Small-account sizing may return no affordable trade.

## Executable changes and review fixes

| Issue | Change |
|---|---|
| Corporate actions trusted only in prose | Hash-bound price audit; unresolved action or unreviewed >=25% move blocks fitting; genuine moves require evidence and remain in returns |
| Unaudited or fictional GARCH could be labeled usable for sizing | eligible_as_sizing_input now requires a complete market-data declaration plus the holdout check; fictional/unaudited data remain false |
| Different agents could use materially different GARCH specifications | Output includes code/input/audit hashes, versions, windows/counts, return definition, optimizer and regime ratio |
| Stale intraday signal could fill after missing bars | Entry expires when the immediately following expected bar is missing |
| Switching live approval modes restarted daily counters | Approval and bounded modes share live daily counters in the same journal |
| Contradictory terminal update raised without durable blocking | Persist UNKNOWN and a conflict event before raising; blocks subsequent claims across restart |
| Equivalent decimal fill prices looked contradictory | Compare numerical values for terminal idempotence |
| Proposal could choose its own instrument cap | Require order asset_type to match broker-observed quote metadata |
| A registered setup could be assigned a different sleeve | Require explicit setup_sleeves mapping in policy |

The price audit validates caller declarations and diagnostic consistency, not the
truth of third-party data. It cannot detect every adjustment error. See
[garch-volatility.md](references/garch-volatility.md) for the reproducible baseline
and [REVIEW-2.2.md](REVIEW-2.2.md) for the complete review and remaining gaps.

## Compatibility and delivery

Use the entire ZIP. SKILL.md and VERSION must report 2.2.0. Earlier delivered ZIPs
are preserved. This package remains learning/paper: no installation, broker access,
live order, automation or credential change occurred.

Existing normalized inputs need setup_sleeves in policy and asset_type in quote
metadata. Existing ledger tables remain readable. A future changed personal policy
requires a new applicable authorization. Keep one live journal across live modes;
keep paper state separate. A GARCH run without a data audit may still compute for
research but cannot report eligible_as_sizing_input=true.

Sources and methodological qualifications are linked beside the relevant claims
in [screening-and-value-traps.md](references/screening-and-value-traps.md) and the
GARCH reference. They support the methodology, not the supplied stock selections.
