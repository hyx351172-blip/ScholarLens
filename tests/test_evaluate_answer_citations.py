import unittest

from scripts.evaluate_answer_citations import (
    _build_claim_evidence_bundles,
    _build_judge_prompt,
    _claim_units,
    _enforce_claim_evidence_policy,
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
    def test_claim_evidence_bundles_include_only_each_claims_cited_sources(self):
        # @covers AC-202.1, AC-202.2
        sources = [
            {
                "source_id": "S1",
                "filename": "bert.pdf",
                "chunk_text": "BERT uses masked language modelling.",
            },
            {
                "source_id": "S2",
                "filename": "lora.pdf",
                "chunk_text": "LoRA freezes pretrained weights and learns low-rank updates.",
            },
        ]

        bundles = _build_claim_evidence_bundles(
            "BERT uses masked language modelling [S1]. "
            "LoRA learns low-rank updates [S1]. "
            "LoRA freezes pretrained weights [S2][S9]. "
            "The method is efficient.",
            sources,
        )

        self.assertEqual([item["id"] for item in bundles], ["A1", "A2", "A3", "A4"])
        self.assertEqual(bundles[0]["valid_citation_numbers"], [1])
        self.assertEqual(bundles[1]["valid_citation_numbers"], [1])
        self.assertEqual(bundles[2]["citation_numbers"], [2, 9])
        self.assertEqual(bundles[2]["valid_citation_numbers"], [2])
        self.assertEqual(bundles[2]["invalid_citation_numbers"], [9])
        self.assertEqual(bundles[3]["evidence"], [])
        self.assertNotIn("lora.pdf", str(bundles[1]["evidence"]))

    def test_judge_prompt_isolates_evidence_under_the_claim_that_cited_it(self):
        # @covers AC-202.2
        prompt = _build_judge_prompt(
            question="Compare A and B.",
            answer="A uses mechanism X [S1]. B uses mechanism Y [S2].",
            expected_answer="A and B differ.",
            required_concepts=["difference between A and B"],
            sources=[
                {
                    "source_id": "S1",
                    "filename": "paper-a.pdf",
                    "chunk_text": "A uses mechanism X while B uses mechanism Y.",
                },
                {
                    "source_id": "S2",
                    "filename": "paper-b.pdf",
                    "chunk_text": "B uses mechanism Y.",
                },
            ],
        )

        self.assertIn("Claim A1", prompt)
        self.assertIn("Claim A2", prompt)
        self.assertIn("Cited evidence for A1 only", prompt)
        self.assertIn("A uses mechanism X", prompt)
        self.assertIn("never borrow evidence attached to another claim", prompt)
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

    def test_claim_units_ignore_chinese_structural_lead_in(self):
        answer = """论文《Attention Is All You Need》的结论如下：
- 首个结论有证据 [S1]。
- 第二个结论也有证据 [S1]。
"""

        self.assertEqual(
            _claim_units(answer),
            ["首个结论有证据 [S1]。", "第二个结论也有证据 [S1]。"],
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

    def test_judge_output_requires_every_concept_and_claim_exactly_once(self):
        # @covers AC-202.3
        judgement = _parse_judge_output(
            '{"concepts":[{"id":"C1","covered":true},'
            '{"id":"C2","covered":false}],'
            '"claims":[{"id":"A1","supported":true,"reason":"direct support"},'
            '{"id":"A2","supported":false,"reason":"wrong cited source"}]}',
            ["C1", "C2"],
            {"A1": "Supported claim [S1].", "A2": "Wrong citation [S1]."},
        )

        self.assertEqual(judgement["covered_concept_ids"], ["C1"])
        self.assertEqual(judgement["missing_concept_ids"], ["C2"])
        self.assertEqual(judgement["supported_claim_ids"], ["A1"])
        self.assertEqual(judgement["unsupported_claim_ids"], ["A2"])
        self.assertEqual(judgement["unsupported_claims"], ["Wrong citation [S1]."])
        self.assertEqual(judgement["claim_entailment_rate"], 0.5)

        with self.assertRaisesRegex(ValueError, "exactly once"):
            _parse_judge_output(
                '{"concepts":[{"id":"C1","covered":true}],'
                '"claims":[{"id":"A1","supported":true,"reason":"ok"},'
                '{"id":"A2","supported":false,"reason":"wrong"}]}',
                ["C1", "C2"],
                {"A1": "Supported claim [S1].", "A2": "Wrong citation [S1]."},
            )

        with self.assertRaisesRegex(ValueError, "expected claim exactly once"):
            _parse_judge_output(
                '{"concepts":[{"id":"C1","covered":true},'
                '{"id":"C2","covered":false}],'
                '"claims":[{"id":"A1","supported":true,"reason":"ok"}]}',
                ["C1", "C2"],
                {"A1": "Supported claim [S1].", "A2": "Wrong citation [S1]."},
            )

    def test_uncited_claim_is_deterministically_unsupported(self):
        # @covers AC-202.2, AC-202.3
        bundles = _build_claim_evidence_bundles(
            "Nougat converts document images into markup.",
            [
                {
                    "source_id": "S1",
                    "filename": "nougat.pdf",
                    "chunk_text": "Nougat converts document images into markup.",
                }
            ],
        )
        judgement = {
            "claim_support": [
                {
                    "id": "A1",
                    "claim": bundles[0]["claim"],
                    "supported": True,
                    "reason": "The reference answer agrees.",
                }
            ]
        }

        enforced = _enforce_claim_evidence_policy(judgement, bundles)

        self.assertEqual(enforced["supported_claim_ids"], [])
        self.assertEqual(enforced["unsupported_claim_ids"], ["A1"])
        self.assertEqual(enforced["claim_entailment_rate"], 0.0)
        self.assertIn("No valid claim-scoped cited evidence", enforced["claim_support"][0]["reason"])


if __name__ == "__main__":
    unittest.main()
