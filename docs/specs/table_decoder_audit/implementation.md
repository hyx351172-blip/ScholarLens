# Table decoder length audit v8

## Scope

Continue the v7 length-ceiling investigation on the same three frozen crops.
Capture real pre-decoding tensors and EOS, then (only when the original actually
hits its limit without EOS) compare an isolated 1000-step graph variant against
the original 500-step graph. This is a local structure-only experiment: no OCR
text accuracy claim, no gold in inference, no production parser/database changes,
no paid calls, no changes to downloaded model files or old evidence.

## Acceptance criteria

- AC-1101: Inspect the pinned static graph, not merely its YAML. A controlled
  clone changes exactly the loop bound and three capacity constants together;
  unrecognized graphs, inconsistent dimensions and reused outputs are rejected.
  Original files and copied weights have verified SHA-256 identities.
- AC-1102: Save actual structure probabilities, token IDs, vocabulary, EOS
  position, allocated limit and decoded HTML. Distinguish natural EOS, hard-limit
  exhaustion and unknown termination. Pipeline completion is not EOS evidence.
- AC-1103: Validate frozen input hashes and paths before inference, use fresh
  outputs, at most three crops per arm, CPU-only explicit local models, subprocess
  deadlines and no retries. Journal attempts/failures. Never read gold in inference.
- AC-1104: Compare identical inputs/preprocessing/weights and predicted prefix;
  keep strict HTML/span/grid validation unchanged. Report all failures, runtime
  and the early-EOS control. No automatic candidate promotion or HTML repair.
- AC-1105: Unit/negative tests plus real local model seam, immutable-input checks,
  reproducible commands and an honest report that separates truncation from layout
  errors. If applicable, score structure only in a separate gold-reading stage.

## Tasks / routing

1. RED: tensor termination, exact graph edit, path/hash and validity tests.
2. GREEN: audit, guarded clone, instrumented local runner and paired summary.
3. Run original first; conditional extended experiment; inspect raw evidence.
4. Regressions, traceability, integrity verification and report.

CLI-only backend unit/contract + real local-model slice; no UI or DB E2E change.
The modified graph is experimental, not an official re-exported/trained model.
No commit, push, deployment, full-dataset expansion or additional models here.

## Completed validation

- [x] RED/GREEN unit tests; two real PIR dialect/schema mismatches reproduced and fixed.
- [x] Three original and three extended structure inferences on identical frozen crops.
- [x] Two actual length-limit failures confirmed; both extended outputs reach EOS.
- [x] All prefixes identical; early-EOS control unchanged; strict-valid outputs 0/3 → 2/3.
- [x] Separate official structure-only scoring; v4 baseline reproduced.
- [x] 18 new tests; total 245 passed, 0 failures/errors/skips; isolated 15 tests passed.
- [x] Actual NPZ tensors re-inspected; four graph leaf changes verified; all 15 frozen
  source/crop/baseline artifacts and cached models unchanged.
- [x] Five ACs pass the bidirectional traceability gate; report and commands provided.

No automatic production promotion. Structure TEDS improves on two tables, but OCR
content/cell alignment remains untested. Full evidence and limitations are in
`docs/evaluation/omnidocbench-table-decoder-v8.md`.
