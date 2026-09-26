import sys
from pathlib import Path
import tempfile
import unittest
import struct

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from experiment_table_header_reconstruction import assert_previous_success,load_crop


class HeaderReplayContracts(unittest.TestCase):
    def test_previously_passing_candidate_cannot_change(self):
        prior={'gate':{'passed':True},'html':'old'}
        for out in ({'gate':{'passed':True},'html':'new'},{'gate':{'passed':False},'html':'old'}):
            with self.assertRaises(ValueError): assert_previous_success(out,prior)
        assert_previous_success(prior,prior)

    def test_rejected_prior_may_be_repaired(self):
        assert_previous_success({'gate':{'passed':True},'html':'new'}, {'gate':{'passed':False},'html':None})

    def test_large_crop_rejected_before_decode(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'large.png'
            path.write_bytes(b'\x89PNG\r\n\x1a\n'+b'\x00\x00\x00\x0dIHDR'+struct.pack('>II',50000,50000))
            with self.assertRaisesRegex(ValueError,'pixel budget'): load_crop(path)

    def test_truncated_png_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'bad.png'; path.write_bytes(b'bad')
            with self.assertRaises(ValueError): load_crop(path)


if __name__=='__main__': unittest.main()
