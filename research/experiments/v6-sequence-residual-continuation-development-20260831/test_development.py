import numpy as np,torch
import run_development as run

def validation64():
 with np.load(run.REACH/'validation_relabel/validation_arrays.npz') as z:a={k:z[k][:64] for k in z.files}
 m=np.load(run.REACH/'validation_relabel/validation_metadata.npz')
 return run.arrays_actor(a,m['actors'][:64])

def test_zero_residual_reproduces_frozen_source():
 parent=torch.load(run.PARENT/'latest.pt',map_location='cpu',weights_only=False)
 model=run.build('cpu',parent['adapter']);a=validation64();p=run.infer(model,a,'cpu',count=False)
 source=np.load(run.PARENT/'development_probabilities.npy')[:64]
 assert np.allclose(p,source,atol=2e-5,rtol=0)
 state=model.adapter_state()
 assert state.keys()==parent['adapter'].keys() and all(torch.equal(state[k],parent['adapter'][k]) for k in state)
 base=[p for n,p in model.named_parameters() if n.startswith('base.')]
 adapter=[p for n,p in model.named_parameters() if not n.startswith('base.')]
 assert base and adapter and not any(p.requires_grad for p in base) and all(p.requires_grad for p in adapter)

def test_padding_and_shapes():
 model=run.build('cpu');a=validation64();t=[torch.as_tensor(a[k][:3],dtype=torch.float32) for k in run.KEYS]
 logits,value=model(*t)
 assert logits.shape==(3,9) and value.shape[0]==3
 valid=t[1][:,:24,3,0]>0
 assert valid.any() and (~valid).any()

def test_gate_boundaries():
 def gate(lower,improvement,mean):return lower>0 and improvement>=.005 and mean<=.15
 assert gate(.001,.005,.15) and not gate(0,.005,.15) and not gate(.001,.004,.15) and not gate(.001,.005,.151)

def test_parent_optimizer_and_reconstructed_order():
 ck=torch.load(run.PARENT/'latest.pt',map_location='cpu',weights_only=False)
 assert ck['epoch']==8 and ck['optimizer_steps']==2048
 g=np.random.default_rng(2026102801)
 for _ in range(8):order=g.permutation(262144)
 assert len(order)==262144 and len(np.unique(order))==262144

