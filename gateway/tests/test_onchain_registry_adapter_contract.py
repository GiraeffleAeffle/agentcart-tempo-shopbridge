from __future__ import annotations

import json
import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
CONTRACT_PATH = ROOT / "docs" / "fixtures" / "registry" / "onchain-adapter-contract.json"
CONTRACT_EVENTS_PATH = ROOT / "docs" / "fixtures" / "registry" / "onchain-contract-events.json"
INTERFACE_PATH = ROOT / "contracts" / "interfaces" / "IAgentCartMerchantRegistry.sol"
IMPLEMENTATION_PATH = ROOT / "contracts" / "AgentCartMerchantRegistry.sol"
TRUST_FIXTURE_PATH = ROOT / "docs" / "fixtures" / "registry" / "trust-fixtures.json"


def fixture(path: pathlib.Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def solidity_function_body(source: str, name: str) -> str:
    marker = f"function {name}("
    start = source.index(marker)
    brace = source.index("{", start)
    depth = 0
    for index in range(brace, len(source)):
        if source[index] == "{":
            depth += 1
        elif source[index] == "}":
            depth -= 1
            if depth == 0:
                return source[brace + 1 : index]
    raise AssertionError(f"function body not found: {name}")


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

    def test_contract_storage_is_smaller_than_projection(self) -> None:
        contract = fixture(CONTRACT_PATH)
        storage_fields = set(contract["v1_contract_storage_fields"])
        event_fields = set(contract["event_projection_fields"])

        self.assertIn("controller", storage_fields)
        self.assertIn("record_hash", storage_fields)
        self.assertIn("domain_hash", storage_fields)
        self.assertNotIn("merchant_id", storage_fields)
        self.assertNotIn("payment_recipient", storage_fields)
        self.assertNotIn("ship_to_countries", storage_fields)
        self.assertIn("payment_recipient", event_fields)
        self.assertIn("ship_to_countries", event_fields)
        self.assertEqual(
            contract["controller_bound_proof_fields"],
            ["controller", "chain_id", "registry_address", "record_id", "record_hash"],
        )

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
        self.assertEqual(onchain_record["controller"], onchain_identity["controller"])
        self.assertEqual(onchain_record["registry_address"], onchain_identity["registry_address"])
        self.assertEqual(onchain_record["record_id"], onchain_identity["record_id"])
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
        self.assertIn("verify_controller_bound_domain_proof", steps)
        self.assertIn("apply_configured_attestation_policy", steps)
        self.assertIn("Sponsored ranking", contract["non_goals"])
        self.assertIn("Publishing household demand", contract["non_goals"])

    def test_v1_challenges_are_event_only(self) -> None:
        contract = fixture(CONTRACT_PATH)
        policy = contract["challenge_policy"]

        self.assertEqual(policy["v1_status_effect"], "event_only")
        self.assertFalse(policy["slashing_required_for_pilot"])
        self.assertFalse(policy["merchant_slashing_required_for_v1"])

    def test_solidity_interface_exposes_minimal_v1_events(self) -> None:
        source = INTERFACE_PATH.read_text(encoding="utf-8")

        self.assertIn("interface IAgentCartMerchantRegistry", source)
        for event_name in (
            "MerchantRegistered",
            "MerchantUpdated",
            "ControllerChanged",
            "MerchantRevoked",
            "MerchantForceRevoked",
            "SupersessionRequested",
            "SupersessionApproved",
            "SupersessionCanceled",
            "SupersessionActivated",
            "MerchantAttested",
            "MerchantSuspended",
            "MerchantUnsuspended",
            "MerchantFlagged",
            "ValidatorSet",
            "AttestationThresholdSet",
            "GovernanceActionScheduled",
            "GovernanceActionCanceled",
            "OwnershipTransferStarted",
        ):
            self.assertIn(f"event {event_name}", source)
        self.assertIn("function register(", source)
        self.assertIn("function update(", source)
        self.assertIn("function attest(", source)
        self.assertIn("function attestation(", source)
        self.assertIn("function approveSupersession(", source)
        self.assertIn("function cancelSupersession(", source)
        self.assertIn("function flag(", source)
        self.assertIn("function record(", source)
        self.assertIn("function recordIdForDomain(", source)
        self.assertIn("function revokedRecordHashes(", source)
        self.assertIn("function isAttestationCurrent(", source)
        self.assertIn("function setAttestationThreshold(", source)
        self.assertIn("function scheduleGovernanceAction(", source)
        self.assertIn("function acceptOwnership(", source)

    def test_contract_events_fixture_uses_interface_events(self) -> None:
        source = INTERFACE_PATH.read_text(encoding="utf-8")
        fixture_document = fixture(CONTRACT_EVENTS_PATH)

        self.assertEqual(fixture_document["schema"], "agentcart.onchain_registry_contract_events.v1")
        self.assertEqual(fixture_document["interface"], "contracts/interfaces/IAgentCartMerchantRegistry.sol")
        for event in fixture_document["events"]:
            self.assertIn(f"event {event['event']}", source)
        self.assertEqual(
            fixture_document["events"][0]["onchain_record"],
            fixture(CONTRACT_PATH)["sample"]["onchain_record"],
        )

    def test_solidity_implementation_is_present_and_bound_to_fixture(self) -> None:
        contract = fixture(CONTRACT_PATH)
        source = IMPLEMENTATION_PATH.read_text(encoding="utf-8")

        self.assertEqual(contract["implementation"], "contracts/AgentCartMerchantRegistry.sol")
        self.assertIn("contract AgentCartMerchantRegistry is IAgentCartMerchantRegistry", source)
        self.assertIn("mapping(bytes32 => Record) private _records", source)
        self.assertIn("mapping(bytes32 => mapping(address => Attestation)) private _attestations", source)
        self.assertIn("mapping(bytes32 => bytes32) public recordIdForDomain", source)
        self.assertIn("mapping(bytes32 => bool) public revokedRecordHashes", source)
        self.assertIn("mapping(address => bool) public validators", source)
        self.assertIn("mapping(address => uint64) public validatorEnabledAt", source)
        self.assertIn("mapping(bytes32 => mapping(address => uint64)) public nextFlagAvailableAt", source)
        self.assertIn("mapping(bytes32 => uint64) public governanceActionReadyAt", source)
        self.assertIn("address[] private _validatorList", source)

    def test_solidity_storage_stays_identity_and_integrity_only(self) -> None:
        source = IMPLEMENTATION_PATH.read_text(encoding="utf-8")
        forbidden_state_terms = (
            "catalog",
            "products",
            "prices",
            "quotes",
            "buyer",
            "household",
            "order",
            "ranking",
            "rank",
            "stake",
            "bond",
            "payable",
            "slashing",
        )

        for term in forbidden_state_terms:
            self.assertNotIn(term, source.lower(), term)

    def test_solidity_record_id_is_bound_to_controller_domain_chain_and_contract(self) -> None:
        source = IMPLEMENTATION_PATH.read_text(encoding="utf-8")
        body = solidity_function_body(source, "computeRecordId")

        self.assertIn('"agentcart.merchant.registry.v1"', body)
        self.assertIn("block.chainid", body)
        self.assertIn("address(this)", body)
        self.assertIn("domainHash", body)
        self.assertIn("controller", body)

    def test_solidity_identity_changes_clear_attestation_state(self) -> None:
        source = IMPLEMENTATION_PATH.read_text(encoding="utf-8")
        update_body = solidity_function_body(source, "update")
        controller_body = solidity_function_body(source, "setController")
        suspend_body = solidity_function_body(source, "suspend")
        public_revoke_body = solidity_function_body(source, "revoke")
        revoke_body = solidity_function_body(source, "_revoke")

        for body in (update_body, controller_body, suspend_body, revoke_body):
            self.assertIn("stored.attestedAt = 0", body)
            self.assertIn("stored.attestationExpiresAt = 0", body)
            self.assertIn("stored.attestationGeneration += 1", body)
            self.assertIn("stored.attestationCount = 0", body)
        self.assertIn("stored.recordHash = newRecordHash", controller_body)
        self.assertIn("_requireActiveRecordHash(newRecordHash)", controller_body)
        self.assertIn("_requireNonEmptyUri(recordURI)", controller_body)
        self.assertIn("revokedRecordHashes[stored.recordHash] = true", revoke_body)
        self.assertIn("delete recordIdForDomain[stored.domainHash]", revoke_body)
        self.assertIn("_revoke(recordId, reasonHash)", public_revoke_body)

    def test_solidity_attestation_requires_validator_current_hash_and_expiry(self) -> None:
        source = IMPLEMENTATION_PATH.read_text(encoding="utf-8")
        body = solidity_function_body(source, "attest")

        self.assertIn("onlyValidator", source[source.index("function attest(") : source.index("{", source.index("function attest("))])
        self.assertIn("recordHash != stored.recordHash", body)
        self.assertIn("expiresAt <= block.timestamp", body)
        self.assertIn("validatorAttestation.recordHash = recordHash", body)
        self.assertIn("validatorAttestation.resultHash = resultHash", body)
        self.assertIn("validatorAttestation.expiresAt = expiresAt", body)
        self.assertIn("validatorAttestation.generation = stored.attestationGeneration", body)
        self.assertIn("_syncAttestationSummary(recordId, stored)", body)

    def test_solidity_attestation_summary_recomputes_from_validator_entries(self) -> None:
        source = IMPLEMENTATION_PATH.read_text(encoding="utf-8")
        summary_body = solidity_function_body(source, "_attestationSummary")
        current_body = solidity_function_body(source, "isAttestationCurrent")
        record_body = solidity_function_body(source, "record")

        self.assertIn("_validatorList.length", summary_body)
        self.assertIn("!validators[validator]", summary_body)
        self.assertIn("stored.attestedAt < validatorEnabledAt[validator]", summary_body)
        self.assertIn("stored.generation != recordGeneration", summary_body)
        self.assertIn("stored.recordHash != recordHash", summary_body)
        self.assertIn("stored.expiresAt <= block.timestamp", summary_body)
        self.assertIn("_quorumExpiresAt(expiries, count, attestationThreshold)", summary_body)
        self.assertIn("_attestationSummary(recordId, stored.recordHash, stored.attestationGeneration)", current_body)
        self.assertIn("_attestationSummary(recordId, stored.recordHash, stored.attestationGeneration)", record_body)

    def test_solidity_supersession_requires_approval_before_activation(self) -> None:
        source = IMPLEMENTATION_PATH.read_text(encoding="utf-8")
        request_body = solidity_function_body(source, "requestSupersession")
        approve_body = solidity_function_body(source, "approveSupersession")
        cancel_body = solidity_function_body(source, "cancelSupersession")
        activate_body = solidity_function_body(source, "activateSupersession")

        self.assertIn("approvedBy: address(0)", request_body)
        self.assertIn("approvedAt: 0", request_body)
        self.assertIn("_requireOwnerOrValidator()", approve_body)
        self.assertIn("pending.approvedBy = msg.sender", approve_body)
        self.assertIn("pending.approvedAt = approvedAt", approve_body)
        self.assertIn("emit SupersessionApproved", approve_body)
        self.assertIn("previous.controller == msg.sender", cancel_body)
        self.assertIn("delete _supersessions[pendingRecordId]", cancel_body)
        self.assertIn("pending.approvedAt == 0", activate_body)
        self.assertIn("pending.approvedAt + SUPERSESSION_DELAY_SECONDS", activate_body)

    def test_solidity_sensitive_owner_actions_are_delayed_or_accepted(self) -> None:
        source = IMPLEMENTATION_PATH.read_text(encoding="utf-8")
        validator_body = solidity_function_body(source, "setValidator")
        threshold_body = solidity_function_body(source, "setAttestationThreshold")
        force_revoke_body = solidity_function_body(source, "forceRevoke")
        transfer_body = solidity_function_body(source, "transferOwnership")
        accept_body = solidity_function_body(source, "acceptOwnership")
        consume_body = solidity_function_body(source, "_consumeGovernanceAction")

        self.assertIn("_consumeGovernanceAction(validatorActionHash(validator, enabled))", validator_body)
        self.assertIn("_consumeGovernanceAction(attestationThresholdActionHash(threshold))", threshold_body)
        self.assertIn("_consumeGovernanceAction(forceRevokeActionHash(recordId, reasonHash))", force_revoke_body)
        self.assertIn("pendingOwner = newOwner", transfer_body)
        self.assertNotIn("owner = newOwner", transfer_body)
        self.assertIn("msg.sender != pendingOwner", accept_body)
        self.assertIn("owner = msg.sender", accept_body)
        self.assertIn("GOVERNANCE_EXECUTION_WINDOW_SECONDS", consume_body)
        self.assertIn("GovernanceActionExpired", consume_body)

    def test_solidity_flags_are_event_only(self) -> None:
        source = IMPLEMENTATION_PATH.read_text(encoding="utf-8")
        body = solidity_function_body(source, "flag")

        self.assertIn("emit MerchantFlagged", body)
        self.assertNotIn("status", body)
        self.assertNotIn("recordIdForDomain", body)
        self.assertNotIn("revokedRecordHashes", body)


if __name__ == "__main__":
    unittest.main()
