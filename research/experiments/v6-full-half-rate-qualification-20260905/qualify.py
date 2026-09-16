"""Qualify two actual retained full endpoints without running poker hands."""
import ast
import copy
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import time
import traceback
import xml.etree.ElementTree as ET

import torch

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[2]
sys.path.insert(0, str(BASE))
import lr_transfer as t
from inspect_parents import make_model, require, sha, TRAINER_SHA
from research.experiment_log import atomic_json

PILOT = ROOT / 'research/experiments/v6-current-kl-representation-pilot-20260905'
PARENTS = {
    'seed1': ('3d7914ba11c5deaf9725afbd59f4a805fd7f0bead37a2c8eddb6bffa9038b8f3', 9445556, 1992),
    'seed3': ('0a5e09c32dbdc098215fb29221a7f497a95755e2c5273060c8c01924d92d5cc0', 9441064, 1993)}


def check_trainer():
    path = ROOT / 'scripts/alpha_holdem/train_v5.py'
    require(sha(path) == TRAINER_SHA, 'qualified trainer changed')
    tree = ast.parse(path.read_text(encoding='utf-8'))
    guards = [node for node in ast.walk(tree) if isinstance(node, ast.If)
              and ast.unparse(node.test) == 'progress >= 0.5 and (not args.preserve_resumed_optimizer_lr)']
    # ast.unparse varies in parentheses by Python version; accept semantic structure.
    if not guards:
        guards = [node for node in ast.walk(tree) if isinstance(node, ast.If)
                  and ast.dump(node.test) == ast.dump(ast.parse(
                      'progress >= 0.5 and not args.preserve_resumed_optimizer_lr', mode='eval').body)]
    require(len(guards) == 1, 'LR preservation guard missing or ambiguous')
    assignments = [node for node in ast.walk(tree) if isinstance(node, ast.Assign)
                   and any(isinstance(target, ast.Subscript) and isinstance(target.slice, ast.Constant)
                           and target.slice.value == 'lr' for target in node.targets)]
    require(len(assignments) == 1 and assignments[0] in list(ast.walk(guards[0])),
            'unexpected optimizer LR assignment')
    calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call)
             and ast.unparse(node.func) == 'optimizer.load_state_dict']
    require(len(calls) == 1 and ast.unparse(calls[0].args[0]) == "ckpt['optimizer']", 'restore path changed')
    return {'source_sha256': TRAINER_SHA, 'optimizer_load_line': calls[0].lineno,
            'preserve_guard_line': guards[0].lineno, 'guarded_lr_assignments': len(assignments),
            'scope': 'Source inspection, not real worker execution'}


def inspect_actual(parent, physical, iteration):
    t.validate_source(parent)
    require(parent['iteration'] == iteration and
            parent['environment_hand_accounting']['completed_hands'] == physical, 'parent counters changed')
    require(len(parent['ppo_replay_entries']) == 2 and parent['main_process_rng_state'] is not None,
            'serialized continuation state missing')
    model = make_model(parent)
    named = list(model.named_parameters())
    group = parent['optimizer']['param_groups'][0]
    require(len(named) == len(group['params']) == len(parent['optimizer']['state']) == 86,
            'actual full parameter/state coverage changed')
    require(abs(group['lr'] - 1e-4) < 1e-18, 'actual source LR unexpected')
    rows = []
    for index, (name, parameter) in enumerate(named):
        state = parent['optimizer']['state'][index]
        require(set(state) == {'step', 'exp_avg', 'exp_avg_sq'}, 'unsupported Adam state')
        step = state['step']
        require(step.numel() == 1 and torch.isfinite(step).all() and float(step) > 0
                and float(step).is_integer(), 'invalid clock')
        for key in ('exp_avg', 'exp_avg_sq'):
            moment = state[key]
            require(moment.dtype == parameter.dtype and moment.shape == parameter.shape
                    and torch.isfinite(moment).all(), 'invalid moment')
        require(torch.all(state['exp_avg_sq'] >= 0), 'negative second moment')
        rows.append({'id': index, 'name': name, 'shape': list(parameter.shape), 'step': float(step)})
    return rows


def fixture(parent, derived):
    control, treatment = make_model(parent), make_model(derived)
    original = {name: value.detach().clone() for name, value in control.named_parameters()}
    co = torch.optim.Adam(control.parameters(), lr=.0003)
    to = torch.optim.Adam(treatment.parameters(), lr=.0003)
    co.load_state_dict(copy.deepcopy(parent['optimizer']))
    to.load_state_dict(copy.deepcopy(derived['optimizer']))
    require(to.param_groups[0]['lr'] == co.param_groups[0]['lr'] * 0.5, 'load did not preserve LR')
    for index, ((cn, cp), (tn, tp)) in enumerate(zip(control.named_parameters(), treatment.named_parameters())):
        require(cn == tn, 'parameter order changed')
        cp.grad = torch.full_like(cp, (index + 1) * 1e-6)
        tp.grad = cp.grad.clone()
    co.step()
    to.step()
    squared_control, squared_half, max_error, changed = 0.0, 0.0, 0.0, 0
    for index, ((name, cp), (_, tp)) in enumerate(zip(control.named_parameters(), treatment.named_parameters())):
        require(t.equal_tree(co.state[cp], to.state[tp]), 'same-gradient Adam state differs')
        require(float(co.state[cp]['step']) == float(parent['optimizer']['state'][index]['step']) + 1,
                'clock reset or skipped')
        old = original[name].double()
        cd, td = cp.detach().double() - old, tp.detach().double() - old
        error = (td - 0.5 * cd).abs()
        tolerance = torch.finfo(cp.dtype).eps * (1 + old.abs())
        require(torch.isfinite(tp).all() and torch.all(error <= tolerance), 'half displacement outside float rounding')
        squared_control += float(cd.square().sum())
        squared_half += float(td.square().sum())
        max_error = max(max_error, float(error.max()))
        changed += int(not torch.equal(tp.detach(), original[name]))
    require(changed == 86 and squared_control > 0, 'fixture did not exercise all parameters')
    ratio = (squared_half / squared_control) ** .5
    require(abs(ratio - .5) < 1e-3, 'material displacement ratio mismatch')
    return {'passed': True, 'same_gradient_bitwise_equal_adam_states': 86, 'advanced_state_clocks': 86,
            'changed_parameter_tensors': changed, 'loaded_control_lr': co.param_groups[0]['lr'],
            'loaded_half_lr': to.param_groups[0]['lr'], 'displacement_l2_ratio': ratio,
            'max_half_displacement_rounding_error': max_error, 'updated_models_saved': False,
            'scope': 'Synthetic identical gradients; not PPO-gradient equivalence or poker strength'}


