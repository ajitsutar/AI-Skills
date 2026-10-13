# AI Skills

Reusable Agent Skills in self-contained folders. Download any one folder under `skills/` to use that skill independently; the full-repository Claude Code plugin is optional. See the license status below before reuse or redistribution.

## Included Skills

- `create-karaoke-video`: Create karaoke videos from supplied audio and lyrics, with timing, ASS subtitles and MP4 rendering. Optional vocal separation requires a model-specific rights record for the actual intended use.
- `create-guitar-karaoke`: Create guitar-muted practice mixes and still-image videos from verified supplied stems, with whole-song and selected-window modes. Optional model separation uses local assets with recorded weight permissions; model downloads are not automatic.
- `concert-ticket-checkout`: Assist with browser-based concert ticket searches, seat comparison, cart setup, checkout review, and user-supervised purchasing boundaries.
- `deal-watch-alerts`: Build configurable deal-watch automations that verify selected variants, condition rules, thresholds, duplicate memory, and optional chat/email/SMS alerts.
- `linkedin-knowledge-digest`: Filter LinkedIn feed and inbox activity into concise knowledge-bearing digests with clickable source links while excluding career milestones, hiring posts, self-promotion, and low-value outreach.
- `travel-deal-finder`: Compare current travel deals across flights, hotels, packages, and rental cars with clear ranking rules and source verification.

- `robinhood-ai-trading-agent`: Research and recommend stocks, analyze portfolios and day/swing strategies over arbitrary holding periods, and produce reproducible Value–Quality–Momentum rankings, evidence-backed financial normalization, and GARCH/GJR/EGARCH risk diagnostics. Research findings are advisory. Order intent goes to the host's normal broker workflow with zero execution gates imposed by this skill. The shared ranking is an uncalibrated research baseline, not a Strong Buy classifier.

The trading skill supports current stock research, portfolio management, news and
guidance review, analyst evidence, statistical strategy validation, multi-asset
risk, cash/performance accounting, fractional-share sizing and order-intent handoff.
Small-dollar and recurring-contribution research includes budget, fee and settlement
analysis. The host and broker handle execution independently of the research skill.
Stock
discovery defaults to all U.S. exchange-listed stocks and listed ADRs; S&P 500 is
an explicit preset. Its saved contracts and numerical helpers support reproducible
calculations while retaining source quality, coverage and unvalidated-performance
limits.

Read its [current capabilities and setup](skills/robinhood-ai-trading-agent/README.md)
or explore the [prompt catalog for investors, traders and quants](skills/robinhood-ai-trading-agent/EXAMPLE-PROMPTS.md).
Examples cover supported workflows and useful gap assessments without a fixed count.
For implementation boundaries and remaining research needs, see the
[capability review](skills/robinhood-ai-trading-agent/references/institutional-gap-review-4.2.md).

## Download one skill

The trading skill also supports a [local research library and incremental review](skills/robinhood-ai-trading-agent/references/research-memory.md): preserve evidence and replay inputs, refresh changing data, and reuse verified unchanged primary research without carrying old stock picks forward automatically.

Open a skill folder below and follow its local `INSTALL.md`. Copy the **whole folder**,
not just `SKILL.md`. Everything specific to that skill stays in that folder.

| Skill folder | Installation |
|---|---|
| [concert-ticket-checkout](skills/concert-ticket-checkout) | [Guide](skills/concert-ticket-checkout/INSTALL.md) |
| [create-guitar-karaoke](skills/create-guitar-karaoke) | [Guide](skills/create-guitar-karaoke/INSTALL.md) |
| [create-karaoke-video](skills/create-karaoke-video) | [Guide](skills/create-karaoke-video/INSTALL.md) |
| [deal-watch-alerts](skills/deal-watch-alerts) | [Guide](skills/deal-watch-alerts/INSTALL.md) |
| [linkedin-knowledge-digest](skills/linkedin-knowledge-digest) | [Guide](skills/linkedin-knowledge-digest/INSTALL.md) |
| [robinhood-ai-trading-agent](skills/robinhood-ai-trading-agent) | [Guide](skills/robinhood-ai-trading-agent/INSTALL.md) |
| [travel-deal-finder](skills/travel-deal-finder) | [Guide](skills/travel-deal-finder/INSTALL.md) |

Without Git, use GitHub's **Code > Download ZIP**, extract it, and keep only the
skill folder you want. With Git, a sparse checkout downloads a selected skill's
files without the other skill folders. For example:

```bash
git clone --depth 1 --filter=blob:none --sparse https://github.com/ajitsutar/AI-Skills.git
cd AI-Skills
git sparse-checkout set skills/robinhood-ai-trading-agent
```

