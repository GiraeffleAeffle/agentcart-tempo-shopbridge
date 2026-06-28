from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import unittest
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "woocommerce-shopbridge-smoke.py"
INTEGRATION_SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "woocommerce-demo-integration.sh"
RESET_SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "woocommerce-demo-reset.sh"
SEED_SCRIPT_PATH = Path(__file__).resolve().parents[2] / "demo" / "woocommerce" / "seed-products.sh"
ROOT_PACKAGE_PATH = Path(__file__).resolve().parents[2] / "package.json"
DEMO_README_PATH = Path(__file__).resolve().parents[2] / "demo" / "woocommerce" / "README.md"
SPEC = importlib.util.spec_from_file_location("woocommerce_shopbridge_smoke", SCRIPT_PATH)
assert SPEC and SPEC.loader
smoke = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = smoke
SPEC.loader.exec_module(smoke)


def args(**overrides):
    values = {
        "quantity": 1,
        "country": "DE",
        "postcode": "10115",
        "city": "Berlin",
        "address": "Demo Street 1",
        "currency": "EUR",
        "merchant_token": "agentcart-woo-demo-token",
        "expect_shipping_cents": None,
        "require_shipping": True,
        "require_vat_lines": True,
        "require_real_refund_verifier_evidence": False,
        "rounding_tolerance_cents": 1,
    }
    values.update(overrides)
    return argparse.Namespace(**values)


def sample_capability():
    return {
        "merchant": {"id": "woocommerce-demo-shop"},
        "protocol_profiles": [
            {
                "id": "agentcart-shopbridge",
                "type": "commerce",
                "status": "available",
            }
        ],
        "readiness": {"demo_ready": True},
        "setup_guide": {
            "next_step": {"id": "ready"},
            "steps": [
                {"id": "merchant_identity"},
                {"id": "products"},
                {"id": "tax_shipping"},
                {"id": "payment_verifier"},
                {"id": "registry"},
                {"id": "sandbox_test"},
            ],
        },
        "merchant_setup_explainer": [
            {
                "id": "merchant_identity",
                "title": "Name the shop and support contact",
                "merchant_action": "Choose a stable merchant id and add support email.",
                "skipping_means": "Buyers cannot identify support.",
                "settings_anchor": "#agentcart-settings",
                "state": "complete",
            },
            {
                "id": "products",
                "title": "Choose which products agents may see",
                "merchant_action": "Select manual, tag, category, or all-product exposure.",
                "skipping_means": "No products appear to buyer agents.",
                "settings_anchor": "#agentcart-product-exposure",
                "state": "complete",
            },
            {
                "id": "tax_shipping",
                "title": "Use WooCommerce tax and shipping rules",
                "merchant_action": "Configure tax rates, shipping methods, and ship-to countries.",
                "skipping_means": "Quotes may miss VAT or shipping.",
                "settings_anchor": "#agentcart-readiness",
                "state": "complete",
            },
            {
                "id": "payment_verifier",
                "title": "Connect payment verification before real checkout",
                "merchant_action": "Configure verifier URL, token, and recipient details.",
                "skipping_means": "Public agents should not create paid orders.",
                "settings_anchor": "#agentcart-settings",
                "state": "needs_setup",
            },
            {
                "id": "registry",
                "title": "Publish the shop for agent discovery",
                "merchant_action": "Submit or refresh the generated registry record.",
                "skipping_means": "Agents need the direct manifest URL.",
                "settings_anchor": "#agentcart-registry-proof",
                "state": "needs_setup",
            },
            {
                "id": "sandbox_test",
                "title": "Run a test quote and checkout",
                "merchant_action": "Run quote and checkout tests from Quick Start.",
                "skipping_means": "No local checkout evidence exists.",
                "settings_anchor": "#agentcart-endpoints",
                "state": "complete",
            },
        ],
        "endpoints": {
            "registry_bundle": "http://shop/.well-known/agentcart-registry-bundle.json",
            "catalog": "http://shop/wp-json/agentcart/v1/catalog",
            "quote": "http://shop/wp-json/agentcart/v1/quote",
        },
    }


