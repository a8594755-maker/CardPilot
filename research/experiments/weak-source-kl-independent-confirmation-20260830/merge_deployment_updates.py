"""Attach zero-hand deployment provenance after the original writer exits."""
import json
from pathlib import Path

from run_confirmation import BASE, CANDIDATES, ROOT, ensure_idle, log, sha


def main():
    ensure_idle()
    record = json.loads((BASE/'experiment.json').read_text())
    if record['metrics'].get('deployment_provenance_merged') == 1:
        print('Deployment provenance already merged')
        return
    if record['status'] not in ['RUNNING', 'COMPLETED'] or record['metrics'].get('replication_complete') != 1:
        raise ValueError('Completed original confirmation evidence required before merge')
    pending = json.loads((BASE/'deferred_deployment_updates.json').read_text())
    summary = json.loads((BASE/'deployment_readiness/readiness_analysis.json').read_text())
    if (summary['status'] != 'PASS' or summary['checkpoint_sha256'] != CANDIDATES[2][2]
            or any(summary[k] != 0 for k in ['actual_training_hands', 'actual_evaluation_hands', 'actual_slumbot_hands', 'network_calls_attempted'])
            or sha(BASE/'validate_deployment_dry_run.py') != summary['validation_script_sha256']
            or sha(BASE/'deployment_readiness/zero_hand_result.json') != summary['loader_result_sha256']
            or sha(BASE/'execution_code/source_files/scripts/alpha_holdem/play_slumbot.py') != summary['source_sha256']):
        raise ValueError('Supplemental readiness evidence changed or incomplete')
    args = ['--metric', 'deployment_provenance_merged=1', '--command', f'python {Path(__file__).relative_to(ROOT).as_posix()}']
    for command in pending['commands_executed']: args += ['--command', command]
    for key, value in pending['metrics'].items(): args += ['--metric', f'{key}={value}']
    for note in pending['notes']: args += ['--note', note]
    for path in pending['artifacts']+[str(BASE/'deferred_deployment_updates.json'), __file__]: args += ['--artifact', path]
    log(*args)


if __name__ == '__main__':
    main()
