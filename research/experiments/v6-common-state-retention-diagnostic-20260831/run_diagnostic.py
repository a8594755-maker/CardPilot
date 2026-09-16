"""Fixed exogenous-state probability probes while strength evaluation runs."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import random
import re
import shutil
import socket
import subprocess
import sys
import time
from unittest.mock import patch

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[2]
LIVE = ROOT/'research/experiments/v6-source-kl-retention-pilot-20260831'
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT/'scripts'))
from research.experiment_log import capture_code_provenance, sha256_file
from metrics import distribution_metrics, summarize, FLOOR

EXPECTED = dict(source='944f5f6625e29c2d2562cc457206aafcf840ef0c7edd6accbd372e1362dd57b2',
                weak_control='0d2f660b3225664c5ed2bc85467649d3f3d17930cba8ab86c70b3d2082ee8606',
                treatment='9b7b0e3a0c2be3bdfbbab4167e1eb4a5e7f284d619a8afa13d608c9943b46efb')


def logger(verb, *args):
    subprocess.run([sys.executable, str(ROOT/'research/experiment_log.py'), verb, BASE.name,
                    *map(str, args)], cwd=ROOT, check=True)


def verify(copies):
    for item in copies:
        assert all(sha256_file(ROOT/item[k]) == item['sha256'] for k in ['original', 'copy'])


def choose(state, rng, index, table):
    legal = [x for x in table if x is not None]
    mode = index % 4
    if mode == 1: return table[1] if rng.random() < .8 else rng.choice(legal)
    if mode == 2: return f'b{state.min_to}' if state.can_raise and rng.random() < .7 else table[1]
    if mode == 3 and state.can_raise and rng.random() < .5: return f'b{rng.randint(state.min_to, state.max_to)}'
    return rng.choice(legal)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--attempt', required=True)
    args = parser.parse_args()
    if not re.fullmatch(r'attempt[0-9]{2}', args.attempt): raise ValueError('Explicit new attempt required')
    out = BASE/args.attempt
    out.mkdir(exist_ok=False)
    started = time.time()
    command = f'python research/experiments/{BASE.name}/run_diagnostic.py --attempt {args.attempt}'
    logger('update', '--command', command, '--note', f'{args.attempt}started;fixed512model-independent hands,no partial strength results consumed.')
    report = dict(status='RUNNING', command=command, pid=os.getpid(), new_training_hands=0, evaluation_hands=0,
                  slumbot_hands=0, diagnostic_hands=0, diagnostic_states=0)
    def save(): (out/'analysis.json').write_text(json.dumps(report, indent=2, allow_nan=False)+'\n')
    save()
    try:
        live_copies = json.loads((LIVE/'execution_code/copy_manifest.json').read_text())
        verify(live_copies)
        candidates = json.loads((LIVE/'candidate_manifest.json').read_text())
        assert {k:v['sha256'] for k, v in candidates.items()} == EXPECTED
        for label, item in candidates.items(): assert sha256_file(Path(item['path'])) == EXPECTED[label]
        paths = sorted((ROOT/'scripts/alpha_holdem').glob('*.py'))
        paths += [ROOT/'scripts/deep_cfr'/f'{n}.py' for n in ['__init__', 'game_state', 'hand_eval']]
        paths += [ROOT/'research/experiment_log.py']
        paths += [p for p in sorted(BASE.iterdir()) if p.suffix in {'.py', '.md'}]
        relatives = [p.relative_to(ROOT).as_posix() for p in paths]
        code = out/'execution_code'
        code.mkdir()
        capture_code_provenance(ROOT, code, relatives)
        copies = []
        for relative in relatives:
            target = code/'source_files'/relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT/relative, target)
            copies.append(dict(original=relative, copy=target.relative_to(ROOT).as_posix(), sha256=sha256_file(target)))
        (code/'copy_manifest.json').write_text(json.dumps(copies, indent=2)+'\n')
        test_command = [sys.executable, '-m', 'unittest', 'discover', '-s', str(BASE), '-p', 'test_metrics.py', '-v']
        with (out/'tests.log').open('x') as handle:
            result = subprocess.run(test_command, cwd=ROOT, stdout=handle, stderr=subprocess.STDOUT)
        report.update(test_command=test_command, test_exit_code=result.returncode)
        if result.returncode: raise RuntimeError('Metric tests failed;preserve attempt')
        import torch
        from alpha_holdem.rules_v6 import ChipState
        from alpha_holdem.policy_contract_v6 import action_table, apply_incr
        from alpha_holdem.execution_v6 import decide, load_policy
        from deep_cfr.hand_eval import card_to_str
        torch.set_num_threads(1)
        torch.set_num_interop_threads(1)
        models = {label:load_policy(item['path'], 'cpu')[0] for label, item in candidates.items()}
        rng, samples, decks, connections = random.Random(20260924), [], set(), []
        def deny(*a, **kw):
            connections.append('connection')
            raise AssertionError('No network in fixed-state diagnostic')
        with patch.object(socket.socket, 'connect', deny), patch.object(socket, 'create_connection', deny), \
             (out/'states.jsonl').open('x') as raw, (out/'trajectories.jsonl').open('x') as trajectories:
            for hand_index in range(512):
                deck = list(range(52))
                rng.shuffle(deck)
                assert tuple(deck) not in decks
                decks.add(tuple(deck))
                state, prefix, actions, count = ChipState.new(deck), '', [], 0
                while not state.terminal:
                    mask, table = action_table(state)
                    state.assert_invariants()
                    # The generated action has no data dependency on any model.
                    behavior = choose(state, rng, hand_index, table)
                    infos = {label:decide(model, state, uniform=.5, device='cpu')[1] for label, model in models.items()}
                    metrics = {label:distribution_metrics(infos['source']['behavior_probs'], info['behavior_probs'], mask.tolist())
                               for label, info in infos.items()}
                    row = dict(state_index=len(samples), hand_index=hand_index, decision_index=count,
                               street=state.street, seat=state.actor, action=prefix,
                               hole_cards=[card_to_str(c) for c in state.holes[state.actor]],
                               board=[card_to_str(c) for c in state.board], behavior_increment=behavior,
                               inference=infos, metrics=metrics)
                    raw.write(json.dumps(row, allow_nan=False)+'\n')
                    samples.append({k:row[k] for k in ['hand_index', 'street', 'seat', 'metrics']})
                    old = state.street
                    state = apply_incr(state, behavior)
                    prefix += behavior
                    if state.street > old and not state.terminal: prefix += '/'
                    actions.append(behavior)
                    count += 1
                    assert count <= 500
                state.assert_invariants()
                trajectories.write(json.dumps(dict(hand_index=hand_index, deck=deck, actions=actions,
                    states=count, folded=state.folded, terminal_board=list(state.board)))+'\n')
                trajectories.flush()
                raw.flush()
                report.update(diagnostic_hands=hand_index+1, diagnostic_states=len(samples))
                if (hand_index+1) % 64 == 0:
                    save()
                    print(json.dumps({k:report[k] for k in ['diagnostic_hands', 'diagnostic_states']}), flush=True)
        assert not connections
        overall = summarize(samples)
        strata = {f'street{street}_seat{seat}':summarize([r for r in samples if r['street'] == street and r['seat'] == seat])
                  for street in range(4) for seat in range(2)}
        delta = overall['hand_weighted']['treatment']['total_variation']-overall['hand_weighted']['weak_control']['total_variation']
        verify(copies)
        verify(live_copies)
        for label, item in candidates.items(): assert sha256_file(Path(item['path'])) == EXPECTED[label]
        report.update(status='PASS', decision='COMMON_STATE_RETENTION_MEASURED', candidate_sha256=EXPECTED,
                      unique_diagnostic_decks=len(decks), model_inference_queries=len(samples)*3,
                      primary_hand_weighted_tv_delta_treatment_minus_control=delta,
                      directional_retention_hypothesis_supported=delta < 0, kl_probability_floor=FLOOR,
                      overall=overall, strata=strata, source_pairs_verified=len(copies), unchanged_live_source_pairs=len(live_copies),
                      network_connections=0, strength_assessed=False, qualification_admitted=False,
                      raw_sha256={p.name:sha256_file(p) for p in [out/'states.jsonl', out/'trajectories.jsonl', out/'tests.log']})
    except BaseException as exc:
        report.update(status='FAILED', error_type=type(exc).__name__, error=str(exc))
        raise
    finally:
        report.update(wall_time_seconds=time.time()-started, finished_at=datetime.now(timezone.utc).isoformat())
        save()
        artifacts = [out/'analysis.json', *[p for p in out.iterdir() if p.suffix in {'.jsonl', '.log'}]]
        artifacts += [p for p in (out/'execution_code').glob('*') if p.is_file()]
        logger('update', *[v for p in artifacts for v in ['--artifact', p]],
               '--metric', f"{args.attempt}_diagnostic_hands={report['diagnostic_hands']}",
               '--metric', f"{args.attempt}_diagnostic_states={report['diagnostic_states']}",
               '--note', f"{args.attempt}ended{report['status']};descriptive common-state mechanism evidence only,no strength gate or checkpoint selection change.")
    logger('finish', '--status', 'COMPLETED', '--summary',
        f"Common-state retention diagnostic measured3frozen policies on512synthetic hands/{len(samples)}states;hand-weighted TV delta{delta:+.6f}.",
        '--conclusion', 'This outcome-blind exogenous-state diagnostic isolates common-input policy drift,not general playing strength or causal multi-seed learning effects.',
        '--decision', report['decision'], '--next-step',
        'Await the unchanged fixed strength comparison and its required independent confirmation;use common-state drift only to interpret learning mechanisms.',
        '--count', 'new_training_hands=0', '--count', 'evaluation_hands=0', '--count', 'slumbot_hands=0')
    print(json.dumps({k:report[k] for k in ['status', 'decision', 'diagnostic_hands', 'diagnostic_states',
          'model_inference_queries', 'primary_hand_weighted_tv_delta_treatment_minus_control', 'source_pairs_verified']}))


if __name__ == '__main__': main()
