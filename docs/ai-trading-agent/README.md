# AI Trading Agent distribution and listing materials

These public pages and assets describe the full AI Trading Agent skill published by Ajit Sutar. The skill is free and self-contained; it includes investment research, portfolio analysis, paper workflows, and host-dependent native broker handoff and execution instructions.

- [Privacy notice](PRIVACY.md)
- [Terms of use](TERMS.md)
- [Support](SUPPORT.md)
- [Full skill](../../skills/ai-trading-agent/)

## Install from the GitHub repository marketplace

Use a Codex release with repository plugin marketplace support:

```bash
codex plugin marketplace add ajitsutar/AI-Skills --ref main
codex plugin add ai-trading-agent@ajitsutar-ai-skills
```

In a supported desktop client, open the Plugins Directory and select
**Ajit Sutar AI Skills**. Find **AI Trading Agent**. You can also install it there after
registering the source. Refresh or restart the client if the new source has not
appeared. Confirm the plugin is installed and enabled before using it in a new
chat. Registering a catalog alone does not verify installation or execution.

The `ai-trading-agent` entry selects the generated, self-contained package at
`plugins/ai-trading-agent/`, including the complete trading skill, Python helpers
and portfolio-following subskill. The catalog preserves the existing `ai-skills`
entry for the full repository bundle. It is a GitHub-hosted catalog,
not a GitHub Marketplace app or Action, and does not confer OpenAI public-directory
approval. The existing [Claude Code repository plugin](../../README.md#optional-install-all-skills-as-a-claude-code-plugin)
remains a separate installation of all seven skills.

The skill is free and self-contained. No server, daemon or always-on backend is
required. Invoked Python workflows need a compatible runtime and their documented
dependencies; installing the plugin does not install those dependencies or supply
web access, market data or broker connections. Ask the assistant to check the
current host before starting. Paid data subscriptions are optional and can use
existing access supplied by the user. Native broker execution remains subject to
actual host tools, authentication, user authority and platform rules.

Try these supported starter prompts:

- "Research a U.S. stock event using free sources, dated flow and squeeze evidence, and clearly identify missing data."
- "Analyze the risk in my supplied portfolio and compare the results with an explicit benchmark and horizon."
- "Explain the broker handoff workflow, execution modes and host capabilities required before any live order."

See the [full prompt catalog](../../skills/ai-trading-agent/EXAMPLE-PROMPTS.md)
and [runtime setup guide](../../skills/ai-trading-agent/INSTALL.md) for the
workflow-specific prerequisites and limits.

To refresh the tracked repository source, run
`codex plugin marketplace upgrade ajitsutar-ai-skills`, then use the client's
plugin update/reload flow and check the installed version. A source refresh alone
does not prove that an active chat has loaded the new files. See OpenAI's
[repository marketplace documentation](https://developers.openai.com/plugins/build/plugins#add-a-marketplace-from-the-cli)
for supported source and refresh commands.

## Maintain the repository plugin package

The canonical trading source remains in `skills/ai-trading-agent/`. The repository
marketplace points to a generated portable package in `plugins/ai-trading-agent/`;
it has its own `plugin.json`, assets, license and complete skill copy. The existing
`ai-skills` entry continues to point at the repository root and its Claude-compatible
manifest. There is no repository-root Codex manifest overriding that bundle.

After an accepted trading-skill or listing update, run these maintainer commands
from the repository root:

```bash
python .github/scripts/build_trading_plugin.py
python .github/scripts/build_trading_plugin.py --check
```

Commit the regenerated package with the accepted source change. The check verifies
the generated files against their canonical inputs; do not edit the generated
copies directly. These are repository maintenance commands, not a backend or a
prerequisite for users who install the prepared plugin.

## OpenAI directory listing materials

The logo is a text-free, fictional stock-price graph. It does not depict a real security or market history. The separate dark-mode image preserves that fictional illustration. Both images were created with OpenAI image generation for this listing.

`plugin.json` contains the metadata for a separate, full-skill OpenAI plugin package. To assemble that package, copy this manifest and `assets/` to the package root, retain the repository MIT `LICENSE`, and copy the entire `skills/ai-trading-agent/` directory into `skills/ai-trading-agent/` in the package. Do not include other skills, private configuration, credentials, research outputs or release evidence. Confirm that the manifest version matches the selected full skill and revalidate the package before uploading.

The intended directory availability is United States only. Publishing these materials does not mean OpenAI has received, approved or listed the plugin. The full broker-execution capability is disclosed in the metadata; applicable platform rules, automated checks, identity verification and review still determine eligibility.
