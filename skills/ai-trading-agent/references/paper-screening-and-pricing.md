# Replaying a paper screen and its daily marks

Freeze the eligible universe, exchange sessions, observation cutoff, source IDs, currency, 
price basis and thresholds before selection. Run the same rules at a rebalance. Keep 
original observations and later revisions as separate captures. A carried value is a 
bookkeeping mark. Exclude it from returns used to rank volatility, from execution prices 
and from limit or stop triggers. Reconcile dividends and splits consistently with the 
chosen price basis.

## One portfolio mark

Run `python scripts/paper_pricing.py mark mark.json`. The top-level fields below
identify a single series. Each bar repeats the same symbol, provider, currency and
basis. Supply the close for the completed exchange session, its actual observation
timestamp and its retained source identifier. The default session timezone is
America/New_York, with a default 16:00 regular close. Supply the applicable
`session_close_at` timestamp for an early close, or both `session_timezone` and
`session_close_at` for another exchange. Apply the same session conventions to
every member and the panel. Review the stock's status after the session closes.
Use the optional `session_closes` map from ISO session date to offset-aware
closing timestamp for previous sessions with a different close, or for all
previous sessions on another exchange. Historical bars also require post-close captures.

```json
{
  "symbol":"EXAMPLE","provider":"feed-A","currency":"USD","basis":"adjusted_close",
  "session":"2026-04-02","as_of":"2026-04-02T21:00:00Z",
  "bars":[{"symbol":"EXAMPLE","provider":"feed-A","currency":"USD","basis":"adjusted_close",
           "session":"2026-04-01","close":25,"observed_at":"2026-04-01T20:15:00Z","source_id":"bars-1"}],
  "status_check":{"symbol":"EXAMPLE","session":"2026-04-02","observed_at":"2026-04-02T20:30:00Z",
                  "source_id":"exchange-status-review","status":"NO_HALT_OR_DELISTING_OBSERVED"}
}
```

The helper uses the latest eligible capture for each session, keeps before/after 
values for changed closes, and returns the prior bar date and status evidence with
each carry. A missing bar alone cannot establish a halt or ordinary thin trading.
An unresolved halt/delisting review leaves the mark unresolved. Save the original
output with its cutoff and produce a separate rerun to show a later revision.

## One common selection anchor

Use `python scripts/research_preflight.py --anchor-check panel.json` before ranking.
Supply `requested_session`, the ordered `completed_sessions` from the adopted exchange
calendar (requested session first), `universe`, `series` (one mark-format input for
each symbol, including missing ones), and the common `as_of`, `provider`, `currency`
and `basis`. Use captures available by the actual decision clock. The check returns
missing symbols at every attempted date. It blocks an incomplete anchor by default.
When the mandate permits a prior completed close and the requested date is missing
for **every** member, set `allow_previous_complete: true`. The recorded actual
anchor must cover the entire supplied universe. For an almost-empty feed, the mandate may also freeze
`fallback_max_coverage_fraction` before seeing the data (for example 0.01 permits
fallback with at most 1% coverage). Keep both attempted counts. Every eligible name
still needs a close on the chosen date; never move one name back in isolation. Rebase the
benchmark to the same actual anchor and disclose the date of the universe itself.
A later constituent list or source vintage can still introduce look-ahead.

## Task-specific inputs

For an explicitly requested GARCH fit or GARCH-based sizing run
`python scripts/research_preflight.py --require-garch`. A nonzero exit means the
requested operation is unavailable. In a host that permits dependency installation,
use the release's pinned environment; otherwise report the missing capability.
Continue other independent operations. An observed variance or tail estimate must
retain its own method name. See [GARCH](garch-volatility.md).

Use [earnings and event evidence](evidence-semantics.md) and [screening risks](screening-and-value-traps.md)
before ranking a low-risk portfolio. An adopted event exclusion or risk screen
governs eligibility within that study. The host and its task policy govern broker actions.
