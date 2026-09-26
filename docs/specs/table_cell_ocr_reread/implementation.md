# Bounded cell OCR reread v17

Development experiment only: reread cells touched by ambiguous cross-column OCR
in the frozen v15/v16 cohort. No production parser changes, remote inference,
new model downloads, row reconstruction, or gold-guided selection.

- AC-2001: Select only stable matching lattices whose only rejection is ambiguous
  OCR; every ambiguous line must cross columns within a single row. At most 12
  affected cells; otherwise no-op. Select from geometry, not IDs or text.
- AC-2002: Preserve source capture; remove exactly old lines owned by selected
  cells or ambiguous across them. Attach original/new IDs and crop transforms;
  never duplicate old and new evidence or split recognized strings.
- AC-2003: Missing/empty/low-confidence/nonfinite/out-of-region rereads reject.
  Rebind against unchanged geometry and apply the existing row-safety veto;
  rejection retains previous effective output. Retain candidate for diagnosis.
- AC-2004: Run cached local OCR once per selected cell, freeze inputs and outputs
  before separate gold scoring; keep all other cohort artifacts unchanged.
- AC-2005: Measure official TEDS, structure TEDS, coordinate-aligned cell/numeric
  accuracy. Distinguish diagnostic candidate from admitted effective output.

Fixed policy before inference: integer crops lie inside inferred cells; add 16px
white padding, original resolution, PP-OCRv5 server det/rec CPU, minimum line
confidence 0.5, no threshold tuning. Fail closed on any lost previously assigned
numeric token (diagnostic regex, not a scientific correctness guarantee).

Tests: Python unittest, pure selection/replacement/failure tests and frozen real
capture contract. Real local OCR is a separate integration experiment. No new
RAG user journey is connected; no frontend/database/full-RAG E2E claim.
