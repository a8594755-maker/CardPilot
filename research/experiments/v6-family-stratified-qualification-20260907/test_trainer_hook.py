import ast
import hashlib
from pathlib import Path
import unittest
from trainer_hook import transformed_main, EXPECTED_SHA

ROOT = Path(__file__).resolve().parents[3]
SOURCE = ROOT / 'research/experiments/v6-preflop-actor-trunk-route-qualification-20260906/candidate/scripts/alpha_holdem/train_v5.py'

class Tests(unittest.TestCase):
    def test_actual_ast_exact_two_call_delta(self):
        before = SOURCE.read_bytes()
        self.assertEqual(hashlib.sha256(before).hexdigest(), EXPECTED_SHA)
        tree = transformed_main(before.decode('utf-8'))
        compile(tree, str(SOURCE), 'exec')
        calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == '_family_hardness_weights']
        self.assertEqual(len(calls), 2)
        for call in calls:
            self.assertEqual(ast.unparse(call.args.pop()), 'pool.active_ids()')
            call.func.id = 'adaptive_hardness_weights'
        original = next(n for n in ast.parse(before).body if isinstance(n, ast.FunctionDef) and n.name == 'main')
        self.assertEqual(ast.dump(tree.body[0]), ast.dump(original))
        self.assertEqual(SOURCE.read_bytes(), before)

    def test_missing_or_changed_call_fails(self):
        for source in ('def main(): pass', 'def main(): adaptive_hardness_weights(a,b)'):
            with self.assertRaises(ValueError):
                transformed_main(source)

    def test_runtime_identity_arguments(self):
        source = 'def main():\n a = adaptive_hardness_weights([1], 2, 3)\n b = adaptive_hardness_weights([4], 5, 6)\n return a,b\n'
        seen = []
        class Pool:
            def active_ids(self):
                return [101, 203]
        env = {'pool': Pool(), '_family_hardness_weights': lambda *args: seen.append(args)}
        exec(compile(transformed_main(source), '<fixture>', 'exec'), env)
        env['main']()
        self.assertEqual(seen, [([1], 2, 3, [101, 203]), ([4], 5, 6, [101, 203])])

if __name__ == '__main__':
    unittest.main()
