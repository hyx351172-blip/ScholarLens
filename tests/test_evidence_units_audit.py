import asyncio
import copy
import json
import unittest
from unittest.mock import AsyncMock, patch

from backend.chat import evidence_units as units
from tests.integration.audit_evidence_units import assert_coverage, inner_cuts, candidate_packet


class AuditTests(unittest.TestCase):
    # AC-3706
    def test_audit_detects_gaps_and_rewriting(self):
        docs = [dict(filename='a.pdf', chunk_text='First sentence. Second sentence.')]
        catalog = units.build_catalog(docs)
        assert_coverage(docs, catalog)
        for field, value in (('start',1), ('text','forged')):
            bad = copy.deepcopy(catalog); bad[0][field] = value
            with self.assertRaises(ValueError): assert_coverage(docs, bad)
        with self.assertRaises(ValueError): assert_coverage(docs, catalog[:-1])

    def test_inner_cut_diagnostic_is_not_a_semantic_metric(self):
        docs = [dict(filename='a.pdf',chunk_text='An intact sentence. Another sentence.')]
        self.assertEqual(inner_cuts(docs, units.build_catalog(docs)), [])
        cut = [dict(source_id='S1', anchor_id='old', end=5)]
        self.assertEqual(inner_cuts(docs, cut)[0]['end'], 5)

    def test_actual_candidate_packet_is_captured_without_provider(self):
        case = dict(id='fixture', query='q', documents=[dict(filename='a.pdf',chunk_text='First sentence.')])
        with patch('openai.resources.chat.completions.AsyncCompletions.create',
                   AsyncMock(side_effect=AssertionError('network forbidden'))) as external:
            request = asyncio.run(candidate_packet(case))
            external.assert_not_awaited()
        content = json.loads(request['messages'][1]['content'])
        self.assertEqual(content['evidence_catalog_version'], 'sentence_v2')
        self.assertEqual(content['evidence'][0]['text'], 'First sentence.')
        self.assertNotIn('offline-placeholder', json.dumps(request))
        self.assertIsNone(asyncio.run(candidate_packet(dict(documents=[]))))


if __name__ == '__main__': unittest.main()
