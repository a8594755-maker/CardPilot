"""Actual fixed-parent scope qualification; no environment/Slumbot execution."""
from datetime import datetime, timezone
from pathlib import Path
import copy
import json
import sys
import time
import traceback
import xml.etree.ElementTree as ET

import torch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import inspect_parents as p
import scope_transfer as s


def fixture_update(parent, derived, binding):
    control, full = p.make_model(parent), p.make_model(derived)
    c_names, f_names = dict(control.named_parameters()), dict(full.named_parameters())
    head_names = [row['name'] for row in binding['head_parameter_mapping']]
    new_names = derived['optimizer_scope_transfer']['new_parameter_names']
    for name, parameter in c_names.items():
        parameter.requires_grad = name in head_names
    c_opt = torch.optim.Adam([c_names[name] for name in head_names], lr=.0003)
    f_opt = torch.optim.Adam(full.parameters(), lr=.0003)
    c_opt.load_state_dict(copy.deepcopy(parent['optimizer']))
    f_opt.load_state_dict(copy.deepcopy(derived['optimizer']))
    actual_lr = binding['optimizer_group_hyperparameters']['lr']
    p.require(c_opt.param_groups[0]['lr'] == f_opt.param_groups[0]['lr'] == actual_lr,
        'restored effective LR changed')
    for name in new_names:
        p.require(f_names[name] not in f_opt.state, 'invented pre-update representation state')
    for index, name in enumerate(f_names):
        f_names[name].grad = torch.full_like(f_names[name], (index + 1) * 1e-6)
        if name in head_names:
            c_names[name].grad = f_names[name].grad.clone()
    c_opt.step()
    f_opt.step()
    common_steps = {}
    for row in binding['head_parameter_mapping']:
        name = row['name']
        p.require(torch.equal(c_names[name], f_names[name]), 'common parameter update differs')
        p.require(s.equal_tree(c_opt.state[c_names[name]], f_opt.state[f_names[name]]), 'common Adam update differs')
        step = float(f_opt.state[f_names[name]]['step'])
        p.require(step == row['step'] + 1, 'old Adam step was reset or skipped')
        common_steps[name] = step
    for name in new_names:
        p.require(torch.equal(c_names[name], parent['model'][name]), 'heads control modified body')
        p.require(not torch.equal(f_names[name], parent['model'][name]), 'full body received no update')
        p.require(float(f_opt.state[f_names[name]]['step']) == 1, 'new parameter has fabricated history')
    p.require(len(f_opt.state) == len(f_names), 'full Adam coverage incomplete after fixture')
    p.require(all(torch.isfinite(parameter).all().item() for parameter in full.parameters()), 'nonfinite fixture weights')
    return {'passed': True, 'old_parameter_updates_bitwise_equal': len(head_names),
        'old_parameter_steps_after_fixture': common_steps, 'new_parameter_first_steps': len(new_names),
        'new_body_tensors_changed': len(new_names), 'heads_control_body_unchanged': True,
        'restored_effective_lr': actual_lr, 'fixture_updated_weights_persisted': False,
        'scope': 'Same supplied finite gradients; verifies Adam transfer/update semantics,not full PPO-gradient or poker-strength equivalence.'}


