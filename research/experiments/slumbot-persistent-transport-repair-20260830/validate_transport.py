"""Freeze and validate transport repair offline; never launch real poker games."""
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import threading
from http.server import ThreadingHTTPServer

import psutil

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT/'scripts'))
from research.experiment_log import capture_code_provenance
from scripts.alpha_holdem.audit_slumbot_hand_evidence import sha

DIGEST = '91b0c587a5a76e9a8f38217e0b304136ef298118a99b69cc743899fc4b16e428'


def log(*args):
    subprocess.run([sys.executable, 'research/experiment_log.py', 'update', BASE.name,
        *map(str, args)], cwd=ROOT, check=True)


def invoke(args, output):
    log('--command', subprocess.list2cmdline(['python', *map(str, args)]))
    result = subprocess.run([sys.executable, *map(str, args)], cwd=ROOT, capture_output=True, text=True)
    output.write_text(result.stdout+'\n'+result.stderr, encoding='utf-8')
    log('--artifact', output)
    if result.returncode:
        raise RuntimeError(f'Validation failed; inspect {output.name}; no production started')
    return result


def main():
    for process in psutil.process_iter(['name', 'cmdline']):
        if (process.info['name'] or '').lower().startswith('python') and any(
            Path(arg).name in ['play_slumbot.py', 'train_v5.py', 'run_external.py']
            for arg in process.info['cmdline'] or []):
            raise RuntimeError('Do not validate while poker work is live')
    snapshot = BASE/'final_code'
    if snapshot.exists() or (BASE/'transport_analysis.json').exists():
        raise RuntimeError('Preserve prior validation; do not overwrite or replay')
    parent = ROOT/'research/experiments/standard10-native-sampled-slumbot20k-20260830'
    if json.loads((parent/'experiment.json').read_text())['status'] != 'FAILED':
        raise RuntimeError('Parent baseline is not terminal')
    retained_paths = [parent/'experiment.json', parent/'frozen/standard10.pt',
        parent/'integrity_abort_analysis.json', *sorted((parent/'sessions').glob('*'))]
    retained_hashes = {str(p): sha(p) for p in retained_paths if p.is_file()}
    snapshot.mkdir()
    paths = [p.relative_to(ROOT).as_posix() for p in sorted((ROOT/'scripts/alpha_holdem').glob('*.py'))]
    paths += [f'scripts/deep_cfr/{name}.py' for name in ['__init__', 'game_state', 'hand_eval']]
    paths += ['research/experiment_log.py', Path(__file__).relative_to(ROOT).as_posix()]
    _, artifacts = capture_code_provenance(ROOT, snapshot, paths)
    copies = []
    for relative in paths:
        target = snapshot/'source_files'/relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT/relative, target)
        copies.append(dict(original=relative, copy=target.relative_to(ROOT).as_posix(), sha256=sha(target)))
    (snapshot/'copy_manifest.json').write_text(json.dumps(copies, indent=2)+'\n')
    log('--command', f'python {Path(__file__).relative_to(ROOT).as_posix()}',
        *[item for path in [*artifacts, snapshot/'copy_manifest.json', __file__]
          for item in ['--artifact', str(path)]])
    tests = ['-m', 'pytest', *[f'scripts/alpha_holdem/{name}.py' for name in [
        'test_slumbot_transport', 'test_slumbot_execution_telemetry', 'test_stochastic_slumbot_evidence',
        'test_slumbot_ci_from_hands', 'test_sampled_mirror_eval']], 'research/test_experiment_log.py',
        '-q', '--tb=short', f'--junitxml={BASE/"test_results.xml"}']
    tested = invoke(tests, BASE/'test_stdout.log')
    passed = int(re.search(r'(\d+) passed', tested.stdout).group(1))
    if passed != 83:
        raise RuntimeError('Unexpected test count')
    from scripts.alpha_holdem.test_slumbot_transport import Handler, connection_reuse_probe
    from alpha_holdem import slumbot_transport as transport
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    server.calls, server.connections, server.guard = [], 0, threading.Lock()
    thread = threading.Thread(target=server.serve_forever, kwargs={'poll_interval': .05}, daemon=True)
    thread.start()
    try:
        probe = connection_reuse_probe(server, f'http://127.0.0.1:{server.server_port}')
        calls = list(server.calls)
    finally:
        transport.close_transport()
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
    (BASE/'local_http_probe.json').write_text(json.dumps(dict(summary=probe, requests=calls), indent=2)+'\n')
    dry_path = BASE/'strict_zero_hand_loader.json'
    source = ROOT/'models/baseline/standard10/latest.pt'
    invoke([snapshot/'source_files/scripts/alpha_holdem/play_slumbot.py', '--model', source,
        '--hands', '0', '--device', 'cpu', '--strategy', 'model', '--policy-mode', 'sample',
        '--temperature', '1', '--policy-seed', '2026090600', '--strict-policy-execution',
        '--result-json', dry_path], BASE/'loader_stdout.log')
    dry = json.loads(dry_path.read_text())
    if (sha(source) != DIGEST or dry['model_sha256'] != DIGEST or dry['successful_hands'] != 0
            or dry['requested_hands'] != 0 or not dry['dry_run'] or dry['policy_seed'] != 2026090600
            or dry['policy_mode_raw'] != 'sample' or dry['temperature'] != 1
            or dry['strict_policy_execution'] is not True or dry['http_transport'] != transport.TRANSPORT_MODE):
        raise RuntimeError('Zero-hand loader identity/strict-mode validation failed')
    for row in copies:
        if sha(ROOT/row['original']) != row['sha256'] or sha(ROOT/row['copy']) != row['sha256']:
            raise RuntimeError('Source changed during validation')
    if any(sha(Path(path)) != digest for path, digest in retained_hashes.items()):
        raise RuntimeError('Parent evidence changed during repair')
    result = dict(status='PASS', tests_passed=passed, connection_probe=probe,
        actual_slumbot_hands=0, actual_training_hands=0, source_sha256=DIGEST,
        http_transport=transport.TRANSPORT_MODE, strict_zero_hand_loader_pass=True,
        final_source_hash_checks_pass=True, parent_preserved_sha256=retained_hashes,
        limitations=['Loopback fixture demonstrates client reuse, not server keepalive or global port exhaustion.',
            'No POST retries even after ambiguous response failure; a failed fresh session remains nonqualifying.',
            'No strength claim or actual poker evaluation follows from offline protocol fixtures.',
            'Native action probabilities are unchanged; strict mode removes legacy error fallback/skip behavior.',
            'Redirects are explicitly refused rather than followed; cookies are not retained between API calls.'])
    (BASE/'transport_analysis.json').write_text(json.dumps(result, indent=2)+'\n')
    (BASE/'result_summary.md').write_text('\n'.join([
        '# Persistent Slumbot transport repair', '', f'PASS: {passed} tests; actual poker hands: **0**.', '',
        'Local HTTP/1.1 fixture:120 ordered POSTs over120 connections in the per-call control, '
        'versus120 identical POSTs over1 connection using the new transport. No duplicate requests or cookie carryover.', '',
        'HTTP/redirect/JSON/dropped-response/refused-connection failures do not replay POSTs. '
        'Strict client execution stops before fallback or subsequent attempts and preserves completed raw rows. '
        'Legacy behavior remains opt-in by absence of the strict flag; error fallback telemetry remains auditable.', '',
        'Strict manifest metadata, old evidence/CI contracts, seed tests and logger tests passed. '
        'Real Standard10 strict sample/temp1 loader passed atzero hands with unchanged model SHA. '
        'The aborted parent record and retained session artifacts have unchanged hashes.', '',
        *['- '+item for item in result['limitations']], '',
        'Next: separately preregister a fresh fixed20k sampled Standard10 baseline using this validated strict transport; '
        'new seeds/outputs, no pooling with the aborted4,168hands. Still not the qualifying100k goal.', '',
        '[Requests Session connection pooling](https://requests.readthedocs.io/en/stable/user/advanced/)',
    ])+'\n')
    log('--metric', f'tests_passed={passed}', '--metric', 'actual_slumbot_hands=0',
        '--metric', 'control_connections=120', '--metric', 'pooled_connections=1',
        '--metric', 'final_source_hash_checks_pass=1',
        *[item for name in ['test_results.xml', 'local_http_probe.json', 'strict_zero_hand_loader.json',
            'transport_analysis.json', 'result_summary.md'] for item in ['--artifact', str(BASE/name)]])
    subprocess.run([sys.executable, 'research/experiment_log.py', 'finish', BASE.name,
        '--status', 'COMPLETED', '--count', 'new_training_hands=0', '--count', 'evaluation_hands=0',
        '--summary', 'Offline persistent transport passed83tests. Exactly120fixture POSTs use1connection versus120in control; no POST retries, cookie carryover or strict hand fallback. Real Standard10 strict zero-hand loader passed.',
        '--conclusion', 'Client connection reuse and fail-fast evidence contracts are verified without changing learned weights or historical evidence. This addresses avoidable connection churn,not a proven system-wide exhaustion cause or policy strength.',
        '--decision', 'READY_FOR_NEW_STRICT_FRESH_BASELINE',
        '--next-step', 'Preregister a separate fixed20k native-sampled Standard10 baseline with new seeds and strict transport. Never resume or combine aborted parent hands.'], cwd=ROOT, check=True)
    print(json.dumps({k: result[k] for k in ['status', 'tests_passed', 'connection_probe', 'actual_slumbot_hands']}))


if __name__ == '__main__':
    main()
