from __future__ import annotations

import copy
import importlib.util
import json
import pathlib
import sys
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
FIXTURE_PATH = ROOT / "docs" / "fixtures" / "aftercare" / "state-fixtures.json"
DIRECT_SKILL_PATH = ROOT / "gateway" / "shopbridge-direct-skill" / "scripts" / "shopbridge-command.py"
REGISTRY_TOOL_PATH = ROOT / "gateway" / "scripts" / "registry_record.py"
PLUGIN_PATH = ROOT / "woocommerce-shopbridge" / "agentcart-shopbridge" / "agentcart-shopbridge.php"


def load_module(name: str, path: pathlib.Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


shopbridge_direct = load_module("aftercare_fixture_shopbridge_direct", DIRECT_SKILL_PATH)
registry_record_tool = load_module("aftercare_fixture_registry_record_tool", REGISTRY_TOOL_PATH)
agentcart = registry_record_tool.agentcart


def fixture_contract() -> dict:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def service_for_tmp(tmp: pathlib.Path):
    return agentcart.AgentCartService(registry_record_tool.minimal_config(tmp))


def direct_order_from_service_order(order: dict, aftercare_state: dict) -> dict:
    direct_order = copy.deepcopy(order)
    shipment = direct_order.get("shipment") if isinstance(direct_order.get("shipment"), dict) else {}
    direct_order["fulfillment"] = {
        "state": shipment.get("status") or "",
        "carrier": shipment.get("carrier") or "",
        "tracking_number": shipment.get("tracking_number") or "",
        "tracking_url": shipment.get("tracking_url") or "",
        "tracking_status": shipment.get("tracking_status") or shipment.get("status") or "",
        "tracking": shipment.get("tracking") if isinstance(shipment.get("tracking"), dict) else {},
        "has_delivery_exception": bool(shipment.get("has_delivery_exception")),
        "delivery_exception": shipment.get("delivery_exception") if isinstance(shipment.get("delivery_exception"), dict) else None,
        "source": shipment.get("source") or "",
        "note": shipment.get("note") or "",
    }
    direct_order["aftercare_state"] = copy.deepcopy(aftercare_state)
    direct_order["refund_policy"] = {
        "requires_merchant_token": True,
        "remaining_refundable_cents": aftercare_state.get("remaining_refundable_cents", 0),
        "currency": aftercare_state.get("currency") or order.get("currency") or "EUR",
        "merchant_review_required": True,
        "merchant_policy": order.get("merchant_policy") if isinstance(order.get("merchant_policy"), dict) else {},
    }
    direct_order["cancellation_policy"] = {
        "eligible": aftercare_state.get("cancellation_state") == "cancellable_before_fulfillment",
        "requires_merchant_token": True,
        "idempotency_required": True,
        "does_not_execute_refund": True,
        "paid_order_requires_separate_refund": bool(aftercare_state.get("refund_required_after_cancellation")),
        "eligibility": {
            "blocking_reasons": aftercare_state.get("blocking_reasons", []),
            "advertised_request_window_minutes": 30,
        },
    }
    receipt = order.get("payment_receipt") if isinstance(order.get("payment_receipt"), dict) else {}
    if receipt:
        direct_order["payment_verification"] = {
            "rail": receipt.get("method") or "",
            "transaction_reference": receipt.get("id") or "",
            "real_settlement_verified": True,
        }
    return direct_order


def assert_message_contains(testcase: unittest.TestCase, messages: dict, expected_text: str) -> None:
    combined = "\n".join(str(value) for key, value in messages.items() if key != "allowed_claims")
    testcase.assertIn(expected_text, combined)


class AftercareStateFixtureTests(unittest.TestCase):
    def test_fixture_set_names_all_canonical_aftercare_states(self) -> None:
        contract = fixture_contract()

        self.assertEqual(contract["schema"], "agentcart.aftercare_state_fixtures.v1")
        self.assertEqual(contract["state_contract"], "agentcart.aftercare_state_contract.v1")
        self.assertEqual(
            {case["id"] for case in contract["cases"]},
            {
                "unpaid-demo-state",
                "paid-order",
                "delayed-delivery",
                "shipped-tracking",
                "cancellation-requested",
                "partial-refund",
                "verified-refund",
                "refund-failure",
            },
        )

    def test_agentcart_service_aftercare_state_matches_fixtures(self) -> None:
        contract = fixture_contract()
        with tempfile.TemporaryDirectory() as raw_tmp:
            service = service_for_tmp(pathlib.Path(raw_tmp))

            for case in contract["cases"]:
                with self.subTest(case=case["id"]):
                    order = copy.deepcopy(case["order"])
                    expected = case["expected"]

                    state = service.aftercare_state(order)
                    messages = state["buyer_aftercare_messages"]
                    claims = messages["allowed_claims"]

                    for field in (
                        "order_lifecycle_state",
                        "fulfillment_phase",
                        "refund_state",
                        "cancellation_state",
                    ):
                        self.assertEqual(state[field], expected[field])
                    for field in (
                        "remaining_refundable_cents",
                        "refund_required_after_cancellation",
                        "delivery_exception_state",
                        "delivery_exception_requires_attention",
                    ):
                        if field in expected:
                            self.assertEqual(state[field], expected[field])
                    self.assertEqual(claims["refund_executed"], expected["refund_executed"])
                    self.assertEqual(claims["money_returned"], expected["money_returned"])
                    if "latest_refund_reference" in expected:
                        self.assertEqual(claims["latest_refund_reference"], expected["latest_refund_reference"])
                    self.assertEqual(state["data_trust"]["merchant_text"], "untrusted")
                    self.assertFalse(state["data_trust"]["instructions_allowed"])
                    assert_message_contains(self, messages, expected["message_contains"])

    def test_direct_skill_aftercare_summary_matches_fixtures(self) -> None:
        contract = fixture_contract()
        with tempfile.TemporaryDirectory() as raw_tmp:
            service = service_for_tmp(pathlib.Path(raw_tmp))

            for case in contract["cases"]:
                with self.subTest(case=case["id"]):
                    order = copy.deepcopy(case["order"])
                    expected = case["expected"]
                    state = service.aftercare_state(order)
                    direct_order = direct_order_from_service_order(order, state)

                    result = shopbridge_direct.command_aftercare_summary({"order": direct_order})
                    messages = result["buyer_aftercare_messages"]
                    claims = messages["allowed_claims"]
                    action_ids = {
                        str(action.get("id") or "")
                        for action in result["next_actions"]
                        if isinstance(action, dict)
                    }

                    for field in (
                        "order_lifecycle_state",
                        "fulfillment_phase",
                        "refund_state",
                        "cancellation_state",
                    ):
                        self.assertEqual(result["aftercare_state"][field], expected[field])
                    self.assertEqual(claims["refund_executed"], expected["refund_executed"])
                    self.assertEqual(claims["money_returned"], expected["money_returned"])
                    self.assertEqual(result["data_trust"]["merchant_text"], "untrusted")
                    self.assertEqual(result["merchant_policy"]["data_trust"]["merchant_text"], "untrusted")
                    self.assertFalse(result["merchant_policy"]["data_trust"]["instructions_allowed"])
                    assert_message_contains(self, messages, expected["message_contains"])
                    for action_id in expected.get("next_actions", []):
                        self.assertIn(action_id, action_ids)
                    if "tracking" in expected:
                        for field, value in expected["tracking"].items():
                            self.assertEqual(result["fulfillment"][field], value)

    def test_shopbridge_plugin_exposes_same_aftercare_contract_fields(self) -> None:
        plugin = PLUGIN_PATH.read_text(encoding="utf-8")

        for token in (
            "'aftercare_state_contract' => true",
            "'order_lifecycle_state'",
            "'fulfillment_phase'",
            "'cancellation_state'",
            "'refund_state'",
            "'refund_progress'",
            "'cancellation_does_not_execute_refund' => true",
            "'rail_refund_requires_verifier' => true",
            "'delivery_exception_state'",
            "'delivery_exception_requires_attention'",
            "'buyer_aftercare_messages'",
            "'allowed_claims'",
            "'data_trust'",
            "'merchant_text' => 'untrusted'",
            "'instructions_allowed' => false",
            "'display_or_summarize_only' => true",
            "normalize_tracking_status",
            "delivery_exception_from_tracking",
        ):
            self.assertIn(token, plugin)


if __name__ == "__main__":
    unittest.main()