def main():
    base, root = p.BASE, p.ROOT
    report_path = base / 'real_parent_qualification.json'
    p.require(not report_path.exists() and not (base / 'qualification_failure.json').exists(),
        'preserve earlier qualification attempt')
    for seed in p.PARENTS:
        p.require(not (base / 'derived' / f'{seed}_full.pt').exists(), 'preserve derived artifact')
    record = json.loads((base / 'experiment.json').read_text(encoding='utf-8'))
    p.require(record['status'] == 'RUNNING', 'not the same RUNNING record')
    inspection_path = base / 'parent_inspection.json'
    inspection = json.loads(inspection_path.read_text(encoding='utf-8'))
    p.require(inspection['passed'], 'parent inspection failed')
    sources = (Path(__file__), base / 'scope_transfer.py', base / 'test_scope_transfer.py', inspection_path,
        base / 'scope_tests.xml')
    inputs = dict(inspection['source_sha256'])
    for source in sources:
        relative = source.relative_to(root).as_posix()
        p.require(p.sha(source) == record['artifact_integrity'][relative]['sha256'], 'registered source/test artifact changed')
        inputs[str(source)] = p.sha(source)
    p.require(all(p.sha(Path(path)) == digest for path, digest in inputs.items()), 'qualified input changed')
    suite = ET.parse(base / 'scope_tests.xml').getroot().find('testsuite')
    p.require(suite is not None and int(suite.attrib['tests']) == 25 and
        all(int(suite.attrib[key]) == 0 for key in ('failures', 'errors', 'skipped')), 'unit qualification incomplete')
    start = time.monotonic()
    torch.set_num_threads(1)
    torch.manual_seed(20263706)
    result = {}
    try:
        for seed, (path, expected) in p.PARENTS.items():
            p.require(p.sha(path) == expected, 'frozen parent changed')
            inputs[str(path)] = expected
            parent = torch.load(path, map_location='cpu', weights_only=False)
            binding = inspection['parents'][seed]
            p.require(binding['path'] == str(path) and binding['sha256'] == expected, 'parent binding mismatch')
            model = p.make_model(parent)
            derived = s.expand_scope(parent, model, binding)
            output = base / 'derived' / f'{seed}_full.pt'
            s.save_exclusive(output, derived)
            restored = torch.load(output, map_location='cpu', weights_only=False)
            p.require(s.equal_tree(derived, restored), 'derived serialization changed state')
            s.validate_derived(parent, restored, binding)
            proof = fixture_update(parent, restored, binding)
            s.validate_derived(parent, restored, binding)
            p.require(p.sha(path) == expected, 'original parent was modified')
            result[seed] = {'source': str(path), 'source_sha256': expected,
                'derived': str(output), 'derived_sha256': p.sha(output),
                'source_physical_hands': parent['environment_hand_accounting']['completed_hands'],
                'source_iteration': parent['iteration'], 'preserved_top_level_keys':
                    [key for key in parent if key not in ('optimizer', 'all_policy_heads_only_training')],
                'source_optimizer_states': len(parent['optimizer']['state']),
                'derived_optimizer_states_before_gradient': len(restored['optimizer']['state']),
                'derived_optimizer_parameter_ids': len(restored['optimizer']['param_groups'][0]['params']),
                'transfer': restored['optimizer_scope_transfer'], 'fixture_update': proof,
                'serialized_derived_weights_equal_parent': True, 'new_physical_hands': 0}
            del model, parent, derived, restored
        p.require(all(p.sha(Path(path)) == digest for path, digest in inputs.items()), 'input changed during qualification')
        report = {'schema': 'cardpilot.named_scope_transfer.real_parent_qualification.v1', 'passed': True,
            'created_at': datetime.now(timezone.utc).isoformat(), 'outer_argv': sys.orig_argv,
            'wall_seconds': time.monotonic() - start, 'input_sha256': inputs, 'unit_tests_passed': 25,
            'parents': result, 'synthetic_update_fixtures': 2, 'new_training_hands': 0,
            'evaluation_hands': 0, 'slumbot_hands': 0, 'goal_achieved': False,
            'production_trainer_and_network_unchanged': True,
            'actual_rollout_initial_state_and_namespace_audit_still_required': True,
            'decision': 'ADMIT_SEPARATE_MATCHED_CURRENT_REGIMEN_SCOPE_PILOT_NOT_STRENGTH_OR_FINAL_TEST'}
        p.atomic_json(report_path, report)
    except BaseException as exc:
        p.atomic_json(base / 'qualification_failure.json', {'error': repr(exc), 'traceback': traceback.format_exc(),
            'preserve_all_partial_outputs': True, 'automatic_retry': False, 'completed_parent_proofs': result,
            'new_training_hands': 0, 'slumbot_hands': 0})
        raise
    print(json.dumps({'passed': True, 'parents': {seed: {'preserved_states': row['source_optimizer_states'],
        'new_parameter_first_steps': row['fixture_update']['new_parameter_first_steps'],
        'derived_sha256': row['derived_sha256']} for seed, row in result.items()}, 'new_training_hands': 0}))


if __name__ == '__main__':
    main()
