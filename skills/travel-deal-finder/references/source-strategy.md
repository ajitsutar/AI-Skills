# Source Strategy

Use this reference to decide where to search. Do not mechanically visit every site. Pick sources that match the trip shape, destination, and user's priorities.

## Inputs To Resolve

- Flights: origin airports, destination airports or city, dates, traveler ages, cabin, max stops, max elapsed time, baggage needs, preferred or banned airlines, flexible airports.
- Hotels: destination area, dates, rooms, adults and child ages, bed needs, quality level, budget, cancellation, breakfast, parking, resort fees, accessibility, proximity constraints.
- Cars: pickup and return locations, dates/times, driver age, car class, mileage needs, cancellation, insurance preferences, airport versus neighborhood pickup.
- Packages: whether bundle savings matter more than flexibility, whether Costco membership exists, whether transfers, activities, or breakfast matter.

## Good Source Mixes

Flight-only:
- Default to nonstop each way unless the user specifies otherwise. Only after a completed search finds no qualifying nonstop itinerary, ask for the maximum connections per direction before expanding. Apply the same default to package flights; access failures do not establish that no nonstop flights exist.
- Start with Google Flights, Kayak, Expedia, Priceline, or Skyscanner-style metasearch.
- Check airline direct for finalists, especially Southwest, low-cost carriers, and routes where OTAs omit fare details.
- Use airline direct pages when baggage, seat selection, family seating, or schedule reliability matters.

Hotel-only:
- Default to non-smoking rooms and properties that are not adults-only, including package stays, unless explicitly overridden. Verify room smoking status and property age/admission policy; unknown policies remain unconfirmed, and the party's actual ages must always be eligible.
- Default to an explicitly bookable two-queen-bed room unless the user specifies otherwise; verify occupancy and do not silently substitute another bed configuration or room count.
- Compare Hotels.com, Expedia, Priceline, Booking-style sources, and hotel direct pages.
- Check direct hotel rates for member rates, fees, cancellation, breakfast, parking, and room type confirmation.
- Use map/review sources when location quality could outweigh a small price difference.

Packages:
- Compare Costco Travel, Expedia packages, Priceline packages, airline vacation packages, and separate component totals.
- Costco Travel is most useful for hotel-plus-car, flight-hotel-car packages, resort packages, cruises, and destinations where member perks matter.
- If Costco final price is behind membership login, report that limitation and compare visible package structure against public alternatives.

Cars:
- Default to a full-size sedan unless the user specifies otherwise; verify class, body style, passenger/luggage capacity and ask before substituting.
- Compare Costco Travel, Expedia/Priceline/Kayak-style car search, AutoSlash-style search when accessible, and direct rental-company rates.
- Airport pickup can be convenient but may have higher taxes. Include neighborhood pickup if the user values price over convenience.

Flexible trips:
- Start broad with explore/flexible-date sources, then verify finalists with direct booking pages.
- For family trips, prioritize sane times, fewer changes, and room/bed certainty over tiny savings.

## Ranking Heuristics

Hard-filter first:
- Correct dates and destination.
- Correct adults and child ages.
- Required rooms, car class, or flight constraints.
- User-specified budget, cancellation, stop, or duration limits.

Rank only qualifying, complete, live-verified totals by actual cash price. Keep unknown fees, incomplete totals, stale evidence, and discovery-only offers unranked with reasons.

Recommend best value separately using the user's preferences: cancellation, timing, location, direct-booking support, and family suitability (arrival times, connections, bed configuration, and resort logistics). Explain tradeoffs without adding invented monetary penalties to the price.

## Verification Habits

- Prefer current pages over search snippets.
- Capture source URLs for every finalist.
- Treat "from" prices and member-only teasers as unverified until the exact dates and party size are loaded.
- Verify outbound departure and destination-arrival dates, hotel check-in/check-out dates and the computed night count, and return departure and home-arrival dates separately in the selected package details. Search dates may differ from hotel dates, and sites may automatically adjust flights or hotel nights. Revalidate travel-window and stay-length constraints after selection changes.
- Compare offers in one currency. Preserve original prices when converting with a current cited exchange rate, or group currencies separately.
- Keep offers with missing or teaser-only totals unranked; never treat missing values as zero.
- Re-check the final winner on the booking source immediately before recommending it.
- State assumptions clearly when a site does not expose child-age pricing, taxes, fees, or membership-only totals.
- Stop at research and source links. Do not authenticate, enter traveler or payment data, accept terms, or submit a booking.
- Do not bypass CAPTCHAs, queues, rate limits, login gates, region restrictions, or anti-bot controls.

## Package Provider Discovery and Brand Validity

For package searches, select providers by the actual route, destination, resort inventory, and membership benefits. Add a relevant airline vacation service or resort-package specialist to the existing Costco/OTA/direct comparison when it can quote the same trip. These are examples, not a mandatory provider checklist:

- Airline packages: United Vacations (`vacations.united.com`), American Airlines Vacations (`aavacations.com`), Getaways by Southwest (`southwest.com/vacations`), or Alaska Airlines Vacations (`vacations.alaskaair.com`) when the itinerary fits.
- Beach and all-inclusive specialists: CheapCaribbean (`cheapcaribbean.com`) or Apple Vacations (`applevacations.com`) where the destination and chosen resorts are offered.

Before using a remembered provider, confirm its current brand, official booking entry point, destination coverage, and booking horizon from its official site. Follow verified redirects and use the resulting official URL; do not treat legacy brands as additional independent comparisons. For example, Southwest's current package service is Getaways by Southwest, and the legacy Southwest Vacations homepage redirects there. Recheck this relationship when used rather than relying on the example indefinitely.

Read promotion terms for booking/travel dates, holiday blackouts, minimum spend/stay, eligible room or fare types, and child-pricing limits. Count a discount only when it applies to the exact party and itinerary. Destination pages establish provider relevance, not live inventory or a buyable price. Keep current promo codes, prices, and traveler-specific details in the trip research, not this reusable reference.
