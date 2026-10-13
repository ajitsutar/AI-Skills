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
4. Rank evidence quality and expected opportunity without inventing probabilities
   or guaranteed returns. Report what remains unverified. Optional GARCH or other
   risk diagnostics inform the explanation; missing calculations do not gate orders.
5. Allocate the requested budget using the user's actual instructions. If the user
   wants the whole amount invested, do not import a demo cash floor, 10% position
   cap or 5% tactical sleeve. Explain concentration and loss scenarios as advice.

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
