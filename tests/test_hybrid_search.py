import math
import unittest
from copy import deepcopy

from backend.Database.milvus_server.hybrid_search import BM25Index, fuse_rrf, tokenize


def document(cid, text, filename='paper.pdf', **extra):
    return dict(id=cid, chunk_text=text, filename=filename, file_id=filename,
                metadata={'chunk_id': cid}, **extra)


class BM25Tests(unittest.TestCase):
    # AC-5102
    def test_tokenization_case_width_punctuation_cjk_and_formula(self):
        self.assertEqual(tokenize('ＢＥＲＴ GPT-4 论文方法 sqrt(d_k)'),
                         ['bert', 'gpt', '4', '论文', '文方', '方法', 'sqrt', 'd', 'k'])

    def test_exact_term_from_outside_dense_pool(self):
        corpus = [document('a', 'general semantic paper'), document('b', 'rarekey rarekey')]
        self.assertEqual(BM25Index(corpus).search('RAREKEY', 10)[0]['id'], 'b')
        self.assertEqual(BM25Index(corpus).search('unseen', 10), [])
        self.assertEqual(BM25Index(corpus).search('', 10), [])
        self.assertEqual(BM25Index([]).search('rarekey', 10), [])

    def test_bm25_formula_and_corpus_not_mutated(self):
        corpus = [document('a', 'term term'), document('b', 'other other')]
        original = deepcopy(corpus)
        result = BM25Index(corpus).search('term term', 1)
        expected = math.log(1 + 1.5 / 1.5) * 2 * 2.2 / (2 + 1.2)
        self.assertAlmostEqual(result[0]['bm25_score'], expected)
        self.assertEqual(corpus, original)

    def test_stable_tie_and_duplicate_rows_rejected(self):
        self.assertEqual([d['id'] for d in BM25Index([
            document('b', 'same'), document('a', 'same')]).search('same', 2)], ['a', 'b'])
        with self.assertRaisesRegex(ValueError, 'duplicate'):
            BM25Index([document('a', 'same'), document('a', 'different')])


class RRFTests(unittest.TestCase):
    # AC-5103
    def test_union_provenance_and_repeated_contribution(self):
        dense = [document('a', 'a', score=.8), document('b', 'b', score=.7)]
        lexical = [document('b', 'b', bm25_score=4), document('c', 'c', bm25_score=2)]
        fused = fuse_rrf(dense, lexical, 3)
        self.assertEqual([d['id'] for d in fused], ['b', 'a', 'c'])
        self.assertAlmostEqual(fused[0]['score'], 1/62 + 1/61)
        self.assertEqual(fused[0]['branch_ranks'], {'dense': 2, 'bm25': 1})
        self.assertEqual(fused[0]['dense_score'], .7)
        self.assertEqual(fused[0]['bm25_score'], 4)
        self.assertIsNone(fused[-1]['dense_score'])
        self.assertEqual(fused[-1]['score_type'], 'hybrid_rrf')
        duplicate = fuse_rrf([dense[0], dense[0]], [], 3)
        self.assertAlmostEqual(duplicate[0]['score'], 1/61)

    def test_tie_is_deterministic_and_inputs_unchanged(self):
        dense, lexical = [document('b', 'b', score=.9)], [document('a', 'a', bm25_score=1)]
        original = deepcopy((dense, lexical))
        self.assertEqual([d['id'] for d in fuse_rrf(dense, lexical, 10)], ['a', 'b'])
        self.assertEqual((dense, lexical), original)
        self.assertEqual(fuse_rrf([], [], 10), [])
        with self.assertRaises(ValueError):
            fuse_rrf(dense, lexical, 1, rrf_k=0)


if __name__ == '__main__':
    unittest.main()
