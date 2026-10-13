# Host and broker integration boundary

The skill's executable handoff is `scripts/execution_handoff.py`: a pure formatter,
not a transport or approval service. It has no execution gates. Legacy execution
entry points are compatibility handoffs and do not reinstate local grant, ticket,
policy, session, funding, volatility or strategy checks.

The host owns its authenticated broker tools and external platform requirements.
Use their real schemas and preserve the user's instructions. No host executable
hash contract, local policy or one-use dispatch ticket is required by this skill.
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
