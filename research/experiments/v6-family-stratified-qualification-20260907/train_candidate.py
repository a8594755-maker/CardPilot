"""Preserve qualified training wrapper; inject only the family-allocation install."""
import ast
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
from trainer_hook import install as install_family

BASE = Path(__file__).resolve().parent
SOURCE = BASE.parent / 'v6-opponent-execution-mixture-two-seed-geometric-20260907/train_candidate.py'
SOURCE_SHA = 'f759d6a2c64aaa17b5b34bbde12c2d6dbba59a9787b49c8dde6a96c9528ff4cc'

def transformed_wrapper(source):
    tree = ast.parse(source)
    mains = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'main']
    if len(mains) != 1:
        raise ValueError('wrapper main changed')
    count = 0
    for n in ast.walk(mains[0]):
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and isinstance(n.func.value, ast.Name) and n.func.value.id == 'module' and n.func.attr == 'install':
            if len(n.args) != 1 or n.keywords:
                raise ValueError('wrapper installation signature changed')
            n.func = ast.Name(id='_install_family_wrapper', ctx=ast.Load())
            n.args = [ast.Name(id='module', ctx=ast.Load()), *n.args, ast.Name(id='args', ctx=ast.Load())]
            count += 1
    if count != 1:
        raise ValueError('expected exactly one wrapper installation')
    return ast.fix_missing_locations(ast.Module(body=mains, type_ignores=[]))

def family_install(module, mixture_weight, args):
    if mixture_weight != 0:
        raise ValueError('family control requires unchanged sampled opponent execution')
    contract_path = args.run_dir / 'family_contract.json'
    contract = json.loads(contract_path.read_text(encoding='utf-8'))
    sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
    if contract['mode'] != 'stratified' or sha(args.resume) != contract['parent_sha256']:
        raise ValueError('family parent binding mismatch')
    for p, h in contract['input_sha256'].items():
        if sha(p) != h:
            raise ValueError('family source changed: ' + p)
    trainer, binding, original = module.install(mixture_weight)
    hook = install_family(trainer, contract['original_ids'], contract['added_ids'])
    runtime = {'schema': 'family_allocation.runtime.v1', 'hook': hook,
               'contract_sha256': sha(contract_path), 'parent_sha256': contract['parent_sha256'],
               'wrapper_sha256': sha(__file__), 'parent_wrapper_sha256': SOURCE_SHA,
               'command': sys.orig_argv, 'conditional_family_masses': [0.5, 0.25, 0.25],
               'selfplay_fraction_unchanged': True, 'global_per_slot_floor_preserved': False,
               'checkpoint_metadata_sufficient_for_resume': False}
    with (args.run_dir / 'family_runtime.json').open('x', encoding='utf-8') as f:
        json.dump(runtime, f, indent=2)
    binding['family_allocation'] = runtime
    return trainer, binding, original

def main():
    source = SOURCE.read_bytes()
    if hashlib.sha256(source).hexdigest() != SOURCE_SHA:
        raise ValueError('qualified wrapper changed')
    spec = importlib.util.spec_from_file_location('family_preserved_wrapper', SOURCE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module._install_family_wrapper = family_install
    exec(compile(transformed_wrapper(source), str(SOURCE), 'exec'), module.__dict__)
    module.main()

if __name__ == '__main__':
    main()
