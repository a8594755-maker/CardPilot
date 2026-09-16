"""Analyze retained reports and close this terminal experiment; no poker execution."""
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import psutil

HERE = Path(__file__).resolve().parent
BASE = HERE.parent
ROOT = BASE.parents[2]
OLD = ROOT / 'research/experiments/v6-preflop-actor-trunk-two-seed-geometric-20260906/recovery_20260906/post_terminal_review.json'
MATH = ROOT / 'research/experiments/v6-current-kl-representation-pilot-20260905/post_analysis/curve_comparison.py'

def require(ok, message):
    if not ok:
        raise RuntimeError(message)

def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))

def sha(path):
    with Path(path).open('rb') as handle:
        return hashlib.file_digest(handle, 'sha256').hexdigest()

def write_new(path, value):
    with path.open('x', encoding='utf-8') as handle:
        json.dump(value, handle, indent=2, allow_nan=False)

def exact(argv):
    return subprocess.list2cmdline([str(x) for x in argv])

def terminal(identity):
    try:
        process = psutil.Process(identity['pid'])
        require(abs(process.create_time() - identity['create_time']) > 0.01,
                'exact process still live')
    except psutil.NoSuchProcess:
        pass

def logger(args):
    argv = [sys.executable, '-B', str(ROOT / 'research/experiment_log.py'), *args]
    result = subprocess.run(argv, cwd=ROOT, capture_output=True, text=True, encoding='utf-8')
    require(result.returncode == 0, result.stdout + result.stderr)
    return result.stdout

