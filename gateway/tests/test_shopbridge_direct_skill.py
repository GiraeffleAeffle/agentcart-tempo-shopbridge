from __future__ import annotations

import importlib.util
import json
import sys
import unittest
from pathlib import Path
from unittest import mock


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "shopbridge-direct-skill" / "scripts" / "shopbridge-command.py"
SPEC = importlib.util.spec_from_file_location("shopbridge_direct_command", SCRIPT_PATH)
assert SPEC and SPEC.loader
shopbridge_direct = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = shopbridge_direct
SPEC.loader.exec_module(shopbridge_direct)


def sample_quote(**overrides):
    quote = {
        "id": "woo_quote_123",
        "merchant": {"id": "merchant-1", "name": "AgentCart Demo Shop"},
        "items": [
            {
                "product_id": "woo_10",
                "title": "Hazel's Chocolate Tea",
                "quantity": 1,
                "line_total_cents": 990,
            }
        ],
        "subtotal_cents": 990,
        "shipping": {"amount_cents": 490},
        "total_cents": 1480,
        "currency": "EUR",
        "delivery_window": {"label": "2-4 business days"},
        "expires_at": "2999-01-01T00:00:00+00:00",
        "quote_hash": "quote-hash-123",
        "payment_requirements": {
            "verification": {"external_verifier_configured": True},
            "protocols": [
                {"id": "stripe-card-mpp", "available": True},
                {"id": "tempo-mpp", "available": True},
            ],
        },
    }
    quote.update(overrides)
    return quote


class ShopBridgeDirectSkillTests(unittest.TestCase):
    def test_approval_hash_changes_when_total_changes(self) -> None:
        first = shopbridge_direct.approval_packet(sample_quote())["approval_hash"]
        second = shopbridge_direct.approval_packet(sample_quote(total_cents=1490))["approval_hash"]
        self.assertNotEqual(first, second)

    def test_checkout_payload_requires_matching_approval_hash(self) -> None:
        quote = sample_quote()
        receipt = {
            "method": "stripe-card-mpp",
            "status": "succeeded",
            "amount_cents": 1480,
            "currency": "EUR",
            "quote_hash": "quote-hash-123",
            "authorization": "opaque-test-credential",
        }
        with self.assertRaises(SystemExit):
            shopbridge_direct.checkout_payload(
                {"quote": quote, "approved": True, "approval_hash": "wrong", "payment_receipt": receipt}
            )

        approval_hash = shopbridge_direct.approval_packet(quote)["approval_hash"]
        payload = shopbridge_direct.checkout_payload(
            {"quote": quote, "approved": True, "approval_hash": approval_hash, "payment_receipt": receipt}
        )
        self.assertEqual(payload["agentcart_order_id"], f"skill_{approval_hash[:24]}")
        self.assertEqual(payload["payment_receipt"]["amount_cents"], 1480)

    def test_payment_receipt_must_match_quote(self) -> None:
        quote = sample_quote()
        approval_hash = shopbridge_direct.approval_packet(quote)["approval_hash"]
        with self.assertRaises(SystemExit):
            shopbridge_direct.checkout_payload(
                {
                    "quote": quote,
                    "approved": True,
                    "approval_hash": approval_hash,
                    "payment_receipt": {
                        "amount_cents": 1479,
                        "currency": "EUR",
                        "quote_hash": "quote-hash-123",
                    },
                }
            )

    def test_mppx_output_fails_closed_without_reference(self) -> None:
        receipt = shopbridge_direct.base64.urlsafe_b64encode(
            json.dumps({"method": "tempo", "status": "success"}).encode()
        ).decode().rstrip("=")
        output = f"HTTP/1.1 200 OK\npayment-receipt: {receipt}\n\n{{\"ok\":true}}\n"
        with self.assertRaises(SystemExit):
            shopbridge_direct.parse_mppx_output(output)

    def test_checkout_preflight_requires_external_verifier(self) -> None:
        quote = sample_quote(
            payment_requirements={
                "verification": {"external_verifier_configured": False},
                "protocols": [{"id": "tempo-mpp", "available": True}],
            }
        )
        result = shopbridge_direct.command_checkout_preflight({"quote": quote, "payment_rail": "tempo-mpp"})
        self.assertFalse(result["ok"])
        self.assertIn("external_verifier_required_for_public_checkout", result["issues"])

    def test_order_status_sends_status_token_header(self) -> None:
        calls = []

        def fake_request(path, *, method="GET", payload=None, headers=None):
            calls.append({"path": path, "headers": headers})
            return {"ok": True}

        with mock.patch.object(shopbridge_direct, "request_json", side_effect=fake_request):
            result = shopbridge_direct.command_order_status(
                {"order_id": "123", "status_token": "status-token-abc"}
            )

        self.assertEqual(result, {"ok": True})
        self.assertEqual(calls[0]["path"], "/wp-json/agentcart/v1/orders/123/status")
        self.assertEqual(calls[0]["headers"], {"X-AgentCart-Order-Token": "status-token-abc"})


if __name__ == "__main__":
    unittest.main()