def sample_setup_required_capability():
    capability = sample_capability()
    capability["protocol_profiles"] = [
        {
            "id": "agentcart-shopbridge",
            "type": "commerce",
            "status": "setup_required",
            "available": False,
            "setup_required": True,
            "unavailable_reasons": ["payment verifier"],
        }
    ]
    capability["setup_guide"]["production_complete"] = True
    capability["setup_guide"]["steps"] = [
        {"id": "merchant_identity", "required_for": ["production"], "state": "complete"},
        {"id": "products", "required_for": ["production"], "state": "complete"},
        {"id": "tax_shipping", "required_for": ["production"], "state": "complete"},
        {"id": "payment_verifier", "required_for": ["production"], "state": "complete"},
        {"id": "registry", "required_for": ["production"], "state": "complete"},
        {"id": "sandbox_test", "required_for": ["demo"], "state": "complete"},
    ]
    return capability


def sample_manifest():
    return {
        "merchant": {"id": "woocommerce-demo-shop"},
        "protocol_profiles": [
            {
                "id": "agentcart-shopbridge",
                "type": "commerce",
                "status": "available",
            }
        ],
        "endpoints": {
            "catalog": "http://shop/wp-json/agentcart/v1/catalog",
            "quote": "http://shop/wp-json/agentcart/v1/quote",
        },
        "discovery": {
            "registry_claim_hash": "abc123",
            "registry_bundle_url": "http://shop/.well-known/agentcart-registry-bundle.json",
        },
    }


def sample_registry_record():
    return {
        "merchant_id": "woocommerce-demo-shop",
        "name": "Woo Demo Shop",
        "domain": "shop",
        "manifest_url": "http://shop/.well-known/agentcart.json",
        "registry_claim_hash_alg": "sha-256",
        "registry_claim_hash": "abc123",
        "updated_at": "2026-06-23T00:00:00Z",
        "revoked_at": None,
        "signature_alg": "https-domain-proof",
        "signature": "",
        "proof": {
            "type": "https-well-known",
            "url": "http://shop/.well-known/agentcart-registry-proof.json",
        },
    }


def sample_registry_bundle(record=None):
    record = record or sample_registry_record()
    record_hash = smoke.registry_record_hash(record)
    return {
        "type": "agentcart-registry-onboarding-bundle",
        "registry_record": record,
        "record_hash": record_hash,
        "proof_document_expected": sample_registry_proof(record),
        "registry_feed": {"entries": [record]},
    }


def sample_registry_proof(record=None):
    record = record or sample_registry_record()
    return {
        "type": "https-well-known",
        "merchant_id": record["merchant_id"],
        "domain": record["domain"],
        "manifest_url": record["manifest_url"],
        "registry_claim_hash": record["registry_claim_hash"],
        "payment_network": "",
        "payment_recipient": "",
        "updated_at": record["updated_at"],
        "record_hash": smoke.registry_record_hash(record),
    }


def sample_registry_revocations(record=None):
    record = record or sample_registry_record()
    return {
        "type": "agentcart-registry-revocations",
        "merchant_id": record["merchant_id"],
        "domain": record["domain"],
        "updated_at": record["updated_at"],
        "revocations": [],
    }


def sample_catalog_product():
    return {
        "product_id": "woo_10",
        "title": "Hazel Tea",
        "availability": "in_stock",
        "eligible_for_agent_checkout": True,
    }


def sample_quote(**overrides):
    quote = {
        "id": "woo_quote_123",
        "merchant": {"id": "woocommerce-demo-shop"},
        "items": [
            {
                "product_id": "woo_10",
                "quantity": 1,
                "line_total_cents": 990,
            }
        ],
        "subtotal_cents": 990,
        "shipping": {
            "amount_cents": 490,
            "currency": "EUR",
            "source": "woocommerce_cart",
        },
        "vat_lines": [
            {
                "vat_cents": 236,
                "included_in_price": True,
                "source": "woocommerce_cart",
            }
        ],
        "total_cents": 1480,
        "currency": "EUR",
        "quote_hash": "quote-hash",
        "payment_requirements": {
            "protocols": [{"id": "tempo-mpp"}],
            "payment_contract_hash": "payment-contract-hash",
            "verification_contract": {"payment_contract_hash": "payment-contract-hash"},
        },
        "merchant_policy": {"returns_url": "https://shop.test/returns"},
        "delivery_window": {"label": "2-4 business days"},
    }
    quote.update(overrides)
    return quote


