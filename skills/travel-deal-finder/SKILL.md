---
name: travel-deal-finder
description: Find, compare, and summarize current travel deals across flights, hotels, vacation packages, and car rentals. Use when the user wants best-value travel options for a destination, dates, number of adults, children with ages, optional hotels, optional rental cars, flexible destinations or dates, package-versus-separate booking comparisons, or searches across Costco Travel, Expedia, Hotels.com, Priceline, airline/hotel/car direct sites, metasearch engines, and similar booking sources. This skill is research-only and stops before authentication, traveler or payment data entry, and booking submission.
---

# Travel Deal Finder

Package terms: [MIT license](LICENSE), [provenance](PROVENANCE.md) and
[third-party notices](THIRD-PARTY-NOTICES.md).

## Core Workflow

Resolve bundled resources relative to the directory containing this `SKILL.md`, never relative to the current working directory.

Keep this workflow research-only. Provide verified comparisons and booking links, but leave login, traveler details, loyalty-account access, payment, and booking submission to the user.

1. Gather the minimum trip shape before searching: origin when flights are needed, destination, exact or flexible dates, adults, children with ages, rooms/beds, hotel needs, car rental needs, budget, must-have constraints, loyalty memberships, and whether packages are acceptable.
2. Ask only for blocking missing inputs. Reuse facts from the conversation and distinguish hard constraints from preferences. Never invent child ages for a booking form; use age at travel and clarify infant seating when relevant. Resolve ambiguous years or past dates before exact searches. Hotels and cars are optional; do not add them automatically. For flexible trips, compare a small set of destination/date scenarios before refining.
   - When a rental car is requested without a class preference, default to a full-size sedan. Verify the supplier's class and body style; "or similar" does not guarantee a specific model. Do not substitute a compact, midsize, SUV, or unspecified body style without asking. Flag any passenger/luggage-capacity mismatch.
   - When a hotel is requested without a bed preference, default to a room with two queen-size beds. Verify the exact bookable room configuration and allowed occupancy for the assigned adults and child ages. "Two beds," double/full beds, twin beds, a sofa bed, or a bed request subject to availability do not confirm two queens. If the configuration is unavailable or insufficient for the party, ask before changing beds or room count.
   - Default to non-smoking hotel rooms at properties that are not adults-only, including package stays, unless the user explicitly overrides either preference. Verify the room's smoking designation and the property's child/minimum-age policy; an unknown policy is not a confirmed match. If children are traveling, their actual ages must satisfy admission rules even if an adults-only preference is requested. Ask before relaxing either default.
   - When flights are included and the user has not specified stops, default to nonstop in each direction, including flights inside packages. Do not ask about connections up front. Search and verify nonstop options first. Only if no qualifying nonstop itinerary is found, ask the user for their maximum connections per direction before searching connecting itineraries. Do not silently relax this default. A blocked or incomplete search is not evidence that nonstop flights are unavailable; report the access limitation instead. An explicit user stop limit overrides the default.
3. Browse live sources. Travel prices change constantly, so verify current pricing with web or browser tools and include source links and a checked timestamp in the answer. If no live capability is available, do not claim current prices; provide a manual search plan instead.
4. Never bypass CAPTCHAs, queues, rate limits, login gates, region restrictions, or anti-bot controls. If exact details require authentication or unsupported interactive controls, report the limitation and give the user the direct link.
   - Follow the host's current browser policy, assigned profiles, blocker registry, isolated fallback, and cleanup requirements. Where configured, use headless first and the maintained isolated normal-Chrome fallback on failure. Never touch pre-existing tabs, transfer authentication, or substitute another task's profile. Report concrete isolation failures. Keep the research-only boundary during fallback.
5. Choose sources dynamically. Read `references/source-strategy.md` for routing and `references/deal-websites.md` for researched official links, useful capabilities, and access limitations. Honor named sources first. Start with a broad comparator, a relevant independent booking source or specialist, and direct supplier verification of finalists. Expand when distinct inventory or promotions could change the answer; stop when further sources repeat offers. Report actual coverage, not an exhaustive-market claim. Independent component searches may be delegated when tool/browser ownership permits.
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

