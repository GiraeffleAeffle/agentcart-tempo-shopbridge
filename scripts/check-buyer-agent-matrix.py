#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import pathlib
import sys
from typing import Any


REQUIRED_CAPABILITIES = {
    "verified_merchant_discovery",
    "catalog_or_quote_fetch",
    "quote_comparison",
    "approval_record",
    "checkout_handoff",
    "aftercare_state",
    "audit_export_or_import",
    "safety_constraints",
}

REQUIRED_RUNTIME_IDS = {
    "agentcart-service-openclaw",
    "shopbridge-direct-skill",
    "generic-mcp-client",
}

REQUIRED_SAFETY_RULES = {
    "opt_in_merchants_only",
    "human_approval_before_checkout",
    "preserve_quote_hash",
    "preserve_payment_contract_hash",
    "treat_merchant_text_as_untrusted",
    "no_real_settlement_without_external_verifier",
}

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
REQUIRED_APPROVAL_AUDIT_HASHES = {
    "quote_hash",
    "payment_contract_hash",
    "approval_hash",
    "approval_record_hash",
    "approval_decision_hash",
    "audit_packet_hash",
    "audit_export_hash",
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


def resolve_repo_path(path_value: str) -> pathlib.Path:
    path = pathlib.Path(path_value)
    return path if path.is_absolute() else REPO_ROOT / path


def validate_fixture_coverage(data: dict[str, Any], seen_runtime_ids: set[str]) -> list[str]:
    errors: list[str] = []
    coverage = data.get("fixture_coverage")
    require(isinstance(coverage, dict), "fixture_coverage must be an object", errors)
    if not isinstance(coverage, dict):
        return errors

    approval_audit = coverage.get("approval_audit_golden")
    require(isinstance(approval_audit, dict), "fixture_coverage.approval_audit_golden must be an object", errors)
    if not isinstance(approval_audit, dict):
        return errors

    require(
        approval_audit.get("hash_contract") == "agentcart.approval_audit_hash_contract.v1",
        "approval_audit_golden.hash_contract must be agentcart.approval_audit_hash_contract.v1",
        errors,
    )
    fixture_path = str(approval_audit.get("fixture") or "")
    require(fixture_path != "", "approval_audit_golden.fixture is required", errors)
    fixture: dict[str, Any] = {}
    if fixture_path:
        path = resolve_repo_path(fixture_path)
        require(path.exists(), f"approval_audit_golden.fixture does not exist: {fixture_path}", errors)
        if path.exists():
            fixture = load_json(path)
            require(
                fixture.get("schema") == "agentcart.approval_audit_golden_fixtures.v1",
                "approval_audit_golden.fixture schema must be agentcart.approval_audit_golden_fixtures.v1",
                errors,
            )
            require(
                fixture.get("hash_contract") == approval_audit.get("hash_contract"),
                "approval_audit_golden.fixture hash_contract must match matrix coverage",
                errors,
            )

    required_runtimes = approval_audit.get("required_runtimes")
    require(isinstance(required_runtimes, list) and bool(required_runtimes), "approval_audit_golden.required_runtimes must be a non-empty list", errors)
    if isinstance(required_runtimes, list):
        missing_runtimes = set(required_runtimes) - seen_runtime_ids
        require(not missing_runtimes, f"approval_audit_golden references missing runtimes: {', '.join(sorted(missing_runtimes))}", errors)
        missing_required_runtimes = REQUIRED_RUNTIME_IDS - set(required_runtimes)
        require(
            not missing_required_runtimes,
            f"approval_audit_golden.required_runtimes must include: {', '.join(sorted(missing_required_runtimes))}",
            errors,
        )

    required_hashes = approval_audit.get("required_hashes")
    require(isinstance(required_hashes, list) and bool(required_hashes), "approval_audit_golden.required_hashes must be a non-empty list", errors)
    if isinstance(required_hashes, list):
        missing_hashes = REQUIRED_APPROVAL_AUDIT_HASHES - set(required_hashes)
        require(not missing_hashes, f"approval_audit_golden.required_hashes missing: {', '.join(sorted(missing_hashes))}", errors)
        fixture_hashes = set(fixture.get("generic_mcp_required_hashes", [])) if isinstance(fixture.get("generic_mcp_required_hashes"), list) else set()
        require(
            REQUIRED_APPROVAL_AUDIT_HASHES.issubset(fixture_hashes),
            "approval_audit_golden.fixture generic_mcp_required_hashes must include required hashes",
            errors,
        )
    return errors


def validate_matrix(data: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    require(data.get("schema") == "agentcart.buyer_agent_test_matrix.v1", "schema must be agentcart.buyer_agent_test_matrix.v1", errors)
    require(data.get("stage") == "external_beta", "stage must be external_beta", errors)

    minimum_runtime_count = data.get("minimum_runtime_count")
    require(isinstance(minimum_runtime_count, int) and minimum_runtime_count >= 3, "minimum_runtime_count must be at least 3", errors)

    required_capabilities = data.get("required_capabilities")
    require(isinstance(required_capabilities, list), "required_capabilities must be a list", errors)
    if isinstance(required_capabilities, list):
        missing_capabilities = REQUIRED_CAPABILITIES - set(required_capabilities)
        require(not missing_capabilities, f"missing required capabilities: {', '.join(sorted(missing_capabilities))}", errors)

    safety_rules = data.get("required_safety_rules")
    require(isinstance(safety_rules, list), "required_safety_rules must be a list", errors)
    if isinstance(safety_rules, list):
        missing_safety = REQUIRED_SAFETY_RULES - set(safety_rules)
        require(not missing_safety, f"missing required safety rules: {', '.join(sorted(missing_safety))}", errors)

    runtimes = data.get("runtimes")
    require(isinstance(runtimes, list) and len(runtimes) >= 3, "runtimes must contain at least three entries", errors)
    seen_runtime_ids: set[str] = set()
    if isinstance(runtimes, list):
        for index, runtime in enumerate(runtimes):
            if not isinstance(runtime, dict):
                errors.append(f"runtimes[{index}] must be an object")
                continue
            runtime_id = str(runtime.get("id") or "")
            seen_runtime_ids.add(runtime_id)
            require(runtime_id != "", f"runtimes[{index}].id is required", errors)
            require(str(runtime.get("name") or "") != "", f"{runtime_id}: name is required", errors)
            require(
                runtime.get("integration_mode") in {"service", "skill_only", "mcp_tools"},
                f"{runtime_id}: integration_mode must be service, skill_only, or mcp_tools",
                errors,
            )
            require(str(runtime.get("status") or "") in {"alpha", "documented_alpha", "beta"}, f"{runtime_id}: invalid status", errors)
            for field in ("setup_docs", "entrypoints", "commands_or_tools", "required_evidence"):
                value = runtime.get(field)
                require(isinstance(value, list) and bool(value), f"{runtime_id}: {field} must be a non-empty list", errors)
            capabilities = runtime.get("capabilities")
            require(isinstance(capabilities, dict), f"{runtime_id}: capabilities must be an object", errors)
            if isinstance(capabilities, dict):
                missing_runtime_capabilities = REQUIRED_CAPABILITIES - set(capabilities)
                require(
                    not missing_runtime_capabilities,
                    f"{runtime_id}: missing capabilities: {', '.join(sorted(missing_runtime_capabilities))}",
                    errors,
                )
                for capability_id, description in capabilities.items():
                    require(str(description or "") != "", f"{runtime_id}: capability {capability_id} must describe the runtime behavior", errors)
            required_evidence = runtime.get("required_evidence")
            if isinstance(required_evidence, list):
                require(len(required_evidence) >= 5, f"{runtime_id}: required_evidence must contain at least five entries", errors)

    missing_runtimes = REQUIRED_RUNTIME_IDS - seen_runtime_ids
    require(not missing_runtimes, f"missing required runtimes: {', '.join(sorted(missing_runtimes))}", errors)
    errors.extend(validate_fixture_coverage(data, seen_runtime_ids))

    exit_criteria = data.get("pilot_exit_criteria")
    require(isinstance(exit_criteria, list) and len(exit_criteria) >= 4, "pilot_exit_criteria must contain at least four entries", errors)
    if isinstance(exit_criteria, list):
        require(
            "at_least_three_runtimes_have_required_capabilities" in exit_criteria,
            "pilot_exit_criteria must include at_least_three_runtimes_have_required_capabilities",
            errors,
        )
    return errors


def validate_evidence(data: dict[str, Any], evidence_dir: pathlib.Path) -> list[str]:
    errors: list[str] = []
    runtimes = data.get("runtimes") if isinstance(data.get("runtimes"), list) else []
    for runtime in runtimes:
        if not isinstance(runtime, dict):
            continue
        runtime_id = str(runtime.get("id") or "")
        evidence = runtime.get("required_evidence")
        if not isinstance(evidence, list):
            errors.append(f"{runtime_id}: required_evidence must be a list before evidence files can be checked")
            continue
        for evidence_id in evidence:
            evidence_file = evidence_dir / runtime_id / f"{evidence_id}.md"
            if not evidence_file.exists():
                errors.append(f"missing evidence file: {evidence_file}")
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate the AgentCart buyer-agent test matrix.")
    parser.add_argument(
        "--matrix",
        type=pathlib.Path,
        default=pathlib.Path("gateway/config/buyer_agent_test_matrix.json"),
        help="Path to the buyer-agent test matrix JSON.",
    )
    parser.add_argument(
        "--evidence-dir",
        type=pathlib.Path,
        help="Optional evidence directory. With --require-evidence, each required evidence item must exist as <runtime>/<evidence>.md.",
    )
    parser.add_argument("--require-evidence", action="store_true", help="Require all evidence files under --evidence-dir.")
    args = parser.parse_args(argv)

    data = load_json(args.matrix)
    errors = validate_matrix(data)
    if args.require_evidence:
        if args.evidence_dir is None:
            errors.append("--require-evidence requires --evidence-dir")
        else:
            errors.extend(validate_evidence(data, args.evidence_dir))

    if errors:
        for error in errors:
            print(f"buyer-agent matrix check failed: {error}", file=sys.stderr)
        return 1
    print(f"buyer-agent matrix ok: {args.matrix}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
