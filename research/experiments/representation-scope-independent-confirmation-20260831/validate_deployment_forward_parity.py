"""Outcome-blind CPU loader/forward parity on synthetic states; zero real hands."""
import contextlib
import importlib.util
import json
from pathlib import Path
import runpy
import shutil
import sys
from unittest.mock import patch

import numpy as np
import psutil
import requests
import torch

from run_confirmation import BASE, ROOT, CANDIDATES, sha, verify_inputs, verify_sources, capture_code_provenance

PREFIXES = [
    '', 'c', 'b300', 'b300b900',
    'b300c/', 'b300c/k', 'b300c/b400', 'b300c/b400b1200',
    'b300c/b400c/', 'b300c/b400c/k', 'b300c/b400c/b1000', 'b300c/b400c/b1000b3000',
    'b300c/b400c/b1000c/', 'b300c/b400c/b1000c/k',
    'b300c/b400c/b1000c/b2600', 'b300c/b400c/b1000c/b2600b6500',
]
HOLES = [['As', 'Kd'], ['9c', '9h']]
BOARD = ['2c', '7d', 'Ts', 'Jh', 'Qh']


def main():
    if sys.argv[1:]:
        raise ValueError('No automatic rerun or alternate fixtures')
    if sys.platform == 'win32':
        psutil.Process().nice(psutil.BELOW_NORMAL_PRIORITY_CLASS)
    verify_inputs()
    copies = json.loads((BASE/'execution_code/copy_manifest.json').read_text())
    verify_sources(copies)
    directory, provenance = BASE/'deployment_forward_parity', BASE/'deployment_forward_parity_code'
    if directory.exists() or provenance.exists():
        raise ValueError('Preserve previous parity evidence; do not overwrite')
    capture_code_provenance(ROOT, provenance, [Path(__file__).relative_to(ROOT).as_posix()])
    shutil.copy2(__file__, provenance/'source_copy.py')
    if sha(__file__) != sha(provenance/'source_copy.py'):
        raise ValueError('Helper source copy mismatch')
    directory.mkdir(exist_ok=False)
    source_root = BASE/'execution_code/source_files'
    script = source_root/'scripts/alpha_holdem/play_slumbot.py'
    mirror_path = source_root/'scripts/alpha_holdem/v5_mirror_eval.py'
    checkpoint, digest = CANDIDATES[2][1:]
    arguments = [str(script), '--model', str(checkpoint), '--hands', '0', '--device', 'cpu',
        '--strategy', 'model', '--policy-mode', 'sample', '--temperature', '1',
        '--policy-seed', '2026091310', '--strict-policy-execution',
        '--torch-threads', '1', '--torch-interop-threads', '1',
        '--result-json', str(directory/'loader_result.json')]
    network_attempts, loaded, records = [], [], []
    original_load = torch.nn.Module.load_state_dict

    def capture_load(model, state, *args, **kwargs):
        result = original_load(model, state, *args, **kwargs)
        loaded.append(model)
        return result

    def deny_network(*args, **kwargs):
        network_attempts.append('attempted_network_call')
        raise AssertionError('Offline parity must not contact any network')

    result = dict(status='RUNNING', actual_training_hands=0, actual_evaluation_hands=0,
        actual_slumbot_hands=0, planned_synthetic_decisions=32, checkpoint_sha256=digest,
        helper_sha256=sha(__file__), client_script_sha256=sha(script),
        mirror_script_sha256=sha(mirror_path), client_argv=arguments,
        claim_scope='CPU_loader_and_forward_parity_for_identical_input_tensors_only',
        limitations=['Synthetic decision fixtures are not played or scored poker hands.',
            'Does not compare internal versus external observation encoders or action-size mappings.',
            'Does not test CUDA/CPU parity, identical RNG draws, statistical strength or Slumbot admission.',
            'Separate helper added after confirmation launch; no captured execution source or gate changes.'])
    failure = None
    try:
        with patch.object(requests.sessions.Session, 'request', deny_network), \
             patch('socket.socket.connect', deny_network), patch('socket.create_connection', deny_network):
            with (directory/'loader_stdout.log').open('x', encoding='utf-8') as output:
                with patch.object(sys, 'argv', arguments), patch.object(torch.nn.Module, 'load_state_dict', capture_load), \
                     contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
                    namespace = runpy.run_path(str(script), run_name='__main__')
            if len(loaded) != 1:
                raise ValueError('Expected exactly one checkpoint-loaded native model')
            external = loaded[0]
            dry = json.loads((directory/'loader_result.json').read_text())
            expected = dict(successful_hands=0, requested_hands=0, dry_run=True,
                model_sha256=digest, policy_mode_raw='sample', temperature=1.,
                obs_version='v4', starting_stack_bb=200., strict_policy_execution=True,
                http_transport='persistent_session_no_retries_v1')
            if any(dry.get(k) != v for k, v in expected.items()):
                raise ValueError('Actual deployment loader contract mismatch')
            spec = importlib.util.spec_from_file_location('frozen_parity_mirror', mirror_path)
            mirror = importlib.util.module_from_spec(spec)
            sys.modules[spec.name] = mirror
            spec.loader.exec_module(mirror)
            policy = mirror.load_policy('full_forward_parity', checkpoint, 'cpu')
            internal = policy.model
            if policy.sha256 != digest or policy.obs_version != 'v4' or policy.emulate_raise_cap1_legality:
                raise ValueError('Internal native policy identity mismatch')
            if external.training or internal.training or type(external) is not type(internal):
                raise ValueError('Loader model architecture or eval mode mismatch')
            first, second = external.state_dict(), internal.state_dict()
            if first.keys() != second.keys() or any(not torch.equal(first[k], second[k]) for k in first):
                raise ValueError('Loaded state tensors differ')
            for name in ['policy_logit_bias', 'policy_range_override', 'policy_context_override', 'preflop_strategy_profile']:
                if getattr(external, name, None) is not None:
                    raise ValueError('Unexpected external policy override')
            if external.raise_action_mapping != 'preflop_pot_fraction_v2':
                raise ValueError('Unexpected native action-size mapping metadata')
            captured = []

            def forward_hook(model, inputs, outputs):
                captured.append(([value.detach().clone() for value in inputs], outputs[0].detach().clone()))

            hook = external.register_forward_hook(forward_hook)
            try:
                with torch.inference_mode():
                    for prefix in PREFIXES:
                        state = namespace['parse_action'](prefix)
                        if 'error' in state or state['pos'] not in (0, 1) or state['st'] not in range(4):
                            raise ValueError('Invalid synthetic nonterminal fixture')
                        for hole in HOLES:
                            board = BOARD[:[0, 3, 4, 5][state['st']]]
                            captured.clear()
                            selected, info = namespace['decide_action'](external, hole, board, state,
                                state['pos'], 'cpu', greedy=False, temperature=1., obs_version='v4',
                                policy_mode='sample', return_info=True)
                            if len(captured) != 1:
                                raise ValueError('Expected exactly one native forward per synthetic decision')
                            inputs, external_logits = captured[0]
                            internal_logits, _ = internal(*inputs)
                            legal = inputs[3][0].bool()
                            if not legal.any() or not legal[selected] or not torch.isfinite(internal_logits).all():
                                raise ValueError('Invalid logits or selected action')
                            logit_error = float((internal_logits-external_logits).abs().max())
                            reported = torch.tensor(info['behavior_probs'], dtype=torch.float64)
                            reference = torch.zeros_like(reported)
                            reference[legal] = torch.softmax(internal_logits[0, legal].double(), dim=-1)
                            probability_error = float((reported-reference).abs().max())
                            if logit_error > 1e-6 or probability_error > 1e-6:
                                raise ValueError('CPU loader/forward probability mismatch')
                            if (info['policy_mode'] != 'sample' or info['temperature'] != 1.
                                    or info['direct_increment'] is not None or abs(float(reported.sum())-1.) > 1e-6
                                    or not torch.all(reported[~legal] == 0)):
                                raise ValueError('Non-native behavior probability contract')
                            records.append(dict(prefix=prefix, hole=hole, board=board, street=state['st'],
                                physical_seat=state['pos'], selected_slot=selected, legal_mask=info['legal_mask'],
                                behavior_probs=info['behavior_probs'], max_logit_error=logit_error,
                                max_probability_error=probability_error))
            finally:
                hook.remove()
            modules = {}
            for name, module in list(sys.modules.items()):
                if (name.startswith('alpha_holdem.') or name.startswith('deep_cfr.')) and getattr(module, '__file__', None):
                    path = Path(module.__file__).resolve()
                    if not path.is_relative_to(source_root):
                        raise ValueError('A policy dependency was not loaded from the frozen snapshot')
                    modules[name] = dict(path=str(path), sha256=sha(path))
            if len(records) != 32 or network_attempts:
                raise ValueError('Wrong synthetic count or attempted network access')
            result.update(status='PASS', matched_state_tensors=len(first), synthetic_decisions=len(records),
                tested_streets=sorted({r['street'] for r in records}),
                tested_physical_seats=sorted({r['physical_seat'] for r in records}),
                max_logit_error=max(r['max_logit_error'] for r in records),
                max_probability_error=max(r['max_probability_error'] for r in records),
                loaded_dependency_sources=modules)
    except BaseException as error:
        failure = error
        result.update(status='FAILED', error_type=type(error).__name__, error=str(error))
    finally:
        result['network_calls_attempted'] = len(network_attempts)
        result['synthetic_decisions_completed'] = len(records)
        (directory/'synthetic_decisions.json').write_text(json.dumps(records, indent=2)+'\n')
        try:
            verify_inputs()
            verify_sources(copies)
            if sha(__file__) != sha(provenance/'source_copy.py'):
                raise ValueError('Helper source changed')
            result['frozen_inputs_and_execution_sources_unchanged'] = True
        except BaseException as error:
            result.update(status='FAILED', integrity_error=str(error))
            failure = error
        (directory/'parity_analysis.json').write_text(json.dumps(result, indent=2, sort_keys=True)+'\n')
    if failure is not None:
        raise failure
    print(json.dumps({k: result[k] for k in ['status', 'synthetic_decisions', 'max_logit_error',
        'max_probability_error', 'network_calls_attempted', 'actual_evaluation_hands']}))


if __name__ == '__main__':
    main()
