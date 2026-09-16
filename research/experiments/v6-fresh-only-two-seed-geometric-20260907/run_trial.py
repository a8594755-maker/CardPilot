"""Matched replay versus fresh-only learning, using qualified managed lifecycle."""
import ast
import importlib.util
from pathlib import Path
import sys

BASE=Path(__file__).resolve().parent
PARENTS=BASE.parent/'v6-family-allocation-two-seed-geometric-20260907'
SMOKE=BASE.parent/'v6-fresh-only-worker-smoke-20260907'
REPORTER=BASE.parent/'v6-arbitrary-anchor-reporting-20260907'
SOURCE=BASE.parent/'v6-expanded-family-two-seed-geometric-20260907/run_trial.py'
spec=importlib.util.spec_from_file_location('fresh_managed_lifecycle',SOURCE)
old=importlib.util.module_from_spec(spec); spec.loader.exec_module(old)
sys.path.insert(0,str(REPORTER))
from paired_summary import summarize,severe
old.BASE=BASE; old.PARENTS=PARENTS
old.INITIAL={1:15744527,3:15747327}
old.CAPACITY={'control':9,'expanded':9}
old.EXPECTED={1:'5cc8fd0140f03d34450027dc6160c192ea7e7b0a8c7f3c7800ba456ad967d629',3:'633e9559e05dc265f2f1eda344a4af19708851ddaeffe97293ba915252bcc6f5'}
old.EVAL_SEEDS={(s,t):20267400+s*10+t for s in (1,3) for t in (1,2)}

def parent_path(seed,arm,stage):
    return PARENTS/f'seed{seed}_control_stage2/latest.pt' if stage==1 else old.directory(seed,arm,1)/'latest.pt'
old.parent_path=parent_path
original_command=old.training_command
def training_command(seed,arm,stage):
    args=original_command(seed,arm,stage)
    old.ctl.execution.set_option(args,'--ppo-replay-ratio',0 if arm=='expanded' else .5)
    old.ctl.execution.set_option(args,'--ppo-replay-buffer-iterations',2)
    if arm=='expanded':args[2]=str(SMOKE/'train_candidate.py')
    return args
old.training_command=training_command

def replay_progress(final,parent,arm):
    if arm=='control': return final['ppo_replay_cumulative_rows']>parent['ppo_replay_cumulative_rows']
    return final['ppo_replay_cumulative_rows']==parent['ppo_replay_cumulative_rows'] and final['ppo_replay_rng_state']==parent['ppo_replay_rng_state']
old._replay_progress=replay_progress

def transform_train(source):
    tree=ast.parse(source)
    cls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='Controller')
    method=next(n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name=='train')
    target=ast.dump(ast.parse("final['ppo_replay_cumulative_rows'] > parent['ppo_replay_cumulative_rows']",mode='eval').body)
    class Replace(ast.NodeTransformer):
        count=0
        def visit_Compare(self,node):
            if ast.dump(node)==target:
                self.count+=1
                return ast.parse('_replay_progress(final,parent,arm)',mode='eval').body
            return self.generic_visit(node)
        def visit_Constant(self,node):
            if node.value=='capacity5 versus capacity9 expanded fixed families; sampled execution0; managed new namespace':
                return ast.Constant('capacity9 both arms; replay0.5 control versus fresh-only0; retained buffer2; managed new namespace')
            return node
    replace=Replace(); method=replace.visit(method)
    if replace.count!=1:raise ValueError('replay verifier call-site drift')
    return ast.fix_missing_locations(ast.Module(body=[method],type_ignores=[]))
exec(compile(transform_train(SOURCE.read_text(encoding='utf-8')),str(SOURCE),'exec'),old.__dict__)
BaseController=old.Controller

