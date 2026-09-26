import unittest
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from table_orientation_provenance import docling_bbox

class NativeProvenanceTests(unittest.TestCase):
    def test_bottom_left_converts_before_inverse_rotation(self):
        b={'l':20,'r':60,'t':40,'b':10,'coord_origin':'BOTTOMLEFT'}
        self.assertEqual(docling_bbox(b,[100,80],90,[7,11]),[17,31,47,71])
    def test_top_left_equivalent(self):
        b={'l':20,'r':60,'t':60,'b':90,'coord_origin':'TOPLEFT'}
        self.assertEqual(docling_bbox(b,[100,80],90),[10,20,40,60])
    def test_unknown_origin_fails_closed(self):
        with self.assertRaises(ValueError):docling_bbox({'coord_origin':'unknown'},[100,80],0)

if __name__=='__main__':unittest.main()
