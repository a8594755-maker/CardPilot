import copy
import unittest
from expand import expand,FIELDS

def fixture():
    snaps=[{'id':i,'state_dict':{'w':[i]},'score_components':{'kind':'initial_external_opponent' if i<3 else 'learned'}} for i in range(5)]
    p={'pool_strategy':'anchor-latest','pool_snapshots':snaps,'pool_active_metadata':[{k:v for k,v in s.items() if k!='state_dict'} for s in snaps],
       'pool_candidate_history':[{'id':100}], 'adaptive_opponent_ema_rewards':[1.,2.,3.,4.,5.],
       'adaptive_opponent_weights':[.1,.2,.3,.2,.2],'adaptive_opponent_observations':[1,2,3,4,5],
       'model':{'a':[2]},'optimizer':{'step':32},'replay':[1,2],'iteration':8,'total_hands':400}
    a=[{'sha256':str(i)*64,'path':str(i),'family':'sibling','checkpoint':{'model':{'w':[10+i]},'iteration':2,'total_hands':20}} for i in range(4)]
    return p,a
class Tests(unittest.TestCase):
    def test_preservation(self):
        p,a=fixture(); old=copy.deepcopy(p); q=expand(p,a)
        self.assertEqual(p,old)
        self.assertEqual({k:v for k,v in p.items() if k not in FIELDS},{k:v for k,v in q.items() if k not in FIELDS})
        self.assertEqual(q['pool_snapshots'][:5],p['pool_snapshots'])
        self.assertEqual(q['expanded_family_pool_contract']['new_ids'],[101,102,103,104])
    def test_mass(self):
        p,a=fixture(); q=expand(p,a)
        self.assertAlmostEqual(sum(q['adaptive_opponent_weights']),1)
        self.assertEqual(q['adaptive_opponent_observations'][:5],p['adaptive_opponent_observations'])
        self.assertAlmostEqual(q['adaptive_opponent_weights'][0]/q['adaptive_opponent_weights'][1],.5)
    def test_repeated(self):
        p,a=fixture()
        with self.assertRaises(ValueError): expand(expand(p,a),a)
    def test_duplicate(self):
        p,a=fixture(); a[1]=a[0]
        with self.assertRaises(ValueError): expand(p,a)
    def test_bad_weights(self):
        p,a=fixture(); p['adaptive_opponent_weights'][0]=float('nan')
        with self.assertRaises(ValueError): expand(p,a)
    def test_bad_length(self):
        p,a=fixture(); p['adaptive_opponent_observations']=[]
        with self.assertRaises(ValueError): expand(p,a)
    def test_retention(self):
        import importlib.util
        from pathlib import Path
        path=Path(__file__).resolve().parents[1]/'v6-anchor-recent-pool-qualification-20260907/anchor_recent.py'
        spec=importlib.util.spec_from_file_location('selector',path); m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
        p,a=fixture(); q=expand(p,a); s=q['pool_snapshots']
        self.assertEqual(m.retained_snapshots(s,9),s)
        pruned=m.retained_snapshots(s+[{'id':105,'score_components':{}}],9)
        self.assertEqual(len(pruned),9)
        self.assertTrue({0,1,2,101,102,103,104,105}.issubset({x['id'] for x in pruned}))
if __name__=='__main__': unittest.main()
