# Options activity and dated squeeze operands

For an ordinary request such as “Is the options activity unusual, and does the
short positioning support a squeeze?”, the assistant operates the tools. Inventory
the actual available sources and cutoff, retain the original exports, map their
columns internally, run the helpers, and explain the results and gaps. The user
need not write JSON, arrange a data subscription or operate a backend.

Use relevant free sources and already supplied permitted exports first. Every paid
subscription is optional. Check the chosen host's actual data access and the source's
permitted use before acquisition. This implementation analyzes retained files; it
does not provide a new live feed, reconstruct an OPRA tape, authenticate a supplier,
scrape restricted tables, enroll a user or require credentials. When no permitted
print source is available, deliver chain observations separately and say actual
prints are unavailable. A displayed delayed chain is not a substitute for prints.

## Assistant-operated sequence

1. Retain the exact question, source bytes, final source URL, retrieval time, stated
   delay/coverage/permission and the requested cutoff. Distinguish source observation,
   market event, public availability and retrieval. Do not backdate a snapshot.
2. Use `market.options_parse` (`options_activity.parse`) for an explicit mapped
   CSV, or bind supplied common envelopes directly. The parser is vendor-neutral:
   `adapter` is `options_chain_csv`, `options_prints_csv` or `float_shares_csv`;
   `columns` maps each internal field below to the exact retained CSV heading.
   It accepts `schema_version:1`, exact timezone-bearing `as_of`, `text`, `source`,
   optional `available_at`, `id_prefix`, and delimiter (default comma). Without
   explicit availability it uses precise source retrieval as first observed
   availability. Source metadata uses the [common envelope](market-sources.md).
   Extra raw columns remain in `payload.raw_fields`; mapped empty cells remain null.
   Missing/duplicate headers fail, and ragged rows remain ineligible parse errors.
3. Run `market.options_activity` (`options_activity.analyze`) on the full common
   evidence document, including every supplied revision and explicit cutoff.
   Preserve its issues and excluded records. Keep feed observations separate.
4. For float evidence, parse an explicitly reported **float share count**, then
   use `market.bind_float` (`options_activity.bind_float`) with `float_links`.
   It delegates all percentages and squeeze diagnostics to existing
   [positioning and squeeze](market-flow.md); it adds no second calculator.
5. Deliver actual premium separately from quote references, dated volume separately
   from OI, and source-backed positioning separately from squeeze hypotheses.
   No default “unusual” threshold or historical baseline is manufactured. Without
   compatible historical evidence, whether the activity is statistically unusual
   remains unestablished. A reported volume/OI ratio is a dated descriptive quotient.

## Internal contracts and retained meanings

Both option kinds require `ticker` in the envelope and these explicit payload
fields: `feed_id`, `contract_id`, `underlying_id`, `expiry` (ISO day), positive
`strike`, `right` (`call`/`put`), positive premium `multiplier`, uppercase
three-letter `currency`, `premium_unit:currency_per_multiplier_unit`, and
`deliverable` (the source-described deliverable, including adjustments or cash
settlement). Do not guess missing multipliers or turn adjusted deliverables into
standard 100-share contracts. A contract ID with conflicting supplied terms within
the same ticker/feed is unusable. Symbols alone do not establish issuer identity.

| Kind | Additional fields | Result meaning |
|---|---|---|
| `option_print` | `print_id`, exact `event_at`, positive integer `contracts`, `quantity_unit:contracts`, nonnegative `price`, `price_basis:actual_print` | `actual_print_premium = price × contracts × multiplier`, in the reported currency, before fees. This is neither underlying notional nor delta exposure or actual investor risk. |
| `option_chain` | exact `observed_at`; optional integer `volume_contracts` with `volume_date`; optional integer `open_interest_contracts` with `open_interest_date` | Separate reported activity and position snapshots. Missing/invalid/future dates retain supplied counts but prevent the volume/OI quotient. Zero OI has no finite quotient. |
| either | optional `bid`, `ask`, exact `quote_at` as a complete quote trio | Bid/ask/midpoint references and quote age. Zero bid is allowed. Crossed/future quotes are unusable while an independently identified print may remain usable. |

`last_price` on a chain stays a retained source field; it never becomes an
identified print or actual traded premium. The helper never multiplies midpoint,
last price, daily volume or OI into alleged actual traded premium. It does not
pool feeds or cumulative snapshots. `settings.max_quote_age_seconds` optionally
applies a caller-declared quote-age limit; older print-location classifications
become unknown. An at-ask print still has unknown aggressor and opening/closing
intent. A quote's timestamp and age are visible even without a declared limit.

Common `replace`/`cancel` envelopes and `supersedes` retain original vintages.
Revision identity must preserve the contract terms, feed and print ID (or chain
snapshot clock). A corrected payload status requires a replace envelope;
cancellation is never an active print. Future revisions do not alter an earlier
cutoff. Forked eligible revision graphs remain unresolved rather than adding
incompatible leaves. Duplicate feed identities count once only if their payloads
agree; conflicts require an explicit revision. All original evidence remains in
the output, and inputs are never mutated.

The float CSV maps `ticker`, `issuer_id`, `share_class`, positive `float_shares`,
`effective_date`, `share_basis:float`, `quantity_unit:shares`, `measure_basis`, and
the source's `adjustment_basis` when known. Unknown adjustment basis stays unknown.
`float_links` is an assistant-prepared list of exact
`{short_interest_record_id,float_record_id}` pairs. Do not overwrite a conflicting
existing link. The existing positioning engine validates usable availability,
same issuer/class, float date at or before short-interest measurement, and matching
known adjustment bases. Later floats are not backfilled. Outstanding shares and
currency-valued public float are not valid substitutes. Missing comparisons stay
unknown and cannot satisfy declared squeeze criteria.

## Primary semantic and access references

These primary references explain meaning and access limits. Check current terms
for the selected source before acquisition:

- [OCC/OIC general information](https://www.optionseducation.org/referencelibrary/faq/general-information): OI is a series-level outstanding contract count, and clearing is needed to establish opening/closing effects. Volume or OI alone does not reveal bullishness or intent.
- [OCC/OIC options overview](https://www.optionseducation.org/getattachment/8d382efb-64ba-431f-9b87-b7fc9b0916bf/OIC-Options-Overview-For-Investors-v10-final.pdf?lang=en-US): option premium uses the applicable multiplier; adjusted terms and index settlement differ from standard equity deliverables.
- [Cboe delayed quotes](https://www.cboe.com/delayed_quotes/all): the site's displayed notice prohibits automated extraction of delayed quote tables. This is a navigation/reference source, not an implemented scrape or free API.
- [Cboe market-data policies](https://cdn.cboe.com/resources/membership/Market_Data_Policies.pdf): delays and data-use/distribution rules are product-specific. Visibility does not establish permission to collect or redistribute a dataset.
- [SEC smaller reporting companies](https://www.sec.gov/resources-small-businesses/going-public/smaller-reporting-companies): SEC regulatory public float is a market-value measure. Do not reinterpret it as a float-share count.

These operations are research only. They infer no dealer position, dealer gamma,
gamma squeeze, causal covering, probability, order permission or broker action.
