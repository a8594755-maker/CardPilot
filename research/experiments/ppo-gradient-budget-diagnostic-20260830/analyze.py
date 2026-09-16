"""Summarize preregistered gradient probes and hash their raw evidence."""
import hashlib
import json
import math
from pathlib import Path
import statistics

BASE = Path(__file__).resolve().parent


def summary(values):
    values = [v for v in values if v is not None]
    if not values:
        return None
    assert all(math.isfinite(v) for v in values)
    return dict(n=len(values), mean=statistics.mean(values), median=statistics.median(values),
                minimum=min(values), maximum=max(values))


def main():
    result = {'schema': 'cardpilot.ppo_gradient_budget_analysis.v1', 'cohorts': {},
              'limitations': ['First four minibatches per epoch, not a random sample of all updates.',
                              'Gradient norms are pre-Adam, not effective optimizer step sizes.',
                              'Cohorts are new short local runs, not strength evaluations.',
                              'Mature model retains Adam moments but local schedule/counters restart by design.']}
    for cohort in ['source', 'mature']:
        run = BASE / cohort
        rows = [json.loads(line) for line in (run / 'h1_training_metrics.jsonl').read_text().splitlines()]
        audit = json.loads((BASE / f'{cohort}_audit.json').read_text())
        assert audit['status'] == 'PASS'
        probes = [probe for row in rows for probe in row['gradient_diagnostics']]
        assert len(probes) == 8 * len(rows)
        assert all(p['gradient_routing'] == 'global_joint_clip' for p in probes)
        groups = {}
        for group in ['all_trainable', 'policy_head', 'preflop_policy_head', 'value_head']:
            values = [probe['groups'][group] for probe in probes]
            groups[group] = {
                'norms': {key: summary(v['norms'][key] for v in values) for key in values[0]['norms']},
                'cosines': {key: summary(v['cosines'][key] for v in values) for key in values[0]['cosines']},
                'clip_scale': summary(v['hypothetical_clip_scale'] for v in values),
                'source_to_ppo_ratio': summary(v['norms']['source_kl'] / v['norms']['ppo']
                    for v in values if v['norms']['ppo'] > 1e-12),
                'actor_to_ppo_ratio': summary(v['norms']['actor'] / v['norms']['ppo']
                    for v in values if v['norms']['ppo'] > 1e-12),
            }
        joint = [p['groups']['all_trainable'] for p in probes]
        record = {
            'physical_hands': audit['actual_environment_hands'],
            'legacy_marker_hands': audit['legacy_training_marker_hands'],
            'iterations': len(rows), 'probes': len(probes), 'groups': groups,
            'global_clip_fraction': statistics.mean(v['hypothetical_clip_scale'] < 1 for v in joint),
            'critic_exceeds_actor_fraction': statistics.mean(v['norms']['critic'] > v['norms']['actor'] for v in joint),
            'actor_below_clip_joint_above_fraction': statistics.mean(v['norms']['actor'] < 0.5 < v['norms']['total'] for v in joint),
            'max_reference_kl': audit['max_reference_policy_kl'],
            'optimizer_step_min': audit['optimizer_step_min'],
            'optimizer_step_max': audit['optimizer_step_max'],
            'hashes': {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                       for path in [run / 'latest.pt', run / 'h1_training_metrics.jsonl',
                                    run / 'run_manifest.json', run / 'opponent_assignments.jsonl']},
        }
        result['cohorts'][cohort] = record
    result['total_new_physical_hands'] = sum(c['physical_hands'] for c in result['cohorts'].values())
    path = BASE / 'gradient_analysis.json'
    if path.exists():
        raise RuntimeError('Refusing to overwrite analysis artifact')
    path.write_text(json.dumps(result, indent=2, sort_keys=True) + '\n')
    for name, c in result['cohorts'].items():
        print(json.dumps({'cohort': name, 'physical': c['physical_hands'], 'probes': c['probes'],
                          'clip_fraction': c['global_clip_fraction'],
                          'critic_exceeds_actor': c['critic_exceeds_actor_fraction'],
                          'norms': {key: value['mean'] for key, value in c['groups']['all_trainable']['norms'].items()},
                          'cosines': {key: value['mean'] if value else None for key, value in c['groups']['all_trainable']['cosines'].items()}}))


if __name__ == '__main__':
    main()
