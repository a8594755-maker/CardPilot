"""Zero-hand reviewer guards, independent from the live evaluator."""
import copy
import unittest
from review import validate_row, stats


class ReviewTests(unittest.TestCase):
    def test_exact_row(self):
        row=dict(seed=1,anchor='a',anchor_index=0,pair_index=0,deck=list(range(52)),
                 policy='parent',seat=0,action_seed=7,reward_bb=0.5,decisions=2)
        args=(1,'a',0,0,list(range(52)),'parent',0,7)
        validate_row(row,*args)
        for key,value in [('seed',3),('policy','endpoint'),('seat',1),('action_seed',8),
                          ('deck',list(reversed(range(52)))),('reward_bb',float('nan')),
                          ('reward_bb',201),('decisions',0),('decisions',True)]:
            bad=copy.deepcopy(row); bad[key]=value
            with self.subTest(key=key,value=value),self.assertRaises(AssertionError):
                validate_row(bad,*args)

    def test_constant_ci(self):
        result=stats([2,2,2,2])
        self.assertEqual(result['bb100'],200)
        self.assertEqual(result['ci95_low_bb100'],200)

    def test_ci_scale(self):
        result=stats([-1,1])
        self.assertEqual(result['bb100'],0)
        self.assertAlmostEqual(result['ci95_high_bb100'],196)


if __name__=='__main__': unittest.main()