def sample_order_response():
    return {
        "platform": "woocommerce-agentcart-plugin",
        "state": "created",
        "id": "123",
        "status": "processing",
        "status_token": "status-token",
        "payment_verification": {"mode": "trusted_agentcart_token", "real_settlement_verified": False},
        "aftercare_state": {"refund_progress": "not_refunded"},
    }


def sample_order_status():
    return {
        "platform": "woocommerce-agentcart-plugin",
        "id": "123",
        "status": "processing",
        "payment_status": "paid",
        "aftercare_state": {"refund_progress": "not_refunded"},
    }


def sample_refund_response():
    return {
        "platform": "woocommerce-agentcart-plugin",
        "state": "refund_recorded",
        "order_id": "123",
        "refund_id": "456",
        "amount_cents": 1480,
        "currency": "EUR",
        "idempotency_key": "refund-key",
        "real_refund_verified": False,
        "verification_mode": "trusted_agentcart_token",
        "verification": {
            "mode": "trusted_agentcart_token",
            "real_refund_verified": False,
            "note": "WooCommerce refund record only.",
        },
        "aftercare_state": {"refund_progress": "refunded"},
    }


def sample_cancellation_response():
    return {
        "platform": "woocommerce-agentcart-plugin",
        "state": "cancellation_recorded",
        "order_id": "123",
        "order_status": "cancelled",
        "refund_required": True,
        "real_refund_verified": False,
        "cancellation": {
            "id": "cancel_123",
            "real_refund_verified": False,
            "refund_required": True,
            "note": "No payment refund was executed by this cancellation endpoint.",
        },
        "aftercare_state": {"cancellation_state": "cancelled_refund_required"},
    }


