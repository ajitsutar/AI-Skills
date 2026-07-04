# Deal Watch Configuration

Use this reference when creating or updating a reusable deal-watch configuration. YAML is convenient for humans; JSON is better for scripts. Keep secrets, phone numbers, and email addresses out of committed examples unless the user explicitly wants them stored.

## Required Top-Level Fields

```yaml
watch_name: "short-human-name"
memory:
  file: "./deal_alert_memory.json"
  duplicate_policy: "stable_key"
  treat_lower_price_as_new: true
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
- `memory.file`: path to JSON memory. Use an absolute path for recurring automations.
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

Include price if lower prices should trigger new alerts. Exclude volatile fields such as session IDs, tracking parameters, estimated tax, page-load timestamps, or ad click IDs.

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
