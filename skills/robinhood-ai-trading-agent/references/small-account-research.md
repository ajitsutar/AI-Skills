# Example request: “I have $500; find undervalued stocks with high growth potential”

## What the skill can do

Research and compare public companies, produce a sourced shortlist, then calculate
an affordable allocation and reviewable order proposals. Personal live action additionally requires a verified official broker connection, configured policy, readiness checks and an approved exact order or bounded mandate. A request to find stocks alone authorizes research.

The initial sentence does not specify a horizon, loss tolerance, existing exposure,
cash needs or permission for a concrete trade. Continue useful research immediately;
do not treat those gaps as permission to invent a risk profile. If the user supplies
no horizon, state a provisional long-term research horizon (for example 3–5 years),
mark it as an assumption and keep the result as a research plan.

## Research procedure

1. Check whether $500 means new contribution or total portfolio. Existing holdings,
   if known and authorized, affect overlap and concentration. Do not require account
   authentication just to research public stocks.
2. Follow [screening-and-value-traps.md](screening-and-value-traps.md). Use the
   configured universe; S&P 500 is a replaceable starting point for broad U.S.
   discovery. Freeze a dated constituent list and report actual screening coverage,
   exclusions and missing data. Low share price alone is not undervaluation.
3. Gather latest filings and company results: revenue growth, gross/operating
   margins, cash generation, cash/debt, share-count change, stock compensation,
   customer concentration, guidance, catalysts and material risks. Keep reported
   results separate from estimates. Flag stale or missing evidence.
4. Evaluate valuation against comparable businesses and scenario ranges. Use
   earnings/free-cash-flow multiples when meaningful; EV/sales for loss-making
   businesses needs explicit margin/runway assumptions. Negative earnings do not
   create a useful low P/E or PEG score. A low multiple may reflect deterioration.
5. Compare growth quality with price paid, dilution, balance-sheet risk, execution
   risk and the bear case. Keep bull/base/bear assumptions visible. Do not claim a
   single precise intrinsic value or a guaranteed “most undervalued” winner.
6. Use Reddit/X to find disputed assumptions and questions; verify material claims
   with primary evidence. Never turn social enthusiasm into a buy signal.
7. Assess the built-in GARCH(1,1) risk overlay on the finalists as specified in
   SKILL.md. Use sufficient history for the training and holdout windows and report
   the actual run evidence or a specific skip reason. Keep volatility separate
   from valuation and growth; do not turn a low-volatility stock into a valuation
   winner or claim one year automatically meets the helper's 291-price default.
8. Classify first as Eligible, Watch, Speculative, Reject or Event-blocked; rank
   comparable eligible candidates with no fixed output count, including none.
   Keep fundamental and event statuses separate. Include current quote
   timestamp/source, valuation basis, growth evidence, downside, catalysts and
   suitability for the user's horizon. Flag missing live quotes.

## Turning a shortlist into an allocation

Rank research quality separately from portfolio sizing. Apply the current policy,
cash floor and symbol caps before rounding. Keep unused cash when an affordable
whole-share allocation does not fit. Do not buy a worse business just because its
nominal share price is lower, or relax diversification limits to spend all $500.

Fractional availability must be discovered from the broker. The present executable
gate supports whole shares only; it cannot submit a fractional order by changing a
quantity field. A fractional adapter would require separate validation. Fees/spreads
can be material for a small budget.

For a long-term stock purchase, use a thesis/downside review and target allocation;
do not impose an arbitrary intraday stop. Research Eligible does not mean authorized:
it can support a paper proposal, never imply an executed investment. A verified
no-trade conclusion is valid. Day trading uses the separate tactical workflow and
its sleeve cap; a $500 account may produce zero whole-share entries after sizing.

## Runnable fictional example

```powershell
python scripts/portfolio_manager.py examples/small-account.json
```

The fictional $500 account has a 10% target cap for each of two candidates, priced
at $45 and $70. It can propose one $45 share under these example caps; the $70 share
does not fit a $50 target. The remaining $455 is cash before fees. This teaches
affordability and policy constraints, not stock selection or a recommendation.

## More explicit prompt for a future research session

> Research a $500 long-term stock allocation over 3–5 years. Find U.S.-listed
> companies with credible growth and a defensible valuation case. Compare recent
> filings, cash flow, debt, dilution, valuation, catalysts and bear cases. Apply the
> skill's GARCH risk overlay to finalists where data are sufficient and report any
> skipped calculation. Give me
> a sourced shortlist and an allocation under my existing portfolio limits, with
> unused cash allowed. Start with research and reviewable proposals. Use live execution only within my separately approved policy and authorization.
