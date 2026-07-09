from __future__ import annotations

import importlib.util
import json
import pathlib
import sys
import tempfile
import unittest


ROOT_DIR = pathlib.Path(__file__).resolve().parents[2]
TOOL_PATH = ROOT_DIR / "scripts" / "check-pilot-readiness.py"
CHECKLIST_PATH = ROOT_DIR / "gateway" / "config" / "pilot_beta_checklist.json"
SPEC = importlib.util.spec_from_file_location("pilot_readiness_tool", TOOL_PATH)
pilot_readiness_tool = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules["pilot_readiness_tool"] = pilot_readiness_tool
SPEC.loader.exec_module(pilot_readiness_tool)


def load_checklist() -> dict[str, object]:
    return json.loads(CHECKLIST_PATH.read_text(encoding="utf-8"))


def valid_evidence(evidence_id: str, owner_id: str) -> str:
    return (
        f"# {evidence_id}\n\n"
        "- Scope: `pilot_gate`\n"
        f"- Owner id: `{owner_id}`\n"
        "- Recorded at: 2026-07-09T18:00:00Z\n"
        "- Operator: External pilot operator\n"
        "- Command or source: `agentcart evidence verification fixture`\n\n"
        "## Evidence\n\n"
        "The operator captured the complete command output and verified the expected "
        "result against the pilot acceptance criteria. The referenced artifact is retained.\n"
    )


class PilotReadinessTest(unittest.TestCase):
    def test_checked_in_pilot_checklist_is_valid(self) -> None:
        errors = pilot_readiness_tool.validate_checklist(load_checklist())

        self.assertEqual([], errors)

    def test_missing_required_gate_fails(self) -> None:
        checklist = load_checklist()
        checklist["gates"] = [
            gate
            for gate in checklist["gates"]
            if isinstance(gate, dict) and gate.get("id") != "pilot-rollback"
        ]

        errors = pilot_readiness_tool.validate_checklist(checklist)

        self.assertTrue(any("pilot-rollback" in error for error in errors), errors)

    def test_woocommerce_merchant_variance_evidence_is_required(self) -> None:
        checklist = load_checklist()
        merchant_gate = next(
            gate
            for gate in checklist["gates"]
            if isinstance(gate, dict) and gate.get("id") == "pilot-merchant-onboarding"
        )

        self.assertIn("woocommerce_baseline_eu_tax_shipping_result", merchant_gate["required_evidence"])
        self.assertIn("woocommerce_restricted_stock_policy_result", merchant_gate["required_evidence"])

    def test_non_maintainer_walkthrough_evidence_is_required(self) -> None:
        checklist = load_checklist()
        merchant_gate = next(
            gate
            for gate in checklist["gates"]
            if isinstance(gate, dict) and gate.get("id") == "pilot-merchant-onboarding"
        )

        self.assertIn("non_maintainer_setup_walkthrough_notes", merchant_gate["required_evidence"])

    def test_evidence_check_requires_expected_files(self) -> None:
        checklist = load_checklist()
        first_gate = checklist["gates"][0]
        checklist["gates"] = [first_gate]

        with tempfile.TemporaryDirectory() as tmp:
            errors = pilot_readiness_tool.validate_evidence(checklist, pathlib.Path(tmp))

        self.assertGreaterEqual(len(errors), 3)
        self.assertTrue(all("missing evidence file:" in error for error in errors), errors)

    def test_evidence_check_accepts_expected_files(self) -> None:
        checklist = load_checklist()
        first_gate = checklist["gates"][0]
        checklist["gates"] = [first_gate]

        with tempfile.TemporaryDirectory() as tmp:
            evidence_dir = pathlib.Path(tmp)
            gate_dir = evidence_dir / first_gate["id"]
            gate_dir.mkdir(parents=True)
            for evidence_id in first_gate["required_evidence"]:
                (gate_dir / f"{evidence_id}.md").write_text(
                    valid_evidence(evidence_id, first_gate["id"]),
                    encoding="utf-8",
                )

            errors = pilot_readiness_tool.validate_evidence(checklist, evidence_dir)

        self.assertEqual([], errors)

    def test_evidence_check_rejects_generated_placeholder(self) -> None:
        checklist = load_checklist()
        first_gate = checklist["gates"][0]
        first_evidence_id = first_gate["required_evidence"][0]
        first_gate["required_evidence"] = [first_evidence_id]
        checklist["gates"] = [first_gate]

        with tempfile.TemporaryDirectory() as tmp:
            evidence_dir = pathlib.Path(tmp)
            gate_dir = evidence_dir / first_gate["id"]
            gate_dir.mkdir(parents=True)
            (gate_dir / f"{first_evidence_id}.md").write_text(
                f"# {first_evidence_id}\n\n"
                "- Recorded at: TODO\n"
                "- Operator: TODO\n"
                "- Command or source: TODO\n\n"
                "## Evidence\n\n"
                "Paste the transcript, screenshot reference, hash, URL, or decision record here.\n",
                encoding="utf-8",
            )

            errors = pilot_readiness_tool.validate_evidence(checklist, evidence_dir)

        self.assertTrue(any("incomplete marker" in error for error in errors), errors)

    def test_evidence_check_rejects_unsigned_draft(self) -> None:
        checklist = load_checklist()
        first_gate = checklist["gates"][0]
        first_evidence_id = first_gate["required_evidence"][0]
        first_gate["required_evidence"] = [first_evidence_id]
        checklist["gates"] = [first_gate]

        with tempfile.TemporaryDirectory() as tmp:
            evidence_dir = pathlib.Path(tmp)
            gate_dir = evidence_dir / first_gate["id"]
            gate_dir.mkdir(parents=True)
            evidence = valid_evidence(first_evidence_id, first_gate["id"]).replace(
                "2026-07-09T18:00:00Z",
                "2026-07-09 (DRAFT - pending operator confirmation)",
            )
            (gate_dir / f"{first_evidence_id}.md").write_text(evidence, encoding="utf-8")

            errors = pilot_readiness_tool.validate_evidence(checklist, evidence_dir)

        self.assertTrue(any("unsigned draft" in error for error in errors), errors)

    def test_evidence_check_rejects_trivial_content(self) -> None:
        checklist = load_checklist()
        first_gate = checklist["gates"][0]
        first_evidence_id = first_gate["required_evidence"][0]
        first_gate["required_evidence"] = [first_evidence_id]
        checklist["gates"] = [first_gate]

        with tempfile.TemporaryDirectory() as tmp:
            evidence_dir = pathlib.Path(tmp)
            gate_dir = evidence_dir / first_gate["id"]
            gate_dir.mkdir(parents=True)
            (gate_dir / f"{first_evidence_id}.md").write_text(
                f"# {first_evidence_id}\n\n"
                "- Scope: `pilot_gate`\n"
                f"- Owner id: `{first_gate['id']}`\n"
                "- Recorded at: 2026-07-09T18:00:00Z\n"
                "- Operator: External pilot operator\n"
                "- Command or source: manual check\n\n"
                "## Evidence\n\nPassed.\n",
                encoding="utf-8",
            )

            errors = pilot_readiness_tool.validate_evidence(checklist, evidence_dir)

        self.assertTrue(any("substantive evidence" in error for error in errors), errors)


if __name__ == "__main__":
    unittest.main()
