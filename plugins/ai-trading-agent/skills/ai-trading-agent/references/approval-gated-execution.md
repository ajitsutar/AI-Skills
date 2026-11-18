# Approval policy and existing instructions

Each scheduled task has its own persistent policy bound to its actual task ID,
with a default mode of `paper`. Its saved mode selects `paper`, `approval` or
`autonomous`; there is no global or cross-task mode. Verify the binding and read
that task's current private file before host execution. A prompt supplies rules
and order instructions; it does not override the saved mode or the task binding.

In `approval`, require approval for the particular order. An explicit instruction
to place an exact one-shot order can itself provide that approval, so do not ask
again merely to satisfy a skill ritual. Vague standing authority does not approve
unspecified future orders. Preserve approved economics; a material change needs
applicable approval rather than being silently substituted.

In `paper`, simulate only, even when an ordinary prompt requests a real order.
In `autonomous`, use existing standing instructions for in-scope actions without
an extra skill-created per-order confirmation. An actual host/platform/broker
confirmation requirement applies in either live mode and cannot be bypassed.

Only an explicit user-requested change to this task's policy updates its saved
mode. Initializing a task retains a valid existing policy instead of resetting it.
Clarifying a task or its rules does not authorize a mode change. Research
diagnostics remain advisory and add no grants, tickets, strategy-promotion tests
or numerical execution thresholds. The pure handoff formatter neither approves
nor submits an order. See [execution policy](execution-modes.md) and
[execution handoff](execution-handoff.md).