def main():
    require(Path.cwd().resolve() == ROOT, 'wrong workspace')
    record = read(BASE / 'experiment.json')
    require(record['status'] == 'RUNNING', 'preserve finished record')
    output = HERE / 'curve_1m_to_2m.json'
    require(not output.exists(), 'preserve existing analysis; inspect before any retry')
    follow = read(HERE / 'followthrough_execution.json')
    status = read(BASE / 'status.json')
    for identity in (follow, follow['bound_owner'], follow['review_child'], status):
        terminal(identity)
    require(follow['status'] == 'REVIEW_COMPLETE_NEEDS_RESEARCH_DECISION' and
            follow['review_child']['exit_code'] == 0, 'review incomplete')
    current_path = BASE / 'post_terminal_review.json'
    require(sha(current_path) == follow['review_sha256'], 'terminal review changed')
    require(sha(OLD) == '4a244d2f06991c2bab1657f295d1b2fa218758f46827f888555ff35cb770bced', 'old review changed')
    require(sha(MATH) == 'dbe4ae9ad29a542b1a9f6a9c21faa978f36d52793ddf963ce2be442cc18a733d', 'qualified math changed')
    old, current = read(OLD), read(current_path)
    require(old['passed'] and current['passed'] and current['all_recorded_processes_terminal'], 'invalid reports')
    require(current['accounting']['new_training_hands'] == 4190918 and
            current['accounting']['evaluation_hands'] == 32768 and
            current['unique_new_evaluation_decks'] == 4096, 'fixed budget mismatch')
    hashes = dict(current['input_sha256'])
    for path in (OLD, current_path, MATH, Path(__file__), HERE / 'followthrough_execution.json'):
        hashes[str(path)] = sha(path)
    for name in ('qualification.json', 'followthrough_qualification.json'):
        qualification = read(HERE / name)
        require(qualification['passed'] and qualification['exit_code'] == 0, 'qualification failed')
        for path, digest in qualification['input_sha256'].items():
            require(path not in hashes or hashes[path] == digest, 'conflicting source hash')
            hashes[path] = digest
    for path, digest in hashes.items():
        require(sha(path) == digest, 'changed input: ' + path)
    # Import only the already-qualified arithmetic, not its prior experiment main.
    sys.path.insert(0, str(MATH.parent))
    spec = importlib.util.spec_from_file_location('retained_curve_math', MATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    curves = {}
    for seed in ('1', '3'):
        earlier, later = old['stages']['2'][seed], current['stages']['3'][seed]
        doses = {}
        for arm in ('connected', 'detached'):
            previous = old['training_health_and_realized_update_dose'][f'seed{seed}_{arm}_stage2']
            now = current['training_health_and_realized_update_dose'][f'seed{seed}_{arm}_stage3']
            doses[arm] = now['cumulative_physical_hands'] - previous['cumulative_physical_hands']
            require(doses[arm] == now['new_physical_hands_this_stage'] > 0, 'dose mismatch')
        curves[seed] = {
            'relative_advantage_change': module.bucket_changes(earlier['connected_minus_detached'], later['connected_minus_detached']),
            'parent_relative_changes': {arm: module.bucket_changes(earlier['endpoint_minus_parent'][arm], later['endpoint_minus_parent'][arm]) for arm in doses},
            'absolute_changes': {arm: module.bucket_changes(earlier['absolute_vs_anchors'][arm], later['absolute_vs_anchors'][arm]) for arm in doses},
            'new_physical_hands': doses}
    require(sum(sum(s['new_physical_hands'].values()) for s in curves.values()) == 4190918, 'dose sum')
    result = {'passed': True, 'created_at': datetime.now(timezone.utc).isoformat(),
              'command': sys.orig_argv, 'input_sha256': hashes, 'seeds': curves,
              'scope': 'Exploratory independent-deck nominal conditional intervals; not seed-population inference, multiplicity-corrected significance, causal attribution or external strength.',
              'new_training_or_evaluation_hands': 0, 'automatic_next_scale': False}
    write_new(output, result)
    counts = current['accounting']
    metrics = {key: current[key] for key in ('training_subprocess_wall_seconds', 'all_job_wall_seconds',
               'controller_wall_seconds', 'review_wall_seconds', 'actual_new_physical_hands_per_training_wall_second',
               'unique_new_evaluation_decks', 'prior_common_deck_rows_checked', 'statistical_not_bitwise_worker_continuation')}
    metrics.update({'terminal_review_passed': True, 'closure_input_hashes_rechecked': len(hashes),
                    'curve_1m_to_2m': curves, 'goal_achieved': False,
                    'launch_audit_scope_deviation_preserved': True})
    commands = [exact(sys.orig_argv), exact(follow['command']), exact(follow['review_child']['command'])]
    for name in ('qualification.json', 'followthrough_qualification.json'):
        q = read(HERE / name)
        commands += [exact(q['command']), exact(q['pytest_command'])]
    commands += [f'powershell -NoProfile -ExecutionPolicy Bypass -File research/experiments/{BASE.name}/post_analysis/launch_followthrough.ps1',
                 'python research/experiment_log.py audit --since "2026-09-06T16:55:06+00:00" --fail-on-warning']
    artifacts = {p.resolve() for p in HERE.iterdir() if p.is_file()}
    artifacts.add(current_path)
    artifacts.update(p.resolve() for p in BASE.glob('controller*') if p.is_file())
    payload = []
    for flag, values in (('--count', counts), ('--metric', metrics)):
        for key, value in values.items():
            payload += [flag, key + '=' + json.dumps(value, separators=(',', ':'), allow_nan=False)]
    seen = {item['command'] for item in record['commands']}
    for command in dict.fromkeys(commands):
        if command not in seen:
            payload += ['--command', command]
    existing = {Path(p).resolve() for p in record['artifacts']}
    for path in sorted(artifacts):
        if path not in existing:
            payload += ['--artifact', path.relative_to(ROOT).as_posix()]
    payload += ['--note', 'Completed original fixed2M jobs and the single independent reviewer; neither rerun. Added retained1M-to2M independent-deck analysis and deferred helper qualification/actual commands. Preserve 348-record/238-warning mis-scoped launch audit; corrected explicitISO one-record audit passed. Full logger wall includes overnight idle and user discussion; separate controller/training/review wall metrics are actual execution costs. Earlier unknown crash tails remain unknown; statistical worker continuation is not bitwise. Replay is not new environment hands.']
    while payload:
        chunk = []
        while payload and len(exact([sys.executable, ROOT/'research/experiment_log.py', 'update', BASE.name, *chunk, *payload[:2]])) < 24000:
            chunk += payload[:2]
            del payload[:2]
        require(chunk, 'logger item exceeds Windows limit')
        logger(['update', BASE.name, *chunk])
    logger(['finish', BASE.name,
            '--summary', 'Four retained actor-route endpoints completed fixed2M: 4190918 new physical training hands,32768 internal executions,4096 unique evaluation decks; independent terminal review passed.',
            '--conclusion', 'Connected-minus-detached +18.6401/+23.6543 bb100, both nominal95CI include zero. Connected versus original parent -6.1401/-12.1704. No replicated positive own learning curve; relative advantage may reflect control deterioration. Integrity passed, external strength untested at2M.',
            '--decision', 'Evidence shortage, not winning policy or global long-run mechanism disproof. Keep all four endpoints and unchanged raw evidence. No promotion, final qualification or automatic larger training allocation.',
            '--next-step', 'Separately preregister fixed untouched external calibration of all four2M policies using the qualified legacy-observation greedy executor before deciding further compute. Compare both seeds and controls; do not cherry-pick or use Slumbot action labels.'])
    final = read(BASE / 'experiment.json')
    require(final['status'] == 'COMPLETED', 'finish failed')
    audit = BASE / 'post_finish_audit.json'
    require(not audit.exists(), 'preserve audit')
    audit_args = ['audit', '--since', final['created_at'], '--out-json', str(audit), '--fail-on-warning']
    first = logger(audit_args)
    logger(['update', BASE.name, '--artifact', audit.relative_to(ROOT).as_posix(),
            '--command', exact([sys.executable, '-B', ROOT / 'research/experiment_log.py', *audit_args])])
    last = logger(['audit', '--since', final['created_at'], '--fail-on-warning'])
    print(json.dumps({'passed': True, 'status': 'COMPLETED', 'audit': first, 'attachment_audit': last,
                      'connected_parent_relative_curve': {s: curves[s]['parent_relative_changes']['connected']['pooled'] for s in curves}}))

if __name__ == '__main__':
    main()
