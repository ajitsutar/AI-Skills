# Provenance and attribution

Reviewed October 12, 2026. The current repository-authored package is distributed
under the [MIT License](LICENSE), subject to the third-party boundaries below.

## Historical replacement of inherited material

The v3.1 audit found missing workflow credits and unresolved origins for parts of
the uploaded predecessor. The October 8, 2026 repair restored five historical
credits in [SOURCES.md](SOURCES.md), replaced the inherited volatility helper with
a new integration adapter, and replaced the investor-policy template and influencer
adaptation text. The adapter imports the NCSA-licensed arch package; it does not
carry forward the predecessor's optimizer or variance-recursion implementation.

The replaced files are:
- scripts/garch_volatility.py: input validation, data-audit integration,
  chronological scoring and JSON output around the external arch API.
- templates/investor-philosophy.md: a new brief for objectives, allocation,
  practical constraints, authorization and review.
- references/miles-deutscher-adaptation.md: a new source-context note.

The remaining package instructions and helpers were developed in the workspace
during the user's review and upgrade process. That development history and a
negative match scan are not guarantees against every possible external similarity.

## Immediate source and historical limits

The predecessor was the user-supplied robinhood-ai-trading-agent.zip with SHA-256
7d8ea60d8ac35012d8b025fae8c21603379badf378a67239ecf20b5c625ddde3.
On October 12, 2026, the maintainer confirmed that this ZIP was generated using
their personal Codex account. This is user-confirmed creation provenance and
supersedes the earlier unknown-origin wording; no third-party repository has been
identified as the ZIP's source. The prior generation transcript was not supplied.
AI generation is not evidence that every line is unique, so the archive and
current code remain subject to the same external-source comparison and attribution
review as other code. No specific unattributed implementation has been established
within the reviewed scope.

The October 8 audit compared all 86 files of the v3.1 skill at commit
fe65aeba9404211651b867a2d81fe3ae29af0e71 with the supplied archive. It found eight
unchanged Python definitions in the former GARCH helper and retained template text.
It also screened 227 code/Markdown files across five public repositories and
3,086 Python files from eight direct dependencies, without finding candidate
external matches above its exact-match thresholds.

Those searches did not cover all private, deleted, unindexed or rewritten code;
unauthenticated GitHub code search and grep.app were unavailable to that audit.
Replacing material in the current package does not change older commits,
downloaded ZIPs or existing forks. The current MIT grant does not supply rights to
any third-party material that may later be identified. Earlier negative searches
and the maintainer's creation confirmation are distinct kinds of evidence.

## Current audit record

The October 12 audit examined all 190 tracked skill files at commit
`fd3679fb1a9d41542ec531512c0eddac1a52db17`, including 70 Python files and two shell
installers. All files were hashed/read and every Python file was parsed without
executing audited source. Manual review targeted provenance, imports, inherited
replacements, quantitative methods, news/analyst additions and bundled fixtures.

- Comparison with the original ZIP found no identical Python function/class
  definitions and no exact five-line windows meeting the text threshold below.
- Comparison with 241 text/code files from five frozen public repository snapshots
  found only the intentionally preserved arch license text, with its credit intact.
- Comparison with 4,139 installed Python source files across the eleven tested
  dependencies found no exact code windows meeting the threshold.

The text comparison used five consecutive nonblank, non-full-line-comment lines,
trimmed at their edges, totaling at least 180 characters. The archive definition
comparison used Python ASTs without position metadata, retaining identifiers and
literals. These checks cannot exclude shorter, renamed or paraphrased copying.
Targeted public searches did not identify another substantive source match.
The findings are a bounded technical review, not a proof of originality, legal
clearance, ownership or patent novelty. The audit count identifies that snapshot;
later license/documentation additions do not retroactively change its scope.

An October 12 follow-up included all 74 current trading code files, including
the new fractional helper and tests, in a repository-wide comparison of 99 code
files against 4,578 external files. No substantial text-window or normalized
function match was detected. Fresh public searches also examined distinctive
expressions in the original ZIP and the newly added code. AI-generated material
received the same comparison checks; the personal-Codex origin was not used as
an exemption or as proof of originality.

