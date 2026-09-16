"""Read-only checkpoint analysis while the unchanged external evaluator runs."""
import json
from pathlib import Path
import statistics

import torch

from report_completed_pilot import batch_accounting, rounded_value_losses, validate_steps
from run_pilot import BASE, sha


def main():
    torch.set_num_threads(1)
    output = BASE / 'training_mechanism_analysis.json'
    if output.exists():
        raise RuntimeError('Refusing to overwrite existing training analysis')
    selection = json.loads((BASE / 'checkpoint_selection.json').read_text())
    for item in selection.values():
        if sha(item['path']) != item['sha256']:
            raise ValueError('Frozen checkpoint hash changed')
    source = torch.load(selection['source']['path'], map_location='cpu', weights_only=False)['model']
    result = dict(status='PASS', new_hands_from_this_analysis=0, arms={}, delta_cosines={},
                  script_sha256=sha(__file__), input_checkpoints=selection,
                  scope='descriptive_frozen_training_mechanisms_not_strength_or_causal_inference')
    deltas = {}
    for arm, batch in [('control', 1024), ('large', 16384)]:
        run = BASE / arm
        ckpt = torch.load(selection[arm]['path'], map_location='cpu', weights_only=False)
        rows = [json.loads(line) for line in (run / 'h1_training_metrics.jsonl').read_text().splitlines()]
        audit = json.loads((BASE / f'{arm}_audit.json').read_text())
        if audit['status'] != 'PASS' or len(rows) != selection[arm]['iteration']:
            raise ValueError('Incomplete audited training evidence')
        accounting = batch_accounting(rows, batch)
        validate_steps(accounting, [float(s['step']) for s in ckpt['optimizer']['state'].values()])
        frozen = 0
        for name, tensor in ckpt['model'].items():
            if not torch.isfinite(tensor).all():
                raise ValueError('Nonfinite model state')
            if not name.startswith(('policy_head.', 'preflop_policy_head.', 'value_head.')):
                if not torch.equal(tensor, source[name]):
                    raise ValueError('Shared representation changed')
                frozen += 1
        groups = {}
        deltas[arm] = {}
        for group in ['policy_head', 'preflop_policy_head', 'value_head']:
            names = [name for name in source if name.startswith(group+'.')]
            delta = torch.cat([(ckpt['model'][name]-source[name]).flatten().double() for name in names])
            original = torch.cat([source[name].flatten().double() for name in names])
            deltas[arm][group] = delta
            groups[group] = dict(delta_l2=float(delta.norm()), source_l2=float(original.norm()),
                                 relative_delta_l2=float(delta.norm()/original.norm()))
        losses = rounded_value_losses((run / 'latest_train.log').read_text(), len(rows))
        result['arms'][arm] = dict(physical_hands=selection[arm]['physical_hands'],
            frozen_representation_tensors=frozen, groups=groups, batch_accounting=accounting,
            printed_value_losses=losses, median_printed_value_loss=statistics.median(losses),
            median_last_four_printed_value_loss=statistics.median(losses[-4:]),
            final_optimizer_lrs=[g['lr'] for g in ckpt['optimizer']['param_groups']],
            max_source_kl=audit['max_reference_policy_kl'], kl_stops=audit['kl_early_stop_count'])
    for group in deltas['control']:
        c, t = deltas['control'][group], deltas['large'][group]
        denom = float(c.norm()*t.norm())
        result['delta_cosines'][group] = float(c.dot(t))/denom if denom else None
    result['limitations'] = [
        'Parameter distance/cosine is descriptive and does not establish policy quality or functional equivalence.',
        'Both actor and critic optimization differ; data and adaptive-league trajectories also diverge.',
        'Printed value losses are rounded and collected on different on-policy data; they are not matched heldout losses.',
        'No evaluation outcomes were read or selected by this analysis; the fixed evaluation continues unchanged.']
    for item in selection.values():
        if sha(item['path']) != item['sha256']:
            raise ValueError('Input checkpoint changed during read-only analysis')
    output.write_text(json.dumps(result, indent=2, sort_keys=True)+'\n')
    print(json.dumps({key: value for key, value in result.items() if key not in ['input_checkpoints', 'arms']}))
    for name, arm in result['arms'].items():
        print(json.dumps(dict(arm=name, steps=arm['batch_accounting']['total_steps'], groups=arm['groups'],
            frozen_tensors=arm['frozen_representation_tensors'], median_value_loss=arm['median_printed_value_loss'],
            last_four_value_loss=arm['median_last_four_printed_value_loss'])))


if __name__ == '__main__':
    main()
