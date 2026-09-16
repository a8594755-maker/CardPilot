"""Post-terminal raw statistics and independent-stream checks; no network calls."""
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import statistics
import subprocess
import sys

import psutil

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[2]
RUNTIME = BASE / 'prepared_runtime/scripts/alpha_holdem'
CONTROL = ROOT / 'research/experiments/v6-standard10-legacy-bridge-greedy-fresh20k-20260901'
SOURCE_SHA = '7ea4d74d0fcf881c75c4c99bdc0cbe84f82a55001ba277c01aafec6dc5a98f3f'


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def sha(path):
    with Path(path).open('rb') as handle:
        return hashlib.file_digest(handle, 'sha256').hexdigest()


def write_new(path, value):
    with Path(path).open('x', encoding='utf-8') as handle:
        json.dump(value, handle, indent=2, allow_nan=False)
        handle.write('\n')


def terminal_identity(row):
    try:
        proc = psutil.Process(int(row['pid']))
        return abs(proc.create_time() - float(row['create_time'])) >= .001 or not proc.is_running()
    except psutil.NoSuchProcess:
        return True


def stats(values):
    mean = statistics.mean(values)
    half = 1.96 * statistics.stdev(values) / math.sqrt(len(values))
    return {'hands': len(values), 'bb_per_100': mean, 'raw_ci95': [mean-half, mean+half]}


def main():
    execution = read(BASE / 'execution.json')
    if execution['status'] != 'COMPLETED_PENDING_REVIEW' or execution['evaluation_hands'] != 20000:
        raise ValueError('Complete fixed-budget execution required before statistics')
    if not all(terminal_identity(row) for row in [execution, *execution['children']]):
        raise RuntimeError('Evaluation owner or child still live; do not compete for logger')
    if len(execution['children']) != 8 or any(row['exit_code'] != 0 for row in execution['children']):
        raise ValueError('Missing successful session exits')
    audit = read(BASE / 'combined_audit.json')
    if audit['status'] != 'PASS' or audit['successful_hands'] != 20000 or audit['model_sha256'] != SOURCE_SHA:
        raise ValueError('Original full replay audit must pass')
    if sha(BASE / 'frozen/final.pt') != SOURCE_SHA:
        raise ValueError('Frozen model changed')
    outputs = ['independence_audit.json', 'raw_ci.json', 'vs_same_contract_standard10.json',
               'seat_analysis.json', 'post_analysis_inputs.json']
    if any((BASE / name).exists() for name in outputs):
        raise FileExistsError('Preserve previous post-analysis output; no overwrite')
    sessions = [BASE / 'sessions' / f's{i:02d}' for i in range(1, 9)]
    candidates = [path / 'hands.jsonl' for path in sessions]
    controls = [CONTROL / 'sessions' / f's{i:02d}' / 'hands.jsonl' for i in range(1, 9)]
    commands = [
        [sys.executable, str(RUNTIME / 'audit_journaled_slumbot_independence.py'),
         *[arg for path in sessions for arg in ('--session-dir', str(path))],
         '--out-json', str(BASE / 'independence_audit.json')],
        [sys.executable, str(RUNTIME / 'slumbot_ci_from_hands.py'), *map(str, candidates),
         '--baseline-bb100', '-24.5683', '--baseline-hands-min', '20000',
         '--out-json', str(BASE / 'raw_ci.json')],
        [sys.executable, str(RUNTIME / 'compare_independent_slumbot_samples.py'),
         *[arg for path in candidates for arg in ('--candidate', str(path))],
         *[arg for path in controls for arg in ('--control', str(path))],
         '--out-json', str(BASE / 'vs_same_contract_standard10.json')],
    ]
    paths = [Path(__file__), BASE / 'protocol.md', BASE / 'execution.json', BASE / 'completed_analysis.json',
             BASE / 'combined_audit.json', CONTROL / 'completed_analysis.json', *candidates, *controls,
             *[Path(command[1]) for command in commands]]
    hashes = {str(path.resolve()): sha(path) for path in paths}
    write_new(BASE / 'post_analysis_inputs.json', {'input_sha256': hashes, 'commands': commands,
              'started_at': datetime.now(timezone.utc).isoformat(), 'new_hands': 0})
    for command in commands:
        subprocess.run([sys.executable, str(ROOT / 'research/experiment_log.py'), 'update', BASE.name,
                        '--command', subprocess.list2cmdline(command)], cwd=ROOT, check=True)
        subprocess.run(command, cwd=ROOT, check=True, stdout=subprocess.DEVNULL)
    independence = read(BASE / 'independence_audit.json')
    if independence['status'] != 'PASS' or independence['hands'] != 20000:
        raise ValueError('Independent-stream audit failed')
    raw = {0: [], 1: []}
    seat_sessions = []
    for path in candidates:
        groups = {0: [], 1: []}
        with path.open(encoding='utf-8') as handle:
            for line in handle:
                row = json.loads(line)
                pos = row['terminal_response']['client_pos']
                if pos not in (0, 1):
                    raise ValueError('Unknown client seat')
                groups[pos].append(row['winnings_chips'])
                raw[pos].append(row['winnings_chips'])
        seat_sessions.append({'session': path.parent.name, 'seats': {key: stats(value) for key, value in groups.items()}})
    if sum(map(len, raw.values())) != 20000:
        raise ValueError('Seat accounting mismatch')
    for path, expected in hashes.items():
        if sha(path) != expected:
            raise ValueError(f'Frozen post-analysis input changed: {path}')
    result = {'schema': 'cardpilot.static4m.external_development_post_analysis.v1', 'status': 'PASS',
              'evaluation_hands': 20000, 'new_hands_used': 0, 'goal_achieved': False,
              'by_seat': {key: stats(value) for key, value in raw.items()}, 'by_session': seat_sessions,
              'descriptive_only': True, 'baseline_comparison_is_unpaired': True}
    write_new(BASE / 'seat_analysis.json', result)
    args = [sys.executable, str(ROOT / 'research/experiment_log.py'), 'update', BASE.name]
    for path in [Path(__file__), *[BASE / name for name in outputs]]:
        args += ['--artifact', str(path)]
    subprocess.run(args, cwd=ROOT, check=True)
    print(json.dumps({'status': 'PASS', 'hands': 20000, 'new_hands': 0,
                      'same_contract_comparison': read(BASE / 'vs_same_contract_standard10.json'),
                      'by_seat': result['by_seat']}))


if __name__ == '__main__':
    main()
