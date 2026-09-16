from datetime import datetime, timezone

import pytest

import recovery_chain as r


@pytest.mark.parametrize('seed,arm,stage', [(s, a, stage) for stage, order in r.normal.ORDERS.items() for s, a in order])
def test_endpoint_only_redirects_interrupted_stage(tmp_path, seed, arm, stage):
    expected = tmp_path / ('recovery_20260906/seed1_connected_stage1_remainder'
                          if (seed, arm, stage) == (1, 'connected', 1) else f'seed{seed}_{arm}_stage{stage}')
    assert r.endpoint(tmp_path, seed, arm, stage) == expected


@pytest.mark.parametrize('cell', [(2, 'connected', 1), (1, 'half', 1), (1, 'connected', 3)])
def test_unknown_cells_rejected(tmp_path, cell):
    with pytest.raises(ValueError):
        r.endpoint(tmp_path, *cell)


def test_hash_conflicts_are_not_silently_overwritten():
    assert r.merge_hashes({'a': 'x'}, {'a': 'x', 'b': 'y'}) == {'a': 'x', 'b': 'y'}
    with pytest.raises(ValueError, match='conflicting'):
        r.merge_hashes({'a': 'x'}, {'a': 'z'})


def counts(physical, transition, no_decision, residual, replay):
    return dict(zip(r.DELTA_KEYS, (physical, transition, no_decision, residual, replay)))


def test_partial_plus_remainder_telescopes_once_without_replay_as_hands():
    partial = counts(8987, 8253, 734, 0, 14202)
    remainder = counts(300, 250, 40, 10, 900)
    combined = r.combined_deltas(partial, remainder)
    assert combined == counts(9287, 8503, 774, 10, 15102)
    assert partial == counts(8987, 8253, 734, 0, 14202)


@pytest.mark.parametrize('bad', [counts(10, 12, 0, 0, 4), counts(10, 8, -1, 3, 4), counts(10., 8, 2, 0, 4)])
def test_invalid_retained_counts_rejected(bad):
    with pytest.raises(ValueError):
        r.combined_deltas(counts(8987, 8253, 734, 0, 14202), bad)


def test_all_adam_clocks_combine_and_incomplete_or_reset_state_rejects():
    left, right = ({str(i): n for i in range(86)} for n in (2, 17))
    assert set(r.combined_adam_steps(left, right).values()) == {19}
    with pytest.raises(ValueError):
        r.combined_adam_steps(left, {k: v for k, v in right.items() if k != '0'})
    right['0'] = 0
    with pytest.raises(ValueError):
        r.combined_adam_steps(left, right)


def stamp(seconds):
    return datetime.fromtimestamp(seconds, timezone.utc).isoformat()


def test_unknown_exit_produces_observation_bounds_not_exact_or_zero_cost():
    process = {'pid': 7, 'create_time': 100.}
    status = {'active_child_pid': 7, 'updated_at': stamp(130)}
    audit = {'created_at': stamp(180), 'original_controller_last_status_at': stamp(130)}
    assert r.interrupted_wall_bounds(process, status, audit) == [30., 80.]
    status['active_child_pid'] = 8
    with pytest.raises(ValueError):
        r.interrupted_wall_bounds(process, status, audit)


def test_inverted_timing_rejected():
    with pytest.raises(ValueError):
        r.interrupted_wall_bounds({'pid': 7, 'create_time': 100.},
            {'active_child_pid': 7, 'updated_at': stamp(130)},
            {'created_at': stamp(120), 'original_controller_last_status_at': stamp(130)})


@pytest.mark.parametrize('live_pid', (1, 2))
def test_either_live_owner_blocks_before_any_outcome_read(monkeypatch, tmp_path, live_pid):
    reads = []
    def fake_read(path):
        reads.append(path)
        assert path.name == 'ownership.json', 'must not read outcome metadata while owner live'
        return {'pid': 2 if path.parent.name == 'recovery_20260906' else 1, 'create_time': 1.}
    monkeypatch.setattr(r, 'read', fake_read)
    monkeypatch.setattr(r, 'live', lambda pid, _: pid == live_pid)
    with pytest.raises(ValueError, match='controller still live'):
        r.terminal_guard(tmp_path)
    assert len(reads) == live_pid
