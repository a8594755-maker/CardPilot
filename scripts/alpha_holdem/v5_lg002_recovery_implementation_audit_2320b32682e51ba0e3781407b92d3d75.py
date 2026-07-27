#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(r'C:\Users\a8594\CardPilot')
TOKEN = '2320b32682e51ba0e3781407b92d3d75'
PYTHON = Path(r'C:\Users\a8594\AppData\Local\Programs\Python\Python312\python.exe')
TRAINER = ROOT / 'scripts' / 'alpha_holdem' / 'train_v5.py'
NETWORK = ROOT / 'scripts' / 'alpha_holdem' / 'network_hybrid_h1.py'
LAUNCHER = ROOT / 'scripts' / 'alpha_holdem' / f'v5_lg002_recovery_launcher_{TOKEN}.ps1'
TEST = ROOT / 'scripts' / 'alpha_holdem' / f'test_v5_lg002_recovery_{TOKEN}.py'
PREREG = ROOT / 'reports' / f'v5_lg002_recovery_preregistration_{TOKEN}_20260722.json'
PREREG_AUDIT = ROOT / 'reports' / f'v5_lg002_recovery_preregistration_audit_{TOKEN}_20260722.json'
SOURCE = ROOT / 'models' / 'alpha_holdem_v5_hybrid' / 'v5_hybrid_h11_control_catchmse_same33834_20m_r1_20260715' / 'latest.pt'
OUTPUT_ROOT = ROOT / 'models' / 'alpha_holdem_v5_hybrid' / f'v5_lg002_recovery_{TOKEN}_20260722'

