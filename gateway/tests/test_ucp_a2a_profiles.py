from __future__ import annotations

import copy
import importlib.util
import json
import pathlib
import sys
import unittest


ROOT_DIR = pathlib.Path(__file__).resolve().parents[2]
TOOL_PATH = ROOT_DIR / "scripts" / "check-ucp-a2a-profiles.py"
PROFILES_PATH = ROOT_DIR / "gateway" / "config" / "ucp_a2a_profiles.json"
SPEC = importlib.util.spec_from_file_location("ucp_a2a_profiles_tool", TOOL_PATH)
ucp_a2a_profiles_tool = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules["ucp_a2a_profiles_tool"] = ucp_a2a_profiles_tool
SPEC.loader.exec_module(ucp_a2a_profiles_tool)


def load_profiles() -> dict[str, object]:
    return json.loads(PROFILES_PATH.read_text(encoding="utf-8"))


class UCPA2AProfilesTest(unittest.TestCase):
    def test_checked_in_profiles_are_valid(self) -> None:
        errors = ucp_a2a_profiles_tool.validate_profiles(load_profiles())

        self.assertEqual([], errors)

    def test_native_transport_claim_fails_until_runtime_exists(self) -> None:
        profiles = copy.deepcopy(load_profiles())
        profiles["profiles"][0]["native_transport_supported"] = True

        errors = ucp_a2a_profiles_tool.validate_profiles(profiles)

        self.assertTrue(any("native_transport_supported" in error for error in errors), errors)

    def test_missing_a2a_profile_fails(self) -> None:
        profiles = copy.deepcopy(load_profiles())
        profiles["profiles"] = [
            profile
            for profile in profiles["profiles"]
            if isinstance(profile, dict) and profile.get("id") != "a2a-handoff-profile"
        ]

        errors = ucp_a2a_profiles_tool.validate_profiles(profiles)

        self.assertTrue(any("a2a-handoff-profile" in error for error in errors), errors)


if __name__ == "__main__":
    unittest.main()
