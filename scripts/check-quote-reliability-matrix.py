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
DEFAULT_MATRIX = REPO_ROOT / "gateway" / "config" / "quote_reliability_matrix.json"

REQUIRED_INVARIANTS = {
    "quote_hash_preserved",
    "payment_contract_hash_preserved",
    "idempotency_key_required",
    "idempotent_replay_returns_existing_order",
    "quote_lock_before_order_creation",
    "single_use_merchant_quote",
    "stock_revalidated_before_order_creation",
    "money_fields_revalidated_before_payment_verification",
    "machine_readable_recovery_hints",
}

REQUIRED_CASES = {
    "expired-quote-recovery",
    "stock-conflict-recovery",
    "price-drift-recovery",
    "shipping-drift-recovery",
    "tax-drift-recovery",
    "idempotent-checkout-replay",
    "merchant-quote-single-use",
}

REQUIRED_RECOVERY_REASONS = {
    "quote_expired",
    "stock_changed",
    "price_changed",
    "shipping_changed",
    "tax_changed",
}


def load_json(path: pathlib.Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"{path}: invalid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise SystemExit(f"{path}: matrix root must be an object")
    return data


def require(condition: bool, message: str, errors: list[str]) -> None:
    if not condition:
        errors.append(message)


def validate_matrix(data: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    require(data.get("schema") == "agentcart.quote_reliability_matrix.v1", "schema must be agentcart.quote_reliability_matrix.v1", errors)
    require(data.get("stage") == "external_beta", "stage must be external_beta", errors)

    invariants = data.get("required_invariants")
    require(isinstance(invariants, list), "required_invariants must be a list", errors)
    if isinstance(invariants, list):
        missing_invariants = REQUIRED_INVARIANTS - set(invariants)
        require(not missing_invariants, f"missing required invariants: {', '.join(sorted(missing_invariants))}", errors)

    cases = data.get("cases")
    require(isinstance(cases, list) and len(cases) >= len(REQUIRED_CASES), "cases must cover every required reliability case", errors)
    seen_case_ids: set[str] = set()
    seen_recovery_reasons: set[str] = set()
    if isinstance(cases, list):
        for index, case in enumerate(cases):
            if not isinstance(case, dict):
                errors.append(f"cases[{index}] must be an object")
                continue
            case_id = str(case.get("id") or "")
            require(case_id != "", f"cases[{index}].id is required", errors)
            require(case_id not in seen_case_ids, f"duplicate case id: {case_id}", errors)
            seen_case_ids.add(case_id)
            require(str(case.get("priority") or "") in {"P0", "P1", "P2"}, f"{case_id}: priority must be P0, P1, or P2", errors)
            require(str(case.get("trigger") or "") != "", f"{case_id}: trigger is required", errors)
            require(str(case.get("agent_action") or "") != "", f"{case_id}: agent_action is required", errors)
            recovery_reason = str(case.get("recovery_reason") or "")
            expected_error = str(case.get("expected_error") or "")
            if recovery_reason:
                seen_recovery_reasons.add(recovery_reason)
                require(expected_error != "", f"{case_id}: expected_error is required when recovery_reason is set", errors)
    missing_cases = REQUIRED_CASES - seen_case_ids
    require(not missing_cases, f"missing required cases: {', '.join(sorted(missing_cases))}", errors)
    missing_reasons = REQUIRED_RECOVERY_REASONS - seen_recovery_reasons
    require(not missing_reasons, f"missing required recovery reasons: {', '.join(sorted(missing_reasons))}", errors)

    runtime_checks = data.get("runtime_checks")
    require(isinstance(runtime_checks, list) and len(runtime_checks) >= 3, "runtime_checks must contain at least three entries", errors)
    if isinstance(runtime_checks, list):
        for index, check in enumerate(runtime_checks):
            if not isinstance(check, dict):
                errors.append(f"runtime_checks[{index}] must be an object")
                continue
            check_id = str(check.get("id") or "")
            require(check_id != "", f"runtime_checks[{index}].id is required", errors)
            require(str(check.get("target") or "") != "", f"{check_id}: target is required", errors)
            require(str(check.get("test") or "") != "", f"{check_id}: test is required", errors)
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
            test_file = pathlib.Path(file_ref)
            if not test_file.exists() and not test_file.is_absolute():
                test_file = REPO_ROOT / test_file
            if not test_file.exists():
                errors.append(f"{check_id}: missing test file {test_file}")
                continue
            module_name = f"_agentcart_quote_reliability_{test_file.stem}_{index}"
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
    parser = argparse.ArgumentParser(description="Validate the AgentCart quote reliability matrix.")
    parser.add_argument("--matrix", type=pathlib.Path, default=DEFAULT_MATRIX)
    parser.add_argument("--verify-test-refs", action="store_true", help="Import-check runtime test references.")
    args = parser.parse_args(argv)

    data = load_json(args.matrix)
    errors = validate_matrix(data)
    if args.verify_test_refs:
        errors.extend(validate_runtime_test_refs(data))
    if errors:
        for error in errors:
            print(f"quote reliability matrix check failed: {error}", file=sys.stderr)
        return 1
    print(f"quote reliability matrix ok: {args.matrix}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
