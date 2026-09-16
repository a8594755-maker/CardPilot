"""Fail-closed in-memory call-site hook; frozen trainer file stays untouched."""
import ast
import hashlib
from pathlib import Path
from family_weights import stratify

EXPECTED_SHA = 'bcce947477fdcf6593b7a88ce6845bf5638ce6698b9462deeecf4133b05472e6'

def transformed_main(source):
    tree = ast.parse(source)
    mains = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'main']
    if len(mains) != 1:
        raise ValueError('expected one main')
    main = mains[0]
    count = 0
    for node in ast.walk(main):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == 'adaptive_hardness_weights':
            if len(node.args) != 3 or node.keywords:
                raise ValueError('hardness signature changed')
            node.func.id = '_family_hardness_weights'
            node.args.append(ast.Call(func=ast.Attribute(value=ast.Name(id='pool', ctx=ast.Load()), attr='active_ids', ctx=ast.Load()), args=[], keywords=[]))
            count += 1
    if count != 2:
        raise ValueError(f'expected exactly two hardness updates, got {count}')
    return ast.fix_missing_locations(ast.Module(body=[main], type_ignores=[]))

def install(trainer, original_ids, added_ids):
    path = Path(trainer.__file__)
    if hashlib.sha256(path.read_bytes()).hexdigest() != EXPECTED_SHA:
        raise ValueError('frozen trainer changed')
    if hasattr(trainer, '_family_hardness_weights'):
        raise ValueError('hook already installed')
    old, added = frozenset(original_ids), frozenset(added_ids)
    original = trainer.adaptive_hardness_weights
    def family_hardness(rewards, temperature, minimum, ids):
        return stratify(original(rewards, temperature, minimum), ids, old, added)
    code = compile(transformed_main(path.read_text(encoding='utf-8')), str(path), 'exec')
    trainer._family_hardness_weights = family_hardness
    exec(code, trainer.__dict__)
    return {'trainer_sha256': EXPECTED_SHA, 'changed_call_sites': 2,
            'original_ids': sorted(old), 'added_ids': sorted(added),
            'initial_resume_weights_must_be_derived_and_verified_separately': True,
            'global_per_slot_floor_preserved': False}
