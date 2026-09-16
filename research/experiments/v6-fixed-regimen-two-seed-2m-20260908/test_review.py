import math
import unittest
from review import stats, summarize


class ReviewTests(unittest.TestCase):
    def test_units_and_sample_variance(self):
        result=stats([1.,3.])
        self.assertEqual(result['bb100'],200.)
        self.assertAlmostEqual(result['se_bb100'],100.)
        self.assertAlmostEqual(result['ci95'][0],4.)

    def test_invalid_samples(self):
        for sample in ([],[1.],[0.,math.nan],[0.,math.inf]):
            with self.assertRaises(AssertionError):stats(sample)

    def test_mirrored_pair_cancellation_and_seats(self):
        anchors=[f'anchor{i}' for i in range(8)]
        rows=[dict(anchor=a,control_rewards_bb=[0.,0.],treatment_rewards_bb=[1.,-1.]) for a in anchors for _ in range(2)]
        result=summarize(rows,anchors)
        self.assertEqual(result['pooled']['bb100'],0.)
        self.assertEqual(result['pooled']['ci95'],[0.,0.])
        self.assertEqual(result['pooled']['paired_decks'],16)
        self.assertEqual(result['by_seat']['0']['bb100'],100.)
        self.assertEqual(result['by_seat']['1']['bb100'],-100.)

    def test_panel_identity_not_hardcoded(self):
        anchors=[f'new{i}' for i in range(8)]
        rows=[dict(anchor=a,control_rewards_bb=[2.,2.],treatment_rewards_bb=[3.,3.] if i<4 else [1.,1.]) for i,a in enumerate(anchors) for _ in range(2)]
        result=summarize(rows,anchors)
        self.assertEqual(result['by_panel']['preservation']['pooled']['bb100'],100.)
        self.assertEqual(result['by_panel']['transfer']['pooled']['bb100'],-100.)
        self.assertEqual(set(result['by_anchor']),set(anchors))


if __name__=='__main__':unittest.main()
