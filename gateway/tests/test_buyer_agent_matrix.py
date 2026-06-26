from __future__ import annotations

import importlib.util
import json
import pathlib
import sys
import tempfile
import unittest


ROOT_DIR = pathlib.Path(__file__).resolve().parents[2]
TOOL_PATH = ROOT_DIR / "scripts" / "check-buyer-agent-matrix.py"
MATRIX_PATH = ROOT_DIR / "gateway" / "config" / "buyer_agent_test_matrix.json"
SPEC = importlib.util.spec_from_file_location("buyer_agent_matrix_tool", TOOL_PATH)
buyer_agent_matrix_tool = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules["buyer_agent_matrix_tool"] = buyer_agent_matrix_tool
SPEC.loader.exec_module(buyer_agent_matrix_tool)


def load_matrix() -> dict[str, object]:
    return json.loads(MATRIX_PATH.read_text(encoding="utf-8"))


class BuyerAgentMatrixTest(unittest.TestCase):
    def test_checked_in_matrix_is_valid(self) -> None:
        errors = buyer_agent_matrix_tool.validate_matrix(load_matrix())

        self.assertEqual([], errors)

    def test_missing_required_runtime_fails(self) -> None:
        matrix = load_matrix()
        matrix["runtimes"] = [
            runtime
            for runtime in matrix["runtimes"]
            if isinstance(runtime, dict) and runtime.get("id") != "generic-mcp-client"
        ]

        errors = buyer_agent_matrix_tool.validate_matrix(matrix)

        self.assertTrue(any("generic-mcp-client" in error for error in errors), errors)

    def test_missing_runtime_capability_fails(self) -> None:
        matrix = load_matrix()
        first_runtime = matrix["runtimes"][0]
        first_runtime["capabilities"].pop("checkout_handoff")

        errors = buyer_agent_matrix_tool.validate_matrix(matrix)

        self.assertTrue(any("checkout_handoff" in error for error in errors), errors)

    def test_evidence_check_accepts_expected_files_for_one_runtime(self) -> None:
        matrix = load_matrix()
        first_runtime = matrix["runtimes"][0]
        matrix["runtimes"] = [first_runtime]

        with tempfile.TemporaryDirectory() as tmp:
            evidence_dir = pathlib.Path(tmp)
            runtime_dir = evidence_dir / first_runtime["id"]
            runtime_dir.mkdir(parents=True)
            for evidence_id in first_runtime["required_evidence"]:
                (runtime_dir / f"{evidence_id}.md").write_text("ok\n", encoding="utf-8")

            errors = buyer_agent_matrix_tool.validate_evidence(matrix, evidence_dir)

        self.assertEqual([], errors)


if __name__ == "__main__":
    unittest.main()
