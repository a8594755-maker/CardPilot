"""Preserve and close an outcome-blind infrastructure abort, never a completed pilot."""
import json
from pathlib import Path
import subprocess
import sys

import psutil

from run_external import BASE, ROOT, verified_sources
from review_completed_baseline import chip_statistics
from scripts.alpha_holdem.audit_slumbot_hand_evidence import sha


def log(*args):
    subprocess.run([sys.executable, 'research/experiment_log.py', 'update', BASE.name, *map(str, args)], cwd=ROOT, check=True)


def main():
    for process in psutil.process_iter(['name', 'cmdline']):
        if (process.info['name'] or '').lower().startswith('python') and any(
            Path(arg).name in ['play_slumbot.py', 'run_external.py'] for arg in process.info['cmdline'] or []):
            raise RuntimeError('Original writer is not fully stopped')
    out = BASE/'integrity_abort_analysis.json'
    if out.exists() or (BASE/'result_summary.md').exists():
        raise ValueError('Refusing to overwrite terminal analysis')
    record = json.loads((BASE/'experiment.json').read_text())
    ledger = json.loads((BASE/'run_manifest.json').read_text())
    manifest = json.loads((BASE/'evidence_manifest.json').read_text())
    stop = json.loads((BASE/'integrity_stop_reason.json').read_text())
    if ledger['status'] != 'STOPPED_INCOMPLETE_OR_INVALID' or stop['interim_pilot_winrate_or_ci_examined']:
        raise ValueError('Unexpected stop basis')
    verified_sources(json.loads((BASE/'execution_code/copy_manifest.json').read_text()), Path(manifest['policy']['checkpoint']))
    sessions, all_chips = [], []
    for spec in manifest['sessions']:
        path = Path(spec['raw_hands'])
        data = path.read_bytes()
        lines = data.split(b'\n')
        tail = lines.pop()
        rows = [json.loads(line) for line in lines if line.strip()]
        if [row['successful_hand'] for row in rows] != list(range(1, len(rows)+1)):
            raise ValueError('Raw successful-hand evidence is not contiguous')
        chips = [row['winnings_chips'] for row in rows]
        stats = chip_statistics(chips)
        all_chips.extend(chips)
        gaps = [{'successful_hand': row['successful_hand'], 'attempted_hand': row['attempted_hand']}
                for row in rows if row['successful_hand'] != row['attempted_hand']]
        sessions.append(dict(id=spec['id'], completed_raw_hands=len(rows),
            raw_sha256=sha(path), trailing_bytes=len(tail), first_attempt_gap=gaps[0] if gaps else None,
            descriptive_partial_bb100=stats['bb_per_100']))
    partial = chip_statistics(all_chips)
    if partial['hands'] != ledger['completed_raw_hands'] or partial['hands'] != record['accounting']['evaluation_hands']:
        raise ValueError('Terminal partial accounting mismatch')
    result = dict(status='ABORTED_INFRASTRUCTURE_NONQUALIFYING', evaluation_hands=partial['hands'],
        new_training_hands=0, sessions=sessions, exploratory_partial_raw=partial,
        pilot_completed=False, admission_allowed=False, goal_achieved=False,
        stop_reason=stop, outcome_examined_only_after_stop=True,
        limitations='Unplanned infrastructure-truncated subtotal,not the registered20k baseline; no promotion or pooling with future tests.')
    out.write_text(json.dumps(result, indent=2, sort_keys=True)+'\n')
    lines = ['# Native-sampled Standard10 pilot: infrastructure abort', '',
        'Decision: **ABORTED_INFRASTRUCTURE_NONQUALIFYING**. Not a policy-strength failure or a completed20k result.', '',
        f"Preserved **{partial['hands']:,} complete raw hands**. The integrity stop was requested before inspecting interim winrate/CI. "
        'No raw row, checkpoint, session seed or frozen execution source was changed; no supplement or restart was used.', '',
        'Part04 attempt127 failed to establish a new HTTPS connection(WinError10048) and was skipped. '
        'Successful hand127 is attempted hand128; the fixed2500-attempt loop could no longer reach2500successful hands. '
        'The affected owned PID was stopped after ownership verification, and the original wrapper stopped its other clients. '
        'All clients are terminal; the record retains their actual nonzero exit codes.', '',
        f"Exploratory subtotal only, calculated after stopping: {partial['bb_per_100']:+.4f}bb/100, naive raw95% CI "
        f"[{partial['lower_bound_bb_per_100']:+.4f}, {partial['upper_bound_bb_per_100']:+.4f}]. "
        'This unplanned truncated subtotal does not satisfy the registered pilot and admits no formal100k test.', '',
        '## Next', '',
        'Separately log and test persistent per-process HTTP connection reuse with no automatic POST retries, '
        'plus strict immediate failure on hand/transport errors. Do not alter Windows networking settings or unrelated processes. '
        'Only after validation choose a new independently preregistered test with fresh sessions/evidence; never continue these interrupted files.', '',
        'The actual connection setup failure is proven. The client uses per-call requests.post; observed TIME_WAIT churn motivates pooling. '
        'System-wide ephemeral-port exhaustion is not established. [Requests connection reuse](https://requests.readthedocs.io/en/stable/user/advanced/) '
        'and [Microsoft diagnostic guidance](https://learn.microsoft.com/en-us/troubleshoot/windows-client/networking/tcp-ip-port-exhaustion-troubleshooting) '
        'support investigating connection churn,not asserting a broader unverified cause.', '',
        'Goal remains unachieved: a qualifying fixed-policy fresh100k result is still required.']
    (BASE/'result_summary.md').write_text('\n'.join(lines)+'\n')
    pending = json.loads((BASE/'deferred_review_updates.json').read_text())
    args = ['--metric', 'supplemental_review_updates_merged=1', '--metric', 'agent_requested_integrity_abort=1',
            '--command', f'python {Path(__file__).relative_to(ROOT).as_posix()}']
    for command in pending['commands']:
        args += ['--command', command]
    for key, value in pending['metrics'].items(): args += ['--metric', f'{key}={value}']
    for note in pending['notes']: args += ['--note', note]
    for path in pending['artifacts']+[str(BASE/name) for name in ['deferred_review_updates.json',
        'integrity_stop_reason.json', 'integrity_abort_analysis.json', 'result_summary.md', 'close_integrity_abort.py']]:
        args += ['--artifact', path]
    log(*args, '--note', 'Merged all deferred review/tests/prefix provenance after original writer EXIT1. Completion-only review was intentionally NOT run. The agent triggered outcome-blind integrity shutdown after a verified skipped attempt; this was not a score-based stop or mysterious model crash.')
    subprocess.run([sys.executable, 'research/experiment_log.py', 'finish', BASE.name,
        '--status', 'FAILED', '--count', f'evaluation_hands={partial["hands"]}', '--count', 'new_training_hands=0',
        '--summary', f'Outcome-blind infrastructure abort preserved{partial["hands"]}complete raw hands. A local new_hand connection setup error10048 caused a skipped attempt, making the exact fixed20k design unattainable without forbidden supplementation.',
        '--conclusion', 'Original8clients were stopped through owned-process verification and wrapper cleanup; all evidence and immutable policy/source hashes retained. Partial results are exploratory only. No valid completed sampled baseline,policy rejection,formal100k admission or goal success is claimed.',
        '--decision', 'ABORTED_INFRASTRUCTURE_NONQUALIFYING_NO_RESTART_NO_SUPPLEMENT',
        '--next-step', 'Preregister offline HTTP-session pooling/no-POST-retry and strict fail-fast transport repair. Validate with local keep-alive server and mocked failures,then choose a fresh separately logged external experiment; never resume or pool interrupted evidence.'], cwd=ROOT, check=True)
    print(json.dumps(result))


if __name__ == '__main__':
    main()
