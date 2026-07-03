#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.util
import json
import pathlib
import sys
from datetime import datetime, timezone
from types import ModuleType
from typing import Any


ROOT = pathlib.Path(__file__).resolve().parents[1]


def load_tool(name: str, path: pathlib.Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"unable to load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


pilot_tool = load_tool("agentcart_pilot_readiness_tool", ROOT / "scripts" / "check-pilot-readiness.py")
buyer_matrix_tool = load_tool("agentcart_buyer_agent_matrix_tool", ROOT / "scripts" / "check-buyer-agent-matrix.py")
payment_profile_tool = load_tool(
    "agentcart_production_payment_profile_tool",
    ROOT / "scripts" / "check-production-payment-profile.py",
)
woocommerce_tool = load_tool(
    "agentcart_woocommerce_compatibility_tool",
    ROOT / "scripts" / "check-woocommerce-compatibility-matrix.py",
)


def utcnow() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def rel(path: pathlib.Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT))
    except ValueError:
        return str(path)


def evidence_item(scope: str, owner_id: str, evidence_id: str, path: pathlib.Path, exists: bool) -> dict[str, Any]:
    return {
        "scope": scope,
        "owner_id": owner_id,
        "evidence_id": evidence_id,
        "path": str(path),
        "path_hint": rel(path),
        "exists": exists,
    }


def pilot_evidence_items(checklist: dict[str, Any], evidence_dir: pathlib.Path) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for gate in checklist.get("gates", []):
        if not isinstance(gate, dict):
            continue
        gate_id = str(gate.get("id") or "")
        required_evidence = gate.get("required_evidence")
        if not isinstance(required_evidence, list):
            continue
        for evidence_id in required_evidence:
            evidence_name = str(evidence_id)
            path = evidence_dir / gate_id / f"{evidence_name}.md"
            items.append(evidence_item("pilot_gate", gate_id, evidence_name, path, path.exists()))
    return items


def buyer_evidence_items(matrix: dict[str, Any], evidence_dir: pathlib.Path) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for runtime in matrix.get("runtimes", []):
        if not isinstance(runtime, dict):
            continue
        runtime_id = str(runtime.get("id") or "")
        required_evidence = runtime.get("required_evidence")
        if not isinstance(required_evidence, list):
            continue
        for evidence_id in required_evidence:
            evidence_name = str(evidence_id)
            path = evidence_dir / runtime_id / f"{evidence_name}.md"
            items.append(evidence_item("buyer_agent_runtime", runtime_id, evidence_name, path, path.exists()))
    return items


def summarize_items(items: list[dict[str, Any]]) -> dict[str, int]:
    missing = [item for item in items if not item["exists"]]
    return {
        "required": len(items),
        "present": len(items) - len(missing),
        "missing": len(missing),
    }


