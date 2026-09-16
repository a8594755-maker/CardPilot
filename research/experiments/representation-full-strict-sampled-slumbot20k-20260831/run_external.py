# Conditional draft: no tests or real hands until the confirmation passes and this record is registered.
"""Immutable fixed20k strict sampled pilot. Persistent transport; no automatic recovery."""
import json
import math
from pathlib import Path
import shutil
import statistics
import subprocess
import sys
import time

import psutil

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[2]
sys.path.insert(0, str(ROOT))
from research.experiment_log import capture_code_provenance, atomic_json
from scripts.alpha_holdem.audit_slumbot_hand_evidence import sha

CONFIRMATION = ROOT/'research/experiments/representation-scope-independent-confirmation-20260831'
SOURCE = ROOT/'research/experiments/matched-weak-kl-representation-curve-20260830/frozen/full.pt'
DIGEST = 'ff2b9e6fe188ac89aa3ff4b632b70a195a46e8e6a73f1b94a75fcfbbf543c17e'
TARGET, SESSIONS = 2500, 8


def log(*args):
    subprocess.run([sys.executable, 'research/experiment_log.py', 'update', BASE.name, *map(str, args)], cwd=ROOT, check=True)


def record_command(args):
    log('--command', subprocess.list2cmdline(['python', *map(str, args)]))


def client_args(script, checkpoint, spec, hands=None, result=None):
    return [str(script), '--model', str(checkpoint), '--strategy', 'model', '--device', 'cpu',
        '--hands', str(spec['requested_hands'] if hands is None else hands),
        '--strict-policy-execution', '--policy-mode', 'sample', '--temperature', '1', '--policy-seed', str(spec['policy_seed']),
        '--torch-threads', '1', '--torch-interop-threads', '1',
        '--result-json', str(spec['result'] if result is None else result),
        *(['--hand-results-jsonl', str(spec['raw_hands']), '--dump-slumbot', str(spec['dump'])] if hands != 0 else [])]


class RawCounter:
    """Count only complete new JSONL rows; preserve an incomplete live tail."""
    def __init__(self, path):
        self.path, self.offset, self.tail, self.count = Path(path), 0, b'', 0

    def scan(self):
        if not self.path.exists():
            return self.count
        if self.path.stat().st_size < self.offset:
            raise ValueError('A raw evidence file was truncated')
        with self.path.open('rb') as stream:
            stream.seek(self.offset)
            data = self.tail+stream.read()
            self.offset = stream.tell()
        complete = data.split(b'\n')
        self.tail = complete.pop()
        for line in complete:
            if line.strip():
                row = json.loads(line)
                if not isinstance(row, dict) or 'winnings_chips' not in row:
                    raise ValueError('Malformed complete raw row')
                self.count += 1
        return self.count


def verified_sources(copies, checkpoint):
    if sha(SOURCE) != DIGEST or sha(checkpoint) != DIGEST:
        raise ValueError('Frozen source/model changed')
    for item in copies:
        if sha(ROOT/item['original']) != item['sha256'] or sha(ROOT/item['copy']) != item['sha256']:
            raise ValueError('Execution code changed')


def summarize_audit(audit):
    if audit['status'] != 'PASS' or audit['summary']['hands'] != TARGET*SESSIONS or len(audit['sessions']) != SESSIONS:
        raise ValueError('Incomplete fixed20k strict evidence audit')
    means = [row['total_chips']/row['hands'] for row in audit['sessions']]
    if any(row['hands'] != TARGET for row in audit['sessions']):
        raise ValueError('Session size differs from fixed plan')
    # Fixed two-sided95% Student-t quantile,df7. Sensitivity only,not selected CI.
    point = statistics.mean(means)
    if not math.isclose(point, audit['summary']['bb_per_100'], rel_tol=0, abs_tol=1e-8):
        raise ValueError('Equal-size session means disagree with raw pooled mean')
    width = 2.3646242510102993*statistics.stdev(means)/(SESSIONS**.5)
    return dict(status='PASS', evaluation_hands=20000, slumbot_hands=20000, new_training_hands=0,
        raw=audit['summary'], per_session_bb100=means,
        session_mean_t95=dict(df=7, point=point, lower=point-width, upper=point+width),
        admits_separate_fresh100k=audit['summary']['bb_per_100'] > 0,
        goal_achieved=False, claim_scope='fixed_sampled_external_pilot_not_formal100k')


