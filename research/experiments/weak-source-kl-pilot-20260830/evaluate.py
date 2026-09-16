"""Preregistered sampled final-point matrix; no optional extension or selection."""
import json
import math
from pathlib import Path
import statistics
import subprocess
import sys

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))
from run_pilot import ANCHORS, DIGESTS, ROOT, command_record, log, sha

SEED, PAIRS = 20260908, 4096
MODE, RNG = 'sampled_both_sides', 'sha256_seed_pair_physical_seat_decision_v1'
NAMES = ['standard10', 'slumbot_free', 'corrected_cfr96']


def validate(doc, execution, digest, pairs=PAIRS):
    expected = dict(seed=SEED, pairs=pairs, policy_mode=MODE, action_rng_schema=RNG, starting_stack=200.0)
    if any(doc.get(k) != v for k, v in expected.items()):
        raise ValueError('Preregistered cell configuration mismatch')
    if execution.get('status') != 'COMPLETED' or doc['execution'].get('status') != 'COMPLETED':
        raise ValueError('Incomplete execution')
    if doc['candidate']['sha256'] != digest or len(doc['anchors']) != 3:
        raise ValueError('Candidate or anchor count mismatch')
    for i, row in enumerate(doc['anchors']):
        if row['anchor'] != NAMES[i] or row['anchor_sha256'] != DIGESTS[i]:
            raise ValueError('Anchor identity/order mismatch')
        if row.get('action_rng') != dict(seed=SEED+i*1000003, schema=RNG):
            raise ValueError('Action stream identity mismatch')
        if row['pairs'] != pairs or row['hands'] != 2*pairs:
            raise ValueError('Hand count mismatch')
        outcomes = row['paired_outcomes']
        keys = ['overall_bb_per_hand', 'bb_bb_per_hand', 'sb_bb_per_hand']
        if any(len(outcomes[k]) != pairs for k in keys):
            raise ValueError('Missing raw pairs')
        for overall, bb, sb in zip(*(outcomes[k] for k in keys)):
            if not all(math.isfinite(v) and abs(v) <= 200 for v in [overall, bb, sb]) or abs(overall-(bb+sb)/2) > 1e-9:
                raise ValueError('Invalid raw seat evidence')
        if abs(statistics.mean(outcomes[keys[0]])*100-row['candidate_bb100']) > 1e-8:
            raise ValueError('Raw mean disagreement')
    return pairs*6


def compare(control, treatment):
    rows = []
    z_adjusted = statistics.NormalDist().inv_cdf(1-.05/6)
    for c, t in zip(control['anchors'], treatment['anchors']):
        if any(c[k] != t[k] for k in ['anchor', 'anchor_sha256', 'action_rng']):
            raise ValueError('Paired stream mismatch')
        first, second = c['paired_outcomes']['overall_bb_per_hand'], t['paired_outcomes']['overall_bb_per_hand']
        if len(first) != len(second) or len(first) < 2:
            raise ValueError('Incomplete paired outcomes')
        delta = [b-a for a, b in zip(first, second)]
        point, se = statistics.mean(delta)*100, statistics.stdev(delta)*100/math.sqrt(len(delta))
        rows.append(dict(anchor=c['anchor'], delta_bb100=point, ci95_half_width=1.96*se,
                         ci95_lower=point-1.96*se, ci95_upper=point+1.96*se,
                         bonferroni_lower=point-z_adjusted*se, bonferroni_upper=point+z_adjusted*se,
                         ood_valid=bool(c['anchor_ood_valid'] and t['anchor_ood_valid'])))
    return rows


def admission(primary, versus_source):
    valid = len(primary) == len(versus_source) == 3 and all(r['ood_valid'] for r in [*primary, *versus_source])
    return (valid and all(r['delta_bb100'] > 0 for r in primary)
            and any(r['bonferroni_lower'] > 0 for r in primary)
            and all(r['delta_bb100'] >= 0 for r in versus_source))


