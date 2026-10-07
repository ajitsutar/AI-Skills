# Personal Codex setup and operating procedure

This release targets a **supervised personal Codex session** that stays active
during trading, using broker quotes plus public filings/data, with optional paid
data configuration. It is not an unattended trading service.

## 1. Load and verify the complete skill

Extract the ZIP. Confirm VERSION and SKILL.md both say 3.1.0; run the tests using
the README environment commands. Open the entire folder in personal Codex or
explicitly ask that agent to install it. Current Codex documentation describes
user skills under `$HOME/.agents/skills`; choose an explicit destination and avoid
duplicate copies with the same skill name. See [Codex skills](https://learn.chatgpt.com/docs/build-skills).

Optional Windows installation from the extracted directory:

```powershell
python scripts/install_skill.py --destination (Join-Path $HOME '.agents\skills\robinhood-ai-trading-agent')
```

The installer refuses an existing destination. Preserve the old skill and runtime
before an upgrade; do not delete prior state to make installation succeed. A copied
skill does not include its virtual environment: retain/configure the Python path
used to run its helpers. On macOS/Linux use python3 and `.venv/bin/python`.

## 2. Initialize personal state

`personal_runtime.py init <new-runtime-directory>` creates draft `policy.json`,
`execution.db`, `supervised-session.db`, evidence/ and reports/ outside the skill.
It creates no grant or active session. `doctor` checks local prerequisites;
exit code 2 with draft/paper findings is expected initially. Never use test/demo
databases as personal account journals. Use one live journal per account alias
across sessions/modes; keep paper journals separate.

Discuss capital, horizon, cash needs, risk tolerance, permitted strategies/universe,
core targets, tax constraints, sources, hours, event rules and loss/exposure limits.
The example allocations and thresholds are editable illustrations, not suitable
for every investor. Save the concrete policy before asking for activation.

S&P 500 research membership and the trading allowlist are distinct. A scan cannot
silently broaden the approved trade universe. Change policy and reauthorize when
needed. `live_validated_setups=[]` intentionally prevents unreviewed live entries.

## 3. Connect the official broker in the personal account

Use Codex MCP settings and the official Streamable HTTP endpoint documented by
Robinhood: `https://agent.robinhood.com/mcp/trading`. The documented CLI equivalent is:

```text
codex mcp add robinhood-trading --url https://agent.robinhood.com/mcp/trading
```

Complete authentication through the broker/Codex managed flow. Do not paste,
extract, save or transfer passwords, cookies or tokens. Read
[Robinhood setup](https://robinhood.com/us/en/support/articles/agentic-trading-overview/)
and [Codex MCP](https://learn.chatgpt.com/docs/extend/mcp?surface=cli) for the current flow.
No connection is made by the installer or Python helpers.

Discover actual tools/schemas, eligible Agentic account, approval settings, read
permissions, quotes, order previews/status and advanced protection support. Start
with read-only evidence. Do not claim a sandbox exists unless the broker exposes
one. Document any required human approval in Robinhood; never switch it off
automatically. A live test is a real trade and needs explicit authorization.

## 4. Bind observed tools

Copy broker-capabilities.template.json into runtime evidence and populate it only
from the actual connection. Each operation needs its exact tool_name, input_schema,
schema_hash and bindings. See broker-integration.md. Capability snapshots expire
after one day; recheck more often on reconnect, schema changes or account changes.
Private routing identifiers stay in restricted host memory/storage, not the skill,
shared reports or research prompts. Host-managed OAuth remains in the connector.

The bridge builds a concrete request and hashes it. The host obtains the actual
broker review and binds the intended submit request to that review. Review and
submit schemas may differ: never hash the review call and assume it is the submit
call. Capture the interpreted economics/warnings and matching normalized order.

## 5. Start a supervised session and grant permission

After read-only reconciliation and setup, obtain actual human session authorization.
Record a unique owner/run ID, policy hash, session expiry and heartbeat interval
(default 60 seconds; configurable 5–300). Use SupervisedSession.start or the runtime
`session` command. It refuses takeover of an existing RUNNING lease. A lease is an
operational coordination record, not an identity or continuous-monitoring service.

Prepare the exact reviewed order or completed autonomous-mandate worksheet. The
host checks the actual human instruction, then records a policy-bound authorization.
Changing policy invalidates grants and the session hash. Never set approved flags
or use a unit-test grant to manufacture approval.

## 6. Active loop

1. Refresh positions, cash, restrictions, all orders, quotes and child protection.
   Reconcile manual activity and cumulative fills. Resolve unknown submissions first.
2. Run actions_needed; prioritize protection gaps, overdue exits and order conflicts.
   Refresh the heartbeat only after this health observation. If data or tools fail,
   stop entries, preserve protection, and hand off; do not let an empty timer certify health.
3. On completed bars, evaluate the registered setup. Perform event/news checks,
   current quotes, evidence and risk checks. Never use public delayed prices to submit.
4. Preview the exact order, attach readiness_inputs and actual human authorization,
   then call ExecutionLedger.claim. It reruns deterministic personal checks within
   the durable claim. Do not perform long research work after the preview/claim.
5. With may_submit_once=true, invoke the **same hashed actual MCP request once**.
   Recheck actual time, lease, grant, quote/review freshness and revocation immediately
   before dispatch. If these expired, do not send; record the unsent intent as
   REJECTED with evidence. Never silently regenerate arguments after the claim.
6. Record cumulative status/average fill; reconcile native children after each fill.
   ACK is not FILLED. Timeout/ambiguous matching becomes UNKNOWN, never a retry.
7. Repeat while the authorized session remains active. A 5-minute signal cadence
   does not justify ignoring positions for five minutes. Keep native protection
   active between observations; broker queues, model latency and disconnections
   can prevent timely human/session exits. Do not run a setup requiring guaranteed
   subsecond reaction or order-book execution on this host.

Before the entry cutoff, stop creating entries. Before each exit deadline, perform
the cancellation/reduction workflow early enough for broker acknowledgement and
fresh reconciliation. If a halt prevents exit, retain/report the position and
working protection; never declare it flat without broker evidence.

## 7. Cancellation, recovery and shutdown

Use `claim_cancel` for one observed target and schema-bound cancel request.
Cancel-entry permissions and cancel-protection-for-reduction permissions must be
explicit in a mandate; an exact action grant may also authorize cancellation.
Protective cancellation requires a reviewed reduction plan, acknowledgment of the
temporary protection gap and a named human handoff. Never cancel protection simply
because the strategy lost money or the session stopped.

Cancel ACK leaves its reservation unresolved. Query the actual target until
terminal; account for fills during the race. Refresh positions/orders and set
reconciled_through_cancellation only after that reconciliation. A replacement sell
requires its own fresh claim, may use only remaining owned shares, and cannot overlap
still-working stop/target quantities. Native atomic modification is preferable
when the observed broker tool supports the exact action; do not invent it.

On a lost heartbeat, do not silently revive the lease. Read the existing owner,
reconcile all broker state, obtain/verify user takeover authority, stop the old lease
with flat/protected/emergency handoff evidence, then start a new one. Revocation
prevents new actions but does not erase working broker orders. Manual broker action
may be necessary when permissions/connectivity cannot support automated reduction.

At shutdown, record flat or protected human handoff (or an explicit emergency).
`stop` does not flatten positions. Codex closure ends observation; no background
monitoring/notification is implied. Create scheduled tasks only when the user asks.

## Local command interface

`personal_runtime.py <operation> <runtime>` accepts JSON on stdin for risk,
authorize, revoke, claim, reconcile, claim-cancel, reconcile-cancel and session.
`init`, `doctor`, and `unresolved` need no JSON. This interface uses the actual
clock and accepts no caller-supplied now. All broker submissions remain explicit
host MCP calls. Importing the modules is also supported; tests inject a clock only
for deterministic fixtures. Do not persist private routing in a CLI input file.

Useful initial prompt in personal Codex:

> Load the complete Robinhood agent v3.1.0. Start in paper mode. Run doctor, inspect
> my authorized broker read capabilities, configure my investor policy and research
> universe, and show the concrete remaining activation checks. Do not place a trade.

## Release verification

The package includes PACKAGE-MANIFEST.json with SHA-256 hashes for every delivered
file except the manifest itself. VALIDATION-3.1.txt records the current tests/smokes; VALIDATION-3.0.txt is historical.
The outer ZIP has a separate SHA-256 file. A hash comparison detects a changed
copy; it does not authenticate an unknown publisher. Keep the downloaded original
and prior runtime backup when upgrading.
