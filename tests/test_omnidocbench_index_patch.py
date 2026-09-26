"""Exercise the actual pinned upstream matching function, not a copied fix.

Normalization/assignment are isolated stubs; the real end-to-end scorer is also
run for the frozen experiment. Skip when the optional evaluator isn't installed.
"""
import ast
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MATCH_FILE = ROOT / "backend/data/benchmarks/omnidocbench/evaluator/src/core/matching/match.py"


@unittest.skipUnless(MATCH_FILE.is_file(), "optional pinned OmniDocBench checkout not installed")
class OmniDocBenchIndexTests(unittest.TestCase):
    def setUp(self):
        tree = ast.parse(MATCH_FILE.read_text(encoding="utf-8"))
        function = next(node for node in tree.body if isinstance(node, ast.FunctionDef)
                        and node.name == "match_gt2pred_simple")

        def lines(gt, pred, _kind):
            g = [item["content"] for item in gt]
            p = [item["content"] for item in pred]
            return g, g, ["table"] * len(g), p, p, gt, pred

        namespace = {
            "get_gt_pred_lines": lines,
            "compute_edit_distance_matrix_new": lambda g, p: [[0] * len(p) for _ in g],
            "linear_sum_assignment": lambda matrix: (list(range(min(len(matrix), len(matrix[0])))),) * 2,
            "get_pred_category_type": lambda i, items: items[i]["category_type"],
            "split_pred_table_to_text_items": lambda items: items,
        }
        exec(compile(ast.Module(body=[function], type_ignores=[]), str(MATCH_FILE), "exec"), namespace)
        self.match = namespace["match_gt2pred_simple"]

    def test_zero_index_and_zero_character_position_are_valid(self):
        """AC-TABLE-701: first prediction must participate in reading order."""
        for position in (0, 147):
            with self.subTest(position=position):
                result, _ = self.match(
                    [{"content": "table", "order": 1}],
                    [{"content": "table", "position": [position, position + 5], "category_type": "html_table"}],
                    "html_table", "page.png",
                )
                self.assertEqual(result[0]["pred_idx"], [0])
                self.assertEqual(result[0]["pred_position"], position)
                self.assertEqual(result[0]["pred_category_type"], "html_table")

    def test_nonzero_and_unmatched_predictions_remain_distinct(self):
        """AC-TABLE-701: absence stays empty; later prediction retains offset."""
        gt = [{"content": "table", "order": i + 1} for i in range(3)]
        pred = [{"content": "table", "position": [i * 20, i * 20 + 5], "category_type": "html_table"}
                for i in range(2)]
        result, _ = self.match(gt, pred, "html_table", "page.png")
        self.assertEqual(result[1]["pred_position"], 20)
        self.assertEqual(result[2]["pred_idx"], [""])
        self.assertEqual(result[2]["pred_position"], "")
        self.assertEqual(result[2]["pred_category_type"], "")


if __name__ == "__main__":
    unittest.main()
