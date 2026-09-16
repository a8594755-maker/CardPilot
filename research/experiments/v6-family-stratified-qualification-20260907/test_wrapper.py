import ast
import hashlib
import unittest
from train_candidate import SOURCE, SOURCE_SHA, transformed_wrapper

class Tests(unittest.TestCase):
    def test_only_install_call_changed(self):
        source = SOURCE.read_bytes()
        self.assertEqual(hashlib.sha256(source).hexdigest(), SOURCE_SHA)
        tree = transformed_wrapper(source)
        compile(tree, str(SOURCE), 'exec')
        calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == '_install_family_wrapper']
        self.assertEqual(len(calls), 1)
        n = calls[0]
        self.assertEqual(ast.unparse(n.args[0]), 'module')
        self.assertEqual(ast.unparse(n.args[-1]), 'args')
        n.func = ast.Attribute(value=n.args[0], attr='install', ctx=ast.Load())
        n.args = n.args[1:-1]
        original = next(n for n in ast.parse(source).body if isinstance(n, ast.FunctionDef) and n.name == 'main')
        self.assertEqual(ast.dump(tree.body[0]), ast.dump(original))
        self.assertEqual(SOURCE.read_bytes(), source)

if __name__ == '__main__':
    unittest.main()
