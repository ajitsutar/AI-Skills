# Independent Muse/Codex public-data comparison — October 11, 2026

**Measured candidate overlap: 10/10 (100%), passing the predefined 80% target.**
This is research-candidate agreement, not ten filing-verified buys, Strong Buy
confidence, a full-universe investment ranking or investment-performance evidence.

## Exact prompt

> Rerun top 10 buys (strong recommendation) from S&P 500 with 1 year hold horizon. Ignore anything you know about my investment philosophy or preference and only use the prompt.

Both models used the shipped public-vqm-discovery profile, P1Y horizon descriptor,
count 10 and October 9, 2026 completed XNYS close. Each fetched public data itself;
Codex did not supply its snapshot or disclose its picks before Muse froze its
result. The same setup specified full-universe acquisition, exact code execution,
retained receipts and separate research-candidate/eligibility reporting.

## Results

| Issuer | Codex rank | Muse rank | Codex VQM | Muse VQM |
|---|---:|---:|---:|---:|
| CF | 1 | 1 | 0.781903 | 0.784487 |
| INCY | 2 | 2 | 0.774431 | 0.772446 |
| NEM | 3 | 3 | 0.732274 | 0.734031 |
| CNC | 4 | 4 | 0.648191 | 0.643682 |
| VLO | 5 | 7 | 0.634774 | 0.598919 |
| APA | 6 | 6 | 0.625935 | 0.614868 |
| SNDK | 7 | 5 | 0.615203 | 0.621417 |
| EXPE | 8 | 8 | 0.593839 | 0.592593 |
| DGX | 9 | 9 | 0.540704 | 0.539614 |
| MU | 10 | 10 | 0.535526 | 0.535657 |

- Eight exact rank positions match. VLO and SNDK exchange positions 5 and 7.
- Both attempted 503 securities representing 500 issuers. Codex scored 401;
  Muse scored 414. All 401 Codex-scored issuers are in Muse's scored set.
- No common issuer's full-precision score is identical. The largest absolute
  score difference among the 401 common issuers is 0.08776845. These are VQM
  score units, not return forecasts. Peer populations and financial inputs differ.
- Muse additionally scored BEN, BSX, CMI, D, DUK, DVA, EG, EMR, EOG, ETN, EW, GS
  and IT. Codex's independently obtained statements had stale periods, missing
  matching periods or missing values for these issuers. They were excluded by
  the same rules. Exclusion agreement is therefore false.
- Each run retains one missing FDXF cash-flow response. Its successfully fetched
  price history already fails the fixed required history length, so that
  financial gap cannot change eligibility for scoring. Failed price requests or
  financial acquisition failures for history-eligible issuers block acceptance.
- Both outputs are RESEARCH_QUEUE_ONLY; buy_eligibility is NOT_ESTABLISHED,
  eligible_buys is empty and strong_buy_available is false.

## Verification and provenance

Muse confirmed the uploaded archive and all 142 manifest entries, matching the
normalized scorer hash. Its source acquisition ran October 11 at approximately
14:34–14:42 UTC. Codex's independently acquired snapshot was collected and recovered
earlier under the same price-close contract. This is not a historical point-in-time
backtest: financial publication and restatement timing are not certified.

Muse's original 53,281,720-byte JSON was privately transferred in five base64/gzip
parts. Every part, the gzip and original JSON byte hashes were checked. The unchanged
shipped comparator replayed both original bundles and returned PASS. Full datasets,
transfer receipts and comparison diagnostics are retained in the user's local test
artifacts; vendor datasets and private conversation exports are not distributed here.

| Artifact | SHA-256 |
|---|---|
| Tested upload ZIP | 48528e2ccb8b006d2ed9f34b88656225d0c5e91ffc69c20bebc57fe81ef7f672 |
| Normalized scorer | 016dcdc6b58199fef31de610972c4bfd5fed8bfaf2ead597f758414696ebd7d7 |
| Profile | 3587812f53897a3a5b0d05fb74ae485c502aa54925c7ba416774f710ecd19a3f |
| Codex canonical input | 0a2d4f0fd4a59128f774d46934b2af26c4516394bd7081af912db98df24a678d |
| Muse canonical input | 4087bbb854bcfa6a6628542173236441ec6a0a6aeb93bab9bc07671a0c591aa7 |
| Original Muse JSON bytes | 6ff59194d041e8befd010b6486037748cf70558372c76e5f54a4e92e85322513 |

The release adds documentation clarifying that the collector creates its output
directory; the tested calculations and profile were not changed after either
model's final result. Both environments passed 351 software tests. One successful
date/contract does not guarantee future 80% overlap. Specialized bank/REIT data,
filing-level eligibility, return calibration and comparable horizon-specific
investment judgments remain material limits.