def main():
    selection = json.loads((BASE / 'checkpoint_selection.json').read_text())
    snapshot = BASE / 'execution_code/source_files/scripts/alpha_holdem'
    documents, paths, hands = {}, {}, 0
    matrix = BASE / 'matrix'
    matrix.mkdir(exist_ok=False)
    for name in ['source', 'control', 'weak']:
        candidate = selection[name]
        if sha(candidate['path']) != candidate['sha256']:
            raise ValueError('Frozen model changed')
        path, md, execution, stdout = [matrix / f'{name}{suffix}' for suffix in ['.json', '.md', '_execution.json', '_stdout.log']]
        command = [str(snapshot / 'v5_mirror_eval.py'), '--candidate', candidate['path'],
                   '--candidate-label', f'weak_batch_pilot_{name}', '--policy-mode', MODE,
                   '--pairs', str(PAIRS), '--starting-stack', '200', '--seed', str(SEED),
                   '--include-pair-outcomes', '--device', 'cuda', '--priority', 'below-normal',
                   '--out-json', str(path), '--out-md', str(md), '--execution-json', str(execution)]
        for label, anchor in zip(NAMES, ANCHORS): command += ['--anchor', f'{label}={anchor}']
        command_record(command)
        with stdout.open('x', encoding='utf-8') as output:
            subprocess.run([sys.executable, *command], cwd=ROOT, stdout=output, stderr=subprocess.STDOUT, check=True)
        doc = json.loads(path.read_text())
        hands += validate(doc, json.loads(execution.read_text()), candidate['sha256'])
        documents[name], paths[name] = doc, path
        log('--count', f'evaluation_hands={hands}',
            *[item for artifact in [path, md, execution, stdout] for item in ['--artifact', str(artifact)]])
    comparisons = {}
    for name, control, treatment in [('weak_vs_control', 'control', 'weak'),
                                     ('weak_vs_source', 'source', 'weak'),
                                     ('control_vs_source', 'source', 'control')]:
        output = matrix / f'{name}.json'
        command = [str(snapshot / 'paired_mirror_treatment_delta.py'), '--control', str(paths[control]),
                   '--treatment', str(paths[treatment]), '--out', str(output)]
        command_record(command)
        subprocess.run([sys.executable, *command], cwd=ROOT, check=True)
        rows = compare(documents[control], documents[treatment])
        old = json.loads(output.read_text())
        if old['control']['sha256'] != sha(paths[control]) or old['treatment']['sha256'] != sha(paths[treatment]):
            raise ValueError('Paired file identity mismatch')
        expected = {r['anchor']: r for r in old['anchors']}
        for row in rows:
            for key, old_key in [('delta_bb100', 'treatment_minus_control_bb100'), ('ci95_half_width', 'paired_ci95_bb100')]:
                if not math.isclose(row[key], expected[row['anchor']][old_key], abs_tol=1e-9, rel_tol=1e-10):
                    raise ValueError('Independent paired CI recomputation disagrees')
        comparisons[name] = rows
        log('--artifact', str(output))
    admitted = admission(comparisons['weak_vs_control'], comparisons['weak_vs_source'])
    assert hands == 73728
    for candidate in selection.values():
        if sha(candidate['path']) != candidate['sha256']: raise ValueError('A frozen checkpoint changed')
    result = dict(status='PASS', evaluation_hands=hands, seed=SEED, comparisons=comparisons,
                  admits_independent_confirmation=admitted,
                  adjusted_secondary_gate=(admitted and any(r['bonferroni_lower'] > 0 for r in comparisons['weak_vs_control'])),
                  cell_hashes={name: sha(path) for name, path in paths.items()},
                  claim_scope='exploratory_internal_weak_source_kl_pilot_not_slumbot')
    output = BASE / 'pilot_analysis.json'
    output.write_text(json.dumps(result, indent=2, sort_keys=True)+'\n')
    log('--artifact', str(output), '--metric', 'pilot_evaluation_complete=1',
        '--metric', f'admits_independent_confirmation={int(admitted)}',
        '--note', 'Both frozen endpoints evaluated against source and matched source-KL control on independent seed. Complete raw evidence and independent CI recomputation passed. Inspect numerical/Adam health and result before finish; no claim of Slumbot success.')
    print(json.dumps({'admits_independent_confirmation': admitted, 'evaluation_hands': hands}))


if __name__ == '__main__':
    main()
