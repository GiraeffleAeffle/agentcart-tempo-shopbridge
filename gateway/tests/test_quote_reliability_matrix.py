from __future__ import annotations

import importlib.util
import json
import pathlib
import sys
import unittest


ROOT_DIR = pathlib.Path(__file__).resolve().parents[2]
TOOL_PATH = ROOT_DIR / "scripts" / "check-quote-reliability-matrix.py"
MATRIX_PATH = ROOT_DIR / "gateway" / "config" / "quote_reliability_matrix.json"
SPEC = importlib.util.spec_from_file_location("quote_reliability_matrix_tool", TOOL_PATH)
quote_reliability_matrix_tool = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules["quote_reliability_matrix_tool"] = quote_reliability_matrix_tool
SPEC.loader.exec_module(quote_reliability_matrix_tool)


def load_matrix() -> dict[str, object]:
    return json.loads(MATRIX_PATH.read_text(encoding="utf-8"))


class QuoteReliabilityMatrixTest(unittest.TestCase):
    def test_checked_in_matrix_is_valid(self) -> None:
        errors = quote_reliability_matrix_tool.validate_matrix(load_matrix())

        self.assertEqual([], errors)

    def test_runtime_test_references_exist(self) -> None:
        errors = quote_reliability_matrix_tool.validate_runtime_test_refs(load_matrix())

        self.assertEqual([], errors)

    def test_missing_drift_case_fails(self) -> None:
        matrix = load_matrix()
        matrix["cases"] = [
            case
            for case in matrix["cases"]
            if isinstance(case, dict) and case.get("id") != "shipping-drift-recovery"
        ]

        errors = quote_reliability_matrix_tool.validate_matrix(matrix)

        self.assertTrue(any("shipping-drift-recovery" in error for error in errors), errors)

    def test_missing_recovery_reason_fails(self) -> None:
        matrix = load_matrix()
        for case in matrix["cases"]:
            if isinstance(case, dict) and case.get("id") == "tax-drift-recovery":
                case["recovery_reason"] = ""

        errors = quote_reliability_matrix_tool.validate_matrix(matrix)

        self.assertTrue(any("tax_changed" in error for error in errors), errors)


if __name__ == "__main__":
    unittest.main()
