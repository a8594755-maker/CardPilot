#!/usr/bin/env python3
"""Independent read-only implementation audit for the token-bound LG001 path."""
from __future__ import annotations

import ast
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

os.environ['CUDA_VISIBLE_DEVICES'] = '-1'
os.environ['PYTHONDONTWRITEBYTECODE'] = '1'
sys.dont_write_bytecode = True

ROOT = Path(r'C:\Users\a8594\CardPilot')
PYTHON = Path(r'C:\Users\a8594\AppData\Local\Programs\Python\Python312\python.exe')
POWERSHELL = Path(r'C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe')
PREREG = ROOT / 'reports/v5_lg001_unified_behavior_window_preregistration_5ee42cb09c534cb3a294be701e94047f_20260722.json'
PREREG_AUDIT = ROOT / 'reports/v5_lg001_unified_behavior_window_preregistration_audit_5ee42cb09c534cb3a294be701e94047f_20260722.json'
CENSURE = ROOT / 'reports/v5_lg001_duplicate_registration_censure_20260722.json'
TRAINER = ROOT / 'scripts/alpha_holdem/train_v5_hybrid_h1.py'
LAUNCHER = ROOT / 'scripts/alpha_holdem/v5_lg001_launcher_5ee42cb09c534cb3a294be701e94047f.ps1'
TEST = ROOT / 'scripts/alpha_holdem/test_v5_lg001_contract_5ee42cb09c534cb3a294be701e94047f.py'
WINDOW_AUDIT = ROOT / 'scripts/alpha_holdem/v5_lg001_window_audit_5ee42cb09c534cb3a294be701e94047f.py'
SOURCE = ROOT / 'models/alpha_holdem_v5_hybrid/v5_hybrid_h11_control_catchmse_same33834_20m_r1_20260715/h11_control_endpoint.pt'
OUTPUT_ROOT = ROOT / 'models/alpha_holdem_v5_hybrid/v5_lg001_5ee42cb09c534cb3a294be701e94047f_20260722'

