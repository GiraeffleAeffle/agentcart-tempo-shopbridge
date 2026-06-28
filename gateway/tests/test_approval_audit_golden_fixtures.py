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
FIXTURE_PATH = ROOT / "docs" / "fixtures" / "approval-audit" / "golden-fixtures.json"
DIRECT_SKILL_PATH = ROOT / "gateway" / "shopbridge-direct-skill" / "scripts" / "shopbridge-command.py"
REGISTRY_TOOL_PATH = ROOT / "gateway" / "scripts" / "registry_record.py"
GENERIC_MCP_EXAMPLE_PATH = ROOT / "gateway" / "examples" / "buyer-agents" / "generic-mcp-client.example.json"


def load_module(name: str, path: pathlib.Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


shopbridge_direct = load_module("approval_audit_shopbridge_direct", DIRECT_SKILL_PATH)
registry_record_tool = load_module("approval_audit_registry_record_tool", REGISTRY_TOOL_PATH)
agentcart = registry_record_tool.agentcart


def fixture_contract() -> dict:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def service_for_tmp(tmp: pathlib.Path):
    return agentcart.AgentCartService(registry_record_tool.minimal_config(tmp))


def skill_checkout_payload(contract: dict) -> dict:
    quote = copy.deepcopy(contract["final_quote"])
    expected = contract["expected_hashes"]
    decision = contract["decision"]
    return shopbridge_direct.checkout_payload(
        {
            "quote": quote,
            "payment_rail": "stripe-card-mpp",
            "approved": True,
            "approval_hash": expected["approval_hash"],
            "payment_receipt": copy.deepcopy(contract["payment_receipt"]),
            "approved_at": decision["approved_at"],
            "audit_event_timestamp": decision["audit_event_timestamp"],
            "approver": decision["approver"],
            "approval_channel": decision["channel"],
        }
    )


class ApprovalAuditGoldenFixtureTests(unittest.TestCase):
    def test_service_and_direct_skill_produce_matching_approval_hashes(self) -> None:
        contract = fixture_contract()
        quote = copy.deepcopy(contract["final_quote"])
        decision = contract["decision"]
        expected = contract["expected_hashes"]

        with tempfile.TemporaryDirectory() as raw_tmp:
            service = service_for_tmp(pathlib.Path(raw_tmp))
            service_material = service.approval_material_for_quote(quote)
            service_record = service.approval_record_for_quote(
                decision["service_approval_id"],
                quote,
                decision["policy_result"],
                channel=decision["channel"],
            )
            service_decision = service.approval_decision_record(
                {
                    "id": decision["service_approval_id"],
                    "quote_id": quote["id"],
                    "approval_hash": service_record["approval_hash"],
                    "approval_record_hash": service_record["approval_record_hash"],
                    "channel": decision["channel"],
                },
                decision="approved",
                approver=decision["approver"],
                decided_at=decision["approved_at"],
            )

        skill_material = shopbridge_direct.approval_material(quote, payment_rail="stripe-card-mpp")
        skill_packet = shopbridge_direct.approval_packet(quote, payment_rail="stripe-card-mpp")

        self.assertEqual(service_material, skill_material)
        self.assertEqual(agentcart.service_quote_hash(quote), expected["quote_hash"])
        self.assertEqual(service_record["approval_hash"], expected["approval_hash"])
        self.assertEqual(skill_packet["approval_hash"], expected["approval_hash"])
        self.assertEqual(service_record["approval_record_hash"], expected["service_approval_record_hash"])
        self.assertEqual(service_decision["decision_record_hash"], expected["service_approval_decision_hash"])
        self.assertEqual(skill_packet["approval_record_hash"], expected["skill_approval_record_hash"])

    def test_skill_payment_handoff_and_audit_packet_match_golden_hashes(self) -> None:
        contract = fixture_contract()
        quote = copy.deepcopy(contract["final_quote"])
        expected = contract["expected_hashes"]

        handoff = shopbridge_direct.command_payment_handoff(
            {
                "quote": quote,
                "payment_rail": "stripe-card-mpp",
                "approved": True,
                "approval_hash": expected["approval_hash"],
            }
        )
        checkout = skill_checkout_payload(contract)

        self.assertEqual(handoff["payment_handoff_hash"], expected["payment_handoff_hash"])
        self.assertEqual(handoff["payment_request"]["quote_hash"], expected["quote_hash"])
        self.assertEqual(handoff["payment_request"]["payment_contract_hash"], expected["payment_contract_hash"])
        self.assertEqual(checkout["approval_decision_hash"], expected["skill_approval_decision_hash"])
        self.assertEqual(checkout["audit_packet_hash"], expected["audit_packet_hash"])

    def test_tampered_audit_packet_fixture_is_rejected_before_network_import(self) -> None:
        contract = fixture_contract()
        checkout = skill_checkout_payload(contract)
        tamper = contract["tamper_case"]
        tampered = copy.deepcopy(checkout["audit_packet"])
        tampered[tamper["field"]] = tamper["value"]

        with mock.patch.object(
            shopbridge_direct,
            "agentcart_service_request_json",
            side_effect=AssertionError("network import should not be called"),
        ):
            with self.assertRaises(SystemExit) as raised:
                shopbridge_direct.command_audit_import({"audit_packet": tampered})

        self.assertEqual(str(raised.exception), tamper["expected_error"])

    def test_skill_audit_packet_import_is_idempotent_and_export_hash_is_golden(self) -> None:
        contract = fixture_contract()
        checkout = skill_checkout_payload(contract)
        expected = contract["expected_hashes"]
        fixed_now = agentcart.parse_time(contract["decision"]["imported_at"])

        with tempfile.TemporaryDirectory() as raw_tmp:
            service = service_for_tmp(pathlib.Path(raw_tmp))
            with mock.patch.object(agentcart, "utcnow", return_value=fixed_now):
                first = service.import_audit_packet(
                    {"audit_packet": checkout["audit_packet"], "source": "shopbridge-direct-skill"}
                )
                replay = service.import_audit_packet(
                    {"audit_packet": checkout["audit_packet"], "source": "shopbridge-direct-skill"}
                )
                export = service.audit_export(contract["final_quote"]["id"])

        self.assertTrue(first["imported"])
        self.assertEqual(first["event_count"], 3)
        self.assertEqual(first["audit_packet_hash"], expected["audit_packet_hash"])
        self.assertFalse(replay["imported"])
        self.assertEqual(replay["event_count"], 0)
        self.assertEqual(export["imported_packet_count"], 1)
        self.assertEqual(export["audit_export_hash"], expected["audit_export_hash"])

    def test_generic_mcp_example_references_same_required_hashes(self) -> None:
        contract = fixture_contract()
        example = json.loads(GENERIC_MCP_EXAMPLE_PATH.read_text(encoding="utf-8"))
        approval_audit = example["golden_fixtures"]["approval_audit"]

        self.assertEqual(approval_audit["fixture"], "docs/fixtures/approval-audit/golden-fixtures.json")
        self.assertEqual(set(approval_audit["required_hashes"]), set(contract["generic_mcp_required_hashes"]))


if __name__ == "__main__":
    unittest.main()
