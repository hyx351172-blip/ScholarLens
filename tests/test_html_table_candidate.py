import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend/Information-Extraction/unified'))
from parsers.html_table_candidate import parse_html_table


TABLE = '<table><thead><tr><th rowspan="2">Model</th><th colspan="2">Scores</th></tr><tr><th>A</th><th>B</th></tr></thead><tbody><tr><td>X &amp; Y</td><td>0.18</td><td>[UNCERTAIN]</td></tr></tbody></table>'


class HTMLCandidateTests(unittest.TestCase):
    def test_spans_positions_and_roundtrip(self):
        """AC-HTML-901: deterministic placement, not model-emitted indices."""
        data, rendered = parse_html_table(TABLE)
        self.assertEqual((data['num_rows'], data['num_cols']), (3, 3))
        self.assertEqual(data['table_cells'][2]['start_col_offset_idx'], 1)
        self.assertEqual(data['table_cells'][0]['row_span'], 2)
        self.assertEqual(data['table_cells'][1]['col_span'], 2)
        self.assertEqual(data['uncertain_cells'], [[2, 2]])
        self.assertEqual(data['table_cells'][4]['text'], 'X & Y')
        self.assertEqual(parse_html_table(rendered)[0]['table_cells'], data['table_cells'])
        self.assertTrue(all(c['bbox'] is None for c in data['table_cells']))

    def test_empty_cells_formatting_and_markdown_fence(self):
        """AC-HTML-901/902: preserve blanks, line breaks, escaped values."""
        data, html = parse_html_table('```html\n<table border="1"><tr><td></td><td style="color:red"><b>&lt;X&gt;</b><br/>0.25</td></tr></table>\n```')
        self.assertEqual(data['table_cells'][0]['text'], '')
        self.assertEqual(data['table_cells'][1]['text'], '<X>\n0.25')
        self.assertNotIn('style=', html)
        self.assertIn('&lt;X&gt;<br>0.25', html)

    def test_rejects_invalid_markup_geometry_and_unbounded_work(self):
        """AC-HTML-901/902: no browser-style implicit repair of model errors."""
        bad = [
            '<table><tr><td>x',
            '<table><tr><td>x</tr></table>',
            '<table><tr><td rowspan="2">x</td></tr></table>',
            '<table><tr><td>x</td><td>y</td></tr><tr><td>z</td></tr></table>',
            '<table><tr><td>x</td><td rowspan="2">y</td></tr><tr><td colspan="2">z</td></tr></table>',
            '<table><tr><td colspan="0">x</td></tr></table>',
            '<table><tr><td colspan="10000000">x</td></tr></table>',
            '<table><tr><td colspan="2" colspan="1">x</td></tr></table>',
            '<table><tr><td><table><tr><td>x</td></tr></table></td></tr></table>',
            TABLE + TABLE, '<p>Here is your table</p>' + TABLE,
            '<table><tr><td><script>alert(1)</script></td></tr></table>',
            '<table><tr><td onclick="bad()">x</td></tr></table>',
            '<table><tr><td><img src="https://example.test"></td></tr></table>',
        ]
        for raw in bad:
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                parse_html_table(raw)

    def test_spanned_empty_row_and_wrapper(self):
        """AC-HTML-901: a row fully covered by previous spans is valid."""
        d, _ = parse_html_table('<html><body><table><tr><td rowspan="2">x</td></tr><tr></tr></table></body></html>')
        self.assertEqual(d['num_rows'], 2)
        self.assertEqual(d['uncovered_slots'], 0)


if __name__ == '__main__':
    unittest.main()
