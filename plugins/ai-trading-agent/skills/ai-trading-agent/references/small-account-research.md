# Small-account stock research

Research a small budget using the same business and horizon evidence as a larger
account. Small dollars do not imply cheap nominal share prices, an S&P-only universe
or template position caps. Fractional shares and native dollar instructions can
make otherwise expensive shares accessible.

A request to find investments requests research. If the user has also instructed
execution, preserve that existing instruction through the common
[host handoff](execution-handoff.md), without local policies or repeated approval.

## Research and allocation

1. Use the requested horizon and universe. When unspecified, cover U.S.
   exchange-listed stocks including listed ADRs; disclose provisional horizon
   assumptions and actual screening coverage.
2. Review current business results, balance sheet, cash flow, valuation, dilution,
   guidance, catalysts and failure modes. Separate vendor discovery from primary
   evidence. Low P/E or share price alone does not establish undervaluation.
3. Fit the thesis to the requested holding period. Show same-horizon bear/base/bull
   assumptions, costs, event exposure and plausible losses beyond a planned stop.
   Address any supplied loss scenario and explain its effect on the stated goal
   and liquidity needs. A flexible exit does not remove the risk of a loss when
   the money is wanted. Distinguish a scenario from a forecast or loss limit;
   compute any numerical consequences with retained inputs and supported tools.
4. Rank evidence quality and expected opportunity without inventing probabilities
   or guaranteed returns. Report what remains unverified. Optional GARCH or other
   risk diagnostics inform the explanation; missing calculations do not gate orders.
5. Allocate the requested budget using the user's actual instructions. If the user
   wants the whole amount invested, do not import a demo cash floor, 10% position
   cap or 5% tactical sleeve. Explain concentration and loss scenarios as advice.
6. When comparing affordability, prefer `planning.source_budget_sizing` when the
   original full cost source fits its schema; otherwise explicitly map the source
   to `planning.budget_sizing`. Include supplied entry costs and declared
   whole/fractional increments. Each full-budget single-stock alternative is its
   own scenario. Use `planning.source_allocation_context` or an explicit mapping
   to `planning.allocation_context` for its known concentration, fund coverage
   and monetary-volume facts. Keep pre-cost target allocations distinct from
   cost-sized positions. For an implementable sizing scenario, bind exposure to
   that scenario's computed gross position notionals and state the denominator,
   uninvested cash and costs; do not present target-dollar exposure as the sized
   portfolio. Do not infer costs, broker increments or liquidity cutoffs. Keep an
   observed full spread separate from modeled one-way slippage; see
   [decision calculations](portfolio-decision-calculations.md).
7. Separate the initial budget from supplied recurring contributions. Discuss
   whether the quoted increments and per-order costs also support the recurring
   amount. State any omitted timing, price or return assumptions before projecting
   future balances. Compute per-contribution affordability at the same declared
   fixed prices and costs even when future timing/returns are unknown; this is a
   sensitivity per occurrence, not a future-value forecast. Report a concrete
   missing calculation input if even that bounded sensitivity cannot be computed.

Compare the same basis across alternatives. Holdings coverage or more disclosed
sector labels supports an evidence-coverage statement; it does not establish lower
portfolio risk or superior future returns. Tie any preferred approach to the
supplied objective, loss scenario and remaining evidence, with conditional
language where those inputs do not establish suitability.

Finish with a decision-context check: explain how the loss scenario changes the
goal, when retaining cash could fit that goal, and how each compared sized
portfolio reconciles gross holdings, fees and residual cash. Report both target
and sized exposures when both are used. Count distinct underlying issuers and
their weights before describing one alternative as broader than another; no
diversification ranking follows from labels or disclosure coverage alone. Do not
drop this reasoning because the numerical workflow replay passed.

Use the computed `issuer_identity_summary` for issuer-count statements. A known
issuer count is a lower bound when identity or look-through coverage is missing;
cash is not another issuer and separate share classes are not separate issuers.
Check every count used in the conclusion against the retained result. Neither
that count nor shared business descriptions establish measured correlation or a
lower-risk portfolio; retain those distinctions in the final recommendation.

Bind both comparison operands to their own retained result and metadata. Declared
assumptions may support conditional arithmetic but cannot be reported as verified
source facts. Do not attach one portfolio's date or scope to another to make a
comparison pass. A pre-cost basket allocation does not establish its entry debit;
size the combined basket with its own orders before comparing its costs.

Use the shared analytical fractional-increment sensitivity in
[fractional shares](fractional-shares.md) when the source leaves it unspecified,
while preserving unknown actual broker precision. Do not choose a different
discretionary increment for an otherwise identical affordability comparison.

A dated close-price source field maps to `last` under the analytical sizing
convention; preserve its field pointer and date and do not imply a current fill
price. Generic prices without trade/bid/ask semantics remain unresolved. Once a
basket is sized, refresh its exposure with those final gross notionals. The
earlier pre-cost allocation remains a target scenario and cannot substitute for
the sized basket in a portfolio comparison.

See [fractional-shares.md](fractional-shares.md) for Decimal sizing and recurring
contributions. A native dollar-market instruction need not guarantee an exact
final debit when the broker converts dollars to shares using a recent price.
Neither quote age nor execution-price drift creates a skill pause or reapproval.
Actual order availability and account rules belong to the host and broker.

## Fictional calculation

```text
python scripts/portfolio_manager.py examples/small-account.json
```

This fixture demonstrates configured allocation targets and rounding. Its limits,
fee assumptions and cash reserve are inputs to that example, not required settings
for the user's account. Planning output is neither a broker receipt nor an order.

## Example request

> Research a $500 stock allocation for a one-month hold using the full U.S.-listed
> universe. Compare current catalysts, valuation, downside and event risk. Allocate
> the full budget across the strongest supported ideas; show market-price and fee
> uncertainty. Keep research confidence separate from the requested broker handoff.