EXPECTED_HASHES = {
    PYTHON: '4d6f5f81a4bca11191c4c7c6b43632694d0a4ce74e068619d8fdc161d469859a',
    PREREG: '2d0a306ae005028a0745012dba5711316defee7f57bc1e2663e6726135be4125',
    PREREG_AUDIT: '92dd02a8770035c5698edcc7288d8d8ea214c1ce465c8b3ad0a5eb0d07e666e9',
    CENSURE: '840e898f2717ef5c5134f43a9a14a1f3c104e3e9066571ae8bb9cab7b774fa24',
    TRAINER: '91a98cec7677f4ee2ba74491f1be61ef2b3d4bfbb574b3615604d45f569d5591',
    LAUNCHER: 'd858cbb5fc95b4ea8bc977c1954cea120f8783091b24b5e800ba0059c500b689',
    TEST: 'e72817e82f91234a729d6946e4ba3f0700a1da4a12a46f479e5234caf2cd3686',
    WINDOW_AUDIT: '60958789cced670e2abb610ebeb4d9631a49ace2f74244b0a68bbcff6e33bc63',
    SOURCE: '96a007039b0baa29f0c39b0bd7adc67d8ca0733a41a261203f52430e60b5ca13',
}
EXPECTED_MEMBERS = {
    103: (26200, 430445532, 'cdec36f3deb27470a61c586b6491cd5de44aa3a99194b026a6e491a3121335a1'),
    109: (27400, 450186098, 'aee38c625bf0faada6b163f23aeb4cc539d67f7cbe46dc234aa4f46b18960953'),
    115: (28600, 469929538, 'ed92c7724486e446c13e5d4c623327d4288c68652964b7b4f35c0d2a7630d0c1'),
    120: (29600, 486379183, '86c3d7bacce72dd5749c21deaad3865c7313c9f118860cbc7e9b8b378070494e'),
    129: (31400, 515989661, '9d008780ac3cd259579131532df9775b53b4e3c95c7b0f12f2aac70bc915b255'),
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as handle:
        for block in iter(lambda: handle.read(8 << 20), b''):
            digest.update(block)
    return digest.hexdigest()


def canonical_bytes(value) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode('utf-8')


def state_hash(state) -> str:
    digest = hashlib.sha256()
    for name in sorted(state):
        tensor = state[name].detach().cpu().contiguous()
        metadata = canonical_bytes([name, str(tensor.dtype), list(tensor.shape)])
        digest.update(len(metadata).to_bytes(8, 'big'))
        digest.update(metadata)
        digest.update(tensor.numpy().tobytes())
    return digest.hexdigest()


def tree_snapshot(root: Path) -> dict[str, tuple[int, int]]:
    if not root.exists():
        return {}
    return {
        str(path.relative_to(root)): (path.stat().st_size, path.stat().st_mtime_ns)
        for path in root.rglob('*') if path.is_file()
    }


def run() -> dict:
    checks = []
    failures = []

    def check(name: str, passed: bool, detail=None):
        row = {'id': f'c{len(checks) + 1:03d}', 'name': name, 'passed': bool(passed)}
        if detail is not None:
            row['detail'] = detail
        checks.append(row)
        if not passed:
            failures.append(name)

    for path, expected in EXPECTED_HASHES.items():
        actual = sha256(path) if path.is_file() else None
        check(f'hash_exact:{path.name}', actual == expected, actual)

    prereg = json.loads(PREREG.read_text(encoding='utf-8'))
    prereg_audit = json.loads(PREREG_AUDIT.read_text(encoding='utf-8'))
    censure = json.loads(CENSURE.read_text(encoding='utf-8'))
    check('registration_token_exact', prereg.get('registration_token') == '5ee42cb09c534cb3a294be701e94047f')
    check('preregistration_audit_pass_91', prereg_audit.get('overall') == 'PASS' and prereg_audit.get('checks_passed') == 91)
    check('censure_preserves_earlier_pair', censure['earlier_authoritative_registration']['authority'] == 'SOLE_LG001_REGISTRATION_AUTHORITY_PRESERVED')
    check('later_pair_authority_none', censure['later_censured_registration']['authority'] == 'NONE_PROVENANCE_ONLY')

    frozen = prereg.get('frozen_inputs') or []
    check('frozen_inputs_count_16', len(frozen) == 16)
    frozen_mismatches = []
    for row in frozen:
        if row['role'] == 'CURRENT_V5_TRAINER':
            continue
        path = Path(row['path'])
        actual = sha256(path) if path.is_file() else None
        if actual != row['sha256']:
            frozen_mismatches.append(row['role'])
    check('unchanged_frozen_inputs_rehash_15_of_15', not frozen_mismatches, frozen_mismatches)
    base_trainer_row = next(row for row in frozen if row['role'] == 'CURRENT_V5_TRAINER')
    check('allowed_trainer_preimage_bound', base_trainer_row['sha256'] == 'd64e5e907a9066357980fa59dd0029dc4b7436e4e9ca63ce537a81775595f9d1')

    trainer_text = TRAINER.read_text(encoding='utf-8')
    launcher_text = LAUNCHER.read_text(encoding='utf-8')
    test_text = TEST.read_text(encoding='utf-8')
    window_text = WINDOW_AUDIT.read_text(encoding='utf-8')
    for path, text in ((TRAINER, trainer_text), (TEST, test_text), (WINDOW_AUDIT, window_text)):
        try:
            ast.parse(text, filename=str(path))
            parsed = True
        except SyntaxError:
            parsed = False
        check(f'python_ast_parse:{path.name}', parsed)
    required_trainer_tokens = [
        '--lg001-contract', '--lg001-arm', 'lg001_assignment_u64', 'lg001_select_opponent',
        'lg001_validate_frozen_pool', "if not lg001_enabled and iteration % args.snapshot_every",
        "payload['lg001']", 'provenance_tail_sha256', 'LG001 endpoint overshoot exceeds 50,000 hands',
        "os.environ.get('CUDA_VISIBLE_DEVICES') != '0'", 'CPU fallback is forbidden',
    ]
    check('trainer_required_contract_tokens', all(token in trainer_text for token in required_trainer_tokens))
    check('default_sampler_retained', 'random.randint(0, pool.size() - 1)' in trainer_text)
    check('lg001_branch_precedes_default_sampler', trainer_text.index('if lg001_enabled:', trainer_text.index('def assign_opponents')) < trainer_text.index('elif pool.size() == 0:', trainer_text.index('def assign_opponents')))
    check('pool_add_disabled_only_for_lg001', 'if not lg001_enabled and iteration % args.snapshot_every == 0:' in trainer_text)
    check('checkpoint_embeds_full_contract', all(token in trainer_text for token in ('registration_token', 'source_checkpoint_sha256', 'conditional_pool_weights', 'assignment_seed', 'pool_members')))
    check('provenance_extends_existing_hash_chain', "record['lg001'] = dict(lg001_assignment)" in trainer_text and "record['record_sha256']" in trainer_text)
    check('launcher_exact_python', str(PYTHON) in launcher_text and EXPECTED_HASHES[PYTHON] in launcher_text)
    check('launcher_exact_trainer_hash', EXPECTED_HASHES[TRAINER] in launcher_text)
    check('launcher_cuda_parent_zero', "$env:CUDA_VISIBLE_DEVICES = '0'" in launcher_text)
    check('launcher_gpu_uuid_exact', 'GPU-01d41f66-6148-83e4-ce86-8b0c15f8a60d' in launcher_text)
    check('launcher_below_normal', 'BelowNormal' in launcher_text)
    check('launcher_no_cpu_fallback', "'--device', 'cuda'" in launcher_text)
    check('launcher_single_attempt_collision_gate', 'single-attempt output collision' in launcher_text)
    check('launcher_no_automatic_restart', 'No automatic restart is allowed' in launcher_text)
    check('test_declares_zero_bytecode', "sys.dont_write_bytecode = True" in test_text)
    check('window_audit_is_read_only', not any(token in window_text for token in ('.write_text(', '.open(\'w\'', 'torch.save(')))

    import torch
    checkpoint = torch.load(SOURCE, map_location='cpu', weights_only=False)
    check('source_iteration_exact', int(checkpoint.get('iteration', -1)) == 35051)
    check('source_hands_exact', int(checkpoint.get('total_hands', -1)) == 576_021_901)
    check('source_v55_v55_9slot', checkpoint.get('env_version') == 'v55' and checkpoint.get('obs_version') == 'v55' and checkpoint.get('action_space_version') == '9slot_v5')
    check('source_optimizer_present', isinstance(checkpoint.get('optimizer'), dict) and bool(checkpoint['optimizer']))
    pool = checkpoint.get('pool_snapshots') or []
    check('source_pool_exactly_five', len(pool) == 5)
    observed = {}
    for snapshot in pool:
        member_id = int(snapshot.get('id', -1))
        observed[member_id] = (int(snapshot.get('iteration', -1)), int(snapshot.get('hands', -1)), state_hash(snapshot.get('state_dict') or {}))
    check('source_pool_member_identities_exact', observed == EXPECTED_MEMBERS, sorted(observed))

    h4 = json.loads((ROOT / 'reports/h4_pool_meas_001_20260713/result.json').read_text(encoding='utf-8'))
    member_ids = set(EXPECTED_MEMBERS)
    magnitudes = {member_id: [] for member_id in member_ids}
    for edge in h4.get('edges', []):
        a_id, b_id = int(edge['a_id']), int(edge['b_id'])
        if a_id in member_ids and b_id in member_ids:
            value = abs(float(edge['mean_a_bb100']))
            magnitudes[a_id].append(value)
            magnitudes[b_id].append(value)
    scores = {member_id: sum(rows) / len(rows) for member_id, rows in magnitudes.items()}
    total_score = sum(scores.values())
    weights = {member_id: scores[member_id] / total_score for member_id in sorted(scores)}
    registered_scores = {int(k): float(v) for k, v in prereg['frozen_league']['diversity_scores_mean_abs_bb100'].items()}
    registered_weights = {int(k): float(v) for k, v in prereg['frozen_league']['conditional_pool_weights_treatment'].items()}
    check('h4_diversity_scores_recomputed', all(abs(scores[k] - registered_scores[k]) < 1e-12 for k in scores))
    check('h4_diversity_weights_recomputed', all(abs(weights[k] - registered_weights[k]) < 1e-15 for k in weights))
    check('control_weights_uniform', prereg['frozen_league']['conditional_pool_weights_control'] == {str(k): 0.2 for k in sorted(member_ids)})
    check('treatment_total_training_weights_sum_one', abs(sum(prereg['frozen_league']['total_training_weights_treatment'].values()) - 1.0) < 1e-12)

    before_scripts = tree_snapshot(ROOT / 'scripts/alpha_holdem/__pycache__')
    before_output = tree_snapshot(OUTPUT_ROOT)
    env = dict(os.environ)
    env['CUDA_VISIBLE_DEVICES'] = '-1'
    env['PYTHONDONTWRITEBYTECODE'] = '1'
    test_run = subprocess.run(
        [str(PYTHON), '-B', str(TEST)], cwd=ROOT, env=env,
        text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=120,
    )
    check('deterministic_contract_tests_exit_zero', test_run.returncode == 0, test_run.stderr[-1000:])
    check('deterministic_contract_tests_10_pass', 'Ran 10 tests' in test_run.stderr and '\nOK' in test_run.stderr)
    launcher_results = []
    for arm in ('control_uniform', 'treatment_diversity'):
        proc = subprocess.run(
            [str(POWERSHELL), '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', str(LAUNCHER),
             '-Arm', arm, '-Stage', 'stage_a', '-ContractOnly'],
            cwd=ROOT, env=env, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=120,
        )
        try:
            payload = json.loads(proc.stdout)
        except json.JSONDecodeError:
            payload = {}
        launcher_results.append((arm, proc.returncode, payload, proc.stderr))
    check('launcher_control_contract_only_pass', launcher_results[0][1] == 0 and launcher_results[0][2].get('files_written') == 0, launcher_results[0][3])
    check('launcher_treatment_contract_only_pass', launcher_results[1][1] == 0 and launcher_results[1][2].get('files_written') == 0, launcher_results[1][3])
    check('launcher_contract_only_starts_no_child', all(not row[2].get('child_started', True) for row in launcher_results))
    after_scripts = tree_snapshot(ROOT / 'scripts/alpha_holdem/__pycache__')
    after_output = tree_snapshot(OUTPUT_ROOT)
    check('zero_output_root_before_and_after', not before_output and not after_output)
    check('zero_bytecode_or_script_side_effects', before_scripts == after_scripts)
    check('implementation_result_paths_absent', not OUTPUT_ROOT.exists())

    return {
        'schema_version': 'v5.lg001.implementation_audit.stdout.v1',
        'classification': 'LG001_IMPLEMENTATION_AUDIT_PASS_ZERO_OUTPUT_CONTRACT_TESTS_COMPLETE_STOP_BEFORE_TRAINING' if not failures else 'LG001_IMPLEMENTATION_AUDIT_FAIL_CLOSED',
        'overall': 'PASS' if not failures else 'FAIL_CLOSED',
        'checks': checks,
        'checks_passed': sum(1 for row in checks if row['passed']),
        'checks_total': len(checks),
        'failed': failures,
        'test_returncode': test_run.returncode,
        'launcher_contract_only': [
            {'arm': arm, 'returncode': code, 'classification': payload.get('classification'), 'files_written': payload.get('files_written')}
            for arm, code, payload, _ in launcher_results
        ],
        'work_state': {'output_root': 0, 'training_arms': 0, 'checkpoint_changes': 0, 'slumbot_hands': 0, 'official_hands': 0},
        'next_authority': 'ONE_LATER_SEPARATELY_PREFLIGHTED_STAGE_A_CONTROL_LAUNCH_ONLY',
        'training_authority_now': 'NONE',
        'strength': 'L0',
    }


if __name__ == '__main__':
    result = run()
    print(json.dumps(result, indent=2, sort_keys=True))
    raise SystemExit(0 if result['overall'] == 'PASS' else 1)
