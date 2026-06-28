#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import pathlib
import sys
from typing import Any


ROOT = pathlib.Path(__file__).resolve().parents[1]
DEFAULT_CONTRACT = ROOT / "gateway" / "config" / "shopbridge_endpoint_contract.json"
PLUGIN_FILE = ROOT / "woocommerce-shopbridge" / "agentcart-shopbridge" / "agentcart-shopbridge.php"
README_FILE = ROOT / "woocommerce-shopbridge" / "agentcart-shopbridge" / "readme.txt"

EXPECTED_ENDPOINTS = {
    "manifest",
    "catalog",
    "quote",
    "order_create",
    "order_status",
    "refund",
    "cancellation",
}

EXPECTED_INVARIANTS = {
    "quote_hash_binds_money_and_recipient",
    "payment_contract_hash_binds_quote_total_and_rail",
    "checkout_requires_quote_hash_and_idempotency",
    "checkout_revalidates_stock_shipping_tax_and_price",
    "order_status_requires_token_or_signed_request",
    "refund_and_cancellation_are_aftercare_not_silent_payment_claims",
}


def load_json(path: pathlib.Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"{path}: invalid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise SystemExit(f"{path}: contract root must be an object")
    return data


def require(condition: bool, message: str, errors: list[str]) -> None:
    if not condition:
        errors.append(message)


def path_exists(value: Any, dotted_path: str) -> bool:
    parts = dotted_path.split(".")
    return _path_exists(value, parts)


def _path_exists(value: Any, parts: list[str]) -> bool:
    if not parts:
        return True
    current = parts[0]
    rest = parts[1:]
    if current.endswith("[]"):
        key = current[:-2]
        if not isinstance(value, dict) or key not in value or not isinstance(value[key], list) or not value[key]:
            return False
        return any(_path_exists(item, rest) for item in value[key])
    if not isinstance(value, dict) or current not in value:
        return False
    return _path_exists(value[current], rest)


def source_contains_endpoint(path: str, source: str) -> bool:
    if path in source:
        return True
    if path.startswith("/wp-json/agentcart/v1/"):
        route = "/" + path.split("/wp-json/agentcart/v1/", 1)[1]
        route = route.replace("{id}", "(?P<id>[\\d]+)")
        return route in source
    return False


def validate_endpoint(endpoint: dict[str, Any], *, index: int, source: str) -> list[str]:
    errors: list[str] = []
    endpoint_id = str(endpoint.get("id") or "")
    require(endpoint_id != "", f"endpoints[{index}].id is required", errors)
    require(str(endpoint.get("method") or "") in {"GET", "POST"}, f"{endpoint_id}: method must be GET or POST", errors)
    path = str(endpoint.get("path") or "")
    require(path.startswith("/"), f"{endpoint_id}: path must be absolute", errors)
    require(str(endpoint.get("auth") or "") != "", f"{endpoint_id}: auth is required", errors)
    require(str(endpoint.get("stability") or "") == "frozen_alpha", f"{endpoint_id}: stability must be frozen_alpha", errors)
    require(str(endpoint.get("purpose") or "") != "", f"{endpoint_id}: purpose is required", errors)
    require(source_contains_endpoint(path, source), f"{endpoint_id}: endpoint path is not documented or registered: {path}", errors)

    fixtures = endpoint.get("fixtures")
    require(isinstance(fixtures, dict), f"{endpoint_id}: fixtures must be an object", errors)
    response = fixtures.get("response") if isinstance(fixtures, dict) else None
    require(isinstance(response, dict), f"{endpoint_id}: fixtures.response must be an object", errors)
    required_response_paths = endpoint.get("required_response_paths")
    require(
        isinstance(required_response_paths, list) and bool(required_response_paths),
        f"{endpoint_id}: required_response_paths must be a non-empty list",
        errors,
    )
    if isinstance(response, dict) and isinstance(required_response_paths, list):
        for field_path in required_response_paths:
            field_path = str(field_path)
            require(path_exists(response, field_path), f"{endpoint_id}: fixture response missing {field_path}", errors)

    required_request_paths = endpoint.get("required_request_paths")
    if required_request_paths is not None:
        request = fixtures.get("request") if isinstance(fixtures, dict) else None
        require(isinstance(request, dict), f"{endpoint_id}: fixtures.request must be an object when request paths are required", errors)
        require(isinstance(required_request_paths, list) and bool(required_request_paths), f"{endpoint_id}: required_request_paths must be a non-empty list", errors)
        if isinstance(request, dict) and isinstance(required_request_paths, list):
            for field_path in required_request_paths:
                field_path = str(field_path)
                require(path_exists(request, field_path), f"{endpoint_id}: fixture request missing {field_path}", errors)
    return errors


def validate_runtime_checks(data: dict[str, Any], errors: list[str]) -> None:
    checks = data.get("runtime_checks")
    require(isinstance(checks, list) and bool(checks), "runtime_checks must be a non-empty list", errors)
    if not isinstance(checks, list):
        return
    for index, check in enumerate(checks):
        if not isinstance(check, dict):
            errors.append(f"runtime_checks[{index}] must be an object")
            continue
        check_id = str(check.get("id") or f"runtime_checks[{index}]")
        path = ROOT / str(check.get("path") or "")
        require(path.exists(), f"{check_id}: path does not exist: {path}", errors)
        covers = check.get("covers")
        require(isinstance(covers, list) and bool(covers), f"{check_id}: covers must be a non-empty list", errors)
        if isinstance(covers, list):
            for endpoint_id in covers:
                require(str(endpoint_id) in EXPECTED_ENDPOINTS, f"{check_id}: unknown covered endpoint {endpoint_id}", errors)
        symbols = check.get("symbols")
        require(isinstance(symbols, list) and bool(symbols), f"{check_id}: symbols must be a non-empty list", errors)
        if path.exists() and isinstance(symbols, list):
            source = path.read_text(encoding="utf-8")
            for symbol in symbols:
                require(str(symbol) in source, f"{check_id}: symbol not found in {path}: {symbol}", errors)


def validate_documentation(data: dict[str, Any], errors: list[str]) -> None:
    docs = data.get("documentation")
    require(isinstance(docs, list) and bool(docs), "documentation must be a non-empty list", errors)
    if not isinstance(docs, list):
        return
    for doc in docs:
        path = ROOT / str(doc)
        require(path.exists(), f"documentation path does not exist: {doc}", errors)


def validate_contract(data: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    require(data.get("schema") == "agentcart.shopbridge_endpoint_contract.v1", "schema must be agentcart.shopbridge_endpoint_contract.v1", errors)
    require(str(data.get("version") or "") != "", "version is required", errors)
    require(data.get("status") == "implemented_alpha", "status must be implemented_alpha", errors)
    require(data.get("gate_id") == "WOO-002", "gate_id must be WOO-002", errors)
    plugin = data.get("plugin")
    require(isinstance(plugin, dict), "plugin must be an object", errors)
    if isinstance(plugin, dict):
        require(plugin.get("slug") == "agentcart-shopbridge", "plugin.slug must be agentcart-shopbridge", errors)
        require(plugin.get("adapter") == "agentcart.shopbridge.v1", "plugin.adapter must be agentcart.shopbridge.v1", errors)
        require(plugin.get("manifest_is_capability_document") is True, "plugin.manifest_is_capability_document must be true", errors)

    versioning = data.get("versioning_policy")
    require(isinstance(versioning, dict), "versioning_policy must be an object", errors)
    if isinstance(versioning, dict):
        require(versioning.get("compatibility_level") == "alpha_frozen", "versioning_policy.compatibility_level must be alpha_frozen", errors)
        breaking = versioning.get("breaking_changes_require")
        require(isinstance(breaking, list) and "contract version bump" in breaking, "breaking_changes_require must include contract version bump", errors)
        require(versioning.get("field_removal_allowed_without_bump") is False, "field removal must require a version bump", errors)

    source = PLUGIN_FILE.read_text(encoding="utf-8") + "\n" + README_FILE.read_text(encoding="utf-8")
    endpoints = data.get("endpoints")
    require(isinstance(endpoints, list) and bool(endpoints), "endpoints must be a non-empty list", errors)
    seen: set[str] = set()
    if isinstance(endpoints, list):
        for index, endpoint in enumerate(endpoints):
            if not isinstance(endpoint, dict):
                errors.append(f"endpoints[{index}] must be an object")
                continue
            endpoint_id = str(endpoint.get("id") or "")
            require(endpoint_id not in seen, f"duplicate endpoint id: {endpoint_id}", errors)
            seen.add(endpoint_id)
            errors.extend(validate_endpoint(endpoint, index=index, source=source))
    require(EXPECTED_ENDPOINTS.issubset(seen), f"contract must include endpoints: {', '.join(sorted(EXPECTED_ENDPOINTS - seen))}", errors)

    invariants = data.get("invariants")
    require(isinstance(invariants, list) and bool(invariants), "invariants must be a non-empty list", errors)
    invariant_ids = {
        str(item.get("id") or "")
        for item in invariants
        if isinstance(item, dict)
    }
    require(EXPECTED_INVARIANTS.issubset(invariant_ids), f"contract must include invariants: {', '.join(sorted(EXPECTED_INVARIANTS - invariant_ids))}", errors)
    for invariant in invariants if isinstance(invariants, list) else []:
        if not isinstance(invariant, dict):
            errors.append("invariants entries must be objects")
            continue
        require(str(invariant.get("description") or "") != "", f"{invariant.get('id')}: description is required", errors)

    validate_runtime_checks(data, errors)
    validate_documentation(data, errors)
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate the frozen AgentCart ShopBridge endpoint contract.")
    parser.add_argument("--contract", type=pathlib.Path, default=DEFAULT_CONTRACT)
    args = parser.parse_args(argv)

    data = load_json(args.contract)
    errors = validate_contract(data)
    if errors:
        for error in errors:
            print(f"shopbridge endpoint contract check failed: {error}", file=sys.stderr)
        return 1
    print(f"shopbridge endpoint contract ok: {args.contract}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
