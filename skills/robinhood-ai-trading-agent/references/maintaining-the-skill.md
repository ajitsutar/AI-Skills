# Maintaining current documentation

Apply this procedure whenever changing or releasing this skill. The README is a
guide to what the skill does now: purpose, supported workflows, setup, evidence
requirements and material limits. Keep release history, numbered release summaries
and dated test milestones in their appropriate review records, not the README.
Retain machine-readable versions in VERSION, package metadata and integrity records.

## Refresh the examples on every update

1. Review the latest SKILL.md, helper interfaces, profiles and workflow references.
   Check both ordinary investor tasks and advanced quant, risk, validation,
   accounting, data, news and operational workflows.
2. Update README.md for the actual current behavior. Update the repository overview
   when it describes this skill. Preserve install, dependency, licensing and
   execution-scope information people need to use it correctly.
3. Edit `references/example-prompts.json`, the source of the prompt catalog. Each
   section needs actual local guides, an audience and distinct copyable prompts.
   Add newly supported capabilities, revise changed behavior and remove stale
   claims. Include failure analysis and unsupported-capability assessment where
   useful. There is no fixed count, minimum quota or upper limit. Examples must not
   imply missing data, calibrated alpha, broker support or permissions exist.
4. Complete the package's version/entrypoint metadata changes, then regenerate and
   check the documentation from the skill directory:

   ```text
   python scripts/release_docs.py generate --reviewed
   python scripts/release_docs.py check
   ```

5. Rebuild PACKAGE-MANIFEST.json and any standalone ZIP only after the generated
   documentation is current. Include the catalog, release_docs.py and DOCS-STATE.json
   so the check works from this skill folder alone. Run the check again in the
   packaged copy. Keep personal data, source archives and runtime state out of it.

The check fails on a changed VERSION, README, catalog, helper, profile, template,
example, agent, workflow reference, license, provenance or dependency/source notice,
and on manual edits to the generated prompt document. Adding/removing an input file
also invalidates the receipt. It normalizes
LF/CRLF for documentation freshness across operating systems; the package manifest
retains its separate byte-integrity contract. Repository CI runs the same check.

Generation is mechanical; it cannot invent appropriate examples or prove that a
description is true. `--reviewed` records the maintainer's completed review through
an updated fingerprint, not an independent semantic audit. Do not pass it merely
to silence a stale-documentation failure. When a change only fixes documentation
and adds no capability, retaining already accurate prompts is appropriate, but
the catalog still must be reviewed and regenerated for the new package.

## Verification scope

Inspect the rendered catalog's links and workflow coverage. Exercise the generator
and stale-input rejection after changing its behavior. Use tests relevant to any
investment or execution code changes; prose edits alone do not require rerunning
expensive financial models or a whole-market acquisition. Review records describe
checks actually performed; a previous release's test result is historical evidence.
