# Intraday settled-cash review — 3.4.0

The previous entry gate required enough settled cash to pay for a buy, but kept
the ordinary cash floor against total ledger cash. Completed, unsettled sale
proceeds could therefore satisfy that floor while new day-trade buys consumed the
remaining usable cash. This release adds a separate configurable intraday reserve
against settled funds after all pending-buy reservations, including fees.

Choose a dollar minimum, an equity percentage, or both (the larger wins). The draft
uses zero dollars and 5%; older policies inherit their existing cash-floor fraction
when the new fraction is absent. Explicit zero/zero disables only the added reserve.
Configuration changes require the normal policy/session reauthorization for live
use. No account setting, capital allocation or live authorization was changed here.

The intended behavior is staggered use of usable cash. It is not a ban on selling
all positions, nor a forced X/Y stock rotation. Authorized exits remain available;
retaining stocks is not a substitute for settled cash. A blocked buy remains local,
with no broker-queued order to revive when funds settle. Cash-only rejection is
labeled WAIT_FOR_CASH_BUDGET; other failures still block for their own reasons.

Research checked Robinhood's cash-account T+1 rule, banking-holiday caveat and
Agentic limited-margin distinction. Actual broker settled cash remains the release
authority, not a local date calculation. The package keeps its settled-only funding
model. See [configuration, calculations and sources](references/settled-cash-planning.md).

Regression scenarios cover reserve breaches despite high ledger cash, exact cost
including fees, dollar/percentage settings, explicit disable, invalid inputs,
cancel-pending reservations across sleeves, successive round trips across symbols,
next-day non-release without broker confirmation, expired proposals, unaffected
core/swing behavior, necessary exits, and no journal claim when cash is blocked.
See [validation](VALIDATION-3.4.txt). The strategy replay now explicitly discloses
that it does not model broker settlement or this liquidity reserve; price replay
performance is not evidence of sustainable cash-account turnover.

This is an entry-time safeguard under reconciled inputs. It cannot guarantee
continuous liquidity against manual activity, another strategy, withdrawals or
account changes. It cannot instantly fix an already fully invested account. No
broker was connected or trade placed, and live integration remains untested.
