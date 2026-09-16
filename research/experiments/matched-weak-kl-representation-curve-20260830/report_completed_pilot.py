"""Post-run audit/report only. Never mutate training, evaluation, or the record."""
import json
import math
from pathlib import Path
import re
import statistics

import psutil

from evaluate import validate, CONTRASTS, CANDIDATES
from run_pilot import BASE, ROOT, DIGESTS, sha, verify_sources, select_midpoint
from raw_cell_review import review_cell



def compare(control, treatment):
    """Independent two-pass arithmetic directly from mirrored-pair differences."""
    rows = []
    if len(control['anchors']) != 4 or len(treatment['anchors']) != 4:
        raise ValueError('Exactly four registered anchors required')
    z = statistics.NormalDist().inv_cdf(1-.05/8)
    for c, t in zip(control['anchors'], treatment['anchors']):
        if any(c[k] != t[k] for k in ['anchor', 'anchor_sha256', 'action_rng']):
            raise ValueError('Different paired anchor or random stream')
        x, y = c['paired_outcomes']['overall_bb_per_hand'], t['paired_outcomes']['overall_bb_per_hand']
        if len(x) != len(y) or len(x) < 2:
            raise ValueError('Unpaired or incomplete outcomes')
        if any(type(v) not in (int, float) or not math.isfinite(v) or abs(v) > 200 for v in [*x, *y]):
            raise ValueError('Invalid physical paired outcome')
        differences = [100*(b-a) for a, b in zip(x, y)]
        mean = math.fsum(differences)/len(differences)
        se = math.sqrt(math.fsum((v-mean)**2 for v in differences)/(len(differences)-1)/len(differences))
        rows.append(dict(anchor=c['anchor'], delta_bb100=mean, ci95_half_width=1.96*se,
            ci95_lower=mean-1.96*se, ci95_upper=mean+1.96*se,
            bonferroni_lower=mean-z*se, bonferroni_upper=mean+z*se,
            ood_valid=bool(c['anchor_ood_valid'] and t['anchor_ood_valid'])))
    return rows


def admission(primary, versus_source):
    return (len(primary) == len(versus_source) == 4
        and all(r['ood_valid'] for r in [*primary, *versus_source])
        and all(r['delta_bb100'] > 0 for r in primary)
        and sum(r['bonferroni_lower'] > 0 for r in primary) >= 2
        and any(r['anchor'] in ('standard10', 'heldout_weak') and r['bonferroni_lower'] > 0 for r in primary)
        and all(r['delta_bb100'] >= 0 for r in versus_source))


def assert_contrasts_match(actual, saved):
    if len(actual) != len(saved):
        raise ValueError('Contrast count changed')
    for a, b in zip(actual, saved):
        if set(a) != set(b) or a['anchor'] != b['anchor'] or a['ood_valid'] != b['ood_valid']:
            raise ValueError('Contrast identity/validity changed')
        for key in set(a)-{'anchor', 'ood_valid'}:
            if not math.isclose(a[key], b[key], abs_tol=1e-8, rel_tol=1e-10):
                raise ValueError('Independent raw paired statistics disagree')


def validate_training(config, rows, arm):
    if arm not in ('heads', 'full'):
        raise ValueError('Unexpected scope')
    coefficient = .01
    expected = dict(source_policy_kl_coef=coefficient, seed=20260911, worker_seed_base=2026091100,
        hands_per_iter=4096, total_environment_hands=524288, mini_batch_size=1024, lr=.00003,
        ppo_epochs=2, ppo_target_kl=.01, policy_advantage_clip=3., self_play_fraction=.25,
        all_policy_heads_only_training=(arm == 'heads'), separate_preflop_head=True, reset_optimizer=True,
        reset_hand_counter=True, starting_stack=200., fixed_training_deal_stream=True)
    if any(config.get(key) != value for key, value in expected.items()):
        raise ValueError('Preregistered training configuration differs')
    if not rows or any(r.get('reference_policy_kl_coef') != coefficient for r in rows):
        raise ValueError('Executed source-KL coefficient differs')
    for row in rows:
        if any(not isinstance(row.get(key), (int, float)) or not math.isfinite(row[key])
               for key in ['reference_policy_kl', 'approx_kl', 'clip_frac', 'entropy']):
            raise ValueError('Nonfinite or missing PPO health evidence')


