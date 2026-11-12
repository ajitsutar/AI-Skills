# Final REIT report artifact

Compose a saved response from complete REIT source reports, then verify the exact file delivered to the user:

```text
python scripts/research_workflow.py final-compose plan.json --manifest ingress.json --manifest-sha256 EXTERNAL_PIN --source-root originals --private-output-dir new-final
python scripts/research_workflow.py final-verify new-final --final-response new-final/first-response.md
```

The plan has `sections` (one to eight) and optional `unverified_prose`. Each section is exactly `{"kind":"source_report","producer":"reit_sources","request":REQUEST}`. REQUEST follows [REIT operand binding](reit-reconciliation.md) and [property facts](reit-sources.md). No caller-produced successful output, accounting-claim section, terminal-objective section or other producer is accepted.

Composition retains all original corpus bytes, executes each [source producer](supplied-research.md), replays its output and full generated report, and writes `first-response.md`, `audit.json` and `receipt.json`. Verify checks exact final bytes, section membership, source/result/request integrity and the installed implementation. A copied output tree can replay from its retained originals without the earlier host path. Existing output directories are never overwritten; failed partial output remains available for review.

The source report preserves conditional comparisons, original property facts and unresolved scope. `unverified_prose`, when necessary, is visibly labeled and recorded by exact byte spans; its presence yields `PARTIAL_UNAUDITED_PROSE`. Review that prose independently. `whole_report_semantic_pass`, `source_authenticity_verified` and `request_completeness_verified` remain false. A replay receipt does not certify a full investment answer or make an unsupported claim true. Deliver the unchanged saved response; later edits require fresh composition and verification.
