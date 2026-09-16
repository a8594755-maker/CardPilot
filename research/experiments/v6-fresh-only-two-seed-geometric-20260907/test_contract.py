import unittest
import run_trial as t

class Contract(unittest.TestCase):
    def test_same_original_roots(self):
        for seed in (1,3):self.assertEqual(t.parent_path(seed,'control',1),t.parent_path(seed,'expanded',1))
    def test_dose_and_preserved_state_flags(self):
        for seed in (1,3):
            for arm in ('control','expanded'):
                for stage in (1,2):
                    args=t.training_command(seed,arm,stage); opt=lambda k:args[args.index(k)+1]
                    self.assertEqual(int(opt('--total-environment-hands')),t.old.INITIAL[seed]+{1:262144,2:1048576}[stage])
                    self.assertEqual(float(opt('--ppo-replay-ratio')),0 if arm=='expanded' else .5)
                    self.assertEqual(opt('--ppo-replay-buffer-iterations'),'2')
                    self.assertIn('--no-reset-optimizer',args)
                    self.assertNotIn('--reset-hand-counter',args)
    def test_replay_validation(self):
        p={'ppo_replay_cumulative_rows':20,'ppo_replay_rng_state':7}
        self.assertTrue(t.replay_progress(p,p,'expanded'))
        self.assertFalse(t.replay_progress(p,p,'control'))
        self.assertFalse(t.replay_progress({**p,'ppo_replay_cumulative_rows':0},p,'expanded'))
        self.assertFalse(t.replay_progress({**p,'ppo_replay_rng_state':8},p,'expanded'))
    def test_stage2_own_parent(self):
        for seed in (1,3):
            for arm in ('control','expanded'):self.assertEqual(t.parent_path(seed,arm,2),t.old.directory(seed,arm,1)/'latest.pt')

if __name__=='__main__':unittest.main()