def batch_accounting(rows, batch):
    """Reconstruct actual ordinary PPO steps; KL stopping is epoch-boundary only."""
    updates = []
    for expected_iteration, row in enumerate(rows, 1):
        n, epochs = row['fresh_policy_rows'], row['ppo_epochs_completed']
        if (row['iteration'] != expected_iteration or n <= 0 or epochs not in (1, 2)
                or row['ppo_replay_rows'] != 0 or row['policy_rows'] != n
                or row['value_head_catchup_enabled']):
            raise ValueError('Unsupported or incomplete ordinary all-row PPO evidence')
        full, tail = divmod(n, batch)
        updates.append(dict(iteration=expected_iteration, rows=n, epochs=epochs,
            full_batch_steps=full*epochs, partial_batch_steps=int(tail > 0)*epochs,
            partial_batch_rows=tail, total_steps=math.ceil(n/batch)*epochs))
    return dict(updates=updates, total_steps=sum(r['total_steps'] for r in updates),
                full_batch_steps=sum(r['full_batch_steps'] for r in updates),
                partial_batch_steps=sum(r['partial_batch_steps'] for r in updates),
                transition_presentations=sum(r['rows']*r['epochs'] for r in updates))


def validate_steps(accounting, steps, expected_tensors):
    if len(steps) != expected_tensors or any(s != accounting['total_steps'] for s in steps):
        raise ValueError('Fresh-Adam step counts disagree with persisted PPO evidence')


def rounded_value_losses(text, iterations):
    values = [(int(i), float(v)) for i, v in re.findall(
        r'^\[\s*(\d+)\].*?\bvloss=([0-9.eE+-]+)\s', text, flags=re.MULTILINE)]
    if [i for i, _ in values] != list(range(1, iterations+1)):
        raise ValueError('Missing or duplicate printed value-loss evidence')
    if any(not math.isfinite(v) for _, v in values):
        raise ValueError('Nonfinite value loss')
    return [v for _, v in values]


def ensure_writer_finished():
    own = psutil.Process().pid
    for process in psutil.process_iter(['pid', 'name', 'cmdline']):
        if process.pid == own or not (process.info['name'] or '').lower().startswith('python'):
            continue
        args = process.info['cmdline'] or []
        if any(Path(arg).name in ['run_pilot.py', 'evaluate.py', 'train_v5.py', 'v5_mirror_eval.py'] for arg in args):
            raise RuntimeError('Wait for the existing training/evaluation writer to exit')


