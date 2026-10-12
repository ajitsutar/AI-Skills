# Third-party material and dependencies

The repository-authored code and documentation are offered under the [MIT
license](LICENSE). Each skill includes its own copy for standalone distribution.
That grant does not relicense third-party software, model weights, fonts, media,
datasets, broker services or website content. Preserve applicable upstream notices.

Each independently downloadable skill includes its own dependency/source record:

| Skill | Notices | Origin record |
|---|---|---|
| Concert ticket checkout | [Notices](skills/concert-ticket-checkout/THIRD-PARTY-NOTICES.md) | [Provenance](skills/concert-ticket-checkout/PROVENANCE.md) |
| Guitar karaoke | [Notices](skills/create-guitar-karaoke/THIRD-PARTY-NOTICES.md) | [Provenance](skills/create-guitar-karaoke/PROVENANCE.md) |
| Karaoke video | [Notices](skills/create-karaoke-video/THIRD-PARTY-NOTICES.md) | [Provenance](skills/create-karaoke-video/PROVENANCE.md) |
| Deal watch alerts | [Notices](skills/deal-watch-alerts/THIRD-PARTY-NOTICES.md) | [Provenance](skills/deal-watch-alerts/PROVENANCE.md) |
| LinkedIn digest | [Notices](skills/linkedin-knowledge-digest/THIRD-PARTY-NOTICES.md) | [Provenance](skills/linkedin-knowledge-digest/PROVENANCE.md) |
| Trading agent | [Notices](skills/robinhood-ai-trading-agent/THIRD-PARTY-NOTICES.md) | [Provenance](skills/robinhood-ai-trading-agent/PROVENANCE.md) |
| Travel deals | [Notices](skills/travel-deal-finder/THIRD-PARTY-NOTICES.md) | [Provenance](skills/travel-deal-finder/PROVENANCE.md) |

The trading skill intentionally retains the complete
[arch NCSA notice](skills/robinhood-ai-trading-agent/ARCH-LICENSE.txt) and
[workflow source credits](skills/robinhood-ai-trading-agent/SOURCES.md).
Those credits and terms remain intact under the repository's MIT licensing.

Dependencies are installed separately. A release that also distributes a runtime,
binary, checkpoint, font or dependency wheel needs an inventory and notices for
the actual included artifacts; these source-package records are not a complete
transitive bill of materials. The media skills' model terms are separate from
their inference libraries' software licenses.

Repository maintenance uses Python and Node standard libraries. CI additionally
runs the [GitHub checkout](https://github.com/actions/checkout),
[setup-python](https://github.com/actions/setup-python) and
[setup-node](https://github.com/actions/setup-node) actions and the separately
installed Claude Code validator. Their implementations are not bundled here;
their upstream terms apply to those tools.
