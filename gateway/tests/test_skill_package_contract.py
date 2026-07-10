from __future__ import annotations

import importlib.util
import pathlib
import sys
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
TOOL = ROOT / "scripts" / "check-shopbridge-direct-skill-package.py"
SPEC = importlib.util.spec_from_file_location("agentcart_skill_package", TOOL)
skill_package = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules["agentcart_skill_package"] = skill_package
SPEC.loader.exec_module(skill_package)


class SkillPackageContractTest(unittest.TestCase):
    def test_source_skill_folder_is_installable(self) -> None:
        errors = skill_package.validate_skill_dir(ROOT / "gateway" / "shopbridge-direct-skill")

        self.assertEqual([], errors)

    def test_required_files_define_folder_not_zip_runtime(self) -> None:
        self.assertEqual(
            {"SKILL.md", "agents/openai.yaml", "scripts/shopbridge-command.py"},
            skill_package.REQUIRED_FILES,
        )


if __name__ == "__main__":
    unittest.main()
