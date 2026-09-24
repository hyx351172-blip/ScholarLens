# Academic Button System

## Goal

Replace rigid rectangular command controls with a coherent button hierarchy
that matches ScholarLens' restrained academic workspace: compact pill-shaped
actions, soft outline alternatives and circular icon controls. Selection cards
and navigation tabs remain card/tab shaped because they represent choices or
locations rather than commands.

## Acceptance criteria

- **AC-303.1** — Primary, secondary, quiet, ghost and danger command buttons use
  shared variants with consistent pill geometry, typography and spacing.
- **AC-303.2** — Primary actions are visually dominant without gradients; icon
  actions use compact circular hit targets and dangerous actions remain red.
- **AC-303.3** — Buttons expose visible hover, focus-visible and disabled states,
  and icon-only controls retain accessible labels.
- **AC-303.4** — Dashboard, knowledge-base, chat, upload, document, settings and
  retrieval command surfaces use the shared system without changing behavior.
- **AC-303.5** — Button unit tests, TypeScript checks, production build and
  desktop/mobile visual inspection pass.

## Out of scope

- Changing the behavior of uploads, deletion, retrieval or chat actions.
- Turning selection cards, tabs, inputs or citation evidence cards into pills.
- Copying proprietary button assets or branding from the reference product.
