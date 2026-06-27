#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from typing import Any


SMOKE_USER_AGENT = os.getenv("AGENTCART_WOO_SMOKE_USER_AGENT", f"AgentCartShopBridgeSmoke/{os.getpid()}")


class SmokeError(AssertionError):
    pass


class HttpJsonError(SmokeError):
    def __init__(
        self,
        message: str,
        *,
        status: int,
        method: str,
        path: str,
        detail: Any,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(message)
        self.status = status
        self.method = method
        self.path = path
        self.detail = detail
        self.headers = headers or {}


REGISTRY_HASH_EXCLUDED_KEYS = {
    "signature",
    "verification",
    "manifest",
    "manifest_snapshot",
    "proof_snapshot",
    "revocation_snapshot",
}


def http_json(
    base_url: str,
    path: str,
    *,
    method: str = "GET",
    payload: dict[str, Any] | None = None,
    timeout: int = 30,
) -> dict[str, Any]:
    data = json.dumps(payload).encode() if payload is not None else None
    headers = {"Accept": "application/json", "User-Agent": SMOKE_USER_AGENT}
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
        raise HttpJsonError(
            f"HTTP {exc.code} for {method} {path}: {detail}",
            status=int(exc.code),
            method=method,
            path=path,
            detail=detail,
            headers=dict(exc.headers.items()) if exc.headers else {},
        ) from exc
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


def canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_hex(value: Any) -> str:
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def registry_signature_payload(record: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in record.items()
        if key not in REGISTRY_HASH_EXCLUDED_KEYS
    }


def registry_record_hash(record: dict[str, Any]) -> str:
    return sha256_hex(registry_signature_payload(record))


def validate_capability(capability: dict[str, Any]) -> None:
    require(isinstance(capability.get("merchant"), dict), "capability.merchant must be present")
    require(isinstance(capability.get("readiness"), dict), "capability.readiness must be present")
    validate_protocol_profiles(capability, "capability")
    setup_guide = capability.get("setup_guide")
    require(isinstance(setup_guide, dict), "capability.setup_guide must be present")
    require(isinstance(setup_guide.get("steps"), list) and setup_guide["steps"], "setup_guide.steps must be non-empty")
    step_ids = {str(step.get("id") or "") for step in setup_guide["steps"] if isinstance(step, dict)}
    for expected in {"merchant_identity", "products", "tax_shipping", "payment_verifier", "registry", "sandbox_test"}:
        require(expected in step_ids, f"setup_guide missing step: {expected}")
    endpoints = capability.get("endpoints")
    require(isinstance(endpoints, dict), "capability.endpoints must be present")
    for endpoint in ["registry_bundle", "catalog", "quote"]:
        require(bool(endpoints.get(endpoint)), f"capability.endpoints.{endpoint} must be present")


def validate_production_setup(capability: dict[str, Any]) -> dict[str, Any]:
    setup_guide = capability.get("setup_guide")
    require(isinstance(setup_guide, dict), "capability.setup_guide must be present")
    steps = setup_guide.get("steps")
    require(isinstance(steps, list), "setup_guide.steps must be a list")
    blockers: list[dict[str, str]] = []
    for step in steps:
        if not isinstance(step, dict):
            continue
        required_for = step.get("required_for")
        if not isinstance(required_for, list) or "production" not in {str(item) for item in required_for}:
            continue
        state = str(step.get("state") or "")
        if state != "complete":
            blockers.append(
                {
                    "id": str(step.get("id") or ""),
                    "label": str(step.get("label") or ""),
                    "state": state,
                    "summary": str(step.get("summary") or ""),
                }
            )
    if setup_guide.get("production_complete") is not True or blockers:
        raise SmokeError(
            "production setup is incomplete: "
            + ", ".join(
                f"{blocker['id'] or blocker['label']}={blocker['state'] or 'unknown'}"
                for blocker in blockers
            )
        )
    validate_protocol_profiles(capability, "capability", require_available=True)
    return {
        "production_complete": True,
        "checked_step_count": len(
            [
                step
                for step in steps
                if isinstance(step, dict)
                and isinstance(step.get("required_for"), list)
                and "production" in {str(item) for item in step.get("required_for", [])}
            ]
        ),
    }


def validate_manifest(manifest: dict[str, Any]) -> None:
    require(isinstance(manifest.get("merchant"), dict), "manifest.merchant must be present")
    validate_protocol_profiles(manifest, "manifest")
    require(isinstance(manifest.get("endpoints"), dict), "manifest.endpoints must be present")
    require(bool(manifest["endpoints"].get("catalog")), "manifest catalog endpoint missing")
    require(bool(manifest["endpoints"].get("quote")), "manifest quote endpoint missing")
    require(isinstance(manifest.get("discovery"), dict), "manifest.discovery must be present")
    require(bool(manifest["discovery"].get("registry_claim_hash")), "manifest registry claim hash missing")
    require(bool(manifest["discovery"].get("registry_bundle_url")), "manifest registry bundle URL missing")


def validate_protocol_profiles(document: dict[str, Any], label: str, *, require_available: bool = False) -> None:
    profiles = document.get("protocol_profiles")
    require(isinstance(profiles, list) and profiles, f"{label}.protocol_profiles must be non-empty")
    profile_ids = {str(profile.get("id") or "") for profile in profiles if isinstance(profile, dict)}
    require("agentcart-shopbridge" in profile_ids, f"{label}.protocol_profiles must include agentcart-shopbridge")
    for profile in profiles:
        require(isinstance(profile, dict), f"{label}.protocol_profiles entries must be objects")
        require(bool(profile.get("id")), f"{label}.protocol_profiles entry id missing")
        profile_id = str(profile.get("id") or "")
        if require_available:
            require(profile.get("available") is not False, f"{label}.protocol_profiles must not advertise unavailable profile: {profile_id}")
            require(profile.get("setup_required") is not True, f"{label}.protocol_profiles must not advertise setup-required profile: {profile_id}")
            require(str(profile.get("status") or "") != "setup_required", f"{label}.protocol_profiles must be production-available: {profile_id}")
        elif profile.get("available") is False or profile.get("setup_required") is True:
            reasons = profile.get("unavailable_reasons")
            require(
                isinstance(reasons, list) and bool(reasons),
                f"{label}.protocol_profiles setup-required profile must include unavailable_reasons: {profile_id}",
            )
        if profile.get("id") == "signed-http-ready":
            schemes = profile.get("signature_schemes")
            require(isinstance(schemes, list) and bool(schemes), f"{label}.signed-http-ready signature_schemes must be a non-empty list")
            require(
                profile.get("signature_scheme") in {"agentcart-hmac-sha256-v1", "agentcart-rsa-sha256-v1"},
                f"{label}.signed-http-ready signature_scheme mismatch",
            )
            require(isinstance(profile.get("headers"), dict), f"{label}.signed-http-ready headers must be present")
            for header in ["signed_method", "signed_path", "content_digest", "nonce", "expires_at", "signature_alg", "signature"]:
                require(bool(profile["headers"].get(header)), f"{label}.signed-http-ready missing header mapping: {header}")
            require(isinstance(profile.get("required_for"), list), f"{label}.signed-http-ready required_for must be a list")


def validate_registry_bundle(
    bundle: dict[str, Any],
    *,
    manifest: dict[str, Any],
    proof: dict[str, Any],
    revocations: dict[str, Any],
) -> dict[str, Any]:
    require(bundle.get("type") == "agentcart-registry-onboarding-bundle", "registry bundle type mismatch")
    record = bundle.get("registry_record")
    require(isinstance(record, dict), "registry bundle registry_record must be present")
    record_hash = registry_record_hash(record)
    require(bundle.get("record_hash") == record_hash, "registry bundle record_hash does not match registry_record")

    merchant = manifest.get("merchant") if isinstance(manifest.get("merchant"), dict) else {}
    require(str(record.get("merchant_id") or "") == str(merchant.get("id") or ""), "registry record merchant_id must match manifest merchant.id")
    discovery = manifest.get("discovery") if isinstance(manifest.get("discovery"), dict) else {}
    require(
        str(record.get("registry_claim_hash") or "") == str(discovery.get("registry_claim_hash") or ""),
        "registry record claim hash must match manifest discovery claim hash",
    )
    if manifest.get("manifest_url"):
        require(str(record.get("manifest_url") or "") == str(manifest.get("manifest_url") or ""), "registry record manifest_url must match manifest")

    proof_from_bundle = bundle.get("proof_document_expected")
    require(isinstance(proof_from_bundle, dict), "registry bundle proof_document_expected must be present")
    for candidate, label in [(proof_from_bundle, "bundle proof"), (proof, "live proof")]:
        require(candidate.get("record_hash") == record_hash, f"{label} record_hash must match registry record")
        require(str(candidate.get("merchant_id") or "") == str(record.get("merchant_id") or ""), f"{label} merchant_id must match registry record")
        require(str(candidate.get("domain") or "") == str(record.get("domain") or ""), f"{label} domain must match registry record")
        require(str(candidate.get("manifest_url") or "") == str(record.get("manifest_url") or ""), f"{label} manifest_url must match registry record")

    require(revocations.get("type") == "agentcart-registry-revocations", "revocation document type mismatch")
    require(str(revocations.get("merchant_id") or "") == str(record.get("merchant_id") or ""), "revocation merchant_id must match registry record")
    require(isinstance(revocations.get("revocations"), list), "revocation document revocations must be a list")
    revoked_hashes = {
        str(item.get("record_hash") or "")
        for item in revocations.get("revocations", [])
        if isinstance(item, dict)
    }
    require(record_hash not in revoked_hashes, "registry record is listed in merchant revocation document")

    registry_feed = bundle.get("registry_feed")
    require(isinstance(registry_feed, dict), "registry bundle registry_feed must be present")
    entries = registry_feed.get("entries")
    require(isinstance(entries, list) and entries, "registry bundle registry_feed.entries must be non-empty")
    require(any(isinstance(entry, dict) and registry_record_hash(entry) == record_hash for entry in entries), "registry_feed.entries must include the registry_record")
    return {"record_hash": record_hash, "merchant_id": str(record.get("merchant_id") or "")}


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


def validate_rate_limit_error(error: HttpJsonError, *, expected_bucket: str) -> dict[str, Any]:
    require(error.status == 429, f"expected HTTP 429 rate limit response, got {error.status}")
    require(isinstance(error.detail, dict), "rate limit response must be a JSON object")
    require(error.detail.get("code") == "agentcart_rate_limited", "rate limit response code mismatch")
    data = error.detail.get("data")
    require(isinstance(data, dict), "rate limit response data must be present")
    require(int(data.get("status") or 0) == 429, "rate limit data.status must be 429")
    require(str(data.get("bucket") or "") == expected_bucket, f"rate limit bucket must be {expected_bucket}")
    require(int(data.get("limit") or 0) > 0, "rate limit data.limit must be positive")
    require(int(data.get("window_seconds") or 0) > 0, "rate limit data.window_seconds must be positive")
    require(int(data.get("retry_after_seconds") or 0) > 0, "rate limit retry_after_seconds must be positive")
    require("remaining" in data, "rate limit remaining metadata missing")
    require(bool(data.get("reset_at")), "rate limit reset_at metadata missing")
    return data


def rate_limit_probe_scenarios(capability: dict[str, Any], selected_buckets: set[str]) -> list[dict[str, Any]]:
    rate_limits = capability.get("rate_limits")
    require(isinstance(rate_limits, dict), "capability.rate_limits must be present for abuse smoke")
    candidates = {
        "quote": {"path": "/wp-json/agentcart/v1/quote", "method": "POST", "payload": {}},
        "checkout": {"path": "/wp-json/agentcart/v1/orders", "method": "POST", "payload": {}},
        "order_status": {"path": "/wp-json/agentcart/v1/orders/0/status", "method": "GET", "payload": None},
        "refund": {"path": "/wp-json/agentcart/v1/orders/0/refunds", "method": "POST", "payload": {}},
        "cancellation": {"path": "/wp-json/agentcart/v1/orders/0/cancellations", "method": "POST", "payload": {}},
        "registry": {"path": "/.well-known/agentcart-registry-proof.json", "method": "GET", "payload": None},
    }
    scenarios: list[dict[str, Any]] = []
    for bucket in sorted(selected_buckets):
        require(bucket in candidates, f"unsupported rate-limit abuse bucket: {bucket}")
        policy = rate_limits.get(bucket)
        require(isinstance(policy, dict), f"capability.rate_limits.{bucket} must be present")
        scenario = dict(candidates[bucket])
        scenario["bucket"] = bucket
        scenario["limit"] = int(policy.get("limit") or 0)
        require(scenario["limit"] > 0, f"capability.rate_limits.{bucket}.limit must be positive")
        scenarios.append(scenario)
    return scenarios


def expect_rate_limit_exhaustion(
    base_url: str,
    scenario: dict[str, Any],
    *,
    max_attempts: int,
) -> dict[str, Any]:
    bucket = str(scenario["bucket"])
    # Fixed-window limiters can roll over while the probe is running. Allow up
    # to two windows so a live test that starts near a boundary still proves
    # that the next full window returns 429.
    attempts = min((int(scenario["limit"]) * 2) + 2, max(1, max_attempts))
    last_error = "no response"
    for index in range(attempts):
        try:
            http_json(
                base_url,
                str(scenario["path"]),
                method=str(scenario["method"]),
                payload=scenario.get("payload"),
                timeout=10,
            )
        except HttpJsonError as exc:
            if exc.status == 429:
                data = validate_rate_limit_error(exc, expected_bucket=bucket)
                return {
                    "bucket": bucket,
                    "path": scenario["path"],
                    "attempts": index + 1,
                    "limit": data["limit"],
                    "retry_after_seconds": data["retry_after_seconds"],
                    "reset_at": data["reset_at"],
                }
            last_error = str(exc)
    raise SmokeError(f"rate limit bucket {bucket} did not return 429 within {attempts} attempts; last_error={last_error}")


def run_rate_limit_abuse_checks(base_url: str, capability: dict[str, Any], args: argparse.Namespace) -> list[dict[str, Any]]:
    selected = {
        bucket.strip()
        for bucket in str(args.rate_limit_buckets or "").split(",")
        if bucket.strip()
    }
    require(bool(selected), "at least one rate-limit abuse bucket must be selected")
    scenarios = rate_limit_probe_scenarios(capability, selected)
    return [
        expect_rate_limit_exhaustion(base_url, scenario, max_attempts=args.rate_limit_max_attempts)
        for scenario in scenarios
    ]


def run(args: argparse.Namespace) -> dict[str, Any]:
    base_url = args.base_url.rstrip("/")
    capability = http_json(base_url, "/wp-json/agentcart/v1/capability")
    validate_capability(capability)
    production_setup = None
    if args.require_production_ready:
        production_setup = validate_production_setup(capability)
    manifest = http_json(base_url, "/.well-known/agentcart.json")
    validate_manifest(manifest)
    registry_bundle = http_json(base_url, "/.well-known/agentcart-registry-bundle.json")
    registry_proof = http_json(base_url, "/.well-known/agentcart-registry-proof.json")
    registry_revocations = http_json(base_url, "/.well-known/agentcart-registry-revocations.json")
    registry = validate_registry_bundle(
        registry_bundle,
        manifest=manifest,
        proof=registry_proof,
        revocations=registry_revocations,
    )
    catalog_query = urllib.parse.urlencode({"search": args.search, "limit": args.limit})
    catalog = http_json(base_url, f"/wp-json/agentcart/v1/catalog?{catalog_query}")
    product = select_product(catalog, args.product_id)
    payload = quote_payload(product, args)
    quote = http_json(base_url, "/wp-json/agentcart/v1/quote", method="POST", payload=payload)
    validate_quote(quote, args=args, product=product)
    rate_limit_abuse = []
    if args.abuse_rate_limits:
        rate_limit_abuse = run_rate_limit_abuse_checks(base_url, capability, args)
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
        "registry": registry,
        "rate_limit_abuse": rate_limit_abuse,
        "production_setup": production_setup,
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
    parser.add_argument(
        "--require-production-ready",
        action="store_true",
        default=os.getenv("AGENTCART_WOO_SMOKE_REQUIRE_PRODUCTION_READY", "").strip() == "1",
        help="Fail if the live ShopBridge capability setup guide still has production-required setup steps.",
    )
    parser.add_argument(
        "--abuse-rate-limits",
        action="store_true",
        default=os.getenv("AGENTCART_WOO_SMOKE_ABUSE_RATE_LIMITS", "").strip() == "1",
        help="Exhaust selected live REST rate-limit buckets and require a 429 response.",
    )
    parser.add_argument(
        "--rate-limit-buckets",
        default=os.getenv(
            "AGENTCART_WOO_SMOKE_RATE_LIMIT_BUCKETS",
            "quote,checkout,order_status,refund,cancellation,registry",
        ),
    )
    parser.add_argument(
        "--rate-limit-max-attempts",
        type=int,
        default=int(os.getenv("AGENTCART_WOO_SMOKE_RATE_LIMIT_MAX_ATTEMPTS", "200")),
    )
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
