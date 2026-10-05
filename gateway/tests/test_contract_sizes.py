from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import pathlib
import sys
import tempfile
import unittest


ROOT_DIR = pathlib.Path(__file__).resolve().parents[2]
TOOL_PATH = ROOT_DIR / "scripts" / "check-contract-sizes.py"
SPEC = importlib.util.spec_from_file_location("contract_sizes_tool", TOOL_PATH)
assert SPEC and SPEC.loader
contract_sizes_tool = importlib.util.module_from_spec(SPEC)
sys.modules["contract_sizes_tool"] = contract_sizes_tool
SPEC.loader.exec_module(contract_sizes_tool)


class ContractSizesTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = pathlib.Path(self.temp.name)
        self.out = self.root / "out"
        self.out.mkdir()

    def artifact(self, name: str, size: int, source: str | None = None) -> None:
        artifact = {
            "metadata": {"settings": {"compilationTarget": {
                source or f"contracts/{name}.sol": name,
            }}},
            "deployedBytecode": {"object": "0x" + "00" * size},
        }
        (self.out / f"{name}.json").write_text(json.dumps(artifact), encoding="utf-8")

    def run_checker(self) -> tuple[int, str, str]:
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            status = contract_sizes_tool.main(["--out", str(self.out)])
        return status, stdout.getvalue(), stderr.getvalue()

    def test_eip170_exact_boundary_passes(self) -> None:
        self.artifact("AgentCartMerchantRegistryV2", 24_576)
        status, stdout, stderr = self.run_checker()
        self.assertEqual(0, status, stderr)
        row = next(line for line in stdout.splitlines() if line.startswith("AgentCartMerchantRegistryV2"))
        self.assertEqual(["AgentCartMerchantRegistryV2", "24,576", "0"], row.split())

    def test_one_byte_over_boundary_fails_and_lists_offender(self) -> None:
        self.artifact("TooLarge", 24_577)
        status, _, stderr = self.run_checker()
        self.assertEqual(1, status)
        self.assertIn("contracts/TooLarge.sol:TooLarge: 24,577 bytes (1 over limit)", stderr)

    def test_empty_interface_and_test_and_script_contracts_are_ignored(self) -> None:
        self.artifact("Deployable", 1)
        self.artifact("Interface", 0)
        self.artifact("Abstract", 0)
        self.artifact("TestFixture", 24_577, "test/TestFixture.sol")
        self.artifact("DeploymentScript", 24_577, "script/DeploymentScript.sol")
        status, stdout, stderr = self.run_checker()
        self.assertEqual(0, status, stderr)
        self.assertEqual([("contracts/Deployable.sol", "Deployable", 1)],
                         contract_sizes_tool.contract_sizes(self.out, self.root))
        self.assertNotIn("Interface", stdout)
        self.assertNotIn("TestFixture", stdout)

    def test_registry_margin_and_sort_order(self) -> None:
        self.artifact("Zebra", 20)
        self.artifact("AgentCartMerchantRegistryV2", 23_654)
        _, stdout, _ = self.run_checker()
        rows = stdout.splitlines()[2:]
        self.assertEqual(["AgentCartMerchantRegistryV2", "23,654", "922"], rows[0].split())
        self.assertEqual("Zebra", rows[1].split()[0])

    def test_raw_metadata_absolute_sources_and_library_placeholders(self) -> None:
        artifact = {
            "rawMetadata": json.dumps({"settings": {"compilationTarget": {
                str(ROOT_DIR / "contracts" / "Linked.sol"): "Linked",
            }}}),
            "deployedBytecode": {"object": "0x" + "__$" + "a" * 34 + "$__"},
        }
        (self.out / "Linked.json").write_text(json.dumps(artifact), encoding="utf-8")
        (self.out / "build-info.json").write_text('{"output": {}}', encoding="utf-8")
        status, stdout, stderr = self.run_checker()
        self.assertEqual(0, status, stderr)
        self.assertEqual(["Linked", "20", "24,556"], stdout.splitlines()[2].split())

    def test_missing_source_metadata_or_truncated_bytecode_fails(self) -> None:
        artifact_path = self.out / "Broken.json"
        artifact_path.write_text(json.dumps({"deployedBytecode": {"object": "0x00"}}), encoding="utf-8")
        status, _, stderr = self.run_checker()
        self.assertEqual(1, status)
        self.assertIn("missing or ambiguous compilation target", stderr)
        self.artifact("Broken", 1)
        artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
        artifact["deployedBytecode"]["object"] = "0x0"
        artifact_path.write_text(json.dumps(artifact), encoding="utf-8")
        status, _, stderr = self.run_checker()
        self.assertEqual(1, status)
        self.assertIn("odd length", stderr)

    def test_configured_out_default_and_explicit_override(self) -> None:
        self.assertEqual(self.root / "out", contract_sizes_tool.artifact_directory(self.root, None))
        (self.root / "foundry.toml").write_text('[profile.default]\nout = "build/contracts"\n', encoding="utf-8")
        self.assertEqual(self.root / "build/contracts", contract_sizes_tool.artifact_directory(self.root, None))
        self.assertEqual(self.out.resolve(), contract_sizes_tool.artifact_directory(self.root, str(self.out)))

    def test_missing_and_empty_artifacts_fail_closed(self) -> None:
        status, _, stderr = self.run_checker()
        self.assertEqual(1, status)
        self.assertIn("no non-empty contracts/ runtime artifacts", stderr)
        with self.assertRaisesRegex(ValueError, "does not exist"):
            contract_sizes_tool.contract_sizes(self.root / "missing", self.root)


if __name__ == "__main__":
    unittest.main()