The resulting `skills/robinhood-ai-trading-agent/` folder can be copied or zipped
on its own. External runtimes, libraries, configured services and model downloads
remain prerequisites where the individual skill calls for them.

## Layout

```text
skills/
  <skill-name>/
    SKILL.md
    INSTALL.md
    agents/
      openai.yaml                 Codex presentation metadata
      <agent-name>.md             Optional standalone Claude agent
      plugin/<agent-name>.md      Full-repository Claude plugin variant
    scripts/                     That skill's executable helpers, when needed
    references/                  That skill's supporting guidance, when needed
    ...                          Skill-specific data, tests and dependencies
.claude-plugin/                   Optional full-repository plugin metadata
.github/scripts/                  Repository maintenance and validation only
.github/workflows/                Continuous integration
```

There are no repository-root `scripts/` or `agents/` directories. No skill needs
`.github/`, `.claude-plugin/`, another skill, or the root README at runtime.
The optional plugin manifest points directly to each skill-local plugin agent
using Claude Code's [custom agent paths](https://code.claude.com/docs/en/plugins-reference#path-only-fields).

## Use With Codex

Current Codex releases discover personal skills under `~/.agents/skills`. Copy one skill or all seven there.

```powershell
New-Item -ItemType Directory -Force "$HOME\.agents\skills" | Out-Null
Copy-Item -Recurse "skills\<skill-name>" "$HOME\.agents\skills\"
```

On macOS or Linux:

```bash
mkdir -p "$HOME/.agents/skills"
cp -R "skills/<skill-name>" "$HOME/.agents/skills/"
```

Some older Codex desktop installations discover personal skills from `$CODEX_HOME/skills` (commonly `~/.codex/skills`). Use that as a legacy fallback only when it is the location shown by the running app; do not install the same skill name in both roots. Codex does not merge duplicate skill names, so duplicate copies can both appear in selectors. Restart Codex only if a newly copied skill does not appear automatically.

## Optional: install all skills as a Claude Code plugin

Install the repository as a native plugin. This loads all seven skills and their matching agents without copying folders or depending on the current working directory.

In Claude Code:

```text
/plugin marketplace add https://github.com/ajitsutar/AI-Skills.git
/plugin install ai-skills@ajitsutar-ai-skills
/reload-plugins
```

Verify installation with `/skills`, `/agents`, and `/doctor`. Plugin skills use namespaced commands such as:

```text
/ai-skills:create-guitar-karaoke
/ai-skills:travel-deal-finder
/ai-skills:linkedin-knowledge-digest
```

The matching Claude plugin agents have these scoped names:

- `ai-skills:concert-ticket-agent`
- `ai-skills:deal-watch-agent`
- `ai-skills:guitar-karaoke-agent`
- `ai-skills:karaoke-video-agent`
- `ai-skills:linkedin-digest-agent`
- `ai-skills:travel-deal-agent`
- `ai-skills:robinhood-trading-agent`

Claude can delegate automatically from each agent's description. To guarantee one runs, type `@` and choose its scoped name from the agent picker. A manual mention uses `@agent-` followed by the scoped name, for example `@agent-ai-skills:guitar-karaoke-agent`. Each agent preloads only its corresponding skill to keep context focused.

For local development from a clone, start Claude Code with:

```bash
claude --plugin-dir .
```

In PowerShell, the same command is:

```powershell
claude --plugin-dir .
```

Then use `/reload-plugins` after edits. Keep the plugin metadata consistent when publishing updates.

## Standalone Claude Skills

Claude Code can also discover these skills from `~/.claude/skills/` or a project's `.claude/skills/` directory. Copy any or all of the skill folders there. For example:

```bash
mkdir -p ~/.claude/skills
cp -R skills/concert-ticket-checkout ~/.claude/skills/
cp -R skills/create-guitar-karaoke ~/.claude/skills/
cp -R skills/create-karaoke-video ~/.claude/skills/
cp -R skills/deal-watch-alerts ~/.claude/skills/
cp -R skills/linkedin-knowledge-digest ~/.claude/skills/
cp -R skills/travel-deal-finder ~/.claude/skills/
cp -R skills/robinhood-ai-trading-agent ~/.claude/skills/
```

PowerShell equivalent:

```powershell
New-Item -ItemType Directory -Force "$HOME\.claude\skills" | Out-Null
Copy-Item -Recurse skills\concert-ticket-checkout "$HOME\.claude\skills\"
Copy-Item -Recurse skills\create-guitar-karaoke "$HOME\.claude\skills\"
Copy-Item -Recurse skills\create-karaoke-video "$HOME\.claude\skills\"
Copy-Item -Recurse skills\deal-watch-alerts "$HOME\.claude\skills\"
Copy-Item -Recurse skills\linkedin-knowledge-digest "$HOME\.claude\skills\"
Copy-Item -Recurse skills\travel-deal-finder "$HOME\.claude\skills\"
Copy-Item -Recurse skills\robinhood-ai-trading-agent "$HOME\.claude\skills\"
```

