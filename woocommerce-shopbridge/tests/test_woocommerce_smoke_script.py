from __future__ import annotations

import argparse
import importlib.util
import sys
import unittest
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "woocommerce-shopbridge-smoke.py"
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
        "expect_shipping_cents": None,
        "require_shipping": True,
        "require_vat_lines": True,
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
        "endpoints": {
            "registry_bundle": "http://shop/.well-known/agentcart-registry-bundle.json",
            "catalog": "http://shop/wp-json/agentcart/v1/catalog",
            "quote": "http://shop/wp-json/agentcart/v1/quote",
        },
    }


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
        "payment_requirements": {"protocols": [{"id": "stripe-card-mpp"}]},
        "merchant_policy": {"returns_url": "https://shop.test/returns"},
        "delivery_window": {"label": "2-4 business days"},
    }
    quote.update(overrides)
    return quote


class WooCommerceShopBridgeSmokeTests(unittest.TestCase):
    def test_capability_and_manifest_require_setup_and_endpoint_contracts(self) -> None:
        smoke.validate_capability(sample_capability())
        smoke.validate_manifest(sample_manifest())

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


if __name__ == "__main__":
    unittest.main()
