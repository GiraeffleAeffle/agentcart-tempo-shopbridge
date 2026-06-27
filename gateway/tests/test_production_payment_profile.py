from __future__ import annotations

import importlib.util
import pathlib
import sys
import tempfile
import unittest


ROOT_DIR = pathlib.Path(__file__).resolve().parents[2]
TOOL_PATH = ROOT_DIR / "scripts" / "check-production-payment-profile.py"
SPEC = importlib.util.spec_from_file_location("production_payment_profile_tool", TOOL_PATH)
production_payment_profile_tool = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules["production_payment_profile_tool"] = production_payment_profile_tool
SPEC.loader.exec_module(production_payment_profile_tool)


def valid_profile() -> dict[str, str]:
    return {
        "WOOCOMMERCE_MODE": "plugin",
        "AGENTCART_CHECKOUT_MODE": "external_verifier_only",
        "AGENTCART_PAYMENT_VERIFIER_URL": "https://verifier.agentcart.test/stripe-mpp/verify",
        "AGENTCART_PAYMENT_VERIFIER_TOKEN": "verifier-token",
        "AGENTCART_VERIFIER_REPLAY_STORE_PATH": "/data/verifier/replay-store.json",
        "AGENTCART_VERIFIER_REQUIRE_DURABLE_REPLAY": "true",
        "AGENTCART_SIGNED_REQUEST_MODE": "require_mutations",
        "AGENTCART_SIGNED_REQUEST_SECRET": "shared-signing-secret",
        "WOOCOMMERCE_SIGNED_REQUEST_SECRET": "shared-signing-secret",
    }


class ProductionPaymentProfileTest(unittest.TestCase):
    def test_valid_profile_passes(self) -> None:
        errors = production_payment_profile_tool.validate_profile(valid_profile())

        self.assertEqual([], errors)

    def test_demo_profile_fails(self) -> None:
        profile = valid_profile()
        profile["AGENTCART_CHECKOUT_MODE"] = "trusted_token_or_verifier"
        profile["AGENTCART_SIGNED_REQUEST_MODE"] = "off"

        errors = production_payment_profile_tool.validate_profile(profile)

        self.assertTrue(any("external_verifier_only" in error for error in errors), errors)
        self.assertTrue(any("SIGNED_REQUEST_MODE" in error for error in errors), errors)

    def test_payment_verifier_token_is_required(self) -> None:
        profile = valid_profile()
        profile["AGENTCART_PAYMENT_VERIFIER_TOKEN"] = ""

        errors = production_payment_profile_tool.validate_profile(profile)

        self.assertTrue(any("AGENTCART_PAYMENT_VERIFIER_TOKEN" in error for error in errors), errors)

    def test_hmac_secrets_must_match(self) -> None:
        profile = valid_profile()
        profile["WOOCOMMERCE_SIGNED_REQUEST_SECRET"] = "different-secret"

        errors = production_payment_profile_tool.validate_profile(profile)

        self.assertTrue(any("must match" in error for error in errors), errors)

    def test_checked_in_production_overlay_is_shape_valid(self) -> None:
        values = production_payment_profile_tool.parse_env_files(
            [
                ROOT_DIR / "deploy" / "home-server" / ".env.example",
                ROOT_DIR / "deploy" / "home-server" / ".env.production-payment.example",
            ]
        )

        errors = production_payment_profile_tool.validate_profile(values, allow_placeholders=True)

        self.assertEqual([], errors)

    def test_env_overlays_apply_in_order(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = pathlib.Path(tmp) / "base.env"
            overlay = pathlib.Path(tmp) / "overlay.env"
            base.write_text("AGENTCART_CHECKOUT_MODE=trusted_token_or_verifier\n", encoding="utf-8")
            overlay.write_text("AGENTCART_CHECKOUT_MODE=external_verifier_only\n", encoding="utf-8")

            values = production_payment_profile_tool.parse_env_files([base, overlay])

        self.assertEqual("external_verifier_only", values["AGENTCART_CHECKOUT_MODE"])


if __name__ == "__main__":
    unittest.main()
