from __future__ import annotations

import copy
import importlib.util
import json
import pathlib
import sys
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
TOOL_PATH = ROOT / "gateway" / "scripts" / "registry_record.py"
TRUST_FIXTURE_PATH = ROOT / "docs" / "fixtures" / "registry" / "trust-fixtures.json"
ONCHAIN_CONTRACT_PATH = ROOT / "docs" / "fixtures" / "registry" / "onchain-adapter-contract.json"
SPEC = importlib.util.spec_from_file_location("registry_record_tool", TOOL_PATH)
registry_record_tool = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules["registry_record_tool"] = registry_record_tool
SPEC.loader.exec_module(registry_record_tool)


def shopbridge_manifest() -> dict[str, object]:
    return {
        "merchant": {
            "id": "merchant-tea-shop",
            "name": "Merchant Tea Shop",
            "merchant_of_record": {
                "name": "Merchant Tea Shop GmbH",
                "country": "DE",
                "support_email": "support@merchant.example",
            },
            "terms_url": "https://merchant.example/terms",
            "returns_url": "https://merchant.example/returns",
        },
        "manifest_url": "https://merchant.example/.well-known/agentcart.json",
        "protocols": [
            {
                "id": "agentcart-shopbridge",
                "version": "0.1",
                "role": "merchant_catalog_quote_checkout",
            },
            {
                "id": "tempo-mpp",
                "network": "testnet",
                "recipient": "0x1111111111111111111111111111111111111111",
            },
        ],
        "delivery": {
            "ship_to_countries": ["DE", "AT", "DE"],
        },
        "endpoints": {
            "catalog": "https://merchant.example/wp-json/agentcart/v1/catalog",
            "quote": "https://merchant.example/wp-json/agentcart/v1/quote",
        },
        "discovery": {
            "registry_proof": {
                "signature_alg": "https-domain-proof",
                "url": "https://merchant.example/.well-known/agentcart-registry-proof.json",
            },
        },
    }


def shopbridge_profile_manifest() -> dict[str, object]:
    manifest = shopbridge_manifest()
    manifest["protocols"] = [{"id": "agentcart-shopbridge"}]
    manifest["protocol_profiles"] = [
        {"id": "agentcart-shopbridge", "type": "commerce", "status": "available"},
        {
            "id": "mpp-http-auth",
            "type": "payment",
            "payment_protocol_id": "tempo-mpp",
            "status": "available",
            "network": "testnet",
            "recipient": "0x1111111111111111111111111111111111111111",
        },
        {
            "id": "stripe-card-mpp",
            "type": "payment",
            "payment_protocol_id": "stripe-card-mpp",
            "status": "available",
            "network_id": "acct_shop_123",
        },
    ]
    return manifest


def shopbridge_manifest_with_published_claim() -> dict[str, object]:
    manifest = shopbridge_manifest()
    manifest["discovery"] = {
        "registry_proof": {
            "signature_alg": "https-domain-proof",
            "url": "https://merchant.example/.well-known/agentcart-registry-proof.json",
        }
    }
    claim = registry_record_tool.registry_claim(manifest)
    claim["revocation_url"] = "https://merchant.example/.well-known/agentcart-registry-revocations.json"
    record = {
        **claim,
        "registry_claim_hash_alg": "sha-256",
        "registry_claim_hash": registry_record_tool.agentcart.canonical_json_hash(claim),
        "updated_at": registry_record_tool.iso_now(),
        "revoked_at": None,
        "signature_alg": "https-domain-proof",
        "signature": "",
        "proof": {
            "type": "https-well-known",
            "url": "https://merchant.example/.well-known/agentcart-registry-proof.json",
        },
    }
    manifest["discovery"] = {
        "registry_proof": {
            "signature_alg": "https-domain-proof",
            "url": "https://merchant.example/.well-known/agentcart-registry-proof.json",
        },
        "registry_claim_hash_alg": "sha-256",
        "registry_claim_hash": record["registry_claim_hash"],
        "registry_claim": claim,
        "registry_record_hash": registry_record_tool.agentcart.registry_record_hash(record),
        "registry_updated_at": record["updated_at"],
        "registry_ready": True,
        "suggested_registry_record": record,
        "revocation_url": record["revocation_url"],
    }
    return manifest


def revocation_document(record: dict[str, object], revocations: list[dict[str, object]] | None = None) -> dict[str, object]:
    return {
        "type": "agentcart-registry-revocations",
        "merchant_id": record["merchant_id"],
        "domain": record["domain"],
        "updated_at": record["updated_at"],
        "revocations": revocations or [],
    }


def registry_trust_fixture() -> dict[str, object]:
    return json.loads(TRUST_FIXTURE_PATH.read_text(encoding="utf-8"))


