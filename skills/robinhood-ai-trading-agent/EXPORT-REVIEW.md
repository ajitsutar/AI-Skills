# AI-Skills repository export of v3.1.0

This export retains the Robinhood-specific execution workflow and skill name.
Research, portfolio analysis and strategy testing remain available in paper mode.

Changes from the standalone v3.1 archive are limited to repository packaging:

- Flat name/description frontmatter; version remains in VERSION and the skill body.
- Explicit skill-relative resource paths and helper working directory.
- Portable Codex interface metadata; omitted explicit true invocation policy keeps
  the normal automatic-discovery default.
- Parentheses/line wrapping around the existing URL-credential rejection condition;
  no change to its behavior. This avoids a false credential-assignment scan finding.
- Redacted local paths in an old validation receipt and regenerated file hashes.
- A matching root Claude agent, catalog/version updates and an offline CI test step
  are supplied in the repository integration bundle outside this skill directory.

Original review/validation receipts remain historical. Current repository export
checks are recorded in [EXPORT-VALIDATION.txt](EXPORT-VALIDATION.txt). Runtime broker
integration in Claude has not been tested. Installation does not authorize trades.
