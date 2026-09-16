"""Post-terminal evidence review. Never reads current results before all sessions end."""
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import psutil
import protocol as p
from run_external import read, sha, write, check, validate_summary

BASE = p.BASE


def terminal_ready():
    owner = read(BASE / 'execution/owner.json')
    try:
        proc = psutil.Process(owner['pid'])
        p.require(abs(proc.create_time()-owner['create_time']) > .001, 'Controller still owns evidence')
    except psutil.NoSuchProcess:
        pass
    terminal = read(BASE / 'execution/terminal.json')
    p.require(terminal['status'] == 'EVALUATION_COMPLETE_PENDING_AUDIT' and terminal['external_hands'] == 80000,
              'Incomplete fixed evaluation')
    p.require(not (BASE / 'execution/failure.json').exists(), 'Execution failure requires separate review')
    for item in p.schedule():
        job = BASE / 'execution' / item['session_id']
        identity = read(job / 'process.json')
        try:
            proc = psutil.Process(identity['pid'])
            p.require(abs(proc.create_time()-identity['create_time']) > .001, 'Session process still live')
        except psutil.NoSuchProcess:
            pass
        p.require(read(job / 'terminal.json')['exit_code'] == 0, 'Failed child')


def verify_audits(audits, prior_tokens):
    seen = set(prior_tokens)
    decisions = 0
    for arm in p.ARMS:
        audit = audits[arm]
        p.require(audit['status'] == 'PASS' and audit['sessions'] == 8 and audit['successful_hands'] == 20000,
                  'Incomplete arm replay')
        expected = {r['session_id']:r for r in p.schedule() if r['arm'] == arm}
        rows = audit['results']
        p.require(len(rows) == 8 and {r['session_id'] for r in rows} == set(expected), 'Replay session mismatch')
        for row in rows:
            item = expected[row['session_id']]
            p.require(row['status'] == 'PASS' and row['model_sha256'] == p.MODEL_HASHES[arm] and
                      row['policy_seed'] == item['policy_seed'], 'Replay identity mismatch')
            p.require(row['successful_hands'] == row['attempted_hands'] == row['target_hands'] == 2500,
                      'Incomplete replay count')
            p.require(not any(row[k] for k in ('pending_request_id','protocol_failures','committed_without_raw',
                                               'partial_journal','partial_hands')), 'Unresolved evidence')
            p.require(row['decision_replays'] == row['policy_draws_verified'] > 0, 'Missing full model replay')
            tokens = set(row['token_sha256'])
            p.require(tokens and not (tokens & seen), 'Reused token chain')
            seen.update(tokens)
            decisions += row['decision_replays']
    return dict(passed=True, decision_replays=decisions, disjoint_observed_token_chains=True,
                server_rng_independence_proven=False)


