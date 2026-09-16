"""Five deterministic production-contract probes, without completed hands or network."""
import importlib.util
import json
from pathlib import Path
import shutil
import sys
from unittest.mock import patch

import numpy as np
import psutil
import requests

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[2]
sys.path.insert(0, str(ROOT))
from research.experiment_log import capture_code_provenance, sha256_file

MAPPING = 'preflop_pot_fraction_v2'


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def action_strings(table, action_type):
    labels = {action_type.FOLD: 'f', action_type.CHECK: 'k', action_type.CALL: 'c'}
    return [None if action is None else labels.get(action.type, f'b{round(100*action.amount)}') for action in table]


def describe(state):
    return dict(street=int(state.street), actor=int(state.current_player), board_cards=len(state.board),
        pot_bb=state.pot, stacks_bb=state.stacks, street_committed_bb=state.street_committed,
        terminal=state.is_terminal())


def main():
    if sys.argv[1:]:
        raise ValueError('No alternate fixtures or automatic rerun')
    for process in psutil.process_iter(['pid', 'name', 'cmdline']):
        if process.pid == psutil.Process().pid:
            continue
        if (process.info['name'] or '').lower().startswith('python') and any(
                Path(arg).name in ['train_v5.py', 'v5_mirror_eval.py', 'play_slumbot.py', 'run_external.py', 'run_confirmation.py']
                for arg in process.info['cmdline'] or []):
            raise RuntimeError('Wait for existing poker writers to exit')
    record = json.loads((BASE/'experiment.json').read_text())
    if record['status'] != 'RUNNING':
        raise ValueError('Preregistered RUNNING record required')
    directory = BASE/'execution_code'
    if directory.exists() or (BASE/'audit_analysis.json').exists():
        raise ValueError('Preserve existing evidence; do not overwrite')
    directory.mkdir(exist_ok=False)
    paths = [p.relative_to(ROOT).as_posix() for p in sorted((ROOT/'scripts/alpha_holdem').glob('*.py'))]
    paths += [f'scripts/deep_cfr/{name}.py' for name in ['__init__', 'game_state', 'hand_eval']]
    paths += ['research/experiment_log.py', Path(__file__).relative_to(ROOT).as_posix(),
              (BASE/'preregistration.md').relative_to(ROOT).as_posix()]
    capture_code_provenance(ROOT, directory, paths)
    copies = []
    for relative in paths:
        target = directory/'source_files'/relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT/relative, target)
        copies.append(dict(original=relative, copy=target.relative_to(ROOT).as_posix(), sha256=sha256_file(target)))
    (directory/'copy_manifest.json').write_text(json.dumps(copies, indent=2)+'\n')

    def verify():
        for item in copies:
            if any(sha256_file(ROOT/item[key]) != item['sha256'] for key in ['original', 'copy']):
                raise ValueError('Captured execution source changed')

    verify()
    attempted_network = []

    def deny_network(*args, **kwargs):
        attempted_network.append(True)
        raise AssertionError('No network in deterministic contract audit')

    findings = []
    with patch.object(requests.sessions.Session, 'request', deny_network), \
         patch('socket.socket.connect', deny_network), patch('socket.create_connection', deny_network):
        source = directory/'source_files/scripts/alpha_holdem'
        mirror = load('contract_mirror', source/'v5_mirror_eval.py')
        client = load('contract_client', source/'play_slumbot.py')
        from alpha_holdem.environment_v55 import HUNLEnvironmentV55, build_action_table, encode_action_history_v4
        from deep_cfr.game_state import Action, ActionType, Street

        training = HUNLEnvironmentV55(starting_stack=200., action_history_style='v4', raise_action_mapping=MAPPING)
        training.state = mirror.make_fixed_state(training, list(range(52)))
        root_obs = training._get_obs()
        default_env = HUNLEnvironmentV55(starting_stack=200.)
        mirror_state = mirror.make_fixed_state(default_env, list(range(52)))
        mirror_obs, mirror_table = mirror.observation_for(mirror_state, 1, 'v4', include_position=False)
        external_mask, external_table = client.build_action_table(client.parse_action(''), MAPPING)
        training_table = action_strings(training.last_action_table, ActionType)
        mirror_table = action_strings(mirror_table, ActionType)
        findings.append(dict(probe='posted_blinds_action_binding',
            training_mask=root_obs['legal_mask'].tolist(), training_actions=training_table,
            mirror_mask=mirror_obs['legal_mask'].tolist(), mirror_actions=mirror_table,
            slumbot_mask=external_mask.tolist(), slumbot_actions=external_table,
            trainer_matches_slumbot=training_table == external_table and np.array_equal(root_obs['legal_mask'], external_mask),
            mismatch=training_table != mirror_table or not np.array_equal(root_obs['legal_mask'], mirror_obs['legal_mask'])))

        after_limp = training.state.apply(training.last_action_table[1])
        external_limp = client.parse_action('c')
        findings.append(dict(probe='sb_completion_bb_option', native=describe(after_limp),
            slumbot=dict(street=external_limp['st'], actor=external_limp['pos'], board_cards=0),
            mismatch=int(after_limp.street) != external_limp['st'] or after_limp.current_player != external_limp['pos']))

        # Construct the physical state after a legal limp-check, independently
        # of the native first-CALL transition. No production engine is patched.
        flop = training.state.clone()
        flop.street, flop.current_player = Street.FLOP, 0
        flop.pot, flop.stacks, flop.street_committed = 2., [199., 199.], [0., 0.]
        flop.raise_count, flop.last_bet_size, flop.num_actions_this_street = 0, 0., 0
        flop.board, flop.deck = [49, 50, 51], list(range(4, 49))
        flop.actions_history = [(1, Action(ActionType.CALL)), (0, Action(ActionType.CHECK))]
        flop_mask, flop_table = build_action_table(flop, MAPPING)
        flop_strings = action_strings(flop_table, ActionType)
        external_flop_mask, external_flop_table = client.build_action_table(client.parse_action('ck/'), MAPPING)
        sub_big_blind = [a.amount for a in flop.legal_actions() if a.type == ActionType.BET and a.amount < 1.]
        findings.append(dict(probe='flop_minimum_opening_bet', native=describe(flop),
            native_mask=flop_mask.tolist(), native_actions=flop_strings,
            slumbot_mask=external_flop_mask.tolist(), slumbot_actions=external_flop_table,
            native_opening_bets_below_one_bb=sub_big_blind,
            mismatch=bool(sub_big_blind) or flop_strings != external_flop_table))

        opening = next(a for a in flop.legal_actions() if a.type == ActionType.BET and a.amount == 3.)
        facing_bet = flop.apply(opening)
        facing_mask, facing_table = build_action_table(facing_bet, MAPPING)
        external_facing_mask, external_facing_table = client.build_action_table(client.parse_action('ck/b300'), MAPPING)
        short_raises = [a.amount for a in facing_bet.legal_actions() if a.type == ActionType.RAISE and a.amount < 6.]
        findings.append(dict(probe='full_raise_increment_after_three_bb_bet', native=describe(facing_bet),
            native_mask=facing_mask.tolist(), native_actions=action_strings(facing_table, ActionType),
            slumbot_mask=external_facing_mask.tolist(), slumbot_actions=external_facing_table,
            native_non_allin_raise_targets_below_six_bb=short_raises,
            mismatch=bool(short_raises) or action_strings(facing_table, ActionType) != external_facing_table))

        facing_allin = flop.apply(flop_table[8])
        external_allin = client.parse_action('ck/b19900')
        native_action = encode_action_history_v4(facing_allin, 1)
        external_action = client.encode_action_history(external_allin, 1, external_allin['pos'], obs_version='v4')
        cells = np.argwhere(native_action != external_action)
        findings.append(dict(probe='opening_allin_v4_action_type', native=describe(facing_allin),
            slumbot=dict(street=external_allin['st'], actor=external_allin['pos'], commitments=client.compute_commitments(external_allin)),
            differences=[dict(index=cell.tolist(), native=float(native_action[tuple(cell)]),
                slumbot=float(external_action[tuple(cell)])) for cell in cells], mismatch=bool(len(cells))))
        if any(state.is_terminal() for state in [training.state, mirror_state, after_limp, flop, facing_bet, facing_allin]):
            raise ValueError('Synthetic contract audit must not complete a hand')
    verify()
    if attempted_network:
        raise ValueError('Unexpected network attempt')
    differences = sum(bool(row['mismatch']) for row in findings)
    result = dict(status='COMPLETED', decision='CONTRACT_DIVERGENCE_FOUND' if differences else 'FIXED_PROBES_MATCH',
        probe_count=len(findings), discrepant_probes=differences, actual_training_hands=0,
        actual_evaluation_hands=0, actual_slumbot_hands=0, completed_environment_hands=0,
        network_calls_attempted=0, captured_source_pairs=len(copies), frozen_sources_unchanged=True,
        findings=findings, limitations=['Deterministic counterexamples, not representative policy strength or causal loss attribution.',
            'Constructed flop fixture isolates the public-state legal table from the separate SB-limp transition discrepancy.',
            'No historical hand, checkpoint, source or result is modified; further repair requires its own recorded experiment.'])
    (BASE/'audit_analysis.json').write_text(json.dumps(result, indent=2, sort_keys=True)+'\n')
    lines = ['# Native state contract audit', '', f"Decision: `{result['decision']}`.", '',
        '| Fixed probe | Discrepancy observed |', '|---|---|',
        *[f"| {row['probe']} | {row['mismatch']} |" for row in findings], '',
        'Zero completed environment hands, training hands, external hands or network attempts.', '',
        *['- '+item for item in result['limitations']]]
    (BASE/'result_summary.md').write_text('\n'.join(lines)+'\n', encoding='utf-8')
    print(json.dumps(dict(decision=result['decision'], probe_count=len(findings), discrepant_probes=differences,
        actual_training_hands=0, actual_evaluation_hands=0, actual_slumbot_hands=0)))


if __name__ == '__main__':
    main()
