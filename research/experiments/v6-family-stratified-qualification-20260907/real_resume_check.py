"""Two real checkpoint serializations; only initial sampling weights may change."""
import copy
import importlib.util
import json
from pathlib import Path
import sys
import torch
from family_weights import bind_families, stratify
from trainer_hook import install

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE.parent / 'v6-expanded-family-pool-qualification-20260907'))
from real_parent_check import equal, sha, require

EXPECTED = {1: 'e80960428456e9f1c897bb444f256fbaec45295a6186a4251040f70029b4d3b5',
            3: '767983e4f51668f926988332b46b2fc10e45add6c578efddce9f1f6fe74ef03a'}

def main():
    torch.set_num_threads(1)
    require('--seed' in sys.argv, 'one seed per fresh process required')
    seed_arg = int(sys.argv[sys.argv.index('--seed') + 1])
    require(seed_arg in EXPECTED, 'unknown seed')
    report_path = BASE / f'real_resume_seed{seed_arg}.json'
    require(not report_path.exists(), 'preserve report')
    wrapper = BASE.parent / 'v6-opponent-execution-mixture-qualification-20260907/train_candidate.py'
    require(sha(wrapper) == '97bd808d0587e0b30573c2872d1abcaf3fe23648bf572a9df43db8cfffc2162d', 'wrapper changed')
    spec = importlib.util.spec_from_file_location('family_real_integration', wrapper)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    reports = {}
    hashes = {str(p): sha(p) for p in BASE.glob('*.py')}
    hashes[str(wrapper)] = sha(wrapper)
    trainer, binding, _ = module.install(0.)
    hook = None
    for seed in (seed_arg,):
        p = BASE.parent / 'v6-expanded-family-worker-smoke-20260907/derived' / f'seed{seed}_recent_stage2/latest.pt'
        require(sha(p) == EXPECTED[seed], 'retained root changed')
        hashes[str(p)] = EXPECTED[seed]
        parent = torch.load(p, map_location='cpu', weights_only=False)
        fixed = [s for s in parent['pool_snapshots'] if s.get('score_components', {}).get('kind') == 'initial_external_opponent']
        old_hashes = {s['score_components']['checkpoint_sha256'] for s in fixed if s['score_components'].get('admission_kind') != 'explicit_family_expansion'}
        added_hashes = {s['score_components']['checkpoint_sha256'] for s in fixed if s['score_components'].get('admission_kind') == 'explicit_family_expansion'}
        old, added = bind_families(parent['pool_snapshots'], old_hashes, added_hashes)
        ids = [s['id'] for s in parent['pool_snapshots']]
        derived = copy.deepcopy(parent)
        derived['adaptive_opponent_weights'] = stratify(parent['adaptive_opponent_weights'], ids, old, added)
        require(all(equal(parent[k], derived[k]) for k in parent if k != 'adaptive_opponent_weights'), 'nonallocation mutation')
        out = BASE / 'derived' / f'seed{seed}_recent_stage2'
        if not out.exists():
            out.mkdir(parents=True, exist_ok=False)
            with (out / 'latest.pt').open('xb') as f:
                torch.save(derived, f)
        else:
            require('--verify-existing' in sys.argv, 'existing derivation needs explicit verification mode')
        restored = torch.load(out / 'latest.pt', map_location='cpu', weights_only=False)
        require(equal(restored, derived), 'serialization changed state')
        pool = trainer.OpponentPool(k=9, strategy='anchor-latest', history_limit=200)
        pool.load_from_checkpoint(restored['pool_snapshots'], candidate_history=restored['pool_candidate_history'])
        require(pool.active_ids() == ids, 'loader reordered identities')
        if hook is None:
            hook = install(trainer, old, added)
        else:
            require(hook['original_ids'] == sorted(old) and hook['added_ids'] == sorted(added), 'seed identity differs; separate process required')
        rewards = restored['adaptive_opponent_ema_rewards']
        actual = trainer._family_hardness_weights(rewards, 1., .01, pool.active_ids())
        expected = stratify(trainer.adaptive_hardness_weights(rewards, 1., .01), ids, old, added)
        require(actual == expected, 'actual update hook differs')
        pool.add(parent['model'], hands=parent['total_hands'], iteration=parent['iteration'] + 1, selection_loss=0., score_components={})
        updated = trainer._family_hardness_weights([0.] * 9, 1., .01, pool.active_ids())
        require(abs(sum(updated) - 1) < 1e-8 and old | added <= set(pool.active_ids()), 'turnover contract')
        reports[str(seed)] = {'source': str(p), 'source_sha256': EXPECTED[seed], 'derived': str(out / 'latest.pt'),
                             'derived_sha256': sha(out / 'latest.pt'), 'iteration': parent['iteration'],
                             'physical_hands': parent['environment_hand_accounting']['completed_hands'],
                             'original_ids': sorted(old), 'added_ids': sorted(added),
                             'initial_weights': restored['adaptive_opponent_weights'], 'hook': hook,
                             'only_changed_checkpoint_field': 'adaptive_opponent_weights',
                             'all_other_fields_bitwise_preserved': True, 'serialization_roundtrip_passed': True}
        del parent, derived, restored, pool
    require(all(sha(Path(p)) == h for p, h in hashes.items()), 'input changed')
    report = {'passed': True, 'input_sha256': hashes, 'seeds': reports, 'training_hands': 0, 'evaluation_hands': 0,
              'scope': 'Real checkpoint serialization, pool loader/turnover and actual hardness hook; NOT worker rollout, assignment replay or bitwise worker RNG qualification.'}
    with report_path.open('x', encoding='utf-8') as f:
        json.dump(report, f, indent=2)
    print(json.dumps({'passed': True, 'seeds': reports}))

if __name__ == '__main__':
    main()
