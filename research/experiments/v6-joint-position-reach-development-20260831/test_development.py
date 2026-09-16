import numpy as np,torch
import run_development as run
from alpha_holdem.execution_v6 import load_policy

def test_joint_position_scope_and_identity():
 m,ck,digest=load_policy(run.PREV/'latest.pt','cpu')
 assert digest==run.SOURCE_SHA and ck['position_adapter_hidden']==128
 trainable=[n for n,_ in m.named_parameters() if not n.startswith('value_head.')]
 frozen=[n for n,_ in m.named_parameters() if n.startswith('value_head.')]
 assert len(trainable)==88 and len(frozen)==6
 assert len([n for n in trainable if n.startswith('position_policy_adapters.')])==8

def test_extra_actor_identity():
 arrays={'extra_info':np.zeros((3,2),dtype=np.float32),'card_info':np.empty((3,)),'action_info':np.empty((3,)),'legal_mask':np.empty((3,))}
 out=run.arrays_with_actor(arrays,np.array([0,1,1]))
 assert out['extra_info'].shape==(3,3) and np.array_equal(out['extra_info'][:,2],[0,1,1])

def test_gate_boundaries():
 def gate(lower,mean,improvement):return lower>0 and mean<=.17 and improvement>=.01
 assert gate(.001,.17,.01) and not gate(0,.17,.01) and not gate(.001,.171,.01)


