# Research runtime and host handoff contracts

Research helpers accept their documented JSON/CSV inputs and return analytical
results. Decimal amounts should retain their exact basis and units. Fictional
examples demonstrate calculations; they are not live prices or personal advice.
Input validation protects the meaning of a calculation, not execution permission.

`execution_handoff.handoff(payload)` and its JSON-stdin CLI preserve supplied
instructions/payload and advisory findings for the host. No policy, grant, ticket,
ledger, evidence threshold or execution readiness record is required. The helper
performs no broker call. CLI output redacts private account/authentication keys;
its in-memory result retains the supplied broker payload for the host.

Legacy guarded/user-directed/runtime interfaces are compatibility handoffs or
advisory research utilities. Historical databases are not altered to erase past
records and are not used to approve or veto new execution. The current package
has no local order-state machine or automatic broker retry/cancellation service.

The host uses actual tool schemas and existing user instructions, then reports
the broker/platform outcome. Research labels, risk diagnostics, recommended
allocations and hypothetical fills are not broker status. See
[execution-handoff.md](execution-handoff.md) and
[host-execution-integration.md](host-execution-integration.md).

## Task-bound persistent execution policy

Each scheduled task owns a separate persistent policy bound to its actual task
ID. There is no global execution policy and no inheritance from another task.
For host execution, use that task's private path and verify its task-ID binding
before reading `mode`: `paper`, `approval` or `autonomous`. New task policies start
in `paper`. Ordinary prompt text does not select or override that mode or replace
the actual task identity. Prompts supply trading rules, scope and limits; clarify
material missing intent without changing policy.

Research initialization does not create or select an execution policy, and the
pure handoff helper does not read or enforce one. Formatting a payload therefore
cannot establish that the host may submit it.

`scripts/execution_policy.py init PATH --task-id ID` initializes the specified
task's private policy in paper mode. A valid existing policy for the same task is
retained, not reset. Do not overwrite malformed or differently bound policies.
`scripts/execution_policy.py show PATH --task-id ID` reads that task's policy.
Only an explicit user request to change this task's mode permits
`scripts/execution_policy.py set PATH --task-id ID --mode MODE`. Preserve other
policy fields. These commands manage local configuration only: they do not connect
a broker, enable a scheduler, submit orders or change external permissions.
Re-read the same task's policy before each host action; do not cache an earlier
mode or choose another task's more permissive policy. Missing or invalid policy
never permits live dispatch.

In `paper`, keep actions simulated. In `approval`, obtain approval for the
particular order; an explicit exact one-shot instruction can supply it, but vague
standing authority cannot. In `autonomous`, carry out actions covered by the
user's current standing instructions without another skill-created per-order ask.
The host and broker's actual permission and confirmation requirements still apply.
See [execution policy](execution-modes.md) for task setup and conflict handling.

## Advisory diagnostic fields

`risk_engine.evaluate` returns `within_research_limits`, `diagnostic_status`,
`advisory_only: true` and `enforces_execution: false`. Status values are
`WITHIN_RESEARCH_LIMITS`, `ADVISORY_RISK_OBSERVATIONS` or
`SCENARIO_CASH_SHORTFALL`; none authorizes or refuses an order.

The optional interval-volatility helper returns `within_historical_range` (null
when unavailable), advisory observations and `observation_refresh_after`. The
refresh time describes when the observation ages, not an execution deadline.
Synthetic/interpolated baseline bars are excluded; a synthetic current bar cannot
establish a measured current move. Missing evidence remains an analytical unknown.
Both CLIs return successful structured advisory results without execution-stop
exit codes. Mathematical input errors still mean the requested calculation could
not be produced; they do not prevent a host handoff.

Some retained research results expose `execution_authorized: false` or
`validated_for_live: false`. These legacy fields mean that a calculation does not
grant authority or demonstrate live validation. They are not a denial of the
user's existing instruction and must not be interpreted as a host execution gate.
