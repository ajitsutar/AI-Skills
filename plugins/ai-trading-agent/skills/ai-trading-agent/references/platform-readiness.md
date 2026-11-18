# Platform evidence for research, paper and live use

`scripts/platform_readiness.py` assesses the **completeness of a supplied evidence
catalog** for a named native host, exact package/runtime, asset class, operating
mode and bounded scope. It performs no network or broker operation and opens no
receipt references. It never authorizes, refuses, submits or cancels a trade.
Native host/broker permissions and existing user instructions remain authoritative.
Do not connect its output to a new skill-owned approval or dispatch gate.

The supported assessment classes are `stocks`, `etfs`, `options`, `futures`, `fx`,
`bonds` and `crypto`. Assessment support does not mean an instrument model, data
feed or broker operation is implemented for every class. A scope must describe
the actual products, strategy/order variants, venues, sessions and limitations;
do not replace this with an unsupported claim of all instruments or all trading.

## Status meanings

| `evidence_status` | Meaning |
|---|---|
| `UNVERIFIED` | Required evidence is missing, incomplete, stale, future-dated or bound to a different scope/host/deployment. This is not a broker rejection. |
| `UNSUPPORTED_IN_SUPPLIED_HOST_OBSERVATION` | A current hash-bound supplied observation records unsupported capability for this exact scope and mode, with all observation checks present. This is not a permanent platform-wide denial. |
| `CONFLICTING_EVIDENCE` | Current passing and failing receipts conflict, or current supported/unsupported host observations conflict. A favorable receipt does not erase a retained failure. |
| `EVIDENCE_QUALIFIED_CONDITIONAL` | Every required category has a current, correctly bound passing receipt and no retained failure conflict. **Only submitted catalog completeness is qualified.** |

`catalog_evidence_complete` is false for the first three states. It is not a
production-readiness certification. `readiness_claim` always remains
`NOT_ESTABLISHED_BY_THIS_ASSESSOR`; `execution_authorized`, `enforces_execution`,
`skill_submitted_order` and `external_permissions_changed` are always false.
There is no favorable numeric score or `production_ready: true` switch.

A malicious or mistaken author can invent plausible receipts and hashes. The
helper cannot authenticate evidence, establish actual test execution or judge
test sufficiency. Independent review of the referenced artifacts and actual host
operation remains necessary before making a whole-system readiness claim.

## Input contract

All described objects have exact fields. Unknown fields, duplicate IDs, malformed
hashes and unknown check names/outcomes are rejected. Timestamps must be explicit
timezone-aware ISO instants with seconds. The CLI also rejects duplicate JSON
object keys and nonfinite JSON constants. No default freshness window is invented.

The document contains exactly:

- `schema_version: 1`, `as_of`.
- `host`: `id` (a nonprivate logical host label), `package_sha256`, `runtime_sha256`.
  Use null for unknown hashes; this prevents qualification. Use the exact deployed
  package and a retained runtime/environment manifest hash, not a version label.
- `requests`: nonempty array of `asset_class`, `mode` (`research`, `paper`, `live`),
  `scope_id` and `scope_description`. IDs are unique per asset/mode.
- `evidence`: array of `{id, receipt, receipt_sha256}`.
- `documentation`: contextual descriptions, separately specified below.

Each receipt contains `kind`, `host_id`, `asset_class`, `mode`, `scope_id`,
`scope_sha256`, `observed_at`, `valid_until`, `package_sha256`, `runtime_sha256`,
`capability_sha256`, `artifact_ref` and `checks`. The artifact reference is a
nonempty locator for a retained report; never put credentials or account routing
in this shareable packet. References are not fetched or checked for existence.

`scope_sha256` equals `digest(request)` for the complete request object. Changing
the economic scope description invalidates old receipts even if its ID is reused.
Receipt hashes use `digest(receipt)`: sorted-key compact JSON, Unicode preserved,
NaN disallowed, UTF-8, SHA256. `digest` is exported by the module. This binds the
structured report contents, not the external artifact's existence or authenticity.
Retain original reports and their content hashes within the referenced evidence.

