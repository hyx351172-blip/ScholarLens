import asyncio
import json
import unittest

from backend.chat.multi_query_retrieval import (
    PLANNER_SYSTEM_PROMPT,
    create_query_plan,
    execute_retrieval_plan,
    parse_query_plan,
)


def _hit(chunk_id: str, score: float = 0.5) -> dict:
    return {
        "score": score,
        "chunk_text": f"text for {chunk_id}",
        "filename": f"{chunk_id}.pdf",
        "metadata": {"chunk_id": chunk_id},
    }


class QueryPlanParsingTests(unittest.TestCase):
    def test_valid_comparison_plan_is_normalized(self):
        raw = json.dumps(
            {
                "intent": "comparison",
                "subqueries": [
                    {
                        "id": "Paper A",
                        "target": "Paper A",
                        "query": "How does Paper A train?",
                    },
                    {
                        "id": "paper_b",
                        "target": "Paper B",
                        "query": "How does Paper B train?",
                    },
                ],
            }
        )

        plan = parse_query_plan(raw, "Compare Paper A and Paper B")

        self.assertTrue(plan.is_multi_query)
        self.assertEqual([item.query_id for item in plan.subqueries], [
            "paper-a",
            "paper_b",
        ])
        self.assertEqual(plan.subqueries[0].target, "Paper A")

    def test_duplicate_or_original_subqueries_are_rejected(self):
        raw = json.dumps(
            {
                "intent": "comparison",
                "subqueries": [
                    {"id": "a", "target": "A", "query": "Compare A and B"},
                    {"id": "b", "target": "B", "query": "Compare A and B"},
                ],
            }
        )

        with self.assertRaisesRegex(ValueError, "distinct"):
            parse_query_plan(raw, "Compare A and B")

    def test_duplicate_targets_are_rejected(self):
        raw = json.dumps(
            {
                "intent": "comparison",
                "subqueries": [
                    {"id": "bert-a", "target": "BERT", "query": "How is BERT pretrained?"},
                    {"id": "bert-b", "target": "bert", "query": "How is BERT fine-tuned?"},
                    {"id": "gpt", "target": "GPT-3", "query": "How does GPT-3 learn in context?"},
                ],
            }
        )

        with self.assertRaisesRegex(ValueError, "targets must be unique"):
            parse_query_plan(raw, "Compare BERT and GPT-3")


class QueryPlannerTests(unittest.IsolatedAsyncioTestCase):
    def test_prompt_requires_atomic_non_broadened_queries(self):
        self.assertIn("atomic retrieval question", PLANNER_SYSTEM_PROMPT)
        self.assertIn("Do not broaden", PLANNER_SYSTEM_PROMPT)
        self.assertIn("user explicitly requested", PLANNER_SYSTEM_PROMPT)

    async def test_invalid_planner_output_falls_back_to_single_query(self):
        async def generate(_messages):
            return "not JSON"

        plan = await create_query_plan("Compare A and B", generate)

        self.assertFalse(plan.is_multi_query)
        self.assertEqual(plan.fallback_reason, "invalid_planner_output")

    async def test_invalid_plan_gets_one_bounded_repair_attempt(self):
        calls = 0

        async def generate(messages):
            nonlocal calls
            calls += 1
            if calls == 1:
                return "not JSON"
            self.assertIn("was invalid", messages[-1]["content"])
            return json.dumps(
                {
                    "intent": "comparison",
                    "subqueries": [
                        {"id": "a", "target": "A", "query": "Question about A"},
                        {"id": "b", "target": "B", "query": "Question about B"},
                    ],
                }
            )

        plan = await create_query_plan("Compare A and B", generate)

        self.assertTrue(plan.is_multi_query)
        self.assertEqual(calls, 2)

    async def test_planner_timeout_falls_back_to_single_query(self):
        async def generate(_messages):
            await asyncio.sleep(0.05)
            return "{}"

        plan = await create_query_plan(
            "Compare A and B",
            generate,
            timeout_seconds=0.001,
        )

        self.assertFalse(plan.is_multi_query)
        self.assertEqual(plan.fallback_reason, "planner_timeout")


class ParallelRetrievalTests(unittest.IsolatedAsyncioTestCase):
    async def test_original_and_subqueries_are_retrieved_concurrently(self):
        plan = parse_query_plan(
            json.dumps(
                {
                    "intent": "comparison",
                    "subqueries": [
                        {"id": "a", "target": "A", "query": "Question A"},
                        {"id": "b", "target": "B", "query": "Question B"},
                    ],
                }
            ),
            "Compare A and B",
        )
        active = 0
        max_active = 0

        async def retrieve(query):
            nonlocal active, max_active
            active += 1
            max_active = max(max_active, active)
            await asyncio.sleep(0.01)
            active -= 1
            return [_hit(query.replace(" ", "-"))]

        execution = await execute_retrieval_plan(
            original_query="Compare A and B",
            plan=plan,
            retrieve=retrieve,
            top_k=3,
            original_reserve=1,
            per_target_reserve=1,
        )

        self.assertEqual(max_active, 3)
        self.assertEqual(execution.trace["mode"], "multi_query")
        self.assertEqual(len(execution.documents), 3)

    async def test_failed_target_query_returns_original_results(self):
        plan = parse_query_plan(
            json.dumps(
                {
                    "intent": "comparison",
                    "subqueries": [
                        {"id": "a", "target": "A", "query": "Question A"},
                        {"id": "b", "target": "B", "query": "Question B"},
                    ],
                }
            ),
            "Compare A and B",
        )

        async def retrieve(query):
            if query == "Question B":
                raise RuntimeError("temporary search failure")
            if query == "Compare A and B":
                return [_hit("baseline")]
            return [_hit("a")]

        execution = await execute_retrieval_plan(
            original_query="Compare A and B",
            plan=plan,
            retrieve=retrieve,
            top_k=3,
            original_reserve=1,
            per_target_reserve=1,
        )

        self.assertEqual(
            [item["metadata"]["chunk_id"] for item in execution.documents],
            ["baseline"],
        )
        self.assertEqual(execution.trace["mode"], "single_query_fallback")
        self.assertEqual(execution.trace["fallback_reason"], "target_retrieval_failed")


if __name__ == "__main__":
    unittest.main()
