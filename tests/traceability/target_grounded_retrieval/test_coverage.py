"""Feature coverage manifest for the mechanical release gate.

@covers AC-201.1 — TargetFilenameResolutionTests
@covers AC-201.2 — filter pushdown and payload contract tests
@covers AC-201.3 — catalog failure degradation test
@covers AC-201.4 — retrieval trace assertion
@covers AC-201.5 — development dataset and live evaluator

The executable tests live in the repository's normal ``tests`` modules; this
file keeps the feature-scoped traceability checker from conflating unrelated
historical AC namespaces.
"""
