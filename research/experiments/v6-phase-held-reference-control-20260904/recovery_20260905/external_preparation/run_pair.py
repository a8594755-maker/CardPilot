"""Draft guarded80k external runner; refuses launch until the training record finishes."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import statistics
import subprocess
import sys
import time
import traceback

import psutil

HERE = Path(__file__).resolve().parent
TRAINING = HERE.parents[1]
ROOT = TRAINING.parents[2]
sys.path.insert(0, str(HERE))
import pair_protocol as protocol
sys.path.insert(0, str(ROOT))
from research.experiment_log import atomic_json, capture_code_provenance

EXPECTED_MODELS = {
    'static': (TRAINING / 'recovery_20260905/static_stage2_remainder/latest.pt',
               '41ff38496167424fa71373028e9291a0d8bd595315f7121d8fa303e6b15a3372'),
    'moving256': (TRAINING / 'moving256_stage2/latest.pt',
                  'b0ab97e76dd6d3603b5b6cde0b2fccaa1726fb8b825b23458f9f9f58dc36f932'),
}
RUNTIME_SOURCE = ROOT / 'research/experiments/v6-static-seed1-4m-greedy-fresh20k-slumbot-20260904/prepared_runtime/scripts'
REPORT = TRAINING / 'recovery_20260905/post_terminal_report.json'
READINESS = ROOT / 'research/experiments/v6-source-live-readiness-20260831/reviewed_analysis.json'


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def sha(path):
    with Path(path).open('rb') as handle:
        return hashlib.file_digest(handle, 'sha256').hexdigest()


def write_new(path, value):
    with Path(path).open('x', encoding='utf-8') as handle:
        json.dump(value, handle, indent=2, allow_nan=False)
        handle.write('\n')
        handle.flush()
        os.fsync(handle.fileno())


def check_hashes(hashes):
    for path, expected in hashes.items():
        protocol.require(sha(path) == expected, f'frozen input changed: {path}')


def prior_initial_sessions(experiments, excluded):
    """Cover readable initial tokens even where an old combined audit failed."""
    sessions, unreadable = [], []
    for path in sorted(Path(experiments).glob('*/sessions/**/hands.jsonl')):
        if Path(excluded) in path.parents:
            continue
        try:
            with path.open('rb') as handle:
                prefix = handle.readline()
            if not prefix:
                continue
            if not prefix.endswith(b'\n'):
                unreadable.append({'path': str(path), 'reason': 'no_complete_initial_record'})
                continue
            row = json.loads(prefix)
            if not row.get('session_token_sha256'):
                continue  # not a journaled Slumbot record
            sessions.append({'path': str(path), 'prefix_bytes': len(prefix),
                'prefix_sha256': hashlib.sha256(prefix).hexdigest(),
                'initial_token_sha256': row['session_token_sha256'],
                'session_id': row['session_id'], 'policy_seed': row['policy_seed']})
        except (OSError, UnicodeError, json.JSONDecodeError, KeyError) as exc:
            unreadable.append({'path': str(path), 'reason': type(exc).__name__})
    return sessions, unreadable


def check_prior_prefixes(sessions):
    for row in sessions:
        with Path(row['path']).open('rb') as handle:
            actual = hashlib.sha256(handle.read(row['prefix_bytes'])).hexdigest()
        protocol.require(actual == row['prefix_sha256'], 'captured prior-session prefix changed')


def check_unused_session_identifiers(sessions):
    old_ids = {row['session_id'] for row in sessions}
    old_seeds = {row['policy_seed'] for row in sessions}
    protocol.require(not old_ids.intersection(row['session_id'] for row in protocol.schedule()), 'planned session ID already used')
    protocol.require(not old_seeds.intersection(row['policy_seed'] for row in protocol.schedule()), 'planned policy seed already used')


def live_identity(identity):
    try:
        process = psutil.Process(int(identity['pid']))
        return abs(process.create_time() - identity['create_time']) < .001 and process.is_running()
    except psutil.NoSuchProcess:
        return False


def training_ready():
    protocol.require(read(TRAINING / 'experiment.json')['status'] == 'COMPLETED', 'training experiment not finished')
    for directory in (TRAINING, TRAINING / 'recovery_20260905'):
        protocol.require(not live_identity(read(directory / 'ownership.json')), 'training controller still live')
    report = read(REPORT)
    protocol.require(report['passed'] and report['unknown_interrupted_suffix_not_recovered_or_counted'], 'interruption-aware report not qualified')
    protocol.require(report['accounting']['evaluation_hands'] == 131072 and report['accounting']['slumbot_hands'] == 0,
                     'original internal evaluation incomplete')
    protocol.require(all(n >= 8392280 for n in report['accounting']['per_arm_cumulative_physical_hands'].values()), 'training target incomplete')
    for path, expected in EXPECTED_MODELS.values():
        protocol.require(sha(path) == expected == report['input_sha256'][str(path)], 'audited final endpoint changed')
    protocol.require(read(READINESS)['status'] == 'PASS', 'journaled runtime readiness not qualified')


def preflight(base):
    """No file writes, model loading or network in preflight, including rejection."""
    base = Path(base).resolve()
    protocol.require(base.parent == ROOT / 'research/experiments', 'not a direct experiment directory')
    training_ready()
    protocol.require(read(base / 'experiment.json')['status'] in ('PLANNED', 'RUNNING'), 'external experiment not preregistered')
    spec = read(base / 'launch_spec.json')
    protocol.require(spec['schema'] == 'cardpilot.phase_reference.external_pair.v1' and spec['development_only'] is True,
                     'wrong external protocol')
    protocol.require(spec['schedule'] == protocol.schedule(), 'fixed schedule changed')
    protocol.require(spec['models'] == {arm: {'path': str(path), 'sha256': digest}
                     for arm, (path, digest) in EXPECTED_MODELS.items()}, 'model substitution')
    protocol.require(Path(spec['runtime_source']).resolve() == RUNTIME_SOURCE, 'unexpected poker runtime')
    protocol.require(spec['training_report_sha256'] == sha(REPORT), 'training report binding changed')
    protocol.require(spec['preregistration_sha256'] == sha(base / 'preregistration.md'), 'preregistration changed')
    runtime = {str(path): sha(path) for path in RUNTIME_SOURCE.rglob('*.py') if '__pycache__' not in path.parts}
    protocol.require(runtime and runtime == spec['runtime_sha256'], 'runtime snapshot incomplete or changed')
    check_hashes(spec['code_sha256'])
    for path in (Path(__file__).resolve(), HERE / 'pair_protocol.py', HERE / 'test_run_pair.py', HERE / 'test_pair_protocol.py'):
        protocol.require(spec['code_sha256'].get(str(path)) == sha(path), 'executed source absent from binding')
    for name in ('execution.json', 'execution_code', 'runtime', 'frozen', 'sessions'):
        protocol.require(not (base / name).exists(), f'prior attempt present; no restart: {name}')
    names = {'train_v5.py', 'play_slumbot_v6_journaled.py', 'v6_public_opponent_matched_eval.py',
             'v6_legacy_bridge_drift_audit.py', 'resume_control.py', 'run_pilot.py', 'run_pair.py'}
    for process in psutil.process_iter(['pid', 'cmdline']):
        if process.pid != os.getpid():
            protocol.require(not any(Path(arg).name in names for arg in process.info.get('cmdline') or []),
                             f'other poker job active: {process.pid}')
    protocol.require(shutil.disk_usage(base).free >= 10 * 1024**3, 'insufficient evidence disk space')
    return spec


class RawCounter:
    """Count only complete committed JSON records, without recomputing running scores."""
    def __init__(self, base, model_hashes):
        self.base, self.models = Path(base), model_hashes
        self.offsets, self.counts = {}, {}

    def refresh(self):
        for item in protocol.schedule():
            path = self.base / 'sessions' / item['arm'] / f's{item["index"]:02d}' / 'hands.jsonl'
            if not path.exists():
                continue
            offset = self.offsets.get(str(path), 0)
            protocol.require(path.stat().st_size >= offset, 'raw evidence truncated')
            count = self.counts.get(str(path), 0)
            with path.open('rb') as handle:
                handle.seek(offset)
                while line := handle.readline():
                    if not line.endswith(b'\n'):
                        break
                    row = json.loads(line)
                    count += 1
                    protocol.require(row['successful_hand'] == row['attempted_hand'] == count <= item['hands'], 'raw hand counter mismatch')
                    protocol.require(row['session_id'] == item['session_id'] and row['policy_seed'] == item['policy_seed'] and
                                     row['model_sha256'] == self.models[item['arm']], 'raw identity mismatch')
                    offset = handle.tell()
                    self.offsets[str(path)], self.counts[str(path)] = offset, count
            self.offsets[str(path)], self.counts[str(path)] = offset, count
        return sum(self.counts.values())


def verify_audits(audits, models, prior_tokens):
    seen = set()
    for arm in protocol.ARMS:
        audit = audits[arm]
        protocol.require(audit['status'] == 'PASS' and audit['sessions'] == 16 and audit['successful_hands'] == 40000,
                         'incomplete per-model audit')
        protocol.require(audit['model_sha256'] == models[arm] and audit['token_chains_disjoint'], 'wrong audit model or token reuse')
        expected = {item['session_id']: item for item in protocol.schedule() if item['arm'] == arm}
        protocol.require(len(audit['results']) == 16 and {row['session_id'] for row in audit['results']} == set(expected), 'audit session identity mismatch')
        for row in audit['results']:
            item = expected[row['session_id']]
            protocol.require(row['status'] == 'PASS' and row['model_sha256'] == models[arm] and row['policy_seed'] == item['policy_seed'], 'wrong session replay identity')
            protocol.require(row['successful_hands'] == row['attempted_hands'] == row['target_hands'] == 2500, 'partial session audit')
            protocol.require(not any(row[key] for key in ('pending_request_id', 'protocol_failures', 'committed_without_raw', 'partial_journal', 'partial_hands')), 'unresolved evidence')
            protocol.require(row['decision_replays'] == row['policy_draws_verified'] > 0, 'missing full model replay')
            tokens = set(row['token_sha256'])
            protocol.require(tokens and not tokens.intersection(seen | prior_tokens), 'cross-arm/prior token chain reused')
            seen.update(tokens)
    return {'status': 'PASS', 'sessions': 32, 'hands': 80000, 'disjoint_cross_arm_and_prior_tokens': True,
            'server_rng_independence_proven': False}


def parse_raw(base, models):
    groups = {arm: [] for arm in protocol.ARMS}
    seats = {arm: {0: [], 1: []} for arm in protocol.ARMS}
    streams = []
    for item in protocol.schedule():
        path = Path(base) / 'sessions' / item['arm'] / f's{item["index"]:02d}' / 'hands.jsonl'
        chips, visible = [], []
        by_seat = {0: [], 1: []}
        with path.open(encoding='utf-8') as handle:
            for index, line in enumerate(handle, 1):
                protocol.require(line.endswith('\n'), 'incomplete raw line')
                row = json.loads(line)
                protocol.require(row['successful_hand'] == row['attempted_hand'] == index and row['session_id'] == item['session_id'], 'raw hand identity changed')
                protocol.require(row['policy_seed'] == item['policy_seed'] and row['model_sha256'] == models[item['arm']], 'raw frozen identity changed')
                protocol.require(row['strict_policy_execution'] and row['policy_mode'] == 'greedy' and row['policy_temperature'] == 0, 'wrong execution mode')
                protocol.require(row['terminal_validation']['status'] == 'PASS' and row['winnings_bb'] == row['winnings_chips'] / 100, 'terminal accounting failed')
                for decision in row['decisions']:
                    protocol.require(decision['policy_mode'] == 'greedy' and decision['temperature'] == 0 and
                        decision['observation_bridge_contract'] == protocol.BRIDGE and
                        decision['selected_action_slot'] == decision['greedy_action_slot'] and
                        decision['behavior_action_probability'] == 1 and decision['direct_increment'] in decision['v6_action_table'], 'greedy bridge decision mismatch')
                terminal = row['terminal_response']
                seat = terminal['client_pos']
                protocol.require(type(seat) is int and seat in (0, 1), 'invalid seat')
                chips.append(row['winnings_chips'])
                by_seat[seat].append(row['winnings_chips'])
                visible.append((seat, tuple(sorted(terminal['hole_cards']))))
        protocol.require(len(chips) == 2500, 'incomplete planned session')
        groups[item['arm']].append(chips)
        for seat in (0, 1):
            protocol.require(len(by_seat[seat]) > 1, 'missing seat observations')
            seats[item['arm']][seat].append(by_seat[seat])
        streams.append({'session_id': item['session_id'], 'arm': item['arm'], 'visible': visible})
    cross_pairs = []
    for left_index, left in enumerate(streams):
        for right in streams[left_index + 1:]:
            if left['arm'] == right['arm']:
                continue
            matches = sum(a == b for a, b in zip(left['visible'], right['visible']))
            protocol.require(matches / 2500 < .05, 'cross-arm visible hero-hole stream suspiciously shared')
            cross_pairs.append({'left': left['session_id'], 'right': right['session_id'], 'matches': matches, 'positions': 2500})
    return groups, seats, {'status': 'PASS', 'cross_arm_same_position_hero_hole_checks': cross_pairs,
        'scope': 'Empirical same-index seat/hero-hole shared-stream check; not proof of arbitrary server RNG independence.'}


def seat_report(seats):
    summaries, contrasts = {}, {}
    for arm in protocol.ARMS:
        summaries[arm] = {}
        for seat in (0, 1):
            groups = seats[arm][seat]
            raw = [value for group in groups for value in group]
            mean = statistics.mean(raw)
            half = 1.96 * statistics.stdev(raw) / len(raw) ** .5
            summaries[arm][str(seat)] = {'hands': len(raw), 'bb_per_100': mean, 'raw_ci95': [mean - half, mean + half],
                'session_hand_counts': [len(group) for group in groups],
                'equal_session_mean_sensitivity': protocol.mean_t([statistics.mean(group) for group in groups]),
                'unequal_seat_counts_can_change_session_vs_hand_weighting': True}
    for seat in (0, 1):
        contrasts[str(seat)] = protocol.welch(
            [value for group in seats['moving256'][seat] for value in group],
            [value for group in seats['static'][seat] for value in group])
    return {'by_arm': summaries, 'moving_minus_static_by_seat': contrasts,
            'descriptive_only': True, 'primary_family_adjustment_not_applied_to_seat_detail': True}


class Runner:
    def __init__(self, base):
        self.started = time.monotonic()
        self.base = Path(base).resolve()
        self.spec = preflight(self.base)
        self.models = {arm: row['sha256'] for arm, row in self.spec['models'].items()}
        self.counter = RawCounter(self.base, self.models)
        self.children, self.handles = [], []
        self.last_tick, self.last_count = 0., 0
        self.execution = {'status': 'PREPARING', 'pid': os.getpid(), 'create_time': psutil.Process().create_time(),
            'started_at': datetime.now(timezone.utc).isoformat(), 'children': [], 'waves': [],
            'evaluation_hands': 0, 'slumbot_hands': 0, 'new_training_hands': 0, 'goal_achieved': False}
        # Exclusive creation arbitrates even two callers that passed preflight together.
        write_new(self.base / 'execution.json', self.execution)
        self.inputs = dict(self.spec['runtime_sha256']) | self.spec['code_sha256']
        for path in (self.base / 'launch_spec.json', self.base / 'preregistration.md', REPORT, READINESS):
            self.inputs[str(path)] = sha(path)
        for row in self.spec['models'].values():
            self.inputs[row['path']] = row['sha256']
        self.runtime = self.base / 'runtime/scripts'
        self.prior_sessions = []

    def verify_inputs(self):
        check_hashes(self.inputs)
        check_prior_prefixes(self.prior_sessions)

    def log(self, *args):
        command = [sys.executable, str(ROOT / 'research/experiment_log.py'), 'update', self.base.name, *map(str, args)]
        subprocess.run(command, cwd=ROOT, check=True, capture_output=True, text=True, timeout=45)

    def record(self, argv):
        self.log('--command', subprocess.list2cmdline(argv))

    def tick(self, force=False):
        if not force and time.monotonic() - self.last_tick < 15:
            return
        count = self.counter.refresh()
        protocol.require(count >= self.last_count, 'raw accounting decreased')
        self.last_count = count
        self.execution.update(evaluation_hands=count, slumbot_hands=count,
            updated_at=datetime.now(timezone.utc).isoformat(), wall_time_seconds=time.monotonic() - self.started)
        atomic_json(self.base / 'execution.json', self.execution)
        self.log('--count', f'evaluation_hands={count}', '--count', f'slumbot_hands={count}',
                 '--metric', f'controller_phase={self.execution["status"]}')
        self.last_tick = time.monotonic()

    def prepare(self):
        self.verify_inputs()
        self.record([sys.executable, '-u', str(Path(__file__)), '--experiment-dir', str(self.base)])
        for source, digest in self.spec['runtime_sha256'].items():
            target = self.runtime / Path(source).relative_to(RUNTIME_SOURCE)
            target.parent.mkdir(parents=True, exist_ok=True)
            protocol.require(not target.exists(), 'runtime file would be overwritten')
            shutil.copy2(source, target)
            self.inputs[str(target)] = digest
        (self.base / 'frozen').mkdir()
        for arm, model in self.spec['models'].items():
            target = self.base / 'frozen' / f'{arm}.pt'
            shutil.copy2(model['path'], target)
            self.inputs[str(target)] = model['sha256']
        code = self.base / 'execution_code'
        code.mkdir()
        sources = list(self.spec['code_sha256']) + [str(self.base / 'preregistration.md'), str(self.base / 'launch_spec.json'), str(ROOT / 'research/experiment_log.py')]
        relative = [Path(path).relative_to(ROOT).as_posix() for path in sources]
        capture_code_provenance(ROOT, code, relative)
        copies = []
        for path in sources:
            source = Path(path)
            target = code / 'source_files' / source.relative_to(ROOT)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            digest = sha(target)
            self.inputs[str(target)] = digest
            copies.append({'original': str(source), 'copy': str(target), 'sha256': digest})
        write_new(code / 'copy_manifest.json', copies)
        self.prior_sessions, unreadable_initial = prior_initial_sessions(ROOT / 'research/experiments', self.base)
        check_unused_session_identifiers(self.prior_sessions)
        self.prior_tokens = {row['initial_token_sha256'] for row in self.prior_sessions}
        prior, unreadable_prior = [], []
        for path in sorted((ROOT / 'research/experiments').glob('*/*combined_audit.json')):
            if self.base in path.parents:
                continue
            try:
                audit = read(path)
            except (OSError, UnicodeError, json.JSONDecodeError) as exc:
                unreadable_prior.append({'path': str(path), 'error': type(exc).__name__, 'not_claimed_as_validated': True})
                continue
            if audit.get('status') != 'PASS':
                continue
            tokens = {value for row in audit.get('results', []) for value in row.get('token_sha256', [])}
            self.prior_tokens.update(tokens)
            self.inputs[str(path)] = sha(path)
            prior.append({'path': str(path), 'sha256': sha(path), 'tokens': len(tokens)})
        write_new(self.base / 'input_manifest.json', {'input_sha256': self.inputs, 'prior_token_audits': prior,
            'unreadable_prior_audits_not_covered': unreadable_prior,
            'prior_raw_initial_sessions': self.prior_sessions, 'unreadable_initial_records_not_covered': unreadable_initial,
            'prior_scope': 'Every readable initial raw token plus every PASS combined-audit token chain; unreadable/unknown tails are not claimed covered.',
            'prior_tokens': len(self.prior_tokens), 'models': self.spec['models'], 'schedule': protocol.schedule()})
        commands = [{'session': row, 'command': [sys.executable, '-u', *protocol.session_command(row, self.base, self.runtime)]}
                    for row in protocol.schedule()]
        write_new(self.base / 'session_commands.json', commands)
        self.log('--artifact', str(self.base / 'input_manifest.json'), '--artifact', str(self.base / 'session_commands.json'))
        self.verify_inputs()
        argv = [sys.executable, '-B', '-m', 'pytest', '-q', str(HERE / 'test_run_pair.py'),
                str(HERE / 'test_pair_protocol.py'), f'--junitxml={self.base / "prerun_tests.xml"}']
        self.wait_jobs([self.launch(argv, 'offline_prerun_tests', self.base / 'prerun_tests_stdout.log')])
        self.verify_inputs()
        self.log('--artifact', str(self.base / 'prerun_tests.xml'), '--metric', 'offline_tests_passed_before_first_request=true')

    def launch(self, argv, role, output_path, **extra):
        self.record(argv)
        handle = Path(output_path).open('x', encoding='utf-8')
        self.handles.append(handle)
        child = subprocess.Popen(argv, cwd=ROOT, stdout=handle, stderr=subprocess.STDOUT,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        row = {'role': role, 'pid': child.pid, 'create_time': psutil.Process(child.pid).create_time(),
               'command': argv, 'exit_code': None, **extra}
        self.children.append((child, row))
        self.execution['children'].append(row)
        atomic_json(self.base / 'execution.json', self.execution)
        return child, row, handle

    def wait_jobs(self, jobs):
        while any(child.poll() is None for child, _, _ in jobs):
            for child, row, _ in jobs:
                row['exit_code'] = child.poll()
            self.tick()
            time.sleep(2)
        for child, row, handle in jobs:
            row['exit_code'] = child.wait()
            handle.close()
        self.tick(force=True)
        protocol.require(all(row['exit_code'] == 0 for _, row, _ in jobs), 'failed job; preserve without replacement')

    def audit_job(self, script, extra, output):
        self.execution['status'] = f'AUDITING_{output.stem}'
        job = self.launch([sys.executable, '-u', str(script), *extra], output.stem, output)
        self.wait_jobs([job])

    def run(self):
        success = False
        try:
            self.prepare()
            for wave in range(protocol.WAVES):
                self.verify_inputs()
                self.execution['status'] = f'RUNNING_WAVE_{wave}'
                wave_info = {'wave': wave, 'started_at': datetime.now(timezone.utc).isoformat(), 'finished_at': None}
                self.execution['waves'].append(wave_info)
                jobs = []
                for item in (row for row in protocol.schedule() if row['wave'] == wave):
                    argv = [sys.executable, '-u', *protocol.session_command(item, self.base, self.runtime)]
                    jobs.append(self.launch(argv, item['session_id'], self.base / f'{item["arm"]}_s{item["index"]:02d}_stdout.log',
                                            arm=item['arm'], wave=wave, session_index=item['index']))
                self.wait_jobs(jobs)
                protocol.require(self.last_count == (wave + 1) * 20000, 'incomplete fixed wave; no later wave')
                wave_info['finished_at'] = datetime.now(timezone.utc).isoformat()
                self.tick(force=True)
            self.verify_inputs()
            audits, independence = {}, {}
            for arm in protocol.ARMS:
                directories = [self.base / 'sessions' / arm / f's{index:02d}' for index in range(1, 17)]
                args = ['--model', str(self.base / 'frozen' / f'{arm}.pt'), '--observation-bridge', 'legacy-v4']
                args += [arg for path in directories for arg in ('--session-dir', str(path))]
                output = self.base / f'{arm}_combined_audit.json'
                self.audit_job(self.runtime / 'alpha_holdem/audit_slumbot_v6_session.py', args, output)
                audits[arm] = read(output)
                # Single-model invariant is retained; mixed-model checks are separate.
                output = self.base / f'{arm}_independence_audit.json'
                args = [arg for path in directories for arg in ('--session-dir', str(path))] + ['--out-json', str(output)]
                self.audit_job(self.runtime / 'alpha_holdem/audit_journaled_slumbot_independence.py', args,
                               self.base / f'{arm}_independence_stdout.log')
                independence[arm] = read(output)
                protocol.require(independence[arm]['status'] == 'PASS' and independence[arm]['hands'] == 40000 and
                                 independence[arm]['sessions'] == 16, 'session stream audit failed')
            cross = verify_audits(audits, self.models, self.prior_tokens)
            groups, seats, streams = parse_raw(self.base, self.models)
            for arm in protocol.ARMS:
                by_id = {row['session_id']: row for row in audits[arm]['results']}
                items = [row for row in protocol.schedule() if row['arm'] == arm]
                protocol.require(all(sum(chips) == by_id[item['session_id']]['cumulative_chips'] for item, chips in zip(items, groups[arm])),
                                 'raw reward differs from replay audit')
            self.verify_inputs()
            write_new(self.base / 'completed_analysis.json', {'status': 'COMPLETED_PENDING_REVIEW',
                'statistics': protocol.summarize_pair(groups, evidence_valid=True), 'seat_analysis': seat_report(seats),
                'cross_arm_token_audit': cross, 'cross_arm_visible_stream_audit': streams,
                'independence': independence, 'models': self.spec['models'],
                'evaluation_hands': 80000, 'slumbot_hands': 80000, 'new_training_hands': 0,
                'goal_achieved': False, 'automatic_final_test_authorized': False,
                'decision': 'EXTERNAL_DEVELOPMENT_COMPARISON_RESEARCH_REVIEW_REQUIRED'})
            success = True
        except BaseException as exc:
            write_new(self.base / 'failure.json', {'error': repr(exc), 'traceback': traceback.format_exc(),
                'automatic_retry': False, 'no_new_waves_authorized': True})
        finally:
            for child, row in self.children:
                if child.poll() is None:
                    row['exit_code'] = child.wait()
                else:
                    row['exit_code'] = child.returncode
            for handle in self.handles:
                if not handle.closed:
                    handle.close()
            try:
                self.last_count = self.counter.refresh()
            except Exception as exc:
                success = False
                self.last_count = sum(self.counter.counts.values())
                write_new(self.base / 'accounting_error.json', {'error': repr(exc), 'count_is_verified_lower_bound': True})
            self.execution.update(status='COMPLETED_PENDING_REVIEW' if success else 'FAILED_PRESERVED',
                finished_at=datetime.now(timezone.utc).isoformat(), evaluation_hands=self.last_count,
                slumbot_hands=self.last_count, wall_time_seconds=time.monotonic() - self.started)
            atomic_json(self.base / 'execution.json', self.execution)
            self.log('--count', 'new_training_hands=0', '--count', f'evaluation_hands={self.last_count}',
                '--count', f'slumbot_hands={self.last_count}', '--metric', f'wall_time_seconds={self.execution["wall_time_seconds"]}')
            artifacts = [path for path in self.base.rglob('*') if path.is_file() and '__pycache__' not in path.parts
                         and path.name != 'experiment.json']
            for start in range(0, len(artifacts), 12):
                self.log(*[arg for path in artifacts[start:start + 12] for arg in ('--artifact', str(path))])
            print(json.dumps({'status': self.execution['status'], 'durable_raw_hands': self.last_count}), flush=True)
        if not success:
            raise SystemExit(1)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--experiment-dir', type=Path, required=True)
    parser.add_argument('--preflight-only', action='store_true')
    args = parser.parse_args()
    if args.preflight_only:
        preflight(args.experiment_dir)
        print(json.dumps({'preflight_passed': True, 'network_requests': 0, 'new_hands': 0}))
    else:
        Runner(args.experiment_dir).run()
