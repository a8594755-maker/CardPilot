#!/usr/bin/env python3
import importlib.util,json,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
def load(name,path):
 s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
def main():
 lockm=load('lockm',ROOT/'scripts/alpha_holdem/v5_hybrid_h1_design_lock.py'); ep=load('ep',ROOT/'scripts/alpha_holdem/v5_hybrid_h1_endpoint_watch.py'); judge=load('judge',ROOT/'scripts/alpha_holdem/v5_hybrid_h1_judge.py'); monitor=load('monitor',ROOT/'scripts/alpha_holdem/v5_monitor.py'); passed=[]
 lock=lockm.build(); r=lockm.verify(lock); assert r['overall']=='PASS';passed+=['lock_build_verify']
 assert lock['calibration']['files']['audit.md']=='b3e591e179debb54e931c14fae120a16d47a00991cac525ef0845b1c8c994941';passed+=['audit_md_pinned']
 assert lock['gates']['entropy_median_drop_max']==.10;passed+=['entropy_contract']
 c=lock['arms']['control']['expected_config'];t=lock['arms']['treatment']['expected_config'];dif=sorted(k for k in set(c)|set(t) if c.get(k)!=t.get(k));assert dif==['critic_contract','h1_migration_report','value_coef'];passed+=['atomic_package']
 bad=json.loads(json.dumps(lock));bad['arms']['treatment']['expected_config']['workers']=23;assert lockm.verify(bad)['overall']=='FAIL';passed+=['tamper_fail_closed']
 assert not ep.errors(c,c); assert ep.errors({'workers':21},c);passed+=['endpoint_config']
 actual=dict(c);actual.pop('assignment_provenance_schema');assert not ep.errors(actual,c);passed+=['design_only_manifest_field_excluded']
 xs=[{'recorded_at':f'2026-07-12T00:00:{i:02d}+00:00','hands':i*100} for i in range(10)];assert judge.effective(xs)==100.0;passed+=['effective_hps']
 assert lock['authority']['official_slumbot_hands']==0 and lock['authority']['slumbot_paths']=='TERMINAL_BLOCKED';passed+=['slumbot_block']
 src=(ROOT/'scripts/alpha_holdem/train_v5_hybrid_h1.py').read_text(encoding='utf-8');assert "torch.save(checkpoint_payload(), args.out)" in src and "write_manifest('finished', total_hands=total_hands, iteration=iteration, checkpoint=str(out_path))" in src;passed+=['normal_completion_manifest_finished']
 line='[31401] hands=516,006,045 rew=+0.100 rew100=+0.100 ploss=0.0100 vloss=0.000123 vloss_bb2=4.9200 ent=1.2345 kl=0.0010 clipfrac=0.010 d1bite=0.000 r50=1.00/r95=1.01/r99=1.02/rmax=1.03 eps=0.000 pool=5 mirror=1/1 aiev=1:2 aiev_skip=0:0 trans=10 terms=2 mix=F0.100/C0.200/R0.600/A0.100 pmix=F0.100/C0.200/R0.600/A0.100 xmix=F0.100/C0.200/R0.600/A0.100 h/s=7000 tdec/s=8000 inf_bs=256.0 collect=2.0s ppo=1.0s';match=monitor.LOG_RE.search(line);assert match and float(match.groupdict()['entropy'])==1.2345;passed+=['monitor_h1_vloss_bb2']
 rearm=(ROOT/'scripts/alpha_holdem/v5_rearm_watchers.ps1').read_text(encoding='utf-8');begin=rearm.index('if ($script:isHybridH1Arm',rearm.index('# Launch all'));h1=rearm[begin:rearm.index('} else {',begin)]
 assert all(x in h1 for x in ['Launch-Health','Launch-Dashboard','Launch-OpsLog','Launch-Archive','Launch-ExpW1EndpointFreeze']) and all(x not in h1 for x in ['Launch-GateSequence','Launch-EvalCadence','Launch-Internal','Launch-SlumbotPromotion20k']);passed+=['h1_watcher_only_launch_set']
 epsrc=(ROOT/'scripts/alpha_holdem/v5_hybrid_h1_endpoint_watch.py').read_text(encoding='utf-8');assert 'WAITING_FOR_EXACT_ENDPOINT_ARTIFACTS' in epsrc and 'ENDPOINT_AUDIT_TIMEOUT' in epsrc and 'default=180' in epsrc;passed+=['bounded_endpoint_readiness_wait']
 print(json.dumps({'overall':'PASS','passed':len(passed),'tests':passed},indent=2));return 0
if __name__=='__main__':raise SystemExit(main())
