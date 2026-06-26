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
DEFAULT_PROFILES = REPO_ROOT / "gateway" / "config" / "ucp_a2a_profiles.json"

REQUIRED_BOUNDARIES = {
    "no_native_ucp_transport_claim",
    "no_native_a2a_json_rpc_claim",
    "human_approval_required",
    "quote_hash_preserved",
    "merchant_text_untrusted",
    "merchant_of_record_preserved",
    "payment_verifier_required_for_real_settlement",
}

REQUIRED_PROFILE_IDS = {
    "ucp-checkout-mapping",
    "a2a-handoff-profile",
}

REQUIRED_RUNTIME_CHECKS = {
    "service-standards-profile-served",
    "service-capability-links-standards-profile",
    "profile-config-contract",
}


def load_json(path: pathlib.Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"{path}: invalid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise SystemExit(f"{path}: profile root must be an object")
    return data


def require(condition: bool, message: str, errors: list[str]) -> None:
    if not condition:
        errors.append(message)


def repo_path(path_value: str) -> pathlib.Path:
    path = pathlib.Path(path_value)
    return path if path.is_absolute() else REPO_ROOT / path


def validate_concept_entries(profile_id: str, entries: Any, *, key: str, errors: list[str]) -> None:
    require(isinstance(entries, list) and bool(entries), f"{profile_id}: {key} must be a non-empty list", errors)
    if not isinstance(entries, list):
        return
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            errors.append(f"{profile_id}: {key}[{index}] must be an object")
            continue
        require(str(entry.get("source") or "") != "", f"{profile_id}: {key}[{index}].source is required", errors)
        require(str(entry.get("agentcart") or "") != "", f"{profile_id}: {key}[{index}].agentcart is required", errors)
        endpoints = entry.get("endpoints")
        require(isinstance(endpoints, list) and bool(endpoints), f"{profile_id}: {key}[{index}].endpoints must be non-empty", errors)


def validate_profiles(data: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    require(data.get("schema") == "agentcart.ucp_a2a_profiles.v1", "schema must be agentcart.ucp_a2a_profiles.v1", errors)
    require(data.get("stage") == "external_beta", "stage must be external_beta", errors)
    require(data.get("gate_id") == "STD-003", "gate_id must be STD-003", errors)
    require(data.get("status") == "implemented_alpha", "status must be implemented_alpha", errors)
    require(
        data.get("compliance_claim") == "mapping_profiles_not_native_ucp_or_a2a",
        "compliance_claim must be mapping_profiles_not_native_ucp_or_a2a",
        errors,
    )

    documents = data.get("published_documents")
    require(isinstance(documents, list) and bool(documents), "published_documents must be a non-empty list", errors)
    if isinstance(documents, list):
        urls = {
            url
            for document in documents
            if isinstance(document, dict)
            for url in document.get("urls", [])
            if isinstance(url, str)
        }
        require("/.well-known/agentcart-standards.json" in urls, "published_documents must include /.well-known/agentcart-standards.json", errors)
        require("/v1/standards/profiles" in urls, "published_documents must include /v1/standards/profiles", errors)

    boundaries = data.get("required_boundaries")
    require(isinstance(boundaries, list), "required_boundaries must be a list", errors)
    if isinstance(boundaries, list):
        missing_boundaries = REQUIRED_BOUNDARIES - set(boundaries)
        require(not missing_boundaries, f"missing required boundaries: {', '.join(sorted(missing_boundaries))}", errors)

    profiles = data.get("profiles")
    require(isinstance(profiles, list), "profiles must be a list", errors)
    seen_profile_ids: set[str] = set()
    if isinstance(profiles, list):
        for index, profile in enumerate(profiles):
            if not isinstance(profile, dict):
                errors.append(f"profiles[{index}] must be an object")
                continue
            profile_id = str(profile.get("id") or "")
            seen_profile_ids.add(profile_id)
            require(profile_id != "", f"profiles[{index}].id is required", errors)
            require(profile.get("status") == "mapping_alpha", f"{profile_id}: status must be mapping_alpha", errors)
            require(profile.get("native_transport_supported") is False, f"{profile_id}: native_transport_supported must be false until implemented", errors)
            require(str(profile.get("claim") or "") != "", f"{profile_id}: claim is required", errors)
            if profile_id == "ucp-checkout-mapping":
                require(profile.get("source_standard") == "UCP", "ucp-checkout-mapping: source_standard must be UCP", errors)
                validate_concept_entries(profile_id, profile.get("concept_map"), key="concept_map", errors=errors)
            if profile_id == "a2a-handoff-profile":
                require(profile.get("source_standard") == "A2A", "a2a-handoff-profile: source_standard must be A2A", errors)
                require(profile.get("native_agent_card_published") is False, "a2a-handoff-profile: native_agent_card_published must be false until implemented", errors)
                validate_concept_entries(profile_id, profile.get("skill_map"), key="skill_map", errors=errors)
    missing_profiles = REQUIRED_PROFILE_IDS - seen_profile_ids
    require(not missing_profiles, f"missing profiles: {', '.join(sorted(missing_profiles))}", errors)

    runtime_checks = data.get("runtime_checks")
    require(isinstance(runtime_checks, list), "runtime_checks must be a list", errors)
    seen_checks: set[str] = set()
    if isinstance(runtime_checks, list):
        for index, check in enumerate(runtime_checks):
            if not isinstance(check, dict):
                errors.append(f"runtime_checks[{index}] must be an object")
                continue
            check_id = str(check.get("id") or "")
            seen_checks.add(check_id)
            require(check_id != "", f"runtime_checks[{index}].id is required", errors)
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
            module_name = f"_agentcart_ucp_a2a_profiles_{test_file.stem}_{index}"
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
    parser = argparse.ArgumentParser(description="Validate the AgentCart UCP/A2A profile mapping gate.")
    parser.add_argument("--profiles", type=pathlib.Path, default=DEFAULT_PROFILES)
    parser.add_argument("--verify-test-refs", action="store_true", help="Import-check runtime test references.")
    args = parser.parse_args(argv)

    data = load_json(args.profiles)
    errors = validate_profiles(data)
    if args.verify_test_refs:
        errors.extend(validate_runtime_test_refs(data))
    if errors:
        for error in errors:
            print(f"UCP/A2A profile check failed: {error}", file=sys.stderr)
        return 1
    print(f"UCP/A2A profiles ok: {args.profiles}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
