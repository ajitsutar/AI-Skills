# Qualify a buyer's research workflow

Use this guide to turn a proposed purchase into a bounded evaluation: what is
being supplied, which desk tasks it covers, what it costs, and which evidence the
buyer still needs. Copy [the worksheet](../templates/buyer-qualification.json)
outside the skill before filling it. Keep buyer evidence, commercial terms,
account details and completed worksheets private.

The worksheet is a planning aid, not an input to an assessor or an approval
record. Its nulls mean unprovided; empty arrays mean no entries have been recorded.
Neither means zero, permission, complete coverage or a successful exercise.
There is no automatic purchase or rollout decision. The firm decides whether
its actual evidence and terms support its intended use.

## Start with the purchased deliverable and claim

Specify whether the offering is a maintained skill, integration, deployment
service, support, or an explicit combination. Record price, billing/usage basis,
maintenance scope, source/model-change responsibilities, support hours and
response commitments, exclusions, termination, and data/output export terms.
Retain the actual quote and terms, their dates and hashes. The included MIT
license permits use under its terms; it does not supply a paid service, support
commitment or warranty. No paid vendor or subscription is required by this guide.

Qualify the buyer's chosen host and its existing controls. This self-contained
skill does not require a locally hosted backend, server or background service.
Bundled helpers run on demand where the host supports them; unsupported execution
or tooling remains an explicit gap. Do not deploy a backend without an explicit
user request.

Name the actual host, package/runtime identities, permitted model/tool routes,
assets, desk tasks, data classification and report/review destinations. State
unsupported tasks and the escalation or abstention route. Separate these claims:

- **Automated quality:** compare prespecified error/check outcomes; do not call
  proxy durations analyst time saved.
- **Human productivity:** use actual human work, review and correction effort
  under an adopted comparison protocol, retaining measurement limitations.
- **Alpha or strategy selection:** requires separate investment evidence. A
  research-productivity purchase need not make this claim.
- **Execution:** requires the actual host/broker and operational authority.
  A research-only purchase can exclude execution entirely.

Do not treat these as interchangeable. Existing
[institutional acceptance](institutional-acceptance.md) supports one prespecified
benefit per value input. Keep distinct comparison protocols and results for
different benefits or comparators instead of pooling their observations.

## Reuse the native evidence workflows

| Buyer question | Retained native input and operation | What remains external |
|---|---|---|
| Does the actual answer cover the original task? | [Final report](final-report.md) / [complete delivery](source-access.md) native replay; optional [answer review](answer-review.md) for itemized declared reviewer findings bound to the delivered artifact, request and sources | Native consistency and declared semantic judgments remain distinct; neither authenticates source truth or reviewer competence |
| Is the supplied deployment evidence coherent? | `institutional_acceptance.assess(document, evidence_root)`; retain the original inputs for every component | Whether supplied observations and declarations are authentic and sufficient |
| Are the host/mode/assets supported in the observed scope? | [Platform readiness](platform-readiness.md), `platform_readiness.assess(document)` | Actual connected host capability, permissions and operational test execution |
| Is the requested data grid available by its cutoffs? | [Source strategy readiness](quant-data-contracts.md), `source_strategy_readiness.assess(document)` | Complete history, authentic source facts, corporate-action correctness and delivery service levels |
| Is source use reviewed? | [Rights inventory](release-acceptance.md), `release_acceptance.rights_inventory(document)` | Entitlement, interpretation of terms and the additional use dimensions below |
| Is a registered comparison actually comparable? | [Review packets](review-packet.md) and institutional acceptance's value component | Honest clocks, actual human effort, causal savings and economic benefit |
| Are controls and recovery exercises retained? | Institutional acceptance's governance/operations components; [research operations](research-operations.md) journals/recovery | Actual host enforcement and a staffed operating/support service |

These are the existing exact schemas. The worksheet does not replace them or add
fields to them. Supply original assessor inputs and pinned artifacts, rather than
copying a favorable status from an unrelated deployment. Keep the native status,
scope, cutoff, coverage, failures and qualifications with any buyer summary.
`DECLARED_SCOPE_EVIDENCE_COMPLETE` describes a catalog; its value criterion can
still be negative. It is not institutional readiness or purchase approval.

For a runnable offline starting point, run these from the standalone skill folder:

```text
python scripts/platform_readiness.py examples/platform-readiness.json --output ../PRIVATE-NEW-platform-evidence.json
python scripts/release_acceptance.py rights templates/source-rights-inventory.json
```

Choose an unused explicit private output path. The bundled platform example has
unknown deployment identities and no observed host evidence; it stays
`UNVERIFIED`. The rights template has unknown permissions and stays unresolved.
These commands make no host, broker or source calls. Replace their example inputs
with the buyer's retained originals to perform an assessment; running the examples
does not qualify that buyer. Follow the institutional acceptance guide to bind
the full deployment and review/value protocols once those originals exist.

## Compare value and total cost over the same scope

