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
