from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "shopbridge-direct-skill" / "scripts" / "shopbridge-command.py"
SPEC = importlib.util.spec_from_file_location("shopbridge_direct_command", SCRIPT_PATH)
assert SPEC and SPEC.loader
shopbridge_direct = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = shopbridge_direct
SPEC.loader.exec_module(shopbridge_direct)


def registry_updated_at() -> str:
    return shopbridge_direct.utcnow().replace(microsecond=0).isoformat().replace("+00:00", "Z")


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


def sample_payment_receipt(**overrides):
    receipt = {
        "method": "stripe-card-mpp",
        "status": "succeeded",
        "amount_cents": 1480,
        "currency": "EUR",
        "quote_hash": "quote-hash-123",
        "stripe_profile_id": "acct_shop_123",
        "authorization": "opaque-test-credential",
    }
    receipt.update(overrides)
    return receipt


def sample_x402_quote():
    return sample_quote(
        payment_requirements={
            "verification": {"external_verifier_configured": True},
            "x402": {
                "enabled": True,
                "version": 2,
                "payment_required_header": "PAYMENT-REQUIRED",
                "payment_signature_header": "PAYMENT-SIGNATURE",
                "payment_response_header": "PAYMENT-RESPONSE",
                "payment_required_header_value": "encoded-payment-required",
                "payment_required": {
                    "x402Version": 2,
                    "accepts": [
                        {
                            "scheme": "exact",
                            "network": "eip155:84532",
                            "maxAmountRequired": "14800000",
                            "resource": "https://merchant.example/wp-json/agentcart/v1/orders",
                            "description": "AgentCart ShopBridge checkout",
                            "payTo": "0x1111111111111111111111111111111111111111",
                            "asset": "0x2222222222222222222222222222222222222222",
                            "maxTimeoutSeconds": 300,
                        }
                    ],
                    "error": "PAYMENT-SIGNATURE header or quote-bound payment_receipt is required",
                },
            },
            "protocols": [
                {
                    "id": "x402-compatible",
                    "available": True,
                    "network": "eip155:84532",
                    "asset": "0x2222222222222222222222222222222222222222",
                    "pay_to": "0x1111111111111111111111111111111111111111",
                    "max_amount_required": "14800000",
                    "payment_required_header": "PAYMENT-REQUIRED",
                    "payment_signature_header": "PAYMENT-SIGNATURE",
                    "payment_response_header": "PAYMENT-RESPONSE",
                }
            ],
        }
    )


def registry_manifest_and_record(
    *,
    merchant_id: str = "merchant-tea-shop",
    name: str = "Merchant Tea Shop",
    domain: str = "merchant.example",
    stripe_profile_id: str = "acct_shop_123",
    updated_at: str | None = None,
):
    updated_at = updated_at or registry_updated_at()
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
        "protocol_profile_ids": ["agentcart-shopbridge", "stripe-card-mpp"],
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
        "updated_at": updated_at,
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
        "protocol_profiles": [
            {
                "id": "agentcart-shopbridge",
                "type": "commerce",
                "status": "available",
            },
            {
                "id": "stripe-card-mpp",
                "type": "payment",
                "status": "available",
                "payment_protocol_id": "stripe-card-mpp",
                "network_id": stripe_profile_id,
            },
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


def attach_revocation_url(manifest, record, proof, *, domain: str = "merchant.example"):
    revocation_url = f"https://{domain}/.well-known/agentcart-registry-revocations.json"
    claim = manifest["discovery"]["registry_claim"]
    claim["revocation_url"] = revocation_url
    record["revocation_url"] = revocation_url
    record["registry_claim_hash"] = shopbridge_direct.sha256_hex(claim)
    manifest["discovery"]["registry_claim_hash"] = record["registry_claim_hash"]
    manifest["discovery"]["suggested_registry_record"] = record
    proof["registry_claim_hash"] = record["registry_claim_hash"]
    proof["revocation_url"] = revocation_url
    proof["record_hash"] = shopbridge_direct.registry_record_hash(record)
    return {
        "type": "agentcart-registry-revocations",
        "merchant_id": record["merchant_id"],
        "domain": record["domain"],
        "updated_at": record["updated_at"],
        "revocations": [],
    }


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
        "aftercare_state": {
            "fulfillment_phase": "pre_fulfillment",
            "cancellation_state": "cancellable_before_fulfillment",
            "refund_state": "refund_available",
            "remaining_refundable_cents": 1480,
            "fulfillment_locked": False,
            "refund_required_if_cancelled": True,
            "cancellation_does_not_execute_refund": True,
            "rail_refund_requires_verifier": True,
            "blocking_reasons": [],
            "next_actions": ["check_status_later", "request_cancellation", "request_refund"],
        },
        "merchant_policy": {
            "returns_url": "https://merchant.example/returns",
            "refunds": {
                "requires_merchant_review": True,
                "rail_refund_requires_verifier": True,
                "policy_url": "https://merchant.example/returns",
            },
            "cancellations": {
                "buyer_request_allowed": True,
                "request_window_minutes": 30,
                "requires_merchant_review": True,
                "policy_url": "https://merchant.example/returns",
            },
            "substitutions": {
                "policy": "approval_required",
                "label": "Substitutions require buyer approval.",
                "requires_buyer_approval": True,
                "not_allowed": False,
                "merchant_may_substitute": False,
            },
        },
        "refund_policy": {
            "endpoint": "https://merchant.example/wp-json/agentcart/v1/orders/123/refunds",
            "requires_merchant_token": True,
            "remaining_refundable_cents": 1480,
            "currency": "EUR",
            "merchant_review_required": False,
            "item_policy_summary": {
                "commerce_policy_codes": [],
                "restricted_goods_codes": [],
                "perishable_item_count": 0,
                "deposit_item_count": 0,
                "non_returnable_item_count": 0,
                "merchant_review_required": False,
                "buyer_agent_note": "Standard merchant refund policy applies.",
            },
        },
        "cancellation_policy": {
            "endpoint": "https://merchant.example/wp-json/agentcart/v1/orders/123/cancellations",
            "requires_merchant_token": True,
            "idempotency_required": True,
            "eligible": True,
            "does_not_execute_refund": True,
            "paid_order_requires_separate_refund": True,
            "refund_endpoint": "https://merchant.example/wp-json/agentcart/v1/orders/123/refunds",
            "eligibility": {
                "eligible": True,
                "status": "processing",
                "blocking_reasons": [],
                "within_advertised_buyer_request_window": True,
                "advertised_request_window_minutes": 30,
                "refund_required_if_cancelled": True,
            },
        },
        "items": [],
        "cancellations": [],
        "refunds": [],
    }
    order.update(overrides)
    return order


