# Version 3.2: provenance repair and licensed volatility backend

October 8, 2026.

The provenance review identified four dropped acknowledgments and inherited code
whose upstream origin could not be verified. This release restores the complete
credit list, replaces the inherited numerical implementation with an adapter to
arch 8.0.0, and replaces the retained investor-template and adaptation text.
Full scope and limitations are in [PROVENANCE.md](PROVENANCE.md).

## Behavioral compatibility

The volatility command retains its CSV/audit arguments, risk-sizing eligibility
gate, percent-squared forecast units, per-period decimal volatility, and legacy
daily-named JSON fields. It still uses zero-mean Gaussian log returns. Daily
volatility remains background context for day trading, not a precise intraday stop.

Estimation and initialization now belong to arch. Forecasts therefore need not
match v3.1 numbers. Parameter names and installed backend versions are explicit in
the output. Refit/revalidate existing numerical research before comparing releases;
do not reuse a prior script hash or treat the migration as strategy promotion.

Chronological holdout parameters are estimated once on the training prefix.
Every target forecast uses only its already observed prefix through arch's fixed
parameter API. The target and future returns are excluded even from backcasting.
A full-sample refit is used only for the subsequent forward forecast.
Nonconvergent, nonfinite and nonstationary fits cannot supply sizing inputs.

## Validation focus

Numerical tests cover GARCH/GJR expected multi-step variance, the EGARCH innovation
term and unsupported multi-step gate, holdout future-data isolation, failed fits,
units, parameter names, and audited/unaudited fictional-data eligibility.
The complete trading suite continues to cover portfolio, execution and day-trading
controls. Release results are recorded in VALIDATION-3.2.txt.

The arch license contains public author contact details. The repository's export
scanner permits those email matches only for the exact reviewed license path and
normalized content hash. All other detections remain active. Focused scanner tests
check that modified notices and unexpected secrets are still rejected.

No broker connection, live order or schedule is part of this release. No blanket
repository license is selected, and historical copies are not rewritten.
