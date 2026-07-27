#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import random
import sys
from pathlib import Path

THIS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(THIS_DIR))

import train_v5 as trainer  # noqa: E402


def independent_u64(iteration: int) -> int:
    payload = (
        'LG002R_ASSIGNMENT_V1|2320b32682e51ba0e3781407b92d3d75|'
        f'2026072203|{iteration}'
    )
    return int.from_bytes(hashlib.sha256(payload.encode('utf-8')).digest()[:8], 'big')


def independent_hash(record: dict) -> str:
    unsigned = dict(record)
    unsigned.pop('record_sha256', None)
    raw = json.dumps(unsigned, sort_keys=True, separators=(',', ':'), ensure_ascii=False)
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()


def main() -> int:
    checks: dict[str, bool] = {}
    pool = [{'id': member_id} for member_id in trainer.LG002_RECOVERY_CHECKPOINT_ORDER]

    checks['identity_constants_exact'] = (
        trainer.LG002_RECOVERY_TOKEN == '2320b32682e51ba0e3781407b92d3d75'
        and trainer.LG002_RECOVERY_PREREG_SHA256
        == 'ef41b731de6ad74f93d01cbb2f4ce245bcde9323335e331a6c31f0daf3e9eda9'
        and trainer.LG002_RECOVERY_ASSIGNMENT_SEED == 2026072203
    )
    checks['u64_independent_replay_2048'] = all(
        trainer.lg002_assignment_u64(i) == independent_u64(i)
        for i in range(35052, 37100)
    )

    random.seed(90125)
    before = random.getstate()
    pairs = [
        (
            trainer.lg002_select_opponent('control_uniform', i, pool),
            trainer.lg002_select_opponent('treatment_diversity', i, pool),
        )
        for i in range(35052, 35152)
    ]
    after = random.getstate()
    checks['no_global_rng_consumption'] = before == after
    checks['same_u64_and_self_branch_both_arms'] = all(
        control[1]['u64'] == treatment[1]['u64']
        and (
            (control[0] == trainer.HERO_MODEL_ID)
            == (treatment[0] == trainer.HERO_MODEL_ID)
        )
        for control, treatment in pairs
    )

    self_index, self_meta = trainer.lg002_select_from_u64(
        'control_uniform', 0, pool,
    )
    first_pool_index, first_pool_meta = trainer.lg002_select_from_u64(
        'control_uniform', int(0.2 * (1 << 64)), pool,
    )
    checks['left_closed_right_open_self_boundary'] = (
        self_index == trainer.HERO_MODEL_ID
        and self_meta['selected_member_id'] is None
        and first_pool_index == trainer.LG002_RECOVERY_CHECKPOINT_ORDER.index(103)
        and first_pool_meta['selected_member_id'] == 103
    )

    try:
        trainer.lg002_select_opponent(
            'control_uniform', 35052, list(reversed(pool)),
        )
    except ValueError:
        checks['pool_order_fail_closed'] = True
    else:
        checks['pool_order_fail_closed'] = False

    base = trainer.build_assignment_provenance_record(
        run_id='test', applies_to_iteration=35052, total_hands=576021901,
        assignment_mode='per-iteration', assignments=[pairs[0][0][0]],
        pool_snapshots=pool, previous_record_sha256=None,
    )
    enriched = trainer.lg002_enrich_provenance_record(base, pairs[0][0][1])
    checks['provenance_replay_exact'] = (
        enriched['record_sha256'] == independent_hash(enriched)
        and enriched['lg002_recovery']['registration_sha256']
        == trainer.LG002_RECOVERY_PREREG_SHA256
        and enriched['lg002_recovery']['selected_member_state_sha256']
        == pairs[0][0][1]['selected_member_state_sha256']
    )
    checks['weights_exact_and_normalized'] = all(
        abs(sum(weights.values()) - 1.0) <= 1e-12
        for weights in trainer.LG002_RECOVERY_CONDITIONAL_WEIGHTS.values()
    ) and trainer.LG002_RECOVERY_CONDITIONAL_WEIGHTS['treatment_diversity'][120] == 0.325118010944971

    source = Path(trainer.__file__).read_text(encoding='utf-8')
    checks['pool_mutation_guard_present'] = (
        'iteration % args.snapshot_every == 0 and not lg002_recovery_active' in source
        and 'LG002 frozen membership: snapshot addition disabled' in source
    )
    checks['mse_catchup_and_kl_path_preserved'] = (
        "target_kl=args.ppo_target_kl" in source
        and "value_head_catchup=args.h8_value_head_catchup_after_kl_stop" in source
        and "else args.h9_catchup_loss" in source
    )

    passed = sum(bool(value) for value in checks.values())
    result = {
        'schema_version': 'v5.lg002.recovery.implementation_test.v1',
        'status': 'PASS' if passed == len(checks) else 'FAIL',
        'passed': passed,
        'total': len(checks),
        'checks': checks,
    }
    print(json.dumps(result, sort_keys=True, separators=(',', ':')))
    return 0 if result['status'] == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
