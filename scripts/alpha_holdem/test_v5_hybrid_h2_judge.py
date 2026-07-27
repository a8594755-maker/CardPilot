import unittest
from v5_hybrid_h2_judge import classify

BASE={'offline_variance_point':True,'offline_variance_ci_lower':True,'offline_bias_point':True,'offline_bias_ci_upper':True,'endpoint_mse_point':True,'endpoint_mse_ci_upper':True,'mirror_noninferiority':True,'throughput_first60':True,'throughput_full':True,'entropy_floor':True,'entropy_noninferior':True}
class TestH2Judge(unittest.TestCase):
 def test_pass(self):self.assertEqual(classify(dict(BASE),{}, {'status':'PASS'})[0],'PASS')
 def test_first60_abort(self):
  x=dict(BASE);x['throughput_first60']=False;self.assertEqual(classify(x,{}, {'status':'PASS'}),('FAIL','H2_FAIL_PROTOCOL_ABORT_FIRST60_THROUGHPUT'))
 def test_guard_fail(self):
  x=dict(BASE);x['endpoint_mse_ci_upper']=False;self.assertEqual(classify(x,{}, {'status':'PASS'})[0],'FAIL')
 def test_mirror_inconclusive(self):
  x=dict(BASE);x['mirror_noninferiority']=False
  verdict=classify(x,{}, {'status':'INCONCLUSIVE'})[0]
  self.assertEqual(verdict,'INCONCLUSIVE')
  self.assertTrue(verdict in ('FAIL','INCONCLUSIVE'))
 def test_mirror_fail(self):
  x=dict(BASE);x['mirror_noninferiority']=False;self.assertEqual(classify(x,{}, {'status':'FAIL'})[0],'FAIL')
if __name__=='__main__':unittest.main()
