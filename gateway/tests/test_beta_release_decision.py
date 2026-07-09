from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import pathlib
import sys
import tempfile
import types
import unittest


ROOT_DIR = pathlib.Path(__file__).resolve().parents[2]
DECISION_TOOL_PATH = ROOT_DIR / "scripts" / "build-beta-release-decision.py"
EVIDENCE_TOOL_PATH = ROOT_DIR / "scripts" / "collect-pilot-evidence.py"
CHECKLIST_PATH = ROOT_DIR / "gateway" / "config" / "pilot_beta_checklist.json"
MATRIX_PATH = ROOT_DIR / "gateway" / "config" / "buyer_agent_test_matrix.json"
WOOCOMMERCE_MATRIX_PATH = ROOT_DIR / "gateway" / "config" / "woocommerce_compatibility_matrix.json"


def load_tool(name: str, path: pathlib.Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


decision_tool = load_tool("beta_release_decision_tool", DECISION_TOOL_PATH)
evidence_tool = load_tool("pilot_evidence_runner_for_decision_tool", EVIDENCE_TOOL_PATH)


def write_payment_env(path: pathlib.Path) -> None:
    path.write_text(
        "\n".join(
            [
                "WOOCOMMERCE_MODE=plugin",
                "AGENTCART_CHECKOUT_MODE=external_verifier_only",
                "AGENTCART_PAYMENT_VERIFIER_URL=https://verifier.agentcart.test/stripe-mpp/verify",
                "AGENTCART_PAYMENT_VERIFIER_TOKEN=vvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvv",
                "AGENTCART_VERIFIER_REPLAY_STORE_DRIVER=sqlite",
                "AGENTCART_VERIFIER_REPLAY_STORE_PATH=/data/verifier/replay-store.sqlite",
                "AGENTCART_VERIFIER_REQUIRE_DURABLE_REPLAY=true",
                "AGENTCART_SIGNED_REQUEST_MODE=require_mutations",
                "AGENTCART_SIGNED_REQUEST_SECRET=ssssssssssssssssssssssssssssssssssssssss",
                "WOOCOMMERCE_SIGNED_REQUEST_SECRET=ssssssssssssssssssssssssssssssssssssssss",
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def fill_sample_evidence(sample_root: pathlib.Path) -> None:
    for path in sample_root.rglob("*.md"):
        if path.name == "README.md":
            continue
        scope = "buyer_agent_runtime" if "buyer-agents" in path.parts else "pilot_gate"
        owner_id = path.parent.name
        evidence_id = path.stem
        path.write_text(
            f"# {evidence_id}\n\n"
            f"- Scope: `{scope}`\n"
            f"- Owner id: `{owner_id}`\n"
            "- Recorded at: 2026-07-09T18:00:00Z\n"
            "- Operator: Pilot release decision fixture operator\n"
            "- Command or source: `agentcart beta release decision fixture`\n\n"
            "## Evidence\n\n"
            "The fixture records the complete command, observed result, acceptance criteria, "
            "and retained artifact reference required for a valid release decision report.\n",
            encoding="utf-8",
        )


def runner_args(
    *,
    pilot_evidence_dir: pathlib.Path,
    buyer_agent_evidence_dir: pathlib.Path,
    payment_env_file: pathlib.Path,
) -> types.SimpleNamespace:
    return types.SimpleNamespace(
        checklist=CHECKLIST_PATH,
        pilot_evidence_dir=pilot_evidence_dir,
        buyer_agent_matrix=MATRIX_PATH,
        buyer_agent_evidence_dir=buyer_agent_evidence_dir,
        payment_env_file=[payment_env_file],
        allow_payment_placeholders=False,
        woocommerce_matrix=WOOCOMMERCE_MATRIX_PATH,
        run_woocommerce_smoke=False,
        include_optional_woocommerce=False,
        woocommerce_entry="",
        report_out=None,
        write_sample=None,
    )


class BetaReleaseDecisionTest(unittest.TestCase):
    def test_no_go_decision_lists_failed_gates_and_evidence_references(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            pilot_evidence = root / "pilot"
            buyer_evidence = root / "buyer-agents"
            payment_env = root / "payment.env"
            report_path = root / "pilot-evidence-report.json"
            decision_path = root / "decision.md"
            pilot_evidence.mkdir()
            buyer_evidence.mkdir()
            write_payment_env(payment_env)
            report = evidence_tool.collect_evidence(
                runner_args(
                    pilot_evidence_dir=pilot_evidence,
                    buyer_agent_evidence_dir=buyer_evidence,
                    payment_env_file=payment_env,
                )
            )
            report_path.write_text(json.dumps(report), encoding="utf-8")

            with contextlib.redirect_stdout(io.StringIO()):
                exit_code = decision_tool.main(
                    [
                        "--report",
                        str(report_path),
                        "--decision",
                        "no-go",
                        "--operator",
                        "release-owner",
                        "--follow-up-issue",
                        "https://github.com/example/repo/issues/1",
                        "--out",
                        str(decision_path),
                    ]
                )
            decision = decision_path.read_text(encoding="utf-8")

        self.assertEqual(0, exit_code)
        self.assertIn("Decision: **NO-GO**", decision)
        self.assertIn("pilot-readiness", decision)
        self.assertIn("buyer-agent-runtime-evidence", decision)
        self.assertIn("non_maintainer_setup_walkthrough_notes", decision)
        self.assertIn("woocommerce_baseline_eu_tax_shipping_result", decision)
        self.assertIn("verifier_metrics_snapshot", decision)
        self.assertIn("https://github.com/example/repo/issues/1", decision)

    def test_go_decision_requires_passed_report_and_operational_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            pilot_evidence = root / "pilot"
            buyer_evidence = root / "buyer-agents"
            payment_env = root / "payment.env"
            report_path = root / "pilot-evidence-report.json"
            pilot_evidence.mkdir()
            buyer_evidence.mkdir()
            write_payment_env(payment_env)
            report = evidence_tool.collect_evidence(
                runner_args(
                    pilot_evidence_dir=pilot_evidence,
                    buyer_agent_evidence_dir=buyer_evidence,
                    payment_env_file=payment_env,
                )
            )
            report_path.write_text(json.dumps(report), encoding="utf-8")

            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                exit_code = decision_tool.main(["--report", str(report_path), "--decision", "go"])

        self.assertEqual(1, exit_code)
        self.assertIn("go decision requires a passed pilot evidence report", stdout.getvalue())
        self.assertIn("go decision requires --beta-scope", stdout.getvalue())

    def test_no_go_with_failed_report_requires_follow_up(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            pilot_evidence = root / "pilot"
            buyer_evidence = root / "buyer-agents"
            payment_env = root / "payment.env"
            report_path = root / "pilot-evidence-report.json"
            pilot_evidence.mkdir()
            buyer_evidence.mkdir()
            write_payment_env(payment_env)
            report = evidence_tool.collect_evidence(
                runner_args(
                    pilot_evidence_dir=pilot_evidence,
                    buyer_agent_evidence_dir=buyer_evidence,
                    payment_env_file=payment_env,
                )
            )
            report_path.write_text(json.dumps(report), encoding="utf-8")

            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                exit_code = decision_tool.main(["--report", str(report_path), "--decision", "no-go"])

        self.assertEqual(1, exit_code)
        self.assertIn("no-go decisions with failed gates should list follow-up", stdout.getvalue())

    def test_go_decision_includes_scope_and_present_evidence_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            sample_root = root / "pilot-evidence"
            payment_env = root / "payment.env"
            report_path = root / "pilot-evidence-report.json"
            decision_path = root / "decision.md"
            write_payment_env(payment_env)
            evidence_tool.write_sample_evidence(
                types.SimpleNamespace(
                    checklist=CHECKLIST_PATH,
                    buyer_agent_matrix=MATRIX_PATH,
                    write_sample=sample_root,
                )
            )
            fill_sample_evidence(sample_root)
            report = evidence_tool.collect_evidence(
                runner_args(
                    pilot_evidence_dir=sample_root / "pilot",
                    buyer_agent_evidence_dir=sample_root / "buyer-agents",
                    payment_env_file=payment_env,
                )
            )
            report_path.write_text(json.dumps(report), encoding="utf-8")

            with contextlib.redirect_stdout(io.StringIO()):
                exit_code = decision_tool.main(
                    [
                        "--report",
                        str(report_path),
                        "--decision",
                        "go",
                        "--operator",
                        "release-owner",
                        "--beta-scope",
                        "one supervised staging merchant, no real refunds",
                        "--rollback-owner",
                        "ops-owner",
                        "--support-channel",
                        "support@example.test",
                        "--observation-window",
                        "14 days",
                        "--accepted-risk",
                        "sandbox evidence only in this fixture",
                        "--out",
                        str(decision_path),
                    ]
                )
            decision = decision_path.read_text(encoding="utf-8")

        self.assertEqual(0, exit_code)
        self.assertIn("Decision: **GO**", decision)
        self.assertIn("one supervised staging merchant", decision)
        self.assertIn("Rollback owner: ops-owner", decision)
        self.assertIn("Support channel: support@example.test", decision)
        self.assertIn("Observation window: 14 days", decision)
        self.assertIn("sandbox evidence only in this fixture", decision)
        self.assertIn("valid at", decision)


if __name__ == "__main__":
    unittest.main()
