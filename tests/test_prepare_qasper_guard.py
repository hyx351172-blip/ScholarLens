import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('prepare', Path(__file__).parent/'integration/prepare_qasper_guard.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class QasperPreparationTests(unittest.TestCase):
    def qa(self, flags, evidence):
        return {'answers': [{'answer': {'unanswerable': flag, 'evidence': evidence}} for flag in flags]}

    def test_disagreement_is_not_unanswerable(self):
        self.assertEqual(module.eligibility(self.qa([True, False], []), []), (None, 'annotation_disagreement'))

    def test_real_unanswerable(self):
        self.assertEqual(module.eligibility(self.qa([True, True], []), ['text']), ('unanswerable', None))

    def test_text_evidence_must_map(self):
        self.assertEqual(module.eligibility(self.qa([False], ['Supported text.']), ['Supported text.']), ('answerable', None))
        self.assertEqual(module.eligibility(self.qa([False], ['Other']), ['Supported text.'])[1], 'evidence_not_mapped')

    def test_visual_evidence_excluded(self):
        self.assertEqual(module.eligibility(self.qa([False], ['FLOAT SELECTED table']), ['text'])[1], 'missing_or_visual_evidence')

    def test_normalization(self):
        self.assertEqual(module.normalize('What IS this?'), module.normalize('what is this'))

    def test_new_batch_is_deterministic_and_paper_disjoint(self):
        data = {}
        for i in range(8):
            qa = self.qa([i % 2 == 0], ['text'])
            qa.update(question=f'question {i}', question_id=str(i))
            data[str(i)] = {'abstract': 'text', 'qas': [qa]}
        kwargs = dict(targets={'answerable': 2, 'unanswerable': 2},
                      excluded_papers={'0', '1'}, seed='validation')
        selected = module.select(data, set(), **kwargs)[0]
        self.assertEqual(selected, module.select(data, set(), **kwargs)[0])
        self.assertEqual(len(selected), 4)
        self.assertEqual(len({x[1] for x in selected}), 4)
        self.assertFalse({x[1] for x in selected} & {'0', '1'})