def main():
    ensure_writer_finished()
    output, report = BASE / 'completed_analysis.json', BASE / 'result_summary.md'
    if output.exists() or report.exists():
        raise RuntimeError('Refusing to overwrite a completed analysis')
    record = json.loads((BASE / 'experiment.json').read_text())
    analysis = json.loads((BASE / 'pilot_analysis.json').read_text())
    selection = json.loads((BASE / 'checkpoint_selection.json').read_text())
    if (record['metrics'].get('pilot_evaluation_complete') != 1
            or analysis['status'] != 'PASS' or analysis['evaluation_hands'] != 163840
            or record['accounting']['evaluation_hands'] != 163840):
        raise ValueError('Evaluation is incomplete')
    verify_sources(json.loads((BASE / 'execution_code/copy_manifest.json').read_text()))
    documents, cell_reviews = {}, {}
    if set(selection) != set(CANDIDATES):
        raise ValueError('Unexpected curve candidate selection')
    for name, candidate in selection.items():
        path = BASE / 'matrix' / f'{name}.json'
        doc = json.loads(path.read_text())
        validate(doc, json.loads((BASE / 'matrix' / f'{name}_execution.json').read_text()), candidate['sha256'])
        cell_reviews[name] = review_cell(doc)
        if sha(path) != analysis['cell_hashes'][name] or sha(candidate['path']) != candidate['sha256']:
            raise ValueError('Raw evidence or frozen policy changed')
        documents[name] = doc
    for label, first, second in CONTRASTS:
        independent = compare(documents[first], documents[second])
        assert_contrasts_match(independent, analysis['comparisons'][label])
    admitted = admission(analysis['comparisons']['full_final_vs_heads_final'], analysis['comparisons']['full_final_vs_source'])
    if admitted != analysis['admits_independent_confirmation']:
        raise ValueError('Gate mismatch')
    import torch
    torch.set_num_threads(1)
    source = torch.load(selection['source']['path'], map_location='cpu', weights_only=False)
    result = dict(status='PASS', arms={}, comparisons=analysis['comparisons'], cell_reviews=cell_reviews,
                  evaluation_hands=163840, slumbot_hands=0,
                  admits_independent_confirmation=admitted,
                  decision='REPRESENTATION_SCOPE_ADMITS_CONFIRMATION' if admitted else 'REPRESENTATION_SCOPE_NOT_ADMITTED')
    for arm, batch, initial_lr in [('heads', 1024, .00003), ('full', 1024, .00003)]:
        run = BASE / arm
        audit = json.loads((BASE / f'{arm}_audit.json').read_text())
        manifest = json.loads((run / 'run_manifest.json').read_text())
        rows = [json.loads(line) for line in (run / 'h1_training_metrics.jsonl').read_text().splitlines()]
        candidate = selection[f'{arm}_final']
        ckpt = torch.load(candidate['path'], map_location='cpu', weights_only=False)
        physical = manifest['environment_hand_accounting']['completed_hands']
        if (audit['status'] != 'PASS' or physical < 524288 or physical != candidate['physical_hands']
                or len(rows) != manifest['iteration'] or ckpt['iteration'] != manifest['iteration']
                or ckpt['total_hands'] != manifest['total_hands']
                or not manifest['environment_hand_accounting']['prefix_complete']
                or sha(candidate['path']) != sha(run / 'latest.pt')):
            raise ValueError('Training endpoint/session mismatch')
        integrity_paths = dict(assignments=run/'opponent_assignments.jsonl', checkpoint=run/'latest.pt',
            manifest=run/'run_manifest.json', metrics=run/'h1_training_metrics.jsonl', train_log=run/'latest_train.log')
        for label, path in integrity_paths.items():
            if sha(path) != audit['artifact_integrity'][label]['sha256']:
                raise ValueError('A session artifact changed after its audit')
        if list(ckpt['model']) != list(source['model']):
            raise ValueError('Unexpected model architecture change')
        changes, representation_changes, unchanged = {}, {}, 0
        for name, value in ckpt['model'].items():
            if not torch.isfinite(value).all():
                raise ValueError('Nonfinite model state')
            if name.startswith(('policy_head.', 'preflop_policy_head.', 'value_head.')):
                changes[name] = float(torch.linalg.vector_norm(value-source['model'][name]))
            else:
                moved = not torch.equal(value, source['model'][name])
                if arm == 'heads' and moved:
                    raise ValueError('Frozen representation changed')
                representation_changes[name] = float(torch.linalg.vector_norm(value-source['model'][name]))
                unchanged += int(not moved)
        if (len(changes) != 10 or len(representation_changes) != 76
                or unchanged != (76 if arm == 'heads' else 0)
                or any(value <= 0 for value in changes.values())):
            raise ValueError('Expected all native head tensors to update')
        for state in ckpt['optimizer']['state'].values():
            if any(isinstance(v, torch.Tensor) and not torch.isfinite(v).all() for v in state.values()):
                raise ValueError('Nonfinite Adam state')
        steps = [float(state['step']) for state in ckpt['optimizer']['state'].values()]
        accounting = batch_accounting(rows, batch)
        validate_steps(accounting, steps, 10 if arm == 'heads' else 86)
        value_losses = rounded_value_losses((run / 'latest_train.log').read_text(), len(rows))
        config = manifest['config']
        coefficient = .01
        validate_training(config, rows, arm)
        if config['mini_batch_size'] != batch or config['lr'] != initial_lr or not config['reset_optimizer']:
            raise ValueError('Regimen is not the preregistered fresh-Adam arm')
        mid = selection[f'{arm}_mid']
        expected_mid = select_midpoint(run)
        mid_ckpt = torch.load(mid['path'], map_location='cpu', weights_only=False)
        if (sha(expected_mid) != mid['sha256'] or sha(mid['path']) != mid['sha256']
                or mid['physical_hands'] != mid_ckpt['environment_hand_accounting']['completed_hands']
                or mid['iteration'] != mid_ckpt['iteration']):
            raise ValueError('Curve midpoint differs from first counter-selected archive')
        if (ckpt['environment_hand_accounting']['completed_hands'] != physical
                or not ckpt['environment_hand_accounting']['prefix_complete']
                or record['metrics'].get(f'{arm}_exit_code') != 0):
            raise ValueError('Incomplete terminal checkpoint/exit evidence')
        result['arms'][arm] = dict(midpoint=mid,physical_hands=physical, overshoot=physical-524288,
            marker_hands=manifest['total_hands'], updates=len(rows), minibatch=batch, initial_lr=initial_lr,
            source_kl_coefficient=coefficient,
            final_optimizer_lrs=[group['lr'] for group in ckpt['optimizer']['param_groups']],
            batch_accounting=accounting, unchanged_representation_tensors=unchanged, head_change_l2=changes,
            representation_change_l2=representation_changes, optimizer_state_tensors=len(steps),
            kl_early_stops=sum(bool(r['kl_early_stop_triggered']) for r in rows),
            max_reference_kl=max(r['reference_policy_kl'] for r in rows),
            max_approx_kl=max(r['approx_kl'] for r in rows), max_clip_fraction=max(r['clip_frac'] for r in rows),
            entropy_first=rows[0]['entropy'], entropy_last=rows[-1]['entropy'],
            value_loss_from_six_decimal_printed_log=value_losses,
            median_marker_hands_per_second=statistics.median(r['hands_per_second'] for r in rows),
            checkpoint_sha256=candidate['sha256'])
    total = sum(v['physical_hands'] for v in result['arms'].values())
    if total != record['accounting']['new_training_hands']:
        raise ValueError('Experiment physical accounting disagrees')
    result['new_training_hands'] = total
    result['input_hashes'] = {str(BASE/'matrix'/f'{name}.json'): sha(BASE/'matrix'/f'{name}.json') for name in selection}
    result['review_script_sha256'] = sha(__file__)
    verify_sources(json.loads((BASE/'execution_code/copy_manifest.json').read_text()))
    for candidate in selection.values():
        if sha(candidate['path']) != candidate['sha256']:
            raise ValueError('Checkpoint changed during review')
    result['limitations'] = [
        'Parameter scope is the sole learning intervention; it changes both actor and critic representation gradients, not actor capacity alone.',
        'One training seed per arm; shared seeds do not ensure matched trajectories after policies/timing diverge.',
        'Finite physical budgets stop at PPO boundaries, with reported overshoot.',
        'Partial minibatches get one Adam update each like full minibatches; weighting differs with their sizes.',
        'Different trajectories can yield different update counts and training losses; these are not matched heldout critic quality.',
        'Three assessment anchors are training opponents; fourth weak policy is excluded only from this run and shares earlier source/league lineage.',
        'This fixed/adaptive league and physical budget are not a faithful paper-scale AlphaHoldem or NashPG reproduction.',
        'Admission requires two adjusted positive lower bounds including Standard10 or heldout weak, all four positive primary points, no negative source point, then independent confirmation.',
        'Internal sampled results are neither Slumbot bb/100 nor a proof of general strength.']
    result['limitations'].append('OOD validity is recomputed from aggregate decision/node counts; this is not a new per-action trace audit.')
    lines = ['# Matched weak-KL representation-scope curve', '', f"Decision: `{result['decision']}`.", '',
        'Curve checkpoints are fixed by physical counters only; only final endpoints determine admission.', '',
        f"New physical training hands: {total:,}. Frozen internal evaluation: 163,840 hands. Slumbot hands: 0.", '',
        '| Arm | Physical hands | Updates | Source-KL coefficient | Adam steps | Partial steps | Max source KL |',
        '|---|---:|---:|---|---:|---:|---:|']
    for name, row in result['arms'].items():
        lines.append(f"| {name} | {row['physical_hands']:,} | {row['updates']} | {row['source_kl_coefficient']} "
                     f"| {row['batch_accounting']['total_steps']} | {row['batch_accounting']['partial_batch_steps']} | {row['max_reference_kl']:.6f} |")
    lines += ['', 'Primary contrast: full_final minus heads_final, bb/100; confidence intervals use mirrored pairs.', '',
        '| Anchor | Delta | 95% CI | Bonferroni 98.75% CI |', '|---|---:|---:|---:|']
    for row in result['comparisons']['full_final_vs_heads_final']:
        lines.append(f"| {row['anchor']} | {row['delta_bb100']:+.4f} | [{row['ci95_lower']:+.4f}, {row['ci95_upper']:+.4f}] "
                     f"| [{row['bonferroni_lower']:+.4f}, {row['bonferroni_upper']:+.4f}] |")
    lines += ['', 'Descriptive curve versus the same original source; no midpoint promotion or optional selection:', '',
              '| Candidate | Actual physical training hands | Standard10 delta | Free delta | CFR96 delta | Heldout weak delta |',
              '|---|---:|---:|---:|---:|---:|']
    for name in ['heads_mid', 'heads_final', 'full_mid', 'full_final']:
        values = result['comparisons'][f'{name}_vs_source']
        lines.append(f"| {name} | {selection[name]['physical_hands']:,} | "
                     + ' | '.join(f"{row['delta_bb100']:+.4f}" for row in values) + ' |')
    lines += ['', 'All descriptive per-opponent paired intervals and within-arm mid-to-final contrasts are retained in completed_analysis.json; '
              'the four final full-minus-heads contrasts alone determine the primary gate.']
    lines += ['', 'Both session audits, frozen input/source hashes, raw paired statistics, finite model/Adam state, '
              'all-head changes, heads-only frozen versus full-network changed representation, and reconstructed-versus-saved Adam steps passed.', '',
              'Limitations:', '', *['- '+value for value in result['limitations']], '',
              'Next: independently confirm the exact frozen endpoints on preregistered fresh deals before promotion.' if admitted
              else 'Do not promote or scale this regimen; select a new evidence-driven diagnostic or treatment after reviewing the contrasts and training health.', '',
              'The long-term goal remains unachieved: the same frozen policy must still complete at least100000 fresh Slumbot hands with positive bb/100 and95% CI lower bound.']
    output.write_text(json.dumps(result, indent=2, sort_keys=True)+'\n')
    report.write_text('\n'.join(lines)+'\n', encoding='utf-8')
    print(json.dumps(dict(decision=result['decision'], new_training_hands=total, evaluation_hands=163840)))


if __name__ == '__main__':
    main()
