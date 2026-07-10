from __future__ import annotations

import importlib.util
import pathlib
import sys
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
TOOL = ROOT / "scripts" / "stamp-release-version.py"
SPEC = importlib.util.spec_from_file_location("agentcart_release_stamp", TOOL)
release_stamp = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules["agentcart_release_stamp"] = release_stamp
SPEC.loader.exec_module(release_stamp)


class ReleaseVersionStampTest(unittest.TestCase):
    def test_nested_skill_metadata_version_is_stamped(self) -> None:
        source = (
            "---\n"
            "name: shopbridge-direct\n"
            "description: Direct ShopBridge buyer skill.\n"
            "metadata:\n"
            '  version: "0.1.0-alpha"\n'
            "---\n"
        )

        updated = release_stamp.replace_once(
            source,
            release_stamp.SKILL_VERSION_PATTERN,
            r'\g<1>1.12.0\g<2>',
            "ShopBridge direct skill metadata",
        )

        self.assertIn('  version: "1.12.0"', updated)
        self.assertNotIn("0.1.0-alpha", updated)


if __name__ == "__main__":
    unittest.main()
