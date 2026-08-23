from __future__ import annotations

import importlib.util
import pathlib
import shutil
import sys
import tempfile
import unittest
import zipfile


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

    def test_required_files_define_portable_core(self) -> None:
        self.assertEqual(
            {
                "SKILL.md",
                "scripts/shopbridge-command.py",
                "scripts/shopbridge_safe_http.py",
                "scripts/shopbridge_registry_trust.py",
                "scripts/shopbridge_onchain_projection.py",
                "scripts/shopbridge_onchain_rpc.py",
            },
            skill_package.PORTABLE_REQUIRED_FILES,
        )

    def test_openai_metadata_is_an_optional_adapter(self) -> None:
        self.assertEqual({"agents/openai.yaml"}, skill_package.OPTIONAL_ADAPTER_FILES)

        with tempfile.TemporaryDirectory() as temporary_directory:
            portable_skill = pathlib.Path(temporary_directory) / "shopbridge-direct-skill"
            shutil.copytree(ROOT / "gateway" / "shopbridge-direct-skill", portable_skill)
            shutil.rmtree(portable_skill / "agents")

            self.assertEqual([], skill_package.validate_skill_dir(portable_skill))

    def test_portable_zip_does_not_require_openai_adapter(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            zip_path = pathlib.Path(temporary_directory) / "shopbridge-direct-skill.zip"
            with zipfile.ZipFile(zip_path, "w") as archive:
                archive.writestr("shopbridge-direct-skill/SKILL.md", "portable workflow")
                archive.writestr("shopbridge-direct-skill/scripts/shopbridge-command.py", "")
                archive.writestr("shopbridge-direct-skill/scripts/shopbridge_safe_http.py", "")
                archive.writestr("shopbridge-direct-skill/scripts/shopbridge_registry_trust.py", "")
                archive.writestr("shopbridge-direct-skill/scripts/shopbridge_onchain_projection.py", "")
                archive.writestr("shopbridge-direct-skill/scripts/shopbridge_onchain_rpc.py", "")

            self.assertEqual([], skill_package.validate_zip(zip_path))


if __name__ == "__main__":
    unittest.main()