def validate_confirmation(record, review, readiness):
    if (record['status'] != 'COMPLETED' or record['metrics'].get('post_exit_review_pass') != 1
            or record['accounting']['evaluation_hands'] != 196608
            or review['status'] != 'PASS' or review['replication_passed'] is not True
            or review['decision'] != 'REPRESENTATION_SCOPE_REPLICATION_PASSED'
            or review['seed'] != 20260913 or review['evaluation_hands'] != 196608
            or review['new_training_hands'] != 0 or review['slumbot_hands'] != 0
            or review['candidate_hashes']['full'] != DIGEST
            or readiness['status'] != 'PASS' or readiness['checkpoint_sha256'] != DIGEST
            or readiness['actual_slumbot_hands'] != 0 or readiness['network_calls_attempted'] != 0):
        raise ValueError('Completed independent confirmation and exact-checkpoint readiness are required')


def verify_confirmation_gate():
    record = json.loads((CONFIRMATION/'experiment.json').read_text())
    review = json.loads((CONFIRMATION/'reviewed_analysis.json').read_text())
    readiness = json.loads((CONFIRMATION/'deployment_readiness/readiness_analysis.json').read_text())
    validate_confirmation(record, review, readiness)
    if (sha(CONFIRMATION/'finish_confirmation.py') != review['review_script_sha256']
            or sha(CONFIRMATION/'replication_analysis.json') != review['original_analysis_sha256']):
        raise ValueError('Reviewed confirmation provenance changed')
    for label, digest in review['cell_hashes'].items():
        if sha(CONFIRMATION/'matrix'/f'{label}.json') != digest:
            raise ValueError('Confirmation raw evidence changed')


