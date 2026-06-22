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
                {
                    "id": "stripe-card-mpp",
                    "available": True,
                    "network_id": "acct_shop_123",
                    "stripe_profile_id": "acct_shop_123",
                },
                {
                    "id": "tempo-mpp",
                    "available": True,
                    "network": "testnet",
                    "recipient": "0x1111111111111111111111111111111111111111",
                },
            ],
        },
    }
    quote.update(overrides)
    return quote


def registry_manifest_and_record(
    *,
    merchant_id: str = "merchant-tea-shop",
    name: str = "Merchant Tea Shop",
    domain: str = "merchant.example",
    stripe_profile_id: str = "acct_shop_123",
):
    claim = {
        "merchant_id": merchant_id,
        "name": name,
        "domain": domain,
        "manifest_url": f"https://{domain}/.well-known/agentcart.json",
        "endpoints": {
            "catalog": f"https://{domain}/wp-json/agentcart/v1/catalog",
            "quote": f"https://{domain}/wp-json/agentcart/v1/quote",
            "orders": f"https://{domain}/wp-json/agentcart/v1/orders",
        },
        "supported_protocols": ["agentcart-shopbridge", "stripe-card-mpp"],
        "payment_network": "testnet",
        "payment_recipient": "",
        "stripe_profile_id": stripe_profile_id,
        "ship_to_countries": ["DE"],
        "proof_url": f"https://{domain}/.well-known/agentcart-registry-proof.json",
    }
    record = {
        **claim,
        "registry_claim_hash_alg": "sha-256",
        "registry_claim_hash": shopbridge_direct.sha256_hex(claim),
        "updated_at": "2999-01-01T00:00:00Z",
        "revoked_at": None,
        "signature_alg": "https-domain-proof",
        "signature": "",
        "proof": {
            "type": "https-well-known",
            "url": f"https://{domain}/.well-known/agentcart-registry-proof.json",
        },
    }
    manifest = {
        "merchant": {"id": merchant_id, "name": name},
        "manifest_url": f"https://{domain}/.well-known/agentcart.json",
        "protocols": [
            {"id": "agentcart-shopbridge"},
            {"id": "stripe-card-mpp", "network_id": stripe_profile_id},
        ],
        "delivery": {"ship_to_countries": ["DE"]},
        "endpoints": claim["endpoints"],
        "discovery": {
            "registry_claim_hash_alg": "sha-256",
            "registry_claim_hash": record["registry_claim_hash"],
            "registry_claim": claim,
            "suggested_registry_record": record,
        },
    }
    proof = {
        "merchant_id": record["merchant_id"],
        "domain": record["domain"],
        "manifest_url": record["manifest_url"],
        "registry_claim_hash": record["registry_claim_hash"],
        "payment_network": record["payment_network"],
        "payment_recipient": record["payment_recipient"],
        "updated_at": record["updated_at"],
        "record_hash": shopbridge_direct.registry_record_hash(record),
    }
    return manifest, record, proof


