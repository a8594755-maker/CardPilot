from __future__ import annotations

import unittest
from pathlib import Path


SCRIPT = Path(__file__).with_name('v5_continue_after_gate.ps1')


class ContinueDesignLockContractTest(unittest.TestCase):
    def test_execute_is_fail_closed_on_immutable_design_lock(self):
        source = SCRIPT.read_text(encoding='utf-8')
        self.assertIn('[string]$DesignLockPath = ""', source)
        self.assertIn('[string]$ExpectedDesignLockSha256 = ""', source)
        self.assertIn('[string]$DesignArm = ""', source)
        self.assertIn('Execute requires -DesignLockPath, -ExpectedDesignLockSha256, and -DesignArm', source)
        self.assertIn('v5_cutover_design_lock_verify.py', source)
        self.assertIn('immutable design-lock preflight failed; refusing trainer launch', source)
        self.assertIn('Design-locked cutover forbids inline watcher launch', source)
        execute_guard = source.index('Execute requires -DesignLockPath')
        stop_old = source.index('stopping old trainer PID')
        launch = source.index('launching continuation trainer')
        self.assertLess(execute_guard, stop_old)
        self.assertLess(execute_guard, launch)

    def test_locked_reproducibility_flags_are_explicit(self):
        source = SCRIPT.read_text(encoding='utf-8')
        for token in (
            '"--ppo-epochs"',
            '"--mini-batch-size"',
            '"--epsilon"',
            '"--seed"',
            '"--worker-seed-base"',
            '"--fixed-training-deal-stream"',
            '"--opponent-assignment-provenance-file"',
            'assignment_provenance_schema = "v5.opponent_assignment_provenance.v1"',
        ):
            self.assertIn(token, source)

    def test_exp_w1_copy_source_is_verified_before_and_after_copy(self):
        source = SCRIPT.read_text(encoding='utf-8')
        for token in (
            '[int]$ExpW1ValueWarmupEpochs = 0',
            '"--exp-w1-value-warmup-epochs"',
            '"--exp-w1-design-lock"',
            '"--exp-w1-design-lock-sha256"',
            '$trainerAbs = Resolve-RepoPath $TrainerCopySource',
            'post-copy immutable design-lock verification failed; refusing trainer launch',
        ):
            self.assertIn(token, source)
        preflight = source.index('verifying immutable cutover design lock')
        copy_step = source.index('Copy-Item -LiteralPath $trainerCopySourceAbs -Destination $liveTrainerPath -Force')
        postcopy = source.index('post-copy immutable design-lock verification failed')
        launch = source.index('launching continuation trainer')
        self.assertLess(preflight, copy_step)
        self.assertLess(copy_step, postcopy)
        self.assertLess(postcopy, launch)


if __name__ == '__main__':
    unittest.main()
