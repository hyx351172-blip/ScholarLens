import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from table_orientation import choose_orientation, ocr_quality, original_bbox


def evidence(score=.9, horizontal=True):
    return {'rec_texts': ['a readable line']*6, 'rec_scores': [score]*6,
            'rec_boxes': [[0, i*20, 150 if horizontal else 10, i*20+(10 if horizontal else 150)] for i in range(6)]}


class OrientationTests(unittest.TestCase):
    def test_confident_quarter_turn(self):
        q={a: ocr_quality(evidence(.3)) for a in [0,90,180,270]}
        q[90]=ocr_quality(evidence(.95))
        self.assertEqual(choose_orientation(q)['angle_ccw'],90)

    def test_upright_retained(self):
        q={a:ocr_quality(evidence(.3)) for a in [0,90,180,270]}
        q[0]=ocr_quality(evidence(.95))
        self.assertEqual(choose_orientation(q)['angle_ccw'],0)

    def test_ambiguous_and_low_evidence_keep_original(self):
        q={a:ocr_quality(evidence()) for a in [0,90,180,270]}
        self.assertEqual(choose_orientation(q)['angle_ccw'],0)
        empty=ocr_quality({'rec_texts':[],'rec_scores':[],'rec_boxes':[]})
        self.assertEqual(choose_orientation({a:empty for a in q})['angle_ccw'],0)

    def test_vertical_text_does_not_win_on_confidence_alone(self):
        self.assertLess(ocr_quality(evidence(.99,False))['score'],ocr_quality(evidence(.85))['score'])

    def test_missing_probe_and_invalid_scores_rejected(self):
        with self.assertRaises(ValueError): choose_orientation({0:ocr_quality(evidence())})
        for value in [float('nan'),-1,1.1]:
            raw=evidence();raw['rec_scores'][0]=value
            with self.assertRaises(ValueError): ocr_quality(raw)
        raw=evidence();raw['rec_boxes'].pop()
        with self.assertRaises(ValueError): ocr_quality(raw)

    def test_all_four_inverse_boxes_and_page_offsets(self):
        # Original rectangle [10,20,40,60] inside a 100 x 80 crop.
        boxes={0:[10,20,40,60],90:[20,60,60,90],180:[60,20,90,60],270:[20,10,60,40]}
        for a,b in boxes.items():
            self.assertEqual(original_bbox(b,[100,80],a),[10,20,40,60])
            self.assertEqual(original_bbox(b,[100,80],a,[7,11]),[17,31,47,71])

    def test_bad_dimensions_and_outside_geometry(self):
        for size,angle,box in [([0,80],0,[0,0,1,1]),([100,80],45,[0,0,1,1]),
                               ([100,80],90,[0,0,90,30])]:
            with self.assertRaises(ValueError):original_bbox(box,size,angle)

if __name__ == '__main__': unittest.main()
