from __future__ import annotations

import copy
import importlib.util
import json
import pathlib
import sys
import tempfile
import unittest
from unittest import mock


ROOT = pathlib.Path(__file__).resolve().parents[2]
FIXTURE_PATH = ROOT / "docs" / "fixtures" / "registry" / "trust-fixtures.json"
DIRECT_SKILL_PATH = ROOT / "gateway" / "shopbridge-direct-skill" / "scripts" / "shopbridge-command.py"
REGISTRY_TOOL_PATH = ROOT / "gateway" / "scripts" / "registry_record.py"


def load_module(name: str, path: pathlib.Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


shopbridge_direct = load_module("registry_fixture_shopbridge_direct", DIRECT_SKILL_PATH)
registry_record_tool = load_module("registry_fixture_record_tool", REGISTRY_TOOL_PATH)
agentcart = registry_record_tool.agentcart


def fixture_contract() -> dict:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def path_part(container, part: str):
    if isinstance(container, list):
        return int(part)
    return part


def set_path(document: dict, dotted_path: str, value) -> None:
    current = document
    parts = dotted_path.split(".")
    for part in parts[:-1]:
        key = path_part(current, part)
        current = current[key] if isinstance(current, list) else current.setdefault(key, {})
    current[path_part(current, parts[-1])] = value


def delete_path(document: dict, dotted_path: str) -> None:
    current = document
    parts = dotted_path.split(".")
    for part in parts[:-1]:
        key = path_part(current, part)
        current = current[key] if isinstance(current, list) else current.get(key, {})
        if not isinstance(current, (dict, list)):
            return
    key = path_part(current, parts[-1])
    if isinstance(current, list):
        del current[key]
    else:
        current.pop(key, None)


def documents_for_case(contract: dict, case: dict) -> tuple[dict, dict, dict, dict]:
    documents = copy.deepcopy(contract["base"])
    for dotted_path, value in case.get("set", {}).items():
        root, child_path = dotted_path.split(".", 1)
        set_path(documents[root], child_path, value)
    for dotted_path in case.get("delete", []):
        root, child_path = dotted_path.split(".", 1)
        delete_path(documents[root], child_path)
    return documents["record"], documents["manifest"], documents["proof"], documents["revocation"]


def direct_skill_result(record: dict, manifest: dict, proof: dict, revocation: dict, *, max_age_days: int) -> dict:
    return shopbridge_direct.command_resolve_merchant(
        {
            "registry_record": copy.deepcopy(record),
            "manifest_snapshot": copy.deepcopy(manifest),
            "proof_snapshot": copy.deepcopy(proof),
            "revocation_snapshot": copy.deepcopy(revocation),
            "registry_max_age_days": max_age_days,
        }
    )


def service_result(record: dict, manifest: dict, proof: dict, revocation: dict, *, max_age_days: int) -> dict:
    candidate = copy.deepcopy(record)
    candidate["manifest_snapshot"] = copy.deepcopy(manifest)
    candidate["proof_snapshot"] = copy.deepcopy(proof)
    candidate["revocation_snapshot"] = copy.deepcopy(revocation)
    with tempfile.TemporaryDirectory() as raw_tmp:
        service = agentcart.AgentCartService(
            registry_record_tool.minimal_config(pathlib.Path(raw_tmp), max_age_days=max_age_days)
        )
        entry = service.verify_registry_record(candidate)
    verification = entry.get("verification") if isinstance(entry.get("verification"), dict) else {}
    return {"ok": verification.get("state") == "verified", "verification": verification, "entry": entry}


def registry_tool_result(record: dict, manifest: dict, proof: dict, revocation: dict, *, max_age_days: int) -> dict:
    return registry_record_tool.verify_registry_record(
        copy.deepcopy(record),
        manifest_snapshot=copy.deepcopy(manifest),
        proof_snapshot=copy.deepcopy(proof),
        revocation_snapshot=copy.deepcopy(revocation),
        max_age_days=max_age_days,
    )


class RegistryTrustFixtureTests(unittest.TestCase):
    def test_shared_registry_fixtures_verify_consistently_across_runtimes(self) -> None:
        contract = fixture_contract()

        for case in contract["cases"]:
            with self.subTest(case=case["id"]):
                record, manifest, proof, revocation = documents_for_case(contract, case)
                max_age_days = int(case.get("max_age_days", contract.get("max_age_days", 36500)))
                expected_ok = bool(case["expected"]["ok"])
                expected_errors = set(case["expected"].get("errors", []))

                results = {
                    "service": service_result(record, manifest, proof, revocation, max_age_days=max_age_days),
                    "direct_skill": direct_skill_result(record, manifest, proof, revocation, max_age_days=max_age_days),
                    "registry_tool": registry_tool_result(record, manifest, proof, revocation, max_age_days=max_age_days),
                }

                for name, result in results.items():
                    self.assertEqual(result["ok"], expected_ok, f"{name}: {result}")
                    errors = set(result["verification"].get("errors", []))
                    self.assertTrue(expected_errors.issubset(errors), f"{name}: expected {expected_errors}, got {errors}")

    def test_public_http_registry_feeds_are_rejected_before_fetching(self) -> None:
        with mock.patch.object(shopbridge_direct, "fetch_json_url", side_effect=AssertionError("unexpected direct skill fetch")):
            with self.assertRaises(SystemExit) as direct_error:
                shopbridge_direct.registry_records_from_args({"registry_url": "http://registry.example/agentcart.json"})

        self.assertEqual(str(direct_error.exception), "registry_url_requires_https")

        with tempfile.TemporaryDirectory() as raw_tmp:
            base_config = registry_record_tool.minimal_config(pathlib.Path(raw_tmp))
            service = agentcart.AgentCartService(
                agentcart.Config(
                    **{
                        **base_config.__dict__,
                        "merchant_registry_url": "http://registry.example/agentcart.json",
                    }
                )
            )
            service.http_json = mock.Mock(side_effect=AssertionError("unexpected service fetch"))  # type: ignore[method-assign]

            with self.assertRaises(agentcart.UpstreamError) as service_error:
                service.load_registry_records()

        self.assertIn("merchant_registry_url_requires_https", str(service_error.exception))


if __name__ == "__main__":
    unittest.main()
