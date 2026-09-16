"""One-shot CPU endpoint deployment parity on retained internal states; no requests/updates."""
from datetime import datetime, timezone
import gc
import importlib.util
from pathlib import Path
import sys
import time
import traceback

import numpy as np
import torch
import run_pair as r

BASE = Path(__file__).resolve().parent
QUAL = r.ROOT / 'research/experiments/v6-preflop-actor-trunk-route-qualification-20260906'
NETWORK = QUAL / 'candidate/scripts/alpha_holdem/network_hybrid_h1.py'
NETWORK_SHA = '07350adfc79db5e81d5d978751492aad443aa72d493ff4f9c3cec5774c2840f8'


def retained_inputs(checkpoint):
    selected, identities = {s: [] for s in (0, 3, 4, 5)}, {s: [] for s in (0, 3, 4, 5)}
    for entry in checkpoint['ppo_replay_entries']:
        for bi, block in enumerate(entry['blocks']):
            for ri, row in enumerate(block):
                street = int(row[0].reshape(6, 4, 13)[4].sum())
                r.protocol.require(street in selected, 'unknown replay street')
                if len(selected[street]) < 16:
                    selected[street].append(row)
                    identities[street].append([entry['iteration'], bi, ri])
    r.protocol.require(all(len(rows) == 16 for rows in selected.values()), 'incomplete retained street coverage')
    return selected, identities


def main():
    started = time.monotonic()
    out, failure = BASE / 'endpoint_parity.json', BASE / 'endpoint_parity_failure_v2.json'
    r.protocol.require(not out.exists() and not failure.exists(), 'preserve prior endpoint qualification')
    torch.set_num_threads(1)
    torch.manual_seed(2026430601)
    r.protocol.require(r.sha(NETWORK) == NETWORK_SHA, 'qualified candidate network changed')
    sys.path.insert(0, str(r.RUNTIME_SOURCE))
    from alpha_holdem.legacy_observation_bridge_v6 import load_policy
    r.protocol.require(load_policy.__module__ == 'alpha_holdem.legacy_observation_bridge_v6',
        'must use the registered journaled legacy-v4 bridge loader')
    import alpha_holdem.network_hybrid_h1 as deployed
    r.protocol.require(Path(deployed.__file__).resolve() ==
        r.RUNTIME_SOURCE / 'alpha_holdem/network_hybrid_h1.py', 'unexpected inference import')
    spec = importlib.util.spec_from_file_location('actor_candidate_endpoint_parity', NETWORK)
    candidate = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(candidate)
    inputs = {str(NETWORK): NETWORK_SHA, str(Path(__file__).resolve()): r.sha(__file__),
              str(BASE / 'run_pair.py'): r.sha(BASE / 'run_pair.py')}
    inputs.update({str(p): r.sha(p) for p in r.RUNTIME_SOURCE.rglob('*.py') if '__pycache__' not in p.parts})
    models = {}
    try:
        for arm, (path, expected) in r.EXPECTED_MODELS.items():
            r.protocol.require(r.sha(path) == expected, 'endpoint substituted')
            inputs[str(path)] = expected
            bridge = load_policy(path, 'cpu')
            model, checkpoint, actual = bridge.model, bridge.checkpoint, bridge.sha256
            connected = arm.endswith('connected')
            r.protocol.require(actual == expected, 'deployment loaded wrong file')
            r.protocol.require(checkpoint['environment_hand_accounting']['completed_hands'] ==
                r.EXPECTED_HANDS[arm], 'endpoint counter changed')
            flag = checkpoint.get('config', {}).get('preflop_trunk_gradient', False)
            r.protocol.require(type(flag) is bool and flag is connected and
                checkpoint.get('preflop_trunk_gradient', False) is connected, 'wrong training route')
            training = candidate.AlphaHoldemNet(norm_layer='gn', critic_contract='critic_v2',
                separate_preflop_head=True, preflop_trunk_gradient=connected).eval()
            with torch.no_grad():
                training(torch.zeros(1,6,4,13), torch.zeros(1,25,4,5), torch.zeros(1,3))
            training.load_state_dict(checkpoint['model'], strict=True)
            r.protocol.require(set(training.state_dict()) == set(model.state_dict()) ==
                set(checkpoint['model']), 'deployment state coverage mismatch')
            r.protocol.require(all(torch.equal(value, checkpoint['model'][name]) for name, value in
                model.state_dict().items()), 'deployment altered trained tensors')
            selected, identities = retained_inputs(checkpoint)
            by_street = {}
            with torch.no_grad():
                for street, rows in selected.items():
                    x = [torch.from_numpy(np.stack([row[i] for row in rows])) for i in range(4)]
                    x[0], x[1] = x[0].reshape(-1,6,4,13), x[1].reshape(-1,25,4,5)
                    r.protocol.require(all(torch.isfinite(t).all() for t in x), 'nonfinite retained input')
                    a, b = training(*x), model(*x)
                    r.protocol.require(all(torch.equal(left, right) and torch.isfinite(left).all()
                        for left, right in zip(a,b)), 'training/deployment forward disagreement')
                    r.protocol.require(torch.equal(a[0].argmax(-1), b[0].argmax(-1)), 'greedy disagreement')
                    by_street[str(street)] = {'retained_rows': 16, 'logits_exact': True,
                        'value_exact': True, 'greedy_exact': True}
            models[arm] = {'path': str(path), 'sha256': expected,
                'physical_lineage_hands': r.EXPECTED_HANDS[arm], 'preflop_trunk_gradient': connected,
                'retained_rows': 64, 'row_identities': identities, 'by_street': by_street,
                'model_tensors_loaded_exactly': len(model.state_dict()), 'optimizer_updates': 0}
            del bridge, model, training, checkpoint, selected, x, a, b
            gc.collect()
        r.check_hashes(inputs)
        r.write_new(out, {'passed': True, 'created_at': datetime.now(timezone.utc).isoformat(),
            'command': sys.orig_argv, 'wall_seconds': time.monotonic() - started,
            'input_sha256': inputs, 'models': models,
            'model_sha256': {arm: digest for arm, (_, digest) in r.EXPECTED_MODELS.items()},
            'retained_input_rows': 256, 'diagnostic_rows_are_not_new_hands': True,
            'network_requests': 0, 'new_training_hands': 0, 'evaluation_hands': 0,
            'optimizer_updates': 0, 'forward_contract_scope': 'exact final weights on 16 retained rows per street, four streets per policy; not a proof over all possible states'})
        print('Four frozen final endpoints: 256 retained-state inference rows exact; no new hands.')
    except BaseException:
        r.write_new(failure, {'passed': False, 'command': sys.orig_argv, 'traceback': traceback.format_exc(),
            'input_sha256': inputs, 'models_completed': models, 'network_requests': 0, 'new_hands': 0})
        raise


if __name__ == '__main__':
    main()
