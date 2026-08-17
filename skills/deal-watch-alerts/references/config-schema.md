# Deal Watch Configuration

Use this reference when creating or updating a reusable deal-watch configuration. YAML is convenient for humans; JSON is better for scripts. Keep secrets, phone numbers, and email addresses out of committed examples unless the user explicitly wants them stored.

## Required Top-Level Fields

```yaml
watch_name: "short-human-name"
browser:
  mode: "headless"
  isolation: "dedicated_profile"
  profile_id: "short-human-name"
  overlap_policy: "fail_closed"
  continue_on_source_error: true
  navigation_timeout_seconds: 45
  settle_seconds: 3
  checkpoint_file: "./deal_scan_checkpoint.json"
memory:
  file: "./deal_alert_memory.json"
  duplicate_policy: "stable_key"
  treat_lower_price_as_new: true
  strip_tracking_parameters: true
  key_fields:
    - "store"
    - "product_id_or_url"
    - "item_id"
    - "model"
    - "variant"
    - "condition"
    - "seller"
    - "currency"
  required_key_fields:
    - "store"
    - "product_id_or_url"
    - "item_id"
    - "model"
    - "variant"
    - "condition"
    - "seller"
sources:
  - name: "Amazon"
    type: "retailer"
    enabled: true
    urls:
      - "https://example.com/product"
    search_queries:
      - "exact item search query"
items:
  - id: "item-1"
    label: "Human-readable item name"
    threshold:
      amount: 1500.00
      currency: "USD"
      comparator: "<="
    required:
      identity_terms: ["Brand", "Model"]
      attributes:
        screen_size: "16-inch"
        min_ram_gb: 32
        storage_gb: 512
        color: "Space Black"
      reject_terms: ["18GB", "24GB", "screen scratches"]
    condition:
      accepted_labels: ["Good", "Excellent", "Premium"]
      evidence_required:
        screen: "no scratches"
        body: "light scratches or better"
      reject_labels: ["Fair", "Acceptable", "Poor", "Parts only"]
notifications:
  chat:
    enabled: true
  email:
    enabled: false
    to: []
    subject: "Deal"
  sms_email_gateway:
    enabled: false
    to: null
    subject: "Deal"
    max_chars: 70
    no_urls: true
  webhook:
    enabled: false
    url_env: null
```

## Field Guidance

- `watch_name`: stable name for automation logs, memory files, and summaries.
- `browser.mode`: use `headless` for unattended checks unless the user explicitly requires a visible browser.
- `browser.isolation`: use `dedicated_profile` for a watch-specific authenticated profile or `per_run_profile` for an isolated run copy. Never point at the user's everyday browser profile.
- `browser.profile_id`: stable, watch-specific identifier. Different automations must not share one profile.
- `browser.overlap_policy`: use `fail_closed` when a profile is already active, or `isolated_copy` only when the launcher can safely create independent run profiles. Do not coordinate unrelated watches with one global browser lock.
- `browser.continue_on_source_error`: when true, checkpoint the failed source, restart the isolated worker if needed, and continue. Browser-isolation or authentication-integrity failures still stop the run.
- `browser.navigation_timeout_seconds` and `browser.settle_seconds`: bound page waits. A timeout or blank page becomes `unverifiable`, never `no_match`.
- `browser.checkpoint_file`: absolute path for recurring automations. Write source status after every source so a later failure does not erase completed coverage.
- `memory.file`: path to JSON memory. Use an absolute path for recurring automations.
- `memory.duplicate_policy`: currently only `stable_key` is supported.
- `memory.treat_lower_price_as_new`: must be YAML/JSON boolean `true` or `false`, not a quoted string. When true, only a price below the best prior alert for the same offer is new; increases remain duplicate.
- `memory.strip_tracking_parameters`: must be a boolean. It removes fragments and common ad/tracking query parameters from fallback URL identity while preserving meaningful query parameters.
- `memory.key_fields`: non-empty list of fields that define the same offer. `price` is handled by the lower-price policy and is ignored here; `currency` is always added. The configured fields must produce at least one populated non-currency identity value. Add `shipping` or `availability` only when a change should define a materially different offer.
- `memory.required_key_fields`: optional subset of `key_fields` that must be populated before computing, claiming, or committing an alert key. Use it for seller, condition, selected variant, and other evidence whose absence could otherwise create an unstable key. Omit only fields genuinely optional for that watch.
- `sources[].type`: use `retailer`, `marketplace`, `deal_aggregator`, `search`, or `api`.
- `sources[].urls`: direct product, search, or saved-filter URLs. Prefer direct product URLs when variants matter.
- `sources[].search_queries`: exact search queries to use when direct URLs fail or when discovery is needed.
- `items[].threshold.comparator`: use `<=` for "at or below"; use `<` only for strict "below".
- `items[].required.identity_terms`: terms that must describe the selected offer or final merchant page.
- `items[].required.attributes`: configured item-specific fields. Do not assume the set; use whatever matters for the item.
- `items[].required.reject_terms`: terms that disqualify a candidate even if the title looks promising.
- `items[].condition`: omit if condition is irrelevant, but never omit if the user cares about refurbished, open-box, used, ticket view, seat obstruction, expiration date, warranty, or similar quality rules.
- `notifications`: configure only channels the user explicitly authorizes.

## Stable Deal Key

Build a stable key from fields that define whether a user would consider the alert materially new:

```text
store | product_id_or_final_url | item_id | selected_variant_fields | condition | seller | item_price
```

Do not put `price` in `key_fields`; `treat_lower_price_as_new` handles it directionally so a decrease can alert while an increase does not. Currency is always part of identity. The helper canonicalizes case/whitespace and structured variants, sorts meaningful URL query parameters, and excludes fragments and common tracking parameters by default. Never use session IDs, estimated tax, page-load timestamps, or ad click IDs as identity.

For concurrent or recurring runs, call `deal_memory.py claim` immediately before sending and `commit` after any confirmed delivery. Release only when every attempted provider proves it accepted nothing; leave partial or ambiguous transactions committed or pending as described in `notification-playbook.md`. Claim expiry is advisory and never clears a claim automatically. Pass the same `--config` to `key`, `check`, `claim`, `commit`, and `record`; changing policy between operations changes the keys.

The memory helper and browser worker solve different races. Memory claims suppress duplicate notifications. Browser isolation prevents profile corruption and cross-run page interference. Configure both; never rely on the memory lock to make a shared Chrome profile safe.

## Candidate Result Shape

Use this shape when handing candidates to `scripts/deal_memory.py`:

```json
{
  "store": "Amazon",
  "product_id": "B000EXAMPLE",
  "product_url": "https://example.com/dp/B000EXAMPLE",
  "item_id": "laptop-m3-16-36-512-black",
  "model": "Example laptop",
  "variant": {
    "screen_size": "16-inch",
    "ram_gb": 36,
    "storage_gb": 512,
    "color": "Space Black"
  },
  "condition": "Refurbished - Good",
  "seller": "Example Seller",
  "price": 1483.91,
  "currency": "USD"
}
```

## Example User Prompt

```text
Use $deal-watch-alerts to watch:
- Item: 16-inch laptop, M3 Pro, at least 32GB RAM, 512GB SSD, Space Black
- Sites: Amazon, Back Market, Walmart, Best Buy, Slickdeals
- Threshold: at or below $1500
- Condition: screen must have no scratches, body light scratches or better
- Notify: post in chat and send SMS through my email-to-SMS gateway
- Memory file: ./deal_alert_memory.json
```
