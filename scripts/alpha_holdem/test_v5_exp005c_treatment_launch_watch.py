import unittest
from pathlib import Path


SOURCE = Path(__file__).with_name('v5_exp005c_treatment_launch_watch.ps1').read_text(encoding='utf-8')


class TreatmentLaunchContractTests(unittest.TestCase):
    def test_requires_valid_frozen_control_and_no_trainer(self):
        self.assertIn("control.state -ne 'ARM_ENDPOINT_FROZEN'", SOURCE)
        self.assertIn('CONTROL_ENDPOINT_HASH_MISMATCH', SOURCE)
        self.assertIn('ANOTHER_TRAINER_ALREADY_ALIVE', SOURCE)
        self.assertIn('TREATMENT_RUN_DIR_ALREADY_EXISTS_REFUSE_DUPLICATE', SOURCE)

    def test_exact_treatment_contract(self):
        for token in ("'-DesignArm','treatment'", "'-OpponentAssignment','per-group'", "'-OpponentGroups','5'", "'-TotalHands','535989661'", "'-SaveInterval','1'", "'-FixedTrainingDealStream'"):
            self.assertIn(token, SOURCE)

    def test_no_meas_or_slumbot_command(self):
        args = SOURCE.split('$a=@(', 1)[1].split("& powershell @a", 1)[0]
        self.assertNotIn('Slumbot', args)
        self.assertNotIn('MEAS', args)

    def test_post_launch_identity_wait_is_bounded_and_strict(self):
        for token in (
            'PostLaunchIdentityTimeoutSeconds = 90',
            'Wait-TreatmentIdentity',
            "m.config.opponent_assignment -eq 'per-group'",
            'm.config.fixed_training_deal_stream',
            'm.config.worker_seed_base -eq 73000',
            'timeout_seconds=$PostLaunchIdentityTimeoutSeconds',
        ):
            self.assertIn(token, SOURCE)


if __name__ == '__main__':
    unittest.main()
