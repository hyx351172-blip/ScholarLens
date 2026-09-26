import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from bounded_table_orientation import sample_boxes


class BoundedOrientationTests(unittest.TestCase):
    def test_vertical_boxes_not_recognized_as_horizontal(self):
        polys=[[[5,5],[15,5],[15,90],[5,90]]]*50
        self.assertEqual(sample_boxes(polys,[200,200]),[])

    def test_count_width_and_spatial_coverage_bounded(self):
        polys=[[[0,i*5],[999,i*5],[999,i*5+4],[0,i*5+4]] for i in range(100)]
        boxes=sample_boxes(polys,[1000,600])
        self.assertEqual(len(boxes),24)
        self.assertEqual(boxes[0]['detection_id'],0)
        self.assertEqual(boxes[-1]['detection_id'],99)
        self.assertTrue(all(b['bbox'][2]-b['bbox'][0]<=12*(b['bbox'][3]-b['bbox'][1]) for b in boxes))

    def test_invalid_geometry_fails(self):
        for polys in [[[[0,0]]],[[[0,0],[2,0],[2,float('nan')],[0,2]]]]:
            with self.assertRaises(ValueError):sample_boxes(polys,[100,100])

if __name__=='__main__':unittest.main()