EXPECTED = {
    PREREG: 'ef41b731de6ad74f93d01cbb2f4ce245bcde9323335e331a6c31f0daf3e9eda9',
    PREREG_AUDIT: '318899d0b0f1bfbfe80867473cf5ad192500379f6e8cc23479de22c9ef29bdec',
    NETWORK: '25f4520d31f4ce5ffcfd23fc0d56b8736fd3b5fad537706b9cd13ee270b4a171',
    SOURCE: '96a007039b0baa29f0c39b0bd7adc67d8ca0733a41a261203f52430e60b5ca13',
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def run_json(command: list[str], env: dict[str, str]) -> tuple[dict, str]:
    completed = subprocess.run(
        command, cwd=ROOT, env=env, text=True, capture_output=True,
        timeout=180, check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            f'child failed exit={completed.returncode} command={command!r} '
            f'stdout={completed.stdout!r} stderr={completed.stderr!r}'
        )
    lines = [line for line in completed.stdout.splitlines() if line.strip()]
    if not lines:
        raise RuntimeError(f'child emitted no JSON: {command!r}')
    return json.loads(lines[-1]), completed.stderr


def main() -> int:
    checks: dict[str, bool] = {}
    checks['all_required_files_present'] = all(
        path.is_file() for path in (*EXPECTED, TRAINER, LAUNCHER, TEST)
    )
    actual_frozen_hashes = {str(path): sha256(path) for path in EXPECTED}
    checks['frozen_input_hashes_exact'] = all(
        actual_frozen_hashes[str(path)] == expected for path, expected in EXPECTED.items()
    )
    prereg = json.loads(PREREG.read_text(encoding='utf-8-sig'))
    prereg_audit = json.loads(PREREG_AUDIT.read_text(encoding='utf-8-sig'))
    checks['preimplementation_audit_pass_100_of_100'] = (
        prereg_audit.get('summary', {}).get('overall') == 'PASS'
        and prereg_audit.get('summary', {}).get('passed') == 100
        and prereg_audit.get('summary', {}).get('total') == 100
    )
    checks['registration_identity_exact'] = (
        prereg.get('registration_token') == TOKEN
        and prereg.get('schema_version') == 'v5.lg002.recovery.preregistration.v1'
    )
    checks['single_recovery_only'] = (
        prereg['recovery_authority']['correction_ordinal'] == 1
        and prereg['recovery_authority']['maximum_corrections'] == 1
        and prereg['recovery_authority']['second_recovery'] == 'FORBIDDEN'
    )
    checks['output_root_absent_before'] = not OUTPUT_ROOT.exists()

    trainer_source = TRAINER.read_text(encoding='utf-8')
    launcher_source = LAUNCHER.read_text(encoding='utf-8')
    test_source = TEST.read_text(encoding='utf-8')
    compile(trainer_source, str(TRAINER), 'exec')
    compile(test_source, str(TEST), 'exec')
    checks['python_compile'] = True
    checks['trainer_postimage_differs_from_registered_preimage'] = (
        sha256(TRAINER) != prereg['actual_runtime_contract']['base_trainer_sha256']
    )
    checks['default_opt_in_none'] = "default='none'" in trainer_source and '--lg002-recovery-arm' in trainer_source
    checks['network_unchanged'] = actual_frozen_hashes[str(NETWORK)] == EXPECTED[NETWORK]
    checks['selector_sha256_u64_rule_present'] = (
        "LG002R_ASSIGNMENT_V1|{token}|{int(seed)}|{int(absolute_iteration)}" in trainer_source
        and "digest()[:8], 'big'" in trainer_source
    )
    checks['selector_no_random_calls'] = 'def lg002_select_from_u64' in trainer_source
    selector_block = trainer_source.split('def lg002_select_from_u64', 1)[1].split('def lg002_select_opponent', 1)[0]
    checks['selector_block_no_global_rng'] = 'random.' not in selector_block and 'np.random' not in selector_block
    checks['pool_mutation_disabled_both_arms'] = (
        'iteration % args.snapshot_every == 0 and not lg002_recovery_active' in trainer_source
    )
    checks['legacy_arms_fail_closed'] = 'forbids every legacy H2/H6-H18 arm identity and path' in trainer_source
    checks['target_kl_preserved'] = "'ppo_target_kl': 0.03" in trainer_source
    checks['mse_catchup_preserved'] = (
        'args.h8_value_head_catchup_after_kl_stop' in trainer_source
        and "'value_head_catchup_loss': 'mse'" in trainer_source
    )
    checks['checkpoint_identity_fields_present'] = (
        "payload['lg002_recovery']" in trainer_source
        and "'assignment_provenance_tail_sha256'" in trainer_source
        and "'new_snapshot_addition_disabled': True" in trainer_source
    )
    checks['provenance_hash_chain_present'] = (
        'def lg002_enrich_provenance_record' in trainer_source
        and "'previous_record_sha256'" in trainer_source
        and "'selected_member_state_sha256'" in trainer_source
    )
    checks['launcher_absolute_child_boundary'] = all(
        str(path) in launcher_source
        for path in (PYTHON, TRAINER, PREREG, SOURCE, OUTPUT_ROOT)
    )
    checks['launcher_modes_exact'] = all(
        mode in launcher_source for mode in ('ContractProbe', 'StageAControl', 'StageATreatment')
    ) and 'StageB' not in launcher_source
    checks['launcher_stage_a_wall_guard'] = "'--max-runtime-seconds', '10800'" in launcher_source
    checks['launcher_probe_gpu_denied'] = "CUDA_VISIBLE_DEVICES', '-1'" in launcher_source

    env = os.environ.copy()
    env['PYTHONDONTWRITEBYTECODE'] = '1'
    unit_result, unit_stderr = run_json([str(PYTHON), str(TEST)], env)
    checks['unit_test_pass_10_of_10'] = (
        unit_result.get('status') == 'PASS'
        and unit_result.get('passed') == 10
        and unit_result.get('total') == 10
    )
    checks['unit_test_stderr_empty'] = not unit_stderr.strip()

    probe_results: list[dict] = []
    for arm in ('control_uniform', 'treatment_diversity'):
        probe, stderr = run_json([
            'powershell.exe', '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass',
            '-File', str(LAUNCHER), '-Mode', 'ContractProbe', '-Arm', arm,
        ], env)
        probe_results.append(probe)
        checks[f'probe_{arm}_pass'] = (
            probe.get('status') == 'PASS'
            and probe.get('arm') == arm
            and probe.get('files_written') == 0
            and probe.get('gpu_initialized') is False
            and probe.get('global_rng_consumption') == 0
        )
        checks[f'probe_{arm}_stderr_empty'] = not stderr.strip()

    checks['exactly_two_registered_probes'] = (
        len(probe_results) == 2
        and [probe['arm'] for probe in probe_results]
        == ['control_uniform', 'treatment_diversity']
    )
    checks['same_probe_u64_both_arms'] = [
        row['u64'] for row in probe_results[0]['selector_samples']
    ] == [row['u64'] for row in probe_results[1]['selector_samples']]
    checks['source_model_optimizer_hand_pool_exact'] = all(
        probe['contract']['source_checkpoint_sha256'] == EXPECTED[SOURCE]
        and probe['contract']['source_iteration'] == 35051
        and probe['contract']['source_total_hands'] == 576021901
        and probe['contract']['pool_checkpoint_order'] == [109, 115, 120, 129, 103]
        and len(probe['contract']['member_state_sha256']) == 5
        for probe in probe_results
    )
    checks['probe_weights_differ_only_conditionally'] = (
        probe_results[0]['contract']['conditional_weights']
        != probe_results[1]['contract']['conditional_weights']
        and sum(probe_results[0]['contract']['conditional_weights'].values()) == 1.0
        and abs(sum(probe_results[1]['contract']['conditional_weights'].values()) - 1.0) <= 1e-12
    )
    checks['output_root_absent_after'] = not OUTPUT_ROOT.exists()
    checks['no_training_checkpoint_or_official_hands'] = (
        checks['output_root_absent_after']
        and all(probe['files_written'] == 0 for probe in probe_results)
    )

    passed = sum(bool(value) for value in checks.values())
    status = 'PASS' if passed == len(checks) else 'FAIL_CLOSED'
    result = {
        'schema_version': 'v5.lg002.recovery.implementation_audit.v1',
        'classification': (
            'LG002_RECOVERY_IMPLEMENTATION_AUDIT_PASS_STAGE_A_LAUNCH_READY_ONLY'
            if status == 'PASS'
            else 'LG002_RECOVERY_IMPLEMENTATION_AUDIT_FAIL_CLOSED_NO_LAUNCH'
        ),
        'status': status,
        'registration_token': TOKEN,
        'registration_sha256': EXPECTED[PREREG],
        'trainer_sha256': sha256(TRAINER),
        'launcher_sha256': sha256(LAUNCHER),
        'test_sha256': sha256(TEST),
        'network_sha256': sha256(NETWORK),
        'probe_count': len(probe_results),
        'probe_arms': [probe['arm'] for probe in probe_results],
        'probe_results': probe_results,
        'unit_result': unit_result,
        'checks': checks,
        'summary': {'passed': passed, 'total': len(checks)},
        'training_started': False,
        'gpu_initialized': False,
        'output_root_exists': OUTPUT_ROOT.exists(),
        'official_hands': 0,
        'strength': 'L0',
        'next': 'STOP_IMPLEMENTATION_READY_ONLY_BEFORE_TRAINING',
    }
    print(json.dumps(result, sort_keys=True, separators=(',', ':')))
    return 0 if status == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
