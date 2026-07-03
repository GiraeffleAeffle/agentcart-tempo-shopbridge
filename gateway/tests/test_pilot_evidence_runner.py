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
TOOL_PATH = ROOT_DIR / "scripts" / "collect-pilot-evidence.py"
CHECKLIST_PATH = ROOT_DIR / "gateway" / "config" / "pilot_beta_checklist.json"
MATRIX_PATH = ROOT_DIR / "gateway" / "config" / "buyer_agent_test_matrix.json"
WOOCOMMERCE_MATRIX_PATH = ROOT_DIR / "gateway" / "config" / "woocommerce_compatibility_matrix.json"
SPEC = importlib.util.spec_from_file_location("pilot_evidence_runner_tool", TOOL_PATH)
pilot_evidence_runner_tool = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules["pilot_evidence_runner_tool"] = pilot_evidence_runner_tool
SPEC.loader.exec_module(pilot_evidence_runner_tool)


def write_payment_env(path: pathlib.Path) -> None:
    path.write_text(
        "\n".join(
            [
                "WOOCOMMERCE_MODE=plugin",
                "AGENTCART_CHECKOUT_MODE=external_verifier_only",
                "AGENTCART_PAYMENT_VERIFIER_URL=https://verifier.agentcart.test/stripe-mpp/verify",
                "AGENTCART_PAYMENT_VERIFIER_TOKEN=verifier-token",
                "AGENTCART_VERIFIER_REPLAY_STORE_DRIVER=sqlite",
                "AGENTCART_VERIFIER_REPLAY_STORE_PATH=/data/verifier/replay-store.sqlite",
                "AGENTCART_VERIFIER_REQUIRE_DURABLE_REPLAY=true",
                "AGENTCART_SIGNED_REQUEST_MODE=require_mutations",
                "AGENTCART_SIGNED_REQUEST_SECRET=shared-signing-secret",
                "WOOCOMMERCE_SIGNED_REQUEST_SECRET=shared-signing-secret",
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def runner_args(
    *,
    pilot_evidence_dir: pathlib.Path,
    buyer_agent_evidence_dir: pathlib.Path,
    payment_env_file: pathlib.Path,
    report_out: pathlib.Path | None = None,
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
        report_out=report_out,
        write_sample=None,
    )


class PilotEvidenceRunnerTest(unittest.TestCase):
    def test_missing_evidence_report_includes_gate_ids_and_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            pilot_evidence = root / "pilot"
            buyer_evidence = root / "buyer-agents"
            payment_env = root / "payment.env"
            pilot_evidence.mkdir()
            buyer_evidence.mkdir()
            write_payment_env(payment_env)

            report = pilot_evidence_runner_tool.collect_evidence(
                runner_args(
                    pilot_evidence_dir=pilot_evidence,
                    buyer_agent_evidence_dir=buyer_evidence,
                    payment_env_file=payment_env,
                )
            )

        self.assertEqual("failed", report["status"])
        pilot_gate = next(gate for gate in report["gates"] if gate["id"] == "pilot-readiness")
        buyer_gate = next(gate for gate in report["gates"] if gate["id"] == "buyer-agent-runtime-evidence")

        self.assertTrue(
            any(
                item["owner_id"] == "pilot-merchant-onboarding"
                and item["evidence_id"] == "plugin_zip_install_screenshot_or_log"
                and item["path"].endswith(
                    "pilot/pilot-merchant-onboarding/plugin_zip_install_screenshot_or_log.md"
                )
                for item in pilot_gate["missing_evidence"]
            ),
            pilot_gate["missing_evidence"],
        )
        self.assertTrue(
            any(
                item["owner_id"] == "pilot-merchant-onboarding"
                and item["evidence_id"] == "woocommerce_baseline_eu_tax_shipping_result"
                and item["path"].endswith(
                    "pilot/pilot-merchant-onboarding/woocommerce_baseline_eu_tax_shipping_result.md"
                )
                for item in pilot_gate["missing_evidence"]
            ),
            pilot_gate["missing_evidence"],
        )
        self.assertTrue(
            any(
                item["owner_id"] == "pilot-merchant-onboarding"
                and item["evidence_id"] == "non_maintainer_setup_walkthrough_notes"
                and item["path"].endswith(
                    "pilot/pilot-merchant-onboarding/non_maintainer_setup_walkthrough_notes.md"
                )
                for item in pilot_gate["missing_evidence"]
            ),
            pilot_gate["missing_evidence"],
        )
        self.assertTrue(
            any(
                "missing evidence for pilot_gate pilot-merchant-onboarding: "
                "plugin_zip_install_screenshot_or_log -> " in error
                for error in pilot_gate["errors"]
            ),
            pilot_gate["errors"],
        )
        self.assertTrue(
            any(
                "missing evidence for pilot_gate pilot-merchant-onboarding: "
                "woocommerce_restricted_stock_policy_result -> " in error
                for error in pilot_gate["errors"]
            ),
            pilot_gate["errors"],
        )
        self.assertTrue(
            any(
                "missing evidence for pilot_gate pilot-merchant-onboarding: "
                "non_maintainer_setup_walkthrough_notes -> " in error
                for error in pilot_gate["errors"]
            ),
            pilot_gate["errors"],
        )
        self.assertTrue(
            any(
                item["owner_id"] == "shopbridge-direct-skill"
                and item["evidence_id"] == "merchant_discovery_transcript"
                and item["path"].endswith("buyer-agents/shopbridge-direct-skill/merchant_discovery_transcript.md")
                for item in buyer_gate["missing_evidence"]
            ),
            buyer_gate["missing_evidence"],
        )
        self.assertEqual(["pilot-readiness", "buyer-agent-runtime-evidence"], report["release_decision"]["failed_gate_ids"])

    def test_sample_writer_documents_transcript_names_and_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            sample_root = root / "pilot-evidence"
            payment_env = root / "payment.env"
            write_payment_env(payment_env)

            sample = pilot_evidence_runner_tool.write_sample_evidence(
                types.SimpleNamespace(
                    checklist=CHECKLIST_PATH,
                    buyer_agent_matrix=MATRIX_PATH,
                    write_sample=sample_root,
                )
            )
            report = pilot_evidence_runner_tool.collect_evidence(
                runner_args(
                    pilot_evidence_dir=sample_root / "pilot",
                    buyer_agent_evidence_dir=sample_root / "buyer-agents",
                    payment_env_file=payment_env,
                )
            )

            readme = (sample_root / "README.md").read_text(encoding="utf-8")
            walkthrough = (
                sample_root
                / "pilot"
                / "pilot-merchant-onboarding"
                / "non_maintainer_setup_walkthrough_notes.md"
            ).read_text(encoding="utf-8")

        self.assertEqual("agentcart.pilot_evidence_sample.v1", sample["schema"])
        self.assertEqual("passed", report["status"])
        self.assertIn("## Maintainer Help Log", walkthrough)
        self.assertIn("| Severity | Title | Follow-up issue | Notes |", walkthrough)
        self.assertIn("buyer-agents/agentcart-service-openclaw/merchant_discovery_transcript.md", readme)
        self.assertIn("buyer-agents/agentcart-service-openclaw/quote_comparison_transcript.md", readme)
        self.assertIn("buyer-agents/shopbridge-direct-skill/merchant_discovery_transcript.md", readme)
        self.assertIn("buyer-agents/shopbridge-direct-skill/quote_comparison_transcript.md", readme)
        self.assertIn("buyer-agents/generic-mcp-client/quote_creation_transcript.md", readme)

    def test_main_writes_attachable_json_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            sample_root = root / "pilot-evidence"
            payment_env = root / "payment.env"
            report_path = root / "pilot-evidence-report.json"
            write_payment_env(payment_env)
            pilot_evidence_runner_tool.write_sample_evidence(
                types.SimpleNamespace(
                    checklist=CHECKLIST_PATH,
                    buyer_agent_matrix=MATRIX_PATH,
                    write_sample=sample_root,
                )
            )

            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                exit_code = pilot_evidence_runner_tool.main(
                    [
                        "--pilot-evidence-dir",
                        str(sample_root / "pilot"),
                        "--buyer-agent-evidence-dir",
                        str(sample_root / "buyer-agents"),
                        "--payment-env-file",
                        str(payment_env),
                        "--report-out",
                        str(report_path),
                    ]
                )

            report = json.loads(report_path.read_text(encoding="utf-8"))

        self.assertEqual(0, exit_code)
        self.assertIn('"schema": "agentcart.pilot_evidence_runner.v1"', stdout.getvalue())
        self.assertEqual("agentcart.pilot_evidence_runner.v1", report["schema"])
        self.assertEqual("passed", report["release_decision"]["status"])
        self.assertTrue(report["release_decision"]["attach_this_report"])


if __name__ == "__main__":
    unittest.main()
