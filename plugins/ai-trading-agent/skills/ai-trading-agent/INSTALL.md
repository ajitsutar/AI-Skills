# Install AI Trading Agent

This folder is the complete skill source package. Keep `SKILL.md` and all its
subfolders together. No files from another skill or the repository root are
required to use it. Runtime tools and Python/Node packages depend on the
helpers used. No paid subscription is required to use this skill. External
services and model downloads are optional, feature-specific capabilities;
missing data or dependencies can limit a particular analysis. See
[source access](references/source-access.md) and [SKILL.md](SKILL.md).

For a reproducible Windows/CPython 3.12 research environment, use the complete
artifact-hashed profiles in `environments/windows-cp312-core/` or
`environments/windows-cp312-data-quant/`. The latter adds PyArrow, QuantLib and
VADER. See [release acceptance](references/release-acceptance.md) for fresh-environment
installation and frozen-fixture replay. These locks do not claim compatibility
with other operating systems or include transformer model weights. Keep downloaded
wheels and virtual environments outside the installed skill folder.

For task-specific setup and missing-capability recovery, follow [workflow setup](references/workflow-setup.md). Its checks distinguish observed Python/file behavior from declared native host tools; a successful local check does not qualify every host. Keep each representative exercise and its actual result outside the installed skill.

## Host-permitted research environment on other systems

Use Python 3.11 or newer available to the selected host. Where that host permits
local Python and dependency installation, create a fresh, unused environment
outside the skill; do not install globally or launch a server. For Linux, run
from this extracted skill folder (the macOS executable layout is the same):

```sh
python3 -m venv ../trading-env
../trading-env/bin/python -m pip install -r requirements-tested.txt
../trading-env/bin/python -m pip check
../trading-env/bin/python -B scripts/research_preflight.py
../trading-env/bin/python -B scripts/release_acceptance.py fixtures examples/release-acceptance-fixtures.json ../trading-fixtures-new
../trading-env/bin/python -B -m unittest discover -s tests -v
```

On Windows, use `python` to create the environment and substitute
`..\trading-env\Scripts\python.exe` for its executable. Choose unused environment
and fixture-output paths. The package remains portable files plus invoked local
helpers: no backend, daemon, endpoint or always-on service is required. A host
that cannot run Python or install these packages can still use the instructions
and supported supplied evidence, but must report unavailable calculations.

`requirements-tested.txt` pins direct research dependencies; it is not a complete
artifact-hashed transitive lock for every OS/Python combination. Optional PyArrow,
QuantLib, VADER and model-weight features retain their separate requirements;
missing components remain explicit limitations. Do not copy Windows-only wheels
or present a preflight availability result as proof of a clean installation.

The repository validation workflow runs standalone tests on Ubuntu and Windows
with CPython 3.11 and `requirements-tested.txt`. This describes its configured
scope; consult the actual matching-commit CI result before claiming a pass. It
does not establish a Linux CPython3.12 artifact lock/clean-install receipt,
macOS qualification, or successful feature use on Muse, Claude, Instinct or any
other model host. Cross-host first responses and feature qualification require
separate observed evidence under [release acceptance](references/release-acceptance.md).
Find the public [validation workflow and run history](https://github.com/ajitsutar/AI-Skills/actions/workflows/validate.yml) in [AI-Skills](https://github.com/ajitsutar/AI-Skills). Match the published commit and skill version/manifest to the package being used, then inspect that commit's job results; a newer green run does not verify an older or modified package. The workflow configuration is available [in the repository](https://github.com/ajitsutar/AI-Skills/blob/main/.github/workflows/validate.yml).
Record install failures, actual package versions, preflight gaps and test results
for the environment used. No dependency installation occurred merely by reading
this recipe.

## Codex or another Agent Skills host

Copy this entire `ai-trading-agent` folder into the skills directory used by your host.
Do not install two copies of the same skill. Select `$ai-trading-agent` in Codex, or use
your host's skill selector. `agents/openai.yaml` supplies Codex presentation metadata.
For an existing installation, move the old `robinhood-ai-trading-agent` folder out
of the active skills directory after preserving any personal changes, then install
this renamed folder. Existing references must use the new invocation name.

## Claude Code: one standalone skill

Copy this entire folder to `~/.claude/skills/ai-trading-agent/` (or your project's
`.claude/skills/ai-trading-agent/`). Invoke `/ai-trading-agent`. No repository plugin is needed.

The optional specialized agent is included in `agents/robinhood-trading-agent.md`. To use it,
copy that file to `~/.claude/agents/` (or your project's `.claude/agents/`) after
installing the skill. It preloads `ai-trading-agent` and is named `ai-trading-agent`.
The template filename is retained for compatibility; its old filename is not the
skill or agent invocation name. Replace an older installed copy rather than keeping
two versions.
The nested `agents/plugin/` variant is only for the repository-wide `ai-skills`
plugin; do not copy that variant into your standalone agents directory.

## ZIP upload

For a host that accepts skill ZIPs, zip this entire folder so the archive contains
`ai-trading-agent/SKILL.md` and its sibling resources. Do not zip only `SKILL.md`.
Keep generated outputs, environments and account configuration outside the package.
Uploading the package does not configure external tools or grant transaction authority.

## Optional historical-data storage dependency

The compressed raw-response store and compact evidence mode use the standard
library. ZSTD Parquet batch reads/writes additionally require PyArrow:

```text
python -m pip install -r requirements-optional-data.txt
```

Install into the host's selected research environment. Missing PyArrow leaves
gzip storage available and causes an explicit error for Parquet operations; it
does not justify relabeling another format as Parquet. Run
`python scripts/research_preflight.py` to inspect available components.

## License and notices

Keep the included [MIT License](LICENSE), [third-party notices](THIRD-PARTY-NOTICES.md)
and [arch license](ARCH-LICENSE.txt) in copies and ZIPs. MIT covers the
repository-authored skill code and documentation; dependencies, reports and market
data retain their own terms. [PROVENANCE.md](PROVENANCE.md) records the source audit
and the user-confirmed personal-Codex origin of the historical predecessor.
