import copy
import unittest
from family_weights import stratify, bind_families

class Tests(unittest.TestCase):
    def test_mass_and_ratios(self):
        w = [i / 45 for i in range(1, 10)]
        out = stratify(w, range(9), range(3), range(3, 7))
        self.assertAlmostEqual(sum(out[:3]), .5)
        self.assertAlmostEqual(sum(out[3:7]), .25)
        self.assertAlmostEqual(sum(out[7:]), .25)
        for indices in (range(3), range(3, 7), range(7, 9)):
            for i in indices:
                for j in indices:
                    self.assertAlmostEqual(out[i] / out[j], w[i] / w[j])

    def test_permutation_and_turnover(self):
        ids = [0, 1, 2, 10, 11, 12, 13, 100, 101]
        w = [1 / 9] * 9
        a = stratify(w, ids, {0, 1, 2}, {10, 11, 12, 13})
        self.assertEqual(list(reversed(a)), stratify(w, list(reversed(ids)), {0, 1, 2}, {10, 11, 12, 13}))
        self.assertEqual(a, stratify(w, ids[:7] + [102, 103], {0, 1, 2}, {10, 11, 12, 13}))

    def test_input_immutable_and_idempotent(self):
        w = [1 / 9] * 9
        before = copy.deepcopy(w)
        out = stratify(w, range(9), range(3), range(3, 7))
        self.assertEqual(w, before)
        again = stratify(out, range(9), range(3), range(3, 7))
        for a, b in zip(out, again):
            self.assertAlmostEqual(a, b)

    def test_reject_invalid(self):
        for w in ([0] * 9, [float('nan')] * 9, [-1] + [0.25] * 8, [0] * 3 + [1 / 6] * 6):
            with self.assertRaises(ValueError):
                stratify(w, range(9), range(3), range(3, 7))
        with self.assertRaises(ValueError):
            stratify([1 / 9] * 9, [0] * 9, range(3), range(3, 7))

    def test_hash_identity(self):
        snaps = [{'id': i + 100, 'score_components': {'kind': 'initial_external_opponent', 'checkpoint_sha256': str(i)}} for i in range(7)]
        before = copy.deepcopy(snaps)
        old, added = bind_families(list(reversed(snaps)), {'0', '1', '2'}, {'3', '4', '5', '6'})
        self.assertEqual(old, {100, 101, 102})
        self.assertEqual(added, {103, 104, 105, 106})
        self.assertEqual(snaps, before)
        with self.assertRaises(ValueError):
            bind_families(snaps + [snaps[0]], {'0', '1', '2'}, {'3', '4', '5', '6'})

if __name__ == '__main__':
    unittest.main()
