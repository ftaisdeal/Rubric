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
        heavy, light = CRITERIA[0], CRITERIA[1]
        weights = {c.id: 10 for c in CRITERIA} | {heavy.id: 30}
        a = all_scores(1) | {heavy.id: 5}
        b = all_scores(1) | {light.id: 5}
        self.assertGreater(total_score(a, weights), total_score(b, weights))

    def test_default_weights_total_100(self):
        self.assertEqual(sum(c.weight for c in CRITERIA), 100)

    def test_custom_weights_override_defaults(self):
        a, b = CRITERIA[0].id, CRITERIA[1].id
        weights = {c.id: 0 for c in CRITERIA} | {a: 100}
        self.assertEqual(total_score(all_scores(1) | {a: 5}, weights), 100)
        self.assertEqual(total_score(all_scores(1) | {b: 5}, weights), 0)

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
