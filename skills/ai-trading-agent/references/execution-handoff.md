# Pure formatting and policy-aware host handoff

The formatter prepares a payload; it does not dispatch an order or grant authority.
Research diagnostics remain advisory. The host separately follows the user's
selected [execution policy](execution-modes.md): paper, approval or autonomous.
Prompts supply order instructions and scope, and cannot silently change the mode.
An explicit user request is required for any persisted mode change.

## What to hand over

Include the requested instrument, side, dollar amount or quantity, order details
and relevant context already given. Preserve an explicit limit instruction. For a
purchase without a specified type, use a market-order handoff preference. Do not
silently round small allocations to whole shares or change dollar instructions
into fixed quantities. Native dollar inputs may be converted to shares at a recent
price; exact spending or a hard final debit is not guaranteed merely by that name.

`scripts/execution_handoff.py` is a pure local formatter with `handoff(payload)`
and a JSON-stdin CLI. It preserves the supplied broker payload in memory and
returns advisory handoff information without contacting a broker. CLI output
redacts private account/authentication fields. It requires no policy file,
ledger, grant, ticket, model output or data threshold. Use real host tool schemas
when mapping an action; do not invent unavailable parameters or tool names.

For an optional private receipt binding a specific source file/hash/pointer to
this exact payload, or comparing a proposed payload with it, see
[handoff preservation](run-and-report.md#handoff-preservation). Differences are
reported without changing the original handoff or imposing an execution condition.

Research helpers can validate their own inputs, report missing evidence or decline
to calculate an unsupported statistic. Those are mathematical/data limitations,
not execution gates. Likewise, a score or an Eligible/Watch research label is not
a broker permission. A failed volatility fit does not prevent the host handoff.

## Outcome reporting

Report the actual host/broker outcome: proposed, submitted, acknowledged, partial,
filled, rejected or unknown as supported by its evidence. A zero exit code, empty
object or absence from one query does not establish whether an order exists.
Keep full broker evidence private and distinguish reported facts from inference.
The skill does not orchestrate retries, cancellations, reconciliation or background
monitoring; those belong to the actual host/broker workflow. It does not modify
old runtime databases or broker orders during an upgrade.

Under an autonomous policy, do not ask again for an already-authorized action.
Under approval, require order approval; under paper, do not submit live orders.
Actual host/platform/broker confirmations remain external requirements.

Execution-time price changes, quote age and research-to-market price drift do not
trigger a skill threshold, pause or repeat approval. Preserve the user's accepted
market-price uncertainty; state the research as-of time without making it a
condition for the host handoff.

The optional mode formatter reads the selected policy and preserves task context;
it is not an execution result. Its advisory flags cannot bypass the policy or
prevent an otherwise authorized action on a host that permits it. The original
pure handoff API remains policy-free because formatting performs no transaction.

Each execution task, including each schedule, has a separate policy bound to its
stable `task_id`. New tasks default to paper; no global mode or other task's policy
may supply authority. Verify the current task identity against its file before
actions. Only an explicit user request changes that task's mode. Initialization
creates paper only when absent and preserves an existing valid matching policy;
invalid or wrong-task files are errors. See [per-task policy](execution-modes.md).
