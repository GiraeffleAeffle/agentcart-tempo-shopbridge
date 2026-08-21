import json
import os
import pathlib
import socket
import subprocess
import tempfile
import time
import unittest
import urllib.error
import urllib.request


ROOT = pathlib.Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


class StripeMppVerifierProcessTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.port = free_port()
        self.process = None
        self.start_process()

    def start_process(self, env_overrides: dict | None = None, *, require_ready: bool = True) -> None:
        env = os.environ.copy()
        env.update(
            {
                "STRIPE_MPP_VERIFIER_BIND": "127.0.0.1",
                "STRIPE_MPP_VERIFIER_PORT": str(self.port),
                "STRIPE_SANDBOX_SECRET_KEY": "sk_test_process_dummy",
                "STRIPE_PROFILE_ID": "profile_process_dummy",
                "MPP_SECRET_KEY": "m" * 40,
                "AGENTCART_PAYMENT_VERIFIER_TOKEN": "v" * 40,
                "AGENTCART_VERIFIER_REPLAY_STORE_PATH": str(pathlib.Path(self.temp_dir.name) / "replay.json"),
                "AGENTCART_TEMPO_REFUND_MODE": "disabled",
            }
        )
        if env_overrides:
            env.update(env_overrides)
        self.process = subprocess.Popen(
            ["node", "scripts/stripe-mpp-verifier.mjs"],
            cwd=ROOT,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        if require_ready:
            self.wait_for_health()
        else:
            self.wait_for_health_response()

    def stop_process(self) -> None:
        if self.process is None:
            return
        self.process.terminate()
        try:
            self.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait(timeout=5)
        if self.process.stdout:
            self.process.stdout.close()
        self.process = None

    def restart_process(self, env_overrides: dict | None = None, *, require_ready: bool = True) -> None:
        self.stop_process()
        self.port = free_port()
        self.start_process(env_overrides, require_ready=require_ready)

    def tearDown(self) -> None:
        self.stop_process()
        self.temp_dir.cleanup()

    def wait_for_health(self) -> None:
        deadline = time.time() + 10
        while time.time() < deadline:
            if self.process.poll() is not None:
                output = self.process.stdout.read() if self.process.stdout else ""
                self.fail(f"verifier exited early: {output}")
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{self.port}/health", timeout=0.5) as response:
                    payload = json.loads(response.read().decode("utf-8"))
                    if payload.get("ok") is True:
                        return
            except (OSError, json.JSONDecodeError):
                time.sleep(0.1)
        self.fail("verifier did not become healthy before timeout")

    def wait_for_health_response(self) -> dict:
        deadline = time.time() + 10
        while time.time() < deadline:
            if self.process.poll() is not None:
                output = self.process.stdout.read() if self.process.stdout else ""
                self.fail(f"verifier exited early: {output}")
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{self.port}/health", timeout=0.5) as response:
                    return json.loads(response.read().decode("utf-8"))
            except urllib.error.HTTPError as error:
                try:
                    return json.loads(error.read().decode("utf-8"))
                finally:
                    error.close()
            except (OSError, json.JSONDecodeError):
                time.sleep(0.1)
        self.fail("verifier health endpoint did not respond before timeout")

    def post_verify(self, payload: dict) -> tuple[int, dict]:
        request = urllib.request.Request(
            f"http://127.0.0.1:{self.port}/agentcart/verify",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "authorization": "Bearer " + ("v" * 40),
                "content-type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=5) as response:
                return response.status, json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            try:
                return error.code, json.loads(error.read().decode("utf-8"))
            finally:
                error.close()

    def test_tempo_payment_response_retains_payer_address(self) -> None:
        reference = f"process-payer-test-{time.time_ns()}"
        payload = {
            "operation": "payment",
            "quote_hash": "a" * 64,
            "payment_contract_hash": "b" * 64,
            "payment_receipt": {
                "method": "tempo-mpp",
                "rail": "tempo-mpp",
                "amount_cents": 1490,
                "currency": "USD",
                "quote_hash": "a" * 64,
                "payment_contract_hash": "b" * 64,
                "external_value_proof": {
                    "provider": "tempo_mpp",
                    "state": "succeeded",
                    "amount": "14.90",
                    "network": "testnet",
                    "recipient": "0x1111111111111111111111111111111111111111",
                    "payer_address": "0x2222222222222222222222222222222222222222",
                    "payer_source": "did:pkh:eip155:42431:0x2222222222222222222222222222222222222222",
                    "transaction_reference": reference,
                    "payment_receipt": {"method": "tempo", "status": "success", "reference": reference},
                },
            },
            "expected": {
                "amount_cents": 1490,
                "currency": "USD",
                "merchant_id": "agentcart-usd-staging-shop",
                "rail": "tempo-mpp",
                "payment_contract_hash": "b" * 64,
                "tempo_network": "testnet",
                "tempo_recipient": "0x1111111111111111111111111111111111111111",
            },
        }

        status, body = self.post_verify(payload)

        self.assertEqual(status, 200, body)
        self.assertEqual(body["payer_address"], "0x2222222222222222222222222222222222222222")
        self.assertEqual(body["payer_source"], "did:pkh:eip155:42431:0x2222222222222222222222222222222222222222")

    def test_weak_or_reused_verifier_credentials_fail_readiness(self) -> None:
        self.restart_process(
            {
                "AGENTCART_PAYMENT_VERIFIER_TOKEN": "short",
                "MPP_SECRET_KEY": "short",
            },
            require_ready=False,
        )

        health = self.wait_for_health_response()

        self.assertFalse(health["ok"])
        self.assertTrue(any("minimum 32 characters" in error for error in health["configuration_errors"]))

        shared = "z" * 40
        self.restart_process(
            {
                "AGENTCART_PAYMENT_VERIFIER_TOKEN": shared,
                "MPP_SECRET_KEY": shared,
            },
            require_ready=False,
        )

        reused_health = self.wait_for_health_response()

        self.assertFalse(reused_health["ok"])
        self.assertTrue(any("distinct credentials" in error for error in reused_health["configuration_errors"]))

    def test_tempo_only_profile_does_not_require_stripe_credentials(self) -> None:
        self.restart_process(
            {
                "AGENTCART_VERIFIER_ENABLED_RAILS": "tempo-mpp",
                "STRIPE_SANDBOX_SECRET_KEY": "",
                "STRIPE_PROFILE_ID": "",
                "MPP_SECRET_KEY": "",
            }
        )

        with urllib.request.urlopen(f"http://127.0.0.1:{self.port}/health", timeout=2) as response:
            health = json.loads(response.read().decode("utf-8"))

        self.assertTrue(health["ok"], health)
        self.assertEqual(health["enabled_rails"], ["tempo-mpp"])
        self.assertNotIn("STRIPE_SANDBOX_SECRET_KEY", health["missing"])
        self.assertNotIn("STRIPE_PROFILE_ID", health["missing"])
        self.assertNotIn("MPP_SECRET_KEY", health["missing"])

        status, body = self.post_verify(
            {
                "operation": "payment",
                "quote_hash": "a" * 64,
                "payment_contract_hash": "b" * 64,
                "payment_receipt": {"method": "stripe-card-mpp"},
                "expected": {
                    "amount_cents": 1490,
                    "currency": "USD",
                    "merchant_id": "agentcart-usd-staging-shop",
                    "rail": "stripe-card-mpp",
                    "payment_contract_hash": "b" * 64,
                },
            }
        )
        self.assertEqual(status, 400, body)
        self.assertIn("disabled", body["error"])

    def test_unknown_enabled_rail_fails_readiness(self) -> None:
        self.restart_process(
            {"AGENTCART_VERIFIER_ENABLED_RAILS": "tempo-mpp,typo-rail"},
            require_ready=False,
        )

        health = self.wait_for_health_response()

        self.assertFalse(health["ok"])
        self.assertEqual(health["enabled_rails"], ["tempo-mpp"])
        self.assertTrue(
            any("unsupported rails: typo-rail" in error for error in health["configuration_errors"]),
            health,
        )

    def test_verifier_auth_is_checked_before_json_parsing(self) -> None:
        request = urllib.request.Request(
            f"http://127.0.0.1:{self.port}/agentcart/verify",
            data=b"not-json",
            headers={"content-type": "application/json"},
            method="POST",
        )

        with self.assertRaises(urllib.error.HTTPError) as raised:
            urllib.request.urlopen(request, timeout=5)

        try:
            self.assertEqual(raised.exception.code, 401)
        finally:
            raised.exception.close()

    def test_tempo_refund_disabled_adapter_rejects_explicitly(self) -> None:
        fixture = REPO_ROOT / "docs" / "fixtures" / "verifier" / "refund-request.tempo-mpp.json"
        payload = json.loads(fixture.read_text(encoding="utf-8"))
        payload["refund"]["requested_reference"] = f"refund-disabled-{time.time_ns()}"

        status, body = self.post_verify(payload)

        self.assertEqual(status, 400, body)
        self.assertEqual(body["provider_error_class"], "tempo_refund_adapter_missing")
        self.assertIn("Tempo refund adapter is not configured", body["error"])

    def test_tempo_settlement_verify_mode_rejects_non_transaction_hash(self) -> None:
        self.restart_process({"AGENTCART_TEMPO_SETTLEMENT_MODE": "verify"})
        payload = {
            "operation": "payment",
            "quote_hash": "a" * 64,
            "payment_contract_hash": "b" * 64,
            "payment_receipt": {
                "method": "tempo-mpp",
                "rail": "tempo-mpp",
                "amount_cents": 1490,
                "currency": "USD",
                "quote_hash": "a" * 64,
                "payment_contract_hash": "b" * 64,
                "external_value_proof": {
                    "provider": "tempo_mpp",
                    "state": "succeeded",
                    "amount": "14.90",
                    "network": "testnet",
                    "recipient": "0x1111111111111111111111111111111111111111",
                    "payer_address": "0x2222222222222222222222222222222222222222",
                    "transaction_reference": "not-a-transaction-hash",
                },
            },
            "expected": {
                "amount_cents": 1490,
                "currency": "USD",
                "merchant_id": "agentcart-usd-staging-shop",
                "rail": "tempo-mpp",
                "payment_contract_hash": "b" * 64,
                "tempo_network": "testnet",
                "tempo_recipient": "0x1111111111111111111111111111111111111111",
            },
        }

        status, body = self.post_verify(payload)

        self.assertEqual(status, 400, body)
        self.assertEqual(body["provider_error_class"], "tempo_settlement_reference_invalid")
        self.assertIn("transaction reference must be an EVM transaction hash", body["error"])


if __name__ == "__main__":
    unittest.main()
