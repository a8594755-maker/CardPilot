"""Reuse qualified two-seed smoke orchestration with bound family-only injection."""
from pathlib import Path
import json
import sys

BASE = Path(__file__).resolve().parent
OLD = BASE.parent / 'v6-expanded-family-worker-smoke-20260907'
sys.path.insert(0, str(OLD))
import run_smoke_v3 as s

def configure():
    s.BASE = BASE
    s.PARENTS = BASE / 'derived'
    s.EXPECTED = {seed: s.read(BASE / f'real_resume_seed{seed}.json')['seeds'][str(seed)]['derived_sha256'] for seed in (1, 3)}

def prepare():
    configure()
    s.require(not (BASE / 'preparation.json').exists(), 'preserve preparation')
    hashes = {str(p): s.sha(p) for p in BASE.glob('*.py')}
    hashes[str(OLD / 'run_smoke_v3.py')] = s.sha(OLD / 'run_smoke_v3.py')
    hashes[str(OLD / 'pool_gate.py')] = s.sha(OLD / 'pool_gate.py')
    parents = {}
    for seed in (1, 3):
        report_path = BASE / f'real_resume_seed{seed}.json'
        report = s.read(report_path)
        s.require(report['passed'], 'real derivation not qualified')
        r = report['seeds'][str(seed)]
        source, target = Path(r['source']), Path(r['derived'])
        s.require(s.sha(source) == r['source_sha256'] and s.sha(target) == r['derived_sha256'], 'checkpoint changed')
        hashes[str(report_path)] = s.sha(report_path)
        hashes[str(source)] = r['source_sha256']
        hashes[str(target)] = r['derived_sha256']
        for name in ('command.json', 'h1_training_metrics.jsonl', 'opponent_assignments.jsonl', 'mixture_runtime.json'):
            src, dst = source.parent / name, target.parent / name
            s.require(not dst.exists(), 'preserve existing prefix')
            s.shutil.copy2(src, dst)
            s.require(s.sha(src) == s.sha(dst), 'copy mismatch')
            hashes[str(src)] = hashes[str(dst)] = s.sha(src)
        parents[str(seed)] = {'path': str(target), 'sha256': r['derived_sha256']}
    s.write_new(BASE / 'preparation.json', {'passed': True, 'parents': parents, 'input_sha256': hashes,
        'target_extra_physical_per_seed': 16384, 'no_automatic_retry': True,
        'scope': 'Family assignment and resume mechanism only, not strength; statistical worker continuation.'})
    print('Both preserved prefix sets copied; no new hands.')

class FamilySmoke(s.Smoke):
    def execute(self, argv, run, capture, training=False):
        argv = list(argv)
        argv[2] = str(BASE / 'train_candidate.py')
        parent = s.read(run / 'parent_contract.json')
        seed = next(seed for seed in (1, 3) if s.EXPECTED[seed] == parent['sha256'])
        r = s.read(BASE / f'real_resume_seed{seed}.json')['seeds'][str(seed)]
        s.write_new(run / 'family_contract.json', {'mode': 'stratified', 'parent_sha256': parent['sha256'],
            'original_ids': r['original_ids'], 'added_ids': r['added_ids'],
            'input_sha256': {str(p): s.sha(p) for p in BASE.glob('*.py')}})
        wall = super().execute(argv, run, capture, training=training)
        runtime = s.read(run / 'family_runtime.json')
        s.require(runtime['parent_sha256'] == parent['sha256'] and runtime['contract_sha256'] == s.sha(run / 'family_contract.json'), 'family runtime binding')
        return wall

def main():
    if '--prepare' in sys.argv:
        prepare()
        return
    configure()
    s.Smoke = FamilySmoke
    s.main()

if __name__ == '__main__':
    main()
