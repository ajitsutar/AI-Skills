# Research from an ordinary request

The user can ask, "Review this company's earnings and guidance, explain what
changed, and tell me the main risks." The assistant does the work: interpret the
request, collect permitted evidence, prepare internal inputs, invoke the relevant
helpers, write the complete answer, review it and correct identified errors. Do
not ask the user to author JSON, choose scripts or complete a technical review
form. Ask a focused factual question only when a material ambiguity cannot be
resolved from the request and available sources. Continue useful independent work.

This lane currently covers **earnings/guidance** and **event-driven U.S. stock
research**. Its named workflows guide the host assistant; the helper does not
claim to decode arbitrary natural-language intent. Research is on demand and
self-contained. Use the chosen host's native tools and permitted execution
environment. No local service, daemon, API key or model backend is required.

## What the assistant does

1. Retain the exact original request as UTF-8 bytes. Read all supplied context.
   Identify the issuer, actual question, relevant period, as-of cutoff, horizon,
   comparisons and source/access restrictions. List every material requested
   subtask, including qualitative topics that no calculator can answer.
2. Obtain the permitted evidence using host-native tools, starting with free
   primary sources. Prefer issuer releases, SEC filings and attached exhibits
   for issuer claims; retain both current and previous guidance where comparison
   is requested. An 8-K listing or exhibit link does not establish the contents
   of an unopened release. Open and retain the actual documents. Preserve source
   URLs, retrieval clocks, filing acceptance clocks, and period/basis/currency.
   Source identity and timestamps remain attributed unless independently checked.
3. Save only explicitly selected files in a scoped private run directory outside
   the installed skill. Never scan personal folders or read credentials, browser
   state or private runtime configuration. Keep original bytes separate from
   host-derived normalized inputs. Link each derived input to the originals and
   explain any unresolved mapping, unit or accounting-basis issue in the answer.
4. Call `research_session.start_session` with the exact request, named workflow,
   explicit source paths and assistant-authored material tasks. Each task quotes
   a unique literal span from the request. Keep the returned `session_sha256`
   outside the run and pass it on every subsequent phase; never replace it with
   a hash recomputed from an edited manifest. The helper retains exact input
   bytes and source hashes; those checks do not establish source authenticity or
   semantic completeness of the assistant's task inventory.
5. Prepare the evidence with `prepare_packet`. Select explicit filing documents
   for `filing_documents.extract_document`. Inspect actual passages, tables,
   qualifications and linked exhibits; parser matches are unreviewed candidates.
   Use the existing `research_workflow.execute` for relevant numerical work.
   Preserve each producer's failures, ambiguity and incompatible basis findings.
   Address every material subtask as supported, limited or unsupported, with
   evidence and reasons. These are assistant judgments; do not mark missing
   evidence supported to produce a favorable status. Retain `packet_sha256`.
6. Write the whole readable answer and structured companion. Lead with the
   research conclusion, then explain the evidence, changes, relevant calculations,
   alternative explanations and risks. Cite original sources and retained
   calculation results near claims. Separate issuer outlook, analyst scenarios
   and observed results. A useful limited answer explains what is known, what
   remains unresolved and what evidence would change the assessment. Do not
   substitute the packet, a checklist or a numerical annex for this answer.
7. Start the [review/correction cycle](research-review-cycle.md) through
   `research_session.start_review`, supplying the original session and packet
   pins. All exact original sources, filing extractions, numerical outputs and
   packet are frozen into review. Task-specific units remain; an additional
   reserved `session-whole-answer` unit binds the entire original request and
   every frozen source. The reviewer must inspect the complete request and both
   answer artifacts for omissions, factual errors, source limitations and
   consistency beyond the granular task roster.
8. Use native independent review when the host supports it, otherwise disclose
   native self-review. The assistant prepares the review document from actual
   findings. `freeze_draft`, `record_review` and `select_final` forward to the
   existing `answer_review.assess` revision chain. Carry its externally retained
   `head_sha256` across calls. Correct supported findings within the bounded
   correction budget; preserve the first answer, every review and revised answer.
9. Deliver the exact selected complete Markdown answer and structured companion,
   with the returned deterministic `delivery-notice.md` alongside them. The notice
   states self-review versus declared independent native review and carries open
   findings or missing review units. A limited or incomplete review can still
   yield a useful response; it must retain its actual status and limitations.
   The helpers never prove arbitrary prose correct, authenticate a reviewer or
   authorize an investment/broker action.

## Earnings and guidance

For "What changed in earnings and guidance?", collect the release/exhibit, relevant
financial statements and prior comparable outlook before stating a change.
Preserve revenue versus EPS, fiscal versus calendar periods, GAAP versus adjusted
figures, continuing operations, diluted share basis and currency. A supplied
earnings estimate can support an explicitly labeled multiple through the existing
`analyst.earnings_basis`; it does not establish fair value. Use other existing
supported producers when the question calls for them. If no existing producer
covers a material computation, state that gap and the scope of any separately
checked host calculation. Do not invent an unrelated calculation to make the
workflow look complete.

For example, in the fictional end-to-end regression, the host retains an issuer
8-K saying revenue was USD 110 million versus USD 100 million and FY2030 adjusted
diluted EPS guidance was USD 2.00, plus a USD 50 quote. The host prepares the
guidance/quote input, the existing producer calculates 25x, and the complete answer
explains the reported revenue, guidance basis, forward-looking nature and supply
constraints. The review binds the actual answer and all retained evidence. The
test demonstrates the integrated path, not the accuracy of real issuer research.

