# Citation Evidence Navigation

## Goal

Turn ScholarLens answers into an inspectable research workflow: every inline
`[Sx]` citation can be opened as evidence, and the evidence panel identifies
the paper, page range, section, chunk and retrieved excerpt without changing
the retrieval or generation algorithms.

The visual direction is a light, restrained academic workspace: white content
surfaces, soft lavender accents, compact navigation and document-first
hierarchy. The supplied Scholaread screenshot is a reference, not a source of
brand assets or copied implementation.

## Acceptance criteria

- **AC-301.1** — Assistant citation markers such as `[S1]` and `[S1][S2]` are
  rendered as accessible interactive controls and map only to sources returned
  with the same assistant message.
- **AC-301.2** — Selecting a valid citation opens an evidence panel showing the
  source ID, filename, page range, section path, chunk ID and exact retrieved
  excerpt when those fields are available.
- **AC-301.3** — Missing or invented source IDs are visibly marked unavailable
  and never open a different source as a fallback.
- **AC-301.4** — The chat source contract exposes the stable `source_id` and an
  optional `file_id` in both streaming and non-streaming responses without
  removing or renaming existing fields.
- **AC-301.5** — The application shell and research chat use the light academic
  visual direction at desktop and remain usable at narrow viewport widths.
- **AC-301.6** — Citation parsing/mapping tests, backend contract tests, the
  frontend production build and the existing Python regression suite pass.

## Out of scope

- Changing retrieval ranking, chunking, prompts or model configuration.
- Re-running or tuning against consumed held-out datasets.
- Pixel-for-pixel copying of Scholaread or reuse of its proprietary assets.
- PDF text highlighting by bounding box; the current contract has no stable
  bounding-box locator for every retrieved chunk.
