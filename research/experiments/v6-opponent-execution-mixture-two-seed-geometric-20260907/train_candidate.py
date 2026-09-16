"""Hash-bound real-worker mixture smoke with exclusive runtime evidence."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
QUALIFIED = ROOT / 'research/experiments/v6-opponent-execution-mixture-qualification-20260907/train_candidate.py'
DIGEST = '97bd808d0587e0b30573c2872d1abcaf3fe23648bf572a9df43db8cfffc2162d'

def validate_contract(weight, contract, prior=None):
    if weight not in (0., .5) or contract.get('opponent_greedy_mixture') != weight:
        raise ValueError('registered mixture mismatch')
    if prior is not None and prior.get('greedy_weight') != weight:
        raise ValueError('prior mixture differs')
    return True

def main():
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument('--opponent-greedy-mixture', type=float, required=True)
    parser.add_argument('--run-dir', type=Path, required=True)
    parser.add_argument('--resume', type=Path, required=True)
    args, _ = parser.parse_known_args()
    if args.opponent_greedy_mixture not in (0., .5):
        raise ValueError('registered mixture must be zero or half')
    digest = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    if digest(QUALIFIED) != DIGEST:
        raise ValueError('qualified source changed')
    contract = json.loads((args.run_dir/'parent_contract.json').read_text())
    if args.resume.resolve() != Path(contract['path']).resolve() or digest(args.resume) != contract['sha256']:
        raise ValueError('wrong parent')
    validate_contract(args.opponent_greedy_mixture, contract)
    if contract.get('prior_mixture_runtime'):
        prior_path = Path(contract['prior_mixture_runtime'])
        if digest(prior_path) != contract['prior_mixture_runtime_sha256']:
            raise ValueError('prior mixture runtime changed')
        validate_contract(args.opponent_greedy_mixture, contract, json.loads(prior_path.read_text()))
    runtime = {'schema':'opponent_mixture.runtime.v1', 'greedy_weight':args.opponent_greedy_mixture,
        'parent_sha256':contract['sha256'], 'qualified_sha256':DIGEST,
        'wrapper_sha256':digest(Path(__file__)), 'command':sys.orig_argv,
        'checkpoint_metadata_contains_mixture':False,
        'resume_requires_bound_runtime_manifest':True}
    def write_new(path, obj):
        with path.open('x', encoding='utf-8') as handle:
            json.dump(obj, handle, indent=2)
    write_new(args.run_dir/'mixture_runtime.json', runtime)
    spec = importlib.util.spec_from_file_location('qualified_mixture', QUALIFIED)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    base = module.OpponentView
    observation = {'opponent_forward_rows':0, 'opponent_forward_batches':0, 'first_batch':None}
    class ObservedOpponent(base):
        def __call__(self, *inputs, **kwargs):
            logits, values = self.model(*inputs, **kwargs)
            mixed = module.mixture_logits(logits, self.weight)
            observation['opponent_forward_rows'] += len(logits)
            observation['opponent_forward_batches'] += 1
            if observation['first_batch'] is None:
                original = logits[:8].softmax(-1)
                actual = mixed[:8].softmax(-1)
                observation['first_batch'] = {'original_probabilities':original.cpu().tolist(),
                    'mixture_probabilities':actual.cpu().tolist(),
                    'legal_masks':inputs[3][:8].cpu().tolist(),
                    'greedy_actions':logits[:8].argmax(-1).cpu().tolist()}
            return mixed, values
    module.OpponentView = ObservedOpponent
    trainer, binding, original_inference = module.install(args.opponent_greedy_mixture)
    if args.opponent_greedy_mixture == 0:
        def zero_inference(hero_model, opp_models, *inputs, **kwargs):
            return original_inference(hero_model, [ObservedOpponent(m, 0.) for m in opp_models], *inputs, **kwargs)
        trainer.run_inference_v5 = zero_inference
    argv = list(sys.argv)
    index = argv.index('--opponent-greedy-mixture')
    del argv[index:index+2]
    sys.argv = argv
    print(json.dumps(binding), flush=True)
    trainer.mp.set_start_method('spawn')
    clean = False
    try:
        trainer.main()
        clean = True
    finally:
        write_new(args.run_dir/'mixture_observation.json', {'clean_return':clean,
            'runtime_sha256':digest(args.run_dir/'mixture_runtime.json'), **observation})

if __name__ == '__main__':
    main()
