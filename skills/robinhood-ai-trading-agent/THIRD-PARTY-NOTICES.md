# Third-party dependencies and notices

The repository-authored skill code and documentation use the [MIT License](LICENSE).
The license does not replace the independent terms below or grant rights to
publisher reports, market data or material of unknown origin. Keep this file and
the included notices in standalone distributions; see [PROVENANCE.md](PROVENANCE.md)
for the historical predecessor and the latest bounded attribution audit.

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
| lxml | BSD-3-Clause project license; linked libxml2/libxslt have their own notices |
| tzdata | Apache-2.0 wrapper plus timezone-data terms |

Read the exact installed distribution's license and notice files for its version.
requirements-tested.txt records tested direct libraries and the numerical backend's
statsmodels dependency; it is not a complete transitive lockfile or license bill
of materials. If shipping an environment, wheels or binaries, review that actual
distribution and preserve all applicable notices, including transitive components.

An open-source client library does not grant permission to redistribute retrieved
market data. Obtain data through authorized sources under their applicable terms.

The repository's MIT license covers its own code; these notices describe external
components and retain their terms. Workflow influences are acknowledged separately
in [SOURCES.md](SOURCES.md).

## Version 4.0 research methods

New modules use existing external NumPy/SciPy/Requests dependencies. Their
implementation is recorded in the repository's development history; research
references are attributed in [quant methods](references/quant-research.md), including
Black-Scholes-Merton pricing, Holm correction and circular block resampling.
Cvxportfolio/Ledoit-Wolf implementations are not
bundled or imported. Referencing a method does not imply source-code reuse, an
endorsement or a license grant over the publications.

## Version 4.2 news and analyst research

The feed parsers, compact language rule set, guidance comparison and analyst
arithmetic are original package code using Python's standard library and the
existing Requests dependency. No external sentiment lexicon, FinBERT weights,
publisher implementation or paid news/research dataset is copied into the package.
Official API and methodology references are linked from references/news-and-guidance.md
and references/analyst-research.md. Public availability is not permission to
redistribute full news articles, reports or provider data; retain only permitted
local evidence and exclude personal source archives from releases.

## Optional sentiment model runtime (5.0)

No transformer code, model weights or tokenizer data are redistributed with this package.
The original optional adapter can call separately installed Hugging Face Transformers
(Apache-2.0), PyTorch (BSD-style license) and safetensors (Apache-2.0). Their installed versions
and distribution notices must be retained separately. The adapter performs no installation or
download. Model weights and training datasets have independent terms; software license terms
do not grant rights to them. For example, the current ProsusAI/finbert model card specifies
CC-BY-NC-SA-4.0 for its weights. It is not bundled or assumed unrestricted. The caller supplies
license identification, source, intended use and permission attestation, plus pinned file hashes.
License metadata is a recorded assertion, not automatic legal verification.

Primary license sources: [Transformers](https://github.com/huggingface/transformers/blob/main/LICENSE),
[PyTorch](https://github.com/pytorch/pytorch/blob/main/LICENSE),
[safetensors](https://github.com/huggingface/safetensors/blob/main/LICENSE),
[FinBERT model card](https://huggingface.co/ProsusAI/finbert).

## Optional portable calculations (5.1)

The original local wrappers call separately installed statsmodels (BSD), QuantLib
(modified BSD), and VADER (MIT) APIs. Their implementations and VADER lexicon are
not bundled in the skill; installed distributions retain their own notices.
See [portable methods: sources and licenses](references/portable-quant.md#sources-and-licenses)
for the upstream projects and license links. These optional libraries run inside
the host Python environment and require no backend service.
