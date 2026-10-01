from __future__ import annotations

import copy
import dataclasses
import hashlib
import importlib.util
import json
import pathlib
import sys
import tempfile
import threading
import unittest
import urllib.request

import agentcart


ROOT = pathlib.Path(__file__).resolve().parents[2]
FIXTURE_PATH = ROOT / "docs/fixtures/canonical-json/vectors.json"


def load_module(name: str, path: pathlib.Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


skill = load_module("canonical_json_direct_skill", ROOT / "gateway/shopbridge-direct-skill/scripts/shopbridge-command.py")
registry_tool = load_module("canonical_json_registry_tool", ROOT / "gateway/scripts/registry_record.py")


class CanonicalJsonTests(unittest.TestCase):
    def assert_vectors(self, canonical, hash_value) -> None:
        vectors = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
        for vector in vectors["cases"]:
            with self.subTest(vector=vector["name"]):
                self.assertEqual(canonical(vector["value"]), vector["canonical"])
                self.assertEqual(hash_value(vector["value"]), vector["sha256"])

    def test_gateway_vectors(self) -> None:
        self.assert_vectors(agentcart.canonical_json, agentcart.canonical_json_hash)

    def test_skill_command_vectors(self) -> None:
        self.assert_vectors(skill.canonical, skill.sha256_hex)

    def test_skill_registry_trust_vectors(self) -> None:
        self.assert_vectors(skill.registry_trust.canonical_json, skill.registry_trust.canonical_json_hash)

    def test_skill_onchain_projection_vectors(self) -> None:
        self.assert_vectors(skill.onchain_projection.canonical_json, skill.onchain_projection.canonical_json_hash)

    def test_non_ascii_skill_packet_import_route_and_persisted_replay(self) -> None:
        contract = json.loads((ROOT / "docs/fixtures/approval-audit/golden-fixtures.json").read_text(encoding="utf-8"))
        quote = contract["final_quote"]
        approval = skill.approval_packet(quote, payment_rail="stripe-card-mpp")["approval_record"]
        decision = skill.approval_decision_record(
            {"approver": "Jürgen Müller", "approved_at": contract["decision"]["approved_at"]}, approval
        )
        packet = skill.skill_audit_packet(
            order_id="unicode-order", quote=quote, approval_record=approval,
            decision_record=decision, receipt=contract["payment_receipt"],
            occurred_at=contract["decision"]["audit_event_timestamp"],
        )
        with tempfile.TemporaryDirectory() as raw_tmp:
            config = dataclasses.replace(
                registry_tool.minimal_config(pathlib.Path(raw_tmp)), agentcart_token="canonical-test-token"
            )
            service = agentcart.AgentCartService(config)
            server = agentcart.AgentCartServer(("127.0.0.1", 0), service)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                request = urllib.request.Request(
                    f"http://127.0.0.1:{server.server_port}/v1/audit/import",
                    data=json.dumps({"audit_packet": packet}, ensure_ascii=False).encode("utf-8"),
                    headers={"Content-Type": "application/json", "X-AgentCart-Token": config.agentcart_token},
                    method="POST",
                )
                with urllib.request.urlopen(request, timeout=5) as response:
                    self.assertEqual(response.status, 201)
                    imported = json.load(response)
                self.assertTrue(imported["imported"])
                self.assertEqual(imported["event_count"], 3)
                reloaded = agentcart.AgentCartService(config)
                export = reloaded.audit_export(quote["id"])
                self.assertEqual(export["events"][0]["actor"], "Jürgen Müller")
                self.assertEqual(export["imported_packets"][0]["audit_packet_hash"], packet["audit_packet_hash"])
                self.assertFalse(reloaded.import_audit_packet({"audit_packet": packet})["imported"])
                tampered = copy.deepcopy(packet)
                tampered["events"][0]["actor"] = "Jürgen Meier"
                with self.assertRaises(agentcart.BadRequest):
                    reloaded.import_audit_packet({"audit_packet": tampered})
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=5)

    def test_hosted_transparency_preserves_legacy_unicode_chain(self) -> None:
        legacy = {
            "schema": "agentcart.registry_transparency_event.v1", "sequence": 1,
            "previous_event_hash": "", "reason": "Jürgen Müller",
        }
        legacy["event_hash"] = hashlib.sha256(
            json.dumps(legacy, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        with tempfile.TemporaryDirectory() as raw_tmp:
            service = agentcart.AgentCartService(registry_tool.minimal_config(pathlib.Path(raw_tmp)))
            store = {"transparency_log": [legacy]}
            service.append_hosted_registry_transparency_event(
                store, operation="revoke", payload={"reason": "Straße"}, record_hash="a" * 64,
                merchant_id="unicode-merchant", domain="merchant.example", state="revoked",
                created_at="2026-09-01T00:00:00Z", revocation={"reason": "Straße"},
            )
            events = store["transparency_log"]
            self.assertTrue(service.verify_hosted_registry_transparency_events(events)["chain_valid"])
            events[0]["reason"] = "changed"
            self.assertFalse(service.verify_hosted_registry_transparency_events(events)["chain_valid"])

    def test_operator_ledger_preserves_legacy_unicode_chain(self) -> None:
        legacy = {
            "schema": registry_tool.ONCHAIN_LEDGER_EVENT_SCHEMA, "sequence": 1,
            "operation": "revoke", "record_hash": "a" * 64,
            "previous_event_hash": "", "reason": "Jürgen Müller",
        }
        legacy["event_hash"] = hashlib.sha256(
            json.dumps(legacy, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        new = registry_tool.onchain_ledger_event(
            [legacy], operation="revoke", record_hash="b" * 64,
            created_at="2026-09-01T00:00:00Z", reason="Straße",
        )
        with tempfile.TemporaryDirectory() as raw_tmp:
            path = pathlib.Path(raw_tmp) / "ledger.jsonl"
            path.write_text("\n".join(json.dumps(event) for event in [legacy, new]) + "\n", encoding="utf-8")
            events = registry_tool.load_onchain_ledger_events(path)
        self.assertTrue(registry_tool.verify_onchain_ledger_events(events)["chain_valid"])
        events[1]["reason"] = "changed"
        self.assertFalse(registry_tool.verify_onchain_ledger_events(events)["chain_valid"])

    def test_marked_ledgers_do_not_accept_ascii_or_unknown_encodings(self) -> None:
        for marker in ("shopbridge-json-v1", "unknown"):
            event = {
                "schema": registry_tool.ONCHAIN_LEDGER_EVENT_SCHEMA, "sequence": 1,
                "operation": "revoke", "record_hash": "a" * 64,
                "previous_event_hash": "", "reason": "Jürgen Müller", "canonicalization": marker,
            }
            event["event_hash"] = hashlib.sha256(
                json.dumps(
                    event, sort_keys=True, separators=(",", ":"), ensure_ascii=marker == "shopbridge-json-v1"
                ).encode("utf-8")
            ).hexdigest()
            with self.subTest(marker=marker):
                self.assertFalse(registry_tool.verify_onchain_ledger_events([event])["chain_valid"])

    def seed_refund_order(self, service) -> str:
        order_id = "unicode-refund-order"
        service.state["orders"][order_id] = {
            "id": order_id, "merchant_id": "demo-tea-shop", "total_cents": 1000,
            "quote_id": "unicode-refund-quote",
            "currency": "EUR", "state": "placed", "refunds": [],
        }
        return order_id

    def test_legacy_unicode_refund_request_replays_after_reload(self) -> None:
        request = {"idempotency_key": "legacy-refund", "amount_cents": 100, "reason": "Rücksendung"}
        with tempfile.TemporaryDirectory() as raw_tmp:
            config = registry_tool.minimal_config(pathlib.Path(raw_tmp))
            service = agentcart.AgentCartService(config)
            order_id = self.seed_refund_order(service)
            refund = {"id": "legacy-refund-record", "amount_cents": 100, "reason": "Rücksendung"}
            service.state["orders"][order_id]["refunds"] = [refund]
            material = {"order_id": order_id, "request": request}
            legacy_hash = hashlib.sha256(
                json.dumps(material, sort_keys=True, separators=(",", ":")).encode("utf-8")
            ).hexdigest()
            service.state["refund_idempotency"]["legacy-refund"] = {
                "order_id": order_id, "refund_id": refund["id"], "request_hash": legacy_hash,
            }
            service.save_state()
            reloaded = agentcart.AgentCartService(config)
            replay = reloaded.refund_order(order_id, request)
            self.assertTrue(replay["idempotent_replay"])
            self.assertEqual(replay["refund"]["id"], refund["id"])
            self.assertEqual(replay["order"]["refunds"], [refund])
            with self.assertRaises(agentcart.Conflict):
                reloaded.refund_order(order_id, {**request, "reason": "Andere Rücksendung"})

    def test_new_unicode_refund_replays_but_changed_request_conflicts(self) -> None:
        request = {"idempotency_key": "new-refund", "amount_cents": 100, "reason": "Rücksendung"}
        with tempfile.TemporaryDirectory() as raw_tmp:
            config = registry_tool.minimal_config(pathlib.Path(raw_tmp))
            service = agentcart.AgentCartService(config)
            order_id = self.seed_refund_order(service)
            first = service.refund_order(order_id, request)
            reloaded = agentcart.AgentCartService(config)
            replay = reloaded.refund_order(order_id, request)
            self.assertTrue(replay["idempotent_replay"])
            self.assertEqual(replay["refund"]["id"], first["refund"]["id"])
            self.assertEqual(replay["order"]["refunds"], [first["refund"]])
            with self.assertRaises(agentcart.Conflict):
                reloaded.refund_order(order_id, {**request, "reason": "Andere Rücksendung"})

    def test_refund_replay_rejects_unknown_or_missing_encoding_markers(self) -> None:
        request = {"idempotency_key": "invalid-encoding-refund", "amount_cents": 100, "reason": "Rücksendung"}
        with tempfile.TemporaryDirectory() as raw_tmp:
            config = registry_tool.minimal_config(pathlib.Path(raw_tmp))
            service = agentcart.AgentCartService(config)
            order_id = self.seed_refund_order(service)
            service.refund_order(order_id, request)
            entry = service.state["refund_idempotency"][request["idempotency_key"]]
            # A newly generated UTF-8 request hash must not be accepted as an
            # unmarked historical ASCII hash, or under an unknown marker.
            del entry["canonicalization"]
            with self.assertRaises(agentcart.Conflict):
                service.refund_order(order_id, request)
            entry["canonicalization"] = "unknown"
            with self.assertRaises(agentcart.Conflict):
                service.refund_order(order_id, request)
            entry["request_hash"] = ""
            with self.assertRaises(agentcart.Conflict):
                service.refund_order(order_id, request)


if __name__ == "__main__":
    unittest.main()