class WooCommerceShopBridgeSmokeTests(unittest.TestCase):
    def test_capability_and_manifest_require_setup_and_endpoint_contracts(self) -> None:
        smoke.validate_capability(sample_capability())
        smoke.validate_manifest(sample_manifest())

    def test_setup_required_shopbridge_profile_is_allowed_in_non_strict_smoke(self) -> None:
        smoke.validate_capability(sample_setup_required_capability())

    def test_production_ready_smoke_rejects_setup_required_shopbridge_profile(self) -> None:
        with self.assertRaises(smoke.SmokeError):
            smoke.validate_production_setup(sample_setup_required_capability())

    def test_registry_bundle_validator_accepts_matching_proof_and_revocations(self) -> None:
        record = sample_registry_record()

        result = smoke.validate_registry_bundle(
            sample_registry_bundle(record),
            manifest=sample_manifest(),
            proof=sample_registry_proof(record),
            revocations=sample_registry_revocations(record),
        )

        self.assertEqual(result["merchant_id"], "woocommerce-demo-shop")
        self.assertEqual(result["record_hash"], smoke.registry_record_hash(record))

    def test_registry_bundle_validator_rejects_hash_drift(self) -> None:
        record = sample_registry_record()
        bundle = sample_registry_bundle(record)
        bundle["record_hash"] = "0" * 64

        with self.assertRaises(smoke.SmokeError):
            smoke.validate_registry_bundle(
                bundle,
                manifest=sample_manifest(),
                proof=sample_registry_proof(record),
                revocations=sample_registry_revocations(record),
            )

    def test_select_product_rejects_empty_or_ineligible_catalogs(self) -> None:
        with self.assertRaises(smoke.SmokeError):
            smoke.select_product({"products": []})
        with self.assertRaises(smoke.SmokeError):
            smoke.select_product({"products": [{"product_id": "woo_1", "eligible_for_agent_checkout": False}]})

        self.assertEqual(
            smoke.select_product({"products": [sample_catalog_product()]})["product_id"],
            "woo_10",
        )

    def test_quote_validator_accepts_woocommerce_cart_totals(self) -> None:
        smoke.validate_quote(
            sample_quote(),
            args=args(expect_shipping_cents=490),
            product=sample_catalog_product(),
        )

    def test_quote_validator_rejects_total_that_does_not_match_subtotal_plus_shipping(self) -> None:
        with self.assertRaises(smoke.SmokeError):
            smoke.validate_quote(
                sample_quote(total_cents=1200),
                args=args(),
                product=sample_catalog_product(),
            )

    def test_quote_validator_rejects_missing_vat_when_required(self) -> None:
        with self.assertRaises(smoke.SmokeError):
            smoke.validate_quote(
                sample_quote(vat_lines=[]),
                args=args(require_vat_lines=True),
                product=sample_catalog_product(),
            )

    def test_checkout_payload_binds_quote_total_hash_and_payment_contract(self) -> None:
        payload = smoke.checkout_payload(
            sample_quote(),
            args(),
            idempotency_key="checkout-key",
            receipt_id="receipt-123",
        )

        self.assertEqual(payload["merchant_quote_id"], "woo_quote_123")
        self.assertEqual(payload["quote_hash"], "quote-hash")
        self.assertEqual(payload["idempotency_key"], "checkout-key")
        self.assertEqual(payload["payment_receipt"]["id"], "receipt-123")
        self.assertEqual(payload["payment_receipt"]["amount_cents"], 1480)
        self.assertEqual(payload["payment_receipt"]["currency"], "EUR")
        self.assertEqual(payload["payment_receipt"]["quote_hash"], "quote-hash")
        self.assertEqual(payload["payment_receipt"]["payment_contract_hash"], "payment-contract-hash")

    def test_endpoint_harness_exercises_checkout_status_refund_cancellation_paths(self) -> None:
        calls = []
        original = smoke.http_json

        def fake_http_json(base_url, path, *, method="GET", payload=None, timeout=30, headers=None):
            calls.append((path, method, payload, headers))
            if path == "/wp-json/agentcart/v1/orders":
                if str(payload.get("merchant_quote_id", "")).startswith("woo_quote_missing_"):
                    raise smoke.HttpJsonError(
                        "HTTP 409",
                        status=409,
                        method=method,
                        path=path,
                        detail={"code": "agentcart_quote_expired", "data": {"status": 409}},
                    )
                if payload.get("quote_hash") == "bad-quote-hash":
                    raise smoke.HttpJsonError(
                        "HTTP 409",
                        status=409,
                        method=method,
                        path=path,
                        detail={"code": "agentcart_quote_mismatch", "data": {"status": 409}},
                    )
                return sample_order_response()
            if path == "/wp-json/agentcart/v1/orders/123/status":
                return sample_order_status()
            if path == "/wp-json/agentcart/v1/orders/123/cancellations":
                return sample_cancellation_response()
            if path == "/wp-json/agentcart/v1/orders/123/refunds":
                if "refund_idempotency_key" not in payload:
                    raise smoke.HttpJsonError(
                        "HTTP 400",
                        status=400,
                        method=method,
                        path=path,
                        detail={"code": "agentcart_refund_idempotency_key_required", "data": {"status": 400}},
                    )
                return sample_refund_response()
            raise AssertionError(f"unexpected harness call: {method} {path}")

        smoke.http_json = fake_http_json
        try:
            result = smoke.run_endpoint_harness("http://shop", sample_quote(), args())
        finally:
            smoke.http_json = original

        self.assertEqual(result["checkout"]["id"], "123")
        self.assertEqual(result["status"]["payment_status"], "paid")
        self.assertEqual(result["refund"]["real_refund_verified"], False)
        self.assertEqual(result["cancellation"]["real_refund_verified"], False)
        self.assertEqual(
            [(path, method) for path, method, _payload, _headers in calls],
            [
                ("/wp-json/agentcart/v1/orders", "POST"),
                ("/wp-json/agentcart/v1/orders", "POST"),
                ("/wp-json/agentcart/v1/orders", "POST"),
                ("/wp-json/agentcart/v1/orders/123/status", "GET"),
                ("/wp-json/agentcart/v1/orders/123/refunds", "POST"),
                ("/wp-json/agentcart/v1/orders/123/cancellations", "POST"),
                ("/wp-json/agentcart/v1/orders/123/refunds", "POST"),
            ],
        )

    def test_refund_validator_can_require_real_verifier_evidence(self) -> None:
        smoke.validate_refund_response(sample_refund_response(), require_real_refund_verifier_evidence=False)

        with self.assertRaises(smoke.SmokeError):
            smoke.validate_refund_response(sample_refund_response(), require_real_refund_verifier_evidence=True)

    def test_rate_limit_error_validator_requires_retry_metadata(self) -> None:
        error = smoke.HttpJsonError(
            "HTTP 429",
            status=429,
            method="POST",
            path="/wp-json/agentcart/v1/quote",
            detail={
                "code": "agentcart_rate_limited",
                "message": "Too many AgentCart requests. Try again shortly.",
                "data": {
                    "status": 429,
                    "bucket": "quote",
                    "limit": 30,
                    "window_seconds": 60,
                    "retry_after_seconds": 42,
                    "remaining": 0,
                    "reset_at": "2026-06-26T12:00:00Z",
                },
            },
        )

        data = smoke.validate_rate_limit_error(error, expected_bucket="quote")

        self.assertEqual(data["bucket"], "quote")
        self.assertEqual(data["retry_after_seconds"], 42)

    def test_rate_limit_abuse_probe_stops_on_429(self) -> None:
        calls = []
        original = smoke.http_json

        def fake_http_json(base_url, path, *, method="GET", payload=None, timeout=30):
            calls.append((base_url, path, method, payload, timeout))
            if len(calls) < 3:
                raise smoke.HttpJsonError(
                    "HTTP 401",
                    status=401,
                    method=method,
                    path=path,
                    detail={"code": "rest_forbidden"},
                )
            raise smoke.HttpJsonError(
                "HTTP 429",
                status=429,
                method=method,
                path=path,
                detail={
                    "code": "agentcart_rate_limited",
                    "data": {
                        "status": 429,
                        "bucket": "refund",
                        "limit": 10,
                        "window_seconds": 60,
                        "retry_after_seconds": 31,
                        "remaining": 0,
                        "reset_at": "2026-06-26T12:00:00Z",
                    },
                },
            )

        smoke.http_json = fake_http_json
        try:
            result = smoke.expect_rate_limit_exhaustion(
                "http://shop",
                {
                    "bucket": "refund",
                    "path": "/wp-json/agentcart/v1/orders/0/refunds",
                    "method": "POST",
                    "payload": {},
                    "limit": 10,
                },
                max_attempts=20,
            )
        finally:
            smoke.http_json = original

        self.assertEqual(result["bucket"], "refund")
        self.assertEqual(result["attempts"], 3)
        self.assertEqual(len(calls), 3)

    def test_rate_limit_scenarios_are_built_from_capability_document(self) -> None:
        capability = sample_capability()
        capability["rate_limits"] = {
            "quote": {"limit": 30, "window_seconds": 60, "scope": "hashed_client"},
            "refund": {"limit": 10, "window_seconds": 60, "scope": "hashed_client"},
        }

        scenarios = smoke.rate_limit_probe_scenarios(capability, {"quote", "refund"})

        self.assertEqual([scenario["bucket"] for scenario in scenarios], ["quote", "refund"])
        self.assertEqual(scenarios[0]["method"], "POST")
        self.assertEqual(scenarios[1]["path"], "/wp-json/agentcart/v1/orders/0/refunds")

    def test_demo_integration_harness_has_documented_separate_command(self) -> None:
        package = json.loads(ROOT_PACKAGE_PATH.read_text(encoding="utf-8"))
        readme = DEMO_README_PATH.read_text(encoding="utf-8")

        self.assertTrue(INTEGRATION_SCRIPT_PATH.exists(), "integration harness wrapper should exist")
        self.assertEqual(package["scripts"]["verify:woo-integration"], "bash scripts/woocommerce-demo-integration.sh")
        self.assertIn("npm run verify:woo-integration", readme)
        self.assertIn("--endpoint-harness", INTEGRATION_SCRIPT_PATH.read_text(encoding="utf-8"))

    def test_demo_reset_wrapper_runs_seed_reset_and_optional_smoke(self) -> None:
        reset_script = RESET_SCRIPT_PATH.read_text(encoding="utf-8")
        seed_script = SEED_SCRIPT_PATH.read_text(encoding="utf-8")

        self.assertIn("AGENTCART_DEMO_RESET=1", reset_script)
        self.assertIn("--no-smoke", reset_script)
        self.assertIn("--hard", reset_script)
        self.assertIn("woocommerce-shopbridge-smoke.py", reset_script)
        self.assertIn("reset_agentcart_demo_state", seed_script)
        self.assertIn("_agentcart_order_id", seed_script)
        self.assertIn("agentcart_shopbridge_registry_public_check", seed_script)
        self.assertIn("agentcart_shopbridge_product_exposure_snapshot", seed_script)


if __name__ == "__main__":
    unittest.main()
