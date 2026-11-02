# Release acceptance and reproducibility evidence

These tools make bounded claims about actual local files and fixture results.
They do not certify predictive skill, production readiness, rights to external
data, or a broker connection. They add no skill-owned trading approval flow.

## Actual offline fixture replay

`release_acceptance.run_fixtures(document, output_dir)` invokes a fixed allowlist
of installed helpers, retains exact inputs and complete results, checks explicit
expected projections/tolerances, and records Python/platform information and
implementation hashes. Output directories must be new. Failures remain recorded;
the runner does not execute arbitrary scripts or operations named by an input.

```text
python scripts/release_acceptance.py fixtures examples/release-acceptance-fixtures.json PRIVATE_NEW_OUTPUT
```

The bundled fictional fixtures check cent conservation and an ACT/365F cash
calculation. They are intentionally small, independently checkable acceptance
examples, not replacements for the regression suite or strategy validation.
Run the full relevant suite as well. A fixture pass in an existing environment
must not be described as a clean installation.

## Exact dependency artifacts and environment profiles

`dependency_inventory.capture` resolves the actual installed dependency closure
from distribution metadata, including requested extras and platform markers.
It emits an observed-version inventory and a CycloneDX 1.6 SBOM. Only when every
resolved package has retained wheel/source-archive bytes, with no version
conflicts, does it emit an installable `--require-hashes` lockfile. Installed-tree
or RECORD hashes cannot substitute for distribution artifact hashes.

```text
python scripts/dependency_inventory.py capture requirements-tested.txt PRIVATE_NEW_INVENTORY --artifacts PRIVATE_WHEELHOUSE
python scripts/dependency_inventory.py verify PRIVATE_NEW_INVENTORY/dependency-inventory.json PRIVATE_WHEELHOUSE
```

Two actual artifact profiles are included under `environments/`:

- `windows-cp312-core`: 42 distributions, the observed core numerical/data runtime.
- `windows-cp312-data-quant`: 45 distributions, adding PyArrow, QuantLib and VADER.

They bind Windows/CPython 3.12 artifacts. Wheels are deliberately not bundled in
the skill. These are not Linux/macOS locks, not a universal Python-version claim,
and not a complete transformer/model-weight environment. A source-archive hash
would authenticate the archive, not a reproducible compiled build; build-time
dependencies need their own lock. The currently captured profiles use wheels.

A separately authorized clean-room acceptance run should create a fresh venv,
install the applicable lock from verified artifacts, and run fixtures and tests:

```text
python -m venv PRIVATE_NEW_ENV
PRIVATE_NEW_ENV/Scripts/python -m pip install --no-index --find-links PRIVATE_WHEELHOUSE --require-hashes -r environments/windows-cp312-data-quant/requirements.lock.txt
PRIVATE_NEW_ENV/Scripts/python scripts/release_acceptance.py fixtures examples/release-acceptance-fixtures.json PRIVATE_NEW_RESULT
PRIVATE_NEW_ENV/Scripts/python -m unittest discover -s tests
```

Record actual commands, exit statuses, install log, runtime, package manifest and
result hashes. No test count alone establishes substantive correctness or market
performance. Keep each failing first attempt and explain repairs. A package hash
change requires a new receipt; do not reuse an earlier receipt as current proof.

## Cross-host first responses

The fictional browser-compatible prompt
`examples/cross-host-acceptance-prompt.txt` needs no private data or filesystem.
Its frozen expected result is separate. Send the same prompt in a fresh context
to each intended host; do not send another host's answer or the expected result.
Use the user's browser-isolation and model-interaction policies. Never bypass
authentication checks, assume unavailable tools exist, or label an unrun host as
passed. Preserve the actual first response, errors, model/version observations,
prompt hash, input-bundle hash, source/tool entitlements and independence limits.

`grade_response(document)` strictly parses a supplied response as JSON, rejects
duplicate keys/nonfinite values and compares the complete object with the frozen
expected fixture. An answer wrapped in unrequested prose/fences is ungradable,
not silently repaired into a pass. This is a pure operation suitable for replay.

```text
python scripts/release_acceptance.py grade RESPONSE_GRADE_INPUT.json
python scripts/release_acceptance.py hosts HOST_CATALOG.json PRIVATE_EVIDENCE_ROOT
```

`compare_host_responses(document, root)` checks actual retained response-file
hashes and input identities. The catalog also requires separately attributed
review of numerical results, universe, dates/availability, units/denominators,
source access, assumptions, exclusions, recommendation limits and export. Missing
hosts remain `NOT_RUN`. These semantic reviews remain reviewer declarations;
file hashes cannot authenticate that an external model produced the file.
Different model outputs are results, not a reason to discard or fabricate runs.
One shared arithmetic fixture does not establish general model equivalence.

## Source rights and release claims

`rights_inventory(document)` evaluates a declared intended use, provider, artifact
kind, terms snapshot hash/date, review expiry, permitted uses, attribution,
retention period and reviewer/evidence pointer. Missing, stale, future or
incompatible review records remain unresolved. The operation neither retrieves
terms nor grants rights. A free website, open-source client or personal-use
entitlement does not by itself support commercial use or redistribution.

```text
python scripts/release_acceptance.py rights templates/source-rights-inventory.json
```

Keep underlying market data, publisher reports, model weights and private evidence
outside the distributable package unless their exact use is supported by an
appropriate rights review. Software-only distribution can use separately acquired
user data; do not present such an arrangement as a bundled data entitlement.
The SBOM inventories dependency metadata, not a completed legal/security audit.

Populate `templates/release-capability-card.json` from actual scoped receipts.
Distinguish implemented local calculation, tested runtime, independently reviewed
research, external data coverage and observed host/broker capability. Numerical
replay, actual host collection and forward investment outcomes are separate
evidence categories. No template default establishes a successful external run.
