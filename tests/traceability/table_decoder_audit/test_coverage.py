"""Executable cases: tests/test_audit_table_decoder.py, test_score_table_decoder_audit.py.

@covers AC-1101 — graph dialect/schema, four-leaf edits, copy hashes and unknown-graph rejection
@covers AC-1102 — real pre-decoding tensors, natural EOS, exact cap, short/invalid tensors
@covers AC-1103 — path/hash preflight, fresh clones, bounded CPU worker and six real inferences
@covers AC-1104 — strict gaps/tags, prefix/confounder tests, failure/regression scoring
@covers AC-1105 — actual model/evaluator seams, original artifact integrity, v8 report

This index is not proof of execution; see the report and saved logs.
"""