def onchain_contract_fixture() -> dict[str, object]:
    return json.loads(ONCHAIN_CONTRACT_PATH.read_text(encoding="utf-8"))


class RegistryRecordToolTests(unittest.TestCase):
    def test_builds_legacy_domain_proof_record_and_paste_back_settings(self) -> None:
        manifest = shopbridge_manifest()
        record = registry_record_tool.build_registry_record(
            manifest,
            updated_at=registry_record_tool.iso_now(),
        )
        bundle = registry_record_tool.onboarding_bundle(record)

        self.assertEqual(record["merchant_id"], "merchant-tea-shop")
        self.assertEqual(record["domain"], "merchant.example")
        self.assertEqual(record["manifest_hash"], registry_record_tool.agentcart.canonical_json_hash(manifest))
        self.assertEqual(record["ship_to_countries"], ["AT", "DE"])
        self.assertEqual(record["payment_network"], "testnet")
        self.assertEqual(record["payment_recipient"], "0x1111111111111111111111111111111111111111")
        self.assertEqual(record["signature_alg"], "https-domain-proof")
        self.assertEqual(
            record["proof"]["url"],
            "https://merchant.example/.well-known/agentcart-registry-proof.json",
        )
        self.assertEqual(
            bundle["legacy_merchant_settings"]["AGENTCART_REGISTRY_RECORD_HASH"],
            registry_record_tool.agentcart.registry_record_hash(record),
        )
        self.assertEqual(
            bundle["legacy_merchant_settings"]["AGENTCART_REGISTRY_MANIFEST_HASH"],
            registry_record_tool.agentcart.canonical_json_hash(manifest),
        )

    def test_builds_record_from_protocol_profiles_without_legacy_payment_protocols(self) -> None:
        manifest = shopbridge_profile_manifest()
        claim = registry_record_tool.registry_claim(manifest)

        self.assertEqual(claim["payment_network"], "testnet")
        self.assertEqual(claim["payment_recipient"], "0x1111111111111111111111111111111111111111")
        self.assertEqual(claim["stripe_profile_id"], "acct_shop_123")
        self.assertEqual(claim["protocol_profile_ids"], ["agentcart-shopbridge", "mpp-http-auth", "stripe-card-mpp"])
        self.assertIn("tempo-mpp", claim["supported_protocols"])
        self.assertIn("stripe-card-mpp", claim["supported_protocols"])

    def test_env_format_says_no_paste_back_for_auto_managed_claim(self) -> None:
        manifest = shopbridge_manifest_with_published_claim()
        with tempfile.TemporaryDirectory() as raw_tmp:
            tmp = pathlib.Path(raw_tmp)
            manifest_file = tmp / "manifest.json"
            output_file = tmp / "env.txt"
            manifest_file.write_text(json.dumps(manifest))

            exit_code = registry_record_tool.main([
                "build",
                "--manifest-file",
                str(manifest_file),
                "--format",
                "env",
                "--output",
                str(output_file),
            ])

            self.assertEqual(exit_code, 0)
            self.assertEqual(
                output_file.read_text(),
                "# no merchant env paste-back is required for this ShopBridge manifest\n",
            )

    def test_build_prefers_auto_managed_shopbridge_registry_claim(self) -> None:
        manifest = shopbridge_manifest_with_published_claim()

        record = registry_record_tool.build_registry_record(manifest)
        bundle = registry_record_tool.onboarding_bundle(record)

        self.assertNotIn("manifest_hash", record)
        self.assertEqual(record, manifest["discovery"]["suggested_registry_record"])
        self.assertEqual(
            record["registry_claim_hash"],
            registry_record_tool.agentcart.canonical_json_hash(manifest["discovery"]["registry_claim"]),
        )
        self.assertEqual(bundle["legacy_merchant_settings"], {})
        self.assertIn("auto-publishes", bundle["merchant_action"])

    def test_projects_shared_registry_record_to_onchain_contract_shape(self) -> None:
        trust = registry_trust_fixture()
        contract = onchain_contract_fixture()

        projection = registry_record_tool.onchain_projection(trust["base"]["record"])

        self.assertEqual(projection, contract["sample"]["onchain_record"])
        self.assertTrue(set(contract["required_onchain_fields"]).issubset(projection))
        self.assertTrue(set(contract["offchain_only_fields"]).isdisjoint(projection))

    def test_build_format_onchain_uses_plugin_published_registry_record(self) -> None:
        trust = registry_trust_fixture()
        contract = onchain_contract_fixture()
        with tempfile.TemporaryDirectory() as raw_tmp:
            tmp = pathlib.Path(raw_tmp)
            manifest_file = tmp / "manifest.json"
            output_file = tmp / "onchain.json"
            manifest_file.write_text(json.dumps(trust["base"]["manifest"]), encoding="utf-8")

            exit_code = registry_record_tool.main([
                "build",
                "--manifest-file",
                str(manifest_file),
                "--format",
                "onchain",
                "--output",
                str(output_file),
            ])

            self.assertEqual(exit_code, 0)
            self.assertEqual(json.loads(output_file.read_text(encoding="utf-8")), contract["sample"]["onchain_record"])

    def test_project_onchain_command_accepts_existing_registry_record(self) -> None:
        trust = registry_trust_fixture()
        contract = onchain_contract_fixture()
        with tempfile.TemporaryDirectory() as raw_tmp:
            tmp = pathlib.Path(raw_tmp)
            record_file = tmp / "record.json"
            output_file = tmp / "onchain.json"
            record_file.write_text(json.dumps(trust["base"]["record"]), encoding="utf-8")

            exit_code = registry_record_tool.main([
                "project-onchain",
                "--record-file",
                str(record_file),
                "--output",
                str(output_file),
            ])

            self.assertEqual(exit_code, 0)
            self.assertEqual(json.loads(output_file.read_text(encoding="utf-8")), contract["sample"]["onchain_record"])

    def test_onchain_projection_fails_closed_when_required_claim_hash_is_missing(self) -> None:
        trust = registry_trust_fixture()
        record = copy.deepcopy(trust["base"]["record"])
        record.pop("registry_claim_hash")

        with self.assertRaisesRegex(ValueError, "registry_claim_hash"):
            registry_record_tool.onchain_projection(record)

    def test_onchain_projection_rejects_malformed_claim_hash(self) -> None:
        trust = registry_trust_fixture()
        record = copy.deepcopy(trust["base"]["record"])
        record["registry_claim_hash"] = "not-a-sha256-hash"

        with self.assertRaisesRegex(ValueError, "SHA-256 hex digest"):
            registry_record_tool.onchain_projection(record)

    def test_auto_managed_shopbridge_registry_claim_verifies(self) -> None:
        manifest = shopbridge_manifest_with_published_claim()
        record = registry_record_tool.build_registry_record(manifest)
        proof = registry_record_tool.domain_proof_document(record)

        result = registry_record_tool.verify_registry_record(
            record,
            manifest_snapshot=manifest,
            proof_snapshot=proof,
            revocation_snapshot=revocation_document(record),
        )

        self.assertTrue(result["ok"], result)
        self.assertEqual(result["verification"]["state"], "verified")
        self.assertEqual(result["entry"]["registry_claim_hash"], record["registry_claim_hash"])

    def test_revoked_auto_managed_shopbridge_registry_record_is_rejected(self) -> None:
        manifest = shopbridge_manifest_with_published_claim()
        record = registry_record_tool.build_registry_record(manifest)
        proof = registry_record_tool.domain_proof_document(record)
        revocation = revocation_document(
            record,
            [
                {
                    "record_hash": registry_record_tool.agentcart.registry_record_hash(record),
                    "revoked_at": registry_record_tool.iso_now(),
                }
            ],
        )

        result = registry_record_tool.verify_registry_record(
            record,
            manifest_snapshot=manifest,
            proof_snapshot=proof,
            revocation_snapshot=revocation,
        )

        self.assertFalse(result["ok"], result)
        self.assertIn("record_revoked_by_revocation_document", result["verification"]["errors"])

    def test_generated_domain_proof_record_verifies_with_snapshots(self) -> None:
        manifest = shopbridge_manifest()
        record = registry_record_tool.build_registry_record(
            manifest,
            updated_at=registry_record_tool.iso_now(),
        )
        proof = registry_record_tool.domain_proof_document(record)

        result = registry_record_tool.verify_registry_record(
            record,
            manifest_snapshot=manifest,
            proof_snapshot=proof,
        )

        self.assertTrue(result["ok"], result)
        self.assertEqual(result["verification"]["state"], "verified")
        self.assertEqual(result["verification"]["signature_alg"], "https-domain-proof")

    def test_builds_hmac_signed_record_for_private_local_feeds(self) -> None:
        manifest = shopbridge_manifest()
        record = registry_record_tool.build_registry_record(
            manifest,
            updated_at=registry_record_tool.iso_now(),
            signature_alg="hmac-sha256",
            hmac_secret="registry-secret",
        )

        result = registry_record_tool.verify_registry_record(
            record,
            manifest_snapshot=manifest,
            hmac_secret="registry-secret",
        )

        self.assertTrue(result["ok"], result)
        self.assertEqual(record["signature_alg"], "hmac-sha256")
        self.assertTrue(str(record["signature"]).startswith("hmac-sha256:"))


if __name__ == "__main__":
    unittest.main()
