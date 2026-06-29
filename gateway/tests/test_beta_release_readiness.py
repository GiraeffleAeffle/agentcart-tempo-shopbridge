from __future__ import annotations

import importlib.util
import json
import pathlib
import sys
import tempfile
import types
import unittest


ROOT_DIR = pathlib.Path(__file__).resolve().parents[2]
TOOL_PATH = ROOT_DIR / "scripts" / "check-beta-release-readiness.py"
CHECKLIST_PATH = ROOT_DIR / "gateway" / "config" / "pilot_beta_checklist.json"
MATRIX_PATH = ROOT_DIR / "gateway" / "config" / "buyer_agent_test_matrix.json"
SPEC = importlib.util.spec_from_file_location("beta_release_readiness_tool", TOOL_PATH)
beta_release_readiness_tool = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules["beta_release_readiness_tool"] = beta_release_readiness_tool
SPEC.loader.exec_module(beta_release_readiness_tool)


def write_pilot_evidence(checklist: dict[str, object], root: pathlib.Path) -> None:
    for gate in checklist["gates"]:
        assert isinstance(gate, dict)
        gate_dir = root / str(gate["id"])
        gate_dir.mkdir(parents=True)
        for evidence_id in gate["required_evidence"]:
            (gate_dir / f"{evidence_id}.md").write_text("recorded evidence\n", encoding="utf-8")


def write_buyer_agent_evidence(matrix: dict[str, object], root: pathlib.Path) -> None:
    for runtime in matrix["runtimes"]:
        assert isinstance(runtime, dict)
        runtime_dir = root / str(runtime["id"])
        runtime_dir.mkdir(parents=True)
        for evidence_id in runtime["required_evidence"]:
            (runtime_dir / f"{evidence_id}.md").write_text("runtime evidence\n", encoding="utf-8")


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


class BetaReleaseReadinessTest(unittest.TestCase):
    def test_release_readiness_requires_and_accepts_evidence(self) -> None:
        checklist = json.loads(CHECKLIST_PATH.read_text(encoding="utf-8"))
        matrix = json.loads(MATRIX_PATH.read_text(encoding="utf-8"))

        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            pilot_evidence = root / "pilot"
            buyer_evidence = root / "buyer"
            payment_env = root / "payment.env"
            write_pilot_evidence(checklist, pilot_evidence)
            write_buyer_agent_evidence(matrix, buyer_evidence)
            write_payment_env(payment_env)
            args = types.SimpleNamespace(
                checklist=CHECKLIST_PATH,
                pilot_evidence_dir=pilot_evidence,
                buyer_agent_matrix=MATRIX_PATH,
                buyer_agent_evidence_dir=buyer_evidence,
                payment_env_file=[payment_env],
                allow_payment_placeholders=False,
            )

            errors = beta_release_readiness_tool.validate_beta_release(args)

        self.assertEqual([], errors)

    def test_missing_pilot_evidence_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            buyer_evidence = root / "buyer"
            payment_env = root / "payment.env"
            write_buyer_agent_evidence(json.loads(MATRIX_PATH.read_text(encoding="utf-8")), buyer_evidence)
            write_payment_env(payment_env)
            args = types.SimpleNamespace(
                checklist=CHECKLIST_PATH,
                pilot_evidence_dir=root / "missing-pilot",
                buyer_agent_matrix=MATRIX_PATH,
                buyer_agent_evidence_dir=buyer_evidence,
                payment_env_file=[payment_env],
                allow_payment_placeholders=False,
            )

            errors = beta_release_readiness_tool.validate_beta_release(args)

        self.assertTrue(any("pilot evidence directory does not exist" in error for error in errors), errors)
        self.assertTrue(any("missing evidence file:" in error for error in errors), errors)

    def test_demo_payment_profile_fails_release_readiness(self) -> None:
        checklist = json.loads(CHECKLIST_PATH.read_text(encoding="utf-8"))
        matrix = json.loads(MATRIX_PATH.read_text(encoding="utf-8"))

        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            pilot_evidence = root / "pilot"
            buyer_evidence = root / "buyer"
            payment_env = root / "payment.env"
            write_pilot_evidence(checklist, pilot_evidence)
            write_buyer_agent_evidence(matrix, buyer_evidence)
            payment_env.write_text(
                "WOOCOMMERCE_MODE=plugin\n"
                "AGENTCART_CHECKOUT_MODE=trusted_token_or_verifier\n"
                "AGENTCART_SIGNED_REQUEST_MODE=off\n",
                encoding="utf-8",
            )
            args = types.SimpleNamespace(
                checklist=CHECKLIST_PATH,
                pilot_evidence_dir=pilot_evidence,
                buyer_agent_matrix=MATRIX_PATH,
                buyer_agent_evidence_dir=buyer_evidence,
                payment_env_file=[payment_env],
                allow_payment_placeholders=False,
            )

            errors = beta_release_readiness_tool.validate_beta_release(args)

        self.assertTrue(any("external_verifier_only" in error for error in errors), errors)
        self.assertTrue(any("AGENTCART_PAYMENT_VERIFIER_TOKEN" in error for error in errors), errors)


if __name__ == "__main__":
    unittest.main()
