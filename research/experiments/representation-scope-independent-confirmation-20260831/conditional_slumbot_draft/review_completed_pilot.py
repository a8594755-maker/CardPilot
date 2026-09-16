# Conditional draft: no tests or real hands until the confirmation passes and this record is registered.
"""Independent post-completion chip-space statistics; never changes raw evidence."""
import json
import math
from pathlib import Path
import statistics

import psutil

from run_external import BASE, ROOT, DIGEST, verified_sources
from scripts.alpha_holdem.audit_slumbot_hand_evidence import sha


def chip_statistics(values):
    if len(values) < 2 or any(type(value) is not int or abs(value) > 20000 for value in values):
        raise ValueError('Invalid completed chip outcomes')
    mean = sum(values)/len(values)
    std_chips = math.sqrt(math.fsum((value-mean)**2 for value in values)/(len(values)-1))
    #100chips/bb cancels100hands: average chips/hand numerically equals bb/100.
    half_width = 1.96*std_chips/math.sqrt(len(values))
    return dict(hands=len(values), total_chips=sum(values), bb_per_100=mean,
                ci95_bb_per_100=half_width, lower_bound_bb_per_100=mean-half_width,
                upper_bound_bb_per_100=mean+half_width, std_bb_per_hand=std_chips/100)


def decision(summary):
    if summary['hands'] != 20000:
        raise ValueError('Only the complete registered pilot has a decision')
    return 'ADMIT_SEPARATE_FRESH100K' if summary['bb_per_100'] > 0 else 'SAMPLED_CANDIDATE_NONPOSITIVE'


