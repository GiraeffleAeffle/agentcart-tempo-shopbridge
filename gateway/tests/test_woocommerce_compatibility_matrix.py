from __future__ import annotations

import importlib.util
import json
import pathlib
import sys
import unittest


ROOT_DIR = pathlib.Path(__file__).resolve().parents[2]
TOOL_PATH = ROOT_DIR / "scripts" / "check-woocommerce-compatibility-matrix.py"
MATRIX_PATH = ROOT_DIR / "gateway" / "config" / "woocommerce_compatibility_matrix.json"
SPEC = importlib.util.spec_from_file_location("woocommerce_compatibility_matrix_tool", TOOL_PATH)
woocommerce_compatibility_matrix_tool = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules["woocommerce_compatibility_matrix_tool"] = woocommerce_compatibility_matrix_tool
SPEC.loader.exec_module(woocommerce_compatibility_matrix_tool)


def load_matrix() -> dict[str, object]:
    return json.loads(MATRIX_PATH.read_text(encoding="utf-8"))


class WooCommerceCompatibilityMatrixTest(unittest.TestCase):
    def test_checked_in_matrix_is_valid(self) -> None:
        errors = woocommerce_compatibility_matrix_tool.validate_matrix(load_matrix())

        self.assertEqual([], errors)

    def test_missing_required_runtime_entry_fails(self) -> None:
        matrix = load_matrix()
        for entry in matrix["runtime_matrix"]:
            entry["required_for_release"] = False

        errors = woocommerce_compatibility_matrix_tool.validate_matrix(matrix)

        self.assertTrue(any("required_for_release" in error for error in errors), errors)

    def test_required_entry_is_selected_by_default(self) -> None:
        matrix = load_matrix()

        entries = woocommerce_compatibility_matrix_tool.selected_entries(
            matrix,
            entry_id="",
            include_optional=False,
        )

        self.assertEqual(["wp-latest-php82-woo-latest"], [entry["id"] for entry in entries])

    def test_demo_reset_script_is_required_by_matrix(self) -> None:
        matrix = load_matrix()
        matrix["verification"].pop("demo_reset_script", None)

        errors = woocommerce_compatibility_matrix_tool.validate_matrix(matrix)

        self.assertTrue(any("demo_reset_script" in error for error in errors), errors)


if __name__ == "__main__":
    unittest.main()