Each check has exactly `id`, `outcome` (`pass`, `fail`, `not_run`) and
`evidence_ref`. A boolean alone cannot qualify a category. All required checks
must be present and pass in a single category receipt. Receipt fragments are not
silently stitched into a pass. Missing and `not_run` checks remain incomplete.
An eligible failing receipt remains visible even if another receipt passes.
Excluded receipts retain reasons; all considered receipt identities/hashes remain
in output. Exclusion does not delete original evidence.

Receipt eligibility is `observed_at <= as_of < valid_until`, plus matching host,
package, runtime and request scope. Validity periods are reviewer-supplied, not
independently justified by the helper. Reassessment after a deployment or schema
change requires appropriately rebound evidence. A result at an old `as_of` does
not establish current host status.

## Observed host and schema binding

A `host_capability` receipt additionally has `capability_status` (`supported`,
`unsupported`, `unknown`) and `tools`. All three host-observation checks below
are required even for a scoped unsupported observation. An absent tool inventory
or a generic documentation page cannot establish that a host is unsupported.

Each observed tool has `name`, `operations`, `input_schema`, `schema_sha256`.
The schema is a nonempty JSON object whose canonical hash must match. Retention
and hash checking do not fully validate JSON Schema semantics or prove live tool
discovery. Supply actual schema-contract evidence under the corresponding check.

For paper/live qualification, observed tools collectively cover `account`,
`quote`, `positions`, `orders`, `fills`, `submit` and `cancel`. Multiple logical
operations may map to one actual host tool, for example order history exposing
cumulative fills, if its observed schema/results support that mapping. This is
an assessment catalog, never a guessed tool invocation. More specific order,
exercise, delivery or settlement behavior belongs in the bounded scope and the
instrument/lifecycle evidence.

`host_capability.capability_sha256` is null to avoid a recursive binding. Every
other paper/live receipt binds `capability_sha256` to the **receipt hash** of a
current fully passing supported host observation with the required operations.
Changing that observation or its tool schema invalidates the operational
receipts until they are reviewed/rebound. Research receipts set this field to
null: offline research qualification does not imply any trading capability.
Evidence is never borrowed from paper to live or between asset classes.
All qualifying categories must share at least one common capability receipt;
individually passing categories tied to incompatible inventory snapshots cannot
be stitched together into a qualified catalog.

## Evidence catalog

`required_categories(mode)` and `required_checks(kind, asset_class)` expose the
exact catalog. Requirements concern this report's completeness; none is an
additional prerequisite imposed on a user-requested broker transaction.

| Kind | Required check IDs |
|---|---|
| `deployment` | `exact_package`, `exact_runtime`, `regression_suite`, `installation_identity` |
| `data_entitlements` | `intended_use_rights`, `coverage_and_latency`, `timestamp_and_units` |
| `calculation_validation` | `independent_arithmetic`, `missingness_and_boundaries`, `frozen_replay` |
| `instrument_semantics` | `instrument_identity`, `valuation_units`, `economic_events`, plus class-specific checks below |
| `host_capability` | `inventory_observed`, `schema_contract_test`, `account_capability_observed` |
| `order_identity` | `durable_intent_id`, `lost_response_reconciliation`, `duplicate_delivery` |
| `order_lifecycle` | `partial_and_terminal_fills`, `reject_and_unknown`, `cancel_replace_race` |
| `restart_recovery` | `restart_after_submit`, `restart_after_fill`, `reconnect_event_replay` |
| `reconciliation` | `orders_and_fills`, `positions_and_cash`, `unexplained_break_handling` |
| `feed_drills` | `stale_and_disconnected`, `late_or_corrected_data`, `halt_and_resume`, `operator_stop_recovery` |
| `environment_separation` | `endpoint_and_account_identity`, `wrong_environment_negative_test`, `secret_redaction` |
| `monitoring` | `heartbeat_and_owner`, `delivery_and_response_drill`, `rollback_and_recovery` |
| `strategy_validation` | `frozen_strategy_and_costs`, `complete_trials`, `untouched_evaluation` |
| `forward_validation` | `precommitted_decisions`, `new_outcomes`, `cost_and_benchmark_reconciliation` |
| `live_operational_validation` | `live_endpoint_identity`, `actual_order_reconciliation`, `observed_recovery` |

