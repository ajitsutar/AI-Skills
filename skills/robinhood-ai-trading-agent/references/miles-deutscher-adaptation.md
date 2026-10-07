# Miles Deutscher Workflow — Codex/Robinhood Adaptation

## Source concepts incorporated

The local skill adapts the publicly described "AI Financial Advisor" workflow into a Robinhood-native architecture. The important ideas are:

1. **Investor one-pager as governing policy.** The agent should read a durable philosophy file before recommendations, rather than relying on a generic system prompt.
2. **Persistent context.** Maintain three conceptual layers: durable investment rules, current portfolio state, and durable conversation/decision history.
3. **Live portfolio + live research.** The portfolio broker is authoritative for positions/order state; market-data and research tools provide current external evidence.
4. **Morning brief.** Produce recurring portfolio-specific summaries that emphasize changes, risks, and decisions.
5. **Structured research.** Pull earnings/filings, compare multiple tickers, and run a discovery pass for less-followed names without automatically trading them.
6. **Scheduled loops.** Re-run the research process on a defined cadence, with execution remaining a separate permissioned step.
7. **Mobile notifications are optional.** A future Telegram or other messaging integration may deliver summaries, but secrets and bot tokens must remain in a proper secret store and not in the skill or journal.

## How this differs from a generic financial chatbot

The key advantage is not a particular model. It is that the model consistently receives the user's durable rules, current portfolio state, and prior decisions before making a recommendation.

## Robinhood-specific mapping

| Miles workflow concept | Robinhood/Codex implementation |
|---|---|
| Investor philosophy | `templates/investor-philosophy.md` copied to `investor-philosophy.md` |
| Live portfolio state | Official Robinhood Trading MCP |
| Persistent history | `trade-journal.md` + sanitized market-brief history |
| Live stock data | Robinhood quotes + optional external market-data MCPs |
| Earnings research | Public filings/earnings sources |
| Insider research | SEC/public filing sources |
| Morning brief | `templates/morning-brief.md` |
| Scheduled loops | Codex/runtime scheduler when available |
| Mobile alerts | Optional user-configured messaging integration |
| Execution | Official Robinhood Trading MCP with broker controls |

## Sources

- Miles Deutscher, "I turned Claude into my personal financial advisor (full system)" (attribution inherited from the supplied ZIP; it contains no exact original X link, so this attribution was not independently verified).
- Miles Deutscher, "AI Financial Advisor" workflow materials: https://milesdeutscher.com/assets/how-i-made-claude-do-the-work-of-5-people-full-guide-cbb1fbb5
- Miles Deutscher Finance, "I Replaced My Financial Advisor With Claude": publicly available workflow/build materials.

Do not copy personal account identifiers, API keys, chat IDs, tokens, or other secrets from any source into this skill.
