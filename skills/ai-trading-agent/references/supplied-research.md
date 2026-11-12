# Source-bound REIT research

For a retained original-source REIT corpus, run the source producer before drafting conclusions:

```text
python scripts/research_workflow.py source-run request.json --manifest ingress.json --manifest-sha256 EXTERNAL_PIN --source-root originals --private-output-dir new-output
python scripts/research_workflow.py source-verify new-output
```

The request is exactly `{"producer":"reit_sources","producer_request":REQUEST}` with optional `unverified_prose`. See [monetary operand binding](reit-reconciliation.md) and [property fractions](reit-sources.md) for REQUEST. The only supported producer is `reit_sources`; no cached result is accepted. Use the separately supplied original manifest pin, never create a new trust root around a later derived request.

The bridge retains the complete original inventory and unchanged request bytes, executes the producer, writes its fixed readable report, then replays original inputs and compares exact structured output and saved report bytes. Verification is read-only and works after copying the retained output tree. It pins all installed Python implementation files. Changed source, request, implementation, result, report or inventory is rejected. Output must be a new private directory; failures retain partial evidence and never overwrite an earlier run.

Fractional JSON values remain Decimal inputs. Normalized calculation hashes use exact finite Decimal strings; raw source/request byte hashes remain separate. Unknown bases, conflicts and conditional values retain their original status. A matching replay is not proof of authenticity, accounting scope beyond the supported schema, complete corpus interpretation or investment correctness. Extra prose is visibly unaudited; `whole_report_semantic_pass` stays false.

Use [final composition](final-report.md) to bind the exact delivered first response to one or more complete supported producer reports. [Original leaf lineage](original-source-lineage.md) remains available for explicit metadata identity checks.
