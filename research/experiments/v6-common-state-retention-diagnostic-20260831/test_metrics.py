import math
import unittest
from metrics import distribution_metrics, summarize


class MetricTests(unittest.TestCase):
    def test_identity_and_entropy(self):
        p = [.25, .75]+[0.0]*7
        result = distribution_metrics(p, p, [1, 1]+[0]*7)
        for key in ['total_variation', 'jensen_shannon', 'source_to_candidate_kl_floor', 'candidate_to_source_kl_floor', 'argmax_disagreement']:
            self.assertAlmostEqual(result[key], 0)
        self.assertAlmostEqual(result['entropy_nats'], -.25*math.log(.25)-.75*math.log(.75))

    def test_disjoint_and_declared_floor(self):
        result = distribution_metrics([1, 0]+[0]*7, [0, 1]+[0]*7, [1, 1]+[0]*7)
        self.assertEqual(result['total_variation'], 1)
        self.assertAlmostEqual(result['jensen_shannon'], math.log(2))
        self.assertAlmostEqual(result['source_to_candidate_kl_floor'], math.log(1e12), places=8)
        self.assertEqual(result['source_clipped_entries'], 1)
        self.assertEqual(result['candidate_clipped_entries'], 1)

    def test_nonlegal_mass_and_nonfinite_rejected(self):
        for p in [[.5, .5]+[0]*7, [float('nan'), 0]+[0]*7, [.9, 0]+[0]*7]:
            with self.assertRaises(ValueError): distribution_metrics(p, [1]+[0]*8, [1]+[0]*8)

    def test_hand_weighting_not_state_iid(self):
        rows = [dict(hand_index=0, metrics={'treatment':{'total_variation':0}})]
        rows += [dict(hand_index=1, metrics={'treatment':{'total_variation':1}}) for _ in range(3)]
        result = summarize(rows)
        self.assertEqual(result['state_weighted']['treatment']['total_variation'], .75)
        self.assertEqual(result['hand_weighted']['treatment']['total_variation'], .5)

    def test_direction_and_bounds(self):
        p, q = [.1, .9]+[0]*7, [.7, .3]+[0]*7
        a, b = distribution_metrics(p, q, [1, 1]+[0]*7), distribution_metrics(q, p, [1, 1]+[0]*7)
        self.assertAlmostEqual(a['total_variation'], b['total_variation'])
        self.assertAlmostEqual(a['jensen_shannon'], b['jensen_shannon'])
        self.assertAlmostEqual(a['source_to_candidate_kl_floor'], b['candidate_to_source_kl_floor'])


if __name__ == '__main__': unittest.main()
