# AI Trading Agent Privacy Notice

## Scope

AI Trading Agent is a self-contained software skill published by Ajit Sutar in the AI-Skills repository. It contains instructions, reference material and invoked helpers. It does not include a publisher-operated backend, account system or background service. This notice describes the package; the AI host, connected services and websites have their own data practices.

## Data used for your requests

Depending on the task, the host and helpers may process your prompts, supplied documents, portfolio holdings, account observations, cash amounts, tax or transaction records, investment preferences, order instructions and research results. Provide only information needed for the task. The package can save source documents, calculation inputs, reports, logs, caches and task-specific execution policies in the output locations used by your host. These may contain personal financial information.

## Network requests and recipients

Requested research can send symbols, date ranges, URLs and other task-specific queries to public sources or providers you configure. SEC requests send the privately configured application/contact User-Agent to SEC. Optional provider helpers can read credentials from configured environment variables and send them as headers to the selected HTTPS provider. These credentials are not intended for public reports or support posts.

When permitted and authorized, native broker tools may process account information and order instructions and perform real investment transactions. Those operations use the host's connected broker capabilities and the broker's requirements. The package does not supply a broker OAuth client. Host processing, external research providers, websites and brokers are separate recipients governed by their own policies and your configuration.

## Publisher access and support

The publisher operates no separate service collecting users' prompts, portfolios or trading data. The package has no built-in publisher telemetry destination. Information you choose to post in the repository's public support issues is visible to the publisher and other readers. Do not post account identifiers, private financial records, passwords, API keys, SEC contact configuration or other sensitive information there.

## Retention and your controls

The package has no automatic retention deadline. Files it creates remain in the selected storage until you or the host remove them; host history, backups and external-provider records are controlled separately. Use your host's file and history controls to manage those copies. You can omit private inputs, use supplied offline files where supported, stop network workflows, remove optional provider configuration and revoke connected-service access through the relevant host or service. Removing the skill alone does not delete previously generated files or external records.

Public support posts are handled through GitHub's issue and account controls. Do not use public issues to request deletion of private financial data or publish that data to identify it. See GitHub's privacy statement for its handling of repository activity: https://docs.github.com/en/site-policy/privacy-policies/github-general-privacy-statement

## Questions

For questions about this package or this notice, use the support instructions in the AI-Skills repository: https://github.com/ajitsutar/AI-Skills/issues
