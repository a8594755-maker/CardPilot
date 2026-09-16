import numpy as np,torch
import run_development as run

def validation64():
 with np.load(run.REACH/'validation_relabel/validation_arrays.npz') as z:a={k:z[k][:64] for k in z.files}
 m=np.load(run.REACH/'validation_relabel/validation_metadata.npz')
 return run.arrays_actor(a,m['actors'][:64])

def test_zero_residual_reproduces_frozen_source():
 model=run.build('cpu');a=validation64();p=run.infer(model,a,'cpu',count=False)
 source=np.load(run.SOURCE/'development_probabilities.npy')[:64]
 assert np.allclose(p,source,atol=2e-5,rtol=0)
 assert all(torch.count_nonzero(x[-1].weight)==0 and torch.count_nonzero(x[-1].bias)==0 for x in model.experts)
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
 def gate(lower,improvement,mean):return lower>0 and improvement>=.01 and mean<=.15
 assert gate(.001,.01,.15) and not gate(0,.01,.15) and not gate(.001,.009,.15) and not gate(.001,.01,.151)

