from collections import OrderedDict
import unittest
from pool_gate import normalized_pool
class Tests(unittest.TestCase):
    def test_mapping(self):
        p={'pool_snapshots':[{'id':4,'state_dict':OrderedDict(w=[2])}],'pool_candidate_history':[1,2,3],'optimizer':{'step':4}}
        q=normalized_pool(p,2)
        self.assertIs(type(q['pool_snapshots'][0]['state_dict']),dict)
        self.assertEqual(q['pool_candidate_history'],[2,3])
        self.assertEqual(p['pool_candidate_history'],[1,2,3])
        self.assertIs(q['optimizer'],p['optimizer'])
        self.assertEqual(q['pool_snapshots'][0]['state_dict']['w'],[2])
if __name__=='__main__': unittest.main()
