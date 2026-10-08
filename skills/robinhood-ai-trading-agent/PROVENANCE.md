# Provenance and release status

Version 3.2.0, October 8, 2026.

## What changed

The v3.1 audit found missing workflow credits and unresolved origins for parts of
the uploaded predecessor. This release restores the five historical credits in
[SOURCES.md](SOURCES.md), replaces the entire inherited volatility helper with a
new integration adapter, and replaces the investor-policy template and influencer
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
Its original author and reuse terms could not be established through the public
search. Do not describe that archive as licensed or wholly original.

The audit compared all 86 files of the v3.1 skill at commit
fe65aeba9404211651b867a2d81fe3ae29af0e71 with the supplied archive. It found eight
unchanged Python definitions in the former GARCH helper and retained template text.
It also screened 227 code/Markdown files across five public repositories and
3,086 Python files from eight direct dependencies, without finding candidate
external matches above its exact-match thresholds.

Those searches did not cover all private, deleted, unindexed or rewritten code.
Unauthenticated GitHub code search and grep.app were unavailable. This is a
technical provenance review, not legal clearance. Replacing material in the
current release does not change older commits, downloaded ZIPs or existing forks.

## Licensing and notices

The repository has not selected a license for its own material; its root README
already states that limitation. This release does not add a blanket license or
claim ownership of third-party material. The bundled upstream license notice
applies to arch, not to the entire skill.

Credits record influences. If identifiable third-party code or text is added
later, record its exact source/version, check its reuse terms, and retain the
applicable copyright, license and notice files. Keep dependency provenance
separate from market-data permissions and brokerage terms.

See [THIRD-PARTY-NOTICES.md](THIRD-PARTY-NOTICES.md) and
[the release review](REVIEW-3.2.md).
