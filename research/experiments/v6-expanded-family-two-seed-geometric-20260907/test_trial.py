import unittest
import run_trial as t
class Tests(unittest.TestCase):
    def test_parents(self):
        for seed in (1,3):
            self.assertNotEqual(t.parent_path(seed,'control',1),t.parent_path(seed,'expanded',1))
            for arm in t.STRATEGIES: self.assertEqual(t.parent_path(seed,arm,2),t.directory(seed,arm,1)/'latest.pt')
    def test_doses(self):
        self.assertEqual(t.DOSES,{1:262144,2:1048576})
        self.assertEqual(t.MIXTURES,{'control':0.,'expanded':0.})
    def test_commands(self):
        for seed,arm in t.ORDER:
            c=t.training_command(seed,arm,1)
            self.assertEqual(c.count('--opponent-greedy-mixture'),1)
            self.assertEqual(c[c.index('--opponent-greedy-mixture')+1],'0.0')
            self.assertEqual(int(c[c.index('--k-best')+1]),t.CAPACITY[arm])
            self.assertEqual(int(c[c.index('--total-environment-hands')+1]),t.INITIAL[seed]+262144)
    def test_order(self):
        self.assertEqual(set(t.ORDER),{(1,'control'),(1,'expanded'),(3,'control'),(3,'expanded')})
        self.assertEqual(len(set(t.EVAL_SEEDS.values())),4)
if __name__=='__main__': unittest.main()
