import json,tempfile,unittest
from pathlib import Path
import v5_hybrid_h2_mirror as h

class TestH2Mirror(unittest.TestCase):
 def setUp(self):
  self.old=(h.PAIRS,h.BOOTSTRAP_REPS);h.PAIRS=20;h.BOOTSTRAP_REPS=100
 def tearDown(self):h.PAIRS,h.BOOTSTRAP_REPS=self.old
 def bundle(self,root):
  deals=[{'index':i,'deal_id':f'd{i}','deck_sha256':f'{i:064x}','opponent_pool_id':h.ACTIVE_POOL_IDS[i%5]} for i in range(h.PAIRS)]
  m={'schema_version':'v5.hybrid.h2.mirror_manifest.v1','preregistration_sha256':h.PREREG_SHA,'pairs':h.PAIRS,'seed':h.SEED,'active_pool_ids':h.ACTIVE_POOL_IDS,'deals':deals};m['manifest_payload_sha256']=h.payload_sha(m,'manifest_payload_sha256');mp=root/'manifest.json';mp.write_text(json.dumps(m))
  lp=root/'lock.json';lock={'design_id':'H2-MIRROR-001','status':'LOCKED','tool_sha256':h.sha256_file(h.TOOL_PATH),'manifest_sha256':h.sha256_file(mp)};lp.write_text(json.dumps(lock));ls=h.sha256_file(lp)
  paths=[]
  for arm,delta in [('control',0),('treatment',1)]:
   p=root/f'{arm}.jsonl';rows=[{'arm':arm,'index':i,'deal_id':f'd{i}','deck_sha256':f'{i:064x}','candidate_rewards_bb':[delta,delta],'pair_mean_bb_per_hand':delta} for i in range(h.PAIRS)];p.write_text('\n'.join(json.dumps(x) for x in rows)+'\n');s={'rows_sha256':h.sha256_file(p),'pairs':h.PAIRS,'ood_rate':0,'measurement_lock_sha256':ls,'tool_sha256':h.sha256_file(h.TOOL_PATH),'runtime':{'torch_threads':1,'torch_interop_threads':1,'priority':{'requested':'below-normal','applied':True}}};p.with_suffix('.summary.json').write_text(json.dumps(s));paths.append(p)
  return mp,lp,ls,*paths
 def test_audit_and_judge(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);mp,lp,ls,c,t=self.bundle(root);ap=root/'audit.json';a=h.audit_bundle(mp,c,t,ap,lp,ls);self.assertEqual(a['overall'],'PASS_IMMUTABLE_H2_MIRROR');j=h.judge(mp,c,t,ap,root/'judge.json',lp,ls);self.assertEqual(j['status'],'PASS');self.assertAlmostEqual(j['treatment_minus_control_bb100'],100)
 def test_tampered_row_fails(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);mp,lp,ls,c,t=self.bundle(root);x=t.read_text().replace('"deal_id": "d0"','"deal_id": "bad"',1);t.write_text(x);a=h.audit_bundle(mp,c,t,root/'audit.json',lp,ls);self.assertEqual(a['overall'],'FAIL_CLOSED')
if __name__=='__main__':unittest.main()
