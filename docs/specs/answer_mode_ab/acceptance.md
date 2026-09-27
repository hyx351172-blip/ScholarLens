# Answer-mode paired development experiment v1

Scope: compare legacy vs claim_bound with frozen retrieved documents, not E2E,
held-out evaluation or an automatic production promotion. No production changes.

- AC-3501: Freeze 12 predetermined development cases and exact ordered sources from the existing scope-corrected run. Separate expectation labels from model inputs. Nine answerable, two unanswerable, one empty case; both modes use identical evidence.
- AC-3502: Capture and execute production generation prompts/guards through ChatService.generate_answer. Model, temperature 0 and max_tokens 2000 match across arms; request format differs as intended. Use sequential counterbalanced order, zero retries, 60-second SDK timeout and 90-second total-call deadline. Empty evidence performs zero generation calls. No retrieval/planning/judge calls.
- AC-3503: Live run requires explicit approval and a fixed maximum of 22 requests. Freeze code/input/request hashes. Write an attempt before every request and refuse unresolved attempts, input drift or a changed protocol. Never overwrite completed output or automatically retry failures.
- AC-3504: Preserve raw response content, finish reason, token usage, delivered answer, guard status, binding metadata and generation latency. Sanitize exception messages/configuration and never serialize API credentials. Distinguish provider errors, truncation, structure rejection and intended abstention.
- AC-3505: Summarize paired results with explicit denominators, token totals and observed latency, retaining failed cases. Legal citations and format acceptance do not establish semantic accuracy. Save a separately labelled AI review draft; human labels remain pending.
- AC-3506: Offline regression exercises production dispatch, pairing, drift/attempt gates and summaries with mocked external generation. Verify frozen v2/v3/v3.1 artifacts unchanged. No default-mode change, frontend modification, service restart or git publication.

Plan: RED safety/contract tests → experiment runner → frozen preparation → authorized
live calls → inspect own evidence and produce AI draft review → regression/report.
Real effects are diagnostic on familiar papers, not generalization or human Gold.