def main():
    for process in psutil.process_iter(['pid', 'name', 'cmdline']):
        if (process.info['name'] or '').lower().startswith('python') and any(
                Path(arg).name in ['run_external.py', 'play_slumbot.py'] for arg in process.info['cmdline'] or []):
            raise RuntimeError('Wait for original external writer to exit')
    report, output = BASE/'result_summary.md', BASE/'completed_analysis.json'
    if report.exists() or output.exists():
        raise ValueError('Refusing to overwrite existing completed analysis')
    record = json.loads((BASE/'experiment.json').read_text())
    ledger = json.loads((BASE/'run_manifest.json').read_text())
    pilot = json.loads((BASE/'pilot_analysis.json').read_text())
    audit = json.loads((BASE/'strict_hand_evidence_audit.json').read_text())
    manifest = json.loads((BASE/'evidence_manifest.json').read_text())
    if (record['metrics'].get('pilot_complete') != 1 or record['accounting']['evaluation_hands'] != 20000
            or ledger['status'] != 'COMPLETED_PENDING_REVIEW' or ledger['completed_raw_hands'] != 20000
            or audit['status'] != 'PASS' or pilot['status'] != 'PASS' or pilot['goal_achieved']):
        raise ValueError('Incomplete or inconsistent terminal pilot state')
    if len(ledger['sessions']) != 8 or any(s['exit_code'] != 0 for s in ledger['sessions']):
        raise ValueError('Missing clean client exits')
    if [s['policy_seed'] for s in manifest['sessions']] != list(range(2026091401, 2026091409)):
        raise ValueError('Session seed/order differs from preregistration')
    verified_sources(json.loads((BASE/'execution_code/copy_manifest.json').read_text()), Path(manifest['policy']['checkpoint']))
    expected_execution = dict(strict_policy_execution=True, http_transport='persistent_session_no_retries_v1')
    if manifest.get('execution') != expected_execution or audit.get('execution_contract') != expected_execution:
        raise ValueError('Missing strict execution contract')
    import torch
    torch.set_num_threads(1)
    checkpoint = torch.load(manifest['policy']['checkpoint'], map_location='cpu', weights_only=False)
    expected_policy_metadata = dict(env_version='v55preflopv2v4obs', obs_version='v4',
        starting_stack_bb=200., raise_action_mapping='preflop_pot_fraction_v2', norm_layer='gn',
        separate_preflop_head=True, policy_logit_bias=None, policy_range_override=None,
        policy_context_override=None, preflop_strategy_profile=None)
    if any(checkpoint.get(key) != expected for key, expected in expected_policy_metadata.items()):
        raise ValueError('Frozen checkpoint has an unexpected policy override or deployment contract')
    for path, digest in audit['input_sha256'].items():
        if sha(Path(path)) != digest:
            raise ValueError('Evidence changed after strict audit')
    expected = {Path(s['raw_hands']).resolve() for s in manifest['sessions']}
    if expected != {p.resolve() for p in (BASE/'sessions').glob('*_hands.jsonl')}:
        raise ValueError('Unexpected or missing raw-hand file outside immutable manifest')
    chips, sessions = [], []
    for spec in manifest['sessions']:
        rows = [json.loads(line) for line in Path(spec['raw_hands']).read_text().splitlines() if line.strip()]
        if (len(rows) != 2500 or spec['requested_hands'] != 2500
                or [r['attempted_hand'] for r in rows] != list(range(1, 2501))
                or [r['successful_hand'] for r in rows] != list(range(1, 2501))):
            raise ValueError('Raw session is not2500 unique successful attempts')
        if any(r.get('strict_policy_execution') is not True or r.get('http_transport') != 'persistent_session_no_retries_v1' for r in rows):
            raise ValueError('Raw strict transport identity mismatch')
        values = [row['winnings_chips'] for row in rows]
        stats = chip_statistics(values)
        sessions.append(dict(id=spec['id'], **stats))
        chips.extend(values)
    summary = chip_statistics(chips)
    for key in ['hands', 'bb_per_100', 'ci95_bb_per_100', 'lower_bound_bb_per_100',
                'upper_bound_bb_per_100', 'std_bb_per_hand']:
        for saved in [pilot['raw'], audit['summary']]:
            if not math.isclose(summary[key], saved[key], rel_tol=1e-11, abs_tol=1e-8):
                raise ValueError('Independent chip-space statistics disagree')
    means = [row['bb_per_100'] for row in sessions]
    width = 2.3646242510102993*statistics.stdev(means)/math.sqrt(8)
    cluster = dict(df=7, point=statistics.mean(means), lower=statistics.mean(means)-width,
                   upper=statistics.mean(means)+width)
    if any(not math.isclose(value, pilot['session_mean_t95'][key], abs_tol=1e-8, rel_tol=1e-11)
           for key, value in cluster.items()):
        raise ValueError('Session-mean sensitivity interval disagrees')
    status = decision(summary)
    if pilot['admits_separate_fresh100k'] != (status == 'ADMIT_SEPARATE_FRESH100K'):
        raise ValueError('Preregistered admission branch mismatch')
    result = dict(status='PASS', decision=status, policy_sha256=DIGEST, raw=summary,
        sessions=sessions, session_mean_t95=cluster, evaluation_hands=20000,
        new_training_hands=0, goal_achieved=False, strict_audit_sha256=sha(BASE/'strict_hand_evidence_audit.json'),
        review_script_sha256=sha(Path(__file__)), input_sha256=audit['input_sha256'])
    result['verified_policy_metadata'] = expected_policy_metadata
    result['execution_contract'] = expected_execution
    lines = ['# Frozen full-network native-sampled Slumbot pilot', '', f'Decision: `{status}`.', '',
        f"Exactly20,000 fresh external hands: **{summary['bb_per_100']:+.4f}bb/100**, raw95% CI "
        f"**[{summary['lower_bound_bb_per_100']:+.4f}, {summary['upper_bound_bb_per_100']:+.4f}]**.", '',
        f"Session-mean t95 sensitivity interval(df7): [{cluster['lower']:+.4f}, {cluster['upper']:+.4f}]. "
        'This is additional sensitivity evidence,not a replacement selected for favorability.', '',
        '| Session | Fresh hands | bb/100 |', '|---|---:|---:|',
        *[f"| {row['id']} | {row['hands']} | {row['bb_per_100']:+.4f} |" for row in sessions], '',
        f'Policy: unchanged full-network final checkpoint, native sample/temp1, SHA256 `{DIGEST}`.',
        'All8original clients exited0. Strict hand/session/model/mode/seed/reward/CI/fallback/replay checks passed; '
        'the independent review recomputed aggregate CIs directly in chip units, checked all hashes and found no extra raw files.', '',
        'The original greedy20k baseline is a different policy; its hands are not pooled here and any historical comparison is not a matched causal effect. '
        'Observable deal checks cannot prove hidden-deck independence; raw normal CIs assume sufficiently independent outcomes.', '',
        'Context: native-sampled Standard10 previously scored-48.9778bb/100 on a separate20k. This is unpaired historical context, not a matched treatment effect or pooled evidence.', '',
        '## Next action', '',
        ('Preregister a separate fresh100000-hand formal test of exactly this frozen policy. Exclude all current pilot and historical hands.'
         if status == 'ADMIT_SEPARATE_FRESH100K' else
         'Do not extend this nonpositive pilot. Select the next general learned-weight experiment from the completed evidence; preserve this candidate evidence.'), '',
        '**Goal remains unachieved:**20k is below the required100k, regardless of point estimate or interval.']
    output.write_text(json.dumps(result, indent=2, sort_keys=True)+'\n')
    report.write_text('\n'.join(lines)+'\n', encoding='utf-8')
    print(json.dumps(dict(decision=status, raw=summary)))


if __name__ == '__main__':
    main()
