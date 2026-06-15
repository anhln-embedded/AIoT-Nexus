import ast
import dataclasses
import inspect
import unittest
from pathlib import Path

import flet as ft


class FletCompatibilityTests(unittest.TestCase):
    def test_hud_uses_valid_flet_constructor_arguments(self):
        hud_path = Path(__file__).parents[1] / "src" / "ui" / "gui" / "hud.py"
        tree = ast.parse(hud_path.read_text(encoding="utf-8"))
        issues = []

        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                continue
            if not isinstance(node.func.value, ast.Name) or node.func.value.id != "ft":
                continue

            name = node.func.attr
            constructor = getattr(ft, name, None)
            if constructor is None:
                issues.append(f"ft.{name} does not exist (line {node.lineno})")
                continue

            try:
                signature = inspect.signature(constructor)
                parameters = signature.parameters
                if str(signature) == "(*args: Any, **kwargs: Any) -> None":
                    parameters = {field.name: None for field in dataclasses.fields(constructor)}
            except (TypeError, ValueError):
                continue

            if any(
                getattr(parameter, "kind", None) == inspect.Parameter.VAR_KEYWORD
                for parameter in parameters.values()
            ):
                continue

            invalid = [
                keyword.arg
                for keyword in node.keywords
                if keyword.arg and keyword.arg not in parameters
            ]
            if invalid:
                issues.append(f"ft.{name} line {node.lineno}: {invalid}")

        self.assertEqual([], issues)


if __name__ == "__main__":
    unittest.main()
