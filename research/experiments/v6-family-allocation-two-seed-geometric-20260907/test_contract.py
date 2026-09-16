import unittest
import run_trial as t

class Tests(unittest.TestCase):
    def test_capacity(self):
        self.assertEqual(t.old.CAPACITY, {'control':9, 'expanded':9})
    def test_no_smoke_descendants(self):
        for seed in (1,3):
            for arm in ('control','expanded'):
                p = t.parent_path(seed,arm,1)
                self.assertEqual(p.parent.parent.name, 'derived')
                self.assertNotIn('smoke_v3', str(p))
    def test_dose_and_resume(self):
        for seed in (1,3):
            for arm in ('control','expanded'):
                argv = t.old.training_command(seed,arm,2)
                self.assertEqual(int(argv[argv.index('--total-environment-hands')+1]), t.old.INITIAL[seed]+1048576)
                self.assertEqual(argv[argv.index('--resume')+1], str(t.old.directory(seed,arm,1)/'latest.pt'))
    def test_fixed_order_and_deck_seeds(self):
        self.assertEqual(len(set(t.old.EVAL_SEEDS.values())),4)
        self.assertEqual(t.old.ORDER, [(1,'control'),(1,'expanded'),(3,'expanded'),(3,'control')])

if __name__ == '__main__': unittest.main()
