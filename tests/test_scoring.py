import unittest

from rubric.rubric import CRITERIA
from rubric.scoring import total_score


def all_scores(n):
    return {c.id: n for c in CRITERIA}


class TotalScoreTests(unittest.TestCase):
    def test_all_ones_is_zero(self):
        self.assertEqual(total_score(all_scores(1)), 0)

    def test_all_fives_is_hundred(self):
        self.assertEqual(total_score(all_scores(5)), 100)

    def test_all_threes_is_fifty(self):
        self.assertAlmostEqual(total_score(all_scores(3)), 50)

    def test_weights_matter(self):
        heavy = max(CRITERIA, key=lambda c: c.weight)
        light = min(CRITERIA, key=lambda c: c.weight)
        a = all_scores(1) | {heavy.id: 5}
        b = all_scores(1) | {light.id: 5}
        self.assertGreater(total_score(a), total_score(b))

    def test_missing_score_is_incomplete(self):
        scores = all_scores(5)
        scores.pop(CRITERIA[0].id)
        self.assertIsNone(total_score(scores))

    def test_out_of_range_is_incomplete(self):
        self.assertIsNone(total_score(all_scores(5) | {CRITERIA[0].id: 6}))
        self.assertIsNone(total_score(all_scores(5) | {CRITERIA[0].id: 0}))

    def test_unknown_ids_ignored(self):
        self.assertEqual(total_score(all_scores(5) | {"removed": 1}), 100)

    def test_rubric_is_well_formed(self):
        ids = [c.id for c in CRITERIA]
        self.assertEqual(len(ids), len(set(ids)))
        for c in CRITERIA:
            self.assertGreater(c.weight, 0)
            self.assertEqual(len(c.levels), 5)


if __name__ == "__main__":
    unittest.main()
