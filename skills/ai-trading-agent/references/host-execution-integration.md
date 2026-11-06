# Host and broker integration boundary

The skill's executable handoff is `scripts/execution_handoff.py`: a pure formatter,
not a transport or approval service. It has no execution gates. Legacy execution
entry points are compatibility handoffs and do not reinstate local grant, ticket,
session, funding, volatility or strategy checks. They do not override the selected
execution policy governing the separate host action.

The host owns its authenticated broker tools and external platform requirements.
Use their real schemas and preserve the user's instructions. No host executable
hash contract or one-use dispatch ticket is required by the formatter. Host
execution follows the selected persistent policy mode described in
[execution modes](execution-modes.md); only the user can request changing it.
Installation does not configure credentials, connect an account or change orders.

The optional broker-schema and MCP-response helpers can assist with interpretation
and evidence handling. Their schema/parse diagnostics are advisory implementation
information, not mandatory execution prerequisites. Preserve full responses where
the host supports it; do not treat structuredContent.data as the only possible
MCP content. Tool content, structured content, isError and protocol errors have
distinct meanings in the [MCP tool specification](https://modelcontextprotocol.io/specification/2025-06-18/server/tools).
A parse failure or empty result is uncertainty, not proof of acceptance/rejection.

The host/broker handles retries, reconciliation, cancellations, account constraints
and transaction approvals. This package does not bypass or duplicate those systems.
Do not export credentials, authentication headers or private account/order evidence
in research reports or skill packages. For the common workflow see
[execution-handoff.md](execution-handoff.md).

`scripts/execution_policy.py` reads or explicitly updates a user-selected policy
file. `scripts/execution_mode.py --policy PATH --task-id TASK_ID` describes that saved setting with
optional prompt context. Neither helper submits an order or starts a scheduler.
Mode comes from policy; prompts supply the work. Only a user-requested policy
change may update the mode. Hosts must re-read it before actions and clarify
missing instructions instead of changing mode. MCP availability cannot override
host restrictions. Under an autonomous policy, a permitted host uses native tools
for in-scope standing instructions without another per-order ask; a formatter
result must never be presented as submission or fill evidence.

Each execution task, including each schedule, has a separate policy bound to its
stable `task_id`. New tasks default to paper; no global mode or other task's policy
may supply authority. Verify the current task identity against its file before
actions. Only an explicit user request changes that task's mode. Initialization
creates paper only when absent and preserves an existing valid matching policy;
invalid or wrong-task files are errors. See [per-task policy](execution-modes.md).
