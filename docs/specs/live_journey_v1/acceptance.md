# Live journey v1 acceptance

Scope: one newly uploaded Attention paper, isolated development KB, four API
questions and a browser citation interaction. This is a development smoke run,
not an independent held-out benchmark. No application fixes or production changes.

- AC-2101: Real upload completes extraction, structure-aware chunking and storage;
  nonzero chunk counts match document list/details; served PDF hash matches input.
- AC-2102: Actual chat response succeeds with nonempty answer. Answerable questions
  have sources; citation IDs exist; every returned source has matching file ID,
  chunk evidence and valid page range. Check quality separately against original PDF.
- AC-2103: Explicit table question must answer Table 2's 28.4/41.8, not conflate the
  nearby prose's 41.0. Unanswerable GPT-4/MMLU question must not invent a result.
- AC-2104: Browser shows uploaded document; one streamed answer completes; clicking
  a citation reveals evidence and corresponding page. Report any incomplete step.

Budget: one PDF embedding job, four API questions plus one UI question; no VLM,
no separate paid judge, no automatic retries of completed expensive stages.
Local services retain configured credentials in memory; never persist config/default.
Failures are reported, not repaired in this task. No delete/merge/push.