class Controller(BaseController):
    def train(self,seed,arm,stage):
        if stage==2 and arm=='expanded':
            p=parent_path(seed,arm,stage).parent/'fresh_only_runtime.json'
            old.require(str(p) in self.inputs and old.sha(p)==self.inputs[str(p)],'prior fresh runtime')
        old.train(self,seed,arm,stage)
        folder=old.directory(seed,arm,stage)
        rows=old.ctl.execution.complete_jsonl(folder/'h1_training_metrics.jsonl')
        boundary=old.read(folder/'parent_contract.json')['iteration']
        rows=[r for r in rows if r['iteration']>boundary]
        ratio=0 if arm=='expanded' else .5
        old.require(rows and all(r['ppo_replay_ratio']==ratio and r['ppo_replay_buffer_iterations']==2 for r in rows),'actual replay config')
        old.require(all(r['ppo_replay_rows']==0 for r in rows) if ratio==0 else sum(r['ppo_replay_rows'] for r in rows)>0,'actual replay rows')
        if arm=='expanded':
            p=folder/'fresh_only_runtime.json'; runtime=old.read(p)
            old.require(runtime['ratio']==0 and runtime['buffer_iterations']==2 and runtime['parent_sha256']==old.read(folder/'parent_contract.json')['sha256'],'fresh runtime')
            self.inputs[str(p)]=old.sha(p)
        old.write_new(folder/'replay_contract_review.json',dict(passed=True,ratio=ratio,buffer_iterations=2,completed_iterations=len(rows),new_replay_rows=sum(r['ppo_replay_rows'] for r in rows)))

    def evaluate(self,stage):
        anchors=old.read(BASE/'qualification.json')['anchors']
        groups={'preservation':list(anchors)[:4],'transfer':list(anchors)[4:]}
        results={}; fresh=[]
        for seed in (1,3):
            arms={}
            for arm in ('control','expanded'):
                out=BASE/f'eval_seed{seed}_{arm}_stage{stage}'; job=BASE/f'job_{out.name}'; job.mkdir()
                endpoint=old.directory(seed,arm,stage)/'latest.pt'
                argv=[sys.executable,'-B','-u',str(old.ROOT/'scripts/alpha_holdem/v6_public_opponent_matched_eval.py'),'--control',str(parent_path(seed,'control',1)),'--treatment',str(endpoint)]
                for name,p in anchors.items():argv+=['--anchor',f'{name}={p}']
                argv+=['--pairs-per-anchor','1024','--seed',str(old.EVAL_SEEDS[seed,stage]),'--device','cuda','--out-dir',str(out)]
                self.phase='EVALUATING_'+out.name; self.execute(argv,job)
                report=old.read(out/'summary.json'); raw=out/'common_deck_pairs.jsonl.gz'
                expected={'control':old.EXPECTED[seed],'treatment':old.sha(endpoint),**{f'anchor:{k}':old.sha(Path(p)) for k,p in anchors.items()}}
                old.require(report['status']=='COMPLETED' and report['evaluation_hands']==32768 and report['raw_pairs_sha256']==old.sha(raw) and report['input_sha256']==expected,'eval evidence')
                old.require(report['policy_mode']=='greedy' and report['starting_stack_bb']==200 and report['observation_style']=='legacy_v4','eval contract')
                arms[arm]=old.ctl.evidence.read_rows(raw)
                old.require(len(arms[arm])==8192,'pair count')
            results[str(seed)]={}
            for group,names in groups.items():
                a={arm:[r for r in rows if r['anchor'] in names] for arm,rows in arms.items()}
                contrast=summarize(old.ctl.evidence.join_arms(a['control'],a['expanded']),anchors=names,pairs_per_anchor=1024)
                endpoints={arm:summarize(rows,anchors=names,pairs_per_anchor=1024) for arm,rows in a.items()}
                results[str(seed)][group]=dict(fresh_minus_replay=contrast,endpoint_minus_root=endpoints,broad_collapse=severe(contrast,minimum_bad_anchors=3) or any(severe(v,minimum_bad_anchors=3) for v in endpoints.values()))
            fresh+=arms['control']
        old.require(len({tuple(r['deck']) for r in fresh})==16384,'cross-seed duplicates')
        freshness=old.ctl.evidence.check_prior_decks(fresh,self.corpus)
        analysis=dict(passed=True,stage=stage,seeds=results,freshness=freshness,evaluation_hands=131072,broad_collapse=any(g['broad_collapse'] for s in results.values() for g in s.values()))
        old.write_new(BASE/f'stage{stage}_analysis.json',analysis)
        for p in BASE.glob(f'eval_*_stage{stage}/common_deck_pairs.jsonl.gz'):self.corpus[str(p)]=old.sha(p)
        old.logger('--artifact',str(BASE/f'stage{stage}_analysis.json'))
        return analysis

if __name__=='__main__':
    old.Controller=Controller
    old.main()
