#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import pathlib
from datetime import datetime, timezone
from typing import Any


ROOT = pathlib.Path(__file__).resolve().parents[1]


EVIDENCE_REFERENCES = (
    (
        "Verifier operations",
        (
            "verifier_health_or_fixture_result",
            "verifier_metrics_snapshot",
            "sqlite_replay_backup_restore_drill",
            "verifier_alert_delivery_result",
            "provider_error_review",
            "production_payment_profile_check_result",
            "sample_payment_contract_hash",
        ),
    ),
    (
        "WooCommerce variance",
        (
            "woocommerce_compatibility_matrix_result",
            "woocommerce_baseline_eu_tax_shipping_result",
            "woocommerce_restricted_stock_policy_result",
        ),
    ),
    (
        "Merchant walkthrough",
        ("non_maintainer_setup_walkthrough_notes",),
    ),
)


def utcnow() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def rel(path: pathlib.Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT))
    except ValueError:
        return str(path)


def load_report(path: pathlib.Path) -> dict[str, Any]:
    report = json.loads(path.read_text(encoding="utf-8"))
    if report.get("schema") != "agentcart.pilot_evidence_runner.v1":
        raise ValueError("report schema must be agentcart.pilot_evidence_runner.v1")
    if not isinstance(report.get("gates"), list):
        raise ValueError("report must contain gates")
    return report


def parse_repeated(values: list[str]) -> list[str]:
    return [value.strip() for value in values if value.strip()]


def gate_summary(report: dict[str, Any], status: str) -> list[dict[str, Any]]:
    return [gate for gate in report.get("gates", []) if gate.get("status") == status]


