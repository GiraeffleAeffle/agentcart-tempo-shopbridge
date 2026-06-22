#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from typing import Any


class SmokeError(AssertionError):
    pass


def http_json(
    base_url: str,
    path: str,
    *,
    method: str = "GET",
    payload: dict[str, Any] | None = None,
    timeout: int = 30,
) -> dict[str, Any]:
    data = json.dumps(payload).encode() if payload is not None else None
    headers = {"Accept": "application/json"}
    if data is not None:
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(f"{base_url.rstrip('/')}{path}", data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read().decode()
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode(errors="replace")
        try:
            detail: Any = json.loads(raw)
        except json.JSONDecodeError:
            detail = raw
        raise SmokeError(f"HTTP {exc.code} for {method} {path}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise SmokeError(f"Request failed for {method} {path}: {exc.reason}") from exc
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise SmokeError(f"Invalid JSON for {method} {path}: {exc}") from exc
    if not isinstance(parsed, dict):
        raise SmokeError(f"{method} {path} did not return a JSON object")
    return parsed


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SmokeError(message)


def validate_capability(capability: dict[str, Any]) -> None:
    require(isinstance(capability.get("merchant"), dict), "capability.merchant must be present")
    require(isinstance(capability.get("readiness"), dict), "capability.readiness must be present")
    setup_guide = capability.get("setup_guide")
    require(isinstance(setup_guide, dict), "capability.setup_guide must be present")
    require(isinstance(setup_guide.get("steps"), list) and setup_guide["steps"], "setup_guide.steps must be non-empty")
    step_ids = {str(step.get("id") or "") for step in setup_guide["steps"] if isinstance(step, dict)}
    for expected in {"merchant_identity", "products", "tax_shipping", "payment_verifier", "registry", "sandbox_test"}:
        require(expected in step_ids, f"setup_guide missing step: {expected}")
    endpoints = capability.get("endpoints")
    require(isinstance(endpoints, dict), "capability.endpoints must be present")
    for endpoint in ["catalog", "quote"]:
        require(bool(endpoints.get(endpoint)), f"capability.endpoints.{endpoint} must be present")


def validate_manifest(manifest: dict[str, Any]) -> None:
    require(isinstance(manifest.get("merchant"), dict), "manifest.merchant must be present")
    require(isinstance(manifest.get("endpoints"), dict), "manifest.endpoints must be present")
    require(bool(manifest["endpoints"].get("catalog")), "manifest catalog endpoint missing")
    require(bool(manifest["endpoints"].get("quote")), "manifest quote endpoint missing")
    require(isinstance(manifest.get("discovery"), dict), "manifest.discovery must be present")
    require(bool(manifest["discovery"].get("registry_claim_hash")), "manifest registry claim hash missing")


def catalog_products(catalog: dict[str, Any]) -> list[dict[str, Any]]:
    products = catalog.get("products")
    require(isinstance(products, list) and products, "catalog.products must be non-empty")
    usable = [
        product
        for product in products
        if isinstance(product, dict)
        and product.get("eligible_for_agent_checkout") is not False
        and str(product.get("availability") or "in_stock") == "in_stock"
    ]
    require(bool(usable), "catalog has no in-stock AgentCart-eligible products")
    return usable


def select_product(catalog: dict[str, Any], product_id: str = "") -> dict[str, Any]:
    products = catalog_products(catalog)
    if product_id:
        for product in products:
            if str(product.get("product_id") or product.get("id") or "") == product_id:
                return product
        raise SmokeError(f"Product not found in catalog: {product_id}")
    return products[0]


def quote_payload(product: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    product_id = str(product.get("product_id") or product.get("id") or "")
    require(bool(product_id), "selected catalog product is missing product_id")
    return {
        "items": [{"product_id": product_id, "quantity": args.quantity}],
        "ship_to": {
            "country": args.country,
            "postcode": args.postcode,
            "city": args.city,
            "address_1": args.address,
        },
    }


def validate_quote(quote: dict[str, Any], *, args: argparse.Namespace, product: dict[str, Any]) -> None:
    require(str(quote.get("id") or "").startswith("woo_quote_"), "quote.id must be a Woo quote id")
    require(bool(quote.get("quote_hash")), "quote.quote_hash is required")
    require(str(quote.get("currency") or "") == args.currency, f"quote.currency must be {args.currency}")
    require(isinstance(quote.get("merchant"), dict), "quote.merchant must be present")
    items = quote.get("items")
    require(isinstance(items, list) and items, "quote.items must be non-empty")
    product_ids = {str(item.get("product_id") or "") for item in items if isinstance(item, dict)}
    expected_product_id = str(product.get("product_id") or product.get("id") or "")
    require(expected_product_id in product_ids, "quote.items must include the selected product")

    subtotal = int(quote.get("subtotal_cents") or 0)
    total = int(quote.get("total_cents") or 0)
    shipping = quote.get("shipping")
    require(subtotal > 0, "quote.subtotal_cents must be positive")
    require(total > 0, "quote.total_cents must be positive")
    require(isinstance(shipping, dict), "quote.shipping must be present")
    shipping_cents = int(shipping.get("amount_cents") or 0)
    require(str(shipping.get("source") or "") == "woocommerce_cart", "quote.shipping.source must be woocommerce_cart")
    if args.expect_shipping_cents is not None:
        require(
            shipping_cents == int(args.expect_shipping_cents),
            f"quote.shipping.amount_cents expected {args.expect_shipping_cents}, got {shipping_cents}",
        )
    if args.require_shipping:
        require(shipping_cents > 0, "quote.shipping.amount_cents must be positive")
    require(abs(total - (subtotal + shipping_cents)) <= args.rounding_tolerance_cents, "quote total must equal subtotal + shipping within tolerance")

    vat_lines = quote.get("vat_lines")
    require(isinstance(vat_lines, list), "quote.vat_lines must be a list")
    if args.require_vat_lines:
        require(bool(vat_lines), "quote.vat_lines must be non-empty")
        require(any(int(line.get("vat_cents") or 0) > 0 for line in vat_lines if isinstance(line, dict)), "quote.vat_lines must include VAT cents")

    payment = quote.get("payment_requirements")
    require(isinstance(payment, dict), "quote.payment_requirements must be present")
    require(isinstance(payment.get("protocols"), list) and payment["protocols"], "quote.payment_requirements.protocols must be non-empty")
    require(isinstance(quote.get("merchant_policy"), dict), "quote.merchant_policy must be present")
    require(isinstance(quote.get("delivery_window"), dict), "quote.delivery_window must be present")


def run(args: argparse.Namespace) -> dict[str, Any]:
    base_url = args.base_url.rstrip("/")
    capability = http_json(base_url, "/wp-json/agentcart/v1/capability")
    validate_capability(capability)
    manifest = http_json(base_url, "/.well-known/agentcart.json")
    validate_manifest(manifest)
    catalog_query = urllib.parse.urlencode({"search": args.search, "limit": args.limit})
    catalog = http_json(base_url, f"/wp-json/agentcart/v1/catalog?{catalog_query}")
    product = select_product(catalog, args.product_id)
    payload = quote_payload(product, args)
    quote = http_json(base_url, "/wp-json/agentcart/v1/quote", method="POST", payload=payload)
    validate_quote(quote, args=args, product=product)
    return {
        "ok": True,
        "base_url": base_url,
        "merchant": capability.get("merchant", {}),
        "product": {
            "product_id": product.get("product_id") or product.get("id"),
            "title": product.get("title"),
        },
        "quote": {
            "id": quote.get("id"),
            "total_cents": quote.get("total_cents"),
            "currency": quote.get("currency"),
            "shipping_cents": (quote.get("shipping") or {}).get("amount_cents"),
            "vat_line_count": len(quote.get("vat_lines") or []),
            "quote_hash": quote.get("quote_hash"),
        },
        "setup_next_step": (capability.get("setup_guide") or {}).get("next_step"),
    }


def parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Smoke test a live AgentCart ShopBridge WooCommerce endpoint.")
    parser.add_argument("--base-url", default=os.getenv("AGENTCART_WOO_SMOKE_BASE_URL", "").strip())
    parser.add_argument("--search", default=os.getenv("AGENTCART_WOO_SMOKE_SEARCH", "tea"))
    parser.add_argument("--product-id", default=os.getenv("AGENTCART_WOO_SMOKE_PRODUCT_ID", ""))
    parser.add_argument("--quantity", type=int, default=int(os.getenv("AGENTCART_WOO_SMOKE_QUANTITY", "1")))
    parser.add_argument("--country", default=os.getenv("AGENTCART_WOO_SMOKE_COUNTRY", "DE"))
    parser.add_argument("--postcode", default=os.getenv("AGENTCART_WOO_SMOKE_POSTCODE", "10115"))
    parser.add_argument("--city", default=os.getenv("AGENTCART_WOO_SMOKE_CITY", "Berlin"))
    parser.add_argument("--address", default=os.getenv("AGENTCART_WOO_SMOKE_ADDRESS", "Demo Street 1"))
    parser.add_argument("--currency", default=os.getenv("AGENTCART_WOO_SMOKE_CURRENCY", "EUR"))
    parser.add_argument("--limit", type=int, default=int(os.getenv("AGENTCART_WOO_SMOKE_LIMIT", "12")))
    parser.add_argument("--rounding-tolerance-cents", type=int, default=int(os.getenv("AGENTCART_WOO_SMOKE_ROUNDING_TOLERANCE_CENTS", "1")))
    parser.add_argument("--expect-shipping-cents", type=int, default=None)
    parser.add_argument("--require-shipping", action="store_true")
    parser.add_argument("--require-vat-lines", action="store_true")
    return parser


def main() -> int:
    args = parser().parse_args()
    if not args.base_url:
        print("AGENTCART_WOO_SMOKE_BASE_URL or --base-url is required", file=sys.stderr)
        return 2
    try:
        result = run(args)
    except SmokeError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2), file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
