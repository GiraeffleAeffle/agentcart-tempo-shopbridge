#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib
import importlib.util
import json
import pathlib
import sys
from typing import Any


REQUIRED_CONTROLS = {
    "merchant_text_untrusted",
    "instructions_allowed_false",
    "human_approval_required",
    "no_checkout_from_text",
    "quote_hash_preserved",
    "payment_contract_hash_preserved",
}

REQUIRED_SURFACES = {
    "product_title",
    "product_description",
    "merchant_name",
    "registry_profile",
    "delivery_note",
    "refund_policy",
}

INJECTION_MARKERS = {
    "ignore",
    "system:",
    "approved",
    "skip",
    "refund",
    "verifier",
    "checkout",
}

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]


def load_json(path: pathlib.Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"{path}: invalid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise SystemExit(f"{path}: corpus root must be an object")
    return data


def require(condition: bool, message: str, errors: list[str]) -> None:
    if not condition:
        errors.append(message)


def validate_corpus(data: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    require(data.get("schema") == "agentcart.prompt_injection_corpus.v1", "schema must be agentcart.prompt_injection_corpus.v1", errors)
    require(data.get("stage") == "external_beta", "stage must be external_beta", errors)

    controls = data.get("required_controls")
    require(isinstance(controls, list), "required_controls must be a list", errors)
    if isinstance(controls, list):
        missing_controls = REQUIRED_CONTROLS - set(controls)
        require(not missing_controls, f"missing required controls: {', '.join(sorted(missing_controls))}", errors)

    cases = data.get("cases")
    require(isinstance(cases, list) and len(cases) >= len(REQUIRED_SURFACES), "cases must cover every required surface", errors)
    seen_surfaces: set[str] = set()
    seen_ids: set[str] = set()
    if isinstance(cases, list):
        for index, case in enumerate(cases):
            if not isinstance(case, dict):
                errors.append(f"cases[{index}] must be an object")
                continue
            case_id = str(case.get("id") or "")
            surface = str(case.get("surface") or "")
            payload = str(case.get("payload") or "")
            expected_controls = case.get("expected_controls")
            require(case_id != "", f"cases[{index}].id is required", errors)
            require(case_id not in seen_ids, f"duplicate case id: {case_id}", errors)
            seen_ids.add(case_id)
            require(surface in REQUIRED_SURFACES, f"{case_id}: surface must be one of {', '.join(sorted(REQUIRED_SURFACES))}", errors)
            seen_surfaces.add(surface)
            require(len(payload) >= 20, f"{case_id}: payload must be at least 20 characters", errors)
            lower_payload = payload.lower()
            require(
                any(marker in lower_payload for marker in INJECTION_MARKERS),
                f"{case_id}: payload should contain a recognizable injection marker",
                errors,
            )
            require(isinstance(expected_controls, list) and len(expected_controls) >= 3, f"{case_id}: expected_controls must contain at least three entries", errors)
            if isinstance(expected_controls, list):
                unknown_controls = set(expected_controls) - REQUIRED_CONTROLS
                require(not unknown_controls, f"{case_id}: unknown expected controls: {', '.join(sorted(unknown_controls))}", errors)
                require("merchant_text_untrusted" in expected_controls, f"{case_id}: expected_controls must include merchant_text_untrusted", errors)
                require("instructions_allowed_false" in expected_controls, f"{case_id}: expected_controls must include instructions_allowed_false", errors)
    missing_surfaces = REQUIRED_SURFACES - seen_surfaces
    require(not missing_surfaces, f"missing required surfaces: {', '.join(sorted(missing_surfaces))}", errors)

    runtime_checks = data.get("runtime_checks")
    require(isinstance(runtime_checks, list) and len(runtime_checks) >= 2, "runtime_checks must contain at least two entries", errors)
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
            module_name = f"_agentcart_prompt_corpus_{test_file.stem}_{index}"
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
    parser = argparse.ArgumentParser(description="Validate the AgentCart prompt-injection corpus.")
    parser.add_argument(
        "--corpus",
        type=pathlib.Path,
        default=pathlib.Path("gateway/config/prompt_injection_corpus.json"),
        help="Path to the prompt-injection corpus JSON.",
    )
    parser.add_argument("--verify-test-refs", action="store_true", help="Import-check runtime test references.")
    args = parser.parse_args(argv)
    data = load_json(args.corpus)
    errors = validate_corpus(data)
    if args.verify_test_refs:
        errors.extend(validate_runtime_test_refs(data))
    if errors:
        for error in errors:
            print(f"prompt-injection corpus check failed: {error}", file=sys.stderr)
        return 1
    print(f"prompt-injection corpus ok: {args.corpus}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
