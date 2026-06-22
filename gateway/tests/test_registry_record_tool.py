from __future__ import annotations

import importlib.util
import pathlib
import sys
import unittest


TOOL_PATH = pathlib.Path(__file__).resolve().parents[1] / "scripts" / "registry_record.py"
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


class RegistryRecordToolTests(unittest.TestCase):
    def test_builds_domain_proof_record_and_paste_back_settings(self) -> None:
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
            bundle["merchant_settings"]["AGENTCART_REGISTRY_RECORD_HASH"],
            registry_record_tool.agentcart.registry_record_hash(record),
        )
        self.assertEqual(
            bundle["merchant_settings"]["AGENTCART_REGISTRY_MANIFEST_HASH"],
            registry_record_tool.agentcart.canonical_json_hash(manifest),
        )

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