def evidence_paths_by_id(report: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    found: dict[str, list[dict[str, Any]]] = {}
    seen: set[tuple[str, str]] = set()

    def add_ref(evidence_id: str, item: dict[str, Any]) -> None:
        path = str(item.get("path_hint") or item.get("path") or "")
        key = (evidence_id, path)
        if key in seen:
            return
        seen.add(key)
        found.setdefault(evidence_id, []).append(item)

    for gate in report.get("gates", []):
        for item in gate.get("evidence", []):
            if not isinstance(item, dict):
                continue
            evidence_id = str(item.get("evidence_id") or "")
            add_ref(evidence_id, item)
        for item in gate.get("missing_evidence", []):
            if not isinstance(item, dict):
                continue
            evidence_id = str(item.get("evidence_id") or "")
            add_ref(evidence_id, item)
        for error in gate.get("errors", []):
            if not isinstance(error, str) or " -> " not in error:
                continue
            left, path = error.rsplit(" -> ", 1)
            evidence_id = left.rsplit(": ", 1)[-1].strip()
            add_ref(
                evidence_id,
                {
                    "evidence_id": evidence_id,
                    "path_hint": path,
                    "exists": False,
                    "scope": str(gate.get("id") or ""),
                    "owner_id": "",
                },
            )
    return found


def missing_follow_up_errors(report: dict[str, Any], follow_up_issues: list[str]) -> list[str]:
    failed_gates = gate_summary(report, "failed")
    if not failed_gates:
        return []
    if follow_up_issues:
        return []
    return ["no-go decisions with failed gates should list follow-up issue URLs or accepted blocker owners"]


def validate_inputs(args: argparse.Namespace, report: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    decision = args.decision
    if decision == "go" and report.get("status") != "passed":
        errors.append("go decision requires a passed pilot evidence report")
    if decision == "go":
        required_go_fields = {
            "--beta-scope": args.beta_scope,
            "--rollback-owner": args.rollback_owner,
            "--support-channel": args.support_channel,
            "--observation-window": args.observation_window,
        }
        for name, value in required_go_fields.items():
            if not str(value or "").strip():
                errors.append(f"go decision requires {name}")
    if decision == "no-go":
        errors.extend(missing_follow_up_errors(report, parse_repeated(args.follow_up_issue)))
    return errors


def bullet_list(items: list[str], fallback: str = "_None recorded._") -> str:
    if not items:
        return fallback
    return "\n".join(f"- {item}" for item in items)


def gate_table(gates: list[dict[str, Any]]) -> str:
    if not gates:
        return "| Gate | Status | Missing evidence | Errors |\n| --- | --- | ---: | --- |\n"
    lines = ["| Gate | Status | Missing evidence | Errors |", "| --- | --- | ---: | --- |"]
    for gate in gates:
        errors = gate.get("errors", [])
        error_summary = "; ".join(str(error) for error in errors[:3])
        if len(errors) > 3:
            error_summary += f"; ... +{len(errors) - 3} more"
        lines.append(
            "| {id} | {status} | {missing} | {errors} |".format(
                id=gate.get("id", ""),
                status=gate.get("status", ""),
                missing=gate.get("evidence_summary", {}).get("missing", 0),
                errors=error_summary.replace("|", "\\|") or "-",
            )
        )
    return "\n".join(lines)


def evidence_reference_section(report: dict[str, Any]) -> str:
    paths = evidence_paths_by_id(report)
    lines = ["## Required Evidence References", ""]
    for label, evidence_ids in EVIDENCE_REFERENCES:
        lines.append(f"### {label}")
        for evidence_id in evidence_ids:
            refs = paths.get(evidence_id, [])
            if not refs:
                lines.append(f"- `{evidence_id}`: not found in report")
                continue
            for ref in refs:
                exists = "present" if ref.get("exists") else "missing"
                path = ref.get("path_hint") or ref.get("path") or ""
                lines.append(f"- `{evidence_id}`: {exists} at `{path}`")
        lines.append("")
    return "\n".join(lines).rstrip()


def render_decision(args: argparse.Namespace, report: dict[str, Any], report_path: pathlib.Path) -> str:
    release_decision = report.get("release_decision", {})
    passed_gates = gate_summary(report, "passed")
    failed_gates = [gate for gate in report.get("gates", []) if gate.get("status") != "passed"]
    accepted_risks = parse_repeated(args.accepted_risk)
    follow_up_issues = parse_repeated(args.follow_up_issue)
    blockers = [
        f"{gate.get('id')}: {len(gate.get('errors', []))} error(s), "
        f"{gate.get('evidence_summary', {}).get('missing', 0)} missing evidence item(s)"
        for gate in failed_gates
    ]

    lines = [
        "# External Beta Go/No-Go Decision",
        "",
        f"- Decision: **{args.decision.upper()}**",
        f"- Generated at: `{utcnow()}`",
        f"- Operator: {args.operator or 'TODO'}",
        f"- Evidence report: `{rel(report_path)}`",
        f"- Report status: `{report.get('status')}`",
        f"- Report generated at: `{report.get('generated_at', '')}`",
        f"- Missing evidence count: `{release_decision.get('missing_evidence_count', 0)}`",
        f"- Blocking gate count: `{release_decision.get('blocking_gate_count', 0)}`",
        "",
        "## Beta Scope",
        "",
        args.beta_scope or "_Required for GO. For NO-GO, describe the intended scope before retry._",
        "",
        "## Operational Commitments",
        "",
        f"- Rollback owner: {args.rollback_owner or 'TODO'}",
        f"- Support channel: {args.support_channel or 'TODO'}",
        f"- Observation window: {args.observation_window or 'TODO'}",
        "",
        "## Passed Gates",
        "",
        gate_table(passed_gates),
        "",
        "## Failed Gates",
        "",
        gate_table(failed_gates),
        "",
        "## Blockers",
        "",
        bullet_list(blockers),
        "",
        "## Accepted Risks",
        "",
        bullet_list(accepted_risks),
        "",
        "## Follow-Up Issues",
        "",
        bullet_list(follow_up_issues, "_None recorded. Required for NO-GO blockers._"),
        "",
        evidence_reference_section(report),
        "",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build a supervised external beta go/no-go decision record from a pilot evidence report."
    )
    parser.add_argument("--report", required=True, type=pathlib.Path, help="pilot-evidence-report.json from collect-pilot-evidence.py.")
    parser.add_argument("--decision", required=True, choices=("go", "no-go"), help="Operator decision.")
    parser.add_argument("--operator", default="", help="Named operator making or recording the decision.")
    parser.add_argument("--beta-scope", default="", help="Exact external beta scope.")
    parser.add_argument("--rollback-owner", default="", help="Named rollback owner.")
    parser.add_argument("--support-channel", default="", help="Monitored pilot support channel.")
    parser.add_argument("--observation-window", default="", help="Observation window for the beta decision.")
    parser.add_argument("--accepted-risk", action="append", default=[], help="Accepted risk statement. Repeat as needed.")
    parser.add_argument("--follow-up-issue", action="append", default=[], help="Follow-up issue URL or blocker owner. Repeat as needed.")
    parser.add_argument("--out", type=pathlib.Path, help="Write markdown decision record to this path.")
    args = parser.parse_args(argv)

    try:
        report = load_report(args.report)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"beta release decision failed: {exc}")
        return 1

    errors = validate_inputs(args, report)
    if errors:
        for error in errors:
            print(f"beta release decision failed: {error}")
        return 1

    rendered = render_decision(args, report, args.report)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
