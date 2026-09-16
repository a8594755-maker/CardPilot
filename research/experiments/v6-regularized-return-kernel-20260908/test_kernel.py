import json
import math
from pathlib import Path
import unittest
from regularized_return import transformed_returns as transform


class KernelTests(unittest.TestCase):
    def test_eta_zero(self):
        self.assertEqual(transform([0,1],[-1,-2],[-2,-1],[3,-3],0)['returns_bb'],[(3,-3),(3,-3)])

    def test_identity_reference(self):
        self.assertEqual(transform([0,1],[-1,-2],[-1,-2],[3,-3],2)['returns_bb'],[(3,-3),(3,-3)])

    def test_opponent_sign_and_future_propagation(self):
        result=transform([0,1],[-1,-1],[-2,-3],[0,0],1)
        self.assertEqual(result['shaping_rewards_bb'],[(-1,1),(2,-2)])
        self.assertEqual(result['returns_bb'],[(1,-1),(2,-2)])

    def test_label_swap(self):
        a=transform([0,1,0],[-1,-2,-3],[-2,-1,-2],[4,-4],0.2)
        b=transform([1,0,1],[-1,-2,-3],[-2,-1,-2],[-4,4],0.2)
        self.assertEqual(a['returns_bb'],[tuple(reversed(x)) for x in b['returns_bb']])
        self.assertTrue(all(sum(x)==0 for x in a['returns_bb']))

    def test_expected_penalty_is_kl(self):
        policy=[0.25,0.75]; reference=[0.5,0.5]
        expected=sum(p*transform([0],[math.log(p)],[math.log(q)],[0,0],2)['returns_bb'][0][0]
                     for p,q in zip(policy,reference))
        self.assertAlmostEqual(expected,-2*sum(p*math.log(p/q) for p,q in zip(policy,reference)))

    def test_guards(self):
        for args in [([2],[-1],[-1],[0,0],1),([0],[-1],[],[0,0],1),
                     ([0],[float('nan')],[-1],[0,0],1),([0],[1],[-1],[0,0],1),
                     ([0],[-1],[-1],[1,1],1),([0],[-1],[-1],[0,0],-1)]:
            with self.subTest(args=args),self.assertRaises(ValueError): transform(*args)


if __name__=='__main__':
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(KernelTests))
    path=Path(__file__).with_name('test_result.json')
    with path.open('x',encoding='utf-8') as handle:
        json.dump(dict(passed=result.wasSuccessful(),tests=result.testsRun,training_hands=0,evaluation_hands=0),handle)
    raise SystemExit(0 if result.wasSuccessful() else 1)