def sample_order_status(**overrides):
    order = {
        "id": "123",
        "number": "1001",
        "status": "processing",
        "payment_status": "paid",
        "status_url": "https://merchant.example/wp-json/agentcart/v1/orders/123/status",
        "fulfillment": {
            "state": "preparing",
            "order_status": "processing",
            "carrier": "",
            "tracking_number": "",
            "tracking_url": "",
            "estimated_delivery_window": {
                "label": "2-4 business days",
                "earliest_date": "2999-01-03",
                "latest_date": "2999-01-05",
            },
            "note": "No carrier tracking metadata is attached yet.",
        },
        "payment_verification": {
            "rail": "stripe-card-mpp",
            "transaction_reference": "pi_test_123",
            "real_settlement_verified": True,
        },
        "refund_policy": {
            "endpoint": "https://merchant.example/wp-json/agentcart/v1/orders/123/refunds",
            "requires_merchant_token": True,
            "remaining_refundable_cents": 1480,
            "currency": "EUR",
        },
        "refunds": [],
    }
    order.update(overrides)
    return order


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
            "stripe_profile_id": "acct_shop_123",
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
        self.assertEqual(payload["rail"], "stripe-card-mpp")
        self.assertEqual(payload["payment_destination"]["stripe_profile_id"], "acct_shop_123")

    def test_approval_packet_binds_stripe_payment_destination(self) -> None:
        packet = shopbridge_direct.approval_packet(sample_quote(), payment_rail="stripe-card-mpp")

        self.assertEqual(packet["approval_material"]["payment_destination"]["rail"], "stripe-card-mpp")
        self.assertEqual(packet["approval_material"]["payment_destination"]["stripe_profile_id"], "acct_shop_123")
        self.assertIn("acct_shop_123", packet["summary"])

    def test_checkout_payload_rejects_wrong_stripe_destination(self) -> None:
        quote = sample_quote()
        approval_hash = shopbridge_direct.approval_packet(quote, payment_rail="stripe-card-mpp")["approval_hash"]

        with self.assertRaises(SystemExit):
            shopbridge_direct.checkout_payload(
                {
                    "quote": quote,
                    "payment_rail": "stripe-card-mpp",
                    "approved": True,
                    "approval_hash": approval_hash,
                    "payment_receipt": {
                        "method": "stripe-card-mpp",
                        "amount_cents": 1480,
                        "currency": "EUR",
                        "quote_hash": "quote-hash-123",
                        "stripe_profile_id": "acct_wrong",
                    },
                }
            )

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

    def test_checkout_preflight_reports_selected_payment_destination(self) -> None:
        result = shopbridge_direct.command_checkout_preflight(
            {"quote": sample_quote(), "payment_rail": "stripe-card-mpp"}
        )

        self.assertTrue(result["ok"], result)
        self.assertEqual(result["payment_destination"]["rail"], "stripe-card-mpp")
        self.assertEqual(result["payment_destination"]["stripe_profile_id"], "acct_shop_123")

    def test_resolve_merchant_verifies_registry_record_and_returns_base_url(self) -> None:
        manifest, record, proof = registry_manifest_and_record()

        result = shopbridge_direct.command_resolve_merchant(
            {
                "registry_record": record,
                "manifest_snapshot": manifest,
                "proof_snapshot": proof,
            }
        )

        self.assertTrue(result["ok"], result)
        self.assertEqual(result["base_url"], "https://merchant.example")
        self.assertEqual(result["merchant"]["id"], "merchant-tea-shop")
        self.assertEqual(result["verification"]["state"], "verified")

    def test_resolve_merchant_rejects_bad_domain_proof_hash(self) -> None:
        manifest, record, proof = registry_manifest_and_record()
        proof["record_hash"] = "0" * 64

        result = shopbridge_direct.command_resolve_merchant(
            {
                "registry_record": record,
                "manifest_snapshot": manifest,
                "proof_snapshot": proof,
            }
        )

        self.assertFalse(result["ok"], result)
        self.assertIn("domain_proof_record_hash_mismatch", result["verification"]["errors"])

    def test_resolve_merchant_rejects_external_http_without_fetching(self) -> None:
        _manifest, record, _proof = registry_manifest_and_record()
        record["manifest_url"] = "http://merchant.example/.well-known/agentcart.json"
        record["proof"]["url"] = "http://merchant.example/.well-known/agentcart-registry-proof.json"

        with mock.patch.object(shopbridge_direct, "fetch_json_url", side_effect=AssertionError("unexpected fetch")):
            result = shopbridge_direct.command_resolve_merchant({"registry_record": record})

        self.assertFalse(result["ok"], result)
        self.assertIn("manifest_url_requires_https", result["verification"]["errors"])
        self.assertIn("domain_proof_url_requires_https", result["verification"]["errors"])

    def test_catalog_uses_resolved_base_url(self) -> None:
        calls = []

        def fake_request(path, *, method="GET", payload=None, headers=None, base_url=None):
            calls.append({"path": path, "base_url": base_url})
            return {"merchant": {"name": "Merchant Tea Shop"}, "products": []}

        with mock.patch.object(shopbridge_direct, "request_json", side_effect=fake_request):
            result = shopbridge_direct.command_catalog(
                {"base_url": "https://merchant.example", "search": "tea"}
            )

        self.assertEqual(result["merchant"]["name"], "Merchant Tea Shop")
        self.assertEqual(calls[0]["base_url"], "https://merchant.example")
        self.assertIn("search=tea", calls[0]["path"])

    def test_discover_quotes_ranks_verified_merchants_and_returns_winner_quote(self) -> None:
        manifest_a, record_a, proof_a = registry_manifest_and_record(
            merchant_id="shop-a",
            name="Alpha Tea",
            domain="alpha.example",
            stripe_profile_id="acct_alpha",
        )
        manifest_b, record_b, proof_b = registry_manifest_and_record(
            merchant_id="shop-b",
            name="Beta Tea",
            domain="beta.example",
            stripe_profile_id="acct_beta",
        )
        calls = []

        def payment_requirements(profile_id):
            return {
                "verification": {"external_verifier_configured": True},
                "protocols": [
                    {
                        "id": "stripe-card-mpp",
                        "available": True,
                        "network_id": profile_id,
                        "stripe_profile_id": profile_id,
                    }
                ],
            }

        def fake_request(path, *, method="GET", payload=None, headers=None, base_url=None):
            calls.append({"path": path, "method": method, "payload": payload, "base_url": base_url})
            if path.startswith("/wp-json/agentcart/v1/catalog"):
                if base_url == "https://alpha.example":
                    return {
                        "merchant": {"id": "shop-a", "name": "Alpha Tea"},
                        "products": [
                            {
                                "id": "alpha-tea",
                                "title": "Alpha Tea Tin",
                                "eligible_for_agent_checkout": True,
                                "shipping_regions": ["DE"],
                            }
                        ],
                    }
                return {
                    "merchant": {"id": "shop-b", "name": "Beta Tea"},
                    "products": [
                        {
                            "id": "beta-tea",
                            "title": "Beta Tea Tin",
                            "eligible_for_agent_checkout": True,
                            "shipping_regions": ["DE"],
                        }
                    ],
                }
            product_id = payload["items"][0]["product_id"]
            if product_id == "alpha-tea":
                return sample_quote(
                    id="quote-alpha",
                    merchant={"id": "shop-a", "name": "Alpha Tea"},
                    items=[
                        {
                            "product_id": "alpha-tea",
                            "title": "Alpha Tea Tin",
                            "quantity": 1,
                            "line_total_cents": 1090,
                        }
                    ],
                    subtotal_cents=1090,
                    total_cents=1580,
                    quote_hash="hash-alpha",
                    payment_requirements=payment_requirements("acct_alpha"),
                )
            return sample_quote(
                id="quote-beta",
                merchant={"id": "shop-b", "name": "Beta Tea"},
                items=[
                    {
                        "product_id": "beta-tea",
                        "title": "Beta Tea Tin",
                        "quantity": 1,
                        "line_total_cents": 890,
                    }
                ],
                subtotal_cents=890,
                total_cents=1380,
                quote_hash="hash-beta",
                payment_requirements=payment_requirements("acct_beta"),
            )

        with mock.patch.object(shopbridge_direct, "request_json", side_effect=fake_request):
            result = shopbridge_direct.command_discover_quotes(
                {
                    "registry_records": [record_a, record_b],
                    "manifest_snapshots": {"shop-a": manifest_a, "shop-b": manifest_b},
                    "proof_snapshots": {"shop-a": proof_a, "shop-b": proof_b},
                    "query": "tea",
                    "country": "DE",
                    "postal_code": "10115",
                    "payment_rail": "stripe-card-mpp",
                }
            )

        self.assertEqual(len(result["candidates"]), 2)
        self.assertEqual(result["winner"]["quote_id"], "quote-beta")
        self.assertEqual(result["winner"]["quote"]["id"], "quote-beta")
        self.assertEqual(
            result["winner"]["approval_packet"]["approval_material"]["payment_destination"]["stripe_profile_id"],
            "acct_beta",
        )
        self.assertEqual(result["candidates"][0]["rank"], 1)
        self.assertFalse(result["winner"]["registry"]["paid_placement"])
        self.assertEqual([call["base_url"] for call in calls if call["method"] == "POST"], ["https://alpha.example", "https://beta.example"])

    def test_discover_quotes_rejects_unverified_merchants_before_catalog_or_quote(self) -> None:
        manifest, record, proof = registry_manifest_and_record()
        proof["record_hash"] = "0" * 64

        with mock.patch.object(shopbridge_direct, "request_json", side_effect=AssertionError("unexpected merchant call")):
            result = shopbridge_direct.command_discover_quotes(
                {
                    "registry_records": [record],
                    "manifest_snapshots": {"merchant-tea-shop": manifest},
                    "proof_snapshots": {"merchant-tea-shop": proof},
                    "query": "tea",
                }
            )

        self.assertEqual(result["candidates"], [])
        self.assertEqual(result["rejected"][0]["reason"], "merchant registry verification failed")
        self.assertIn("domain_proof_record_hash_mismatch", result["rejected"][0]["detail"]["errors"])

    def test_order_status_sends_status_token_header(self) -> None:
        calls = []

        def fake_request(path, *, method="GET", payload=None, headers=None, base_url=None):
            calls.append({"path": path, "headers": headers, "base_url": base_url})
            return {"ok": True}

        with mock.patch.object(shopbridge_direct, "request_json", side_effect=fake_request):
            result = shopbridge_direct.command_order_status(
                {"order_id": "123", "status_token": "status-token-abc"}
            )

        self.assertEqual(result, {"ok": True})
        self.assertEqual(calls[0]["path"], "/wp-json/agentcart/v1/orders/123/status")
        self.assertEqual(calls[0]["headers"], {"X-AgentCart-Order-Token": "status-token-abc"})
        self.assertEqual(calls[0]["base_url"], shopbridge_direct.BASE_URL)

    def test_aftercare_summary_reports_safe_next_actions_and_refund_draft(self) -> None:
        result = shopbridge_direct.command_aftercare_summary(
            {
                "order": sample_order_status(),
                "merchant": {
                    "name": "Merchant Tea Shop",
                    "merchant_of_record": {"support_email": "support@example.test"},
                    "returns_url": "https://merchant.example/returns",
                },
                "refund_reason": "Item damaged",
                "refund_amount_cents": 500,
            }
        )

        self.assertEqual(result["order"]["id"], "123")
        self.assertEqual(result["fulfillment"]["state"], "preparing")
        self.assertEqual(result["refund"]["remaining"], "14.80 EUR")
        self.assertTrue(result["refund"]["requires_merchant_or_gateway"])
        self.assertEqual(result["support"]["email"], "support@example.test")
        self.assertEqual(result["payment_proof"]["transaction_reference"], "pi_test_123")
        self.assertEqual(result["refund_request_draft"]["amount"], "5.00 EUR")
        self.assertIn("does not call merchant-token refund endpoints", result["safety_note"])
        self.assertIn("request_refund", {action["id"] for action in result["next_actions"]})

    def test_aftercare_summary_can_fetch_order_status(self) -> None:
        calls = []

        def fake_request(path, *, method="GET", payload=None, headers=None, base_url=None):
            calls.append({"path": path, "headers": headers, "base_url": base_url})
            return sample_order_status()

        with mock.patch.object(shopbridge_direct, "request_json", side_effect=fake_request):
            result = shopbridge_direct.command_aftercare_summary(
                {
                    "base_url": "https://merchant.example",
                    "order_id": "123",
                    "status_token": "status-token-abc",
                }
            )

        self.assertEqual(result["order"]["id"], "123")
        self.assertEqual(calls[0]["path"], "/wp-json/agentcart/v1/orders/123/status")
        self.assertEqual(calls[0]["headers"], {"X-AgentCart-Order-Token": "status-token-abc"})
        self.assertEqual(calls[0]["base_url"], "https://merchant.example")


if __name__ == "__main__":
    unittest.main()
