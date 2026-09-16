"""Reuse verified training lifecycle; isolate family allocation and grouped eval."""
from pathlib import Path
import importlib.util
import sys

BASE = Path(__file__).resolve().parent
OLD = BASE.parent / 'v6-expanded-family-two-seed-geometric-20260907'
QUAL = BASE.parent / 'v6-family-stratified-qualification-20260907'
spec = importlib.util.spec_from_file_location('allocation_parent_trial', OLD / 'run_trial.py')
old = importlib.util.module_from_spec(spec)
spec.loader.exec_module(old)
old.BASE = BASE
old.CAPACITY = {'control': 9, 'expanded': 9}
old.EVAL_SEEDS = {(seed,stage):20267000+10*seed+stage for seed in (1,3) for stage in (1,2)}
old.EXPECTED = {seed: old.sha(BASE.parent/'v6-expanded-family-worker-smoke-20260907/derived'/f'seed{seed}_recent_stage2/latest.pt') for seed in (1,3)}

def parent_path(seed, arm, stage):
    if stage == 2:
        return old.directory(seed, arm, 1) / 'latest.pt'
    root = QUAL if arm == 'expanded' else BASE.parent / 'v6-expanded-family-worker-smoke-20260907'
    return root / 'derived' / f'seed{seed}_recent_stage2/latest.pt'

old.parent_path = parent_path
BaseController = old.Controller

class Controller(BaseController):
    def execute(self, argv, folder, capture=None, training=False):
        if training and '_expanded_' in folder.name:
            argv = list(argv)
            argv[2] = str(QUAL / 'train_candidate.py')
            parent = old.read(folder / 'parent_contract.json')
            seed = int(folder.name.split('_')[0][4:])
            r = old.read(QUAL / f'real_resume_seed{seed}.json')['seeds'][str(seed)]
            if folder.name.endswith('stage2'):
                prior = Path(parent['path']).parent / 'family_runtime.json'
                old.require(str(prior) in self.inputs and old.sha(prior) == self.inputs[str(prior)], 'prior family runtime changed')
            old.write_new(folder / 'family_contract.json', {'mode':'stratified','parent_sha256':parent['sha256'],
                'original_ids':r['original_ids'],'added_ids':r['added_ids'],
                'input_sha256':{str(p):old.sha(p) for p in QUAL.glob('*.py')}})
        wall = super().execute(argv, folder, capture, training=training)
        if training and '_expanded_' in folder.name:
            runtime = old.read(folder / 'family_runtime.json')
            old.require(runtime['contract_sha256'] == old.sha(folder / 'family_contract.json'), 'family runtime contract')
            self.inputs[str(folder / 'family_runtime.json')] = old.sha(folder / 'family_runtime.json')
        return wall

    def evaluate(self, stage):
        q = old.read(BASE / 'qualification.json')
        anchors = q['anchors']
        groups = {'preservation':list(anchors)[:4], 'adaptation':list(anchors)[4:]}
        results, fresh = {}, []
        for seed in (1,3):
            arms = {}
            for arm in ('control','expanded'):
                out = BASE / f'eval_seed{seed}_{arm}_stage{stage}'
                job = BASE / f'job_{out.name}'
                job.mkdir()
                endpoint = old.directory(seed,arm,stage) / 'latest.pt'
                argv = [sys.executable,'-B','-u',str(old.ROOT/'scripts/alpha_holdem/v6_public_opponent_matched_eval.py'),
                    '--control',str(parent_path(seed,'control',1)),'--treatment',str(endpoint)]
                for name,path in anchors.items(): argv += ['--anchor',f'{name}={path}']
                argv += ['--pairs-per-anchor','1024','--seed',str(old.EVAL_SEEDS[seed,stage]),'--device','cuda','--out-dir',str(out)]
                self.phase = 'EVALUATING_' + out.name
                self.execute(argv,job)
                report = old.read(out/'summary.json')
                rows = old.ctl.evidence.read_rows(out/'common_deck_pairs.jsonl.gz')
                old.require(report['status']=='COMPLETED' and report['evaluation_hands']==32768 and len(rows)==8192, 'evaluation count')
                old.require(report['raw_pairs_sha256']==old.sha(out/'common_deck_pairs.jsonl.gz'), 'raw hash')
                old.require(report['policy_mode']=='greedy' and report['starting_stack_bb']==200 and report['observation_style']=='legacy_v4','execution contract')
                old.require(report['input_sha256']=={'control':old.EXPECTED[seed],'treatment':old.sha(endpoint),**{f'anchor:{k}':old.sha(Path(v)) for k,v in anchors.items()}},'checkpoint hashes')
                arms[arm] = rows
            results[str(seed)] = {}
            for group,names in groups.items():
                a = {arm:[r for r in rows if r['anchor'] in names] for arm,rows in arms.items()}
                contrast = old.ctl.evidence.summarize_rows(old.ctl.evidence.join_arms(a['control'],a['expanded']))
                endpoints = {arm:old.ctl.evidence.summarize_rows(rows) for arm,rows in a.items()}
                results[str(seed)][group] = {'stratified_minus_flat':contrast,'endpoint_minus_root':endpoints,
                    'broad_collapse':old.ctl.evidence.broad_collapse(contrast) or any(old.ctl.evidence.broad_collapse(v) for v in endpoints.values())}
            fresh += arms['control']
        old.require(len({tuple(r['deck']) for r in fresh})==16384,'cross-seed duplicates')
        freshness = old.ctl.evidence.check_prior_decks(fresh,self.corpus)
        analysis = {'passed':True,'stage':stage,'seeds':results,'freshness':freshness,'evaluation_hands':131072,
            'broad_collapse':any(g['broad_collapse'] for seed in results.values() for g in seed.values())}
        old.write_new(BASE/f'stage{stage}_analysis.json',analysis)
        for p in BASE.glob(f'eval_*_stage{stage}/common_deck_pairs.jsonl.gz'): self.corpus[str(p)] = old.sha(p)
        old.logger('--artifact',str(BASE/f'stage{stage}_analysis.json'))
        return analysis

if __name__ == '__main__':
    old.Controller = Controller
    old.main()