def main():
    output = BASE / 'qualification.json'
    require(not output.exists() and not (BASE / 'qualification_failure.json').exists(), 'preserve earlier attempt')
    record = json.loads((BASE / 'experiment.json').read_text(encoding='utf-8'))
    require(record['status'] == 'RUNNING', 'qualification not preregistered')
    require(json.loads((PILOT / 'experiment.json').read_text(encoding='utf-8'))['status'] == 'COMPLETED', 'parent not terminal')
    review = PILOT / 'post_terminal_review.json'
    require(sha(review) == '0cb118d8232db5094e2f68a7ee03993ae5e28231f0f947126e0d9a2704b60971', 'parent review changed')
    paths = [BASE / name for name in ('protocol.md', 'lr_transfer.py', 'qualify.py', 'test_lr_transfer.py', 'lr_tests.xml')]
    for path in paths:
        require(record['artifact_integrity'][path.relative_to(ROOT).as_posix()]['sha256'] == sha(path),
                'registered source/test changed')
    paths += [review, t.SCOPE / 'scope_transfer.py', t.SCOPE / 'inspect_parents.py',
              ROOT / 'scripts/alpha_holdem/train_v5.py', ROOT / 'scripts/alpha_holdem/network_hybrid_h1.py']
    inputs = {str(path): sha(path) for path in paths}
    suite = ET.parse(BASE / 'lr_tests.xml').getroot().find('testsuite')
    require(suite is not None and int(suite.attrib['tests']) == 24 and
            all(int(suite.attrib[key]) == 0 for key in ('failures', 'errors', 'skipped')), 'unit qualification incomplete')
    start = time.monotonic()
    torch.set_num_threads(1)
    torch.manual_seed(20263905)
    results = {}
    try:
        trainer = check_trainer()
        for seed, (expected, physical, iteration) in PARENTS.items():
            path = PILOT / f'{seed}_full_stage2/latest.pt'
            require(sha(path) == expected, 'frozen parent changed')
            inputs[str(path)] = expected
            parent = torch.load(path, map_location='cpu', weights_only=False)
            description = inspect_actual(parent, physical, iteration)
            binding = {'path': str(path), 'sha256': expected}
            derived = t.derive(parent, binding)
            target = BASE / 'derived' / f'{seed}_half.pt'
            t.save_exclusive(target, derived)
            restored = torch.load(target, map_location='cpu', weights_only=False)
            require(t.equal_tree(derived, restored), 'serialization round trip changed')
            t.validate_derived(parent, restored, binding)
            proof = fixture(parent, restored)
            t.validate_derived(parent, restored, binding)
            results[seed] = {'source': binding, 'derived': str(target), 'derived_sha256': sha(target),
                'physical_hands': physical, 'iteration': iteration, 'parameter_state_mapping': description,
                'preserved_checkpoint_fields': [key for key in parent if key != 'optimizer'],
                'transfer': restored[t.PROVENANCE], 'fixture': proof, 'roundtrip_exact': True}
            del parent, derived, restored
        require(all(sha(Path(path)) == digest for path, digest in inputs.items()), 'source changed during qualification')
        report = {'schema': 'cardpilot.full_half_rate_qualification.v1', 'passed': True,
            'created_at': datetime.now(timezone.utc).isoformat(), 'outer_argv': sys.orig_argv,
            'wall_seconds': time.monotonic() - start, 'input_sha256': inputs, 'unit_tests_passed': 24,
            'parents': results, 'trainer_restore_inspection': trainer, 'new_training_hands': 0,
            'evaluation_hands': 0, 'slumbot_hands': 0, 'final_qualification_hands': 0,
            'synthetic_update_fixtures': 2, 'goal_achieved': False,
            'actual_production_initial_state_and_namespace_audit_still_required': True}
        atomic_json(output, report)
    except BaseException as exc:
        atomic_json(BASE / 'qualification_failure.json', {'error': repr(exc), 'traceback': traceback.format_exc(),
                    'completed_parent_proofs': results, 'preserve_partial_outputs': True, 'automatic_retry': False})
        raise
    print(json.dumps({'passed': True, 'parents': {seed: {'derived_sha256': row['derived_sha256'],
        'fixture': row['fixture']} for seed, row in results.items()}, 'new_training_hands': 0}))


if __name__ == '__main__':
    main()
