# Third-party notices

The bundled [MIT license](LICENSE) covers repository-maintained skill material.
It does not relicense external runtimes, services or content retrieved during use.
[Provenance](PROVENANCE.md) records the reviewed history and remaining limitations.

## External runtimes and interfaces

- **Node.js:** the helpers use built-in modules such as `fs`, `path`, `os`,
  `assert` and `vm`, plus local helper modules. No npm dependency or Node runtime
  is bundled. Node.js and its included components retain their
  [upstream license notices](https://github.com/nodejs/node/blob/main/LICENSE).
- **Browser DOM and Chrome:** extraction helpers call browser-provided DOM and
  URL interfaces. Chrome is an external prerequisite for the documented browser
  transport; its implementation is not included in this package.
- **macOS and AppleScript:** the optional transport invokes `osascript` and
  Chrome's AppleScript interface on macOS. Apple's runtime and Chrome's scripting
  implementation are external, not redistributed by this skill.

These interface dependencies are not claims that their source code was copied.
No separately licensed third-party code distribution, model weights or assets
were identified in the reviewed package.

## Service and content rights

LinkedIn, Slack and other destinations retain their own service terms and access
requirements. The skill's license grants no access rights or permission to bypass
them. Authors and publishers retain rights in posts, articles, reports and private
messages processed during use. Preserve source links and any applicable content
notices; permission to use this skill is not permission to republish that content.
