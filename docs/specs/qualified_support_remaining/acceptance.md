# v2.1 remaining-51 batch

Prepare a new opt-in batch for the 51 never-attempted packets. Preserve the
stopped v2 run and its independent v2.1 offline reinterpretation. No publication
or production changes. A separate explicit 51-call approval is required.

- AC-4601: Verify the frozen v2 and v2.1 replay histories. Exclude exactly the previously attempted SF-72 packet; freeze the remaining 29 SciFact and 22 regression entries, labels and unchanged request bodies in original order, with labels absent from requests.
- AC-4602: Bind v2.1 parsing to this new batch without modifying frozen code or prompts. Complete responses use the new quote matcher; API errors, refusal and truncation remain errors, not recoverable outputs. Preserve raw output, request identity, usage and parser provenance.
- AC-4603: Require explicit approval of at most 51 new calls before credentials. Keep model qwen3-vl-plus, max_tokens=1500, temperature=0, retries=0, deadline=60 seconds, serial operation and first-error stop. Exclusive attempt/run markers prevent duplicate spending; interrupted or stopped runs do not resume.
- AC-4604: Reparse raw responses when scoring. Score only the predefined 29-case live SciFact subset, with its matching v1 subset and full denominator including errors/missing/uncertain. Show the excluded historical replay separately, never pool it as a new live sample. Regression22 has transitions only, no semantic accuracy or human Gold.
- AC-4605: Cached summaries and individual records must agree, secret echoes must be redacted and failed, history/input/result drift must fail closed. Preserve all unattempted cases and null human-review fields; publish no mixed52 live accuracy.
- AC-4606: RED/GREEN tests, complete regression and traceability pass before freezing. Preparation makes zero external calls; live execution only after new approval. Store report, usage and write-once artifacts without changing old experiments.
