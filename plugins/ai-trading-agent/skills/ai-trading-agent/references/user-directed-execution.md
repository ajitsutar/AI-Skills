# User instructions and execution handoff

Requested broker actions use the host's actual tools under the current task's own
persistent execution policy. Each scheduled task has an independent policy bound
to its actual task ID; there is no global policy or mode inherited from another
task. New task policies start in `paper`. Read the task-specific file, verify its
binding to the actual task ID and re-read its current `mode` before acting:
`paper` means simulation only, `approval` requires approval for the particular order, and
`autonomous` permits in-scope actions under existing standing authority without
an additional per-order ask. The mode comes from the policy file, not an ordinary
prompt. Prompts supply the trading rules, scope and limits.

An explicit instruction for an exact one-shot order can itself provide that
order's approval in `approval` mode; a vague standing instruction is not approval
for unspecified future orders. It cannot override `paper`. An explicit user
request to change this task's policy is a configuration update; persist it and
read the result for the same task ID before applying the new mode. Do not silently
change modes for a trade or alter another task's policy. Task creation alone never
selects a live mode. Ask clarifying questions when task instructions are incomplete.

A recommendation-only request remains research. Research and pure payload
formatting require no execution-policy setup, grants, tickets, volatility clearance
or local order ledger. A formatted handoff is not a submission or a bypass of the
selected mode. Broker/platform permissions and order types remain external. See
[execution policy](execution-modes.md) and [execution handoff](execution-handoff.md)
for policy selection, payload handling and truthful outcome reporting.
