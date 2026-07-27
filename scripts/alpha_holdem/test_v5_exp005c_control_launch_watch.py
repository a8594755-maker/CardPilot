import re
import unittest
from pathlib import Path


SCRIPT = Path(__file__).with_name('v5_exp005c_control_launch_watch.ps1')


class ControlLaunchWatchContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = SCRIPT.read_text(encoding='utf-8')

    def test_requires_exact_pilot_stop_and_no_trainer(self):
        self.assertIn("'PILOT_STOPPED_AT_ENDPOINT'", self.source)
        self.assertIn("method_judgment -ne 'FORBIDDEN_EXPLORATORY_PILOT'", self.source)
        self.assertIn('ANOTHER_TRAINER_ALREADY_ALIVE', self.source)
        self.assertIn('CONTROL_RUN_DIR_ALREADY_EXISTS_REFUSE_DUPLICATE', self.source)
        self.assertIn('WAITING_FOR_CANONICAL_PILOT_WATCHER_REARM', self.source)

    def test_exact_locked_control_contract(self):
        for token in (
            '2d64d3b82700d5bea2250121a09567e78f46b6bcc486a55d593acb33bcb86007',
            "'-DesignArm','control'",
            "'-OpponentAssignment','per-iteration'",
            "'-TotalHands','535989661'",
            "'-SaveInterval','1'",
            "'-FixedTrainingDealStream'",
            "'-OpponentAssignmentProvenanceFile'",
            "'-SkipGateCheck'",
        ):
            self.assertIn(token, self.source)

    def test_no_slumbot_or_meas_launch(self):
        args_block = self.source.split('$args = @(', 1)[1].split(')', 1)[0]
        self.assertNotRegex(args_block, re.compile(r'Slumbot|MEAS', re.I))

    def test_post_launch_manifest_uses_nested_config_and_pid(self):
        self.assertIn("manifest.config.opponent_assignment -eq 'per-iteration'", self.source)
        self.assertIn('manifest.config.total_hands -eq 535989661', self.source)
        self.assertIn('manifest.process_id -eq [int]$controlTrainers[0].ProcessId', self.source)
        self.assertIn('Wait-ControlIdentity', self.source)
        self.assertIn('PostLaunchIdentityTimeoutSeconds = 90', self.source)
        self.assertIn('manifest.config.fixed_training_deal_stream', self.source)
        self.assertIn('manifest.config.worker_seed_base -eq 73000', self.source)

    def test_recovery_is_narrow_and_provenance_bound(self):
        for token in (
            'RecoverPostLaunchIdentity',
            "prior.state -ne 'POST_LAUNCH_IDENTITY_FAILURE'",
            'exact single control trainer identity did not stabilize',
            'first.applies_to_iteration -ne 31401',
            'first.total_hands_before_iteration -ne 515989661',
            'v5_rearm_watchers.ps1',
        ):
            self.assertIn(token, self.source)


if __name__ == '__main__':
    unittest.main()
