import unittest
from backend.chat.structured_answer import render_answer
from backend.chat.answer_guard import INSUFFICIENT_EVIDENCE


class StructuredAnswerTests(unittest.TestCase):
    def row(self, **kwargs):
        return dict(candidate_id='C1', entity='Corpus', status='supported', answer='353 conversations',
                    evidence=[{'source_id':'S2', 'quote':'353 conversations'}], **kwargs)

    def test_supported_candidate_keeps_original_source(self):
        text, status = render_answer({'answers':[self.row()]}, {'S2':'353 conversations from 40 speakers'}, ['C1'])
        self.assertIn('[S2]', text)
        self.assertIn('353 conversations', text)
        self.assertEqual(status, 'structured_passed')

    def test_missing_candidate_fails_closed(self):
        self.assertEqual(render_answer({'answers':[self.row()]}, {'S2':'353 conversations'}, ['C1','C2'])[1], 'invalid_structure')

    def test_invalid_evidence_fails_closed(self):
        for sources in ({}, {'S2':'different content'}):
            self.assertEqual(render_answer({'answers':[self.row()]}, sources, ['C1'])[0], INSUFFICIENT_EVIDENCE)

    def test_partial_answer_not_erased(self):
        other = {'candidate_id':'C2','entity':'Simulated corpus','status':'insufficient','answer':'','evidence':[]}
        text, status = render_answer({'answers':[self.row(),other]}, {'S2':'353 conversations'}, ['C1','C2'])
        self.assertIn('353 conversations', text)
        self.assertIn('证据不足', text)
        self.assertEqual(status, 'structured_partial')

    def test_all_insufficient_and_bad_schema(self):
        for value in (None, {}, {'answers':[]}, {'answers':[{'candidate_id':'C1','entity':'X','status':'insufficient','answer':'','evidence':[]}]}):
            self.assertEqual(render_answer(value, {}, ['C1'])[0], INSUFFICIENT_EVIDENCE)

    def test_duplicate_and_injected_citations_rejected(self):
        row = self.row()
        self.assertEqual(render_answer({'answers':[row,row]}, {'S2':'353 conversations'}, ['C1'])[1], 'invalid_structure')
        row['answer'] = 'Invented [S99]'
        self.assertEqual(render_answer({'answers':[row]}, {'S2':'353 conversations'}, ['C1'])[0], INSUFFICIENT_EVIDENCE)
