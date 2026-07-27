import unittest
from pathlib import Path

from v5_exp005c_arm_endpoint_freeze_watch import config_errors, endpoint_errors


class EndpointFreezeWatchTests(unittest.TestCase):
    def test_config_exact_subset_and_float_equivalence(self):
        self.assertEqual([], config_errors({'lr': 0.0003, 'workers': 22}, {'lr': 3e-4, 'workers': 22}))
        self.assertTrue(config_errors({'lr': 0.001}, {'lr': 3e-4}))

    def test_endpoint_budget_and_identity(self):
        source = Path('source.pt').resolve()
        expected = {'workers': 22, 'assignment_provenance_schema': 'v5.opponent_assignment_provenance.v1'}
        manifest = {
            'run_id': 'r', 'status': 'finished', 'config': {'workers': 22},
            'lineage_parent_checkpoint': str(source), 'iteration': 32617, 'total_hands': 536000000,
        }
        checkpoint = {
            'iteration': 32617, 'total_hands': 536000000, 'env_version': 'v55',
            'obs_version': 'v55', 'action_space_version': '9slot_v5',
        }
        self.assertEqual([], endpoint_errors(
            manifest=manifest, checkpoint=checkpoint, expected_run_id='r',
            expected_config=expected, expected_source=source,
            minimum_hands=535989661, maximum_overshoot=50000,
        ))
        checkpoint['total_hands'] = 536100000
        self.assertTrue(endpoint_errors(
            manifest=manifest, checkpoint=checkpoint, expected_run_id='r',
            expected_config=expected, expected_source=source,
            minimum_hands=535989661, maximum_overshoot=50000,
        ))

    def test_runtime_contract_requires_exact_health_and_empty_stderr(self):
        source = Path(__file__).with_name('v5_exp005c_arm_endpoint_freeze_watch.py').read_text(encoding='utf-8')
        self.assertIn('WAITING_FOR_EXACT_ENDPOINT_HEALTH', source)
        self.assertIn("health.get('overall') != 'PASS'", source)
        self.assertIn("stderr_path.stat().st_size != 0", source)


if __name__ == '__main__':
    unittest.main()
