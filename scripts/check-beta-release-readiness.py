#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.util
import pathlib
import sys
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


def validate_beta_release(args: argparse.Namespace) -> list[str]:
    errors: list[str] = []

    checklist: dict[str, Any] = pilot_tool.load_json(args.checklist)
    errors.extend(pilot_tool.validate_checklist(checklist))
    if not args.pilot_evidence_dir.exists():
        errors.append(f"pilot evidence directory does not exist: {args.pilot_evidence_dir}")
    errors.extend(pilot_tool.validate_evidence(checklist, args.pilot_evidence_dir))

    matrix: dict[str, Any] = buyer_matrix_tool.load_json(args.buyer_agent_matrix)
    errors.extend(buyer_matrix_tool.validate_matrix(matrix))
    if not args.buyer_agent_evidence_dir.exists():
        errors.append(f"buyer-agent evidence directory does not exist: {args.buyer_agent_evidence_dir}")
    errors.extend(buyer_matrix_tool.validate_evidence(matrix, args.buyer_agent_evidence_dir))

    try:
        payment_env = payment_profile_tool.parse_env_files(args.payment_env_file)
    except ValueError as exc:
        errors.append(str(exc))
    else:
        errors.extend(
            payment_profile_tool.validate_profile(
                payment_env,
                allow_placeholders=args.allow_payment_placeholders,
            )
        )

    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "External beta release gate. Unlike scripts/verify.sh, this fails "
            "without recorded pilot evidence and a production-shaped payment profile."
        )
    )
    parser.add_argument(
        "--checklist",
        type=pathlib.Path,
        default=ROOT / "gateway" / "config" / "pilot_beta_checklist.json",
        help="Pilot beta checklist JSON.",
    )
    parser.add_argument(
        "--pilot-evidence-dir",
        required=True,
        type=pathlib.Path,
        help="Evidence directory for the pilot checklist.",
    )
    parser.add_argument(
        "--buyer-agent-matrix",
        type=pathlib.Path,
        default=ROOT / "gateway" / "config" / "buyer_agent_test_matrix.json",
        help="Buyer-agent matrix JSON.",
    )
    parser.add_argument(
        "--buyer-agent-evidence-dir",
        required=True,
        type=pathlib.Path,
        help="Evidence directory for the buyer-agent runtime matrix.",
    )
    parser.add_argument(
        "--payment-env-file",
        action="append",
        required=True,
        type=pathlib.Path,
        help="Production payment env file. Pass multiple files to apply overrides.",
    )
    parser.add_argument(
        "--allow-payment-placeholders",
        action="store_true",
        help="Accept placeholder payment env values. Only use for validating example files, not real beta releases.",
    )
    args = parser.parse_args(argv)

    errors = validate_beta_release(args)
    if errors:
        for error in errors:
            print(f"beta release readiness check failed: {error}", file=sys.stderr)
        return 1
    print("beta release readiness ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
