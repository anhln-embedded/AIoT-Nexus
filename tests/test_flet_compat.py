import ast
import dataclasses
import inspect
import unittest
from pathlib import Path
from unittest import mock

import flet as ft

from src.ui.gui.hud import apply_control_palette, configure_window, log_window_diagnostics


class FakeWindow:
    full_screen = False
    frameless = False
    maximized = False
    resizable = True
    maximizable = True
    width = None
    height = None
    min_width = None
    min_height = None
    max_width = None
    max_height = None


class FakePage:
    def __init__(self):
        self.padding = None
        self.window = FakeWindow()


class FletCompatibilityTests(unittest.TestCase):
    def test_pi_window_is_fullscreen_kiosk(self):
        page = FakePage()
        configure_window(page, is_pi=True)

        self.assertEqual(page.padding, 0)
        self.assertTrue(page.window.full_screen)
        self.assertTrue(page.window.frameless)
        self.assertFalse(page.window.maximized)
        self.assertFalse(page.window.resizable)

    def test_windows_window_keeps_development_dimensions(self):
        page = FakePage()
        configure_window(page, is_pi=False)

        self.assertEqual(page.padding, 0)
        self.assertEqual(page.window.width, 1280)
        self.assertEqual(page.window.height, 800)
        self.assertEqual(page.window.max_width, 1280)
        self.assertEqual(page.window.max_height, 800)
        self.assertFalse(page.window.resizable)

    def test_preview_resolution_can_be_overridden(self):
        page = FakePage()
        configure_window(page, is_pi=False, width=1280, height=720)

        self.assertEqual(page.window.width, 1280)
        self.assertEqual(page.window.height, 720)

    def test_window_diagnostics_include_fullscreen_state(self):
        page = FakePage()
        configure_window(page, is_pi=True)

        with mock.patch("builtins.print") as print_mock:
            log_window_diagnostics(page, "test")

        output = print_mock.call_args.args[0]
        self.assertIn("[AIOT WINDOW]", output)
        self.assertIn("stage='test'", output)
        self.assertIn("full_screen=True", output)

    def test_control_palette_switches_to_light_and_back(self):
        child = ft.Text("Nội dung", color="#EAFBFA")
        hover_surface = ft.Container(bgcolor="#18313A")
        control = ft.Container(
            bgcolor="#12161F",
            border=ft.Border.all(1, "#45A29E"),
            shadow=ft.BoxShadow(color=ft.Colors.with_opacity(0.22, "#66FCF1")),
            content=ft.Column([child, hover_surface]),
        )

        apply_control_palette(control, light=True)
        self.assertEqual(control.bgcolor, "#EEF3F5")
        self.assertEqual(control.border.top.color, "#168A84")
        self.assertEqual(control.shadow.color, "#007C76,0.22")
        self.assertEqual(child.color, "#18383D")
        self.assertEqual(hover_surface.bgcolor, "#DCEDEC")

        apply_control_palette(control, light=False)
        self.assertEqual(control.bgcolor, "#12161F")
        self.assertEqual(control.border.top.color, "#45A29E")
        self.assertEqual(control.shadow.color, "#66FCF1,0.22")
        self.assertEqual(child.color, "#EAFBFA")
        self.assertEqual(hover_surface.bgcolor, "#18313A")

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
