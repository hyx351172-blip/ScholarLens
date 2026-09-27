# SciFact verifier smoke baseline v1

Scope: offline adapter and scorer for the existing selected-claim verifier.
Select 10 SUPPORT, 10 CONTRADICT and 10 NOT_ENOUGH_INFO claim–abstract pairs
from the local official **dev** split before obtaining any model predictions.
This is an oracle-candidate, full-abstract classification smoke test, not the
official SciFact leaderboard, an untouched test set or end-to-end RAG accuracy.
No generation, retrieval, PDF parsing, paid requests or production changes.

- AC-4101: Validate unique claim/document IDs, annotated label consistency, corpus references and rationale indices. Reject malformed data. Use evidence documents for positive/contradiction pairs, and cited documents of evidence-empty claims for NEI; never substitute empty text for NEI.
- AC-4102: Deterministically sample 10 pairs per class, with unique claim IDs, normalized claims and document IDs. Preserve original claims and the entire joined abstract; log all eligibility exclusions and deduplication. Fail if a balanced sample cannot be formed; do not truncate or relax the existing eight-anchor contract.
- AC-4103: Build fixed_v1 packets with all abstract anchors using the unchanged verifier policy. Inference requests contain neither gold labels nor rationale indices. Keep alternative gold rationale sets and null project-human review fields separately. Freeze inputs, protocol, code, historical integrity and requests using hashes and write-once artifacts.
- AC-4104: Score strict packet-bound raw decisions: supported/entailed → SUPPORT, unsupported/contradicted → CONTRADICT, unsupported/not_in_evidence → NEI. Uncertain is an abstention, never an automatic correct NEI. Keep invalid, missing and failed responses in the full sample denominator. Reject duplicate/unknown result keys or mismatched request hashes.
- AC-4105: Report per-class and macro F1, full-denominator accuracy, confusion including uncertain/error/missing, false acceptance of negatives and conservative blocking of positives. No results means null model metrics, not fabricated accuracy. This adapter does not score official rationale selection or retrieval.
- AC-4106: Offline RED/GREEN tests, regression, traceability and historical hash checks pass. Do not load credentials or call a model. Report sampling/representation limits and request separate finite paid-call authorization for a later live run. No automatic commits, pushes or default activation.

Plan: contract tests (RED) → adapter/scorer (GREEN) → real dev-only preparation
→ offline report. Stop before any external model request. Results of this smoke
set must not later be presented as held-out results after tuning on it.
