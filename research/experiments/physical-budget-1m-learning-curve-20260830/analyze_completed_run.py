"""Independently recompute complete matrix statistics and validate final weights.

Does not change checkpoints or finish the record. Run only after evaluation ends.
"""
import hashlib
import json
import math
from pathlib import Path
import statistics
import sys

import psutil

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[2]
ID = BASE.name


def sha(path):
    digest = hashlib.sha256()
    with path.open('rb') as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def paired_statistics(control, treatment):
    if len(control) != len(treatment) or len(control) < 2:
        raise ValueError('Paired data need matching lengths of at least two')
    delta = [float(t) - float(c) for c, t in zip(control, treatment)]
    if not all(math.isfinite(value) for value in delta):
        raise ValueError('Non-finite paired outcomes')
    point = statistics.mean(delta) * 100
    half_width = 1.96 * statistics.stdev(delta) * 100 / math.sqrt(len(delta))
    return dict(pairs=len(delta), delta_bb100=point, ci95_half_width=half_width,
                ci95_lower=point-half_width, ci95_upper=point+half_width)


def main():
    for process in psutil.process_iter(['pid', 'cmdline']):
        command = ' '.join(process.info['cmdline'] or [])
        if process.pid != psutil.Process().pid and ID in command and any(
            name in command for name in ['run_training.py', 'run_evaluation.py', 'v5_mirror_eval.py']
        ):
            raise RuntimeError('Active experiment writer/evaluator: wait, do not race it')
    summary = json.loads((BASE / 'matrix_summary.json').read_text())
    if summary['evaluation_hands'] != 147456:
        raise ValueError('The preregistered matrix is incomplete')
    output = BASE / 'completed_analysis.json'
    if output.exists():
        raise RuntimeError('Refusing to overwrite an existing final analysis')
    selection = json.loads((BASE / 'checkpoint_selection.json').read_text())['selected']
    audit = json.loads((BASE / 'production_audit.json').read_text())
    record = json.loads((BASE / 'experiment.json').read_text())
    if audit['status'] != 'PASS' or record['metrics'].get('discovery_matrix_complete') != 1:
        raise ValueError('Completed session audit and matrix marker required')
    if record['accounting']['evaluation_hands'] != 147456:
        raise ValueError('Experiment accounting disagrees with complete raw matrix')
    for selected in selection.values():
        if sha(ROOT / selected['evaluation_path']) != selected['sha256']:
            raise ValueError('A frozen evaluation checkpoint changed')
    production_files = {'checkpoint': 'latest.pt', 'manifest': 'run_manifest.json',
                        'metrics': 'h1_training_metrics.jsonl', 'assignments': 'opponent_assignments.jsonl',
                        'train_log': 'latest_train.log'}
    for key, filename in production_files.items():
        if sha(BASE / 'production' / filename) != audit['artifact_integrity'][key]['sha256']:
            raise ValueError('Training evidence changed after completed session audit')
    for anchor in audit['fixed_opponents']:
        if sha(Path(anchor['path'])) != anchor['sha256']:
            raise ValueError('A fixed anchor changed after training audit')
    snapshot_files = json.loads((BASE / 'evaluation_code/copy_manifest.json').read_text())
    for item in snapshot_files:
        if sha(ROOT / item['copy']) != item['sha256']:
            raise ValueError('Frozen evaluator source changed')
    matrix = {}
    for mode, count in [('greedy', 2048), ('sampled', 4096)]:
        source_path = BASE / 'matrix' / f'{mode}_source.json'
        source = json.loads(source_path.read_text())
        for label in ['early', 'mid', 'final']:
            name = f'{mode}_{label}'
            path = BASE / 'matrix' / f'{name}.json'
            if sha(path) != summary['cells'][name]['sha256']:
                raise ValueError('Matrix cell hash changed')
            if sha(source_path) != summary['cells'][f'{mode}_source']['sha256']:
                raise ValueError('Control cell hash changed')
            treatment = json.loads(path.read_text())
            paired = json.loads((BASE / 'matrix' / f'{name}_delta.json').read_text())
            if paired['control']['sha256'] != sha(source_path) or paired['treatment']['sha256'] != sha(path):
                raise ValueError('Paired delta input hash mismatch')
            for field in ['seed', 'pairs', 'starting_stack', 'policy_mode', 'action_rng_schema']:
                if source[field] != treatment[field]:
                    raise ValueError(f'Paired alignment mismatch: {field}')
            if source['pairs'] != count or source['seed'] != 20260893:
                raise ValueError('Pair budget or seed differs from preregistration')
            if treatment['candidate']['sha256'] != selection[label]['sha256']:
                raise ValueError('Treatment identity mismatch')
            anchors = []
            old_by_anchor = {row['anchor']: row for row in paired['anchors']}
            for c, t in zip(source['anchors'], treatment['anchors']):
                for field in ['anchor', 'anchor_sha256', 'action_rng']:
                    if c[field] != t[field]:
                        raise ValueError(f'Anchor alignment mismatch: {field}')
                stats = paired_statistics(c['paired_outcomes']['overall_bb_per_hand'],
                                          t['paired_outcomes']['overall_bb_per_hand'])
                if stats['pairs'] != count:
                    raise ValueError('Incomplete pair evidence')
                old = old_by_anchor[c['anchor']]
                for key, old_key in [('delta_bb100', 'treatment_minus_control_bb100'),
                                     ('ci95_half_width', 'paired_ci95_bb100'),
                                     ('ci95_lower', 'paired_ci95_lower_bb100')]:
                    if not math.isclose(stats[key], old[old_key], rel_tol=1e-10, abs_tol=1e-9):
                        raise ValueError('Independent CI recomputation disagrees')
                stats.update(anchor=c['anchor'], control_bb100=c['candidate_bb100'],
                             candidate_bb100=t['candidate_bb100'],
                             ood_valid=bool(c['anchor_ood_valid'] and t['anchor_ood_valid']))
                anchors.append(stats)
            eligible = (len(anchors) == 3 and all(r['ood_valid'] and r['delta_bb100'] > 0 for r in anchors)
                        and any(r['ci95_lower'] > 0 for r in anchors))
            if eligible != summary['cells'][name]['admits_independent_confirmation']:
                raise ValueError('Admission recomputation mismatch')
            matrix[name] = dict(anchors=anchors, admits_independent_confirmation=eligible,
                                primary_endpoint=(label == 'final'),
                                physical_training_hands=selection[label]['physical_hands'])
    import torch
    torch.set_num_threads(1)
    source = torch.load(ROOT / selection['source']['evaluation_path'], map_location='cpu', weights_only=False)
    final = torch.load(ROOT / selection['final']['evaluation_path'], map_location='cpu', weights_only=False)
    heads = ('policy_head.', 'preflop_policy_head.', 'value_head.')
    frozen = [name for name in source['model'] if not name.startswith(heads)]
    if len(frozen) != 76 or not all(torch.equal(source['model'][name], final['model'][name]) for name in frozen):
        raise ValueError('Final frozen representation changed')
    if not all(torch.isfinite(value).all() for value in final['model'].values()):
        raise ValueError('Non-finite final weights')
    changed = [name for name in final['model'] if name.startswith(heads) and
               (name not in source['model'] or not torch.equal(source['model'][name], final['model'][name]))]
    if not all(any(name.startswith(prefix) for name in changed) for prefix in heads):
        raise ValueError('Missing learned updates in one head')
    accounting = final['environment_hand_accounting']
    if accounting['completed_hands'] != audit['actual_environment_hands'] or not accounting['prefix_complete']:
        raise ValueError('Final physical accounting mismatch')
    final_admitted = [mode for mode in ['greedy', 'sampled']
                      if matrix[f'{mode}_final']['admits_independent_confirmation']]
    earlier_admitted = [key for key, row in matrix.items()
                        if not row['primary_endpoint'] and row['admits_independent_confirmation']]
    decision = ('FINAL_ENDPOINT_ADMITS_INDEPENDENT_CONFIRMATION' if final_admitted else
                'EARLIER_ONLY_SIGNAL_REQUIRES_INDEPENDENT_CONFIRMATION' if earlier_admitted else
                'NO_GENERAL_GAIN_ADMISSION_AFTER_1M_PHYSICAL_HANDS')
    result = dict(status='PASS', decision=decision, final_admitted_modes=final_admitted,
                  earlier_admitted_cells=earlier_admitted, matrix=matrix,
                  physical_training_hands=accounting['completed_hands'],
                  legacy_marker_hands=final['total_hands'], evaluation_hands=147456,
                  frozen_tensors_unchanged=len(frozen), changed_head_tensors=changed,
                  final_checkpoint_sha256=selection['final']['sha256'],
                  matrix_summary_sha256=sha(BASE / 'matrix_summary.json'),
                  frozen_evaluation_source_files_verified=len(snapshot_files),
                  production_artifact_hashes_verified=len(production_files),
                  claim_scope='exploratory_internal_only_not_slumbot',
                  statistical_caveat='Nominal pair-level normal CIs; multi-checkpoint/mode admission is not confirmatory significance.')
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + '\n')
    lines = ['# One-million physical-hand learning curve', '', f'Decision: `{decision}`.', '',
             f"Measured training: **{accounting['completed_hands']:,} physical hands**, {final['iteration']} updates. "
             f"Legacy transition-bearing markers: {final['total_hands']:,}. Frozen internal evaluation:147456hands; no new Slumbot hands.", '',
             '| Checkpoint/mode | Physical training hands | Standard10 delta | Slumbot-free delta | CFR96 delta | Confirmation admission |',
             '|---|---:|---:|---:|---:|---|']
    for name, row in matrix.items():
        by_name = {r['anchor']: r for r in row['anchors']}
        values = [f"{by_name[a]['delta_bb100']:+.3f} +/- {by_name[a]['ci95_half_width']:.3f}"
                  for a in ['standard10', 'slumbot_free', 'corrected_cfr96']]
        lines.append(f"| {name} | {row['physical_training_hands']:,} | {' | '.join(values)} | {row['admits_independent_confirmation']} |")
    lines += ['', 'Deltas are matched treatment-minus-Standard10-control bb/100 with nominal95% pair CI half-width. ',
              'Controls share deck and (when sampled) action random streams. The final endpoint is primary; early/mid checkpoints are exploratory.', '',
              'Integrity: independent standard-library CI recomputation agrees with stored paired results; selected model and raw matrix hashes match;76 frozen tensors unchanged; all policy/value heads changed by finite updates. See completed_analysis.json and production_audit.json.', '',
              'No internal admission establishes Slumbot strength, Nash convergence, or low exploitability. Any admitted cell requires a separately preregistered independent confirmation. If no cell is admitted, do not scale this unchanged configuration or promote its checkpoints to a100k Slumbot test. The result does not falsify the AlphaHoldem paper: batch size, update scope, regularization and league differ.', '',
              'Goal remains unachieved: one frozen policy must still pass at least100000 fresh Slumbot hands above0bb/100 with positive95% CI lower bound.']
    (BASE / 'result_summary.md').write_text('\n'.join(lines) + '\n')
    print(json.dumps({key:result[key] for key in ['status','decision','final_admitted_modes','earlier_admitted_cells']}))


if __name__ == '__main__':
    main()
