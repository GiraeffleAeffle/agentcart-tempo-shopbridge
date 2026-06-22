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
            "catalog": "http://shop/wp-json/agentcart/v1/catalog",
            "quote": "http://shop/wp-json/agentcart/v1/quote",
        },
    }


def sample_manifest():
    return {
        "merchant": {"id": "woocommerce-demo-shop"},
        "endpoints": {
            "catalog": "http://shop/wp-json/agentcart/v1/catalog",
            "quote": "http://shop/wp-json/agentcart/v1/quote",
        },
        "discovery": {"registry_claim_hash": "abc123"},
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


if __name__ == "__main__":
    unittest.main()