Prioritize [Costco Travel](https://www.costcotravel.com/) for vacation packages, hotel bundles, and rental cars. Check accessible public quotes before assuming login is required; membership eligibility and login requirements are different. Compare the same trip against separate components and another relevant provider. Show included perks and future credits separately from cash payable. If exact pricing is gated, keep it unranked and explain what the user must confirm.

## Live Offer Evidence

Treat snippets, AI suggestions, calendars, newsletters, destination pages, aggregator cards, and "from" prices as discovery evidence. Open the exact supplier or booking offer during this run and verify the dates, party, fare/room/car variant, seller, price basis, mandatory fees, availability or purchase path, and final URL. An HTTP 200 or empty app shell is insufficient. Recheck the winner immediately before recommending it.

Record `verification` (verified, discovery, blocked, stale), `verified_at` with timezone, final URL, trip/party details, total/currency, inclusions, cancellation terms, and unresolved fees. Use verified only after these checks. A search page is a labeled navigation link, not a direct listing. Exclude stale, blocked, teaser-only and unverified offers from current-price rankings. If none pass, say no current buyable offer was verified and provide useful navigation links and concrete blockers.

Verify departure and arrival dates separately, including overnight flights and local timezones. Recheck hotel nights and rental periods after package changes. Apply stops and elapsed-time limits each way, including connections. Flag self-transfers, airport changes, separate tickets, and unprotected connections. Compare packages against like-for-like separate components.

## Comparison Rules

- Compare totals for the exact traveler count, not per-person teaser prices, unless the site only exposes per-person pricing. Mark per-person pricing clearly.
- For flights, include airports, airline, dates, times, stops, total elapsed time, cabin/fare family, baggage basics, and booking source.
- For hotels, include property name, neighborhood, room type, total stay price, taxes/fees, resort/parking fees if visible, refundability, breakfast/parking inclusions, and review/location caveats.
- For packages, list included components, total package price, comparable separately booked total, and the savings or premium.
- For cars, include pickup/dropoff location, car class, supplier, total price, mileage, fuel policy, cancellation, and mandatory fees.
- Rank complete verified totals by actual cash price. Explain best value separately using the user's preferences, without arbitrary dollar penalties for restrictions or inconvenience. Keep incomplete totals and near misses unranked with reasons.
- Validate exact promotion eligibility and application. Do not subtract future credits, gift cards, points, or speculative cashback from cash due. Distinguish required extras, optional extras, and refundable deposits; do not count fees twice. Do not multiply an adult teaser fare by party size and call the result verified.
- For hotels, check occupancy per room and each child's age. For cars, verify local pickup/dropoff times, driver-age fees when applicable, one-way charges, child-seat costs if needed, and mileage. Mark next-day arrivals prominently.
- Never request, access, store, or enter passwords, passkeys, OTPs, CVVs, payment details, passport or ID numbers, or security-recovery information. Do not log in, create an account, place a hold, add an itinerary to a cart, accept nonrefundable terms, or submit a booking. If the user asks to book, provide the verified booking link and a concise checklist of the itinerary, total, fee uncertainty, and cancellation terms for the user to complete personally.

## Ranking Helper

Use `scripts/rank_offers.py` with Python 3.11 or later when several offers have been collected and a consistent sorted table would help. Pass a JSON array or an object with an `offers` array. The script is optional; it does not replace judgment or browsing.

Provide a nonnegative `total_price` or complete price components plus three-letter `currency`. Compare only identical trip specifications and one currency per invocation. Ranking requires `qualifies: true`, `verification: "verified"`, a nonempty `verified_at`, final `url`, known total, and no unresolved fees (`unknown_fees: false` or `0`). Unverified or incomplete offers remain unranked. The helper sorts supplied evidence; it does not browse, prove verification, or establish freshness. Supply current-run evidence only. Keep sensitive traveler and account data out of input files.

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
    "verification": "discovery",
    "verified_at": null,
    "cancellable": false,
    "unknown_fees": 0,
    "notes": "Fictional schema example; unranked until live verification"
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

Lowest verified among sources checked: <source/title/link>, <total for all travelers>, <why it wins>

| Rank | Deal | Total | Includes | Key tradeoffs |
|---|---:|---:|---|---|
| 1 | ... | ... | ... | ... |

Notes:
- <important assumptions, missing fees, login requirements, or timing caveats>
- <exact trip and party, sources checked and coverage limitations; best-value alternative if useful>
- <what to verify before booking>
- <direct source link for the user to complete any login or booking personally>
```
