import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend" / "Information-Extraction" / "unified"))
from parsers.markdown_renderer import render_document_markdown
from parsers.models import ContentBlock


class MarkdownRendererTests(unittest.TestCase):
    def test_keeps_tables_and_split_heading_hierarchy_without_running_inference(self):
        blocks = [
            ContentBlock("heading", 0, "heading", "2 Method 2.1 Training", relations={
                "generated_section_titles": ["2 Method", "2.1 Training"],
                "generated_section_levels": [1, 2],
            }),
            ContentBlock("table", 1, "table", "| Name | Score |\n|---|---|\n| A | 1 |"),
            ContentBlock("caption", 2, "caption", "Table 1. Scores."),
            ContentBlock("footer", 3, "page_footer", "page noise"),
        ]
        markdown = render_document_markdown(blocks)
        self.assertIn("# 2 Method\n\n## 2.1 Training", markdown)
        self.assertIn(blocks[1].text, markdown)
        self.assertEqual(markdown.count("Table 1. Scores."), 1)
        self.assertNotIn("page noise", markdown)

    def test_formula_delimiters_are_not_duplicated_and_missing_text_stays_missing(self):
        for text in ("x^2", "$$x^2$$", r"\[x^2\]", r"\(x^2\)"):
            with self.subTest(text=text):
                self.assertEqual(
                    render_document_markdown([ContentBlock("f", 0, "formula", text)]),
                    "$$\nx^2\n$$\n",
                )
        self.assertEqual(
            render_document_markdown([ContentBlock("f", 0, "formula", "")]),
            "<!-- formula-not-decoded -->\n",
        )

    def test_code_fences_do_not_end_at_embedded_backticks(self):
        markdown = render_document_markdown([ContentBlock("code", 0, "code", "print('```')")])
        self.assertEqual(markdown, "````\nprint('```')\n````\n")


if __name__ == "__main__":
    unittest.main()