The original ZIP's Python helper and shell installer were also compared directly
against 241 retained public files and 4,139 installed dependency Python files.
No qualifying text, exact-definition or identifier-normalized AST match was found.
One external file using newer syntax was subsequently parsed and compared with
Python 3.12, also without a match. The original cached `.pyc` was inventoried, not
decompiled; it is not included in the current package. Fresh searches identified
ordinary GARCH-equation similarity, not a substantive shared implementation.

Current news/feed parsing, guidance comparison and analyst arithmetic are recorded
as workspace-developed code. They use a compact explicit language rule set and
external Requests rather than bundled sentiment-model weights or publisher reports.
The current inventory contains fictional fixtures, not the private research
archives used during development. Preserve source evidence outside the public
package and review rights before adding third-party material.

## Licensing and notices

The included [MIT License](LICENSE), copyright 2026 Ajit Sutar, covers the
repository-authored code and documentation. It does not claim ownership of or
relicense external dependencies, publications, market data or trademarks. Adding
this license to the current package does not change historical archive bytes.
The bundled [arch license](ARCH-LICENSE.txt)
retains its original author and terms and applies to that dependency.

Credits record influences. If identifiable third-party code or text is added
later, record its exact source/version, check its reuse terms, and retain the
applicable copyright, license and notice files. Retain the MIT license and these
notices in standalone distributions. Keep dependency provenance separate from
market-data permissions and brokerage terms. For future contributions, retain the
file/commit, author or origin evidence, exact upstream source/version when applicable,
license/notice disposition and audit date; a negative similarity scan alone cannot
establish the contributor's rights.

See [THIRD-PARTY-NOTICES.md](THIRD-PARTY-NOTICES.md) and
[the release review](REVIEW-3.2.md).

## Version 3.3 additions

Holding-period planning, declaration checks and fictional regression fixtures were
created for this repository in response to the user's workflow review. They reuse
the existing exchange_calendars integration, add no copied external implementation
or dependency, and preserve all 3.2 credits and notices. New fixtures contain no
personal account data or pasted private-agent research.

## Version 3.6 additions

The VQM contracts, accounting adapters, benchmark allocator and tests were newly
written for this repository. Research papers are credited in the shared-default
reference as conceptual influences; no paper code or datasets were copied.
The allocator imports the existing SciPy dependency. This is not a published
strategy replication or a claim of validated investment performance.

## Version 3.8 additions

The public research acquisition adapter, replayable queue, report checks and
fictional regression tests were written for this repository. They adapt this
workspace's repository-authored vendor experiment without embedding its data or
selected stocks. The current audit identified no external strategy implementation
match at its stated thresholds. The adapter
imports installed yfinance, requests, pandas and lxml libraries; their code and
retrieved market datasets are not redistributed in the skill package.

## Version 4.0 quantitative additions

The new quant workbench, validation, allocation, scenario, operational, primary-data,
monitoring and portfolio-simulation modules are recorded as implementations written
for this package. They do not bundle AQR or Cvxportfolio libraries or datasets;
the bounded audit above describes the actual comparisons performed. Published
method attributions and adoption limits are in references/quant-research.md. NumPy,
SciPy and Requests remain external dependencies under their existing licenses;
no publication text, vendor datasets or external implementation is redistributed.

## Fractional-share additions

The dollar-budget sizing helper, fractional runtime checks, recurring-occurrence
proposal generator and fictional tests were written in this workspace for the
small-account request. They use Python's standard-library Decimal arithmetic and
the existing local risk, broker-binding and ledger interfaces. No external broker
client, credentials or strategy implementation is included. The official Robinhood
product pages used to establish feature boundaries are linked in the
[fractional-share guide](references/fractional-shares.md); product documentation
is not treated as evidence of a connected tool's actual schema or permissions.
