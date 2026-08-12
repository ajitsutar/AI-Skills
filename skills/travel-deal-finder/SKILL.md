---
name: travel-deal-finder
description: Find, compare, and summarize current travel deals across flights, hotels, vacation packages, and car rentals. Use when the user wants best-value travel options for a destination, dates, number of adults, children with ages, optional hotels, optional rental cars, flexible destinations or dates, package-versus-separate booking comparisons, or searches across Costco Travel, Expedia, Hotels.com, Priceline, airline/hotel/car direct sites, metasearch engines, and similar booking sources.
---

# Travel Deal Finder

## Core Workflow

Resolve bundled resources relative to this `SKILL.md`, never relative to the current working directory. In Claude Code, `${CLAUDE_SKILL_DIR}` is the skill directory. In other agents, resolve the equivalent directory from the loaded skill path.

1. Gather the minimum trip shape before searching: origin when flights are needed, destination, exact or flexible dates, adults, children with ages, rooms/beds, hotel needs, car rental needs, budget, must-have constraints, loyalty memberships, and whether packages are acceptable.
2. Ask only for blocking missing inputs. If a reasonable assumption is safe, proceed and state it, such as using the user's locale/currency or treating kids as seat-holding children rather than lap infants.
3. Browse live sources. Travel prices change constantly, so verify current pricing with web or browser tools and include source links and a checked timestamp in the answer.
4. Choose sources dynamically instead of using a fixed list. Read `references/source-strategy.md` when planning nontrivial searches, packages, international trips, hotel/car bundles, or when the user names specific sites.
5. Normalize every candidate to total trip cost, including taxes, resort fees, baggage/seat fees when visible, hotel mandatory fees, car taxes and surcharges, and package inclusions. Keep unknown fees visible rather than hiding them.
6. Apply hard constraints first, then rank value. Exclude or label offers that miss required dates, traveler counts, stop/duration limits, room count, cancellation rules, pickup location, or other user constraints.
7. Summarize the best deal, strong alternatives, and tradeoffs. Prefer a compact table plus a short recommendation.

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
- Do not book, log in with user credentials, enter payment details, or transmit personal information unless the user explicitly asks and confirms at the point of action.

## Ranking Helper

Use `scripts/rank_offers.py` when several offers have been collected and a consistent sorted table would help. Pass a JSON array or an object with an `offers` array. The script is optional; it does not replace judgment or browsing.

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
```
