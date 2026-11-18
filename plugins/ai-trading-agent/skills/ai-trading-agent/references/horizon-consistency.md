# Comparing clocks for one research request

Use `research.audit_horizon_consistency` when a research route and another
clock, screen or handoff are used for the same request. It recomputes the supplied
helper inputs and compares as-of, entry, comparison and hard-exit clocks, including
their precision. It does not interpret the original prose or authenticate the
caller-selected request identity.

The workflow argument is `{"document": ...}`. The document contains:

- `request_id`: one explicit identifier for this research request.
- `route`: `{request_id, document}` containing the original `research.route_horizon`
  input, not a rewritten copy of its result.
- `contexts`: records with distinct `id`, the same `request_id`, `kind` and original
  input `document`.

Supported context kinds are `route_request`, `clock_request` (a
`horizon_review.resolve_horizon` specification), `screen_request` (a screen
document) and `handoff_contract` (a locked `research_handoff` contract whose hash
is checked). For a legacy clock or screen, also declare `clock_role` as
`comparison_only` or `hard_exit`. The legacy `exit_at` name alone does not prove a
forced-sale mandate. Preserve the actual inputs through workflow source bindings;
the audit retains their hashes and recomputed clocks.

`CONSISTENT` means only that these explicitly related clocks agree. `CONFLICT`
retains differences or contradictory exit intent. `UNRESOLVED` means a context is
invalid or lacks an exact clock. A bare long-term screen cannot supply an exact
comparison check, and an empty audit cannot pass. A date and timestamp do not
become equal by inventing a time. Equivalent timezone representations of the same
instant do match.

For example, a flexible review ending on a Sunday must retain that date. A
separately supplied hard-exit clock that resolves to the preceding session is a
different clock; declaring it `comparison_only` avoids inventing a forced-sale
instruction but does not eliminate the date/precision discrepancy. Conversely,
an explicit fixed deadline continues to use the normal exchange-calendar,
buffer, chronology and evidence checks; this audit never weakens those checks.

See [the synthetic input](../examples/fictional-horizon-consistency.json).
It contains two separately valid but inconsistent clocks and should report a
conflict. It contains no market recommendation or execution authority.

This check does not replace primary review, scenarios, cash applicability,
event coverage, screening, covenant definitions or final narrative review. It
cannot prove that an omitted context was checked or that declared intent matches
the user. Do not cite a consistency result as overall research correctness.
