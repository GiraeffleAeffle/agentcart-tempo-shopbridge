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
        env = os.environ.copy()
        env.update(
            {
                "STRIPE_MPP_VERIFIER_BIND": "127.0.0.1",
                "STRIPE_MPP_VERIFIER_PORT": str(self.port),
                "STRIPE_SANDBOX_SECRET_KEY": "sk_test_process_dummy",
                "STRIPE_PROFILE_ID": "profile_process_dummy",
                "MPP_SECRET_KEY": "mpp_process_dummy",
                "AGENTCART_PAYMENT_VERIFIER_TOKEN": "process-token",
                "AGENTCART_VERIFIER_REPLAY_STORE_PATH": str(pathlib.Path(self.temp_dir.name) / "replay.json"),
                "AGENTCART_TEMPO_REFUND_MODE": "disabled",
            }
        )
        self.process = subprocess.Popen(
            ["node", "scripts/stripe-mpp-verifier.mjs"],
            cwd=ROOT,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        self.wait_for_health()

    def tearDown(self) -> None:
        self.process.terminate()
        try:
            self.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait(timeout=5)
        if self.process.stdout:
            self.process.stdout.close()
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

    def post_verify(self, payload: dict) -> tuple[int, dict]:
        request = urllib.request.Request(
            f"http://127.0.0.1:{self.port}/agentcart/verify",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "authorization": "Bearer process-token",
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

    def test_tempo_refund_disabled_adapter_rejects_explicitly(self) -> None:
        fixture = REPO_ROOT / "docs" / "fixtures" / "verifier" / "refund-request.tempo-mpp.json"
        payload = json.loads(fixture.read_text(encoding="utf-8"))
        payload["refund"]["requested_reference"] = f"refund-disabled-{time.time_ns()}"

        status, body = self.post_verify(payload)

        self.assertEqual(status, 400, body)
        self.assertEqual(body["provider_error_class"], "tempo_refund_adapter_missing")
        self.assertIn("Tempo refund adapter is not configured", body["error"])


if __name__ == "__main__":
    unittest.main()