def result(
    gate_id: str,
    label: str,
    command: str,
    errors: list[str],
    *,
    evidence: list[dict[str, Any]] | None = None,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    missing = [item for item in evidence or [] if not item["exists"]]
    actionable_errors = list(errors)
    actionable_errors.extend(
        f"missing evidence for {item['scope']} {item['owner_id']}: {item['evidence_id']} -> {item['path']}"
        for item in missing
    )
    return {
        "id": gate_id,
        "label": label,
        "status": "passed" if not actionable_errors else "failed",
        "command": command,
        "errors": actionable_errors,
        "missing_evidence": missing,
        "evidence_summary": summarize_items(evidence or []),
        "details": details or {},
    }


def validate_pilot(args: argparse.Namespace) -> dict[str, Any]:
    checklist = pilot_tool.load_json(args.checklist)
    errors = pilot_tool.validate_checklist(checklist)
    if not args.pilot_evidence_dir.exists():
        errors.append(f"pilot evidence directory does not exist: {args.pilot_evidence_dir}")
    evidence = pilot_evidence_items(checklist, args.pilot_evidence_dir)
    return result(
        "pilot-readiness",
        "Pilot P0 checklist evidence",
        (
            f"python3 scripts/check-pilot-readiness.py --checklist {rel(args.checklist)} "
            f"--evidence-dir {args.pilot_evidence_dir} --require-evidence"
        ),
        errors,
        evidence=evidence,
        details={"checklist": rel(args.checklist), "stage": checklist.get("stage")},
    )


def validate_buyer_agents(args: argparse.Namespace) -> dict[str, Any]:
    matrix = buyer_matrix_tool.load_json(args.buyer_agent_matrix)
    errors = buyer_matrix_tool.validate_matrix(matrix)
    if not args.buyer_agent_evidence_dir.exists():
        errors.append(f"buyer-agent evidence directory does not exist: {args.buyer_agent_evidence_dir}")
    evidence = buyer_evidence_items(matrix, args.buyer_agent_evidence_dir)
    return result(
        "buyer-agent-runtime-evidence",
        "Buyer-agent runtime evidence",
        (
            f"python3 scripts/check-buyer-agent-matrix.py --matrix {rel(args.buyer_agent_matrix)} "
            f"--evidence-dir {args.buyer_agent_evidence_dir} --require-evidence"
        ),
        errors,
        evidence=evidence,
        details={"matrix": rel(args.buyer_agent_matrix), "stage": matrix.get("stage")},
    )


def validate_payment_profile(args: argparse.Namespace) -> dict[str, Any]:
    errors: list[str] = []
    details: dict[str, Any] = {"env_files": [rel(path) for path in args.payment_env_file]}
    try:
        values = payment_profile_tool.parse_env_files(args.payment_env_file)
    except ValueError as exc:
        errors.append(str(exc))
        values = {}
    if values:
        errors.extend(
            payment_profile_tool.validate_profile(
                values,
                allow_placeholders=args.allow_payment_placeholders,
            )
        )
        details["checkout_mode"] = values.get("AGENTCART_CHECKOUT_MODE", "")
        details["replay_store_driver"] = values.get("AGENTCART_VERIFIER_REPLAY_STORE_DRIVER", "")
        details["woocommerce_mode"] = values.get("WOOCOMMERCE_MODE", "")
    payment_args = " ".join(f"--env-file {path}" for path in args.payment_env_file)
    if args.allow_payment_placeholders:
        payment_args += " --allow-placeholders"
    return result(
        "production-payment-profile",
        "Production payment profile",
        f"python3 scripts/check-production-payment-profile.py {payment_args}",
        errors,
        details=details,
    )


def validate_woocommerce(args: argparse.Namespace) -> dict[str, Any]:
    matrix = woocommerce_tool.load_json(args.woocommerce_matrix)
    errors = woocommerce_tool.validate_matrix(matrix)
    details: dict[str, Any] = {
        "matrix": rel(args.woocommerce_matrix),
        "smoke_requested": args.run_woocommerce_smoke,
        "entry": args.woocommerce_entry,
        "include_optional": args.include_optional_woocommerce,
    }
    command = f"python3 scripts/check-woocommerce-compatibility-matrix.py --matrix {rel(args.woocommerce_matrix)}"
    if args.run_woocommerce_smoke:
        command += " --run-smoke"
        if args.include_optional_woocommerce:
            command += " --include-optional"
        if args.woocommerce_entry:
            command += f" --entry {args.woocommerce_entry}"
        if not errors:
            try:
                entries = woocommerce_tool.selected_entries(
                    matrix,
                    entry_id=args.woocommerce_entry,
                    include_optional=args.include_optional_woocommerce,
                )
                if not entries:
                    errors.append("no selected WooCommerce compatibility runtime entries")
                for entry in entries:
                    woocommerce_tool.run_smoke_entry(entry)
            except Exception as exc:  # pragma: no cover - exercised through CLI smoke, not unit tests.
                errors.append(f"WooCommerce compatibility smoke failed: {exc}")
    return result(
        "woocommerce-compatibility",
        "WooCommerce compatibility gate",
        command,
        errors,
        details=details,
    )


def release_decision_summary(gates: list[dict[str, Any]]) -> dict[str, Any]:
    failed = [gate for gate in gates if gate["status"] != "passed"]
    return {
        "status": "passed" if not failed else "failed",
        "blocking_gate_count": len(failed),
        "failed_gate_ids": [gate["id"] for gate in failed],
        "missing_evidence_count": sum(gate["evidence_summary"]["missing"] for gate in gates),
        "attach_this_report": True,
    }


def collect_evidence(args: argparse.Namespace) -> dict[str, Any]:
    gates = [
        validate_pilot(args),
        validate_buyer_agents(args),
        validate_payment_profile(args),
        validate_woocommerce(args),
    ]
    return {
        "schema": "agentcart.pilot_evidence_runner.v1",
        "generated_at": utcnow(),
        "status": "passed" if all(gate["status"] == "passed" for gate in gates) else "failed",
        "inputs": {
            "checklist": str(args.checklist),
            "pilot_evidence_dir": str(args.pilot_evidence_dir),
            "buyer_agent_matrix": str(args.buyer_agent_matrix),
            "buyer_agent_evidence_dir": str(args.buyer_agent_evidence_dir),
            "payment_env_files": [str(path) for path in args.payment_env_file],
            "woocommerce_matrix": str(args.woocommerce_matrix),
            "run_woocommerce_smoke": args.run_woocommerce_smoke,
            "include_optional_woocommerce": args.include_optional_woocommerce,
            "woocommerce_entry": args.woocommerce_entry,
        },
        "gates": gates,
        "release_decision": release_decision_summary(gates),
    }


def markdown_template(scope: str, owner_id: str, evidence_id: str) -> str:
    if evidence_id == "non_maintainer_setup_walkthrough_notes":
        return (
            "# Non-Maintainer Merchant Setup Walkthrough Notes\n\n"
            f"- Scope: `{scope}`\n"
            f"- Owner id: `{owner_id}`\n"
            "- Operator: TODO\n"
            "- Observer: TODO\n"
            "- Merchant/staging URL: TODO\n"
            "- Started at: TODO\n"
            "- Finished at: TODO\n"
            "- Plugin ZIP source: TODO\n"
            "- Checkout mode: TODO\n"
            "- Payment/verifier mode: TODO\n"
            "- Result: passed | blocked | partial\n\n"
            "## Setup Path\n\n"
            "- Starting doc: `woocommerce-shopbridge/README.md#merchant-setup`\n"
            "- WordPress/WooCommerce version: TODO\n"
            "- ShopBridge plugin version: TODO\n"
            "- Product exposure mode: TODO\n"
            "- Registry result: TODO\n"
            "- Live smoke command: TODO\n"
            "- Live smoke result: TODO\n\n"
            "## Evidence Links\n\n"
            "- Settings readiness snapshot: TODO\n"
            "- Catalog preview/export: TODO\n"
            "- Sandbox quote check: TODO\n"
            "- Sandbox checkout test: TODO\n"
            "- Live WooCommerce smoke: TODO\n"
            "- Registry record or bundle URL: TODO\n\n"
            "## Maintainer Help Log\n\n"
            "| Time | Step | What the operator tried | Help needed | Root cause | Follow-up issue |\n"
            "| --- | --- | --- | --- | --- | --- |\n"
            "| TODO | TODO | TODO | TODO | TODO | TODO |\n\n"
            "## Remaining Blockers\n\n"
            "| Severity | Title | Follow-up issue | Notes |\n"
            "| --- | --- | --- | --- |\n"
            "| TODO | TODO | TODO | TODO |\n"
        )
    return (
        f"# {evidence_id}\n\n"
        f"- Scope: `{scope}`\n"
        f"- Owner id: `{owner_id}`\n"
        "- Recorded at: TODO\n"
        "- Operator: TODO\n"
        "- Command or source: TODO\n\n"
        "## Evidence\n\n"
        "Paste the transcript, screenshot reference, hash, URL, or decision record here.\n"
    )


def write_sample_evidence(args: argparse.Namespace) -> dict[str, Any]:
    checklist = pilot_tool.load_json(args.checklist)
    matrix = buyer_matrix_tool.load_json(args.buyer_agent_matrix)
    sample_root = args.write_sample
    pilot_dir = sample_root / "pilot"
    buyer_dir = sample_root / "buyer-agents"
    written: list[str] = []
    pilot_items = pilot_evidence_items(checklist, pilot_dir)
    buyer_items = buyer_evidence_items(matrix, buyer_dir)
    for item in pilot_items:
        path = pathlib.Path(item["path"])
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            path.write_text(markdown_template(item["scope"], item["owner_id"], item["evidence_id"]), encoding="utf-8")
            written.append(str(path))
    for item in buyer_items:
        path = pathlib.Path(item["path"])
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            path.write_text(markdown_template(item["scope"], item["owner_id"], item["evidence_id"]), encoding="utf-8")
            written.append(str(path))
    readme = sample_root / "README.md"
    if not readme.exists():
        expected_paths = "\n".join(
            f"- `{pathlib.Path(item['path']).relative_to(sample_root)}`" for item in [*pilot_items, *buyer_items]
        )
        readme.write_text(
            "# Pilot Evidence Sample\n\n"
            "This folder is a template only. Replace every `TODO` with real pilot transcripts,\n"
            "hashes, command output, screenshots, or decision records before using it for a\n"
            "release decision.\n\n"
            "Expected evidence files:\n\n"
            f"{expected_paths}\n\n"
            "Validate with:\n\n"
            "```sh\n"
            "python3 scripts/collect-pilot-evidence.py \\\n"
            f"  --pilot-evidence-dir {sample_root}/pilot \\\n"
            f"  --buyer-agent-evidence-dir {sample_root}/buyer-agents \\\n"
            "  --payment-env-file deploy/home-server/.env \\\n"
            "  --report-out pilot-evidence-report.json\n"
            "```\n",
            encoding="utf-8",
        )
        written.append(str(readme))
    return {
        "schema": "agentcart.pilot_evidence_sample.v1",
        "sample_root": str(sample_root),
        "written": written,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Collect and validate the AgentCart external beta pilot evidence gates."
    )
    parser.add_argument("--checklist", type=pathlib.Path, default=ROOT / "gateway" / "config" / "pilot_beta_checklist.json")
    parser.add_argument("--pilot-evidence-dir", type=pathlib.Path, help="Pilot checklist evidence root.")
    parser.add_argument("--buyer-agent-matrix", type=pathlib.Path, default=ROOT / "gateway" / "config" / "buyer_agent_test_matrix.json")
    parser.add_argument("--buyer-agent-evidence-dir", type=pathlib.Path, help="Buyer-agent runtime evidence root.")
    parser.add_argument("--payment-env-file", action="append", type=pathlib.Path, help="Production payment env file. Pass multiple files to apply overrides.")
    parser.add_argument("--allow-payment-placeholders", action="store_true", help="Accept placeholder payment env values for checked-in samples only.")
    parser.add_argument("--woocommerce-matrix", type=pathlib.Path, default=ROOT / "gateway" / "config" / "woocommerce_compatibility_matrix.json")
    parser.add_argument("--run-woocommerce-smoke", action="store_true", help="Run selected WooCommerce compatibility Docker smoke entries.")
    parser.add_argument("--include-optional-woocommerce", action="store_true", help="With --run-woocommerce-smoke, include optional matrix entries.")
    parser.add_argument("--woocommerce-entry", default="", help="Run one WooCommerce compatibility matrix entry.")
    parser.add_argument("--report-out", type=pathlib.Path, help="Write the JSON release-decision report to this path.")
    parser.add_argument("--write-sample", type=pathlib.Path, help="Create a sample evidence folder template and exit.")
    args = parser.parse_args(argv)

    if args.write_sample:
        print(json.dumps(write_sample_evidence(args), indent=2, sort_keys=True))
        return 0

    required = {
        "--pilot-evidence-dir": args.pilot_evidence_dir,
        "--buyer-agent-evidence-dir": args.buyer_agent_evidence_dir,
        "--payment-env-file": args.payment_env_file,
    }
    missing_args = [name for name, value in required.items() if not value]
    if missing_args:
        parser.error(f"missing required argument(s) unless --write-sample is used: {', '.join(missing_args)}")

    report = collect_evidence(args)
    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.report_out:
        args.report_out.parent.mkdir(parents=True, exist_ok=True)
        args.report_out.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    if report["status"] != "passed":
        for gate in report["gates"]:
            for error in gate["errors"]:
                print(f"pilot evidence runner failed [{gate['id']}]: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
