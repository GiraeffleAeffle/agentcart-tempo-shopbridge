#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib
import importlib.util
import json
import pathlib
import sys
from typing import Any


REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
DEFAULT_MAPPING = REPO_ROOT / "gateway" / "config" / "ap2_mandate_mapping.json"

REQUIRED_MAPPING_FIELDS = {
    "checkout_mandate",
    "payment_mandate",
    "audit_bindings",
    "safety",
    "mapping_hash",
}

REQUIRED_INVARIANTS = {
    "human_approval_required",
    "quote_hash_preserved",
    "payment_contract_hash_preserved",
    "amount_currency_bound",
    "merchant_bound",
    "not_signed_vdc_claim",
    "trusted_surface_signature_required",
}

REQUIRED_RUNTIME_PATHS = {
    "agentcart-service-approval",
    "direct-skill-approval",
    "direct-skill-payment-handoff",
}

REQUIRED_RUNTIME_CHECKS = {
    "service-approval-record-mapping",
    "direct-skill-approval-packet-mapping",
    "direct-skill-payment-handoff-mapping",
}


def load_json(path: pathlib.Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"{path}: invalid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise SystemExit(f"{path}: mapping root must be an object")
    return data


def require(condition: bool, message: str, errors: list[str]) -> None:
    if not condition:
        errors.append(message)


def repo_path(path_value: str) -> pathlib.Path:
    path = pathlib.Path(path_value)
    return path if path.is_absolute() else REPO_ROOT / path


def validate_field_map(data: dict[str, Any], errors: list[str]) -> None:
    field_map = data.get("field_map")
    require(isinstance(field_map, dict), "field_map must be an object", errors)
    if not isinstance(field_map, dict):
        return

    checkout = field_map.get("checkout_mandate")
    require(isinstance(checkout, dict), "field_map.checkout_mandate must be an object", errors)
    if isinstance(checkout, dict):
        require(checkout.get("vct") == "mandate.checkout.1", "checkout_mandate.vct must be mandate.checkout.1", errors)
        checkout_fields = checkout.get("fields")
        require(isinstance(checkout_fields, list) and bool(checkout_fields), "checkout_mandate.fields must be non-empty", errors)
        if isinstance(checkout_fields, list):
            for required in ("merchant", "items", "total.amount_cents", "total.currency", "quote_hash", "expires_at"):
                require(required in checkout_fields, f"checkout_mandate.fields missing {required}", errors)

    payment = field_map.get("payment_mandate")
    require(isinstance(payment, dict), "field_map.payment_mandate must be an object", errors)
    if isinstance(payment, dict):
        require(payment.get("vct") == "mandate.payment.1", "payment_mandate.vct must be mandate.payment.1", errors)
        payment_fields = payment.get("fields")
        require(isinstance(payment_fields, list) and bool(payment_fields), "payment_mandate.fields must be non-empty", errors)
        if isinstance(payment_fields, list):
            for required in (
                "transaction_id",
                "checkout_reference_hash",
                "merchant",
                "amount.amount_cents",
                "amount.currency",
                "payment_destination",
                "payment_contract_hash",
                "quote_hash",
            ):
                require(required in payment_fields, f"payment_mandate.fields missing {required}", errors)


def validate_mapping(data: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    require(data.get("schema") == "agentcart.ap2_mandate_mapping.v1", "schema must be agentcart.ap2_mandate_mapping.v1", errors)
    require(data.get("stage") == "external_beta", "stage must be external_beta", errors)
    require(data.get("gate_id") == "STD-002", "gate_id must be STD-002", errors)
    require(data.get("status") == "implemented_alpha", "status must be implemented_alpha", errors)
    require(
        data.get("compliance_claim") == "ap2_style_field_mapping_not_signed_ap2_vdc",
        "compliance_claim must be ap2_style_field_mapping_not_signed_ap2_vdc",
        errors,
    )

    required_fields = data.get("required_mapping_fields")
    require(isinstance(required_fields, list), "required_mapping_fields must be a list", errors)
    if isinstance(required_fields, list):
        missing_fields = REQUIRED_MAPPING_FIELDS - set(required_fields)
        require(not missing_fields, f"missing required mapping fields: {', '.join(sorted(missing_fields))}", errors)

    invariants = data.get("required_invariants")
    require(isinstance(invariants, list), "required_invariants must be a list", errors)
    if isinstance(invariants, list):
        missing_invariants = REQUIRED_INVARIANTS - set(invariants)
        require(not missing_invariants, f"missing required invariants: {', '.join(sorted(missing_invariants))}", errors)

    runtime_paths = data.get("runtime_paths")
    require(isinstance(runtime_paths, list), "runtime_paths must be a list", errors)
    seen_paths: set[str] = set()
    if isinstance(runtime_paths, list):
        for index, runtime_path in enumerate(runtime_paths):
            if not isinstance(runtime_path, dict):
                errors.append(f"runtime_paths[{index}] must be an object")
                continue
            path_id = str(runtime_path.get("id") or "")
            source = str(runtime_path.get("source") or "")
            output = str(runtime_path.get("output") or "")
            covers = runtime_path.get("covers")
            require(path_id != "", f"runtime_paths[{index}].id is required", errors)
            require(path_id not in seen_paths, f"duplicate runtime path id: {path_id}", errors)
            seen_paths.add(path_id)
            require(source != "", f"{path_id}: source is required", errors)
            if source:
                require(repo_path(source).exists(), f"{path_id}: missing source {source}", errors)
            require(output != "", f"{path_id}: output is required", errors)
            require(isinstance(covers, list) and bool(covers), f"{path_id}: covers must be a non-empty list", errors)
    missing_runtime_paths = REQUIRED_RUNTIME_PATHS - seen_paths
    require(not missing_runtime_paths, f"missing runtime paths: {', '.join(sorted(missing_runtime_paths))}", errors)

    validate_field_map(data, errors)

    runtime_checks = data.get("runtime_checks")
    require(isinstance(runtime_checks, list), "runtime_checks must be a list", errors)
    seen_checks: set[str] = set()
    if isinstance(runtime_checks, list):
        for index, check in enumerate(runtime_checks):
            if not isinstance(check, dict):
                errors.append(f"runtime_checks[{index}] must be an object")
                continue
            check_id = str(check.get("id") or "")
            require(check_id != "", f"runtime_checks[{index}].id is required", errors)
            require(check_id not in seen_checks, f"duplicate runtime check id: {check_id}", errors)
            seen_checks.add(check_id)
            require(str(check.get("target") or "") != "", f"{check_id}: target is required", errors)
            require(str(check.get("test") or "") != "", f"{check_id}: test is required", errors)
    missing_checks = REQUIRED_RUNTIME_CHECKS - seen_checks
    require(not missing_checks, f"missing runtime checks: {', '.join(sorted(missing_checks))}", errors)
    return errors


def validate_runtime_test_refs(data: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    runtime_checks = data.get("runtime_checks") if isinstance(data.get("runtime_checks"), list) else []
    for index, check in enumerate(runtime_checks):
        if not isinstance(check, dict):
            continue
        test_ref = str(check.get("test") or "")
        check_id = str(check.get("id") or f"runtime_checks[{index}]")
        if "::" in test_ref:
            file_ref, attr_ref = test_ref.split("::", 1)
            parts = attr_ref.split(".", 1)
            if len(parts) != 2:
                errors.append(f"{check_id}: file test reference must be path::Class.method")
                continue
            test_file = repo_path(file_ref)
            if not test_file.exists():
                errors.append(f"{check_id}: missing test file {test_file}")
                continue
            module_name = f"_agentcart_ap2_mapping_{test_file.stem}_{index}"
            spec = importlib.util.spec_from_file_location(module_name, test_file)
            if spec is None or spec.loader is None:
                errors.append(f"{check_id}: cannot load test file {test_file}")
                continue
            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            try:
                spec.loader.exec_module(module)
            except Exception as exc:  # pragma: no cover - error message path
                errors.append(f"{check_id}: cannot import {test_file}: {exc}")
                continue
            class_name, method_name = parts
            test_class = getattr(module, class_name, None)
            if test_class is None:
                errors.append(f"{check_id}: missing test class {class_name}")
                continue
            if getattr(test_class, method_name, None) is None:
                errors.append(f"{check_id}: missing test method {class_name}.{method_name}")
            continue

        parts = test_ref.rsplit(".", 2)
        if len(parts) != 3:
            errors.append(f"{check_id}: test must be module.Class.method or path::Class.method")
            continue
        module_name, class_name, method_name = parts
        try:
            module = importlib.import_module(module_name)
        except Exception as exc:  # pragma: no cover - error message path
            errors.append(f"{check_id}: cannot import {module_name}: {exc}")
            continue
        test_class = getattr(module, class_name, None)
        if test_class is None:
            errors.append(f"{check_id}: missing test class {class_name}")
            continue
        if getattr(test_class, method_name, None) is None:
            errors.append(f"{check_id}: missing test method {class_name}.{method_name}")
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate the AgentCart AP2-style mandate mapping gate.")
    parser.add_argument("--mapping", type=pathlib.Path, default=DEFAULT_MAPPING)
    parser.add_argument("--verify-test-refs", action="store_true", help="Import-check runtime test references.")
    args = parser.parse_args(argv)

    data = load_json(args.mapping)
    errors = validate_mapping(data)
    if args.verify_test_refs:
        errors.extend(validate_runtime_test_refs(data))
    if errors:
        for error in errors:
            print(f"AP2 mandate mapping check failed: {error}", file=sys.stderr)
        return 1
    print(f"AP2 mandate mapping ok: {args.mapping}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
