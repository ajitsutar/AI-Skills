---
name: concert-ticket-checkout
description: Assist with browser-based concert ticket searches, seat comparison, cart setup, checkout review, and user-supervised purchasing on Ticketmaster, AXS, Live Nation, venue sites, and similar ticketing platforms. Use when the user asks an agent to find or buy concert tickets, compare seats or prices, use their browser/login/passkey, monitor availability, prepare checkout, or help with a ticket purchase while preserving authentication, payment, CAPTCHA, queue, and final-purchase boundaries.
---

# Concert Ticket Checkout

## Core Rules

1. Use live browser or web sources because ticket inventory, prices, fees, and queues change constantly.
2. Never bypass queues, CAPTCHAs, rate limits, waiting rooms, transfer limits, region locks, or ticketing-site anti-bot controls.
3. Never access, store, export, request, or describe the user's passkey, password, OTP, CVV, wallet confirmation, payment secret, ID document, or security recovery flow.
4. Pause and hand control to the user for passkeys, login approvals, CAPTCHAs, payment entry, wallet prompts, identity checks, and any security-sensitive confirmation.
5. Do not click the final purchase, place-order, confirm-payment, or accept-nonrefundable button unless the user explicitly confirms the exact event, date, venue, section/row/seats or GA area, quantity, all-in price, merchant, and delivery restrictions in the current checkout.
6. If the user asks for a test run or says not to buy, stop before authentication or checkout submission and summarize what was found.
7. If no live web or browser capability is available, do not claim current inventory or pricing. Provide official source links or a manual search checklist and stop before cart or checkout work.

## Input Parameters

Accept structured or natural-language purchase parameters. Normalize them before searching:

```yaml
artist: required artist, band, event, or performer name
number_of_seats: required positive integer
price_max: required max all-in price per ticket unless the user explicitly says total budget
restrictions: "no obstructed or limited view" by default; "unrestricted" only when the user explicitly allows it
date_time: optional exact date, exact time, date range, or list of acceptable dates/times
location: optional city, venue, region, or distance radius
ticket_type: optional primary, verified resale, resale allowed, VIP allowed, or cheapest acceptable
```

If `artist`, `number_of_seats`, or `price_max` is missing, ask for the missing value before reserving seats. If `location` is missing and the artist has plausible events in more than one region, ask for a location before reserving seats. For search-only tasks, proceed with visible assumptions and mark the missing fields clearly.

Date handling:

- If the user provides one exact date or date/time, match that date first and only use another date after asking.
- If the user provides multiple dates, choose the earliest matching event by default unless the user ranks or excludes dates.
- If the user provides no date, choose the earliest upcoming matching event that satisfies the location and ticket constraints, and state that assumption before reserving seats.
- If multiple same-day events exist, prefer the earliest start time unless the user specifies a time.

Restrictions handling:

- Treat obstructed view, limited view, restricted view, side/rear view, single seats when adjacent seats are required, and ambiguous warnings as disqualifying unless the user set `restrictions: unrestricted`.
- Treat wheelchair-only, companion, or other accessibility-restricted inventory as disqualifying unless the user explicitly requested that accommodation and confirms eligibility. `restrictions: unrestricted` never overrides this accessibility check.
- If a site does not expose restriction details until checkout, re-check the final checkout details before asking for purchase approval.

## Workflow

1. Capture and normalize purchase parameters: artist, number of seats, price maximum, restrictions, date/time selection, location, ticket type, accessibility needs, preferred sites, resale tolerance, and whether logged-in browser state is required.
2. Search official and reputable sources first: artist site, venue site, Ticketmaster/Live Nation, AXS, primary box office, and only then resale markets if the user allows resale.
3. Exclude lookalike events that do not match the user's intent, such as tribute bands, fan parties, screenings, DJ nights, cover acts, unrelated artists, or wrong cities/dates.
4. Apply hard constraints before ranking: exact or defaulted date choice, adjacent seat quantity, price maximum, view restrictions, location, and accessibility requirements.
5. For viable listings, compare all-in cost when visible: ticket price, fees, taxes, delivery charges, parking or required add-ons, transfer limits, refundability, seat location, view restrictions, and timing risk.
6. Prefer official primary tickets over resale when comparable. Flag resale, speculative listings, obstructed/limited-view seats, will-call constraints, nontransferable tickets, and unusually high fees.
7. If a static web page omits inventory, prices, seat maps, queue state, or cart controls because JavaScript/cookies are required, switch to a real browser session when available instead of guessing.
8. When using the user's browser, keep them informed before actions that change account state: logging in, joining a queue, reserving seats, adding tickets to cart, accepting terms, or entering checkout.
9. At checkout review, present a concise confirmation block and wait for explicit user approval before any final purchase action.

## Confirmation Block

Use this format before any final purchase action:

```markdown
Purchase review:
- Artist/event:
- Date/time:
- Venue/city:
- Quantity:
- Seats/section:
- Ticket type: primary/resale/verified resale
- All-in price per ticket:
- All-in total:
- Price max and whether it is per-ticket or total:
- Restrictions checked:
- Accessibility eligibility checked:
- Merchant:
- Delivery/transfer restrictions:
- Refund/cancellation notes:

Waiting for explicit approval before final purchase.
```

## Availability Monitoring

- Start monitoring only when the user explicitly asks and a recurring monitor or scheduler is available. Otherwise perform one current check and explain that unattended monitoring is unavailable.
- Resolve the exact event, venue/city, acceptable dates, quantity, all-in price ceiling, ticket type, resale policy, view restrictions, check interval, deadline, and notification destination before starting.
- Prefer official ticket alerts. For repeated checks, use a conservative interval, obey site rate limits and terms, and stop when the site blocks automation or requests authentication or CAPTCHA.
- Never hold inventory, remain in a queue, keep an authenticated session active, add tickets to a cart, or attempt a purchase as part of unattended monitoring.
- Store only the search criteria, deadline, source URLs, and a minimal last-seen listing fingerprint for duplicate suppression. Never store credentials, cookies, payment data, or identity information.
- In every alert, include the checked time and timezone, source link, seat/section or GA area, quantity, visible all-in price or fee uncertainty, restrictions, and a reminder that the user must re-verify availability before checkout.

## Browser Handoffs

- Use authenticated browser state only when the host exposes it and its browser-isolation rules permit it. Use a dedicated automation window when required, and never navigate, close, or modify unrelated tabs or windows.
- Use a non-authenticated browser or web search for discovery when login is not needed.
- If a safe interactive browser is unavailable, limit the task to public discovery and give the user direct links for manual checkout.
- Tell the user exactly when to take over, for example: "Please complete the passkey prompt, then tell me when the page is back."
- After the user completes a handoff, re-check the visible page state before continuing.
- If a site detects automation, blocks interaction, or enters a waiting room, stop automation and explain the current state. Do not attempt evasive behavior.

## Output

For search or comparison tasks, provide:

```markdown
Checked: <date/time and timezone>
Request: <artist>, <number_of_seats> seats, <price_max>, <restrictions>, <date_time or default-date rule>

Best option: <event/source/link>, <all-in total if visible>, <why it fits>

| Option | Source | Date | Location | Seats | Total | Notes |
|---|---|---|---|---|---:|---|
| ... | ... | ... | ... | ... | ... | ... |

Next action: <what the user should do or approve>
```

If no suitable tickets are available, say so clearly and include the checked sources.
