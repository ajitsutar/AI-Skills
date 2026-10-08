# Third-party dependencies and notices

## Numerical backend

The volatility adapter imports [arch 8.0.0](https://pypi.org/project/arch/8.0.0/)
by Kevin Sheppard. Its published license expression is NCSA. The full notice from
that wheel is preserved in [ARCH-LICENSE.txt](ARCH-LICENSE.txt).
No arch implementation source, wheel or compiled binary is vendored here.

The adapter uses the public [model and forecasting APIs](https://arch.readthedocs.io/en/latest/univariate/forecasting.html).
Its code is an integration layer written for this package. Backcasting, likelihood
optimization, variance filtering and analytical forecasting come from the installed
library. Output records the actual backend version and parameter names.

## Other installed packages

Requirements install dependencies rather than copying their source into the skill.
The tested environment includes the following project-level licenses; bundled
components may carry additional notices.

| Package | Observed license or license family |
|---|---|
| NumPy | BSD-3-Clause and additional bundled-component terms |
| SciPy | BSD project license and bundled-component notices |
| pandas | BSD-3-Clause |
| statsmodels | BSD-3-Clause |
| exchange_calendars | Apache-2.0 |
| yfinance | Apache-2.0 |
| jsonschema | MIT |
| requests | Apache-2.0; upstream LICENSE and NOTICE |
| tzdata | Apache-2.0 wrapper plus timezone-data terms |

Read the exact installed distribution's license and notice files for its version.
requirements-tested.txt records tested direct libraries and the numerical backend's
statsmodels dependency; it is not a complete transitive lockfile or license bill
of materials. If shipping an environment, wheels or binaries, review that actual
distribution and preserve all applicable notices, including transitive components.

An open-source client library does not grant permission to redistribute retrieved
market data. Obtain data through authorized sources under their applicable terms.

These notices do not license the repository's own code. Workflow influences are
acknowledged separately in [SOURCES.md](SOURCES.md).
