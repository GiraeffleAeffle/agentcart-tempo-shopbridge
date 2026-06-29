from __future__ import annotations

import importlib.util
import pathlib
import sys
import unittest


ROOT_DIR = pathlib.Path(__file__).resolve().parents[2]
TOOL_PATH = ROOT_DIR / "scripts" / "check-verifier-ops-pack.py"
SPEC = importlib.util.spec_from_file_location("verifier_ops_pack_tool", TOOL_PATH)
verifier_ops_pack_tool = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules["verifier_ops_pack_tool"] = verifier_ops_pack_tool
SPEC.loader.exec_module(verifier_ops_pack_tool)


class VerifierOpsPackTest(unittest.TestCase):
    def test_checked_in_verifier_ops_pack_matches_runtime_surfaces(self) -> None:
        errors = verifier_ops_pack_tool.validate()

        self.assertEqual([], errors)


if __name__ == "__main__":
    unittest.main()