Research requires the first four categories. Paper requires those plus host
capability, identity, lifecycle, restart, reconciliation, feed drills, environment
separation, monitoring and strategy validation. Live adds forward validation and
live operational validation. A paper simulator's fills do not satisfy live
operational evidence. Collecting live evidence itself requires appropriate user
and platform authority; this helper neither requests nor supplies that authority.

Class-specific `instrument_semantics` checks:

- Stocks: `corporate_actions_and_settlement`.
- ETFs: `fund_distributions_and_settlement`.
- Options: `multiplier_and_expiry`, `exercise_assignment_and_settlement`,
  `option_permissions_and_margin`.
- Futures: `expiry_roll_and_delivery`, `variation_margin_and_collateral`.
- FX: `base_quote_and_pip_convention`, `rollover_and_settlement`.
- Bonds: `clean_dirty_price_and_daycount`, `coupon_redemption_and_credit`.
- Crypto: `pair_units_and_venue`, `custody_and_trading_permissions`.

For a truly inapplicable branch, record the supported scope and an actual negative
or boundary test in the referenced evidence; do not label an unrun test as passed.
For example, a long-only scope still needs evidence of what happens to an attempted
unsupported variant. Tests may establish correct handling of unsupported operations
without establishing the ability to perform them.

## Documentation and Robinhood snapshot

A documentation object has `id`, `host_id`, `asset_classes`, `modes`,
`observed_at`, `source_url` (HTTPS), `summary`, and `support` (`documented`,
`not_documented`, `documented_unsupported`). These are contextual source assertions.
They never qualify or deny the observed host. Future-relative documentation is
retained with a flag, not used as contemporaneous evidence. Documentary conclusions
are dated snapshots and must be revisited as platform capabilities change.

Snapshot reviewed October 23, 2026 Pacific time:
[Robinhood, Trading with your agent](https://robinhood.com/us/en/support/articles/trading-with-your-agent/)
describes external-agent long equity, options and crypto orders, excludes multi-leg
options orders, and lists account/pair-specific crypto conditions. It does not
establish external-agent futures, FX or bond trading. Individual ETF and other
instrument eligibility still requires observed host evidence. Product navigation
links are not agent capability evidence. No actual account or host tool inventory
was obtained for the packaged example.

The original code in this module implements an evidence-report schema, not a
Robinhood SDK or copied platform implementation. Its catalog is a conservative
engineering assessment design, not a regulatory certification or a universal
investment-validation standard. Existing `broker_bridge`, `execution_ledger` and
`guarded_execution` advisory/retired boundaries remain intact.

## Example

From the skill directory, choose a new output path outside the skill:

```text
python scripts/platform_readiness.py examples/platform-readiness.json --output ../platform-evidence-new.json
```

The example has 21 asset/mode requests, unknown deployment/runtime hashes, empty
observed evidence, and dated Robinhood documentation context. All 21 results
are `UNVERIFIED`. No account data, fake operating receipts or claimed platform
qualification is included. Output uses exclusive creation to preserve evidence.

The Python API is `assess(document)`. Tests use deliberately fictional receipts
to exercise schema/binding/time/conflict handling; a test catalog that qualifies
is not evidence that any real host was validated. A complete report also cannot
prove source authenticity, profitability, correct narrative interpretation or
every instrument's coverage.
