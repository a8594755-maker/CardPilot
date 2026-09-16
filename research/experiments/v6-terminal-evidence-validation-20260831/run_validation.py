"""Snapshot, directed tests and512fixed independent-oracle terminal deals."""
import argparse
import ast
from datetime import datetime, timezone
import importlib.util
import json
import os
from pathlib import Path
import random
import shutil
import socket
import subprocess
import sys
import time
from unittest.mock import patch

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[2]
ORACLE = ROOT/'research/experiments/native-rules-contract-repair-20260831'
LIVE = ROOT/'research/experiments/v6-source-kl-retention-pilot-20260831'
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT/'scripts'))
from research.experiment_log import capture_code_provenance, sha256_file


def logger(verb, *args):
    subprocess.run([sys.executable, str(ROOT/'research/experiment_log.py'), verb, BASE.name,
                    *map(str, args)], cwd=ROOT, check=True)


def verify(copies):
    for item in copies:
        if any(sha256_file(ROOT/item[key]) != item['sha256'] for key in ['original', 'copy']):
            raise RuntimeError('Source identity mismatch')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--attempt', required=True)
    args = parser.parse_args()
    if not __import__('re').fullmatch(r'attempt[0-9]{2}', args.attempt):
        raise ValueError('Explicit preserved attempt directory required')
    out = BASE/args.attempt
    out.mkdir(exist_ok=False)
    started = time.time()
    command = f'python research/experiments/{BASE.name}/run_validation.py --attempt {args.attempt}'
    logger('update', '--command', command, '--note', f'{args.attempt}started;fixed512decks/seed20260922,no poker API requests or learned-weight changes.')
    report = dict(status='RUNNING', command=command, pid=os.getpid(), new_training_hands=0,
                  evaluation_hands=0, slumbot_hands=0, oracle_deals=0, accepted_seat_views=0,
                  accepted_expanded_views=0, reward_corruptions_rejected=0)
    def save(): (out/'analysis.json').write_text(json.dumps(report, indent=2)+'\n')
    save()
    try:
        live_copies = json.loads((LIVE/'execution_code/copy_manifest.json').read_text())
        verify(live_copies)
        assert sha256_file(ORACLE/'oracle_validation.py') == '63be73da2ccf015af23af2be3f8f63ec52f5f391d8f1f81a83c1c60df4dfa86e'
        assert sha256_file(BASE/'official_sample_api.txt') == '17ab1f6c1a25db1822cef7f34ed67b6516ac65ea24897adcc92d8f2db8f71505'
        paths = [ROOT/'scripts/alpha_holdem'/f'{n}.py' for n in ['__init__', 'slumbot_terminal_v6',
                 'rules_v6', 'policy_contract_v6', 'play_slumbot', 'slumbot_transport']]
        paths += [ROOT/'scripts/deep_cfr'/f'{n}.py' for n in ['__init__', 'hand_eval', 'game_state']]
        paths += [ROOT/'research/experiment_log.py', ORACLE/'oracle_validation.py']
        paths += sorted((ORACLE/'oracle_vendor/pokerkit').glob('*.py'))
        paths += [p for p in sorted(BASE.iterdir()) if p.suffix in {'.py', '.md', '.txt'}]
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
        env = os.environ.copy()
        env.update(OMP_NUM_THREADS='1', OPENBLAS_NUM_THREADS='1', MKL_NUM_THREADS='1')
        test_cmd = [sys.executable, '-m', 'unittest', 'discover', '-s', str(BASE), '-p', 'test_terminal.py', '-v']
        report['test_command'] = test_cmd
        with (out/'directed_tests.log').open('x') as handle:
            test = subprocess.run(test_cmd, cwd=ROOT, env=env, stdout=handle, stderr=subprocess.STDOUT)
        report['test_exit_code'] = test.returncode
        save()
        if test.returncode: raise RuntimeError('Directed terminal tests failed; preserve attempt')
        import torch
        torch.set_num_threads(1)
        torch.set_num_interop_threads(1)
        spec = importlib.util.spec_from_file_location('pinned_terminal_oracle', ORACLE/'oracle_validation.py')
        oracle = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(oracle)
        fixture_spec = importlib.util.spec_from_file_location('terminal_fixtures', BASE/'test_terminal.py')
        fixtures = importlib.util.module_from_spec(fixture_spec)
        fixture_spec.loader.exec_module(fixtures)
        from alpha_holdem.slumbot_terminal_v6 import validate_terminal
        source_ast = ast.parse((BASE/'official_sample_api.txt').read_text())
        node = next(n for n in source_ast.body if isinstance(n, ast.FunctionDef) and n.name == 'ParseAction')
        # Only this inspected pure parser is executed, never the example's HTTP,
        # login, strategy or main functions. Also restrict its call expressions.
        assert all(isinstance(n.func, ast.Name) and n.func.id in {'len', 'range', 'int'}
                   for n in ast.walk(node) if isinstance(n, ast.Call))
        namespace = dict(NUM_STREETS=4, SMALL_BLIND=50, BIG_BLIND=100, STACK_SIZE=20000)
        exec(compile(ast.Module(body=[node], type_ignores=[]), 'official_ParseAction_only', 'exec'), namespace)
        official_parse = namespace['ParseAction']
        rng, seen_decks = random.Random(20260922), set()
        denied = []
        def deny(*a, **kw):
            denied.append('connection')
            raise AssertionError('Network forbidden during validation')
        with patch.object(socket.socket, 'connect', deny), patch.object(socket, 'create_connection', deny), \
             (out/'oracle_hands.jsonl').open('x') as raw, (out/'terminal_views.jsonl').open('x') as views:
            for hand_index in range(512):
                deck = list(range(52))
                rng.shuffle(deck)
                assert tuple(deck) not in seen_decks
                seen_decks.add(tuple(deck))
                row = oracle.run_trajectory(deck, rng, hand_index)
                raw.write(json.dumps(row)+'\n')
                raw.flush()
                report['oracle_deals'] += 1
                for seat in [0, 1]:
                    response, previous, incr = fixtures.fixture(row['actions'], seat, deck=deck)
                    result = validate_terminal(response, previous=previous, increment=incr)
                    assert result['payoffs_chips'] == row['payoffs_chips']
                    parsed = official_parse(response['action'])
                    assert isinstance(parsed, dict) and 'error' not in parsed and parsed['pos'] == -1
                    report['accepted_seat_views'] += 1
                    view = dict(hand_index=hand_index, seat=seat, response=response, previous=previous,
                                increment=incr, result=result, corruptions_rejected=[])
                    if row['folded'] < 0:
                        # Slash count in the canonical prefix identifies the street
                        # where the all-in closed; ordinary river showdown adds none.
                        suffix = '/'*(3-response['action'].count('/'))
                        if suffix:
                            expanded = {**response, 'action':response['action']+suffix}
                            assert validate_terminal(expanded, previous=previous, increment=incr) == result
                            parsed = official_parse(expanded['action'])
                            assert isinstance(parsed, dict) and 'error' not in parsed and parsed['pos'] == -1
                            view['expanded_action'] = expanded['action']
                            report['accepted_expanded_views'] += 1
                    for delta in [-1, 1]:
                        try: validate_terminal({**response, 'winnings':response['winnings']+delta})
                        except ValueError:
                            view['corruptions_rejected'].append(delta)
                            report['reward_corruptions_rejected'] += 1
                        else: raise AssertionError('Corrupted payoff accepted')
                    views.write(json.dumps(view)+'\n')
                    views.flush()
                if (hand_index+1) % 64 == 0:
                    save()
                    print(json.dumps({k:report[k] for k in ['oracle_deals', 'accepted_seat_views', 'reward_corruptions_rejected']}), flush=True)
        assert not denied
        verify(copies)
        verify(live_copies)
        report.update(status='PASS', decision='STANDALONE_TERMINAL_VALIDATOR_VALIDATED',
                      unique_oracle_decks=len(seen_decks), source_pairs_verified=len(copies),
                      unchanged_live_source_pairs=len(live_copies), network_connections=0,
                      integrated_client=False, external_qualification_admitted=False,
                      raw_sha256={p.name:sha256_file(p) for p in [out/'oracle_hands.jsonl', out/'terminal_views.jsonl', out/'directed_tests.log']})
    except BaseException as exc:
        report.update(status='FAILED', error_type=type(exc).__name__, error=str(exc))
        raise
    finally:
        report.update(wall_time_seconds=time.time()-started, finished_at=datetime.now(timezone.utc).isoformat())
        save()
        artifacts = [out/'analysis.json', *[p for p in out.iterdir() if p.suffix in {'.jsonl', '.log'}]]
        artifacts += [p for p in (out/'execution_code').glob('*') if p.is_file()]
        logger('update', *[v for p in artifacts for v in ['--artifact', p]],
               '--metric', f"{args.attempt}_oracle_deals={report['oracle_deals']}",
               '--note', f"{args.attempt}ended{report['status']};preserve all evidence. Terminal module is not client integration,session evidence validation or strength evidence.")
    logger('finish', '--status', 'COMPLETED', '--summary',
           'Standalone terminal evidence validation passed directed tests and512fixed independent-oracle deals;0learned or external hands.',
           '--conclusion', 'Exact terminal checks are validated offline; journaling,token-chain,session independence and live-client integration remain required.',
           '--decision', report['decision'], '--next-step',
           'Integrate this validator with a separately registered durable-journal client and validate complete offline multi-session evidence before any live qualification.',
           '--count', 'new_training_hands=0', '--count', 'evaluation_hands=0', '--count', 'slumbot_hands=0')
    print(json.dumps(report))


if __name__ == '__main__': main()
