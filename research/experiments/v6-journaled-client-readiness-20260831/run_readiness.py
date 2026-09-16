"""Preserved attempts for integrated offline evidence readiness, no poker API."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[2]
LIVE = ROOT/'research/experiments/v6-source-kl-retention-pilot-20260831'
sys.path.insert(0, str(ROOT))
from research.experiment_log import capture_code_provenance, sha256_file


def logger(verb, *args):
    subprocess.run([sys.executable, str(ROOT/'research/experiment_log.py'), verb, BASE.name,
                    *map(str, args)], cwd=ROOT, check=True)


def verify(copies):
    for item in copies:
        if any(sha256_file(ROOT/item[k]) != item['sha256'] for k in ['original', 'copy']):
            raise RuntimeError('Source identity mismatch')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--attempt', required=True)
    args = parser.parse_args()
    if not re.fullmatch(r'attempt[0-9]{2}', args.attempt): raise ValueError('Explicit new attempt directory required')
    out = BASE/args.attempt
    out.mkdir(exist_ok=False)
    started = time.time()
    command = f'python research/experiments/{BASE.name}/run_readiness.py --attempt {args.attempt}'
    logger('update', '--command', command, '--note', f'{args.attempt}started;offline only,preserve all failures and all live pilot source files.')
    report = dict(status='RUNNING', command=command, pid=os.getpid(), new_training_hands=0, evaluation_hands=0, slumbot_hands=0)
    def save(): (out/'analysis.json').write_text(json.dumps(report, indent=2)+'\n')
    save()
    try:
        live_copies = json.loads((LIVE/'execution_code/copy_manifest.json').read_text())
        verify(live_copies)
        terminal_copies = json.loads((ROOT/'research/experiments/v6-terminal-evidence-validation-20260831/attempt01/execution_code/copy_manifest.json').read_text())
        terminal_entry = next(r for r in terminal_copies if r['original'] == 'scripts/alpha_holdem/slumbot_terminal_v6.py')
        verify([terminal_entry])
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
        env = os.environ.copy()
        env.update(JOURNAL_TEST_OUTPUT=str(out/'cases'), OMP_NUM_THREADS='1', OPENBLAS_NUM_THREADS='1', MKL_NUM_THREADS='1')
        test_command = [sys.executable, '-m', 'unittest', 'discover', '-s', str(BASE), '-p', 'test_client.py', '-v']
        report.update(test_command=test_command, test_environment={'JOURNAL_TEST_OUTPUT':str(out/'cases'), 'OMP_NUM_THREADS':'1', 'OPENBLAS_NUM_THREADS':'1', 'MKL_NUM_THREADS':'1'})
        with (out/'tests.log').open('x') as handle:
            proc = subprocess.Popen(test_command, cwd=ROOT, env=env, stdout=handle, stderr=subprocess.STDOUT)
            report['test_pid'] = proc.pid
            save()
            # Only this owned offline test process is waited on; no live poker
            # process is interrupted, restarted or inherited by the fixtures.
            code_value = proc.wait()
        report['test_exit_code'] = code_value
        if code_value: raise RuntimeError('Offline readiness tests failed; preserve attempt')
        output = (out/'tests.log').read_text()
        report['directed_tests_passed'] = int(re.search(r'Ran (\d+) tests', output).group(1))
        fixtures = [json.loads(p.read_text()) for p in (out/'cases').rglob('fixture.json')]
        guard = json.loads((out/'cases/network_guard.json').read_text())
        assert guard['connections'] == []
        child = json.loads((out/'cases/test_abrupt_exit_after_fsynced_intent/process.json').read_text())
        assert child['exit_code'] == 17
        multi = json.loads((out/'cases/test_multiple_independent_streams_and_collisions/multi_session_audit.json').read_text())
        assert multi['status'] == 'PASS' and multi['successful_hands'] == 4 and multi['server_rng_independence_proven'] is False
        verify(copies)
        verify(live_copies)
        raw_paths = sorted(p for p in (out/'cases').rglob('*') if p.is_file())
        raw_manifest = [{'path':p.relative_to(ROOT).as_posix(), 'sha256':sha256_file(p), 'bytes':p.stat().st_size} for p in raw_paths]
        (out/'evidence_manifest.json').write_text(json.dumps(raw_manifest, indent=2)+'\n')
        report.update(status='PASS', decision='OFFLINE_CLIENT_EVIDENCE_READINESS', network_connections=0,
                      source_pairs_verified=len(copies), unchanged_live_source_pairs=len(live_copies),
                      preserved_fixture_cases=len(fixtures), preserved_evidence_files=len(raw_manifest),
                      synthetic_terminal_trajectories=sum(f['completed_fixture_trajectories'] for f in fixtures),
                      fixture_requests=sum(len(f['calls']) for f in fixtures), controlled_crash_exit=17,
                      external_qualification_admitted=False, live_compatibility_proven=False,
                      evidence_manifest_sha256=sha256_file(out/'evidence_manifest.json'))
    except BaseException as exc:
        report.update(status='FAILED', error_type=type(exc).__name__, error=str(exc))
        raise
    finally:
        report.update(wall_time_seconds=time.time()-started, finished_at=datetime.now(timezone.utc).isoformat())
        save()
        artifacts = [out/'analysis.json', out/'tests.log']
        artifacts += [p for p in (out/'execution_code').glob('*') if p.is_file()]
        if (out/'evidence_manifest.json').exists(): artifacts.append(out/'evidence_manifest.json')
        logger('update', *[v for p in artifacts if p.exists() for v in ['--artifact', p]],
               '--note', f"{args.attempt}ended{report['status']};all fixture evidence retained. No poker API or GPU use; no live qualification admission.")
    logger('finish', '--status', 'COMPLETED', '--summary',
           f"Journaled client passed{report['directed_tests_passed']}offline tests with durable failure and session evidence;0training/evaluation/Slumbot hands.",
           '--conclusion', 'Offline protocol and shared-inference checks passed; only a separately registered frozen live run can establish current API compatibility and strength.',
           '--decision', report['decision'], '--next-step',
           'Finish the ongoing learned-policy evaluation and require independent confirmation before preregistering any live frozen-policy test using the audited journaled client.',
           '--count', 'new_training_hands=0', '--count', 'evaluation_hands=0', '--count', 'slumbot_hands=0')
    print(json.dumps(report))


if __name__ == '__main__': main()
