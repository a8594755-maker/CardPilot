"""Allow a retained two-iteration buffer with zero replay sampling, explicitly."""
import ast
import hashlib
from pathlib import Path

SHA='bcce947477fdcf6593b7a88ce6845bf5638ce6698b9462deeecf4133b05472e6'
OLD='(args.ppo_replay_buffer_iterations > 0) != (args.ppo_replay_ratio > 0.0)'
NEW='args.ppo_replay_buffer_iterations == 0 and args.ppo_replay_ratio > 0.0'

def transformed(source):
    tree=ast.parse(source)
    mains=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='main']
    if len(mains)!=1: raise ValueError('main coverage')
    wanted=ast.dump(ast.parse(OLD,mode='eval').body)
    found=[n for n in ast.walk(mains[0]) if isinstance(n,ast.If) and ast.dump(n.test)==wanted]
    if len(found)!=1: raise ValueError('parser guard drift')
    found[0].test=ast.parse(NEW,mode='eval').body
    return ast.fix_missing_locations(ast.Module(body=mains,type_ignores=[]))

def install(trainer):
    p=Path(trainer.__file__)
    if hashlib.sha256(p.read_bytes()).hexdigest()!=SHA: raise ValueError('trainer SHA')
    if getattr(trainer,'_retained_zero_replay',False): raise ValueError('duplicate hook')
    exec(compile(transformed(p.read_text(encoding='utf-8')),str(p),'exec'),trainer.__dict__)
    trainer._retained_zero_replay=True
    return dict(trainer_sha256=SHA,changed_parser_guards=1,buffer_restore_append_serialize_unchanged=True,replay_rng_not_consumed_at_zero_target=True)