## Event-driven research

For "Explain the merger and closing risk", collect the actual announcement,
agreement and applicable 8-K exhibits, relevant ownership disclosures or regulatory
documents, and any permitted dated market data required by the request. Distinguish
announcement time, filing acceptance, information availability and price clocks.
Identify stated consideration, conditions, financing, approvals, termination terms
and the difference between an announced event and a completed event. Use retained
institutional/market/evidence producers when their scope fits. A price move does
not establish causation; a 13D/G percentage is not a current tradable position or
proof of an activist intent. See [filing content](filing-documents.md).

If no agreement or announcement is available, deliver an explicitly limited
answer explaining that terms and closing likelihood cannot be established, with
the concrete missing documents. Keep that subtask `unsupported` and its review
finding visible; do not fabricate event probabilities or a recommendation.

## Host-facing API

The following fields are internal assistant work, never a user form:

| Function | Inputs and retained result |
| --- | --- |
| `start_session(root, request_bytes, workflow=..., sources=..., tasks=..., as_of=...)` | New private directory; exact `request.txt`, each `sources/<id>.bin`, host plan and immutable session manifest. Returns `{session, session_sha256}`. Supported workflow names are `earnings_guidance` and `event_research`. |
| `prepare_packet(root, expected_session_sha256=..., dispositions=..., filings=..., calculation=...)` | Explicit filing jobs and existing workbench request; complete material-task dispositions. Returns `{packet, packet_sha256}` and preserves actual producer diagnostics. No automatic network access. |
| `start_review(root, expected_session_sha256=..., expected_packet_sha256=..., adopted_at=..., max_corrections=2)` | Freezes original sources plus generated evidence and creates the revision protocol. Returns the initial review head and protocol reference. |
| `freeze_draft`, `record_review`, `select_final` | Require `expected_session_sha256` and revision `expected_head_sha256`; use [revision API](research-review-cycle.md). Final refs are relative to `root/review/`. Deliver its exact answer pair and notice. |

Source specs are `{id, path, role, origin}` with optional metadata and
`derived_from` source IDs; origin is `supplied`, `host_collected` or `host_derived`.
Derived inputs require explicit lineage. Tasks are
`{id, requirement, request_excerpt, required_source_ids}`. Dispositions are
`{id, status, reason, evidence_ids}` and must include exactly every task. Do not
use `session-` source IDs or the reserved `session-whole-answer` task ID.

For a PDF or other binary original, retain the original bytes and have the host's
native document tools inspect it. Retain a separate nonempty UTF-8 extraction
with page/table locators, and set the original source's
`metadata.readable_projection_source_id` to that explicit source ID. This is a
declared mapping, not proof of extraction fidelity; record `derived_from` on the
projection as appropriate. The linked ID must be a different, explicitly retained
readable source. Text-span review cannot represent inspection of binary bytes.
The review corpus therefore uses an unmistakable **provenance-only manifest** for
that binary source ID, containing its unchanged original filename, SHA-256, byte
length, retained session member, linked extraction and native-inspection limits.
Any review spans for that ID refer only to provenance metadata. The original
binary remains unchanged in the pinned session, and every task requiring it also
requires the linked readable extraction. The whole-answer unit requires both.

Without a linked readable extraction, research can still produce an explicitly
limited answer. Affected units, including whole-answer coverage, must remain
unsupported or unreviewed; reviewing provenance metadata alone cannot yield a
`REVIEWED_DELIVERY`. Keep the missing-content limitation in the answer and notice.
Neither a linked extraction nor a native review declaration certifies that all
pages, visual details or tables were correctly interpreted.

A calculation is an existing full workbench document. Its `contract.prompt` must
equal the unchanged original request text, including trailing newlines. Every job
uses `inputs_source` with path `<retained-source-id>.bin`, exact SHA-256 and the
selected JSON object pointer. The bridge permits no arbitrary filesystem input
paths. Normalized input mapping is still assistant-authored and must be reviewed
against the raw sources. Source binding and numerical replay do not validate
that mapping semantically.

CLI `start`, `prepare` and `start-review` accept explicit local files for internal
host plans; the host writes them. Draft/review/final are available through the
session Python API. For text-only sessions the generic revision helper's CLI can
also perform those stages; it does not enforce session-specific binary evidence
limitations. Sessions with binary originals must use the session `record_review`
and `select_final` routes, which retain missing-projection limitations at both
review and final selection. No user needs to see these internal
schemas. Failed start/packet attempts retain failure receipts and original inputs;
do not overwrite or silently retry. Use a new scoped run for a genuinely new
attempt, retaining the failed run and explaining any resulting limitation.

If the host cannot execute bundled Python, it can still collect permitted sources,
author and natively review the answer using these instructions. Explicitly state
that helper extraction, numerical replay and retained revision receipts were not
performed; never invent tool success or imply identical host capabilities.

## Ordinary example prompts

- "Review Acme's latest earnings and guidance. What changed from the prior
  outlook, what does it imply for valuation, and what are the main risks?"
- "Read the attached 8-K and earnings release. Explain the results and distinguish
  GAAP figures from the adjusted guidance. Use only these files."
- "Explain this announced merger, its key terms and closing risks. Use free
  primary sources and tell me what remains uncertain."
- "Assess the event described in this 13D and 8-K. Separate what the documents
  actually say from possible investment interpretations, then review your answer."
