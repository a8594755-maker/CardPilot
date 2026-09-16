from __future__ import annotations

import importlib.util
from pathlib import Path
import random
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'scripts'))
sys.path.insert(0, str(ROOT / 'scripts' / 'alpha_holdem'))

from alpha_holdem.execution_v6 import decide, load_policy
from alpha_holdem.policy_contract_v6 import action_table, apply_incr
from alpha_holdem.rules_v6 import ChipState


HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location(
    'procedural_heldout_eval', HERE / 'evaluate_heldout.py'
)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_batched_greedy_actions_match_deployment_decide_exactly():
    checkpoint = HERE / 'control' / 'latest.pt'
    model, _, _ = load_policy(checkpoint, 'cpu')
    rng = random.Random(2026110899)
    games = []
    expected_states = []
    while len(games) < 128:
        deck = list(range(52))
        rng.shuffle(deck)
        state = ChipState.new(deck)
        for _ in range(rng.randrange(12)):
            if state.terminal:
                break
            _, table = action_table(state)
            legal = [increment for increment in table if increment is not None]
            state = apply_incr(state, rng.choice(legal))
        if state.terminal:
            continue
        expected_increment, _ = decide(
            model,
            state,
            uniform=0.5,
            device='cpu',
            policy_mode='greedy',
        )
        style_rng = random.Random(len(games))
        style = MODULE.sample_procedural_opponent_style(style_rng)
        game = MODULE.Game(
            endpoint=0,
            pair_index=len(games),
            hero_seat=state.actor,
            state=state,
            style=style,
            rng=style_rng,
        )
        games.append(game)
        expected_states.append(apply_incr(state, expected_increment))

    MODULE.apply_greedy_batch(model, games, 'cpu')
    assert [game.state for game in games] == expected_states


def test_smoke_evidence_has_complete_common_randomness_rows():
    smoke = HERE / 'heldout_smoke'
    rows = [
        MODULE.json.loads(line)
        for line in (smoke / 'pairs.jsonl').read_text(encoding='utf-8').splitlines()
        if line.strip()
    ]
    summary = MODULE.json.loads(
        (smoke / 'summary.json').read_text(encoding='utf-8')
    )
    assert len(rows) == summary['pairs'] == 16
    assert summary['evaluation_hands'] == 4 * len(rows)
    assert MODULE.sha256_file(smoke / 'pairs.jsonl') == summary['pairs_sha256']
    assert sorted({row['block_index'] for row in rows}) == list(range(8))
    assert all(len(row['control_rewards_bb']) == 2 for row in rows)
    assert all(len(row['treatment_rewards_bb']) == 2 for row in rows)
