# Live Query Planner v3 — Alternative Evidence Review

## Why this review exists

The live planner passed JSON validation and preserved both comparison targets
for all six development questions. Exact strict evidence Hit@10 was only 50%,
but every result contained chunks from all required source papers. The three
strict misses therefore need evidence-level review before changing the Gold
set or the release gate.

Do not treat source-paper coverage alone as proof that the answer is supported.
Accept a candidate only when its text directly supports the required claim.

## MQ01 — Transformer versus Mamba

Current strict miss: the result contains the Mamba Gold abstract but not the
Transformer Gold abstract.

Candidate Transformer evidence:

- [x] `bdfaa68d8984f0dc02beaca527b76f207d99b666d31d1da728ee0728182df697:paragraph:block_000011:part_0001`
  - Page 2, `1 Introduction`
  - States that attention models dependencies regardless of distance and that
    the Transformer eschews recurrence while relying on attention for global
    dependencies.
- [x] `bdfaa68d8984f0dc02beaca527b76f207d99b666d31d1da728ee0728182df697:paragraph:block_000016:part_0001`
  - Page 2, `2 Background`
  - States that the Transformer relates distant positions in a constant number
    of operations and relies entirely on self-attention without sequence-aligned
    RNNs or convolution.

Proposed action if accepted: add each accepted Transformer chunk paired with
the existing Mamba abstract as an additional valid evidence set. Do not replace
the existing evidence set.

Reviewer decision: `accepted`

## MQ02 — Donut versus Nougat

Current strict miss: the result contains the Donut Gold method chunk but not
the Nougat Gold abstract.

Candidate Nougat evidence:

- [x] `679be336ce8010d3dc86b9530f0a30d4d5ea2a13153c6f274601b40f4382745b:paragraph:block_000115:part_0001`
  - Page 9, `6 Conclusion`
  - States that Nougat is an end-to-end encoder-decoder Transformer converting
    document pages to markup, using rasterized pages without OCR or embedded
    text representations.

Proposed action if accepted: pair this chunk with the existing Donut method
chunk as an additional valid evidence set.

Reviewer decision: `accepted`

## MQ05 — Transformer versus FlashAttention

Current strict miss: the result contains the FlashAttention Gold figure but
not the Transformer Gold abstract.

Candidate Transformer evidence:

- [x] `bdfaa68d8984f0dc02beaca527b76f207d99b666d31d1da728ee0728182df697:paragraph:block_000049:part_0001`
  - Page 5, `3 Model Architecture > 3.2 Attention > 3.2.3 Applications of Attention in our Model`
  - Describes the roles of encoder-decoder attention, encoder self-attention,
    and masked decoder self-attention in the Transformer.
- [x] `bdfaa68d8984f0dc02beaca527b76f207d99b666d31d1da728ee0728182df697:paragraph:block_000024:part_0001`
  - Page 3, `3 Model Architecture`
  - States that the Transformer encoder and decoder use stacked self-attention
    and point-wise feed-forward layers.

Proposed action if accepted: add each accepted Transformer chunk paired with
the existing FlashAttention figure as an additional valid evidence set.

Reviewer decision: `accepted`

## Sign-off

- Reviewer: `project owner`
- Date: `2026-09-23`
- MQ01 accepted chunk(s): `block_000011`, `block_000016`
- MQ02 accepted chunk(s): `block_000115`
- MQ05 accepted chunk(s): `block_000049`, `block_000024`
- Notes: original Gold sets retained; confirmed alternatives appended.
