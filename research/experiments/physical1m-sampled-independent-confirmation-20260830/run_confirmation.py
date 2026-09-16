"""Fixed sampled-policy replication; preserve completed cells on explicit resume."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import shutil
import statistics
import subprocess
import sys

import psutil

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from research.experiment_log import capture_code_provenance

BASE = Path(__file__).resolve().parent
ID = BASE.name
SEED = 20260894
PAIRS = 8192
MODE = 'sampled_both_sides'
RNG = 'sha256_seed_pair_physical_seat_decision_v1'
PARENT = ROOT / 'research/experiments/physical-budget-1m-learning-curve-20260830'
ANCHORS = [
    ('standard10', ROOT / 'models/baseline/standard10/latest.pt',
     '91b0c587a5a76e9a8f38217e0b304136ef298118a99b69cc743899fc4b16e428'),
    ('slumbot_free', Path('C:/Users/a8594/CardPilot_legacy_20260829/selected_assets/opponents/slumbot_free_anchor_position10m.pt'),
     '457d3babb82cb8014a2b7c378b2b5f916962565e63a44d192d5d7acd8393d6e7'),
    ('corrected_cfr96', Path('C:/Users/a8594/CardPilot_legacy_20260829/selected_assets/opponents/corrected_cfr96_anchor10.pt'),
     '902a7049ca66c0552246d11fe482eed4df47ac5c675ddf051c34ed86dcf213a6'),
]
CANDIDATES = [
    ('control', ANCHORS[0][1], ANCHORS[0][2]),
    ('final', PARENT / 'frozen/final.pt',
     'ddab8c71090a78346bbd9b2b425fd3676a2d6c1cd30e649fa95aab1ff06fa7a3'),
]


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def log(*args):
    subprocess.run([sys.executable, 'research/experiment_log.py', 'update', ID, *map(str, args)],
                   cwd=ROOT, check=True)


def validate_cell(doc, execution, candidate_sha, pairs=PAIRS):
    for key, value in [('seed', SEED), ('pairs', pairs), ('starting_stack', 200.0),
                       ('policy_mode', MODE), ('action_rng_schema', RNG)]:
        if doc.get(key) != value:
            raise ValueError(f'Cell configuration mismatch: {key}')
    if execution.get('status') != 'COMPLETED' or doc['execution'].get('status') != 'COMPLETED':
        raise ValueError('Incomplete execution')
    if doc['candidate']['sha256'] != candidate_sha or len(doc['anchors']) != 3:
        raise ValueError('Wrong candidate identity or anchor count')
    for index, (row, (name, _, digest)) in enumerate(zip(doc['anchors'], ANCHORS)):
        if (row['anchor'], row['anchor_sha256']) != (name, digest):
            raise ValueError('Wrong anchor identity/order')
        if row.get('action_rng') != {'schema': RNG, 'seed': SEED + index * 1000003}:
            raise ValueError('Wrong physical action random stream')
        if row['pairs'] != pairs or row['hands'] != 2*pairs:
            raise ValueError('Wrong evidence count')
        values = row['paired_outcomes']
        keys = ['overall_bb_per_hand', 'bb_bb_per_hand', 'sb_bb_per_hand']
        if any(len(values[key]) != pairs for key in keys):
            raise ValueError('Incomplete pair evidence')
        for overall, bb, sb in zip(*(values[key] for key in keys)):
            if not all(math.isfinite(v) and abs(v) <= 200 for v in [overall, bb, sb]):
                raise ValueError('Nonfinite or out-of-stack outcome')
            if abs(overall - (bb+sb)/2) > 1e-9:
                raise ValueError('Paired-seat arithmetic mismatch')
        if abs(statistics.mean(values[keys[0]])*100 - row['candidate_bb100']) > 1e-8:
            raise ValueError('Reported EV disagrees with raw pairs')
    return 6*pairs


def paired_stats(control, treatment):
    if len(control) != len(treatment) or len(control) < 2:
        raise ValueError('Incomplete paired comparison')
    differences = [float(t)-float(c) for c, t in zip(control, treatment)]
    if not all(math.isfinite(v) for v in differences):
        raise ValueError('Nonfinite paired comparison')
    point = statistics.mean(differences)*100
    se = statistics.stdev(differences)*100/math.sqrt(len(differences))
    z_adjusted = statistics.NormalDist().inv_cdf(1-0.05/(2*3))
    return {'pairs': len(differences), 'delta_bb100': point, 'standard_error_bb100': se,
            'ci95_half_width': 1.96*se, 'ci95_lower': point-1.96*se,
            'ci95_upper': point+1.96*se,
            'bonferroni98p333_lower': point-z_adjusted*se,
            'bonferroni98p333_upper': point+z_adjusted*se}


def classify(rows):
    valid = len(rows) == 3 and all(row['ood_valid'] for row in rows)
    all_positive = valid and all(row['delta_bb100'] > 0 for row in rows)
    nominal = all_positive and any(row['ci95_lower'] > 0 for row in rows)
    adjusted = all_positive and any(row['bonferroni98p333_lower'] > 0 for row in rows)
    return dict(all_anchors_valid=valid, all_point_estimates_positive=all_positive,
                nominal_replication_gate=nominal, multiplicity_adjusted_secondary_gate=adjusted)


def is_other_evaluation_process(info, own_pid):
    # A parent PowerShell command contains this script name too. Only a Python
    # interpreter can be an existing wrapper/evaluator, not its launching shell.
    name = (info.get('name') or '').lower()
    command = ' '.join(info.get('cmdline') or [])
    return (info['pid'] != own_pid and (name.startswith('python') or name == 'py.exe')
            and ID in command and any(script in command for script in
                                      ['run_confirmation.py', 'v5_mirror_eval.py']))


def snapshot(resume):
    dest = BASE / 'execution_code'
    if resume:
        items = json.loads((dest / 'copy_manifest.json').read_text())
        if sha(Path(__file__)) != sha(dest / 'source_files' / Path(__file__).relative_to(ROOT)):
            raise ValueError('Resume launcher changed')
    else:
        dest.mkdir(exist_ok=False)
        paths = [p.relative_to(ROOT).as_posix() for p in sorted((ROOT / 'scripts/alpha_holdem').glob('*.py'))]
        paths += [f'scripts/deep_cfr/{name}.py' for name in ['__init__', 'game_state', 'hand_eval']]
        paths += ['research/experiment_log.py', Path(__file__).relative_to(ROOT).as_posix(),
                  (BASE / 'test_confirmation.py').relative_to(ROOT).as_posix()]
        capture_code_provenance(ROOT, dest, paths)
        items = []
        for relative in paths:
            src, dst = ROOT / relative, dest / 'source_files' / relative
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            items.append({'copy': dst.relative_to(ROOT).as_posix(), 'sha256': sha(src)})
        (dest / 'copy_manifest.json').write_text(json.dumps(items, indent=2)+'\n')
    for item in items:
        if sha(ROOT / item['copy']) != item['sha256']:
            raise ValueError('Frozen source changed')
    return dest, items


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--resume-evaluation', action='store_true')
    args = parser.parse_args()
    for process in psutil.process_iter(['pid', 'name', 'cmdline']):
        if is_other_evaluation_process(process.info, psutil.Process().pid):
            raise RuntimeError('Original replication process is still live; do not race or restart')
    record = json.loads((BASE / 'experiment.json').read_text())
    parent = json.loads((PARENT / 'experiment.json').read_text())
    if record['status'] != 'RUNNING' or parent['status'] != 'COMPLETED':
        raise RuntimeError('Requires current RUNNING record and completed discovery parent')
    parent_analysis = json.loads((PARENT / 'completed_analysis.json').read_text())
    if parent_analysis['final_admitted_modes'] != ['sampled']:
        raise RuntimeError('Fixed primary-final sampled admission not established')
    for _, path, digest in [*ANCHORS, *CANDIDATES]:
        if sha(path) != digest:
            raise ValueError('Input checkpoint identity mismatch')
    frozen_code, copied_files = snapshot(args.resume_evaluation)
    log('--command', subprocess.list2cmdline(['python', str(Path(__file__).relative_to(ROOT)), *sys.argv[1:]]),
        '--metric', 'evaluation_started=1',
        *[item for filename in ['copy_manifest.json', 'source_manifest.json', 'code.patch']
          for item in ['--artifact', str((frozen_code / filename).relative_to(ROOT))]])
    script = frozen_code / 'source_files/scripts/alpha_holdem/v5_mirror_eval.py'
    documents, paths, hands = {}, {}, 0
    for label, checkpoint, digest in CANDIDATES:
        out = BASE / f'{label}.json'
        md, execution, stdout = BASE / f'{label}.md', BASE / f'{label}_execution.json', BASE / f'{label}_stdout.log'
        command = [str(script), '--candidate', str(checkpoint), '--candidate-label', f'physical1m_confirmation_{label}',
                   '--policy-mode', MODE, '--pairs', str(PAIRS), '--starting-stack', '200', '--seed', str(SEED),
                   '--include-pair-outcomes', '--device', 'cuda', '--priority', 'below-normal',
                   '--out-json', str(out), '--out-md', str(md), '--execution-json', str(execution)]
        for name, anchor, _ in ANCHORS:
            command += ['--anchor', f'{name}={anchor}']
        log('--command', subprocess.list2cmdline(['python', *command]))
        if not out.exists():
            if any(path.exists() for path in [md, execution, stdout]):
                raise RuntimeError('Partial cell preserved; inspect before any recovery')
            with stdout.open('x', encoding='utf-8') as handle:
                subprocess.run([sys.executable, *command], cwd=ROOT, stdout=handle,
                               stderr=subprocess.STDOUT, check=True)
        elif not args.resume_evaluation:
            raise RuntimeError('Existing evidence requires explicit resume; never overwrite')
        doc = json.loads(out.read_text())
        hands += validate_cell(doc, json.loads(execution.read_text()), digest)
        if sha(checkpoint) != digest:
            raise ValueError('Candidate changed during evaluation')
        documents[label], paths[label] = doc, out
        log('--count', f'evaluation_hands={hands}',
            *[item for path in [out, md, execution, stdout, checkpoint]
              for item in ['--artifact', str(path)]])
    delta_path = BASE / 'paired_delta.json'
    delta = [str(frozen_code / 'source_files/scripts/alpha_holdem/paired_mirror_treatment_delta.py'),
             '--control', str(paths['control']), '--treatment', str(paths['final']), '--out', str(delta_path)]
    log('--command', subprocess.list2cmdline(['python', *delta]))
    if not delta_path.exists():
        subprocess.run([sys.executable, *delta], cwd=ROOT, check=True)
    stored = json.loads(delta_path.read_text())
    if any(stored[name]['sha256'] != sha(paths[label]) for name, label in [('control', 'control'), ('treatment', 'final')]):
        raise ValueError('Paired delta input hash mismatch')
    rows, original_rows = [], {row['anchor']: row for row in stored['anchors']}
    for c, t in zip(documents['control']['anchors'], documents['final']['anchors']):
        row = paired_stats(c['paired_outcomes']['overall_bb_per_hand'], t['paired_outcomes']['overall_bb_per_hand'])
        original = original_rows[c['anchor']]
        for field, original_field in [('delta_bb100', 'treatment_minus_control_bb100'), ('ci95_half_width', 'paired_ci95_bb100')]:
            if not math.isclose(row[field], original[original_field], rel_tol=1e-10, abs_tol=1e-9):
                raise ValueError('Independent paired statistics disagree')
        row.update(anchor=c['anchor'], ood_valid=bool(c['anchor_ood_valid'] and t['anchor_ood_valid']))
        rows.append(row)
    for _, path, digest in [*ANCHORS, *CANDIDATES]:
        if sha(path) != digest:
            raise ValueError('Checkpoint changed during replication')
    for item in copied_files:
        if sha(ROOT / item['copy']) != item['sha256']:
            raise ValueError('Execution source changed during replication')
    assert hands == 98304
    result = dict(status='PASS', seed=SEED, evaluation_hands=hands, new_training_hands=0,
                  anchors=rows, gates=classify(rows), candidate_sha256=CANDIDATES[1][2],
                  cell_hashes={name: sha(path) for name, path in paths.items()},
                  parent_discovery_hands_excluded=147456, claim_scope='independent_internal_not_slumbot',
                  caveat='Nominal pair normal CIs; one-of-three nominal gate is not familywise significance.')
    result_path = BASE / 'replication_analysis.json'
    if result_path.exists():
        if json.loads(result_path.read_text()) != result:
            raise ValueError('Existing replication analysis differs')
    else:
        result_path.write_text(json.dumps(result, indent=2, sort_keys=True)+'\n')
    log('--artifact', str(delta_path), '--artifact', str(result_path), '--metric', 'replication_complete=1',
        '--metric', f"nominal_replication_gate={int(result['gates']['nominal_replication_gate'])}",
        '--metric', f"adjusted_secondary_gate={int(result['gates']['multiplicity_adjusted_secondary_gate'])}",
        '--note', 'Independent replication completed; source/checkpoint hashes and raw evidence audit PASS. Analyze and finish the same record before selecting any next experiment. No Slumbot success claim.')
    print(json.dumps(result['gates']))


if __name__ == '__main__':
    main()
