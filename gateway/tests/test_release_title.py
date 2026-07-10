from __future__ import annotations

import importlib.util
import pathlib
import sys
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
TOOL = ROOT / "scripts" / "check-conventional-title.py"
SPEC = importlib.util.spec_from_file_location("agentcart_release_title", TOOL)
release_title = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules["agentcart_release_title"] = release_title
SPEC.loader.exec_module(release_title)


class ReleaseTitleTest(unittest.TestCase):
    def test_release_worthy_titles_report_semantic_impact(self) -> None:
        self.assertEqual(([], "minor"), release_title.validate_title("feat(skill): add direct checkout"))
        self.assertEqual(([], "patch"), release_title.validate_title("fix(release): publish artifacts"))
        self.assertEqual(([], "patch"), release_title.validate_title("revert: restore previous verifier"))
        self.assertEqual(([], "major"), release_title.validate_title("feat(api)!: remove legacy checkout"))

    def test_valid_non_release_title_is_explicit(self) -> None:
        self.assertEqual(([], "none"), release_title.validate_title("docs(skill): explain ZIP installation"))

    def test_untyped_or_unsafe_title_is_rejected(self) -> None:
        for title in (
            "Harden staging payments and evidence gates",
            "feat(skill): Add direct checkout",
            "fix: publish artifacts.",
            "feat: publish\nrun arbitrary command",
        ):
            errors, impact = release_title.validate_title(title)
            self.assertTrue(errors, title)
            self.assertIn(impact, {"invalid", "minor", "patch", "none", "major"})


if __name__ == "__main__":
    unittest.main()