If the top-level skills directory did not exist when the session started, restart Claude Code once. Otherwise Claude detects skill changes live. Standalone skills can be invoked with `/skill-name` or preloaded into a custom agent:

```yaml
---
name: guitar-practice-producer
description: Creates guitar-muted practice tracks
skills:
  - create-guitar-karaoke
---
```

The per-skill `agents/openai.yaml` files are Codex metadata. Claude Code ignores
them. For an optional standalone Claude agent, follow that skill's `INSTALL.md`
and copy its `agents/<agent-name>.md` to your Claude agents directory. It uses an
unqualified skill name and needs no repository plugin. The
`agents/plugin/<agent-name>.md` variant uses the `ai-skills:` namespace and is
loaded only by the optional repository plugin. CI checks that the two variants
have identical instructions apart from that preload name.

## Safety Process

Before publishing or updating this repository:

1. Export only skill source files and supporting references.
2. Do not include local task folders, browser/session data, generated outputs, audio/video files, lyrics supplied by users, credentials, keys, tokens, cookies, or personal paths.
3. Replace copyrighted or user-specific examples with generic placeholders.
4. For trading-skill changes, follow its [documentation maintenance procedure](skills/robinhood-ai-trading-agent/references/maintaining-the-skill.md): review the current README and capabilities, refresh the prompt catalog and regenerate it before packaging. Validate the shared skill contract, resource links, Codex metadata, Claude plugin mappings, script syntax, and text hygiene:

```powershell
python .github/scripts/validate_portability.py
```

5. Test one-folder portability and run the safety scan:

```powershell
python .github/scripts/test_portability.py
python .github/scripts/check_standalone.py
```

`check_standalone.py` copies each skill independently into a temporary directory,
validates its local resources and agents, then runs its offline helper tests from
an unrelated working directory without `PYTHONPATH`. Install the CI test
dependencies first, or use `--structure-only` for the copied-resource checks only.
These are maintainer commands, not prerequisites for using a skill.


```powershell
python .github/scripts/safety_scan.py
```

6. When the Claude CLI is installed, validate the Claude package with Anthropic's CLI:

```bash
claude plugin validate . --strict
```

The repository's CI runs the portability checks and focused helper tests on both Windows and Linux, plus Claude's strict plugin validator on Linux. These checks are guardrails, not substitutes for review.

## Portability Contract

- Shared `SKILL.md` files use only the portable `name` and `description` frontmatter fields and avoid host-specific command substitution.
- Supporting resources are resolved relative to the directory containing `SKILL.md`, not the caller's working directory.
- Codex-specific presentation metadata lives only in each skill's `agents/openai.yaml`.
- Each skill contains both its standalone Claude agent and its namespaced plugin variant. The repository plugin manifest explicitly lists only the plugin variants.
- Optional browser, web, messaging, media, or model capabilities are declared as runtime prerequisites in prose; neither host is assumed to provide them automatically.

## Dependencies

Some skill scripts call optional third-party tools such as FFmpeg, Pillow, Demucs, or audio-separator. Dependencies and model checkpoints are not vendored in this repository.

The guitar helper uses external FFmpeg/ffprobe for metadata and media inspection;
it no longer directly depends on Mutagen. Optional separator environments still
have their own transitive dependency terms. The default guitar checkpoint's
license has not been established, and Demucs's software license does not establish
permission for its pretrained weights. Use verified supplied stems/instrumentals,
or follow the affected skill's model-specific permission workflow.

The trading skill has separate Python dependencies in `skills/robinhood-ai-trading-agent/requirements-tested.txt`. Use its isolated research environment. Packaging it as a Claude agent does not establish broker availability; order execution belongs to the host's broker integration.

Agents inherit the tools and MCP servers enabled in the user's Claude Code session. Live browser, web, Slack/email, or other external operations require the corresponding configured capability and authenticated session; the agents stop clearly when a required capability is unavailable.

## License

Repository-authored code and documentation are available under the [MIT license](LICENSE).
Each skill includes its own LICENSE, PROVENANCE.md and THIRD-PARTY-NOTICES.md, so a
standalone download preserves its license and source records. Keep those files
with copies or distributions.

External libraries, model weights, fonts, media and data retain their own terms;
MIT does not relicense them. Read the [notice index](THIRD-PARTY-NOTICES.md) and
[provenance record](PROVENANCE.md) for credited sources and unresolved historical
origins. Model-weight permissions must be established independently of the
inference software's license.
