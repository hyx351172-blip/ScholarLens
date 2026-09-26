# Frontend acceptance — 2026-09-26

Scope: manual browser smoke test after answer-output guard; existing isolated KB
`E2E-v1-20260925-isolated`, one Attention paper, no upload or re-ingestion. Four
new questions were sent through the real frontend. This is not a held-out study.
ai-product-dev-pack was used to distinguish UI observations from offline tests.

## Results

| Check | Result | Observation |
| --- | --- | --- |
| Table 2 question | PASS | Answer gives EN-DE 28.4 / EN-FR 41.8; S4 contains the matching table |
| Unanswerable GPT-4/MMLU question | PASS | Fixed insufficient-evidence response; no added 2023 claim |
| Method question after abstention | PASS | Substantive Transformer explanation with source buttons, not incorrectly rejected |
| Conclusion question | PASS | Substantive conclusion with S1 citations, no malformed marker |
| Citation evidence panel | PASS | S4 shows Table 2, page 8 and logical-table chunk ID |
| PDF page link | PASS in Chrome | Exact observed link opens PDF at 8/15; table values visually match |
| In-app PDF rendering | FAIL in this browser | New tab opens, but document displays a broken-page icon |
| Waiting feedback | PARTIAL | Send control visibly shows a loading indicator and is disabled; no explicit retrieval/validation stage text |
| Cited-source count | FAIL | All 10 retrieved candidates labelled as cited, even on the uncited abstention |

Chrome became available during testing. Initial navigation automation timed out,
but the tab existed and its screenshot confirmed the PDF viewer at page 8/15,
including Table 2. The in-app failure is not evidence that the PDF endpoint fails.
The Chrome check opened the exact observed citation URL, rather than clicking
through a separate Chrome chat session.

## Automated checks

- Frontend `npm test`: 10 passed, zero skips/failures.
- Frontend `npm run build`: TypeScript and Vite succeeded, 16.60 seconds for Vite.
- Existing browser-data age warnings remain; dependencies were not changed.
- No application code was changed in this test turn; no commit/push/merge.

## Remaining work

Fix the misleading source label/count (separate cited evidence from retrieved
candidates), and consider explicit waiting text for buffered generation. A broader
10–20-question/multi-paper false-refusal evaluation remains unperformed; the three
answerable questions here do not establish a general rejection rate or entailment
accuracy. Services remain running for user testing.
