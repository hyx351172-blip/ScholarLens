import sys
from pathlib import Path
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from score_table_header_reconstruction import header_diagnostics


class HeaderMetricsTests(unittest.TestCase):
    def table(self,header):
        return '<table>'+header+('<tr><td>1</td><td>2</td></tr>'*3)+'</table>'

    def test_exact_hierarchy_and_text(self):
        raw=self.table('<tr><td colspan="2">P</td></tr><tr><td>A</td><td>B</td></tr>')
        out=header_diagnostics(raw,raw)
        self.assertTrue(out['available'])
        self.assertEqual(out['matched_span_cells'],1)
        self.assertEqual(out['exact_text_cells'],1)

    def test_missing_parent_span_not_hidden_by_same_words(self):
        gold=self.table('<tr><td colspan="2">P</td></tr><tr><td>A</td><td>B</td></tr>')
        pred=gold.replace('<td colspan="2">P</td>','<td>P</td><td></td>')
        out=header_diagnostics(pred,gold)
        self.assertEqual(out['matched_span_cells'],0)
        self.assertEqual(out['missing_span_cells'],1)

    def test_missing_prefix_is_unavailable_not_perfect(self):
        out=header_diagnostics('<table><tr><td>x</td></tr></table>','<table><tr><td>x</td></tr></table>')
        self.assertFalse(out['available'])


if __name__=='__main__': unittest.main()
