from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import random
import sys
import time
from types import SimpleNamespace

import numpy as np
import torch


ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'scripts'))
sys.path.insert(0, str(ROOT / 'scripts' / 'alpha_holdem'))

from alpha_holdem.environment_v6 import BBStateView  # noqa: E402
from alpha_holdem.execution_v6 import load_policy, sha256_file  # noqa: E402
from alpha_holdem.policy_contract_v6 import METADATA, action_table, apply_incr, observation  # noqa: E402
from alpha_holdem.rules_v6 import ChipState  # noqa: E402
from scripts.alpha_holdem.train_v5 import (  # noqa: E402
    PROCEDURAL_OPPONENT_PROFILES,
    procedural_opponent_action,
    procedural_opponent_hand_seed,
    sample_procedural_opponent_style,
)


@dataclass
class Game:
    endpoint: int
    pair_index: int
    hero_seat: int
    state: ChipState
    style: dict
    rng: random.Random
    reward_bb: float | None = None
    hero_decisions: int = 0
    opponent_decisions: int = 0


def model_uses_position(model) -> bool:
    return bool(getattr(model, 'requires_position_feature', False)) or any(
        int(getattr(model, key, 0)) > 0
        for key in ('position_adapter_hidden', 'position_value_adapter_hidden')
    )


@torch.no_grad()
def apply_greedy_batch(model, games: list[Game], device: str) -> None:
    if not games:
        return
    include_position = model_uses_position(model)
    observations = [
        observation(game.state, include_position=include_position)[0]
        for game in games
    ]
    cards = torch.as_tensor(
        np.stack([row['card_info'] for row in observations]),
        dtype=torch.float32,
        device=device,
    )
    actions = torch.as_tensor(
        np.stack([row['action_info'] for row in observations]),
        dtype=torch.float32,
        device=device,
    )
    extras = torch.as_tensor(
        np.stack([row['extra_info'] for row in observations]),
        dtype=torch.float32,
        device=device,
    )
    masks = torch.as_tensor(
        np.stack([row['legal_mask'] for row in observations]),
        dtype=torch.float32,
        device=device,
    )
    logits, _ = model(cards, actions, extras, masks)
    logits = logits.masked_fill(masks <= 0, -1e30)
    slots = torch.argmax(logits, dim=-1).detach().cpu().tolist()
    for game, slot in zip(games, slots):
        table = action_table(game.state)[1]
        increment = table[int(slot)]
        if increment is None:
            raise RuntimeError('batched greedy model selected an illegal slot')
        game.state = apply_incr(game.state, increment)
        game.hero_decisions += 1


def finish_if_terminal(game: Game) -> bool:
    if not game.state.terminal:
        return False
    game.reward_bb = float(game.state.payoffs()[game.hero_seat]) / 100.0
    return True


def play_games(models, games: list[Game], device: str) -> None:
    active = list(games)
    while active:
        for game in active:
            if game.state.actor == game.hero_seat:
                continue
            mask, table = action_table(game.state)
            slot = procedural_opponent_action(
                SimpleNamespace(state=BBStateView(game.state)),
                game.state.actor,
                mask,
                game.style,
                game.rng,
            )
            increment = table[int(slot)]
            if increment is None:
                raise RuntimeError('procedural evaluator selected an illegal slot')
            game.state = apply_incr(game.state, increment)
            game.opponent_decisions += 1

        active = [game for game in active if not finish_if_terminal(game)]
        if not active:
            break
        for endpoint, model in enumerate(models):
            batch = [
                game
                for game in active
                if game.endpoint == endpoint
                and game.state.actor == game.hero_seat
            ]
            apply_greedy_batch(model, batch, device)
        active = [game for game in active if not finish_if_terminal(game)]


