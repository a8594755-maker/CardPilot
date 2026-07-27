from __future__ import annotations

import unittest
from pathlib import Path

from v5_pilot_endpoint_stop_watch import preconditions


class PilotEndpointStopWatchTest(unittest.TestCase):
    def test_exact_identity_passes_and_mismatch_fails(self):
        run_dir = Path('C:/runs/pilot')
        manifest = {'run_id': 'pilot', 'process_id': 123, 'status': 'running'}
        gate = {
            'overall': 'PASS', 'run_id': 'pilot', 'target_iteration': 32700,
            'checkpoint_iteration': 32700, 'checkpoint_hands': 536000000,
        }
        command = ['python', 'train_v5.py', '--run-dir', str(run_dir.resolve())]
        self.assertEqual(
            preconditions(run_dir=run_dir, expected_pid=123, target_iteration=32700,
                          min_hands=535989661, gate=gate, manifest=manifest,
                          process_cmdline=command),
            [],
        )
        gate['checkpoint_iteration'] = 32600
        errors = preconditions(run_dir=run_dir, expected_pid=123, target_iteration=32700,
                               min_hands=535989661, gate=gate, manifest=manifest,
                               process_cmdline=command)
        self.assertIn('checkpoint iteration is not exact target', errors)


if __name__ == '__main__':
    unittest.main()
