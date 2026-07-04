---
name: deal-watch-alerts
description: Build, run, or maintain configurable deal-watch automations for products, tickets, travel, or other purchasable items. Use when Codex or Claude Code needs to check current prices across retailer, marketplace, or deal-aggregator sites; verify selected variants and condition details; compare against price thresholds; suppress duplicate alerts with memory; and optionally notify by chat, email, SMS/email gateway, or another configured channel.
---

# Deal Watch Alerts

## Overview

Use this skill to turn a user-defined watch target into a repeatable deal check with strict verification before notification. The core job is to prevent false positives: only alert when the same currently selected, buyable offer satisfies every required attribute, condition rule, availability rule, and threshold.

## Quick Workflow

1. Parse or create the watch configuration.
   - Read `references/config-schema.md` when creating, updating, or normalizing configurable parameters.
   - Require item identity, required attributes, price threshold, sites, notification channels, and duplicate-memory location.
   - Treat thresholds as inclusive by default unless the user says "below" or provides a strict comparator.

2. Read duplicate memory before checking live sites.
   - Use `scripts/deal_memory.py` to compute stable keys, check duplicates, and record sent alerts.
   - Treat every prior `alerts_sent[].deal_key` as already notified.
   - If memory is inaccessible, fall back to in-thread or user-provided memory and report that limitation.

3. Check each configured source.
   - Read `references/verification-playbook.md` before doing live verification.
   - Prefer primary product pages over snippets, search pages, cached titles, or aggregator summaries.
   - For deal aggregators, open the linked merchant page and verify the final offer there.

4. Decide whether each candidate qualifies.
   - Verify all required fields on the same selected offer at the same time.
   - Reject hidden, ambiguous, stale, out-of-stock, contradictory, or unselected-variant evidence.
   - Compare the visible item price before tax. Include shipping separately if shown.

5. Notify only for new qualifying deals.
   - Read `references/notification-playbook.md` before sending email, SMS, webhook, or chat alerts.
   - Post the full buy link in chat whenever any external alert is sent.
   - Keep SMS gateway messages short and URL-free unless the user explicitly permits links.
   - After a successful external notification, append or update duplicate memory immediately.

6. Report the result.
   - If a new deal qualifies, start with `BUY SIGNAL` and include item, verified attributes, price, condition evidence, seller/store, direct buy link, notification status, and memory status.
   - If only duplicate deals qualify, say `Already alerted`, include current price/status and link, and say notification skipped as duplicate.
   - If none qualify, say no qualifying deal and include the best visible current price/status per target when available.

## Verification Standard

Before any `BUY SIGNAL` or external alert, explicitly verify:

- item identity: brand/product/model or equivalent user-defined identity
- selected variant attributes: size, color, capacity, RAM, storage, ticket section, dates, quantity, or other configured fields
- condition or grading policy, when condition matters
- selected seller/store
- selected item price and currency
- availability or add-to-cart/buy capability
- direct buy URL or stable product ID

Do not combine a price from one condition, seller, date, size, or variant with attributes from another. If changing any selector changes another required attribute, re-check the final selected offer.

## Duplicate Policy

A deal is duplicate when its stable key already exists in memory or the current thread. A material change can be treated as new only when the user-configured key changes meaningfully, such as:

- lower item price
- different seller
- different condition grade
- different store or product ID
- different qualifying variant
- materially better availability or included shipping, if configured as a key field

Never notify again just because an already-alerted deal remains in stock at the same price from the same seller and condition.

## Resource Guide

- `references/config-schema.md`: configurable watch fields, defaults, and examples.
- `references/verification-playbook.md`: live-site verification procedure and rejection rules.
- `references/notification-playbook.md`: safe chat, email, SMS gateway, and webhook notification rules.
- `scripts/deal_memory.py`: JSON memory helper for stable keys, duplicate checks, and sent-alert recording.

## Portable Use

For Codex, install this folder under a skills directory or reference it explicitly as `$deal-watch-alerts`. For Claude Code or another agent, include the folder in the workspace and instruct the agent to read `deal-watch-alerts/SKILL.md` before running the watch.
