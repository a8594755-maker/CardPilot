import hashlib
import json
import sys
from pathlib import Path

import pytest
import torch

sys.path.insert(0, str(Path(__file__).resolve().parent))

from scripts.alpha_holdem.train_v5 import (
    OpponentPool,
    elo_expected_score,
    elo_match_seed,
    hash_chained_elo_records,
    run_elo_survivor_tournament,
    update_elo_pair,
    write_elo_tournament_evidence,
)


def test_elo_update_is_symmetric_and_conserves_rating():
    assert elo_expected_score(1500.0, 1500.0) == pytest.approx(0.5)
    rating_a, rating_b, detail = update_elo_pair(
        1500.0,
        1500.0,
        wins_a=3,
        draws=1,
        losses_a=0,
        k_factor=32.0,
    )
    assert rating_a > 1500.0
    assert rating_b < 1500.0
    assert rating_a + rating_b == pytest.approx(3000.0)
    assert detail['actual_score_a'] == pytest.approx(0.875)


def test_elo_match_seed_is_pair_symmetric_and_tournament_specific():
    forward = elo_match_seed(71, 3, 12, 4)
    assert forward == elo_match_seed(71, 3, 4, 12)
    assert forward != elo_match_seed(71, 4, 4, 12)


def test_elo_pool_prunes_by_rating_without_reusing_identity():
    pool = OpponentPool(k=2, strategy='elo-kbest')
    state = {'weight': torch.tensor([1.0])}
    first = pool.add(state, selection_score=1400.0)
    second = pool.add(state, selection_score=1600.0)
    third = pool.add(state, selection_score=1500.0)
    assert [first['id'], second['id'], third['id']] == [0, 1, 2]
    assert set(pool.active_ids()) == {1, 2}
    resumed = OpponentPool(k=2, strategy='elo-kbest')
    resumed.load_from_checkpoint(
        pool.snapshots,
        candidate_history=pool.candidate_history,
    )
    fourth = resumed.add(state, selection_score=1700.0)
    assert fourth['id'] == 3
    assert set(resumed.active_ids()) == {1, 3}


def test_elo_pool_can_combine_external_and_initial_hero_seeds():
    pool = OpponentPool(k=4, strategy='elo-kbest')
    external = pool.add(
        {'weight': torch.tensor([1.0])},
        selection_score=1500.0,
        score_components={'kind': 'initial_external_opponent'},
    )
    initial_hero = pool.add(
        {'weight': torch.tensor([2.0])},
        hands=0,
        iteration=0,
        selection_score=1500.0,
        score_components={'kind': 'initial_random_policy'},
    )
    assert [external['id'], initial_hero['id']] == [0, 1]
    assert pool.active_ids() == [0, 1]
    assert [row['score_components']['kind'] for row in pool.snapshots] == [
        'initial_external_opponent',
        'initial_random_policy',
    ]


def test_elo_history_hash_chain_is_canonical_and_atomic(tmp_path):
    history = [
        {'tournament_index': 1, 'ratings': {'0': 1510.0}},
        {'tournament_index': 2, 'ratings': {'0': 1505.0, '1': 1495.0}},
    ]
    records = hash_chained_elo_records(history)
    assert records[0]['previous_record_sha256'] is None
    assert records[1]['previous_record_sha256'] == records[0]['record_sha256']
    for record in records:
        claimed = record['record_sha256']
        unhashed = dict(record)
        unhashed.pop('record_sha256')
        canonical = json.dumps(
            unhashed,
            sort_keys=True,
            separators=(',', ':'),
            ensure_ascii=False,
        )
        assert hashlib.sha256(canonical.encode('utf-8')).hexdigest() == claimed

    evidence_path = tmp_path / 'elo_tournaments.jsonl'
    write_elo_tournament_evidence(evidence_path, history)
    loaded = [json.loads(line) for line in evidence_path.read_text().splitlines()]
    assert loaded == records
    assert not evidence_path.with_suffix('.jsonl.tmp').exists()