Before outcomes, adopt representative tasks, the complete task/claim-unit roster,
material-error tolerance, escalation rules, benefit criterion and common inputs.
Name the current workflow and the agreed alternative, which may be a general AI
assistant or an internal implementation. Compare the assisted workflow to each
separately under a frozen matched-input protocol. Preserve negative results,
missing tasks and unreviewed units. Do not select only successful demonstrations.
Use the existing packet comparison only when the intervention fits its allowed
arms; otherwise adopt a suitable separate protocol. Preserve the packet's
source-only/assisted input separation and keep evaluator criteria and other
participants' answers out of participant inputs.

Institutional acceptance already accounts for work, review and correction time,
per-arm cost and complete registered review-unit coverage. Use those results;
do not count satisfied checks as attempts or missing durations as zero. A single
aggregate `cost_usd` value does not document the offering's whole cost basis.

For each option, reconcile the worksheet's cost lines over one explicit horizon,
currency and task volume: purchased service/license, onboarding/integration,
model, data, compute, support/maintenance, and human work/review/correction.
Identify one-time versus recurring/per-task charges, any minimum commitments,
shared allocations and cost overlaps. Mark each amount measured, quoted, assumed
or unknown and retain its evidence. Record an explicit reason for any category
that is inapplicable. Unknown price, currency, FX, usage or labor-rate inputs stay
unknown. Do not infer a conversion or silently annualize a short observation.

Report observed comparison metrics separately from commercial scenarios. Applying
an assumed task volume or labor rate to declared time differences is a scenario,
not measured realized savings. Avoid counting labor already included in a supplied
cost metric again. Report the full costs and error/review burden with any net-value
claim; CI, model agreement, synthetic examples and proxy scores cannot establish it.

## Qualify the needed data and uses

Specify the universe/assets, fields, units/currencies, history, decision cutoffs,
maximum delivery delay, stale-data policy and correction expectations. Record the
delivery observations and denominator: what was expected, delivered, missing,
stale, revised and reconciled independently. Distinguish source publication,
retrieval, decision and revision clocks. A current capture is not a service-level
record or a complete historical archive.

For historical claims retain point-in-time membership, delistings, identity
changes, availability/revision clocks and corporate-action treatment. Reconcile
sample original records independently and retain discrepancies. The native
observed/scenario grid remains the source for its own coverage result.

For every used source, map its exact identity to the existing rights row and
retain the reviewed terms/entitlement evidence. Separately review retrieval,
retention/deletion, commercial internal use, model processing and redistribution
as applicable, including permitted model routes and retained outputs/logs.
The existing inventory's broad `intended_use` categories and declared retention
days do not interpret all of these terms. A dashboard login or a populated rights
row does not grant them. A suitable free or buyer-supplied source is acceptable;
an unavailable paid adapter is not automatically a blocker for a supported task.

## Demonstrate the actual deployment and service

Assign a firm/deployment owner and support owner. Reuse current firm controls
where appropriate: identity/access separation, approved model/outbound routes,
classification, retention/deletion, and confidential-data negative exercises.
Bind the retained results to the actual host/package/runtime and model routes;
state expected versus observed behavior, time, exceptions and reviewer limits.
Test authorized synthetic canaries instead of copying real secrets into examples.
The skill does not install identity management, enforce routing, supply DLP,
authenticate reviewers, or prove host security from hashes.

Agree response/freshness expectations and recovery objectives appropriate to the
purchased service. Observe restart, interrupted acquisition, duplicate processing,
rollback and restoration on that deployment, retaining failures and recovery
results. State support coverage, escalation, backup/restore ownership, and the
change events that require bounded requalification: package/runtime/model route,
source/schema/terms, permissions or workflow changes. A passing local journal or
another host's exercise does not establish unattended reliability here.

## Keep conditional investment and execution evidence separate

If alpha or strategy selection is sold, adopt a separately authorized protocol
covering selection/trial inventory, benchmark, untouched evaluation, uncertainty,
regimes, spread/fees/impact/delay/financing/borrow and capacity sensitivity. Preserve
failures, exclusions and assumed versus observed costs. Existing methodology and
simulated replay are not observed profitable execution. This guide does not start
a prospective study or restart a cancelled study or its reporting automations.

If execution is procured, freeze instruments, accounts, order/session variants and
authority; retain the actual connected schemas and submission, acknowledgment,
partial/full fill, rejection, unknown-state, cancellation and reconciliation
evidence, including duplicate/recovery behavior. Use the platform catalog for its
bounded asset/mode assessment and record additional desk-specific lifecycle needs.
Formatting an order is not transport or a fill. No worksheet, catalog status or
buyer decision authorizes a live order or account action.

Finish with a dated buyer decision: accepted scope and terms, unresolved items,
owners, explicit exclusions and requalification triggers. Link the actual retained
evidence and record reviewer limits. A scoped decision does not establish
universal bank/hedge-fund suitability.
