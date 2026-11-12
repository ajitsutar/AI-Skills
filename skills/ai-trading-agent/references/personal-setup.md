# Personal setup

Install the whole skill folder and the Python runtime needed for the research
helpers you use. `scripts/research_preflight.py` reports package integrity and
dependencies. Ordinary research initialization creates evidence/report folders;
it does not create or choose an execution policy, schedule monitoring or trade.

Each host execution task, including every scheduled task, needs its own private
policy file bound to its stable task identity. There is no global execution policy.
Initialize new tasks with `execution_policy.py init PATH --task-id TASK_ID`; the
default is paper, and initialization retains an existing matching-task policy. Read
[execution modes](execution-modes.md) for `paper`, `approval` and `autonomous`.
The user alone authorizes changing the persisted mode. The model may apply an
explicit configuration request using `execution_policy.py set`; it must not
change the mode merely to satisfy a trading prompt. Prompts supply tasks and rules,
and the model can ask clarifying questions about material missing intent.

The minimal `templates/execution-policy.example.json` starts in paper mode. Copy
or initialize a separate private paper policy during task setup; never treat the bundled template as
an active account setting. Larger examples include fictional research inputs,
which are not default trading limits. Keep policies, backups and account evidence
outside the installed skill. The mode is read from the selected file on every run
and before actions, with the current task ID checked each time. Prompts cannot
silently override it. Changing one task does not change other tasks; copied
schedules get their own paper policy. Wrong-task or malformed files are errors.

No paid subscription is required for any tool category to use the skill.
Apply [source access](source-access.md) to optional user-provided accounts or
keys: use relevant free evidence first, and continue supported work when paid
access is absent or unavailable. Do not enroll, start a trial, upgrade or buy
access as part of research. Configure external tools through the host's supported settings. Robinhood's
[external-agent onboarding](https://robinhood.com/us/en/support/articles/agentic-trading-overview/)
describes its connection. Actual host/account availability and approvals remain
external. Installation or policy editing does not connect an account or start a job.

Use [execution-handoff.md](execution-handoff.md) for pure payload formatting,
[research-memory.md](research-memory.md) for saved research and
[maintaining-the-skill.md](maintaining-the-skill.md) for package updates.
