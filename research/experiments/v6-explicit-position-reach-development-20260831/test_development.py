import numpy as np,torch
import run_development as run
from alpha_holdem.network import AlphaHoldemNet

def test_position_adapter_zero_init_and_missing_scope():
 ck=torch.load(run.PREV/'unweighted_tv.pt',map_location='cpu',weights_only=False)
 torch.manual_seed(2026102601)
 m=AlphaHoldemNet(norm_layer=ck.get('norm_layer','gn'),separate_preflop_head=True,position_adapter_hidden=128,critic_contract=ck.get('critic_contract','critic_v2'))
 with torch.no_grad():m(torch.zeros(2,6,4,13),torch.zeros(2,25,4,5),torch.zeros(2,3),torch.ones(2,9))
 r=m.load_state_dict(ck['model'],strict=False)
 assert not r.unexpected_keys and len(r.missing_keys)==8 and all(k.startswith('position_policy_adapters.') for k in r.missing_keys)
 assert all(torch.count_nonzero(a[-1].weight)==0 and torch.count_nonzero(a[-1].bias)==0 for a in m.position_policy_adapters)
 assert len([p for n,p in m.named_parameters() if n.startswith('position_policy_adapters.')])==8

def test_extra_actor_identity():
 arrays={'extra_info':np.zeros((3,2),dtype=np.float32),'card_info':np.empty((3,)),'action_info':np.empty((3,)),'legal_mask':np.empty((3,))}
 out=run.arrays_with_actor(arrays,np.array([0,1,1]))
 assert out['extra_info'].shape==(3,3) and np.array_equal(out['extra_info'][:,2],[0,1,1])

def test_gate_boundaries():
 def gate(lower,mean,improvement):return lower>0 and mean<=.17 and improvement>=.01
 assert gate(.001,.17,.01) and not gate(0,.17,.01) and not gate(.001,.171,.01)

