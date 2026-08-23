from __future__ import annotations

import importlib.util
import pathlib
import sys
import tempfile
import unittest


ROOT_DIR = pathlib.Path(__file__).resolve().parents[2]
TOOL_PATH = ROOT_DIR / "scripts" / "check-production-payment-profile.py"
USD_COMPOSE_TEMPLATE = ROOT_DIR / "deploy" / "hetzner-staging" / "ansible" / "templates" / "usd-docker-compose.yml.j2"
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
        "AGENTCART_PAYMENT_VERIFIER_TOKEN": "v" * 40,
        "AGENTCART_VERIFIER_REPLAY_STORE_DRIVER": "sqlite",
        "AGENTCART_VERIFIER_REPLAY_STORE_PATH": "/data/verifier/replay-store.sqlite",
        "AGENTCART_VERIFIER_REQUIRE_DURABLE_REPLAY": "true",
        "AGENTCART_SIGNED_REQUEST_MODE": "require_mutations",
        "AGENTCART_SIGNED_REQUEST_SECRET": "s" * 40,
        "WOOCOMMERCE_SIGNED_REQUEST_SECRET": "s" * 40,
        "WOOCOMMERCE_AGENTCART_TOKEN": "m" * 40,
        "AGENTCART_ALLOW_PRIVATE_PAYMENT_VERIFIER_URL": "false",
    }


def valid_hetzner_usd_staging_secrets() -> dict[str, str]:
    return {
        "STAGING_DOMAIN": "woo-usd.agentcart.test",
        "STAGING_SHOPBRIDGE_TOKEN": "m" * 64,
        "STAGING_PAYMENT_VERIFIER_TOKEN": "v" * 64,
        "STAGING_MPP_SECRET_KEY": "p" * 44,
        "STAGING_SIGNED_REQUEST_MODE": "require_checkout",
        "STAGING_SIGNED_REQUEST_SECRET": "s" * 64,
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

    def test_shared_secrets_must_be_strong_and_separated(self) -> None:
        weak = valid_profile()
        weak["AGENTCART_PAYMENT_VERIFIER_TOKEN"] = "short-token"

        weak_errors = production_payment_profile_tool.validate_profile(weak)

        self.assertTrue(any("at least 32 characters" in error for error in weak_errors), weak_errors)

        reused = valid_profile()
        reused["AGENTCART_PAYMENT_VERIFIER_TOKEN"] = reused["AGENTCART_SIGNED_REQUEST_SECRET"]

        reused_errors = production_payment_profile_tool.validate_profile(reused)

        self.assertTrue(any("must be distinct" in error for error in reused_errors), reused_errors)

    def test_production_replay_store_driver_must_be_sqlite(self) -> None:
        profile = valid_profile()
        profile["AGENTCART_VERIFIER_REPLAY_STORE_DRIVER"] = "json"

        errors = production_payment_profile_tool.validate_profile(profile)

        self.assertTrue(any("REPLAY_STORE_DRIVER" in error for error in errors), errors)

    def test_hmac_secrets_must_match(self) -> None:
        profile = valid_profile()
        profile["WOOCOMMERCE_SIGNED_REQUEST_SECRET"] = "different-secret"

        errors = production_payment_profile_tool.validate_profile(profile)

        self.assertTrue(any("must match" in error for error in errors), errors)

    def test_private_payment_verifier_urls_are_not_allowed_for_production(self) -> None:
        profile = valid_profile()
        profile["AGENTCART_ALLOW_PRIVATE_PAYMENT_VERIFIER_URL"] = "true"

        errors = production_payment_profile_tool.validate_profile(profile)

        self.assertTrue(any("ALLOW_PRIVATE_PAYMENT_VERIFIER_URL" in error for error in errors), errors)

    def test_pinned_internal_verifier_is_accepted_only_for_explicit_trust_mode(self) -> None:
        profile = valid_profile()
        profile["AGENTCART_PAYMENT_VERIFIER_URL"] = "http://agentcart-usd-verifier:4260/agentcart/verify"
        profile["AGENTCART_ALLOW_PRIVATE_PAYMENT_VERIFIER_URL"] = "true"
        profile["AGENTCART_PAYMENT_VERIFIER_TRUST_MODE"] = "pinned_internal"

        errors = production_payment_profile_tool.validate_profile(profile)

        self.assertEqual([], errors)

        profile["AGENTCART_PAYMENT_VERIFIER_URL"] = "http://127.0.0.1:4260/agentcart/verify"
        loopback_errors = production_payment_profile_tool.validate_profile(profile)

        self.assertTrue(any("loopback" in error for error in loopback_errors), loopback_errors)

    def test_hetzner_usd_profile_normalizes_provisioning_keys(self) -> None:
        profile = production_payment_profile_tool.apply_deployment_profile(
            valid_hetzner_usd_staging_secrets(),
            "hetzner-usd-staging",
        )

        errors = production_payment_profile_tool.validate_profile(profile)

        self.assertEqual([], errors)
        self.assertEqual("sqlite", profile["AGENTCART_VERIFIER_REPLAY_STORE_DRIVER"])
        self.assertEqual("pinned_internal", profile["AGENTCART_PAYMENT_VERIFIER_TRUST_MODE"])
        self.assertEqual(profile["AGENTCART_SIGNED_REQUEST_SECRET"], profile["WOOCOMMERCE_SIGNED_REQUEST_SECRET"])

    def test_talos_usd_profile_uses_the_cluster_local_verifier_service(self) -> None:
        profile = production_payment_profile_tool.apply_deployment_profile(
            valid_hetzner_usd_staging_secrets(),
            "talos-usd-staging",
        )

        errors = production_payment_profile_tool.validate_profile(profile)

        self.assertEqual([], errors)
        self.assertEqual("talos-usd-staging", profile["AGENTCART_DEPLOYMENT_PROFILE"])
        self.assertEqual(
            "http://woo-usd-verifier:4260/agentcart/verify",
            profile["AGENTCART_PAYMENT_VERIFIER_URL"],
        )

    def test_hetzner_usd_compose_uses_sqlite_and_pinned_internal_verifier(self) -> None:
        template = USD_COMPOSE_TEMPLATE.read_text(encoding="utf-8")

        self.assertIn("AGENTCART_VERIFIER_REPLAY_STORE_DRIVER: sqlite", template)
        self.assertIn("AGENTCART_VERIFIER_REPLAY_STORE_PATH: /data/replay-store.sqlite", template)
        self.assertIn("AGENTCART_PAYMENT_VERIFIER_TRUST_MODE: pinned_internal", template)
        self.assertIn("dockerfile: Dockerfile", template)

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
