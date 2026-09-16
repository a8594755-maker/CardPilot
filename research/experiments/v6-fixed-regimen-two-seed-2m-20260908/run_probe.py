"""Bounded stationary continuation on qualified managed lifecycle."""
import gzip
import importlib.util
import json
import os
from pathlib import Path
import random
import sys
import time

BASE = Path(__file__).resolve().parent
HELPER = BASE.parent/'v6-current-actor-gradient-probe-20260908/run_probe.py'
spec = importlib.util.spec_from_file_location('stationary_resume_lifecycle', HELPER)
prior = importlib.util.module_from_spec(spec); spec.loader.exec_module(prior)
prior.BASE = BASE
old = prior.old
old.BASE = BASE
old.DOSES = {1:1048576}
old.training_command = prior.original_command
sys.path.insert(0,str(BASE.parent/'v6-arbitrary-anchor-reporting-20260907'))
from paired_summary import summarize, severe


class Controller(prior.Probe):
    def __init__(self):
        super().__init__()
        self.inputs[str(HELPER)] = old.sha(HELPER)
        self.anchors = old.read(prior.PARENT/'qualification.json')['anchors']
        self.roots = {seed:BASE.parent/f'v6-family-allocation-two-seed-geometric-20260907/seed{seed}_control_stage2/latest.pt' for seed in (1,3)}
        for path in list(self.anchors.values())+list(self.roots.values()):
            self.inputs[str(path)] = old.sha(Path(path))
        diagnostic = old.read(BASE.parent/'v6-current-actor-gradient-probe-20260908/post_review.json')
        self.namespaces.update(r['namespace'] for r in diagnostic['runs'])
        temporal = BASE.parent/'v6-temporal-probability-matched-eval-20260908'
        self.prior_gzip = old.read(temporal/'input_contract.json')['prior_corpus']
        self.prior_plain = {str(p):old.sha(p) for p in temporal.glob('seed*.jsonl')}
        planned = set()
        for seed in (1,3):
            for ai in range(8):
                rng = random.Random(202609082000+100*seed+1000003*ai)
                for _ in range(1024):
                    deck=list(range(52));rng.shuffle(deck)
                    assert tuple(deck) not in planned
                    planned.add(tuple(deck))
        historical_rows = 0
        for corpus, opener in ((self.prior_gzip,gzip.open),(self.prior_plain,open)):
            for path,digest in corpus.items():
                assert old.sha(Path(path))==digest
                with opener(path,'rt',encoding='utf-8') as stream:
                    for line in stream:
                        assert tuple(json.loads(line)['deck']) not in planned
                        historical_rows += 1
        self.sources = {p:h for p,h in self.inputs.items() if p.endswith('.py')}
        old.write_new(BASE/'evaluation_contract.json',dict(anchors=self.anchors,roots={str(k):str(v) for k,v in self.roots.items()},input_sha256=self.inputs,prior_gzip=self.prior_gzip,prior_plain=self.prior_plain,planned_unique_decks=len(planned),historical_rows=historical_rows,overlap=0,evaluation_hands=131072))
        self.inputs[str(BASE/'evaluation_contract.json')] = old.sha(BASE/'evaluation_contract.json')

    def evaluate_fixed(self):
        results = {}
        for seed in (1,3):
            results[str(seed)] = {}
            comparison_rows = []
            for label,baseline in [('extension_start',old.parent_path(seed,'control',1)),('earlier_root',self.roots[seed])]:
                out=BASE/f'eval_seed{seed}_{label}'; job=BASE/f'job_seed{seed}_{label}';job.mkdir()
                endpoint=old.directory(seed,'control',1)/'latest.pt'
                argv=[sys.executable,'-B','-u',str(old.ROOT/'scripts/alpha_holdem/v6_public_opponent_matched_eval.py'),'--control',str(baseline),'--treatment',str(endpoint)]
                for name,path in self.anchors.items():argv+=['--anchor',f'{name}={path}']
                argv+=['--pairs-per-anchor','1024','--seed',str(202609082000+100*seed),'--device','cuda','--out-dir',str(out)]
                self.phase='EVALUATING_'+out.name
                self.execute(argv,job)
                report=old.read(out/'summary.json'); raw=out/'common_deck_pairs.jsonl.gz'
                assert report['status']=='COMPLETED' and report['evaluation_hands']==32768
                assert report['raw_pairs_sha256']==old.sha(raw)
                expected={'control':old.sha(baseline),'treatment':old.sha(endpoint),**{f'anchor:{k}':old.sha(Path(p)) for k,p in self.anchors.items()}}
                assert report['input_sha256']==expected
                rows=old.ctl.evidence.read_rows(raw)
                assert len(rows)==8192
                results[str(seed)][label]={panel:summarize([r for r in rows if r['anchor'] in names],anchors=names,pairs_per_anchor=1024) for panel,names in [('preservation',list(self.anchors)[:4]),('transfer',list(self.anchors)[4:])]}
                comparison_rows.append({(r['anchor'],r['pair_index']):(r['deck'],r['treatment_rewards_bb']) for r in rows})
                self.inputs[str(raw)]=old.sha(raw)
                old.logger('--artifact',str(out/'summary.json'),'--artifact',str(raw))
                self.tick(force=True)
            assert comparison_rows[0]==comparison_rows[1], 'same endpoint not reproducible across paired baselines'
        old.write_new(BASE/'evaluation_summary.json',dict(results=results,evaluation_hands=131072,scope='Controller summary only; independent raw review required.'))


def main():
    for key in ('PYTHONDONTWRITEBYTECODE','OMP_NUM_THREADS','MKL_NUM_THREADS','OPENBLAS_NUM_THREADS'):
        os.environ[key]='1'
    controller=Controller()
    try:
        for seed in (1,3):controller.train(seed,'control',1)
        controller.evaluate_fixed()
        old.ctl.execution.check_hashes(controller.inputs)
        old.write_new(BASE/'terminal.json',dict(status='FIXED_2M_COMPLETE_REVIEW_REQUIRED',training=controller.results,wall_seconds=time.perf_counter()-controller.started,evaluation_hands=131072,final_qualification_hands=0))
        controller.phase='FIXED_2M_COMPLETE_REVIEW_REQUIRED';controller.tick(force=True)
    except Exception as error:
        old.write_new(BASE/'controller_error.json',dict(error=repr(error),automatic_retry=False))
        raise


if __name__=='__main__':main()