def main():
    if sys.argv[1:]:
        raise ValueError('No automatic resume or alternate configuration')
    for process in psutil.process_iter(['pid', 'name', 'cmdline']):
        if (process.info['name'] or '').lower().startswith('python') and any(
                Path(arg).name in ['play_slumbot.py', 'train_v5.py', 'v5_mirror_eval.py']
                for arg in process.info['cmdline'] or []):
            raise RuntimeError('Other poker work is live')
    if any((BASE/name).exists() for name in ['frozen', 'execution_code', 'sessions', 'run_manifest.json']):
        raise RuntimeError('Refusing existing production/evidence paths; inspect rather than restart')
    if json.loads((BASE/'experiment.json').read_text())['status'] != 'RUNNING':
        raise ValueError('A preregistered RUNNING experiment is required')
    verify_confirmation_gate()
    readiness = json.loads((ROOT/'research/experiments/slumbot-persistent-transport-repair-20260830/transport_analysis.json').read_text())
    if readiness['status'] != 'PASS' or readiness['actual_slumbot_hands'] != 0 or readiness['tests_passed'] != 83 or readiness['strict_zero_hand_loader_pass'] is not True or sha(SOURCE) != DIGEST:
        raise ValueError('Readiness/source gate failed')
    validated_manifest = ROOT/'research/experiments/slumbot-persistent-transport-repair-20260830/final_code/copy_manifest.json'
    for item in json.loads(validated_manifest.read_text()):
        if sha(ROOT/item['original']) != item['sha256'] or sha(ROOT/item['copy']) != item['sha256']:
            raise ValueError('Readiness-tested source changed before launch')
    if shutil.disk_usage(BASE).free < 2*1024**3:
        raise RuntimeError('Insufficient disk space for immutable evidence')
    snapshot = BASE/'execution_code'
    snapshot.mkdir()
    paths = [p.relative_to(ROOT).as_posix() for p in sorted((ROOT/'scripts/alpha_holdem').glob('*.py'))]
    paths += [f'scripts/deep_cfr/{name}.py' for name in ['__init__', 'game_state', 'hand_eval']]
    paths += ['research/experiment_log.py', Path(__file__).relative_to(ROOT).as_posix(),
              (BASE/'test_external_runner.py').relative_to(ROOT).as_posix(),
              (BASE/'review_completed_pilot.py').relative_to(ROOT).as_posix(),
              (BASE/'finish_completed_run.py').relative_to(ROOT).as_posix(),
              (BASE/'test_completed_review.py').relative_to(ROOT).as_posix()]
    paths.append((BASE/'preregistration.md').relative_to(ROOT).as_posix())
    _, artifacts = capture_code_provenance(ROOT, snapshot, paths)
    copies = []
    for relative in paths:
        target = snapshot/'source_files'/relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT/relative, target)
        copies.append(dict(original=relative, copy=target.relative_to(ROOT).as_posix(), sha256=sha(target)))
    (snapshot/'copy_manifest.json').write_text(json.dumps(copies, indent=2)+'\n')
    (BASE/'frozen').mkdir()
    checkpoint = BASE/'frozen/full.pt'
    shutil.copy2(SOURCE, checkpoint)
    verified_sources(copies, checkpoint)
    session_dir = BASE/'sessions'
    session_dir.mkdir()
    specs = [dict(id=f'part{i:02d}', policy_seed=2026091400+i, requested_hands=TARGET,
        raw_hands=str(session_dir/f'part{i:02d}_hands.jsonl'), dump=str(session_dir/f'part{i:02d}_dump.jsonl'),
        result=str(session_dir/f'part{i:02d}_result.json')) for i in range(1, SESSIONS+1)]
    manifest = dict(schema='cardpilot.slumbot_frozen_evidence_manifest.v1',
        policy=dict(checkpoint=str(checkpoint), sha256=DIGEST, strategy='model', policy_mode='sample',
                    temperature=1., obs_version='v4', starting_stack_bb=200), sessions=specs,
        execution=dict(strict_policy_execution=True, http_transport='persistent_session_no_retries_v1'))
    manifest_path = BASE/'evidence_manifest.json'
    manifest_path.write_text(json.dumps(manifest, indent=2)+'\n')
    record_command([Path(__file__).relative_to(ROOT)])
    log(*[item for path in [*artifacts, snapshot/'copy_manifest.json', checkpoint, manifest_path] for item in ['--artifact', str(path)]],
        '--note', 'Complete execution source and policy frozen. Exactly8x2500 planned; no automatic restart,supplement,reseed or score-based stop. All client/audit commands use this snapshot.')
    script = snapshot/'source_files/scripts/alpha_holdem/play_slumbot.py'
    dry_path = BASE/'snapshot_loader_dry_run.json'
    dry_args = client_args(script, checkpoint, specs[0], hands=0, result=dry_path)
    record_command(dry_args)
    subprocess.run([sys.executable, *dry_args], cwd=ROOT, check=True)
    dry = json.loads(dry_path.read_text())
    if dry['successful_hands'] != 0 or dry['model_sha256'] != DIGEST or dry['policy_seed'] != specs[0]['policy_seed'] or dry['strict_policy_execution'] is not True or dry['http_transport'] != 'persistent_session_no_retries_v1':
        raise ValueError('Snapshot zero-game loader failed')
    log('--artifact', dry_path, '--metric', 'snapshot_loader_pass=1')
    jobs, started, last_log, last_count = [], time.monotonic(), 0., -1
    ledger = dict(status='RUNNING', planned_hands=20000, sessions=[], completed_raw_hands=0)
    ledger_path = BASE/'run_manifest.json'

    def progress(force=False):
        nonlocal last_log, last_count
        count = sum(job['counter'].scan() for job in jobs)
        ledger['completed_raw_hands'] = count
        ledger['elapsed_seconds'] = time.monotonic()-started
        ledger['sessions'] = [dict(id=job['spec']['id'], pid=job['process'].pid,
            started_at_unix=job['started_at'], raw_hands=job['counter'].count,
            exit_code=job['process'].poll(), policy_seed=job['spec']['policy_seed']) for job in jobs]
        atomic_json(ledger_path, ledger)
        if force or (count != last_count and time.monotonic()-last_log >= 15):
            log('--count', f'evaluation_hands={count}', '--count', f'slumbot_hands={count}', '--artifact', ledger_path,
                '--metric', f'active_sessions={sum(job["process"].poll() is None for job in jobs)}')
            last_log, last_count = time.monotonic(), count
        return count

    try:
        for spec in specs:
            verified_sources(copies, checkpoint)
            args = ['-u', *client_args(script, checkpoint, spec)]
            record_command(args)
            stdout = session_dir/f'{spec["id"]}_stdout.log'
            handle = stdout.open('x', encoding='utf-8')
            flags = (subprocess.CREATE_NO_WINDOW | subprocess.BELOW_NORMAL_PRIORITY_CLASS) if sys.platform == 'win32' else 0
            process = subprocess.Popen([sys.executable, *args], cwd=ROOT,
                                       stdout=handle, stderr=subprocess.STDOUT, creationflags=flags)
            job = dict(spec=spec, process=process, output=handle, counter=RawCounter(spec['raw_hands']),
                       started_at=time.time())
            jobs.append(job)
            log('--metric', f'{spec["id"]}_pid={process.pid}')
            ready_started = time.monotonic()
            while job['counter'].scan() < 1 or not Path(spec['dump']).exists() or Path(spec['dump']).stat().st_size == 0:
                progress()
                if process.poll() is not None or any(j['process'].poll() not in (None, 0) for j in jobs):
                    raise RuntimeError('Client exited/failed during first-hand readiness')
                if time.monotonic()-ready_started > 180:
                    raise RuntimeError('First-hand readiness guard reached')
                time.sleep(1)
            log('--metric', f'{spec["id"]}_first_hand_ready=1')
            progress(force=True)
            if spec is not specs[-1]:
                time.sleep(1)
        while any(job['process'].poll() is None for job in jobs):
            progress()
            if any(job['process'].poll() not in (None, 0) for job in jobs):
                raise RuntimeError('Client failed; preserve all evidence without automatic recovery')
            if time.monotonic()-started > 10800:
                raise RuntimeError('Fixed operational time guard reached')
            time.sleep(5)
        for job in jobs:
            job['output'].close()
        count = progress(force=True)
        if any(job['process'].returncode != 0 or job['counter'].tail or job['counter'].count != TARGET for job in jobs):
            raise ValueError('Incomplete client,tail,or exact session count')
        if count != 20000:
            raise ValueError('Fixed20k total not reached exactly')
        verified_sources(copies, checkpoint)
        audit_path = BASE/'strict_hand_evidence_audit.json'
        args = [str(snapshot/'source_files/scripts/alpha_holdem/audit_slumbot_hand_evidence.py'),
                '--manifest', str(manifest_path), '--out-json', str(audit_path)]
        record_command(args)
        subprocess.run([sys.executable, *args], cwd=ROOT, check=True)
        result = summarize_audit(json.loads(audit_path.read_text()))
        result['policy_sha256'] = DIGEST
        (BASE/'pilot_analysis.json').write_text(json.dumps(result, indent=2)+'\n')
        ledger['status'] = 'COMPLETED_PENDING_REVIEW'
        progress(force=True)
        verified_sources(copies, checkpoint)
        log('--metric', 'pilot_complete=1', '--metric', f'admits_separate_fresh100k={int(result["admits_separate_fresh100k"])}',
            '--artifact', audit_path, '--artifact', BASE/'pilot_analysis.json',
            *[item for path in session_dir.iterdir() for item in ['--artifact', str(path)]],
            '--note', 'All8 fixed sessions finished and strict raw/model/mode/seed/dump/CI/replay audits passed. Pilot remains RUNNING for independent review/finish. No goal-completion or100k claim.')
        print(json.dumps({'pilot_complete': True, 'raw_bb100': result['raw']['bb_per_100'],
                          'admits_separate_fresh100k': result['admits_separate_fresh100k']}))
    except BaseException as error:
        # Stop only children owned by this wrapper; do not touch unrelated tasks.
        for job in jobs:
            if job['process'].poll() is None:
                job['process'].terminate()
        for job in jobs:
            try:
                job['process'].wait(timeout=10)
            except subprocess.TimeoutExpired:
                job['process'].kill()
                job['process'].wait(timeout=10)
            finally:
                job['output'].close()
        ledger['status'] = 'STOPPED_INCOMPLETE_OR_INVALID'
        ledger['error_type'] = type(error).__name__
        try:
            progress(force=True)
        except (ValueError, OSError):
            # A malformed final row must not prevent retaining the terminal
            # ledger. Its last known count is a lower bound, not a valid gate.
            ledger['raw_count_complete'] = False
            atomic_json(ledger_path, ledger)
            log('--artifact', ledger_path,
                '--note', 'Terminal raw-row parsing failed. Last logged count is not a completeness claim; preserve files for independent reconciliation.')
        log('--metric', 'terminal_problem=1',
            *[item for path in session_dir.iterdir() for item in ['--artifact', str(path)]],
            '--note', 'Operational/terminal/evidence failure. Only owned live clients were stopped; all files retained. No automatic retry,supplement,reseed,or overwrite. Inspect preserved evidence and diagnose before any recovery.')
        raise


if __name__ == '__main__':
    main()