def test_tournament_order_accounting_determinism_and_mode_restore(monkeypatch):
    from alpha_holdem import v5_mirror_eval

    calls = []

    def fake_summarize_anchor(*, candidate, anchor, pairs, seed,
                              starting_stack, include_pair_outcomes):
        candidate_id = int(candidate.label.rsplit('_', 1)[1])
        anchor_id = int(anchor.label.rsplit('_', 1)[1])
        calls.append((candidate_id, anchor_id, pairs, seed))
        return {
            'pair_wins': pairs if candidate_id % 2 == 0 else 0,
            'pair_draws': 0,
            'pair_losses': 0 if candidate_id % 2 == 0 else pairs,
            'candidate_bb100': 5.0 if candidate_id % 2 == 0 else -5.0,
            'candidate_ci95_bb100': 1.0,
            'ood_nodes': {'candidate': 0, 'anchor': 0},
        }

    monkeypatch.setattr(v5_mirror_eval, 'summarize_anchor', fake_summarize_anchor)
    models = [torch.nn.Linear(1, 1) for _ in range(3)]
    models[0].train(True)
    models[1].train(False)
    models[2].train(True)
    original_modes = [model.training for model in models]
    competitors = [
        {
            'id': competitor_id,
            'model': model,
            'rating': 1500.0,
            'state_sha256': f'sha-{competitor_id}',
        }
        for competitor_id, model in zip((4, 7, 9), models)
    ]

    first = run_elo_survivor_tournament(
        competitors=competitors,
        pairs=8,
        base_seed=123,
        tournament_index=2,
        starting_stack=200.0,
        device='cpu',
        k_factor=32.0,
    )
    first_calls = list(calls)
    calls.clear()
    second = run_elo_survivor_tournament(
        competitors=competitors,
        pairs=8,
        base_seed=123,
        tournament_index=2,
        starting_stack=200.0,
        device='cpu',
        k_factor=32.0,
    )
    assert first == second
    assert calls == first_calls
    assert [(row[0], row[1]) for row in first_calls] == [(4, 7), (4, 9), (7, 9)]
    assert first['evaluation_hands'] == 3 * 8 * 2
    assert first['total_ood_nodes'] == 0
    assert [model.training for model in models] == original_modes


def test_physical_v6_tournament_uses_exact_contract_and_restores_modes(monkeypatch):
    from alpha_holdem import v6_elo_eval

    calls = []

    def fake_summarize_models(**kwargs):
        calls.append((kwargs['pairs'], kwargs['seed'], kwargs['observation_style']))
        return {
            'pair_wins': kwargs['pairs'],
            'pair_draws': 0,
            'pair_losses': 0,
            'candidate_bb100': 7.0,
            'candidate_ci95_bb100': 2.0,
            'ood_nodes': {'candidate': 0, 'anchor': 0},
            'evaluation_contract': 'physical_v6_legacy_v4_observation_v1',
        }

    monkeypatch.setattr(v6_elo_eval, 'summarize_models', fake_summarize_models)
    models = [torch.nn.Linear(1, 1), torch.nn.Linear(1, 1)]
    models[0].train(True)
    models[1].train(False)
    result = run_elo_survivor_tournament(
        competitors=[
            {'id': index, 'model': model, 'rating': 1500.0,
             'state_sha256': f'sha-{index}'}
            for index, model in enumerate(models)
        ],
        pairs=4,
        base_seed=17,
        tournament_index=1,
        starting_stack=200.0,
        device='cpu',
        k_factor=32.0,
        env_version='v6legacyv4obs',
    )
    assert calls == [(4, elo_match_seed(17, 1, 0, 1), 'legacy_v4')]
    assert result['evaluation_contract'] == (
        'physical_v6_legacy_v4_observation_v1'
    )
    assert result['evaluation_hands'] == 8
    assert [model.training for model in models] == [True, False]
