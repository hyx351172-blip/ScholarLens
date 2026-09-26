import sys
import tempfile
from pathlib import Path
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from audit_table_candidate_geometry import run,graph_topk_nodes,overlay,same_artifact


class GeometryAuditTests(unittest.TestCase):
    def test_existing_output_rejected_before_models(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaisesRegex(ValueError,'Fresh output'):run(Path(d))

    def test_graph_limits_come_from_constant_input_not_output_guess(self):
        ops=[{'#':'1.full','O':[{'%':7}],'A':[{'N':'value','AT':{'D':123.0}}]},
             {'#':'1.topk','I':[{'%':6},{'%':7}],'O':[]}]
        g={'program':{'regions':[{'blocks':[{'ops':ops}]}]}}
        self.assertEqual(graph_topk_nodes(g)[0]['k'],123)
        ops[0]['#']='1.unknown';self.assertIsNone(graph_topk_nodes(g)[0]['k'])

    def test_identical_requires_bytes_not_normalized_newlines(self):
        with tempfile.TemporaryDirectory() as td:
            a=Path(td)/'a';b=Path(td)/'b'
            a.write_bytes(b'a\r\nb');b.write_bytes(b'a\nb')
            self.assertEqual(a.read_text(),b.read_text());self.assertFalse(same_artifact(a,b))
            b.write_bytes(a.read_bytes());self.assertTrue(same_artifact(a,b))

    def test_overlay_escapes_diagnostic_text_and_keeps_image_bytes(self):
        d={'grid':None,'normalization':{'status':'rejected','reason':'<script>bad</script>'},'ambiguous_ocr':[]}
        result=overlay(b'abc',[10,20],d,{})
        self.assertIn('data:image/png;base64,YWJj',result)
        self.assertNotIn('<script>',result);self.assertIn('&lt;script&gt;',result)

if __name__=='__main__':unittest.main()
