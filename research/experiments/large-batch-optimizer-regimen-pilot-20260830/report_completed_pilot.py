"""Post-run audit/report only. Never mutate training, evaluation, or the record."""
import json
import math
from pathlib import Path
import re
import statistics

import psutil

from evaluate import admission, compare, validate
from run_pilot import BASE, ROOT, DIGESTS, sha, verify_sources


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


def validate_steps(accounting, steps):
    if len(steps) != 10 or any(s != accounting['total_steps'] for s in steps):
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
            or analysis['status'] != 'PASS' or analysis['evaluation_hands'] != 73728
            or record['accounting']['evaluation_hands'] != 73728):
        raise ValueError('Evaluation is incomplete')
    verify_sources(json.loads((BASE / 'execution_code/copy_manifest.json').read_text()))
    documents = {}
    for name, candidate in selection.items():
        path = BASE / 'matrix' / f'{name}.json'
        doc = json.loads(path.read_text())
        validate(doc, json.loads((BASE / 'matrix' / f'{name}_execution.json').read_text()), candidate['sha256'])
        if sha(path) != analysis['cell_hashes'][name] or sha(candidate['path']) != candidate['sha256']:
            raise ValueError('Raw evidence or frozen policy changed')
        documents[name] = doc
    for label, first, second in [('large_vs_control', 'control', 'large'),
                                  ('large_vs_source', 'source', 'large'),
                                  ('control_vs_source', 'source', 'control')]:
        if compare(documents[first], documents[second]) != analysis['comparisons'][label]:
            raise ValueError('Raw paired contrast no longer matches stored statistics')
    admitted = admission(analysis['comparisons']['large_vs_control'], analysis['comparisons']['large_vs_source'])
    if admitted != analysis['admits_independent_confirmation']:
        raise ValueError('Gate mismatch')
    import torch
    torch.set_num_threads(1)
    source = torch.load(selection['source']['path'], map_location='cpu', weights_only=False)
    result = dict(status='PASS', arms={}, comparisons=analysis['comparisons'],
                  evaluation_hands=73728, slumbot_hands=0,
                  admits_independent_confirmation=admitted,
                  decision='JOINT_REGIMEN_ADMITS_CONFIRMATION' if admitted else 'JOINT_REGIMEN_NOT_ADMITTED')
    for arm, batch, initial_lr in [('control', 1024, .00003), ('large', 16384, .0003)]:
        run = BASE / arm
        audit = json.loads((BASE / f'{arm}_audit.json').read_text())
        manifest = json.loads((run / 'run_manifest.json').read_text())
        rows = [json.loads(line) for line in (run / 'h1_training_metrics.jsonl').read_text().splitlines()]
        candidate = selection[arm]
        ckpt = torch.load(candidate['path'], map_location='cpu', weights_only=False)
        physical = manifest['environment_hand_accounting']['completed_hands']
        if (audit['status'] != 'PASS' or physical < 131072 or physical != candidate['physical_hands']
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
        changes, unchanged = {}, 0
        for name, value in ckpt['model'].items():
            if not torch.isfinite(value).all():
                raise ValueError('Nonfinite model state')
            if name.startswith(('policy_head.', 'preflop_policy_head.', 'value_head.')):
                changes[name] = float(torch.linalg.vector_norm(value-source['model'][name]))
            else:
                if not torch.equal(value, source['model'][name]):
                    raise ValueError('Frozen representation changed')
                unchanged += 1
        if len(changes) != 10 or any(value <= 0 for value in changes.values()):
            raise ValueError('Expected all native head tensors to update')
        for state in ckpt['optimizer']['state'].values():
            if any(isinstance(v, torch.Tensor) and not torch.isfinite(v).all() for v in state.values()):
                raise ValueError('Nonfinite Adam state')
        steps = [float(state['step']) for state in ckpt['optimizer']['state'].values()]
        accounting = batch_accounting(rows, batch)
        validate_steps(accounting, steps)
        value_losses = rounded_value_losses((run / 'latest_train.log').read_text(), len(rows))
        config = manifest['config']
        if config['mini_batch_size'] != batch or config['lr'] != initial_lr or not config['reset_optimizer']:
            raise ValueError('Regimen is not the preregistered fresh-Adam arm')
        result['arms'][arm] = dict(physical_hands=physical, overshoot=physical-131072,
            marker_hands=manifest['total_hands'], updates=len(rows), minibatch=batch, initial_lr=initial_lr,
            final_optimizer_lrs=[group['lr'] for group in ckpt['optimizer']['param_groups']],
            batch_accounting=accounting, unchanged_representation_tensors=unchanged, head_change_l2=changes,
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
    result['limitations'] = [
        'Joint minibatch/LR regimen; neither batch nor LR is isolated causally.',
        'One training seed per arm; shared seeds do not ensure matched trajectories after policies/timing diverge.',
        'Finite physical budgets stop at PPO boundaries, with reported overshoot.',
        'Partial minibatches get one Adam update each like full minibatches; weighting differs with their sizes.',
        'The joint regimen changes critic optimization steps too. Printed value losses are descriptive training losses, not heldout critic quality or a causal explanation.',
        'Three fixed training anchors are also assessment anchors; fresh deals test these opponents, not an untouched opponent population.',
        'All-heads-only, source-KL regularization and fixed/adaptive league differ from paper-scale AlphaHoldem.',
        'Nominal one-of-three CI gate is exploratory, not familywise significance; independent confirmation required.',
        'Internal sampled results are neither Slumbot bb/100 nor a proof of general strength.']
    lines = ['# Matched optimizer-regimen pilot', '', f"Decision: `{result['decision']}`.", '',
        f"New physical training hands: {total:,}. Frozen internal evaluation: 73,728 hands. Slumbot hands: 0.", '',
        '| Arm | Physical hands | Updates | Batch / initial LR | Adam steps | Partial steps | Max source KL |',
        '|---|---:|---:|---|---:|---:|---:|']
    for name, row in result['arms'].items():
        lines.append(f"| {name} | {row['physical_hands']:,} | {row['updates']} | {row['minibatch']} / {row['initial_lr']} "
                     f"| {row['batch_accounting']['total_steps']} | {row['batch_accounting']['partial_batch_steps']} | {row['max_reference_kl']:.6f} |")
    lines += ['', 'Primary contrast: large minus matched control, bb/100; confidence intervals use mirrored pairs.', '',
        '| Anchor | Delta | 95% CI | Bonferroni 98.333% CI |', '|---|---:|---:|---:|']
    for row in result['comparisons']['large_vs_control']:
        lines.append(f"| {row['anchor']} | {row['delta_bb100']:+.4f} | [{row['ci95_lower']:+.4f}, {row['ci95_upper']:+.4f}] "
                     f"| [{row['bonferroni_lower']:+.4f}, {row['bonferroni_upper']:+.4f}] |")
    lines += ['', 'Both session audits, frozen input/source hashes, raw paired statistics, finite model/Adam state, '
              'all-head changes, unchanged shared representation, and reconstructed-versus-saved Adam steps passed.', '',
              'Limitations:', '', *['- '+value for value in result['limitations']], '',
              'Next: independently confirm the exact frozen endpoints on preregistered fresh deals before promotion.' if admitted
              else 'Do not promote or scale this regimen; select a new evidence-driven diagnostic or treatment after reviewing the contrasts and training health.', '',
              'The long-term goal remains unachieved: the same frozen policy must still complete at least100000 fresh Slumbot hands with positive bb/100 and95% CI lower bound.']
    output.write_text(json.dumps(result, indent=2, sort_keys=True)+'\n')
    report.write_text('\n'.join(lines)+'\n', encoding='utf-8')
    print(json.dumps(dict(decision=result['decision'], new_training_hands=total, evaluation_hands=73728)))


if __name__ == '__main__':
    main()
