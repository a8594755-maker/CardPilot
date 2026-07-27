from __future__ import annotations
import copy, json, sys, tempfile, unittest
from pathlib import Path
import numpy as np

SCRIPT_DIR=Path(__file__).resolve().parent
sys.path.insert(0,str(SCRIPT_DIR))
import v5_h1_calibration as cal

class H1CalibrationTest(unittest.TestCase):
    def setUp(self):
        self.old_pairs=cal.PAIRS; cal.PAIRS=2
        self.temp=tempfile.TemporaryDirectory(); self.root=Path(self.temp.name)
    def tearDown(self):
        cal.PAIRS=self.old_pairs; self.temp.cleanup()

    def fixture(self):
        deals=[]
        for index in range(2):
            deck_sha=f'{index+1:064x}'; deals.append({'index':index,'deal_id':f'deal-{index}','deck_sha256':deck_sha,'opponent_pool_id':cal.ACTIVE_POOL_IDS[index%5]})
        identities={'source':{'state_sha256':cal.SOURCE_STATE_SHA},'pool':[{'id':key,'state_sha256':value} for key,value in cal.POOL_STATE_SHAS.items()]}
        manifest={'schema_version':cal.MANIFEST_SCHEMA,'design_id':cal.DESIGN_ID,'preregistration_sha256':cal.PREREG_SHA,'source_checkpoint_sha256':cal.SOURCE_SHA,'pairs':2,'hands':4,'seed':cal.SEED,'seat_order':[0,1],'starting_stack_bb':cal.STACK,'env_version':'v55','obs_version':'v55','action_space_version':'9slot_v5','training_use':'FORBIDDEN_HOLDOUT_ONLY','identities':identities,'deals':deals}
        manifest['manifest_payload_sha256']=cal.payload_sha(manifest,'manifest_payload_sha256')
        packed,obs_sha=cal.pack_obs({'card_info':np.zeros((6,4,13),np.float32),'action_info':np.zeros((25,4,5),np.float32),'extra_info':np.zeros(2,np.float32),'legal_mask':np.ones(9,np.float32)})
        rows=[]; self.hands=[]
        for deal in deals:
            for seat in (0,1):
                reward=20.0 if seat==0 else -10.0
                self.hands.append({'schema_version':'v5.hybrid.h1.calibration_hand.v1','design_id':cal.DESIGN_ID,'hand_id':f"{deal['deal_id']}-s{seat}",'deal_id':deal['deal_id'],'deal_index':deal['index'],'deck_sha256':deal['deck_sha256'],'source_seat':seat,'opponent_pool_id':deal['opponent_pool_id'],'terminal_reward_bb':reward,'source_decisions':1,'source_ood':0,'opponent_decisions':1,'opponent_ood':0})
                rows.append({'schema_version':cal.ROW_SCHEMA,'design_id':cal.DESIGN_ID,'decision_id':f"{deal['deal_id']}-s{seat}-d0",'deal_id':deal['deal_id'],'deal_index':deal['index'],'deck_sha256':deal['deck_sha256'],'source_seat':seat,'opponent_pool_id':deal['opponent_pool_id'],'decision_index':0,'hero_decisions_in_hand':1,'terminal_reward_bb':reward,'gamma':cal.GAMMA,'target_normalized':reward/cal.STACK,'source_value_prediction_normalized':0.0,'action_slot':1,'packed_obs_zlib_b64':packed,'obs_sha256':obs_sha})
        (self.root/'manifest.json').write_text(json.dumps(manifest),encoding='utf-8')
        (self.root/'hands.jsonl').write_text(''.join(json.dumps(row)+'\n' for row in self.hands),encoding='utf-8')
        (self.root/'decisions.jsonl').write_text(''.join(json.dumps(row)+'\n' for row in rows),encoding='utf-8')
        summary={'schema_version':cal.SUMMARY_SCHEMA,'decision_rows':len(rows),'source_ood_rate':0.0,'opponent_ood_rate':0.0,'manifest_sha256':cal.sha256_file(self.root/'manifest.json'),'hands_sha256':cal.sha256_file(self.root/'hands.jsonl'),'decisions_sha256':cal.sha256_file(self.root/'decisions.jsonl')}
        (self.root/'summary.json').write_text(json.dumps(summary),encoding='utf-8')
        return manifest,rows,summary

    def rewrite(self,manifest,rows,summary):
        manifest['manifest_payload_sha256']=cal.payload_sha(manifest,'manifest_payload_sha256')
        (self.root/'manifest.json').write_text(json.dumps(manifest),encoding='utf-8')
        (self.root/'hands.jsonl').write_text(''.join(json.dumps(row)+'\n' for row in self.hands),encoding='utf-8')
        (self.root/'hands.jsonl').write_text(''.join(json.dumps(row)+'\n' for row in self.hands),encoding='utf-8')
        (self.root/'decisions.jsonl').write_text(''.join(json.dumps(row)+'\n' for row in rows),encoding='utf-8')
        summary['hands_sha256']=cal.sha256_file(self.root/'hands.jsonl'); summary['decision_rows']=len(rows); summary['manifest_sha256']=cal.sha256_file(self.root/'manifest.json'); summary['decisions_sha256']=cal.sha256_file(self.root/'decisions.jsonl')
        (self.root/'summary.json').write_text(json.dumps(summary),encoding='utf-8')

    def test_pack_roundtrip_and_tamper(self):
        _,rows,_=self.fixture(); decoded=cal.unpack_obs(rows[0]['packed_obs_zlib_b64'],rows[0]['obs_sha256']); self.assertEqual(sum(v.size for v in decoded),cal.OBS_FLOATS)
        with self.assertRaises(ValueError): cal.unpack_obs(rows[0]['packed_obs_zlib_b64'],'0'*64)

    def test_valid_bundle_passes(self):
        self.fixture(); self.assertEqual(cal.audit_bundle(self.root)['status'],'PASS_IMMUTABLE_HOLDOUT')

    def test_duplicate_decision_fails(self):
        m,r,s=self.fixture(); r[1]['decision_id']=r[0]['decision_id']; self.rewrite(m,r,s); self.assertEqual(cal.audit_bundle(self.root)['status'],'FAIL_CLOSED')

    def test_partial_seat_matrix_fails(self):
        m,r,s=self.fixture(); self.hands.pop(); self.rewrite(m,r,s); self.assertEqual(cal.audit_bundle(self.root)['status'],'FAIL_CLOSED')

    def test_observation_tamper_fails(self):
        m,r,s=self.fixture(); r[0]['obs_sha256']='0'*64; self.rewrite(m,r,s); self.assertEqual(cal.audit_bundle(self.root)['status'],'FAIL_CLOSED')

    def test_model_identity_tamper_fails(self):
        m,r,s=self.fixture(); m['identities']['pool'][0]['state_sha256']='0'*64; self.rewrite(m,r,s); self.assertEqual(cal.audit_bundle(self.root)['status'],'FAIL_CLOSED')

    def test_duplicate_deal_fails(self):
        m,r,s=self.fixture(); m['deals'][1]['deal_id']=m['deals'][0]['deal_id']; self.rewrite(m,r,s); self.assertEqual(cal.audit_bundle(self.root)['status'],'FAIL_CLOSED')

    def test_ood_fails(self):
        m,r,s=self.fixture(); s['source_ood_rate']=0.2; self.rewrite(m,r,s); self.assertEqual(cal.audit_bundle(self.root)['status'],'FAIL_CLOSED')

    def test_target_cluster_tamper_fails(self):
        m,r,s=self.fixture(); r[0]['target_normalized']+=0.01; self.rewrite(m,r,s); self.assertEqual(cal.audit_bundle(self.root)['status'],'FAIL_CLOSED')

    def test_one_shot_output_protection(self):
        (self.root/'marker').write_text('x')
        with self.assertRaises(FileExistsError): cal.generate(Path('missing.pt'),self.root,'cpu')

class H1BoundaryTest(unittest.TestCase):
    def values(self,treatment):
        control={f'd{i}':1.0 for i in range(cal.PAIRS)}; treat={f'd{i}':float(treatment(i)) for i in range(cal.PAIRS)}; return control,treat
    def test_pass_boundary(self):
        c,t=self.values(lambda _:0.5); self.assertEqual(cal.classify_reduction(c,t,reps=200)['status'],'PASS_VALUE_GATE')
    def test_fail_boundary(self):
        c,t=self.values(lambda _:1.0); self.assertEqual(cal.classify_reduction(c,t,reps=200)['status'],'FAIL_VALUE_GATE')
    def test_inconclusive_boundary(self):
        c,t=self.values(lambda i:0.5 if i%2==0 else 1.25); self.assertEqual(cal.classify_reduction(c,t,reps=500)['status'],'INCONCLUSIVE_VALUE_GATE')

if __name__=='__main__': unittest.main()