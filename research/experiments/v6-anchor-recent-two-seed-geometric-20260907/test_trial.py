import unittest
import run_trial as t

class TrialTests(unittest.TestCase):
    def test_matched_parent(self):
        for seed in (1,3):
            self.assertEqual(t.parent_path(seed,'control',1),t.parent_path(seed,'recent',1))

    def test_stage_two_continuity(self):
        for seed,arm in t.ORDER:
            self.assertEqual(t.parent_path(seed,arm,2),t.directory(seed,arm,1)/'latest.pt')

    def test_no_counter_reset(self):
        self.assertEqual(t.additional_count(12595670,12595669),1)
        with self.assertRaises(ValueError): t.additional_count(1,12595669)

    def test_target_and_optimizer(self):
        for stage in t.DOSES:
            for seed,arm in t.ORDER:
                argv=t.training_command(seed,arm,stage)
                self.assertEqual(int(argv[argv.index('--total-environment-hands')+1]),t.INITIAL[seed]+t.DOSES[stage])
                for flag in ('--no-reset-optimizer','--preserve-resumed-optimizer-lr','--preflop-trunk-gradient','--managed-deal-attempts'):
                    self.assertEqual(argv.count(flag),1)

    def test_only_pool_algorithm_differs(self):
        for seed in (1,3):
            for stage in t.DOSES:
                commands=[]
                for arm in t.STRATEGIES:
                    argv=t.training_command(seed,arm,stage)
                    for flag in ('--pool-strategy','--run-dir','--out','--resume','--opponent-assignment-provenance-file'):
                        self.assertEqual(argv.count(flag),1)
                        argv[argv.index(flag)+1]='<matched>'
                    commands.append(argv)
                self.assertEqual(*commands)

    def test_unique_evaluation_seeds(self):
        seeds=[v+1000003*i for v in t.EVAL_SEEDS.values() for i in range(4)]
        self.assertEqual(len(set(seeds)),16)

    def test_invalid_cell(self):
        for cell in ((2,'recent',1),(1,'unknown',1),(1,'recent',3)):
            with self.assertRaises(ValueError): t.directory(*cell)

if __name__ == '__main__': unittest.main()
