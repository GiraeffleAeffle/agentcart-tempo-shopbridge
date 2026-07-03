// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {AgentCartMerchantRegistry} from "../contracts/AgentCartMerchantRegistry.sol";
import {IAgentCartMerchantRegistry} from "../contracts/interfaces/IAgentCartMerchantRegistry.sol";

interface Vm {
    function prank(address sender) external;
    function expectRevert(bytes calldata revertData) external;
}

contract AgentCartMerchantRegistryTest {
    Vm private constant VM = Vm(address(uint160(uint256(keccak256("hevm cheat code")))));

    AgentCartMerchantRegistry private registry;

    address private constant MERCHANT = address(0x1000000000000000000000000000000000000001);
    address private constant MERCHANT_2 = address(0x1000000000000000000000000000000000000002);
    address private constant VALIDATOR = address(0x2000000000000000000000000000000000000001);
    address private constant NEW_CONTROLLER = address(0x3000000000000000000000000000000000000001);

    bytes32 private constant DOMAIN_HASH = keccak256("fixture-shop.example");
    bytes32 private constant RECORD_HASH = keccak256("record-v1");
    bytes32 private constant RECORD_HASH_2 = keccak256("record-v2");
    bytes32 private constant RESULT_HASH = keccak256("validator-result");
    bytes32 private constant REASON_HASH = keccak256("merchant-revoke");
    bytes32 private constant FLAG_TYPE = keccak256("domain_proof_mismatch");

    string private constant RECORD_URI = "https://fixture-shop.example/.well-known/agentcart-registry-bundle.json";
    string private constant EVIDENCE_URI = "https://registry.agentcart.eu/evidence/fixture-shop";

    function setUp() public {
        registry = new AgentCartMerchantRegistry(address(this));
        registry.setValidator(VALIDATOR, true);
    }

    function testRegisterStoresRecordAndDomainIndex() public {
        bytes32 recordId = _register(MERCHANT, RECORD_HASH);
        IAgentCartMerchantRegistry.Record memory stored = registry.record(recordId);

        require(stored.controller == MERCHANT, "controller mismatch");
        require(stored.recordHash == RECORD_HASH, "record hash mismatch");
        require(stored.domainHash == DOMAIN_HASH, "domain hash mismatch");
        require(stored.status == IAgentCartMerchantRegistry.Status.Active, "status mismatch");
        require(registry.recordIdForDomain(DOMAIN_HASH) == recordId, "domain index mismatch");
    }

    function testUpdateClearsAttestationAndRejectsOldHash() public {
        bytes32 recordId = _registerAndAttest();

        VM.prank(MERCHANT);
        registry.update(recordId, RECORD_HASH_2, RECORD_URI);

        IAgentCartMerchantRegistry.Record memory stored = registry.record(recordId);
        require(stored.recordHash == RECORD_HASH_2, "updated hash mismatch");
        require(stored.attestedAt == 0, "attestation timestamp not cleared");
        require(stored.attestationExpiresAt == 0, "attestation expiry not cleared");

        VM.prank(VALIDATOR);
        VM.expectRevert(
            abi.encodeWithSelector(AgentCartMerchantRegistry.RecordHashMismatch.selector, RECORD_HASH_2, RECORD_HASH)
        );
        registry.attest(recordId, RECORD_HASH, RESULT_HASH, uint64(block.timestamp + 1 days), EVIDENCE_URI);
    }

    function testControllerRotationClearsAttestation() public {
        bytes32 recordId = _registerAndAttest();

        VM.prank(MERCHANT);
        registry.setController(recordId, NEW_CONTROLLER);

        IAgentCartMerchantRegistry.Record memory stored = registry.record(recordId);
        require(stored.controller == NEW_CONTROLLER, "controller not rotated");
        require(stored.attestedAt == 0, "attestation timestamp not cleared");
        require(stored.attestationExpiresAt == 0, "attestation expiry not cleared");
    }

    function testRevokeIsMonotonicAndFreesDomain() public {
        bytes32 recordId = _register(MERCHANT, RECORD_HASH);

        VM.prank(MERCHANT);
        registry.revoke(recordId, REASON_HASH);

        IAgentCartMerchantRegistry.Record memory stored = registry.record(recordId);
        require(stored.status == IAgentCartMerchantRegistry.Status.Revoked, "not revoked");
        require(registry.revokedRecordHashes(RECORD_HASH), "record hash not revoked");
        require(registry.recordIdForDomain(DOMAIN_HASH) == bytes32(0), "domain not released");

        VM.prank(MERCHANT_2);
        VM.expectRevert(abi.encodeWithSelector(AgentCartMerchantRegistry.RevokedRecordHash.selector, RECORD_HASH));
        registry.register(DOMAIN_HASH, RECORD_HASH, RECORD_URI);

        _register(MERCHANT_2, RECORD_HASH_2);
    }

    function testSuspendClearsAttestationAndFlagIsEventOnly() public {
        bytes32 recordId = _registerAndAttest();

        VM.prank(VALIDATOR);
        registry.flag(recordId, FLAG_TYPE, EVIDENCE_URI);
        require(registry.record(recordId).status == IAgentCartMerchantRegistry.Status.Active, "flag changed status");

        VM.prank(VALIDATOR);
        registry.suspend(recordId, REASON_HASH);
        IAgentCartMerchantRegistry.Record memory stored = registry.record(recordId);
        require(stored.status == IAgentCartMerchantRegistry.Status.Suspended, "not suspended");
        require(stored.attestedAt == 0, "attestation timestamp not cleared");
        require(stored.attestationExpiresAt == 0, "attestation expiry not cleared");
    }

    function _register(address controller, bytes32 recordHash) private returns (bytes32 recordId) {
        VM.prank(controller);
        return registry.register(DOMAIN_HASH, recordHash, RECORD_URI);
    }

    function _registerAndAttest() private returns (bytes32 recordId) {
        recordId = _register(MERCHANT, RECORD_HASH);

        VM.prank(VALIDATOR);
        registry.attest(recordId, RECORD_HASH, RESULT_HASH, uint64(block.timestamp + 1 days), EVIDENCE_URI);

        require(registry.isAttestationCurrent(recordId), "not attested");
    }
}
