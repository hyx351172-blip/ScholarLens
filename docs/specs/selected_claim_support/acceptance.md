# Selected-anchor claim support gate (experimental)

Goal: add an offline-testable review boundary after claim-bound generation. An
anchor's provenance is not proof that it entails a claim. This component is NOT
wired into default chat and does not create a model client or read credentials.

- AC-3901: Reconstruct the original evidence catalog and answer binding. Each review packet contains exactly one claim and only its explicitly selected, exact source spans; no sibling claims, whole-source expansion, labels or factual history. Reject invalid input/structure and incomplete sentence units before review.
- AC-3902: Bind each decision to a fingerprint of the question, claim, selected spans, catalog mode and review policy. Strict bounded JSON must identify the exact claim and packet, use consistent verdict/reason enums, and cite only its own anchors. Duplicate keys, stale/cross-claim decisions, invented quotes and empty supported citations fail closed.
- AC-3903: Release the unchanged answer only when every claim has a valid supported decision. Unsupported, uncertain, missing and invalid reviews suppress the whole candidate, with distinct diagnostic statuses. Genuine insufficient/empty evidence is separate from reviewer failure. Never auto-expand citations, rewrite claims or label model review as human/semantic verification.
- AC-3904: An injected asynchronous reviewer has a finite per-answer invocation budget, bounded timeout, no orchestrator retries and stop-on-error behavior. Truncation/refusal/malformed output cannot pass. No built-in network/client/environment access; tests use fakes, not paid calls.
- AC-3905: Build a write-once development packet from all 22 saved live claims and both negative controls. Verify historical manifests and result hashes, preserve raw answers, and keep AI draft notes separate from inference with human verdicts null. No semantic accuracy or simulated-detection score is reported as measured model quality.
- AC-3906: RED/GREEN tests, full offline regression, traceability and diff checks pass. No edits to prior experiment files, production dispatcher/defaults, database or services; no automatic commit/push/merge.

Plan: contract tests RED → pure packet/decision/gate component → bounded injected
reviewer → GREEN → frozen historical development packet → regression/report.

Non-goals: automatic answer repair, rule-based semantic inference, paid review,
API rollout, retrieval changes, judge accuracy calibration or a held-out claim.

Tasks: T1 packet isolation; T2 strict decisions; T3 conservative gate and runner;
T4 frozen corpus and development report. Stop after offline acceptance. A later
real judge experiment needs a fresh bounded approval and human calibration.
