"""Recompute noise metrics from retained Gram matrices and audit optimizer lineage."""
import hashlib
import json
import math
from pathlib import Path
import statistics
import sys

ROOT = Path(__file__).resolve().parents[3]
BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from scripts.alpha_holdem.ppo_hand_gradient_noise import summarize_gram


def main():
    import torch
    torch.set_num_threads(1)
    out = BASE / 'gradient_noise_analysis.json'
    if out.exists():
        raise RuntimeError('Refusing to overwrite an existing analysis')
    result = dict(schema='cardpilot.hand_gradient_noise_analysis.v1', cohorts={})
    for cohort in ['source', 'mature']:
        run = BASE / cohort
        audit = json.loads((BASE / f'{cohort}_audit.json').read_text())
        if audit['status'] != 'PASS':
            raise ValueError('Cohort session audit did not pass')
        rows = [json.loads(line) for line in (run / 'h1_training_metrics.jsonl').read_text().splitlines()]
        if len(rows) != audit['final_iteration']:
            raise ValueError('Incomplete metric stream')
        probes, summaries = [], {}
        previous_markers = 0
        for row in rows:
            probe = row['hand_gradient_noise']
            group = probe['grouping']
            if probe['schema'] != 'cardpilot.whole_hand_gradient_noise.v1' or len(group['group_hand_indices']) != 16:
                raise ValueError('Missing or incorrect hand-group probe')
            if group['input_hands'] != row['hands']-previous_markers:
                raise ValueError('Whole-hand grouping does not match fresh marker count')
            previous_markers = row['hands']
            if sum(group['hand_lengths']) != row['fresh_policy_rows']:
                raise ValueError('Hand lengths do not cover all fresh training transitions')
            metadata = {k: v for k, v in group.items() if k != 'sha256'}
            if hashlib.sha256(json.dumps(metadata, sort_keys=True).encode()).hexdigest() != group['sha256']:
                raise ValueError('Grouping provenance changed')
            for name, components in probe['groups'].items():
                for component, old in components.items():
                    rebuilt = summarize_gram(old['gram'], group['hands_per_group'])
                    for key in ['mean_gradient_squared_norm', 'group_covariance_trace', 'estimated_signal_squared_norm']:
                        if not math.isclose(rebuilt[key], old[key], abs_tol=1e-10, rel_tol=1e-8):
                            raise ValueError('Stored gradient-noise statistics disagree with Gram evidence')
                    if rebuilt['noisy_or_unresolved'] != old['noisy_or_unresolved']:
                        raise ValueError('Noise flag mismatch')
            probes.append(probe)
        for name in ['all_actor', 'policy_head', 'preflop_policy_head']:
            summaries[name] = {}
            for component in ['ppo', 'actor', 'source_kl', 'entropy']:
                stats = [probe['groups'][name][component] for probe in probes]
                ratios = [v['noise_to_signal_at_group_size'] for v in stats if v['signal_resolved']]
                cosines = [v['pairwise_cosine_mean'] for v in stats if v['pairwise_cosine_mean'] is not None]
                summaries[name][component] = dict(updates=len(stats), resolved_updates=len(ratios),
                    noisy_or_unresolved_fraction=statistics.mean(v['noisy_or_unresolved'] for v in stats),
                    median_noise_to_signal=(statistics.median(ratios) if ratios else None),
                    median_pairwise_cosine=(statistics.median(cosines) if cosines else None),
                    median_group_covariance_trace=statistics.median(v['group_covariance_trace'] for v in stats))
        checkpoint = torch.load(run / 'latest.pt', map_location='cpu', weights_only=False)
        if cohort == 'mature':
            original = torch.load(ROOT / 'research/experiments/physical-budget-1m-learning-curve-20260830/frozen/final.pt',
                                  map_location='cpu', weights_only=False)
            initial_steps = [float(s['step']) for s in original['optimizer']['state'].values()]
            steps = [float(s['step']) for s in checkpoint['optimizer']['state'].values()]
            if len(steps) != len(initial_steps) or min(steps) <= max(initial_steps):
                raise ValueError('Mature Adam lineage was reset or did not advance')
            lineage = dict(input_step_min=min(initial_steps), input_step_max=max(initial_steps),
                           output_step_min=min(steps), output_step_max=max(steps))
        else:
            lineage = {'fresh_optimizer': True, 'output_step_min': audit['optimizer_step_min']}
        result['cohorts'][cohort] = dict(physical_hands=audit['actual_environment_hands'],
            legacy_marker_hands=audit['legacy_training_marker_hands'], updates=len(rows), summaries=summaries,
            optimizer_lineage=lineage,
            group_hand_sizes=[p['grouping']['hands_per_group'] for p in probes],
            group_row_sizes=[p['grouping']['group_transition_rows'] for p in probes],
            noise_gate=summaries['all_actor']['ppo']['noisy_or_unresolved_fraction'] >= .75)
    admitted = all(row['noise_gate'] for row in result['cohorts'].values())
    result['admits_bounded_batch_treatment'] = admitted
    result['decision'] = ('WHOLE_HAND_NOISE_SUPPORTS_BOUNDED_BATCH_TREATMENT' if admitted
                          else 'WHOLE_HAND_NOISE_NOT_ESTABLISHED_IN_BOTH_COHORTS')
    result['total_new_physical_hands'] = sum(row['physical_hands'] for row in result['cohorts'].values())
    result['limitations'] = ['Pre-Adam gradients, not effective optimizer directions.',
        'Equal-hand clusters have variable transition counts; common normalization preserves transition-weighted objective.',
        'Full-batch normalized/clipped advantages and adaptive league can correlate groups. This is not a formal IID critical-batch estimate.',
        'Cohorts have different model/optimizer/league histories and fresh seeds; differences are descriptive, not a randomized causal model-age effect.',
        'Zero evaluation/Slumbot hands; no poker-strength claim.']
    out.write_text(json.dumps(result, indent=2, sort_keys=True)+'\n')
    lines = ['# Whole-hand gradient-noise diagnostic', '', f"Decision: `{result['decision']}`.", '',
             f"New measured physical training hands: {result['total_new_physical_hands']:,}. No strength-evaluation or Slumbot hands.", '',
             '| Cohort | Updates | Physical hands | PPO noisy/unresolved fraction | PPO median noise/signal | Actor median noise/signal |',
             '|---|---:|---:|---:|---:|---:|']
    for name, row in result['cohorts'].items():
        ppo, actor = row['summaries']['all_actor']['ppo'], row['summaries']['all_actor']['actor']
        lines.append(f"| {name} | {row['updates']} | {row['physical_hands']:,} | {ppo['noisy_or_unresolved_fraction']:.3f} "
                     f"| {ppo['median_noise_to_signal']} | {actor['median_noise_to_signal']} |")
    lines += ['', 'All retained Gram matrices were used to recompute the noise statistics; hand grouping/counts and both session audits passed. '
              'The mature Adam state advanced from its unchanged input; its local hand counter reset belongs only to this new diagnostic.', '',
              'Limitations:', *['- '+value for value in result['limitations']], '',
              'A positive diagnostic gate only admits a separately preregistered bounded optimizer-batch experiment, '
              'with explicit learning-rate/update-count tradeoffs and independent poker evaluation. It does not justify paper-scale training.']
    (BASE / 'result_summary.md').write_text('\n'.join(lines)+'\n')
    print(json.dumps({'decision': result['decision'], 'physical_hands': result['total_new_physical_hands']}))


if __name__ == '__main__':
    main()
