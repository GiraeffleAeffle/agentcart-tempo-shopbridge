from __future__ import annotations

import importlib.util
import json
import pathlib
import sys
import unittest


ROOT_DIR = pathlib.Path(__file__).resolve().parents[2]
TOOL_PATH = ROOT_DIR / "scripts" / "check-prompt-injection-corpus.py"
CORPUS_PATH = ROOT_DIR / "gateway" / "config" / "prompt_injection_corpus.json"
SPEC = importlib.util.spec_from_file_location("prompt_injection_corpus_tool", TOOL_PATH)
prompt_injection_corpus_tool = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules["prompt_injection_corpus_tool"] = prompt_injection_corpus_tool
SPEC.loader.exec_module(prompt_injection_corpus_tool)


def load_corpus() -> dict[str, object]:
    return json.loads(CORPUS_PATH.read_text(encoding="utf-8"))


class PromptInjectionCorpusTest(unittest.TestCase):
    def test_checked_in_corpus_is_valid(self) -> None:
        errors = prompt_injection_corpus_tool.validate_corpus(load_corpus())

        self.assertEqual([], errors)

    def test_runtime_test_references_exist(self) -> None:
        errors = prompt_injection_corpus_tool.validate_runtime_test_refs(load_corpus())

        self.assertEqual([], errors)

    def test_missing_surface_fails(self) -> None:
        corpus = load_corpus()
        corpus["cases"] = [
            case
            for case in corpus["cases"]
            if isinstance(case, dict) and case.get("surface") != "registry_profile"
        ]

        errors = prompt_injection_corpus_tool.validate_corpus(corpus)

        self.assertTrue(any("registry_profile" in error for error in errors), errors)

    def test_missing_untrusted_control_fails(self) -> None:
        corpus = load_corpus()
        first_case = corpus["cases"][0]
        first_case["expected_controls"] = [
            control for control in first_case["expected_controls"] if control != "merchant_text_untrusted"
        ]

        errors = prompt_injection_corpus_tool.validate_corpus(corpus)

        self.assertTrue(any("merchant_text_untrusted" in error for error in errors), errors)


if __name__ == "__main__":
    unittest.main()
