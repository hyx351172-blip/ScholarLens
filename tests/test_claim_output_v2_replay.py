import asyncio
import copy
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from tests.integration.replay_claim_output_v2 import verify_snapshot, replay_one
from tests.integration.compare_answer_modes import digest, value_hash
from backend.chat import claim_bound_answer as v1


class IntegrityTests(unittest.TestCase):
    # AC-3605 / AC-3606
    def test_only_explicit_code_edits_may_use_archived_original(self):
        with TemporaryDirectory() as tmp:
            root=Path(tmp);archive=root/'archive';archive.mkdir()
            code=root/'code.py';data=root/'data.json'
            code.write_text('before');data.write_text('frozen')
            snapshot={'code.py':digest(code),'data.json':digest(data)}
            (archive/'code.py').write_text('before');code.write_text('after')
            r=verify_snapshot(snapshot,root,archive,edited=('code.py',))
            self.assertEqual(r['unchanged_files'],1)
            self.assertEqual(len(r['archived_code']),1)
            data.write_text('changed')
            with self.assertRaises(ValueError):verify_snapshot(snapshot,root,archive,edited=('code.py',))

    def test_corrupt_archive_cannot_hide_code_drift(self):
        with TemporaryDirectory() as tmp:
            root=Path(tmp);archive=root/'archive';archive.mkdir()
            (root/'code.py').write_text('before');snapshot={'code.py':digest(root/'code.py')}
            (archive/'code.py').write_text('not before')
            with self.assertRaises(ValueError):verify_snapshot(snapshot,root,archive,edited=('code.py',))

    def test_replay_compares_raw_claims_not_new_answers(self):
        case=dict(id='T1',query='q',documents=[dict(source_id='S1',filename='a.pdf',chunk_text='A; B')])
        raw='{"status":"answered","claims":[{"text":"A; B.","evidence_ids":["S1:E0001"]}]}'
        answer,binding=v1.render_claim_answer(raw,v1.build_catalog(case['documents']))
        record=dict(id='T1',mode='claim_bound',status='ok',input_sha256=value_hash(case),finish_reason='stop',
            raw_content=raw,answer=answer,binding=binding,guard_status=binding['status'])
        r=asyncio.run(replay_one(case,record))
        self.assertEqual(r['answer'],'A; B. [S1]');self.assertEqual(r['live_calls'],0)
        corrupt=copy.deepcopy(record);corrupt['answer']='forged'
        with self.assertRaises(ValueError):asyncio.run(replay_one(case,corrupt))


if __name__=='__main__':unittest.main()