def ci95(values) -> tuple[float, float]:
    values = np.asarray(values, dtype=np.float64)
    mean = float(values.mean())
    half = float(1.96 * values.std(ddof=1) / math.sqrt(len(values)))
    return mean - half, mean + half


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--control', required=True)
    parser.add_argument('--treatment', required=True)
    parser.add_argument('--out-dir', required=True)
    parser.add_argument('--device', default='cuda')
    parser.add_argument('--pairs-per-block', type=int, default=4096)
    parser.add_argument('--chunk-pairs', type=int, default=128)
    parser.add_argument(
        '--block-seeds',
        type=int,
        nargs='+',
        default=[
            2026110801,
            2026110802,
            2026110803,
            2026110804,
            2026110805,
            2026110806,
            2026110807,
            2026110808,
        ],
    )
    args = parser.parse_args()
    if args.pairs_per_block <= 1 or args.chunk_pairs <= 0:
        parser.error('pairs-per-block must exceed1 and chunk-pairs must be positive')
    if len(args.block_seeds) != 8 or len(set(args.block_seeds)) != 8:
        parser.error('exactly eight unique heldout block seeds are required')

    output = Path(args.out_dir)
    output.mkdir(parents=True, exist_ok=False)
    torch.set_num_threads(1)
    control, _, control_sha = load_policy(args.control, args.device)
    treatment, _, treatment_sha = load_policy(args.treatment, args.device)
    models = [control, treatment]
    started = time.time()
    endpoint_values = [[], []]
    delta_values = []
    block_rows = []
    profile_counts = [0 for _ in PROCEDURAL_OPPONENT_PROFILES]
    pair_global = 0

    pairs_path = output / 'pairs.jsonl'
    with pairs_path.open('x', encoding='utf-8', newline='\n') as handle:
        for block_index, block_seed in enumerate(args.block_seeds):
            deck_rng = random.Random(int(block_seed))
            block_deltas = []
            block_endpoint = [[], []]
            for chunk_start in range(0, args.pairs_per_block, args.chunk_pairs):
                chunk_size = min(
                    args.chunk_pairs, args.pairs_per_block - chunk_start
                )
                pair_specs = []
                games = []
                for local_offset in range(chunk_size):
                    local_pair = chunk_start + local_offset
                    deck = list(range(52))
                    deck_rng.shuffle(deck)
                    styles = []
                    for hero_seat in (0, 1):
                        style_seed = procedural_opponent_hand_seed(
                            int(block_seed), 2 * local_pair + hero_seat
                        )
                        style_rng = random.Random(style_seed)
                        style_rng.random()  # match training fraction-selection draw
                        style = sample_procedural_opponent_style(style_rng)
                        styles.append((style_seed, style))
                        profile_counts[int(style['profile_id'])] += 1
                    pair_specs.append((pair_global, deck, styles))
                    for endpoint in (0, 1):
                        for hero_seat in (0, 1):
                            style_seed, style = styles[hero_seat]
                            style_rng = random.Random(style_seed)
                            style_rng.random()
                            replay_style = sample_procedural_opponent_style(style_rng)
                            if replay_style != style:
                                raise RuntimeError('style replay mismatch before play')
                            games.append(Game(
                                endpoint=endpoint,
                                pair_index=pair_global,
                                hero_seat=hero_seat,
                                state=ChipState.new(deck),
                                style=style,
                                rng=style_rng,
                            ))
                    pair_global += 1

                play_games(models, games, args.device)
                by_pair = {}
                for game in games:
                    if game.reward_bb is None:
                        raise RuntimeError('game completed without a reward')
                    by_pair.setdefault(game.pair_index, {})[
                        (game.endpoint, game.hero_seat)
                    ] = game
                for pair_index, deck, styles in pair_specs:
                    rewards = [
                        [by_pair[pair_index][(endpoint, seat)].reward_bb for seat in (0, 1)]
                        for endpoint in (0, 1)
                    ]
                    pair_means = [float(np.mean(values)) * 100.0 for values in rewards]
                    delta = pair_means[1] - pair_means[0]
                    endpoint_values[0].append(pair_means[0])
                    endpoint_values[1].append(pair_means[1])
                    block_endpoint[0].append(pair_means[0])
                    block_endpoint[1].append(pair_means[1])
                    delta_values.append(delta)
                    block_deltas.append(delta)
                    row = {
                        'block_index': block_index,
                        'block_seed': int(block_seed),
                        'pair_index': pair_index,
                        'deck': deck,
                        'style_seeds': [int(value[0]) for value in styles],
                        'profile_ids': [
                            int(value[1]['profile_id']) for value in styles
                        ],
                        'control_rewards_bb': rewards[0],
                        'treatment_rewards_bb': rewards[1],
                        'control_bb_per_100': pair_means[0],
                        'treatment_bb_per_100': pair_means[1],
                        'treatment_minus_control_bb_per_100': delta,
                        'hero_decisions': [
                            [
                                by_pair[pair_index][(endpoint, seat)].hero_decisions
                                for seat in (0, 1)
                            ]
                            for endpoint in (0, 1)
                        ],
                        'opponent_decisions': [
                            [
                                by_pair[pair_index][(endpoint, seat)].opponent_decisions
                                for seat in (0, 1)
                            ]
                            for endpoint in (0, 1)
                        ],
                    }
                    handle.write(json.dumps(row, separators=(',', ':')) + '\n')
                handle.flush()
                print(json.dumps({
                    'block': block_index + 1,
                    'blocks': len(args.block_seeds),
                    'completed_pairs': len(delta_values),
                    'target_pairs': args.pairs_per_block * len(args.block_seeds),
                }), flush=True)

            block_rows.append({
                'block_index': block_index,
                'block_seed': int(block_seed),
                'pairs': len(block_deltas),
                'control_bb_per_100': float(np.mean(block_endpoint[0])),
                'treatment_bb_per_100': float(np.mean(block_endpoint[1])),
                'treatment_minus_control_bb_per_100': float(np.mean(block_deltas)),
                'delta_ci95': list(ci95(block_deltas)),
            })

    if sha256_file(args.control) != control_sha:
        raise RuntimeError('control checkpoint changed during evaluation')
    if sha256_file(args.treatment) != treatment_sha:
        raise RuntimeError('treatment checkpoint changed during evaluation')
    delta_ci = ci95(delta_values)
    summary = {
        **METADATA,
        'schema': 'cardpilot.procedural_heldout_paired_eval.v1',
        'status': 'COMPLETED',
        'policy_mode': 'greedy',
        'control_sha256': control_sha,
        'treatment_sha256': treatment_sha,
        'block_seeds': args.block_seeds,
        'pairs_per_block': args.pairs_per_block,
        'pairs': len(delta_values),
        'evaluation_hands': 4 * len(delta_values),
        'profile_counts_per_seat_pair': profile_counts,
        'control_bb_per_100': float(np.mean(endpoint_values[0])),
        'control_ci95': list(ci95(endpoint_values[0])),
        'treatment_bb_per_100': float(np.mean(endpoint_values[1])),
        'treatment_ci95': list(ci95(endpoint_values[1])),
        'treatment_minus_control_bb_per_100': float(np.mean(delta_values)),
        'paired_delta_ci95': list(delta_ci),
        'positive_blocks': sum(
            row['treatment_minus_control_bb_per_100'] > 0 for row in block_rows
        ),
        'blocks': block_rows,
        'gate': {
            'paired_delta_positive': float(np.mean(delta_values)) > 0.0,
            'paired_delta_ci_lower_positive': delta_ci[0] > 0.0,
            'at_least_six_of_eight_blocks_positive': sum(
                row['treatment_minus_control_bb_per_100'] > 0
                for row in block_rows
            ) >= 6,
        },
        'pairs_sha256': sha256_file(pairs_path),
        'wall_time_seconds': time.time() - started,
        'completed_at': datetime.now(timezone.utc).isoformat(),
        'command': [sys.executable, *sys.argv],
    }
    summary['gate']['passed'] = all(summary['gate'].values())
    (output / 'summary.json').write_text(
        json.dumps(summary, indent=2, sort_keys=True) + '\n',
        encoding='utf-8',
    )
    print(json.dumps(summary, sort_keys=True))


if __name__ == '__main__':
    main()
