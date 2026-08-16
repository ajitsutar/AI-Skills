---
name: travel-deal-finder
description: Find, compare, and summarize current travel deals across flights, hotels, vacation packages, and car rentals. Use when the user wants best-value travel options for a destination, dates, number of adults, children with ages, optional hotels, optional rental cars, flexible destinations or dates, package-versus-separate booking comparisons, or searches across Costco Travel, Expedia, Hotels.com, Priceline, airline/hotel/car direct sites, metasearch engines, and similar booking sources. This skill is research-only and stops before authentication, traveler or payment data entry, and booking submission.
---

# Travel Deal Finder

## Core Workflow

Resolve bundled resources relative to the directory containing this `SKILL.md`, never relative to the current working directory.

Keep this workflow research-only. Provide verified comparisons and booking links, but leave login, traveler details, loyalty-account access, payment, and booking submission to the user.

1. Gather the minimum trip shape before searching: origin when flights are needed, destination, exact or flexible dates, adults, children with ages, rooms/beds, hotel needs, car rental needs, budget, must-have constraints, loyalty memberships, and whether packages are acceptable.
2. Ask only for blocking missing inputs. If a reasonable assumption is safe, proceed and state it, such as using the user's locale/currency or treating kids as seat-holding children rather than lap infants.
3. Browse live sources. Travel prices change constantly, so verify current pricing with web or browser tools and include source links and a checked timestamp in the answer. If no live capability is available, do not claim current prices; provide a manual search plan instead.
4. Never bypass CAPTCHAs, queues, rate limits, login gates, region restrictions, or anti-bot controls. If exact details require authentication or unsupported interactive controls, report the limitation and give the user the direct link.
   - For browser automation, launch a dedicated new window at the start, keep every automation-created tab in it, and never navigate, focus, or close the user's pre-existing windows or tabs. If the host cannot create and reliably identify an isolated window, stop before interacting with the browser.
5. Choose sources dynamically instead of using a fixed list. Read `references/source-strategy.md` when planning nontrivial searches, packages, international trips, hotel/car bundles, or when the user names specific sites.
6. Normalize every candidate to total trip cost, including taxes, resort fees, baggage/seat fees when visible, hotel mandatory fees, car taxes and surcharges, and package inclusions. Keep unknown fees visible rather than hiding them.
7. Compare monetary totals only in one currency. If sources use different currencies, either convert them to one comparison currency using a current cited rate while preserving original amounts, or group them by currency instead of producing one ranking.
8. Apply hard constraints first, then rank value. Exclude or label offers that miss required dates, traveler counts, stop/duration limits, room count, cancellation rules, pickup location, or other user constraints. Keep offers with unknown or teaser-only totals unranked below verified totals; never treat a missing price as zero.
9. Summarize the best deal, strong alternatives, and tradeoffs. Prefer a compact table plus a short recommendation.

## Source Selection

Use the user's intent to decide which sites to search:

- Flight-only: include a flight metasearch or OTA, likely airline direct sites, and Southwest direct when US domestic routes could include Southwest.
- Hotel-only: include Hotels.com or Expedia, Priceline or another opaque/discount source when acceptable, hotel direct pages for finalists, and map/review checks when location matters.
- Flight plus hotel package: compare Costco Travel, Expedia packages, Priceline packages, airline vacation packages when relevant, and separate flight plus hotel totals.
- Hotel plus car or full vacation package: include Costco Travel when the user has or may have Costco access, plus at least one OTA package source and direct component pricing.
- Car-only: compare Costco Travel, Expedia/Priceline/Kayak-style car searches, and direct rental-company rates for the best locations and cancellation terms.
- Flexible destination/date requests: start broad with metasearch/explore tools, then verify finalists directly.

Costco Travel often requires membership, login, or opaque final pricing. Use it when packages, hotels, cruises, rental cars, or Costco membership are relevant. If exact pricing is gated, report the visible offer and explain what must be confirmed after login.

## Comparison Rules

- Compare totals for the exact traveler count, not per-person teaser prices, unless the site only exposes per-person pricing. Mark per-person pricing clearly.
- For flights, include airports, airline, dates, times, stops, total elapsed time, cabin/fare family, baggage basics, and booking source.
- For hotels, include property name, neighborhood, room type, total stay price, taxes/fees, resort/parking fees if visible, refundability, breakfast/parking inclusions, and review/location caveats.
- For packages, list included components, total package price, comparable separately booked total, and the savings or premium.
- For cars, include pickup/dropoff location, car class, supplier, total price, mileage, fuel policy, cancellation, and mandatory fees.
- Treat unknown fees, nonrefundable terms, inconvenient airports, long layovers, poor reviews, and split-ticket risk as value penalties even when the cash price is low.
- Never request, access, store, or enter passwords, passkeys, OTPs, CVVs, payment details, passport or ID numbers, or security-recovery information. Do not log in, create an account, place a hold, add an itinerary to a cart, accept nonrefundable terms, or submit a booking. If the user asks to book, provide the verified booking link and a concise checklist of the itinerary, total, fee uncertainty, and cancellation terms for the user to complete personally.

## Ranking Helper

Use `scripts/rank_offers.py` with Python 3.11 or later when several offers have been collected and a consistent sorted table would help. Pass a JSON array or an object with an `offers` array. The script is optional; it does not replace judgment or browsing.

For each offer with a known price, provide a nonnegative `total_price` or at least one price component plus a three-letter `currency`. All priced offers in one invocation must use the same currency. Use `unknown_fees: true` when the amount is unknown, or a nonnegative number when an estimated additional amount is known. The helper displays unknown prices and fees explicitly and ranks unknown-price offers after verified-price offers.

Minimal offer JSON:

```json
[
  {
    "source": "Kayak",
    "title": "SJC to BDL Southwest",
    "url": "https://example.com",
    "total_price": 487,
    "currency": "USD",
    "qualifies": true,
    "cancellable": false,
    "unknown_fees": 0,
    "notes": "1 stop each way; under 9h"
  }
]
```

Run:

```bash
python "<skill-dir>/scripts/rank_offers.py" offers.json
```

## Output Template

Use this structure unless the user asks for something else:

```markdown
Checked: <date/time and timezone>

Best deal: <source/title/link>, <total price>, <why it wins>

| Rank | Deal | Total | Includes | Key tradeoffs |
|---|---:|---:|---|---|
| 1 | ... | ... | ... | ... |

Notes:
- <important assumptions, missing fees, login requirements, or timing caveats>
- <what to verify before booking>
- <direct source link for the user to complete any login or booking personally>
```
