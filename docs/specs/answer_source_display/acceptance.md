# Answer source display

- AC-2301: Count unique known citation IDs in the answer, preserving original IDs;
  do not relabel unknown IDs or renumber filtered sources.
- AC-2302: A response without citations has zero cited evidence, even when sources
  were retrieved. Keep uncited candidates in a separately labelled collapsed section.
- AC-2303: Pending answers expose an accessible, explicit waiting status; do not
  claim a precise backend stage because the protocol does not supply stage events.

Plan: reuse the current citation parser, add a pure partition helper and shared
source-list component, preserve existing evidence navigation and button styles.
Scope excludes backend generation, retrieval changes, or automatic merge/push.
