from __future__ import annotations

import copy
import importlib.util
import json
import pathlib
import sys
import unittest


ROOT_DIR = pathlib.Path(__file__).resolve().parents[2]
TOOL_PATH = ROOT_DIR / "scripts" / "check-ap2-mandate-mapping.py"
MAPPING_PATH = ROOT_DIR / "gateway" / "config" / "ap2_mandate_mapping.json"
SPEC = importlib.util.spec_from_file_location("ap2_mandate_mapping_tool", TOOL_PATH)
ap2_mandate_mapping_tool = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules["ap2_mandate_mapping_tool"] = ap2_mandate_mapping_tool
SPEC.loader.exec_module(ap2_mandate_mapping_tool)


def load_mapping() -> dict[str, object]:
    return json.loads(MAPPING_PATH.read_text(encoding="utf-8"))


class AP2MandateMappingTest(unittest.TestCase):
    def test_checked_in_mapping_is_valid(self) -> None:
        errors = ap2_mandate_mapping_tool.validate_mapping(load_mapping())

        self.assertEqual([], errors)

    def test_missing_required_invariant_fails(self) -> None:
        mapping = load_mapping()
        mapping["required_invariants"] = [
            invariant
            for invariant in mapping["required_invariants"]
            if invariant != "trusted_surface_signature_required"
        ]

        errors = ap2_mandate_mapping_tool.validate_mapping(mapping)

        self.assertTrue(any("trusted_surface_signature_required" in error for error in errors), errors)

    def test_full_compliance_claim_fails_until_signed_vdc_exists(self) -> None:
        mapping = copy.deepcopy(load_mapping())
        mapping["compliance_claim"] = "ap2_signed_vdc_compliant"

        errors = ap2_mandate_mapping_tool.validate_mapping(mapping)

        self.assertTrue(any("compliance_claim" in error for error in errors), errors)


if __name__ == "__main__":
    unittest.main()
