#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import pathlib
import sys
from typing import Any


REQUIRED_GATE_IDS = {
    "pilot-merchant-onboarding",
    "pilot-buyer-agent-setup",
    "pilot-payment-mode",
    "pilot-support-channel",
    "pilot-rollback",
    "pilot-safety-privacy",
}

REQUIRED_SUCCESS_METRICS = {
    "checkout_success_rate_min_percent",
    "merchant_setup_time_target_minutes",
    "quote_to_checkout_median_seconds_max",
    "unresolved_p0_incidents_allowed",
    "refund_claims_without_verifier_evidence_allowed",
}


def load_json(path: pathlib.Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"{path}: invalid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise SystemExit(f"{path}: checklist root must be an object")
    return data


def require(condition: bool, message: str, errors: list[str]) -> None:
    if not condition:
        errors.append(message)


def validate_checklist(data: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    require(data.get("schema") == "agentcart.pilot_beta_checklist.v1", "schema must be agentcart.pilot_beta_checklist.v1", errors)
    require(str(data.get("stage") or "") == "external_beta", "stage must be external_beta", errors)

    scope = data.get("minimum_pilot_scope")
    require(isinstance(scope, dict), "minimum_pilot_scope must be an object", errors)
    if isinstance(scope, dict):
        for key in ("merchant_count", "buyer_agent_runtime_count", "successful_checkout_count", "pilot_duration_days"):
            value = scope.get(key)
            require(isinstance(value, int) and value > 0, f"minimum_pilot_scope.{key} must be a positive integer", errors)

    allowed_modes = data.get("payment_modes_allowed")
    blocked_modes = data.get("payment_modes_blocked")
    require(isinstance(allowed_modes, list) and bool(allowed_modes), "payment_modes_allowed must be a non-empty list", errors)
    require(isinstance(blocked_modes, list) and bool(blocked_modes), "payment_modes_blocked must be a non-empty list", errors)
    if isinstance(blocked_modes, list):
        require("public_checkout_with_merchant_token_only" in blocked_modes, "payment_modes_blocked must include public_checkout_with_merchant_token_only", errors)

    gates = data.get("gates")
    require(isinstance(gates, list) and bool(gates), "gates must be a non-empty list", errors)
    seen_gate_ids: set[str] = set()
    if isinstance(gates, list):
        for index, gate in enumerate(gates):
            if not isinstance(gate, dict):
                errors.append(f"gates[{index}] must be an object")
                continue
            gate_id = str(gate.get("id") or "")
            seen_gate_ids.add(gate_id)
            require(gate_id != "", f"gates[{index}].id is required", errors)
            require(gate.get("priority") == "P0", f"{gate_id}: pilot beta gate priority must be P0", errors)
            require(gate.get("blocking") is True, f"{gate_id}: blocking must be true", errors)
            require(str(gate.get("owner") or "") != "", f"{gate_id}: owner is required", errors)
            require(str(gate.get("description") or "") != "", f"{gate_id}: description is required", errors)
            evidence = gate.get("required_evidence")
            criteria = gate.get("exit_criteria")
            require(isinstance(evidence, list) and len(evidence) >= 3, f"{gate_id}: required_evidence must contain at least three entries", errors)
            require(isinstance(criteria, list) and len(criteria) >= 3, f"{gate_id}: exit_criteria must contain at least three entries", errors)
    missing = REQUIRED_GATE_IDS - seen_gate_ids
    require(not missing, f"missing required gate ids: {', '.join(sorted(missing))}", errors)

    metrics = data.get("success_metrics")
    require(isinstance(metrics, dict), "success_metrics must be an object", errors)
    if isinstance(metrics, dict):
        missing_metrics = REQUIRED_SUCCESS_METRICS - set(metrics)
        require(not missing_metrics, f"missing success metrics: {', '.join(sorted(missing_metrics))}", errors)
        require(int(metrics.get("checkout_success_rate_min_percent", 0)) >= 50, "checkout_success_rate_min_percent must be at least 50", errors)
        require(int(metrics.get("unresolved_p0_incidents_allowed", 1)) == 0, "unresolved_p0_incidents_allowed must be 0", errors)
        require(
            int(metrics.get("refund_claims_without_verifier_evidence_allowed", 1)) == 0,
            "refund_claims_without_verifier_evidence_allowed must be 0",
            errors,
        )

    exit_criteria = data.get("pilot_exit_criteria")
    require(isinstance(exit_criteria, list) and len(exit_criteria) >= 4, "pilot_exit_criteria must contain at least four entries", errors)
    if isinstance(exit_criteria, list):
        require("all_p0_gates_have_evidence" in exit_criteria, "pilot_exit_criteria must include all_p0_gates_have_evidence", errors)
    return errors


def validate_evidence(data: dict[str, Any], evidence_dir: pathlib.Path) -> list[str]:
    errors: list[str] = []
    gates = data.get("gates") if isinstance(data.get("gates"), list) else []
    for gate in gates:
        if not isinstance(gate, dict):
            continue
        gate_id = str(gate.get("id") or "")
        evidence = gate.get("required_evidence")
        if not isinstance(evidence, list):
            errors.append(f"{gate_id}: required_evidence must be a list before evidence files can be checked")
            continue
        for evidence_id in evidence:
            evidence_file = evidence_dir / gate_id / f"{evidence_id}.md"
            if not evidence_file.exists():
                errors.append(f"missing evidence file: {evidence_file}")
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate the AgentCart external beta pilot checklist.")
    parser.add_argument(
        "--checklist",
        type=pathlib.Path,
        default=pathlib.Path("gateway/config/pilot_beta_checklist.json"),
        help="Path to the pilot checklist JSON.",
    )
    parser.add_argument(
        "--evidence-dir",
        type=pathlib.Path,
        help="Optional pilot evidence directory. With --require-evidence, each required evidence item must exist as <gate>/<evidence>.md.",
    )
    parser.add_argument("--require-evidence", action="store_true", help="Require all evidence files under --evidence-dir.")
    args = parser.parse_args(argv)

    data = load_json(args.checklist)
    errors = validate_checklist(data)
    if args.require_evidence:
        if args.evidence_dir is None:
            errors.append("--require-evidence requires --evidence-dir")
        else:
            errors.extend(validate_evidence(data, args.evidence_dir))

    if errors:
        for error in errors:
            print(f"pilot readiness check failed: {error}", file=sys.stderr)
        return 1
    print(f"pilot readiness checklist ok: {args.checklist}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
