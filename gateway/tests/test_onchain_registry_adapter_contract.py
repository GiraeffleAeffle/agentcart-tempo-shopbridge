from __future__ import annotations

import json
import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
CONTRACT_PATH = ROOT / "docs" / "fixtures" / "registry" / "onchain-adapter-contract.json"
TRUST_FIXTURE_PATH = ROOT / "docs" / "fixtures" / "registry" / "trust-fixtures.json"


def fixture(path: pathlib.Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


class OnchainRegistryAdapterContractTests(unittest.TestCase):
    def test_onchain_record_is_compact_identity_integrity_projection(self) -> None:
        contract = fixture(CONTRACT_PATH)
        onchain_record = contract["sample"]["onchain_record"]

        self.assertEqual(contract["schema"], "agentcart.onchain_registry_adapter_contract.v1")
        self.assertEqual(contract["source_trust_contract"], "agentcart.registry_trust_contract.v1")
        self.assertTrue(set(contract["required_onchain_fields"]).issubset(onchain_record))

        forbidden = set(contract["offchain_only_fields"])
        self.assertTrue(forbidden.isdisjoint(onchain_record), forbidden.intersection(onchain_record))
        self.assertIn("registry_claim_hash", onchain_record)
        self.assertIn("payment_recipient", onchain_record)

    def test_onchain_sample_projects_the_shared_registry_fixture(self) -> None:
        contract = fixture(CONTRACT_PATH)
        trust = fixture(TRUST_FIXTURE_PATH)
        record = trust["base"]["record"]
        manifest = trust["base"]["manifest"]
        proof = trust["base"]["proof"]
        onchain_record = contract["sample"]["onchain_record"]

        self.assertEqual(onchain_record["record_hash"], proof["record_hash"])
        for key in (
            "merchant_id",
            "domain",
            "manifest_url",
            "registry_claim_hash_alg",
            "registry_claim_hash",
            "payment_network",
            "payment_recipient",
            "updated_at",
            "revocation_url",
            "protocol_profile_ids",
            "supported_protocols",
            "ship_to_countries",
        ):
            self.assertEqual(onchain_record[key], record[key], key)

        onchain_identity = record["onchain_identity"]
        self.assertEqual(onchain_record["chain_id"], onchain_identity["chain_id"])
        self.assertEqual(onchain_record["registry_address"], onchain_identity["registry_address"])
        self.assertEqual(onchain_record["agent_id"], onchain_identity["agent_id"])
        self.assertEqual(onchain_record["registration_uri"], onchain_identity["registration_uri"])
        self.assertEqual(onchain_record["registration_tx_hash"], onchain_identity["registration_tx_hash"])
        self.assertEqual(onchain_record["registry_claim_hash"], manifest["discovery"]["registry_claim_hash"])

    def test_indexer_cache_is_not_the_source_of_truth(self) -> None:
        contract = fixture(CONTRACT_PATH)
        indexer_cache = contract["indexer_cache"]

        self.assertEqual(indexer_cache["source_of_truth"], "smart_contract")
        self.assertIn("onchain_record", indexer_cache["allowed_cache_fields"])
        self.assertIn("private_quotes", indexer_cache["forbidden_cache_fields"])
        self.assertIn("buyer_addresses", indexer_cache["forbidden_cache_fields"])

    def test_staking_hooks_do_not_block_pilot_merchants(self) -> None:
        contract = fixture(CONTRACT_PATH)
        hooks = {hook["id"]: hook for hook in contract["staking_hooks"]}

        self.assertIn("merchant_registration_bond", hooks)
        self.assertIn("validator_attestation_stake", hooks)
        self.assertIn("curator_challenge_bond", hooks)
        self.assertFalse(hooks["merchant_registration_bond"]["required_for_pilot"])
        self.assertFalse(hooks["validator_attestation_stake"]["required_for_pilot"])

    def test_agent_verification_keeps_ranking_buyer_side(self) -> None:
        contract = fixture(CONTRACT_PATH)
        steps = contract["agent_verification_steps"]

        self.assertIn("run_private_quote_requests_and_buyer_side_ranking", steps)
        self.assertIn("Sponsored ranking", contract["non_goals"])
        self.assertIn("Publishing household demand", contract["non_goals"])


if __name__ == "__main__":
    unittest.main()