class ShopBridgeDirectSkillTests(unittest.TestCase):
    def test_doctor_reports_missing_buyer_configuration_without_network(self) -> None:
        with (
            mock.patch.dict(shopbridge_direct.os.environ, {}, clear=True),
            mock.patch.object(shopbridge_direct, "REGISTRY_URL", ""),
            mock.patch.object(shopbridge_direct, "REGISTRY_PATH", ""),
            mock.patch.object(shopbridge_direct, "BASE_URL", shopbridge_direct.DEFAULT_BASE_URL),
            mock.patch.object(shopbridge_direct, "request_json", side_effect=AssertionError("unexpected merchant call")),
        ):
            result = shopbridge_direct.command_doctor({})

        self.assertFalse(result["ok"])
        self.assertEqual(result["mode"], "unconfigured")
        self.assertIn("buyer_configuration", [check["id"] for check in result["checks"]])
        self.assertFalse(result["configuration"]["base_url"]["configured"])

    def test_doctor_reports_registry_path_record_count_without_verifying_merchants(self) -> None:
        _manifest, record, _proof = registry_manifest_and_record()
        with tempfile.TemporaryDirectory() as raw_tmp:
            registry_path = Path(raw_tmp) / "registry.json"
            registry_path.write_text(json.dumps({"entries": [record]}), encoding="utf-8")
            with mock.patch.object(shopbridge_direct, "request_json", side_effect=AssertionError("unexpected merchant call")):
                result = shopbridge_direct.command_doctor({"registry_path": str(registry_path)})

        self.assertTrue(result["ok"], result)
        self.assertEqual(result["mode"], "registry")
        registry_check = next(check for check in result["checks"] if check["id"] == "registry_source")
        self.assertEqual(registry_check["record_count"], 1)
        self.assertEqual(result["next_commands"][0]["command"], "resolve_merchant")

    def test_doctor_can_verify_configured_registry_records_when_requested(self) -> None:
        manifest, record, proof = registry_manifest_and_record()

        result = shopbridge_direct.command_doctor(
            {
                "registry_records": [record],
                "manifest_snapshots": {"merchant-tea-shop": manifest},
                "proof_snapshots": {"merchant-tea-shop": proof},
                "verify_merchants": True,
            }
        )

        self.assertTrue(result["ok"], result)
        verification_check = next(check for check in result["checks"] if check["id"] == "registry_record_verification")
        self.assertEqual(verification_check["checked"], 1)
        self.assertTrue(verification_check["records"][0]["ok"])
        self.assertEqual(verification_check["records"][0]["base_url"], "https://merchant.example")

    def test_doctor_can_probe_single_merchant_readiness_when_requested(self) -> None:
        def fake_request(path, *, method="GET", payload=None, headers=None, base_url=None):
            self.assertEqual(base_url, "https://merchant.example")
            if path == "/.well-known/agentcart.json":
                return {
                    "merchant": {"id": "merchant-1", "name": "Merchant Tea Shop"},
                    "protocol_profiles": [{"id": "agentcart-shopbridge", "type": "commerce"}],
                }
            if path == "/wp-json/agentcart/v1/capability":
                return {
                    "merchant": {"id": "merchant-1", "name": "Merchant Tea Shop"},
                    "protocol_profiles": [
                        {"id": "agentcart-shopbridge", "type": "commerce"},
                        {"id": "stripe-card-mpp", "type": "payment", "network_id": "acct_shop_123"},
                    ],
                    "payment": {
                        "verification": {"external_verifier_configured": True},
                        "protocols": [{"id": "stripe-card-mpp", "available": True}],
                    },
                }
            raise AssertionError(f"unexpected path {path}")

        with mock.patch.object(shopbridge_direct, "request_json", side_effect=fake_request):
            result = shopbridge_direct.command_doctor({"base_url": "https://merchant.example", "probe": True})

        self.assertTrue(result["ok"], result)
        probe = next(check for check in result["checks"] if check["id"] == "merchant_readiness_probe")
        self.assertEqual(
            probe["readiness"]["protocol_profile_ids"],
            ["agentcart-shopbridge", "stripe-card-mpp"],
        )
        self.assertEqual(result["mode"], "single_merchant")
        probe_check = next(check for check in result["checks"] if check["id"] == "merchant_readiness_probe")
        self.assertTrue(probe_check["ok"])

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
        self.assertEqual(payload["approval_record"]["schema"], "agentcart.approval_record.v1")
        self.assertEqual(payload["approval_record_hash"], payload["approval_record"]["approval_record_hash"])
        self.assertEqual(payload["approval_decision_record"]["approval_record_hash"], payload["approval_record_hash"])
        self.assertEqual(payload["approval_decision_record"]["decision"], "approved")
        self.assertEqual(payload["audit_packet"]["schema"], "agentcart.skill_audit_packet.v1")
        self.assertEqual(payload["audit_packet"]["events"][0]["event_type"], "approval.approved")
        self.assertEqual(payload["audit_packet"]["events"][-1]["refs"]["agentcart_order_id"], payload["agentcart_order_id"])

    def test_approval_packet_binds_stripe_payment_destination(self) -> None:
        packet = shopbridge_direct.approval_packet(sample_quote(), payment_rail="stripe-card-mpp")

        self.assertEqual(packet["approval_material"]["payment_destination"]["rail"], "stripe-card-mpp")
        self.assertEqual(packet["approval_material"]["payment_destination"]["stripe_profile_id"], "acct_shop_123")
        self.assertIn("acct_shop_123", packet["summary"])
        self.assertEqual(packet["approval_record"]["schema"], "agentcart.approval_record.v1")
        self.assertEqual(packet["approval_record"]["approval_hash"], packet["approval_hash"])
        self.assertEqual(packet["approval_record"]["approval_record_hash"], packet["approval_record_hash"])
        self.assertEqual(packet["approval_record"]["approval_material"]["total_cents"], 1480)

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
        approval_hash = shopbridge_direct.approval_packet(quote, payment_rail="stripe-card-mpp")["approval_hash"]
        with self.assertRaises(SystemExit):
            shopbridge_direct.checkout_payload(
                {
                    "quote": quote,
                    "payment_rail": "stripe-card-mpp",
                    "approved": True,
                    "approval_hash": approval_hash,
                    "payment_receipt": sample_payment_receipt(amount_cents=1479),
                }
            )

    def test_payment_receipt_must_explicitly_bind_amount_currency_and_quote_hash(self) -> None:
        quote = sample_quote()
        approval_hash = shopbridge_direct.approval_packet(quote, payment_rail="stripe-card-mpp")["approval_hash"]
        receipt = sample_payment_receipt()
        del receipt["amount_cents"]

        with self.assertRaises(SystemExit) as raised:
            shopbridge_direct.checkout_payload(
                {
                    "quote": quote,
                    "payment_rail": "stripe-card-mpp",
                    "approved": True,
                    "approval_hash": approval_hash,
                    "payment_receipt": receipt,
                }
            )

        self.assertIn("payment_receipt missing required field(s): amount_cents", str(raised.exception))

    def test_payment_receipt_must_include_rail_reference_or_credential(self) -> None:
        quote = sample_quote()
        approval_hash = shopbridge_direct.approval_packet(quote, payment_rail="stripe-card-mpp")["approval_hash"]
        receipt = sample_payment_receipt()
        del receipt["authorization"]

        with self.assertRaises(SystemExit) as raised:
            shopbridge_direct.checkout_payload(
                {
                    "quote": quote,
                    "payment_rail": "stripe-card-mpp",
                    "approved": True,
                    "approval_hash": approval_hash,
                    "payment_receipt": receipt,
                }
            )

        self.assertIn("payment_receipt must include one of: authorization, credential, transaction_reference", str(raised.exception))

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

    def test_payment_handoff_requires_approved_matching_approval_hash(self) -> None:
        quote = sample_quote()
        approval_hash = shopbridge_direct.approval_packet(quote, payment_rail="stripe-card-mpp")["approval_hash"]

        with self.assertRaises(SystemExit):
            shopbridge_direct.command_payment_handoff(
                {"quote": quote, "payment_rail": "stripe-card-mpp", "approval_hash": approval_hash}
            )
        with self.assertRaises(SystemExit):
            shopbridge_direct.command_payment_handoff(
                {"quote": quote, "payment_rail": "stripe-card-mpp", "approved": True, "approval_hash": "wrong"}
            )

    def test_payment_handoff_builds_quote_bound_stripe_payment_request(self) -> None:
        quote = sample_quote()
        approval_hash = shopbridge_direct.approval_packet(quote, payment_rail="stripe-card-mpp")["approval_hash"]

        result = shopbridge_direct.command_payment_handoff(
            {
                "quote": quote,
                "payment_rail": "stripe-card-mpp",
                "approved": True,
                "approval_hash": approval_hash,
            }
        )

        self.assertTrue(result["ok"], result)
        self.assertEqual(result["approval_hash"], approval_hash)
        self.assertEqual(result["approval_record_hash"], result["approval_record"]["approval_record_hash"])
        self.assertEqual(result["payment_request"]["rail"], "stripe-card-mpp")
        self.assertEqual(result["payment_request"]["approval_record_hash"], result["approval_record_hash"])
        self.assertEqual(result["payment_request"]["amount_cents"], 1480)
        self.assertEqual(result["payment_request"]["currency"], "EUR")
        self.assertEqual(result["payment_request"]["quote_hash"], "quote-hash-123")
        self.assertEqual(
            result["payment_request"]["payment_destination"]["stripe_profile_id"],
            "acct_shop_123",
        )
        self.assertIn("stripe_profile_id", result["payment_request"]["receipt_requirements"]["required_fields"])
        self.assertIn("authorization", result["payment_request"]["receipt_requirements"]["one_of"])
        self.assertEqual(result["checkout_contract"]["next_command"], "checkout")

    def test_payment_handoff_builds_x402_payment_request_from_quote_requirements(self) -> None:
        quote = sample_x402_quote()
        approval_hash = shopbridge_direct.approval_packet(quote, payment_rail="x402-compatible")["approval_hash"]

        result = shopbridge_direct.command_payment_handoff(
            {
                "quote": quote,
                "payment_rail": "x402-compatible",
                "approved": True,
                "approval_hash": approval_hash,
            }
        )

        self.assertTrue(result["ok"], result)
        destination = result["payment_request"]["payment_destination"]
        self.assertEqual(result["payment_request"]["rail"], "x402-compatible")
        self.assertEqual(destination["network"], "eip155:84532")
        self.assertEqual(destination["asset"], "0x2222222222222222222222222222222222222222")
        self.assertEqual(destination["pay_to"], "0x1111111111111111111111111111111111111111")
        self.assertEqual(destination["max_amount_required"], "14800000")
        self.assertEqual(destination["payment_required"]["x402Version"], 2)
        self.assertIn("x402_payment_signature", result["payment_request"]["receipt_requirements"]["one_of"])
        self.assertIn("max_amount_required", result["payment_request"]["receipt_requirements"]["required_fields"])

    def test_payment_handoff_returns_preflight_issues_without_payment_request(self) -> None:
        quote = sample_quote(
            payment_requirements={
                "verification": {"external_verifier_configured": False},
                "protocols": [{"id": "stripe-card-mpp", "available": True, "stripe_profile_id": "acct_shop_123"}],
            }
        )
        approval_hash = shopbridge_direct.approval_packet(quote, payment_rail="stripe-card-mpp")["approval_hash"]

        result = shopbridge_direct.command_payment_handoff(
            {
                "quote": quote,
                "payment_rail": "stripe-card-mpp",
                "approved": True,
                "approval_hash": approval_hash,
            }
        )

        self.assertFalse(result["ok"], result)
        self.assertIn("external_verifier_required_for_public_checkout", result["issues"])
        self.assertNotIn("payment_request", result)

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
        self.assertEqual(result["protocol_profile_ids"], ["agentcart-shopbridge", "stripe-card-mpp"])
        self.assertEqual([profile["id"] for profile in result["protocol_profiles"]], ["agentcart-shopbridge", "stripe-card-mpp"])

    def test_resolve_merchant_can_use_configured_registry_path(self) -> None:
        manifest, record, proof = registry_manifest_and_record()
        with tempfile.TemporaryDirectory() as raw_tmp:
            registry_path = Path(raw_tmp) / "registry.json"
            registry_path.write_text(json.dumps({"entries": [record]}), encoding="utf-8")

            result = shopbridge_direct.command_resolve_merchant(
                {
                    "registry_path": str(registry_path),
                    "merchant_id": "merchant-tea-shop",
                    "manifest_snapshot": manifest,
                    "proof_snapshot": proof,
                }
            )

        self.assertTrue(result["ok"], result)
        self.assertEqual(result["base_url"], "https://merchant.example")
        self.assertEqual(result["merchant"]["id"], "merchant-tea-shop")

    def test_resolve_merchant_can_use_shopbridge_registry_bundle_path(self) -> None:
        manifest, record, proof = registry_manifest_and_record()
        with tempfile.TemporaryDirectory() as raw_tmp:
            registry_path = Path(raw_tmp) / "registry-bundle.json"
            registry_path.write_text(
                json.dumps({
                    "type": "agentcart-registry-onboarding-bundle",
                    "registry_record": record,
                    "record_hash": shopbridge_direct.registry_record_hash(record),
                }),
                encoding="utf-8",
            )

            result = shopbridge_direct.command_resolve_merchant(
                {
                    "registry_path": str(registry_path),
                    "manifest_snapshot": manifest,
                    "proof_snapshot": proof,
                }
            )

        self.assertTrue(result["ok"], result)
        self.assertEqual(result["base_url"], "https://merchant.example")
        self.assertEqual(result["merchant"]["id"], "merchant-tea-shop")

    def test_registry_record_url_can_use_shopbridge_registry_bundle(self) -> None:
        _manifest, record, _proof = registry_manifest_and_record()
        bundle = {
            "type": "agentcart-registry-onboarding-bundle",
            "registry_record": record,
            "record_hash": shopbridge_direct.registry_record_hash(record),
        }

        with mock.patch.object(shopbridge_direct, "fetch_json_url", return_value=bundle):
            resolved = shopbridge_direct.registry_record_from_args(
                {"registry_record_url": "https://merchant.example/.well-known/agentcart-registry-bundle.json"}
            )

        self.assertEqual(resolved["merchant_id"], "merchant-tea-shop")

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

    def test_resolve_merchant_rejects_stale_registry_record(self) -> None:
        manifest, record, proof = registry_manifest_and_record(updated_at="2000-01-01T00:00:00Z")

        result = shopbridge_direct.command_resolve_merchant(
            {
                "registry_record": record,
                "manifest_snapshot": manifest,
                "proof_snapshot": proof,
                "registry_max_age_days": 180,
            }
        )

        self.assertFalse(result["ok"], result)
        self.assertIn("record_stale", result["verification"]["errors"])

    def test_resolve_merchant_rejects_future_registry_record(self) -> None:
        future = (shopbridge_direct.utcnow() + shopbridge_direct.dt.timedelta(days=1)).replace(microsecond=0)
        manifest, record, proof = registry_manifest_and_record(updated_at=future.isoformat().replace("+00:00", "Z"))

        result = shopbridge_direct.command_resolve_merchant(
            {
                "registry_record": record,
                "manifest_snapshot": manifest,
                "proof_snapshot": proof,
            }
        )

        self.assertFalse(result["ok"], result)
        self.assertIn("updated_at_in_future", result["verification"]["errors"])

    def test_resolve_merchant_rejects_matching_revocation_document(self) -> None:
        manifest, record, proof = registry_manifest_and_record()
        revocation = attach_revocation_url(manifest, record, proof)
        revocation["revocations"].append(
            {
                "record_hash": shopbridge_direct.registry_record_hash(record),
                "revoked_at": "2999-01-02T00:00:00Z",
            }
        )

        result = shopbridge_direct.command_resolve_merchant(
            {
                "registry_record": record,
                "manifest_snapshot": manifest,
                "proof_snapshot": proof,
                "revocation_snapshot": revocation,
            }
        )

        self.assertFalse(result["ok"], result)
        self.assertIn("record_revoked_by_revocation_document", result["verification"]["errors"])

    def test_discover_quotes_rejects_revoked_registry_record_before_catalog(self) -> None:
        manifest, record, proof = registry_manifest_and_record()
        revocation = attach_revocation_url(manifest, record, proof)
        revocation["revocations"].append(
            {
                "record_hash": shopbridge_direct.registry_record_hash(record),
                "revoked_at": "2999-01-02T00:00:00Z",
            }
        )

        with mock.patch.object(shopbridge_direct, "request_json", side_effect=AssertionError("unexpected catalog call")):
            result = shopbridge_direct.command_discover_quotes(
                {
                    "registry_records": [record],
                    "manifest_snapshots": {"merchant-tea-shop": manifest},
                    "proof_snapshots": {"merchant-tea-shop": proof},
                    "revocation_snapshots": {"merchant-tea-shop": revocation},
                    "query": "tea",
                    "country": "DE",
                    "postal_code": "10115",
                    "payment_rail": "stripe-card-mpp",
                }
            )

        self.assertIsNone(result["winner"])
        self.assertEqual(result["rejected"][0]["merchant_id"], "merchant-tea-shop")
        self.assertIn("record_revoked_by_revocation_document", result["rejected"][0]["detail"]["errors"])

    def test_resolve_merchant_rejects_external_http_without_fetching(self) -> None:
        _manifest, record, _proof = registry_manifest_and_record()
        record["manifest_url"] = "http://merchant.example/.well-known/agentcart.json"
        record["proof"]["url"] = "http://merchant.example/.well-known/agentcart-registry-proof.json"

        with mock.patch.object(shopbridge_direct, "fetch_json_url", side_effect=AssertionError("unexpected fetch")):
            result = shopbridge_direct.command_resolve_merchant({"registry_record": record})

        self.assertFalse(result["ok"], result)
        self.assertIn("manifest_url_requires_https", result["verification"]["errors"])
        self.assertIn("domain_proof_url_requires_https", result["verification"]["errors"])

    def test_registry_feed_url_requires_https_before_fetching(self) -> None:
        with mock.patch.object(shopbridge_direct, "fetch_json_url", side_effect=AssertionError("unexpected fetch")):
            with self.assertRaises(SystemExit) as raised:
                shopbridge_direct.registry_records_from_args({"registry_url": "http://registry.example/agentcart.json"})

        self.assertEqual(str(raised.exception), "registry_url_requires_https")

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

    def test_discover_quotes_uses_configured_registry_path_without_inline_records(self) -> None:
        manifest, record, proof = registry_manifest_and_record()

        def fake_request(path, *, method="GET", payload=None, headers=None, base_url=None):
            if path.startswith("/wp-json/agentcart/v1/catalog"):
                return {
                    "merchant": {"id": "merchant-tea-shop", "name": "Merchant Tea Shop"},
                    "products": [
                        {
                            "id": "merchant-tea",
                            "title": "Merchant Tea",
                            "eligible_for_agent_checkout": True,
                            "shipping_regions": ["DE"],
                        }
                    ],
                }
            return sample_quote(
                id="quote-merchant",
                merchant={"id": "merchant-tea-shop", "name": "Merchant Tea Shop"},
                items=[
                    {
                        "product_id": "merchant-tea",
                        "title": "Merchant Tea",
                        "quantity": 1,
                        "line_total_cents": 990,
                    }
                ],
                subtotal_cents=990,
                total_cents=1480,
                quote_hash="quote-hash-merchant",
            )

        with tempfile.TemporaryDirectory() as raw_tmp:
            registry_path = Path(raw_tmp) / "registry.json"
            registry_path.write_text(json.dumps({"entries": [record]}), encoding="utf-8")
            with (
                mock.patch.object(shopbridge_direct, "REGISTRY_PATH", str(registry_path)),
                mock.patch.object(shopbridge_direct, "request_json", side_effect=fake_request),
            ):
                result = shopbridge_direct.command_discover_quotes(
                    {
                        "manifest_snapshots": {"merchant-tea-shop": manifest},
                        "proof_snapshots": {"merchant-tea-shop": proof},
                        "query": "tea",
                        "country": "DE",
                        "postal_code": "10115",
                        "payment_rail": "stripe-card-mpp",
                    }
                )

        self.assertEqual(result["winner"]["quote_id"], "quote-merchant")
        self.assertEqual(result["winner"]["merchant_id"], "merchant-tea-shop")
        self.assertTrue(result["winner"]["registry"]["registry_record_hash"])

    def test_discover_quotes_can_rank_by_unit_price_for_grocery_value(self) -> None:
        manifest_a, record_a, proof_a = registry_manifest_and_record(
            merchant_id="shop-a",
            name="Small Pack Shop",
            domain="small.example",
            stripe_profile_id="acct_small",
        )
        manifest_b, record_b, proof_b = registry_manifest_and_record(
            merchant_id="shop-b",
            name="Bulk Pack Shop",
            domain="bulk.example",
            stripe_profile_id="acct_bulk",
        )

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
            if path.startswith("/wp-json/agentcart/v1/catalog"):
                if base_url == "https://small.example":
                    return {
                        "merchant": {"id": "shop-a", "name": "Small Pack Shop"},
                        "products": [
                            {
                                "id": "small-tea",
                                "title": "Tea 50 g",
                                "eligible_for_agent_checkout": True,
                                "shipping_regions": ["DE"],
                                "package_size": {
                                    "label": "50 g",
                                    "normalized_quantity": 50,
                                    "normalized_unit": "g",
                                },
                            }
                        ],
                    }
                return {
                    "merchant": {"id": "shop-b", "name": "Bulk Pack Shop"},
                    "products": [
                        {
                            "id": "bulk-tea",
                            "title": "Tea 200 g",
                            "eligible_for_agent_checkout": True,
                            "shipping_regions": ["DE"],
                            "package_size": {
                                "label": "200 g",
                                "normalized_quantity": 200,
                                "normalized_unit": "g",
                            },
                        }
                    ],
                }
            product_id = payload["items"][0]["product_id"]
            if product_id == "small-tea":
                return sample_quote(
                    id="quote-small",
                    merchant={"id": "shop-a", "name": "Small Pack Shop"},
                    items=[
                        {
                            "product_id": "small-tea",
                            "title": "Tea 50 g",
                            "quantity": 1,
                            "line_total_cents": 500,
                        }
                    ],
                    subtotal_cents=500,
                    shipping={"amount_cents": 0},
                    total_cents=500,
                    quote_hash="hash-small",
                    payment_requirements=payment_requirements("acct_small"),
                )
            return sample_quote(
                id="quote-bulk",
                merchant={"id": "shop-b", "name": "Bulk Pack Shop"},
                items=[
                    {
                        "product_id": "bulk-tea",
                        "title": "Tea 200 g",
                        "quantity": 1,
                        "line_total_cents": 900,
                    }
                ],
                subtotal_cents=900,
                shipping={"amount_cents": 0},
                total_cents=900,
                quote_hash="hash-bulk",
                payment_requirements=payment_requirements("acct_bulk"),
            )

        with mock.patch.object(shopbridge_direct, "request_json", side_effect=fake_request):
            result = shopbridge_direct.command_discover_quotes(
                {
                    "registry_records": [record_a, record_b],
                    "manifest_snapshots": {"shop-a": manifest_a, "shop-b": manifest_b},
                    "proof_snapshots": {"shop-a": proof_a, "shop-b": proof_b},
                    "query": "tea",
                    "country": "DE",
                    "payment_rail": "stripe-card-mpp",
                    "rank_by": "unit_price",
                }
            )

        self.assertEqual(result["market_design"]["rank_by"], "unit_price")
        self.assertEqual(result["winner"]["quote_id"], "quote-bulk")
        self.assertEqual(result["winner"]["unit_value"]["label"], "4.50 EUR per 100 g")
        self.assertIn("unit value 4.50 EUR per 100 g", result["winner"]["rank_reasons"])

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

    def test_discover_basket_quotes_compares_complete_baskets_across_verified_merchants(self) -> None:
        manifest_a, record_a, proof_a = registry_manifest_and_record(
            merchant_id="shop-a",
            name="Complete Grocery",
            domain="complete.example",
            stripe_profile_id="acct_complete",
        )
        manifest_b, record_b, proof_b = registry_manifest_and_record(
            merchant_id="shop-b",
            name="Tea Only Grocery",
            domain="teaonly.example",
            stripe_profile_id="acct_teaonly",
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

        def catalog_product(product_id, title):
            return {
                "id": product_id,
                "title": title,
                "eligible_for_agent_checkout": True,
                "shipping_regions": ["DE"],
                "package_size": {
                    "label": "1 unit",
                    "normalized_quantity": 1,
                    "normalized_unit": "unit",
                },
            }

        def fake_request(path, *, method="GET", payload=None, headers=None, base_url=None):
            calls.append({"path": path, "method": method, "payload": payload, "base_url": base_url})
            if path.startswith("/wp-json/agentcart/v1/catalog"):
                if base_url == "https://complete.example":
                    if "filters" in path:
                        return {"products": [catalog_product("complete-filters", "Coffee Filters")]}
                    return {"products": [catalog_product("complete-tea", "Breakfast Tea")]}
                if "filters" in path:
                    return {"products": []}
                return {"products": [catalog_product("teaonly-tea", "Breakfast Tea")]}
            self.assertEqual(base_url, "https://complete.example")
            self.assertEqual(
                payload["items"],
                [
                    {"product_id": "complete-tea", "quantity": 1},
                    {"product_id": "complete-filters", "quantity": 2},
                ],
            )
            return sample_quote(
                id="quote-complete",
                merchant={"id": "shop-a", "name": "Complete Grocery"},
                items=[
                    {
                        "product_id": "complete-tea",
                        "title": "Breakfast Tea",
                        "quantity": 1,
                        "line_total_cents": 600,
                    },
                    {
                        "product_id": "complete-filters",
                        "title": "Coffee Filters",
                        "quantity": 2,
                        "line_total_cents": 400,
                    },
                ],
                subtotal_cents=1000,
                shipping={"amount_cents": 500},
                total_cents=1500,
                quote_hash="hash-complete",
                payment_requirements=payment_requirements("acct_complete"),
            )

        with mock.patch.object(shopbridge_direct, "request_json", side_effect=fake_request):
            result = shopbridge_direct.command_discover_basket_quotes(
                {
                    "registry_records": [record_a, record_b],
                    "manifest_snapshots": {"shop-a": manifest_a, "shop-b": manifest_b},
                    "proof_snapshots": {"shop-a": proof_a, "shop-b": proof_b},
                    "basket": [
                        {"query": "tea", "quantity": 1},
                        {"query": "filters", "quantity": 2},
                    ],
                    "country": "DE",
                    "postal_code": "10115",
                    "payment_rail": "stripe-card-mpp",
                }
            )

        self.assertEqual(result["winner"]["quote_id"], "quote-complete")
        self.assertTrue(result["winner"]["full_basket"])
        self.assertEqual(len(result["winner"]["matched_items"]), 2)
        self.assertEqual(result["winner"]["quote"]["total_cents"], 1500)
        self.assertEqual(
            result["winner"]["approval_packet"]["approval_material"]["payment_destination"]["stripe_profile_id"],
            "acct_complete",
        )
        self.assertEqual(result["rejected"][0]["reason"], "merchant could not satisfy required basket items")
        self.assertEqual(result["rejected"][0]["missing_items"][0]["query"], "filters")
        self.assertEqual([call["base_url"] for call in calls if call["method"] == "POST"], ["https://complete.example"])

    def test_discover_basket_quotes_uses_only_explicit_substitutions_with_constraints(self) -> None:
        manifest, record, proof = registry_manifest_and_record(
            merchant_id="shop-a",
            name="Substitution Grocery",
            domain="substitution.example",
            stripe_profile_id="acct_substitution",
        )

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
            if path.startswith("/wp-json/agentcart/v1/catalog"):
                if "organic+milk" in path:
                    return {"products": []}
                return {
                    "products": [
                        {
                            "id": "peanut-oat-milk",
                            "title": "Peanut Oat Milk",
                            "description": "Oat drink.",
                            "tags": ["vegan"],
                            "dietary_tags": ["vegan"],
                            "allergens": ["peanuts"],
                            "eligible_for_agent_checkout": True,
                            "shipping_regions": ["DE"],
                        },
                        {
                            "id": "oat-milk",
                            "title": "Oat Milk",
                            "description": "Dairy-free oat drink.",
                            "tags": ["vegan"],
                            "dietary_tags": ["vegan"],
                            "allergens": [],
                            "eligible_for_agent_checkout": True,
                            "shipping_regions": ["DE"],
                        },
                    ]
                }
            self.assertEqual(payload["items"], [{"product_id": "oat-milk", "quantity": 2}])
            return sample_quote(
                id="quote-oat",
                merchant={"id": "shop-a", "name": "Substitution Grocery"},
                items=[
                    {
                        "product_id": "oat-milk",
                        "title": "Oat Milk",
                        "quantity": 2,
                        "line_total_cents": 500,
                    }
                ],
                subtotal_cents=500,
                shipping={"amount_cents": 300},
                total_cents=800,
                quote_hash="hash-oat",
                payment_requirements=payment_requirements("acct_substitution"),
            )

        with mock.patch.object(shopbridge_direct, "request_json", side_effect=fake_request):
            result = shopbridge_direct.command_discover_basket_quotes(
                {
                    "registry_records": [record],
                    "manifest_snapshots": {"shop-a": manifest},
                    "proof_snapshots": {"shop-a": proof},
                    "basket": [
                        {
                            "query": "organic milk",
                            "quantity": 2,
                            "constraints": {"required_tags": ["vegan"], "exclude_allergens": ["peanut"]},
                            "alternatives": [{"query": "oat milk"}],
                        }
                    ],
                    "country": "DE",
                    "payment_rail": "stripe-card-mpp",
                }
            )

        self.assertEqual(result["winner"]["quote_id"], "quote-oat")
        self.assertEqual(result["winner"]["matched_items"][0]["query"], "organic milk")
        self.assertEqual(result["winner"]["matched_items"][0]["matched_query"], "oat milk")
        self.assertTrue(result["winner"]["matched_items"][0]["substitution"])
        self.assertEqual(result["winner"]["substitutions"][0]["product_id"], "oat-milk")
        self.assertIn("product did not satisfy basket constraints", {item["reason"] for item in result["winner"]["item_rejections"]})

    def test_discover_basket_quotes_rejects_unverified_merchants_before_catalog_or_quote(self) -> None:
        manifest, record, proof = registry_manifest_and_record()
        proof["record_hash"] = "0" * 64

        with mock.patch.object(shopbridge_direct, "request_json", side_effect=AssertionError("unexpected merchant call")):
            result = shopbridge_direct.command_discover_basket_quotes(
                {
                    "registry_records": [record],
                    "manifest_snapshots": {"merchant-tea-shop": manifest},
                    "proof_snapshots": {"merchant-tea-shop": proof},
                    "basket": [{"query": "tea", "quantity": 1}],
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
                "cancellation_reason": "Ordered by mistake",
            }
        )

        self.assertEqual(result["order"]["id"], "123")
        self.assertEqual(result["fulfillment"]["state"], "preparing")
        self.assertEqual(result["refund"]["remaining"], "14.80 EUR")
        self.assertTrue(result["refund"]["requires_merchant_or_gateway"])
        self.assertEqual(result["support"]["email"], "support@example.test")
        self.assertEqual(result["merchant_policy"]["substitution_policy"], "approval_required")
        self.assertEqual(result["aftercare_state"]["fulfillment_phase"], "pre_fulfillment")
        self.assertEqual(result["aftercare_state"]["cancellation_state"], "cancellable_before_fulfillment")
        self.assertEqual(result["aftercare_state"]["refund_state"], "refund_available")
        self.assertTrue(result["aftercare_state"]["refund_required_if_cancelled"])
        self.assertTrue(result["merchant_policy"]["cancellation_request_allowed"])
        self.assertEqual(result["payment_proof"]["transaction_reference"], "pi_test_123")
        self.assertEqual(result["refund_request_draft"]["amount"], "5.00 EUR")
        self.assertIn("does not call merchant-token refund, cancellation, or order mutation endpoints", result["safety_note"])
        self.assertIn("request_refund", {action["id"] for action in result["next_actions"]})
        self.assertIn("request_cancellation", {action["id"] for action in result["next_actions"]})
        self.assertTrue(result["cancellation"]["eligible"])
        self.assertTrue(result["cancellation"]["does_not_execute_refund"])
        self.assertEqual(result["cancellation_request_draft"]["trusted_gateway_payload_hint"]["endpoint"], "https://merchant.example/wp-json/agentcart/v1/orders/123/cancellations")
        self.assertTrue(result["cancellation_request_draft"]["trusted_gateway_payload_hint"]["refund_required_after_cancellation"])
        self.assertEqual(
            result["refund_request_draft"]["trusted_gateway_payload_hint"]["merchant_policy"]["returns_url"],
            "https://merchant.example/returns",
        )

    def test_aftercare_summary_surfaces_normalized_carrier_tracking(self) -> None:
        order = sample_order_status()
        order["fulfillment"] = {
            **order["fulfillment"],
            "state": "shipped",
            "carrier": "Fallback Carrier",
            "tracking_number": "FALLBACK-1",
            "tracking_url": "",
            "tracking_status": "shipped",
            "source": "generic_order_meta",
            "tracking": {
                "carrier": "DHL",
                "tracking_number": "00340434161094000001",
                "tracking_url": "https://example.test/track/00340434161094000001",
                "tracking_status": "in_transit",
                "tracking_status_label": "In transit",
                "shipped_at": "2999-01-03T10:00:00+00:00",
                "delivered_at": "",
                "last_event_at": "2999-01-04T08:00:00+00:00",
                "source": "woocommerce_shipment_tracking",
                "adapter": "woocommerce-shipment-tracking",
                "confidence": "carrier_reference",
                "is_real_carrier_tracking": True,
            },
        }

        result = shopbridge_direct.command_aftercare_summary({"order": order})

        self.assertEqual(result["fulfillment"]["carrier"], "DHL")
        self.assertEqual(result["fulfillment"]["tracking_status"], "in_transit")
        self.assertEqual(result["fulfillment"]["tracking_source"], "woocommerce_shipment_tracking")
        self.assertEqual(result["fulfillment"]["tracking_confidence"], "carrier_reference")
        self.assertTrue(result["fulfillment"]["tracking"]["is_real_carrier_tracking"])
        self.assertIn("open_tracking", {action["id"] for action in result["next_actions"]})

    def test_aftercare_summary_surfaces_item_policy_review(self) -> None:
        order = sample_order_status()
        order["items"] = [
            {
                "product_id": "woo_22",
                "title": "Fresh yogurt bottle",
                "commerce_policy": {
                    "flags": [
                        {"code": "perishable", "summary": "Perishable goods."},
                        {"code": "deposit", "summary": "Deposit-bearing packaging."},
                    ],
                    "returnable_by_default": False,
                },
                "restricted_goods": [],
            }
        ]
        order["refund_policy"]["item_policy_summary"] = {
            "commerce_policy_codes": ["perishable", "deposit"],
            "restricted_goods_codes": [],
            "perishable_item_count": 1,
            "deposit_item_count": 1,
            "non_returnable_item_count": 1,
            "merchant_review_required": True,
            "buyer_agent_note": "Review item-level policy before refund, return, cancellation, or substitution.",
        }
        order["refund_policy"]["merchant_review_required"] = True

        result = shopbridge_direct.command_aftercare_summary({"order": order, "refund_reason": "Spoiled"})

        self.assertTrue(result["refund"]["merchant_review_required"])
        self.assertEqual(result["item_policy"]["commerce_policy_codes"], ["deposit", "perishable"])
        self.assertEqual(result["item_policy"]["perishable_item_count"], 1)
        self.assertIn("review_item_policy", {action["id"] for action in result["next_actions"]})
        self.assertEqual(
            result["refund_request_draft"]["trusted_gateway_payload_hint"]["item_policy_summary"]["deposit_item_count"],
            1,
        )

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
