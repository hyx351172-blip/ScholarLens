import unittest

from scripts.evaluate_answer_citations import (
    _build_judge_prompt,
    _claim_units,
    _evaluate_citation_contract,
    _extract_citation_numbers,
    _parse_judge_output,
)


def _source(index, filename, chunk_id):
    return {
        "source_id": f"S{index}",
        "filename": filename,
        "metadata": {"chunk_id": chunk_id},
    }


class AnswerCitationEvaluationTests(unittest.TestCase):
    def test_judge_prompt_uses_retrieved_evidence_for_grounding(self):
        prompt = _build_judge_prompt(
            question="Compare A and B.",
            answer="A differs from B [S1].",
            expected_answer="A and B differ.",
            required_concepts=["difference between A and B"],
            sources=[
                {
                    "source_id": "S1",
                    "filename": "paper-a.pdf",
                    "chunk_text": "A uses mechanism X while B uses mechanism Y.",
                }
            ],
        )

        self.assertIn("[S1] paper-a.pdf", prompt)
        self.assertIn("A uses mechanism X", prompt)
        self.assertIn("unsupported only when", prompt)
        self.assertIn("C1", prompt)

    def test_claim_units_ignore_pure_markdown_headings_only(self):
        answer = """1. **Input**
**Architecture differences**:
An introductory factual comparison needs evidence.
- A concrete bullet needs evidence [S1].
**Training objective**: this line contains a factual claim.
Specifically:
The method follows Li et al. (2018) and preserves one sentence [S2].
"""

        self.assertEqual(
            _claim_units(answer),
            [
                "An introductory factual comparison needs evidence.",
                "A concrete bullet needs evidence [S1].",
                "**Training objective**: this line contains a factual claim.",
                "The method follows Li et al. (2018) and preserves one sentence [S2].",
            ],
        )

    def test_extracts_single_adjacent_and_grouped_citations(self):
        answer = "One [S1]. Two [S2][S3]. Grouped [S1, S3]."

        self.assertEqual(_extract_citation_numbers(answer), [1, 2, 3, 1, 3])

    def test_complete_answer_cites_both_required_gold_sources(self):
        sources = [
            _source(1, "paper-a.pdf", "a:gold"),
            _source(2, "other.pdf", "x:other"),
            _source(3, "paper-b.pdf", "b:gold"),
        ]
        metrics = _evaluate_citation_contract(
            "Method A uses attention [S1]. Method B uses state spaces [S3].",
            sources,
            required_filenames={"paper-a.pdf", "paper-b.pdf"},
            gold_evidence_sets=[["a:gold", "b:gold"]],
        )

        self.assertTrue(metrics["citation_syntax_valid"])
        self.assertEqual(metrics["invalid_citation_numbers"], [])
        self.assertEqual(metrics["required_source_coverage"], 1.0)
        self.assertTrue(metrics["gold_evidence_citation_hit"])
        self.assertEqual(metrics["claim_citation_completeness"], 1.0)

    def test_invalid_and_missing_citations_fail_contract(self):
        metrics = _evaluate_citation_contract(
            "Supported claim [S1]. Unsupported comparison without a citation. Bad [S9].",
            [_source(1, "paper-a.pdf", "a:gold")],
            required_filenames={"paper-a.pdf", "paper-b.pdf"},
            gold_evidence_sets=[["a:gold", "b:gold"]],
        )

        self.assertFalse(metrics["citation_syntax_valid"])
        self.assertEqual(metrics["invalid_citation_numbers"], [9])
        self.assertEqual(metrics["required_source_coverage"], 0.5)
        self.assertFalse(metrics["gold_evidence_citation_hit"])
        self.assertAlmostEqual(metrics["claim_citation_completeness"], 2 / 3)

    def test_judge_output_requires_every_declared_concept(self):
        judgement = _parse_judge_output(
            '{"concepts":[{"id":"C1","covered":true},'
            '{"id":"C2","covered":false}],"unsupported_claims":[]}',
            ["C1", "C2"],
        )

        self.assertEqual(judgement["covered_concept_ids"], ["C1"])
        self.assertEqual(judgement["missing_concept_ids"], ["C2"])

        with self.assertRaisesRegex(ValueError, "exactly once"):
            _parse_judge_output(
                '{"concepts":[{"id":"C1","covered":true}],'
                '"unsupported_claims":[]}',
                ["C1", "C2"],
            )


if __name__ == "__main__":
    unittest.main()
