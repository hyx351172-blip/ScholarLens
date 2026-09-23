# Academic Icon System

## Goal

Replace the mixed emoji and high-saturation icon treatments in ScholarLens with
a coherent outline icon system suitable for a focused academic workspace. The
provided Scholaread screenshot is a visual reference for weight, restraint and
semantic clarity; it is not a source of copied brand assets.

## Acceptance criteria

- **AC-302.1** — Navigation, dashboard statistics, quick actions, knowledge
  bases, document types, retrieval modes and model settings use semantic vector
  icons rather than pictographic emoji.
- **AC-302.2** — Lucide icons share a consistent `1.75` stroke width and neutral
  slate treatment, with violet reserved for active or interactive emphasis.
- **AC-302.3** — Decorative icons are hidden from assistive technology while
  icon-only controls retain an accessible text label.
- **AC-302.4** — Icon replacements preserve existing actions, data loading and
  responsive layouts at desktop and narrow viewport widths.
- **AC-302.5** — Icon regression tests, TypeScript checks and the production
  frontend build pass.

## Out of scope

- Copying Scholaread logos, robot artwork, custom glyphs or proprietary assets.
- Redesigning retrieval, generation, parsing or persistence behavior.
- Replacing document thumbnails or scientific figures with generated artwork.
