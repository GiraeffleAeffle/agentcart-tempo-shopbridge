#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import pathlib
import sys
from typing import Any


REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = REPO_ROOT / "gateway" / "config" / "buyer_agent_adapter_examples.json"
DEFAULT_MATRIX = REPO_ROOT / "gateway" / "config" / "buyer_agent_test_matrix.json"


def load_json(path: pathlib.Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"{path}: invalid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise SystemExit(f"{path}: JSON root must be an object")
    return data


def require(condition: bool, message: str, errors: list[str]) -> None:
    if not condition:
        errors.append(message)


def resolve_repo_path(path_value: str) -> pathlib.Path:
    path = pathlib.Path(path_value)
    return path if path.is_absolute() else REPO_ROOT / path


def matrix_runtime_by_id(matrix: dict[str, Any]) -> dict[str, dict[str, Any]]:
    runtimes = matrix.get("runtimes")
    if not isinstance(runtimes, list):
        return {}
    return {
        str(runtime.get("id") or ""): runtime
        for runtime in runtimes
        if isinstance(runtime, dict) and str(runtime.get("id") or "")
    }


def validate_example_document(
    example: dict[str, Any],
    expected: dict[str, Any],
    runtime: dict[str, Any],
    required_capabilities: set[str],
    required_safety_rules: set[str],
    errors: list[str],
) -> None:
    example_id = str(expected.get("id") or "")
    require(example.get("schema") == "agentcart.buyer_agent_adapter_example.v1", f"{example_id}: example schema must be agentcart.buyer_agent_adapter_example.v1", errors)
    require(str(example.get("id") or "") == example_id, f"{example_id}: example id must match config id", errors)
    require(str(example.get("runtime_id") or "") == str(expected.get("runtime_id") or ""), f"{example_id}: runtime_id must match config", errors)
    require(str(example.get("integration_mode") or "") == str(expected.get("integration_mode") or ""), f"{example_id}: integration_mode must match config", errors)

    install = example.get("install")
    require(isinstance(install, dict), f"{example_id}: install must be an object", errors)
    if isinstance(install, dict):
        require(
            bool(install.get("skill_directory") or install.get("tool_catalog_urls")),
            f"{example_id}: install must declare skill_directory or tool_catalog_urls",
            errors,
        )
        environment = install.get("required_environment")
        require(isinstance(environment, list) and bool(environment), f"{example_id}: install.required_environment must be a non-empty list", errors)

    run_sequence = example.get("run_sequence")
    require(isinstance(run_sequence, list) and len(run_sequence) >= 5, f"{example_id}: run_sequence must contain at least five steps", errors)
    seen_step_ids: set[str] = set()
    seen_commands: set[str] = set()
    if isinstance(run_sequence, list):
        for index, step in enumerate(run_sequence):
            if not isinstance(step, dict):
                errors.append(f"{example_id}: run_sequence[{index}] must be an object")
                continue
            step_id = str(step.get("id") or "")
            require(step_id != "", f"{example_id}: run_sequence[{index}].id is required", errors)
            require(step_id not in seen_step_ids, f"{example_id}: duplicate run step id {step_id}", errors)
            seen_step_ids.add(step_id)
            command = str(step.get("command") or step.get("tool") or "")
            require(command != "", f"{example_id}: {step_id} must declare command or tool", errors)
            if command:
                seen_commands.add(command)
            expect = step.get("expect")
            require(isinstance(expect, list) and bool(expect), f"{example_id}: {step_id}.expect must be a non-empty list", errors)

    runtime_commands = {
        str(command)
        for command in runtime.get("commands_or_tools", [])
        if isinstance(command, str)
    }
    if runtime_commands:
        overlap = runtime_commands & seen_commands
        require(bool(overlap), f"{example_id}: run_sequence must use at least one matrix command/tool", errors)

    covers = example.get("covers_capabilities")
    require(isinstance(covers, list), f"{example_id}: covers_capabilities must be a list", errors)
    if isinstance(covers, list):
        missing_capabilities = required_capabilities - set(covers)
        require(not missing_capabilities, f"{example_id}: missing capabilities: {', '.join(sorted(missing_capabilities))}", errors)

    safety = example.get("safety_rules")
    require(isinstance(safety, list), f"{example_id}: safety_rules must be a list", errors)
    if isinstance(safety, list):
        missing_safety = required_safety_rules - set(safety)
        require(not missing_safety, f"{example_id}: missing safety rules: {', '.join(sorted(missing_safety))}", errors)

    evidence = example.get("evidence_outputs")
    required_evidence = runtime.get("required_evidence")
    require(isinstance(evidence, list) and bool(evidence), f"{example_id}: evidence_outputs must be a non-empty list", errors)
    if isinstance(evidence, list) and isinstance(required_evidence, list):
        missing_evidence = set(required_evidence) - set(evidence)
        require(not missing_evidence, f"{example_id}: missing evidence outputs: {', '.join(sorted(missing_evidence))}", errors)


def validate_examples(config: dict[str, Any], matrix: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    require(config.get("schema") == "agentcart.buyer_agent_adapter_examples.v1", "schema must be agentcart.buyer_agent_adapter_examples.v1", errors)
    require(config.get("stage") == "external_beta", "stage must be external_beta", errors)

    runtimes = matrix_runtime_by_id(matrix)
    required_runtime_ids = config.get("required_runtime_ids")
    require(isinstance(required_runtime_ids, list) and bool(required_runtime_ids), "required_runtime_ids must be a non-empty list", errors)

    matrix_required_capabilities = matrix.get("required_capabilities")
    required_capabilities = set(matrix_required_capabilities) if isinstance(matrix_required_capabilities, list) else set()
    require(bool(required_capabilities), "matrix.required_capabilities must be available", errors)

    matrix_safety_rules = matrix.get("required_safety_rules")
    required_safety_rules = set(matrix_safety_rules) if isinstance(matrix_safety_rules, list) else set()
    require(bool(required_safety_rules), "matrix.required_safety_rules must be available", errors)

    examples = config.get("examples")
    require(isinstance(examples, list) and bool(examples), "examples must be a non-empty list", errors)
    seen_ids: set[str] = set()
    seen_runtime_ids: set[str] = set()
    if isinstance(examples, list):
        for index, entry in enumerate(examples):
            if not isinstance(entry, dict):
                errors.append(f"examples[{index}] must be an object")
                continue
            example_id = str(entry.get("id") or "")
            runtime_id = str(entry.get("runtime_id") or "")
            integration_mode = str(entry.get("integration_mode") or "")
            example_file = str(entry.get("example_file") or "")
            require(example_id != "", f"examples[{index}].id is required", errors)
            require(example_id not in seen_ids, f"duplicate example id: {example_id}", errors)
            seen_ids.add(example_id)
            require(runtime_id in runtimes, f"{example_id}: runtime_id must exist in buyer-agent matrix", errors)
            seen_runtime_ids.add(runtime_id)
            runtime = runtimes.get(runtime_id, {})
            require(integration_mode == str(runtime.get("integration_mode") or ""), f"{example_id}: integration_mode must match matrix runtime", errors)
            require(example_file != "", f"{example_id}: example_file is required", errors)
            path = resolve_repo_path(example_file)
            require(path.exists(), f"{example_id}: missing example_file {example_file}", errors)
            for setup_doc in entry.get("setup_docs", []):
                if isinstance(setup_doc, str):
                    require(resolve_repo_path(setup_doc).exists(), f"{example_id}: missing setup doc {setup_doc}", errors)
            if path.exists():
                example_doc = load_json(path)
                validate_example_document(
                    example_doc,
                    entry,
                    runtime,
                    required_capabilities,
                    required_safety_rules,
                    errors,
                )

    if isinstance(required_runtime_ids, list):
        missing_examples = set(required_runtime_ids) - seen_runtime_ids
        require(not missing_examples, f"missing examples for required runtimes: {', '.join(sorted(missing_examples))}", errors)
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate checked buyer-agent adapter examples.")
    parser.add_argument("--config", type=pathlib.Path, default=DEFAULT_CONFIG)
    parser.add_argument("--matrix", type=pathlib.Path, default=DEFAULT_MATRIX)
    args = parser.parse_args(argv)

    config = load_json(args.config)
    matrix = load_json(args.matrix)
    errors = validate_examples(config, matrix)
    if errors:
        for error in errors:
            print(f"buyer-agent adapter example check failed: {error}", file=sys.stderr)
        return 1
    print(f"buyer-agent adapter examples ok: {args.config}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
