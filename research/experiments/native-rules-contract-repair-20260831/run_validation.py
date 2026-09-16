"""Retained, fixed-budget differential-validation attempt; no policy training."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import random
import shutil
import subprocess
import sys
import time
import traceback
from unittest.mock import patch

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[2]
sys.path.insert(0, str(ROOT))
from research.experiment_log import capture_code_provenance, sha256_file


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--attempt', required=True)
    args = parser.parse_args()
    if not args.attempt.isalnum():
        raise ValueError('Attempt must be a simple alphanumeric label')
    directory = BASE/args.attempt
    directory.mkdir(exist_ok=False)
    started = time.time()
    paths = [p.relative_to(ROOT).as_posix() for p in sorted((ROOT/'scripts/alpha_holdem').glob('*.py'))]
    paths += ['scripts/deep_cfr/hand_eval.py', 'scripts/deep_cfr/game_state.py',
              'research/experiment_log.py']
    paths += [(BASE/name).relative_to(ROOT).as_posix() for name in
              ['preregistration.md', 'oracle_validation.py', 'test_contract.py', 'test_integration.py', 'run_validation.py']]
    source = directory/'execution_code'
    source.mkdir()
    capture_code_provenance(ROOT, source, paths)
    copies = []
    for relative in paths:
        target = source/'source_files'/relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT/relative, target)
        copies.append(dict(original=relative, copy=target.relative_to(ROOT).as_posix(), sha256=sha256_file(target)))
    (source/'copy_manifest.json').write_text(json.dumps(copies, indent=2)+'\n')
    wheel = BASE/'oracle_wheels/pokerkit-0.7.5-py3-none-any.whl'
    assert sha256_file(wheel) == '3e1a0b2a8a9785369c86e2c1392dd2204ee536fbcbe77a779c875bd545eb63e8'
    vendors = {p.relative_to(BASE).as_posix(): sha256_file(p) for p in sorted((BASE/'oracle_vendor/pokerkit').glob('*.py'))}
    (directory/'oracle_source_hashes.json').write_text(json.dumps(vendors, indent=2)+'\n')
    # Execute original paths with byte-identical pre/post source snapshots.
    # Record actual imports; do not claim an isolated-copy execution.
    sys.path.insert(0, str(ROOT/'scripts'))
    sys.path.insert(0, str(BASE))
    from oracle_validation import run_trajectory
    from alpha_holdem import rules_v6, policy_contract_v6, environment_v6
    import pokerkit
    imported = {m.__name__: str(Path(m.__file__).resolve()) for m in
                [rules_v6, policy_contract_v6, environment_v6, pokerkit]}
    (directory/'imports.json').write_text(json.dumps(imported, indent=2)+'\n')
    completed = 0
    checked_decisions = 0
    error = None
    network_attempts = []
    def deny_network(*a, **kw):
        network_attempts.append(True)
        raise AssertionError('No network in differential validation')
    rng = random.Random(20260915)
    try:
        tests = ['test_contract.py', 'test_integration.py']
        test_paths = [str(BASE/name) for name in tests]
        test_paths += [str(ROOT/'scripts/alpha_holdem'/name) for name in [
            'test_environment_hand_accounting.py', 'test_train_v5_mirror_deals.py',
            'test_train_v5_replay.py', 'test_slumbot_transport.py', 'test_slumbot_ci_from_hands.py']]
        test_cmd = [sys.executable, '-m', 'pytest', *test_paths, '-q', f'--junitxml={directory/"tests.xml"}']
        (directory/'test_command.json').write_text(json.dumps(test_cmd, indent=2)+'\n')
        with (directory/'tests_stdout.log').open('x') as test_log:
            subprocess.run(test_cmd, cwd=ROOT, stdout=test_log, stderr=subprocess.STDOUT, check=True)
        with patch('socket.socket.connect', deny_network), patch('socket.create_connection', deny_network), \
                (directory/'hands.jsonl').open('x') as hands, (directory/'events.jsonl').open('x') as events:
            for index in range(4096):
                deck = list(range(52))
                rng.shuffle(deck)
                events.write(json.dumps(dict(hand_index=index, deck=deck))+'\n')
                def on_action(incr):
                    events.write(json.dumps(dict(hand_index=index, action=incr))+'\n')
                result = run_trajectory(deck, rng, index, on_action)
                hands.write(json.dumps(result)+'\n')
                completed += 1
                checked_decisions += result['checked_decisions']
                if completed%256 == 0:
                    hands.flush()
                    events.flush()
                    print(json.dumps(dict(completed=completed, target=4096, seconds=round(time.time()-started, 3))), flush=True)
            for item in copies:
                assert all(sha256_file(ROOT/item[key]) == item['sha256'] for key in ['original', 'copy'])
            for relative, digest in vendors.items():
                assert sha256_file(BASE/relative) == digest
    except BaseException:
        error = traceback.format_exc()
        print(error, file=sys.stderr)
    analysis = dict(status='PASS' if error is None and completed == 4096 else 'FAILED',
        completed_validation_hands=completed, target=4096, seed=20260915,
        new_training_hands=0, evaluation_hands=0, slumbot_hands=0,
        network_attempts=len(network_attempts), wall_time_seconds=time.time()-started,
        checked_decisions=checked_decisions,
        started_at=datetime.fromtimestamp(started, timezone.utc).isoformat(),
        finished_at=datetime.now(timezone.utc).isoformat(), error=error,
        command=[sys.executable, *sys.argv], source_pairs=len(copies),
        oracle_wheel_sha256=sha256_file(wheel),
        hands_sha256=sha256_file(directory/'hands.jsonl') if (directory/'hands.jsonl').exists() else None,
        scope='Rules oracle, per-decision external reconstruction/encoding, and production entry-point wiring; no optimizer update or live Slumbot')
    (directory/'analysis.json').write_text(json.dumps(analysis, indent=2)+'\n')
    subprocess.run([sys.executable, str(ROOT/'research/experiment_log.py'), 'update', BASE.name,
        '--command', subprocess.list2cmdline(['python', str(Path(__file__).relative_to(ROOT)), *sys.argv[1:]]),
        '--artifact', str(directory/'analysis.json'), '--artifact', str(directory/'hands.jsonl'),
        '--artifact', str(directory/'events.jsonl'), '--artifact', str(source/'source_manifest.json'),
        '--artifact', str(source/'code.patch'), '--artifact', str(source/'copy_manifest.json'),
        '--artifact', str(directory/'imports.json'), '--artifact', str(directory/'oracle_source_hashes.json'),
        '--artifact', str(directory/'tests.xml'), '--artifact', str(directory/'tests_stdout.log'),
        '--artifact', str(directory/'test_command.json'),
        '--metric', f'{args.attempt}_validation_hands={completed}', '--note',
        f'{args.attempt}: {analysis["status"]}; {completed}/4096 seeded oracle validation hands and{checked_decisions}decision checks, zero policy evaluation or training. This repeats the same fixed seed as core01, not independent strength evidence.'], check=True)
    print(json.dumps(analysis), flush=True)
    return int(error is not None)


if __name__ == '__main__':
    raise SystemExit(main())
