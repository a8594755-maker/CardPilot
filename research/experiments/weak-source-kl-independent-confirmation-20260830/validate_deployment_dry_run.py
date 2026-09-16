"""Zero-hand CPU deployment load with network calls blocked in this process."""
import contextlib
import json
from pathlib import Path
import runpy
import sys
from unittest.mock import patch

import requests
import torch

from run_confirmation import BASE, CANDIDATES, sha, verify_inputs, verify_sources


def main():
    verify_inputs()
    copies = json.loads((BASE/'execution_code/copy_manifest.json').read_text())
    verify_sources(copies)
    checkpoint, digest = CANDIDATES[2][1:]
    directory = BASE/'deployment_readiness'
    directory.mkdir(exist_ok=False)
    script = BASE/'execution_code/source_files/scripts/alpha_holdem/play_slumbot.py'
    output = directory/'zero_hand_result.json'
    arguments = [str(script), '--model', str(checkpoint), '--hands', '0', '--device', 'cpu',
        '--strategy', 'model', '--policy-mode', 'sample', '--temperature', '1',
        '--policy-seed', '2026090900', '--strict-policy-execution',
        '--torch-threads', '1', '--torch-interop-threads', '1', '--result-json', str(output)]
    blocked_calls = []

    def deny_network(*args, **kwargs):
        blocked_calls.append('attempted_network_call')
        raise AssertionError('Zero-hand readiness must not contact any network')

    with (directory/'loader_stdout.log').open('x', encoding='utf-8') as log:
        with patch.object(sys, 'argv', arguments), patch.object(requests.sessions.Session, 'request', deny_network), \
             patch('socket.socket.connect', deny_network), patch('socket.create_connection', deny_network), \
             contextlib.redirect_stdout(log), contextlib.redirect_stderr(log):
            runpy.run_path(str(script), run_name='__main__')
    result = json.loads(output.read_text())
    expected = dict(model_sha256=digest, requested_hands=0, successful_hands=0, dry_run=True,
        device='cpu', strategy='model', obs_version='v4', policy_mode_raw='sample',
        temperature=1., starting_stack_bb=200., policy_seed=2026090900,
        strict_policy_execution=True, http_transport='persistent_session_no_retries_v1')
    if any(result.get(key) != value for key, value in expected.items()) or blocked_calls:
        raise ValueError('Zero-hand identity/selector/no-network contract failed')
    if any(result.get(key) is not None for key in ['bb_per_100', 'ci95_bb_per_100', 'significant_winner']):
        raise ValueError('Zero-hand loader must not report a performance result')
    verify_inputs()
    verify_sources(copies)
    summary = dict(status='PASS', actual_training_hands=0, actual_evaluation_hands=0,
        actual_slumbot_hands=0, network_calls_attempted=len(blocked_calls), source_sha256=sha(script),
        checkpoint_sha256=sha(checkpoint), validation_script_sha256=sha(__file__),
        loader_result_sha256=sha(output), client_argv=arguments,
        claim_scope='checkpoint_loading_and_selector_metadata_only_not_action_quality_or_external_admission')
    (directory/'readiness_analysis.json').write_text(json.dumps(summary, indent=2, sort_keys=True)+'\n')
    print(json.dumps(dict(status='PASS', actual_poker_hands=0, network_calls_attempted=0,
                         checkpoint_sha256=digest)))


if __name__ == '__main__':
    main()