def parse_raw(audits):
    groups = {arm:[] for arm in p.ARMS}
    seats = {arm:{0:[],1:[]} for arm in p.ARMS}
    streams, files = [], {}
    for item in p.schedule():
        directory = BASE / 'sessions' / item['arm'] / f"s{item['index']:02d}"
        summary = read(directory / 'summary.json')
        validate_summary(summary, item)
        for name in ('hands.jsonl','journal.jsonl'):
            p.require(sha(directory / name) == summary[name.split('.')[0]+'_sha256'], 'Evidence hash mismatch')
        chips, visible, seat_values = [], [], {0:[],1:[]}
        with (directory / 'hands.jsonl').open() as f:
            for index, line in enumerate(f,1):
                p.require(line.endswith('\n'), 'Partial raw line')
                row = json.loads(line)
                p.require(row['successful_hand'] == row['attempted_hand'] == index and
                    row['session_id'] == item['session_id'] and row['policy_seed'] == item['policy_seed'] and
                    row['model_sha256'] == p.MODEL_HASHES[item['arm']], 'Raw identity mismatch')
                p.require(row['strict_policy_execution'] and row['policy_mode'] == 'sample' and
                    row['policy_temperature'] == 1 and row['terminal_validation']['status'] == 'PASS' and
                    row['winnings_bb'] == row['winnings_chips']/100, 'Wrong raw execution or reward')
                for decision in row['decisions']:
                    p.validate_decision(decision)
                terminal = row['terminal_response']
                seat = terminal['client_pos']
                p.require(type(seat) is int and seat in (0,1), 'Invalid seat')
                chips.append(row['winnings_chips'])
                seat_values[seat].append(row['winnings_chips'])
                visible.append((seat, tuple(sorted(terminal['hole_cards']))))
        p.require(len(chips) == 2500, 'Raw session incomplete')
        replay = next(r for r in audits[item['arm']]['results'] if r['session_id'] == item['session_id'])
        p.require(sum(chips) == replay['cumulative_chips'] == summary['cumulative_chips'], 'Replay reward disagreement')
        groups[item['arm']].append(chips)
        for seat in (0,1):
            p.require(len(seat_values[seat]) > 1, 'Missing seat')
            seats[item['arm']][seat].extend(seat_values[seat])
        streams.append((item['session_id'], visible))
        files.update({str(f):sha(f) for f in directory.glob('*') if f.is_file()})
    worst = 0
    for i, (_, left) in enumerate(streams):
        for _, right in streams[i+1:]:
            rate = sum(a == b for a,b in zip(left,right))/2500
            worst = max(worst, rate)
            p.require(rate < .05, 'Suspiciously shared visible stream')
    return groups, seats, files, worst


def main():
    terminal_ready()
    manifest = read(BASE / 'frozen_manifest.json')
    check(manifest['inputs'])
    started = time.monotonic()
    out = BASE / 'post_review'
    out.mkdir(exist_ok=False)
    runtime = BASE / 'runtime'
    env = dict(os.environ, PYTHONPATH=str(runtime), PYTHONDONTWRITEBYTECODE='1',
               OMP_NUM_THREADS='1', MKL_NUM_THREADS='1', OPENBLAS_NUM_THREADS='1')
    audits = {}
    for arm in p.ARMS:
        argv = [sys.executable,'-B',str(BASE / 'audit_sampled.py'), '--model',str(BASE / 'frozen' / (arm+'.pt')),
                '--observation-bridge','legacy-v4']
        for i in range(1,9):
            argv += ['--session-dir',str(BASE / 'sessions' / arm / f's{i:02d}')]
        with (out / (arm+'_combined_audit.json')).open('xb') as stdout, (out / (arm+'_stderr.log')).open('xb') as stderr:
            result = subprocess.run(argv,cwd=p.ROOT,env=env,stdout=stdout,stderr=stderr)
        write(out / (arm+'_command.json'),dict(argv=argv,exact_command=subprocess.list2cmdline(argv),exit_code=result.returncode))
        p.require(result.returncode == 0, 'Full replay failed; preserve review')
        audits[arm] = read(out / (arm+'_combined_audit.json'))
        print('Full replay complete: '+arm,flush=True)
    cross = verify_audits(audits, manifest['prior_tokens'])
    groups,seats,hashes,worst = parse_raw(audits)
    import statistics
    seat_report = {arm:{seat:dict(hands=len(v),bb_per_100=statistics.mean(v)) for seat,v in values.items()}
                   for arm,values in seats.items()}
    check(manifest['inputs'])
    write(out / 'result.json',dict(passed=True, statistics=p.summarize(groups,evidence_valid=True),
        seat_descriptive=seat_report,cross_token_audit=cross,worst_same_index_visible_match_rate=worst,
        raw_hashes=hashes,external_hands=80000,training_hands=0,final_acceptance_hands=0,
        wall_seconds=time.monotonic()-started,unreadable_prior=manifest['unreadable_prior'],
        reviewer_sha256=sha(Path(__file__)),goal_achieved=False))


if __name__ == '__main__':
    main()
