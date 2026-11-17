# -*- coding: utf-8 -*-
import ast
import os
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _iter_py_files(subdir):
    root = os.path.join(REPO, subdir)
    for dirpath, _dirnames, filenames in os.walk(root):
        for name in filenames:
            if name.endswith('.py'):
                yield os.path.join(dirpath, name)


def _imported_roots(path):
    with open(path, 'r', encoding='utf-8') as handle:
        tree = ast.parse(handle.read(), filename=path)
    roots = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                roots.add(alias.name.split('.', 1)[0])
        elif isinstance(node, ast.ImportFrom) and node.module:
            roots.add(node.module.split('.', 1)[0])
    return roots


class AuthArchitectureTests(unittest.TestCase):
    def test_core_layers_do_not_import_auth(self):
        for layer in ('domain', 'inbound', 'synergy_inbounder', 'synergy_reporter'):
            for path in _iter_py_files(layer):
                with self.subTest(path=os.path.relpath(path, REPO)):
                    self.assertNotIn('auth', _imported_roots(path))

    def test_auth_does_not_import_app_layers(self):
        forbidden = {'domain', 'inbound', 'synergy_inbounder', 'synergy_reporter', 'pages'}
        for path in _iter_py_files('auth'):
            with self.subTest(path=os.path.relpath(path, REPO)):
                overlap = _imported_roots(path) & forbidden
                self.assertEqual(overlap, set())


if __name__ == '__main__':
    unittest.main()
