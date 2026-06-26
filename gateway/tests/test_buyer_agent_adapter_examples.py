from __future__ import annotations

import importlib.util
import json
import pathlib
import sys
import unittest


ROOT_DIR = pathlib.Path(__file__).resolve().parents[2]
TOOL_PATH = ROOT_DIR / "scripts" / "check-buyer-agent-adapter-examples.py"
CONFIG_PATH = ROOT_DIR / "gateway" / "config" / "buyer_agent_adapter_examples.json"
MATRIX_PATH = ROOT_DIR / "gateway" / "config" / "buyer_agent_test_matrix.json"
SPEC = importlib.util.spec_from_file_location("buyer_agent_adapter_examples_tool", TOOL_PATH)
buyer_agent_adapter_examples_tool = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules["buyer_agent_adapter_examples_tool"] = buyer_agent_adapter_examples_tool
SPEC.loader.exec_module(buyer_agent_adapter_examples_tool)


def load_config() -> dict[str, object]:
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def load_matrix() -> dict[str, object]:
    return json.loads(MATRIX_PATH.read_text(encoding="utf-8"))


class BuyerAgentAdapterExamplesTest(unittest.TestCase):
    def test_checked_in_adapter_examples_are_valid(self) -> None:
        errors = buyer_agent_adapter_examples_tool.validate_examples(load_config(), load_matrix())

        self.assertEqual([], errors)

    def test_missing_required_runtime_example_fails(self) -> None:
        config = load_config()
        config["examples"] = [
            example
            for example in config["examples"]
            if isinstance(example, dict) and example.get("runtime_id") != "generic-mcp-client"
        ]

        errors = buyer_agent_adapter_examples_tool.validate_examples(config, load_matrix())

        self.assertTrue(any("generic-mcp-client" in error for error in errors), errors)

    def test_missing_safety_rule_fails(self) -> None:
        matrix = load_matrix()
        config = load_config()
        first_path = ROOT_DIR / config["examples"][0]["example_file"]
        example = json.loads(first_path.read_text(encoding="utf-8"))
        example["safety_rules"] = [
            rule for rule in example["safety_rules"] if rule != "human_approval_before_checkout"
        ]
        runtime = {
            runtime["id"]: runtime
            for runtime in matrix["runtimes"]
            if isinstance(runtime, dict)
        }[example["runtime_id"]]
        errors: list[str] = []

        buyer_agent_adapter_examples_tool.validate_example_document(
            example,
            config["examples"][0],
            runtime,
            set(matrix["required_capabilities"]),
            set(matrix["required_safety_rules"]),
            errors,
        )

        self.assertTrue(any("human_approval_before_checkout" in error for error in errors), errors)


if __name__ == "__main__":
    unittest.main()
