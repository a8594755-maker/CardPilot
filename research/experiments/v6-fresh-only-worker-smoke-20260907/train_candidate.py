"""Fresh-only parser hook on the unchanged observed mixture-zero runtime."""
import argparse
import ast
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

BASE=Path(__file__).resolve().parent
QUAL=BASE.parent/'v6-fresh-only-retained-buffer-qualification-20260907'
SOURCE=BASE.parent/'v6-opponent-execution-mixture-two-seed-geometric-20260907/train_candidate.py'
SHA='f759d6a2c64aaa17b5b34bbde12c2d6dbba59a9787b49c8dde6a96c9528ff4cc'
sys.path.insert(0,str(QUAL))
from hook import install

def main():
    parser=argparse.ArgumentParser(add_help=False)
    parser.add_argument('--run-dir',type=Path,required=True)
    parser.add_argument('--ppo-replay-ratio',type=float,required=True)
    parser.add_argument('--ppo-replay-buffer-iterations',type=int,required=True)
    args,_=parser.parse_known_args()
    if args.ppo_replay_ratio!=0 or args.ppo_replay_buffer_iterations!=2: raise ValueError('fresh-only contract')
    sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    if sha(SOURCE)!=SHA: raise ValueError('parent wrapper changed')
    contract=json.loads((args.run_dir/'parent_contract.json').read_text())
    def inject(module,weight):
        trainer,binding,inference=module.install(weight)
        hook=install(trainer)
        with (args.run_dir/'fresh_only_runtime.json').open('x',encoding='utf-8') as f:
            json.dump(dict(parent_sha256=contract['sha256'],wrapper_sha256=sha(Path(__file__)),hook_sha256=sha(QUAL/'hook.py'),parent_wrapper_sha256=SHA,hook=hook,ratio=0,buffer_iterations=2,command=sys.orig_argv),f,indent=2)
        return trainer,binding,inference
    spec=importlib.util.spec_from_file_location('fresh_observed_parent',SOURCE)
    parent=importlib.util.module_from_spec(spec); spec.loader.exec_module(parent)
    tree=ast.parse(SOURCE.read_text(encoding='utf-8'))
    main_node=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='main')
    calls=[n for n in ast.walk(main_node) if isinstance(n,ast.Call) and ast.unparse(n.func)=='module.install']
    if len(calls)!=1: raise ValueError('install coverage')
    call=calls[0]; call.func=ast.Name(id='_fresh_install',ctx=ast.Load()); call.args.insert(0,ast.Name(id='module',ctx=ast.Load()))
    parent._fresh_install=inject
    exec(compile(ast.fix_missing_locations(ast.Module(body=[main_node],type_ignores=[])),str(SOURCE),'exec'),parent.__dict__)
    parent.main()

if __name__=='__main__': main()
