"""An explicit RNG origin permits partial-lineage evidence, not broken chains."""
import copy
import random
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from scripts.alpha_holdem.train_v5_managed_candidate import (
    build_assignment_provenance_record, build_group_opponent_assignments,
    restore_group_assignment_rng_from_evidence,
)


def evidence():
    rng = random.Random(20260904)
    # Non-seed state ensures replay cannot silently fall back to reseeding.
    for _ in range(19):
        rng.random()
    origin = {'first_iteration': 883, 'python_rng_state': rng.getstate()}
    records = []
    for iteration in range(883, 886):
        weights = [0.2, 0.3, 0.5]
        assignments, groups = build_group_opponent_assignments(
            worker_count=6, pool_size=3, group_count=3, self_play_fraction=1/3,
            rng=rng, pool_weights=weights)
        records.append(build_assignment_provenance_record(
            run_id='origin', applies_to_iteration=iteration,
            total_hands=200 * iteration, assignment_mode='per-group',
            assignments=assignments.tolist(), pool_snapshots=[
                {'id': n, 'hands': 0, 'iteration': 0} for n in range(3)],
            group_metadata=groups['groups'], worker_seed_base=700,
            previous_record_sha256=records[-1]['record_sha256'] if records else None,
            pool_sampling_weights=weights))
    return origin, records, rng.getstate()


def restore(origin, records):
    rng = random.Random(0)
    result = restore_group_assignment_rng_from_evidence(
        records, [], rng=rng, seed=20260904, worker_count=6, pool_size=3,
        group_count=3, self_play_fraction=1/3, checkpoint_iteration=884,
        checkpoint_total_hands=200*885, pool_snapshot_ids=[0, 1, 2], replay_origin=origin)
    return result, rng.getstate()


def test_partial_lineage_origin_restores_pending_assignment_and_rng():
    origin, records, expected_rng = evidence()
    result, actual_rng = restore(origin, records)
    assert actual_rng == expected_rng
    assert result['records_verified'] == 3
    assert result['pending_assignments'] == [row['opponent']['local_index'] for row in records[-1]['workers']]


def test_partial_lineage_without_origin_rejected():
    _, records, _ = evidence()
    with pytest.raises(ValueError, match='not contiguous'):
        restore(None, records)


@pytest.mark.parametrize('kind', ['hash', 'link', 'gap', 'origin_rng', 'origin_iteration'])
def test_origin_never_bypasses_evidence_checks(kind):
    origin, records, _ = evidence()
    records = copy.deepcopy(records)
    if kind == 'hash':
        records[0]['record_sha256'] = '0'*64
    elif kind == 'link':
        records[1]['previous_record_sha256'] = '0'*64
    elif kind == 'gap':
        records.pop(1)
    elif kind == 'origin_rng':
        origin['python_rng_state'] = random.Random(78).getstate()
    else:
        origin['first_iteration'] = 1
    with pytest.raises(ValueError):
        restore(origin, records)


@pytest.mark.parametrize('extra, message', [
    ([], 'fixed-deal resume requires --managed-deal-attempts'),
    (['--managed-deal-attempts'], 'requires --no-reset-optimizer'),
    (['--managed-deal-attempts', '--no-reset-optimizer', '--reset-hand-counter'], 'inherited hand counters'),
])
def test_unsafe_resume_rejected_before_checkpoint_or_worker(monkeypatch, capsys, extra, message):
    from scripts.alpha_holdem.train_v5_managed_candidate import main
    monkeypatch.setattr(sys, 'argv', ['trainer', '--resume', 'does-not-exist.pt',
                                     '--fixed-training-deal-stream', *extra])
    with pytest.raises(SystemExit) as error:
        main()
    assert error.value.code == 2
    assert message in capsys.readouterr().err
