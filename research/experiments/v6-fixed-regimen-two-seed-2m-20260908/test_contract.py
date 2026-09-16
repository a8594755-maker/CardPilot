import unittest
import run_probe as trial


class ContractTests(unittest.TestCase):
    def test_only_lifecycle_command_changes(self):
        allowed={'--resume','--run-dir','--out','--total-environment-hands','--max-runtime-seconds','--deal-attempt-registry','--opponent-assignment-provenance-file'}
        for seed in (1,3):
            original=trial.old.read(trial.prior.PARENT/f'seed{seed}_control_stage2/command.json')
            actual=trial.old.training_command(seed,'control',1)
            self.assertEqual(len(actual),len(original))
            for i,(left,right) in enumerate(zip(original,actual)):
                if left!=right:
                    self.assertTrue(i in (0,2) or original[i-1] in allowed,(i,left,right))
            self.assertNotIn('--gradient-diagnostic-minibatches',actual)
            self.assertIn('--no-reset-optimizer',actual)
            self.assertIn('--preserve-resumed-optimizer-lr',actual)
            self.assertIn('--managed-deal-attempts',actual)
            self.assertNotIn('--reset-hand-counter',actual)

    def test_fixed_scope_and_original_parents(self):
        self.assertEqual(trial.old.DOSES,{1:1048576})
        self.assertEqual(trial.old.ORDER,[(1,'control'),(3,'control')])
        for seed in (1,3):
            self.assertEqual(trial.old.parent_path(seed,'control',1),trial.prior.PARENT/f'seed{seed}_control_stage2/latest.pt')
            self.assertEqual(trial.old.CAPACITY['control'],9)


if __name__=='__main__':unittest.main()
